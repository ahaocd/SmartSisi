#include "application.h"
#include "board.h"
// #include "display.h" // 移除旧 display 依赖
#include "system_info.h"
#include "ml307_ssl_transport.h"
#include "audio_codec.h"
#include "mqtt_protocol.h"
#include "websocket_protocol.h"
#include "font_awesome_symbols.h"
#include "iot/thing_manager.h"
#include "assets/lang_config.h"


#include <cstring>
#include <esp_log.h>
#include <cJSON.h>
#include <driver/gpio.h>
#include <arpa/inet.h>
#include <esp_app_desc.h>

#include "driver/uart.h" // 为 UART 任务添加
#include <vector>        // 为 std::vector 添加
#include <cmath>         // 为 log10 函数添加

// --- 引入FFT库 ---
#include "esp_dsp.h"

#define TAG "Application"

// Barge-in via VAD (device-side) with suppression windows.
// These are conservative defaults to reduce echo-triggered aborts.
static constexpr int64_t kBargeInHoldMs = 200;      // ignore VAD right after TTS starts
static constexpr int64_t kBargeInCooldownMs = 800;  // avoid repeated aborts

// --- 全局变量和任务声明 ---
#ifndef CONFIG_BOARD_TYPE_FOGSEEK_ESP32_S3
#define SISI_SPECTRUM_POINTS 8
static std::vector<uint8_t> g_spectrum_data(SISI_SPECTRUM_POINTS, 0);
static std::mutex g_spectrum_mutex;
#endif
#define UART_BUF_SIZE (256) // 稍微增大缓冲区

// 任务函数：渲染声波动画
#ifndef CONFIG_BOARD_TYPE_FOGSEEK_ESP32_S3
static void voicewave_render_task(void *arg) {
    Application* app = (Application*)arg;  // 正确地使用传递进来的参数
    ESP_LOGI("VoicewaveRender", "🌊 波浪线渲染任务已启动 - 准备显示随机美学波浪线!");
    static uint64_t frame_count = 0;
    while (1) {
        if (app && app->GetVoicewaveDisplay()) {
            if (esp_log_level_get(TAG) == ESP_LOG_VERBOSE) {
                // Verbose logging of memory
            }
            // 根据设备状态选择渲染方式 - 音频驱动的显示逻辑
            if (app->GetDeviceState() == kDeviceStateSpeaking || app->GetDeviceState() == kDeviceStateListening) {
                // 有音频活动时，使用频谱数据
                std::vector<float> spectrum_float(g_spectrum_data.begin(), g_spectrum_data.end());
                app->GetVoicewaveDisplay()->render_spectrum_visualization(spectrum_float);
            } else {
                // 待机时显示小波浪动画
                app->GetVoicewaveDisplay()->render_idle_animation();
            }
            frame_count++;
            if (frame_count % 1000 == 0) {
                ESP_LOGI(TAG, "🎨 波浪线正在运行 - 帧数: %llu, 频谱数据: %u 字节", frame_count, g_spectrum_data.size() * sizeof(uint8_t));
            }
        }
        vTaskDelay(pdMS_TO_TICKS(16)); // ~60 FPS - 现代化刷新率
    }
}
#endif


static const char* const STATE_STRINGS[] = {
    "unknown",
    "starting",
    "configuring",
    "idle",
    "connecting",
    "listening",
    "speaking",
    "upgrading",
    "activating",
    "fatal_error",
    "invalid_state"
};

Application::Application() {
    event_group_ = xEventGroupCreate();
    background_task_ = new BackgroundTask(4096 * 8);
    // voicewave_display_ 延迟到板子初始化后创建

    esp_timer_create_args_t clock_timer_args = {
        .callback = [](void* arg) {
            Application* app = (Application*)arg;
            app->OnClockTimer();
        },
        .arg = this,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "clock_timer",
        .skip_unhandled_events = true
    };
    esp_timer_create(&clock_timer_args, &clock_timer_handle_);

    // 初始化FFT
    esp_err_t ret = dsps_fft2r_init_fc32(NULL, CONFIG_DSP_MAX_FFT_SIZE);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Not possible to initialize FFT2R");
    }
}

Application::~Application() {
    if (clock_timer_handle_ != nullptr) {
        esp_timer_stop(clock_timer_handle_);
        esp_timer_delete(clock_timer_handle_);
    }
    if (background_task_ != nullptr) {
        delete background_task_;
    }
    vEventGroupDelete(event_group_);
}

