#include "websocket_protocol.h"
#include "board.h"
#include "system_info.h"
#include "application.h"

#include <cstring>
#include <cJSON.h>
#include <esp_log.h>
#include <arpa/inet.h>
#include "assets/lang_config.h"

#define TAG "WS"

WebsocketProtocol::WebsocketProtocol() {
    event_group_handle_ = xEventGroupCreate();
}

WebsocketProtocol::~WebsocketProtocol() {
    if (websocket_ != nullptr) {
        delete websocket_;
    }
    vEventGroupDelete(event_group_handle_);
}

void WebsocketProtocol::Start() {
}

void WebsocketProtocol::SendAudio(const std::vector<uint8_t>& data) {
    if (websocket_ == nullptr) {
        return;
    }

    websocket_->Send(data.data(), data.size(), true);
}

void WebsocketProtocol::SendText(const std::string& text) {
    if (websocket_ == nullptr) {
        return;
    }

    if (!websocket_->Send(text)) {
        ESP_LOGE(TAG, "Failed to send text: %s", text.c_str());
        SetError(Lang::Strings::SERVER_ERROR);
    }
}

bool WebsocketProtocol::IsAudioChannelOpened() const {
    return websocket_ != nullptr && websocket_->IsConnected() && !error_occurred_ && !IsTimeout();
}

void WebsocketProtocol::CloseAudioChannel() {
    if (websocket_ != nullptr) {
        delete websocket_;
        websocket_ = nullptr;
    }
}

bool WebsocketProtocol::OpenAudioChannel() {
    if (websocket_ != nullptr) {
        delete websocket_;
    }

    error_occurred_ = false;
    std::string url = CONFIG_WEBSOCKET_URL;
    std::string token = "Bearer " + std::string(CONFIG_WEBSOCKET_ACCESS_TOKEN);
    websocket_ = Board::GetInstance().CreateWebSocket();
    websocket_->SetHeader("Authorization", token.c_str());
    websocket_->SetHeader("Protocol-Version", "1");
    websocket_->SetHeader("Device-Id", SystemInfo::GetMacAddress().c_str());
    websocket_->SetHeader("Client-Id", Board::GetInstance().GetUuid().c_str());

    websocket_->OnData([this](const char* data, size_t len, bool binary) {
        if (binary) {
            ESP_LOGI(TAG, "Received binary data: %d bytes", len);
            if (on_incoming_audio_ != nullptr && len >= sizeof(BinaryProtocol3)) {
                // 解析BP3协议头部
                auto bp3 = (BinaryProtocol3*)data;
                uint16_t payload_size = ntohs(bp3->payload_size);

                // 验证数据完整性
                if (sizeof(BinaryProtocol3) + payload_size <= len) {
                    ESP_LOGI(TAG, "BP3 packet: type=%d, payload_size=%d, total=%d bytes",
                             bp3->type, payload_size, len);
                    // 只传递OPUS payload部分，不包含头部
                    on_incoming_audio_(std::vector<uint8_t>(bp3->payload, bp3->payload + payload_size));
                } else {
                    ESP_LOGE(TAG, "Invalid BP3 packet: expected %d bytes, got %d bytes",
                             (int)(sizeof(BinaryProtocol3) + payload_size), (int)len);
                    // 如果不是BP3格式，尝试直接传递（兼容旧协议）
                    ESP_LOGW(TAG, "Falling back to raw data mode");
                    on_incoming_audio_(std::vector<uint8_t>((uint8_t*)data, (uint8_t*)data + len));
                }
            } else if (on_incoming_audio_ != nullptr) {
                // 数据太小，不是BP3格式，直接传递
                ESP_LOGW(TAG, "Binary data too small for BP3: %d bytes, sending raw", len);
                on_incoming_audio_(std::vector<uint8_t>((uint8_t*)data, (uint8_t*)data + len));
            }
        } else {
            ESP_LOGI(TAG, "Received JSON data: %d bytes", len);
            // Parse JSON data
            auto root = cJSON_Parse(data);
            auto type = cJSON_GetObjectItem(root, "type");
            if (type != NULL) {
                if (strcmp(type->valuestring, "hello") == 0) {
                    ParseServerHello(root);
                } else {
                    if (on_incoming_json_ != nullptr) {
                        on_incoming_json_(root);
                    }
                }
            } else {
                ESP_LOGE(TAG, "Missing message type, data: %s", data);
            }
            cJSON_Delete(root);
        }
        last_incoming_time_ = std::chrono::steady_clock::now();
    });

    websocket_->OnDisconnected([this]() {
        ESP_LOGI(TAG, "Websocket disconnected");
        if (on_audio_channel_closed_ != nullptr) {
            on_audio_channel_closed_();
        }
    });

    // 不断尝试连接WebSocket，直到成功
    bool connected = false;
    int retry_count = 0;
    while (!connected) {
        if (websocket_->Connect(url.c_str())) {
            connected = true;
            ESP_LOGI(TAG, "WebSocket连接成功");
        } else {
            retry_count++;
            ESP_LOGE(TAG, "WebSocket连接失败，3秒后自动重试 (尝试 %d)", retry_count);
            vTaskDelay(pdMS_TO_TICKS(3000));
            // 如果重试10次仍失败，通知用户但继续尝试
            if (retry_count % 10 == 0) {
                ESP_LOGW(TAG, "SISI服务器连接失败，继续重试中... (尝试 %d)", retry_count);
            }
        }
    }

    // Send hello message to describe the client
    // keys: message type, version, audio_params (format, sample_rate, channels)
    std::string message = "{";
    message += "\"type\":\"hello\",";
    message += "\"version\": 1,";
    message += "\"transport\":\"websocket\",";
    message += "\"audio_params\":{";
    message += "\"format\":\"opus\", \"sample_rate\":16000, \"channels\":1, \"frame_duration\":" + std::to_string(OPUS_FRAME_DURATION_MS);
    message += "}}";
    websocket_->Send(message);

    // 不断等待server hello，直到成功接收
    bool received_hello = false;
    retry_count = 0;
    while (!received_hello) {
        EventBits_t bits = xEventGroupWaitBits(event_group_handle_, WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT, pdTRUE, pdFALSE, pdMS_TO_TICKS(10000));
        if (bits & WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT) {
            received_hello = true;
            ESP_LOGI(TAG, "成功接收服务器hello响应");
        } else {
            retry_count++;
            ESP_LOGE(TAG, "服务器hello响应超时，重新发送hello (尝试 %d)", retry_count);
            // 重发hello消息
            websocket_->Send(message);
            
            // 如果多次重试仍失败，通知用户但继续尝试
            if (retry_count % 5 == 0) {
                ESP_LOGW(TAG, "SISI服务器响应超时，继续重试中... (尝试 %d)", retry_count);
            }
        }
    }

    if (on_audio_channel_opened_ != nullptr) {
        on_audio_channel_opened_();
    }

    return true;
}

void WebsocketProtocol::ParseServerHello(const cJSON* root) {
    auto transport = cJSON_GetObjectItem(root, "transport");
    if (transport == nullptr || strcmp(transport->valuestring, "websocket") != 0) {
        ESP_LOGE(TAG, "Unsupported transport: %s", transport->valuestring);
        return;
    }

    auto audio_params = cJSON_GetObjectItem(root, "audio_params");
    if (audio_params != NULL) {
        auto sample_rate = cJSON_GetObjectItem(audio_params, "sample_rate");
        if (sample_rate != NULL) {
            server_sample_rate_ = sample_rate->valueint;
        }
    }

    xEventGroupSetBits(event_group_handle_, WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT);
}