void Application::CheckNewVersion() {
    // 禁用OTA检查，直接设置设备状态为idle并返回
    ESP_LOGI(TAG, "OTA check disabled, proceeding to WebSocket connection");
    // auto& board = Board::GetInstance(); // 移除未使用的变量
    // auto display = board.GetDisplay(); // 注释旧调用
    
    // 标记当前版本为有效
    ota_.MarkCurrentVersionValid();
    
    // 显示当前版本信息
    std::string message = std::string(Lang::Strings::VERSION) + esp_app_get_description()->version;
    // display->ShowNotification(message.c_str()); // 注释旧调用
    
    // 直接设置设备状态为idle
    SetDeviceState(kDeviceStateIdle);
    // display->SetChatMessage("system", ""); // 注释旧调用
    PlaySound(Lang::Sounds::P3_SUCCESS);
    
    return;
    
    // 以下是原始OTA检查代码，已被禁用
    // auto& board = Board::GetInstance();
    // auto display = board.GetDisplay();
    // // Check if there is a new firmware version available
    // ota_.SetPostData(board.GetJson());

    // const int MAX_RETRY = 10;
    // int retry_count = 0;

    // while (true) {
    //     if (!ota_.CheckVersion()) {
    //         retry_count++;
    //         if (retry_count >= MAX_RETRY) {
    //             ESP_LOGE(TAG, "Too many retries, exit version check");
    //             return;
    //         }
    //         ESP_LOGW(TAG, "Check new version failed, retry in %d seconds (%d/%d)", 60, retry_count, MAX_RETRY);
    //         vTaskDelay(pdMS_TO_TICKS(60000));
    //         continue;
    //     }
    //     retry_count = 0;

    //     if (ota_.HasNewVersion()) {
    //         Alert(Lang::Strings::OTA_UPGRADE, Lang::Strings::UPGRADING, "happy", Lang::Sounds::P3_UPGRADE);
    //         // Wait for the chat state to be idle
    //         do {
    //             vTaskDelay(pdMS_TO_TICKS(3000));
    //         } while (GetDeviceState() != kDeviceStateIdle);

    //         // Use main task to do the upgrade, not cancelable
    //         Schedule([this, display]() {
    //             SetDeviceState(kDeviceStateUpgrading);
                
    //             display->SetIcon(FONT_AWESOME_DOWNLOAD);
    //             std::string message = std::string(Lang::Strings::NEW_VERSION) + ota_.GetFirmwareVersion();
    //             display->SetChatMessage("system", message.c_str());

    //             auto& board = Board::GetInstance();
    //             board.SetPowerSaveMode(false);
    // #if CONFIG_USE_WAKE_WORD_DETECT
    //             wake_word_detect_.StopDetection();
    // #endif
    //             // 预先关闭音频输出，避免升级过程有音频操作
    //             auto codec = board.GetAudioCodec();
    //             codec->EnableInput(false);
    //             codec->EnableOutput(false);
    //             {
    //                 std::lock_guard<std::mutex> lock(mutex_);
    //                 audio_decode_queue_.clear();
    //             }
    //             background_task_->WaitForCompletion();
    //             delete background_task_;
    //             background_task_ = nullptr;
    //             vTaskDelay(pdMS_TO_TICKS(1000));

    //             ota_.StartUpgrade([display](int progress, size_t speed) {
    //                 char buffer[64];
    //                 snprintf(buffer, sizeof(buffer), "%d%% %zuKB/s", progress, speed / 1024);
    //                 display->SetChatMessage("system", buffer);
    //             });

    //             // If upgrade success, the device will reboot and never reach here
    //             display->SetStatus(Lang::Strings::UPGRADE_FAILED);
    //             ESP_LOGI(TAG, "Firmware upgrade failed...");
    //             vTaskDelay(pdMS_TO_TICKS(3000));
    //             Reboot();
    //         });

    //         return;
    //     }

    //     // No new version, mark the current version as valid
    //     ota_.MarkCurrentVersionValid();
    //     std::string message = std::string(Lang::Strings::VERSION) + ota_.GetCurrentVersion();
    //     display->ShowNotification(message.c_str());
    
    //     if (ota_.HasActivationCode()) {
    //         // Activation code is valid
    //         SetDeviceState(kDeviceStateActivating);
    //         ShowActivationCode();

    //         // Check again in 60 seconds or until the device is idle
    //         for (int i = 0; i < 60; ++i) {
    //             if (device_state_ == kDeviceStateIdle) {
    //                 break;
    //             }
    //             vTaskDelay(pdMS_TO_TICKS(1000));
    //         }
    //         continue;
    //     }

    //     SetDeviceState(kDeviceStateIdle);
    //     display->SetChatMessage("system", "");
    //     PlaySound(Lang::Sounds::P3_SUCCESS);
    //     // Exit the loop if upgrade or idle
    //     break;
    // }
}

void Application::ShowActivationCode() {
    auto& message = ota_.GetActivationMessage();
    auto& code = ota_.GetActivationCode();

    struct digit_sound {
        char digit;
        const std::string_view& sound;
    };
    static const std::array<digit_sound, 10> digit_sounds{{
        digit_sound{'0', Lang::Sounds::P3_0},
        digit_sound{'1', Lang::Sounds::P3_1}, 
        digit_sound{'2', Lang::Sounds::P3_2},
        digit_sound{'3', Lang::Sounds::P3_3},
        digit_sound{'4', Lang::Sounds::P3_4},
        digit_sound{'5', Lang::Sounds::P3_5},
        digit_sound{'6', Lang::Sounds::P3_6},
        digit_sound{'7', Lang::Sounds::P3_7},
        digit_sound{'8', Lang::Sounds::P3_8},
        digit_sound{'9', Lang::Sounds::P3_9}
    }};

    // This sentence uses 9KB of SRAM, so we need to wait for it to finish
    Alert(Lang::Strings::ACTIVATION, message.c_str(), "happy", Lang::Sounds::P3_ACTIVATION);
    vTaskDelay(pdMS_TO_TICKS(1000));
    background_task_->WaitForCompletion();

    for (const auto& digit : code) {
        auto it = std::find_if(digit_sounds.begin(), digit_sounds.end(),
            [digit](const digit_sound& ds) { return ds.digit == digit; });
        if (it != digit_sounds.end()) {
            PlaySound(it->sound);
        }
    }
}

void Application::Alert(const char* status, const char* message, const char* emotion, const std::string_view& sound) {
    ESP_LOGW(TAG, "Alert %s: %s [%s]", status, message, emotion);
    // auto display = Board::GetInstance().GetDisplay();
    // display->SetStatus(status);
    // display->SetEmotion(emotion);
    // display->SetChatMessage("system", message);
    if (!sound.empty()) {
        PlaySound(sound);
    }
}

void Application::DismissAlert() {
    if (device_state_ == kDeviceStateIdle) {
        // auto display = Board::GetInstance().GetDisplay();
        // display->SetStatus(Lang::Strings::STANDBY);
        // display->SetEmotion("neutral");
        // display->SetChatMessage("system", "");
    }
}

void Application::PlaySound(const std::string_view& sound) {
    auto codec = Board::GetInstance().GetAudioCodec();
    codec->EnableOutput(true);
    SetDecodeSampleRate(16000);
    const char* data = sound.data();
    size_t size = sound.size();
    for (const char* p = data; p < data + size; ) {
        auto p3 = (BinaryProtocol3*)p;
        p += sizeof(BinaryProtocol3);

        auto payload_size = ntohs(p3->payload_size);
        std::vector<uint8_t> opus;
        opus.resize(payload_size);
        memcpy(opus.data(), p3->payload, payload_size);
        p += payload_size;

        std::lock_guard<std::mutex> lock(mutex_);
        audio_decode_queue_.emplace_back(std::move(opus));
    }

    // Ensure prompt sounds are drained even when device stays in idle state.
    xEventGroupSetBits(event_group_, AUDIO_OUTPUT_READY_EVENT);
}

void Application::ToggleChatState() {
    if (device_state_ == kDeviceStateActivating) {
        SetDeviceState(kDeviceStateIdle);
        return;
    }

    if (!protocol_) {
        ESP_LOGE(TAG, "Protocol not initialized");
        return;
    }

    // 添加详细日志以便于调试
    ESP_LOGI(TAG, "ToggleChatState called, current state: %d", device_state_);
    
    if (device_state_ == kDeviceStateIdle) {
        // 立即设置状态，确保用户界面更新
        SetDeviceState(kDeviceStateConnecting);
        
        // 高优先级Schedule任务
        Schedule([this]() {
            ESP_LOGI(TAG, "Opening audio channel...");
            if (!protocol_->OpenAudioChannel()) {
                ESP_LOGE(TAG, "Failed to open audio channel");
                SetDeviceState(kDeviceStateIdle);
                return;
            }
            
            ESP_LOGI(TAG, "Audio channel opened, starting listening");
            keep_listening_ = true;
            protocol_->SendStartListening(kListeningModeAutoStop);
            SetDeviceState(kDeviceStateListening);
        });
    } else if (device_state_ == kDeviceStateSpeaking) {
        ESP_LOGI(TAG, "Aborting speaking");
        Schedule([this]() {
            AbortSpeaking(kAbortReasonNone);
        });
    } else if (device_state_ == kDeviceStateListening) {
        ESP_LOGI(TAG, "Closing audio channel");
        Schedule([this]() {
            protocol_->CloseAudioChannel();
        });
    }
}

void Application::StartListening() {
    if (device_state_ == kDeviceStateActivating) {
        SetDeviceState(kDeviceStateIdle);
        return;
    }

    if (!protocol_) {
        ESP_LOGE(TAG, "Protocol not initialized");
        return;
    }
    
    keep_listening_ = false;
    if (device_state_ == kDeviceStateIdle) {
        Schedule([this]() {
            if (!protocol_->IsAudioChannelOpened()) {
                SetDeviceState(kDeviceStateConnecting);
                if (!protocol_->OpenAudioChannel()) {
                    return;
                }
            }
            protocol_->SendStartListening(kListeningModeManualStop);
            SetDeviceState(kDeviceStateListening);
        });
    } else if (device_state_ == kDeviceStateSpeaking) {
        Schedule([this]() {
            AbortSpeaking(kAbortReasonNone);
            protocol_->SendStartListening(kListeningModeManualStop);
            SetDeviceState(kDeviceStateListening);
        });
    }
}

void Application::StopListening() {
    Schedule([this]() {
        if (device_state_ == kDeviceStateListening) {
            protocol_->SendStopListening();
            SetDeviceState(kDeviceStateIdle);
        }
    });
}

void Application::Start() {
    auto& board = Board::GetInstance();
    SetDeviceState(kDeviceStateStarting);

#ifndef CONFIG_BOARD_TYPE_FOGSEEK_ESP32_S3
    /* 现在正确初始化波形显示 */
    ESP_LOGI(TAG, "Creating voicewave display after board initialization...");
    voicewave_display_ = std::make_unique<SisiVoicewaveDisplay>();
    
    // ✅ SisiVoicewaveDisplay会自动使用全局I2C总线 g_display_i2c_bus
    // 不需要通过dynamic_cast访问板级特定功能
    
    // 现在SisiVoicewaveDisplay是唯一的显示控制器
    // 它将负责你要的所有功能：WiFi状态线条 + 待机波浪线
    ESP_LOGI(TAG, "🚀 正在初始化你的0.43寸OLED显示屏...");
    bool init_success = voicewave_display_->init();
    if (init_success) {
        ESP_LOGI(TAG, "✅ Sisi Voicewave Display Initialized! (你的0.43寸OLED已就绪)");
    } else {
        ESP_LOGE(TAG, "❌ Failed to initialize Sisi Voicewave Display!");
        ESP_LOGI(TAG, "🔧 但仍然启动波浪线任务以尝试恢复...");
    }
    
    // 🔥 强制启动波浪线任务，即使初始化部分失败 - 用于调试和恢复
    ESP_LOGI(TAG, "🌊 启动随机美学波浪线渲染任务...");
    xTaskCreate(voicewave_render_task, "voicewave_render", 4096, this, 5, NULL);
#else
    ESP_LOGI(TAG, "FogSeek board: No display, skipping voicewave display initialization");
#endif

    /* 旧的显示设置被绕过 */
    // auto display = board.GetDisplay();

    /* Setup the audio codec */
    auto codec = board.GetAudioCodec();
    // 服务器发送的16000Hz OPUS数据，解码器必须使用16000Hz
    // 重采样器会处理从16000Hz到codec->output_sample_rate()(24000Hz)的转换
    opus_decode_sample_rate_ = 16000;  // Server always sends 16000Hz OPUS
    opus_decoder_ = std::make_unique<OpusDecoderWrapper>(opus_decode_sample_rate_, 1, OPUS_FRAME_DURATION_MS);
    opus_encoder_ = std::make_unique<OpusEncoderWrapper>(16000, 1, OPUS_FRAME_DURATION_MS);
    
    // For ML307 boards, we use complexity 5 to save bandwidth
    // For other boards, we use complexity 3 to save CPU
    if (board.GetBoardType() == "ml307") {
        ESP_LOGI(TAG, "ML307 board detected, setting opus encoder complexity to 5");
        opus_encoder_->SetComplexity(5);
    } else {
        ESP_LOGI(TAG, "WiFi board detected, setting opus encoder complexity to 3");
        opus_encoder_->SetComplexity(3);
    }

    if (codec->input_sample_rate() != 16000) {
        input_resampler_.Configure(codec->input_sample_rate(), 16000);
        reference_resampler_.Configure(codec->input_sample_rate(), 16000);
    }

    // 配置输出重采样器：从16000Hz OPUS解码到codec输出采样率(24000Hz)
    if (opus_decode_sample_rate_ != codec->output_sample_rate()) {
        ESP_LOGI(TAG, "Configuring output resampler: %dHz -> %dHz", opus_decode_sample_rate_, codec->output_sample_rate());
        output_resampler_.Configure(opus_decode_sample_rate_, codec->output_sample_rate());
    }
    codec->OnInputReady([this, codec]() {
        BaseType_t higher_priority_task_woken = pdFALSE;
        xEventGroupSetBitsFromISR(event_group_, AUDIO_INPUT_READY_EVENT, &higher_priority_task_woken);
        return higher_priority_task_woken == pdTRUE;
    });
    codec->OnOutputReady([this]() {
        BaseType_t higher_priority_task_woken = pdFALSE;
        xEventGroupSetBitsFromISR(event_group_, AUDIO_OUTPUT_READY_EVENT, &higher_priority_task_woken);
        return higher_priority_task_woken == pdTRUE;
    });
    codec->Start();

    /* Start the main loop */
    xTaskCreate([](void* arg) {
        Application* app = (Application*)arg;
        app->MainLoop();
        vTaskDelete(NULL);
    }, "main_loop", 4096 * 2, this, 3, nullptr);

    /* Wait for the network to be ready */
    board.StartNetwork();

    /* Setup the network protocol */
#ifdef CONFIG_CONNECTION_TYPE_WEBSOCKET
    protocol_ = std::make_unique<WebsocketProtocol>();
#else
    protocol_ = std::make_unique<MqttProtocol>();
#endif
    protocol_->OnNetworkError([this](const std::string& message) {
        SetDeviceState(kDeviceStateIdle);
        Alert(Lang::Strings::ERROR, message.c_str(), "sad", Lang::Sounds::P3_EXCLAMATION);
    });
    protocol_->OnIncomingAudio([this](std::vector<uint8_t>&& data) {
        ESP_LOGI(TAG, "Received audio data: %d bytes", data.size());

        // 🔥 如果在Listening状态收到音频数据，自动切换到Speaking状态
        if (device_state_ == kDeviceStateListening) {
            ESP_LOGI(TAG, "Auto-switching to Speaking state on first audio data");
            Schedule([this]() {
                SetDeviceState(kDeviceStateSpeaking);
            });
        }

        // 🔥 关键修复：无论什么状态都先缓存音频数据
        std::lock_guard<std::mutex> lock(mutex_);
        audio_decode_queue_.emplace_back(std::move(data));

        // 🔥 只在speaking状态触发处理，但不丢弃数据
        if (device_state_ == kDeviceStateSpeaking) {
            // 触发音频输出处理
            xEventGroupSetBits(event_group_, AUDIO_OUTPUT_READY_EVENT);
        } else {
            ESP_LOGD(TAG, "Buffering audio data in state: %s", STATE_STRINGS[device_state_]);
        }
    });
    protocol_->OnAudioChannelOpened([this, codec, &board]() {
        board.SetPowerSaveMode(false);
        if (protocol_->server_sample_rate() != codec->output_sample_rate()) {
            ESP_LOGW(TAG, "Server sample rate %d does not match device output sample rate %d, resampling may cause distortion",
                protocol_->server_sample_rate(), codec->output_sample_rate());
        }
        SetDecodeSampleRate(protocol_->server_sample_rate());
        auto& thing_manager = iot::ThingManager::GetInstance();
        protocol_->SendIotDescriptors(thing_manager.GetDescriptorsJson());
        std::string states;
        if (thing_manager.GetStatesJson(states, false)) {
            protocol_->SendIotStates(states);
        }
    });
    protocol_->OnAudioChannelClosed([this, &board]() {
        board.SetPowerSaveMode(true);
        Schedule([this]() {
            SetDeviceState(kDeviceStateIdle);
        });
    });
    protocol_->OnIncomingJson([this](const cJSON* root) {
        // Parse JSON data
        auto type = cJSON_GetObjectItem(root, "type");
        ESP_LOGI(TAG, "Received JSON message, type: %s", type ? type->valuestring : "NULL");
        if (strcmp(type->valuestring, "tts") == 0) {
            auto state = cJSON_GetObjectItem(root, "state");
            ESP_LOGI(TAG, "TTS message, state: %s", state ? state->valuestring : "NULL");
            if (strcmp(state->valuestring, "start") == 0) {
                Schedule([this]() {
                    ESP_LOGI(TAG, "TTS start - switching to Speaking state");
                    aborted_ = false;
                    // 🔥 参考xiaozhi：不清空队列，让音频自然播放完
                    // 只在状态切换时让解码器重置
                    if (device_state_ == kDeviceStateIdle || device_state_ == kDeviceStateListening) {
                        SetDeviceState(kDeviceStateSpeaking);
                    }
                });
            } else if (strcmp(state->valuestring, "stop") == 0) {
                Schedule([this]() {
                    if (device_state_ == kDeviceStateSpeaking) {
                        ESP_LOGI(TAG, "TTS stop received, waiting for audio to finish");
                        // 🔥 等待后台任务完成，但不要清空队列
                        background_task_->WaitForCompletion();

                        // 🔥 等待音频队列播放完成，最多等待5秒
                        int wait_count = 0;
                        while (wait_count < 100) { // 100 * 50ms = 5秒
                            {
                                std::lock_guard<std::mutex> lock(mutex_);
                                if (audio_decode_queue_.empty()) {
                                    ESP_LOGI(TAG, "Audio queue empty, safe to switch state");
                                    break;
                                }
                                if (wait_count % 20 == 0) { // 每秒记录一次
                                    ESP_LOGI(TAG, "Waiting for audio to finish: %d packets remaining",
                                             audio_decode_queue_.size());
                                }
                            }
                            vTaskDelay(pdMS_TO_TICKS(50));
                            wait_count++;
                            // 继续触发音频输出处理
                            xEventGroupSetBits(event_group_, AUDIO_OUTPUT_READY_EVENT);
                        }

                        if (keep_listening_) {
                            protocol_->SendStartListening(kListeningModeAutoStop);
                            SetDeviceState(kDeviceStateListening);
                        } else {
                            SetDeviceState(kDeviceStateIdle);
                        }
                    }
                });
            }
        } else if (strcmp(type->valuestring, "iot") == 0) {
            auto commands = cJSON_GetObjectItem(root, "commands");
            if (commands != NULL) {
                auto& thing_manager = iot::ThingManager::GetInstance();
                for (int i = 0; i < cJSON_GetArraySize(commands); ++i) {
                    auto command = cJSON_GetArrayItem(commands, i);
                    thing_manager.Invoke(command);
                }
            }
        }
    });

    protocol_->Start();

    // Check for new firmware version
    ota_.SetCheckVersionUrl(CONFIG_OTA_VERSION_URL);
    ota_.SetHeader("Device-Id", SystemInfo::GetMacAddress().c_str());
    ota_.SetHeader("Client-Id", board.GetUuid());
    ota_.SetHeader("Accept-Language", Lang::CODE);
    auto app_desc = esp_app_get_description();
    ota_.SetHeader("User-Agent", std::string(BOARD_NAME "/") + app_desc->version);

    xTaskCreate([](void* arg) {
        Application* app = (Application*)arg;
        app->CheckNewVersion();
        vTaskDelete(NULL);
    }, "check_new_version", 4096 * 2, this, 2, nullptr);

#if CONFIG_USE_AUDIO_PROCESSOR
    audio_processor_.Initialize(codec->input_channels(), codec->input_reference());
    audio_processor_.OnOutput([this](std::vector<int16_t>&& data) {
        background_task_->Schedule([this, data = std::move(data)]() mutable {
            opus_encoder_->Encode(std::move(data), [this](std::vector<uint8_t>&& opus) {
                Schedule([this, opus = std::move(opus)]() {
                    protocol_->SendAudio(opus);
                });
            });
        });
    });
#endif

#if CONFIG_USE_WAKE_WORD_DETECT
    const bool has_reference_channel = codec->input_reference();
    const int64_t barge_in_hold_ms = has_reference_channel ? kBargeInHoldMs : 1200;
    const int64_t barge_in_cooldown_ms = has_reference_channel ? kBargeInCooldownMs : 1600;
    ESP_LOGI(TAG, "Barge-in profile: reference=%s, hold=%lldms, cooldown=%lldms",
             has_reference_channel ? "true" : "false",
             (long long)barge_in_hold_ms, (long long)barge_in_cooldown_ms);
    wake_word_detect_.Initialize(codec->input_channels(), codec->input_reference());
    wake_word_detect_.OnVadStateChange([this, barge_in_hold_ms, barge_in_cooldown_ms](bool speaking) {
        Schedule([this, speaking, barge_in_hold_ms, barge_in_cooldown_ms]() {
            if (device_state_ == kDeviceStateListening) {
                voice_detected_ = speaking;
                return;
            }
            if (device_state_ == kDeviceStateSpeaking && speaking) {
                int64_t now_us = esp_timer_get_time();
                if (speaking_start_us_ > 0 &&
                    (now_us - speaking_start_us_) < barge_in_hold_ms * 1000) {
                    return;
                }
                if (last_barge_in_us_ > 0 &&
                    (now_us - last_barge_in_us_) < barge_in_cooldown_ms * 1000) {
                    return;
                }
                last_barge_in_us_ = now_us;
                ESP_LOGI(TAG, "VAD barge-in detected, aborting speaking");
                AbortSpeaking(kAbortReasonNone);
            }
        });
    });

    wake_word_detect_.OnWakeWordDetected([this](const std::string& wake_word) {
        Schedule([this, &wake_word]() {
            if (device_state_ == kDeviceStateIdle) {
                SetDeviceState(kDeviceStateConnecting);
                wake_word_detect_.EncodeWakeWordData();

                if (!protocol_->OpenAudioChannel()) {
                    wake_word_detect_.StartDetection();
                    return;
                }
                
                std::vector<uint8_t> opus;
                // Encode and send the wake word data to the server
                while (wake_word_detect_.GetWakeWordOpus(opus)) {
                    protocol_->SendAudio(opus);
                }
                // Set the chat state to wake word detected
                protocol_->SendWakeWordDetected(wake_word);
                ESP_LOGI(TAG, "Wake word detected: %s", wake_word.c_str());
                keep_listening_ = true;
                SetDeviceState(kDeviceStateIdle);
            } else if (device_state_ == kDeviceStateSpeaking) {
                AbortSpeaking(kAbortReasonWakeWordDetected);
            } else if (device_state_ == kDeviceStateActivating) {
                SetDeviceState(kDeviceStateIdle);
            }

            // Resume detection
            wake_word_detect_.StartDetection();
        });
    });
    wake_word_detect_.StartDetection();
#endif

    SetDeviceState(kDeviceStateIdle);
    esp_timer_start_periodic(clock_timer_handle_, 1000000);
}

void Application::OnClockTimer() {
    clock_ticks_++;

    // Print the debug info every 10 seconds
    if (clock_ticks_ % 10 == 0) {
        // SystemInfo::PrintRealTimeStats(pdMS_TO_TICKS(1000));
        int free_sram = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
        int min_free_sram = heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL);
        ESP_LOGI(TAG, "Free internal: %u minimal internal: %u", free_sram, min_free_sram);

        // If we have synchronized server time, set the status to clock "HH:MM" if the device is idle
        if (ota_.HasServerTime()) {
            if (device_state_ == kDeviceStateIdle) {
                Schedule([this]() {
                    // Set status to clock "HH:MM"
                    time_t now = time(NULL);
                    char time_str[64];
                    strftime(time_str, sizeof(time_str), "%H:%M  ", localtime(&now));
                    // Board::GetInstance().GetDisplay()->SetStatus(time_str); // 注释旧调用
                });
            }
        }
    }
}

void Application::Schedule(std::function<void()> callback) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        main_tasks_.push_back(std::move(callback));
    }
    xEventGroupSetBits(event_group_, SCHEDULE_EVENT);
}

// The Main Loop controls the chat state and websocket connection
// If other tasks need to access the websocket or chat state,
// they should use Schedule to call this function
void Application::MainLoop() {
    while (true) {
        auto bits = xEventGroupWaitBits(event_group_,
            SCHEDULE_EVENT | AUDIO_INPUT_READY_EVENT | AUDIO_OUTPUT_READY_EVENT,
            pdTRUE, pdFALSE, portMAX_DELAY);

        if (bits & AUDIO_INPUT_READY_EVENT) {
            InputAudio();
        }
        if (bits & AUDIO_OUTPUT_READY_EVENT) {
            OutputAudio();
        }
        if (bits & SCHEDULE_EVENT) {
            std::unique_lock<std::mutex> lock(mutex_);
            std::list<std::function<void()>> tasks = std::move(main_tasks_);
            lock.unlock();
            for (auto& task : tasks) {
                task();
            }
        }
    }
}

void Application::ResetDecoder() {
    std::lock_guard<std::mutex> lock(mutex_);
    opus_decoder_->ResetState();
    audio_decode_queue_.clear();
    last_output_time_ = std::chrono::steady_clock::now();
}

void Application::OutputAudio() {
    auto now = std::chrono::steady_clock::now();
    auto codec = Board::GetInstance().GetAudioCodec();
    const int max_silence_seconds = 10;

    std::unique_lock<std::mutex> lock(mutex_);
    if (audio_decode_queue_.empty()) {
        // Disable the output if there is no audio data for a long time
        if (device_state_ == kDeviceStateIdle) {
            auto duration = std::chrono::duration_cast<std::chrono::seconds>(now - last_output_time_).count();
            if (duration > max_silence_seconds) {
                codec->EnableOutput(false);
            }
        }
        return;
    }

    // 🔥 关键修复：始终处理缓冲的音频，确保完整播放
    ESP_LOGV(TAG, "Processing buffered audio: %d packets in state %s",
             audio_decode_queue_.size(), STATE_STRINGS[device_state_]);

    last_output_time_ = now;
    auto opus = std::move(audio_decode_queue_.front());
    audio_decode_queue_.pop_front();
    ESP_LOGV(TAG, "Processing audio packet, remaining queue size: %d",
             audio_decode_queue_.size());
    lock.unlock();

    background_task_->Schedule([this, codec, opus = std::move(opus)]() mutable {
        // 🔥 关键修复：不检查aborted，让所有音频完整播放
        // 这确保解码器状态在整个会话期间保持连续

        std::vector<int16_t> pcm;
        if (!opus_decoder_->Decode(std::move(opus), pcm)) {
            ESP_LOGE(TAG, "Failed to decode audio data");
            return;
        }
        ESP_LOGV(TAG, "Successfully decoded audio: %d samples", pcm.size());

        // --- 心脏搭桥手术 ---
#ifndef CONFIG_BOARD_TYPE_FOGSEEK_ESP32_S3
        if (!pcm.empty()) {
            // 准备FFT输入数据 (取前 N 个点)
            float* fft_input = (float*)malloc(pcm.size() * 2 * sizeof(float));
            for (size_t i = 0; i < pcm.size(); ++i) {
                fft_input[i*2] = (float)pcm[i]; // 实部
                fft_input[i*2+1] = 0;           // 虚部
            }

            // 执行FFT
            dsps_fft2r_fc32(fft_input, pcm.size());
            dsps_bit_rev_fc32(fft_input, pcm.size());
            dsps_cplx2reC_fc32(fft_input, pcm.size());

            // 计算频谱能量并映射到我们需要的8个点
            std::vector<uint8_t> new_spectrum(SISI_SPECTRUM_POINTS, 0);
            int points_per_bin = (pcm.size() / 2) / SISI_SPECTRUM_POINTS;
            for (int i = 0; i < SISI_SPECTRUM_POINTS; ++i) {
                float avg_magnitude = 0;
                for (int j = 0; j < points_per_bin; ++j) {
                    int index = i * points_per_bin + j;
                    avg_magnitude += fft_input[index];
                }
                avg_magnitude /= points_per_bin;

                // 简单的对数映射，让视觉效果更明显
                float log_val = 10 * log10(avg_magnitude + 1);
                int scaled_val = (int)((log_val / 50.0f) * 100); // 50.0f 是一个经验调整值
                new_spectrum[i] = std::max(0, std::min(100, scaled_val));
            }
            
            free(fft_input);

            // 安全地更新全局频谱数据
            std::lock_guard<std::mutex> lock(g_spectrum_mutex);
            g_spectrum_data = new_spectrum;
        }
#endif
        // --- 手术结束 ---

        // Resample if the sample rate is different
        if (opus_decode_sample_rate_ != codec->output_sample_rate()) {
            int target_size = output_resampler_.GetOutputSamples(pcm.size());
            std::vector<int16_t> resampled(target_size);
            output_resampler_.Process(pcm.data(), pcm.size(), resampled.data());
            pcm = std::move(resampled);
        }
        
        codec->OutputData(pcm);
    });
}

void Application::InputAudio() {
    auto codec = Board::GetInstance().GetAudioCodec();
    std::vector<int16_t> data;
    if (!codec->InputData(data)) {
        return;
    }

    if (codec->input_sample_rate() != 16000) {
        if (codec->input_channels() == 2) {
            auto mic_channel = std::vector<int16_t>(data.size() / 2);
            auto reference_channel = std::vector<int16_t>(data.size() / 2);
            for (size_t i = 0, j = 0; i < mic_channel.size(); ++i, j += 2) {
                mic_channel[i] = data[j];
                reference_channel[i] = data[j + 1];
            }
            auto resampled_mic = std::vector<int16_t>(input_resampler_.GetOutputSamples(mic_channel.size()));
            auto resampled_reference = std::vector<int16_t>(reference_resampler_.GetOutputSamples(reference_channel.size()));
            input_resampler_.Process(mic_channel.data(), mic_channel.size(), resampled_mic.data());
            reference_resampler_.Process(reference_channel.data(), reference_channel.size(), resampled_reference.data());
            data.resize(resampled_mic.size() + resampled_reference.size());
            for (size_t i = 0, j = 0; i < resampled_mic.size(); ++i, j += 2) {
                data[j] = resampled_mic[i];
                data[j + 1] = resampled_reference[i];
            }
        } else {
            auto resampled = std::vector<int16_t>(input_resampler_.GetOutputSamples(data.size()));
            input_resampler_.Process(data.data(), data.size(), resampled.data());
            data = std::move(resampled);
        }
    }

#if CONFIG_USE_WAKE_WORD_DETECT
    if (wake_word_detect_.IsDetectionRunning()) {
        wake_word_detect_.Feed(data);
    }
#endif
#if CONFIG_USE_AUDIO_PROCESSOR
    if (audio_processor_.IsRunning()) {
        audio_processor_.Input(data);
    }
#else
    if (device_state_ == kDeviceStateListening) {
        background_task_->Schedule([this, data = std::move(data)]() mutable {
            opus_encoder_->Encode(std::move(data), [this](std::vector<uint8_t>&& opus) {
                Schedule([this, opus = std::move(opus)]() {
                    protocol_->SendAudio(opus);
                });
            });
        });
    }
#endif
}

void Application::AbortSpeaking(AbortReason reason) {
    ESP_LOGI(TAG, "Abort speaking");
    aborted_ = true;
    protocol_->SendAbortSpeaking(reason);
}

void Application::SetDeviceState(DeviceState state) {
    if (device_state_ == state) {
        return;
    }
    
    clock_ticks_ = 0;
    auto previous_state = device_state_;
    device_state_ = state;
    if (state == kDeviceStateSpeaking && previous_state != kDeviceStateSpeaking) {
        speaking_start_us_ = esp_timer_get_time();
    } else if (previous_state == kDeviceStateSpeaking && state != kDeviceStateSpeaking) {
        speaking_stop_us_ = esp_timer_get_time();
    }
    ESP_LOGI(TAG, "STATE: %s", STATE_STRINGS[device_state_]);
    // The state is changed, wait for all background tasks to finish
    background_task_->WaitForCompletion();

    auto& board = Board::GetInstance();
    auto codec = board.GetAudioCodec();
    // auto display = board.GetDisplay(); // 注释旧调用
    auto led = board.GetLed();
    led->OnStateChanged();
    switch (state) {
        case kDeviceStateUnknown:
        case kDeviceStateIdle:
            // display->SetStatus(Lang::Strings::STANDBY); // 注释旧调用
            // display->SetEmotion("neutral"); // 注释旧调用
#if CONFIG_USE_AUDIO_PROCESSOR
            audio_processor_.Stop();
#endif
            break;
        case kDeviceStateConnecting:
            // display->SetStatus(Lang::Strings::CONNECTING); // 注释旧调用
            // display->SetEmotion("neutral"); // 注释旧调用
            // display->SetChatMessage("system", ""); // 注释旧调用
            break;
        case kDeviceStateListening:
            // display->SetStatus(Lang::Strings::LISTENING); // 注释旧调用
            // display->SetEmotion("neutral"); // 注释旧调用
            // 只有从非speaking状态切换到listening时才重置解码器
            // 从speaking切换过来时，让音频自然播放完
            if (previous_state != kDeviceStateSpeaking) {
                ResetDecoder();
            }
            opus_encoder_->ResetState();
#if CONFIG_USE_AUDIO_PROCESSOR
            audio_processor_.Start();
#endif
            UpdateIotStates();
            if (previous_state == kDeviceStateSpeaking) {
                // FIXME: Wait for the speaker to empty the buffer
                vTaskDelay(pdMS_TO_TICKS(120));
            }
            break;
        case kDeviceStateSpeaking:
            // display->SetStatus(Lang::Strings::SPEAKING); // 注释旧调用
            // 🔥 关键修复：参考xiaozhi，在进入speaking状态时重置解码器
            // 这确保每次TTS开始都有干净的解码器状态
            ResetDecoder();
            codec->EnableOutput(true);
#if CONFIG_USE_AUDIO_PROCESSOR
            audio_processor_.Stop();
#endif
            break;
        default:
            // Do nothing
            break;
    }
}

void Application::SetDecodeSampleRate(int sample_rate) {
    if (opus_decode_sample_rate_ == sample_rate) {
        return;
    }

    opus_decode_sample_rate_ = sample_rate;
    opus_decoder_.reset();
    opus_decoder_ = std::make_unique<OpusDecoderWrapper>(opus_decode_sample_rate_, 1, OPUS_FRAME_DURATION_MS);

    auto codec = Board::GetInstance().GetAudioCodec();
    if (opus_decode_sample_rate_ != codec->output_sample_rate()) {
        ESP_LOGI(TAG, "Resampling audio from %d to %d", opus_decode_sample_rate_, codec->output_sample_rate());
        output_resampler_.Configure(opus_decode_sample_rate_, codec->output_sample_rate());
    }
}

void Application::UpdateIotStates() {
    auto& thing_manager = iot::ThingManager::GetInstance();
    std::string states;
    if (thing_manager.GetStatesJson(states, true)) {
        protocol_->SendIotStates(states);
    }
}

void Application::Reboot() {
    ESP_LOGI(TAG, "Rebooting...");
    esp_restart();
}

void Application::WakeWordInvoke(const std::string& wake_word) {
    if (device_state_ == kDeviceStateIdle) {
        ToggleChatState();
        Schedule([this, wake_word]() {
            if (protocol_) {
                protocol_->SendWakeWordDetected(wake_word); 
            }
        }); 
    } else if (device_state_ == kDeviceStateSpeaking) {
        Schedule([this]() {
            AbortSpeaking(kAbortReasonNone);
        });
    } else if (device_state_ == kDeviceStateListening) {   
        Schedule([this]() {
            if (protocol_) {
                protocol_->CloseAudioChannel();
            }
        });
    }
}

bool Application::CanEnterSleepMode() {
    if (device_state_ != kDeviceStateIdle) {
        return false;
    }

    if (protocol_ && protocol_->IsAudioChannelOpened()) {
        return false;
    }

    // Now it is safe to enter sleep mode
    return true;
}
