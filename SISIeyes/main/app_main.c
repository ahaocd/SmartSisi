// SISIeyes unified firmware - Master version from backup with LVGL integration
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <ctype.h>
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "esp_camera.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/i2s_std.h"

#include "esp_http_server.h"
#include "driver/spi_master.h"
// 🔧 ESP-IDF官方LCD驱动
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_pm.h"  // 🔥 电源管理
#include "esp_lcd_panel_ops.h"
// 🚀 LVGL相关头文件
#include "esp_lvgl_port.h"
#include "esp_spiffs.h"  // 🔧 SPIFFS文件系统支持
// #include "melody_visualizer.h"      // DEPRECATED: Replaced by LVGL
// #include "visualizer_integration.h" // DEPRECATED: Replaced by LVGL
// #include "lv_official_demo.h"         // DEPRECATED: Replaced by sisi_ui
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "esp_heap_caps.h"  // 🔧 用于检测PSRAM
#include "esp_system.h"     // 🔧 系统相关函数
#include "freertos/semphr.h"
#include "driver/rmt_tx.h"
#include "led_strip.h"
#include "sisi_ui.h"
#include "cJSON.h"

// 定义MIN宏
#ifndef MIN
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#endif

// 配置参数 - 便于修改
#define WIFI_SSID "iPhone15"
#define WIFI_PASSWORD "88888888"
#define HTTP_BUFFER_SIZE 8192  // 增大缓冲区支持base64图像
#define TFT_DMA_BUFFER_SIZE 2048  // TFT DMA缓冲区大小 (减小避免内存冲突)

/*
 * 🔧 ESP32-S3 CAM 硬件引脚重新分配 - 避免所有冲突
 *
 * 📷 摄像头 (OV5640): GPIO4/5/6/7/8-18/15/13 (固定，不可更改)
 * 🚗 电机 (DRV8833): GPIO1/GPIO2 (ADC引脚，安全)
 * 💡 LED (WS2812): GPIO48 (板载，固定)
 * 📺 显示屏 (ST7789): GPIO0/21/41/42/45/47 (避开PSRAM/USB/UART)
 *
 * ❌ 避开的引脚:
 * - GPIO35-39: PSRAM专用
 * - GPIO19-20: USB专用
 * - GPIO43-44: UART专用 (C口连接正在使用)
 */

// 🚗 DRV8833电机+绕组驱动引脚 (物理并联到OUT1/OUT2)
#define MOTOR_IN1 3    // GPIO3 - 控制电机+绕组 IN1
#define MOTOR_IN2 46   // GPIO46 - 控制电机+绕组 IN2

// 💡 WS2812 LED引脚配置
#define LED_PIN_1 1    // GPIO1 - 第一颗WS2812 (白闪+彩虹)
#define LED_PIN_48 48  // GPIO48 - 4颗WS2812串联 (粉红渐变30秒)
#define LED_NUM_1 1    // GPIO1控制1颗LED
#define LED_NUM_48 4   // GPIO48控制4颗LED

// ST7789 Display Pins
#define PIN_TFT_MOSI 2    // GPIO2 - MOSI (暂停电机，使用GPIO2)
#define PIN_TFT_SCLK 47   // GPIO47 - SCLK (保持不变)
#define PIN_TFT_CS   21   // GPIO21 - CS (保持不变)
#define PIN_TFT_DC   42   // GPIO42 - DC (保持不变)
#define PIN_TFT_RST  -1   // 没有连接 (您明确说了)
#define PIN_TFT_BL   41   // GPIO41 - BL (保持不变，但改用LEDC PWM控制)
#define TFT_WIDTH 172      // ST7789 1.47寸屏实际宽度
#define TFT_HEIGHT 320     // ST7789 1.47寸屏实际高度
#define TFT_BL_CHANNEL LEDC_CHANNEL_2  // Backlight PWM channel
#define TFT_BL_TIMER LEDC_TIMER_2      // Backlight PWM timer

// 音频I2S引脚
// #define I2S_BCK_PIN  26  // 暂未启用，避免与电机冲突
// #define I2S_WS_PIN   25
// #define I2S_DATA_PIN 33

// 摄像头引脚映射 - ESP32-S3 EYE 官方配置 (OV5640)
// ESP32S3_EYE official camera pin configuration
#define CAM_PIN_PWDN    -1   // 无电源控制引脚
#define CAM_PIN_RESET   -1   // 无复位引脚
#define CAM_PIN_XCLK    15   // XCLK - 外部时钟
#define CAM_PIN_SIOD    4    // SDA - I2C数据线 (您的硬件实际引脚)
#define CAM_PIN_SIOC    5    // SCL - I2C时钟线 (您的硬件实际引脚)

// Camera data pins mapping
#define CAM_PIN_D7      16   // CAM_Y9 → GPIO16 → D7 (MSB)
#define CAM_PIN_D6      17   // CAM_Y8 → GPIO17 → D6
#define CAM_PIN_D5      18   // CAM_Y7 → GPIO18 → D5
#define CAM_PIN_D4      12   // CAM_Y6 → GPIO12 → D4
#define CAM_PIN_D3      10   // CAM_Y5 → GPIO10 → D3
#define CAM_PIN_D2      8    // CAM_Y4 → GPIO8  → D2
#define CAM_PIN_D1      9    // CAM_Y3 → GPIO9  → D1
#define CAM_PIN_D0      11   // CAM_Y2 → GPIO11 → D0 (LSB)

#define CAM_PIN_VSYNC   6    // 垂直同步
#define CAM_PIN_HREF    7    // 水平参考
#define CAM_PIN_PCLK    13   // 像素时钟

// 引脚配置验证 - 摄像头和TFT引脚已确认无冲突
// XCLK(15) 是摄像头外部时钟，SCLK(40) 是TFT时钟，功能不同无冲突

// 🔧 ESP-IDF官方LCD驱动句柄
static esp_lcd_panel_io_handle_t io_handle = NULL;
esp_lcd_panel_handle_t panel_handle = NULL;  // 全局LCD panel句柄
esp_lcd_panel_handle_t g_lcd_panel = NULL;   // 全局导出句柄

static const char *TAG = "app_main";

// 🔧 线程安全消息队列
typedef struct {
    char type[16];      // "text", "mode"
    char data[512];     // 消息数据
} display_message_t;

static QueueHandle_t display_queue = NULL;

// 全局变量 - 添加互斥保护
static QueueHandle_t audio_queue;
static volatile bool audio_playing = false;
static volatile bool camera_enabled = false;
static SemaphoreHandle_t camera_mutex = NULL;
static SemaphoreHandle_t audio_mutex = NULL;
static TaskHandle_t audio_task_handle = NULL;

// 🎯 新增：拍照特效控制变量
static volatile bool photo_effect_running = false;
static TaskHandle_t photo_effect_task_handle = NULL;
static SemaphoreHandle_t effect_mutex = NULL;

// WiFi相关 - 保持事件组持续存在
static EventGroupHandle_t wifi_event_group = NULL;
#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT      BIT1
#define WIFI_MAX_RETRY     20
static int s_retry_num = 0;
static bool wifi_initialized = false;

// 🧹 清理：删除视频服务器URL变量

// 函数声明 - 使用官方LCD API
static void backlight_set_brightness(uint8_t brightness);  // 🔧 新增：背光控制函数
static esp_err_t init_spiffs(void);  // 🔧 SPIFFS文件系统初始化
static void audio_init(void);
static void audio_play_tone(float freq, int duration_ms);
static void audio_task(void *pvParameters);
// 暂时未使用的任务声明
// static void command_task(void *pvParameters);    // 🚀 核心0：命令处理任务
// static void display_task(void *pvParameters);    // 🚀 核心1：显示屏任务
static bool wifi_init(void);
static void io_init(void);
static bool cam_init(void);
static esp_err_t camera_capture_and_display(void);  // 🎬 拍照并显示函数

// static bool cam_diagnose_and_recover(void);  // 🔧 未使用，注释避免警告
static void http_start(void);
static void tft_init_full(void);
static void wifi_event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data);

// 🎵 旋律动画可视化函数声明
static esp_err_t init_visualizer_integration(httpd_handle_t server);
// 🗑️ 已删除 set_audio_data 函数声明
// 注释未使用的函数声明，避免编译警告
// static void set_text_display(const char* text);
// static void set_standby_mode(void);
static bool is_valid_hex_color(const char* hex);
// 🎯 两个WS2812 LED句柄
static led_strip_handle_t led_strip_1 = NULL;   // GPIO1 - 白闪+彩虹
static led_strip_handle_t led_strip_48 = NULL;  // GPIO48 - 粉红渐变

static bool ensure_camera_is_ready(void) {
    if (!camera_enabled) {
        ESP_LOGI(TAG, "📷 按需初始化摄像头...");

        // 🛑 先停止视频播放，释放资源
        // 🔧 简单策略：停视频，直接初始化摄像头
        sisi_ui_stop_idle_video();

        if (cam_init()) {
            camera_enabled = true;
            ESP_LOGI(TAG, "✅ 摄像头初始化成功");
        } else {
            ESP_LOGE(TAG, "❌ 摄像头初始化失败");
            return false;
        }
    }
    return true;
}

/* ---------------- Wi-Fi STA ---------------- */
static bool wifi_init(void){
    if (wifi_initialized) {
        ESP_LOGI(TAG, "WiFi already initialized");
        return true;
    }

    // 不在这里初始化NVS，由app_main统一处理
    esp_netif_init();
    esp_event_loop_create_default();
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg=WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);

    // 创建持久的事件组，不要删除
    if (wifi_event_group == NULL) {
        wifi_event_group = xEventGroupCreate();
    }

    // 注册事件处理器，保持持久连接
    esp_event_handler_instance_t instance_any, instance_got_ip;
    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, &instance_any);
    esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, &instance_got_ip);

    wifi_config_t sta={0};
    strcpy((char*)sta.sta.ssid, WIFI_SSID);
    strcpy((char*)sta.sta.password, WIFI_PASSWORD);

    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_ps(WIFI_PS_NONE);
    esp_wifi_set_max_tx_power(78);
    esp_wifi_set_config(WIFI_IF_STA, &sta);

    // ESP-IDF 5.x 已移除 esp_wifi_set_auto_connect()
    // 这里使用自定义事件回调重连逻辑（见 wifi_event_handler），
    // 最大重试次数由 WIFI_MAX_RETRY(20) 控制，无需再调用旧 API

    // 启用自动重连
    esp_wifi_start();

    // 等待初始连接
    EventBits_t bits = xEventGroupWaitBits(wifi_event_group, WIFI_CONNECTED_BIT|WIFI_FAIL_BIT, pdFALSE, pdFALSE, 30000 / portTICK_PERIOD_MS);
    bool ok = (bits & WIFI_CONNECTED_BIT);

    if (ok) {
        wifi_initialized = true;
        ESP_LOGI(TAG, "WiFi connected successfully");
    } else {
        ESP_LOGW(TAG, "WiFi initial connection failed, but will keep retrying");
        // 不返回失败，让系统继续运行，WiFi会在后台重连
        wifi_initialized = true;
    }

    // 不要注销事件处理器和删除事件组！保持持久重连能力
    return true;  // 总是返回成功，让系统继续运行
}

// 🔧 按照ESP-BSP官方标准初始化SPIFFS文件系统
static esp_err_t init_spiffs(void) {
    ESP_LOGI(TAG, "🔧 初始化SPIFFS文件系统...");

    esp_vfs_spiffs_conf_t conf = {
        .base_path = "/spiffs",
        .partition_label = "storage",  // 对应partitions.csv中的storage分区
        .max_files = 5,
        .format_if_mount_failed = true
    };

    esp_err_t ret = esp_vfs_spiffs_register(&conf);
    if (ret != ESP_OK) {
        if (ret == ESP_FAIL) {
            ESP_LOGE(TAG, "❌ SPIFFS挂载失败");
        } else if (ret == ESP_ERR_NOT_FOUND) {
            ESP_LOGE(TAG, "❌ 未找到SPIFFS分区");
        } else {
            ESP_LOGE(TAG, "❌ SPIFFS初始化失败: %s", esp_err_to_name(ret));
        }
        return ret;
    }

    // 检查SPIFFS信息
    size_t total = 0, used = 0;
    ret = esp_spiffs_info("storage", &total, &used);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "❌ 获取SPIFFS信息失败: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "✅ SPIFFS挂载成功");
    ESP_LOGI(TAG, "   📊 分区大小: %d KB", total / 1024);
    ESP_LOGI(TAG, "   📊 已使用: %d KB (%.1f%%)", used / 1024, (float)used * 100 / total);
    ESP_LOGI(TAG, "   📁 挂载点: /spiffs");
    ESP_LOGI(TAG, "   🎬 GIF路径: /spiffs/background.gif");

    return ESP_OK;
}

/* ---------------- Audio I2S (Simplified) ---------------- */
typedef struct {
    float frequency;
    int duration_ms;
} audio_tone_t;

static void audio_init(void){
    // 创建音频互斥锁
    audio_mutex = xSemaphoreCreateMutex();
    if (audio_mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create audio mutex");
        return;
    }

    // 创建音频队列
    audio_queue = xQueueCreate(10, sizeof(audio_tone_t));
    if (audio_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create audio queue");
        return;
    }

    // 创建音频任务
    xTaskCreate(audio_task, "audio_task", 4096, NULL, 5, &audio_task_handle);
    ESP_LOGI(TAG, "Audio system initialized with non-blocking playback");
}

// 音频任务 - 非阻塞播放，空闲时自动停止
static void audio_task(void *pvParameters) {
    audio_tone_t tone;
    int idle_count = 0;
    const int max_idle_cycles = 30; // 30秒无音频后停止任务

    while (1) {
        // 🔧 使用超时接收，避免永久阻塞
        if (xQueueReceive(audio_queue, &tone, 1000 / portTICK_PERIOD_MS)) {
            idle_count = 0; // 重置空闲计数
            if (xSemaphoreTake(audio_mutex, portMAX_DELAY)) {
                audio_playing = true;
                ESP_LOGI(TAG, "Playing tone: %.1f Hz for %lu ms", tone.frequency, (unsigned long)tone.duration_ms);

                // 这里可以添加实际的音频播放代码
                // 目前用延时模拟
                vTaskDelay(tone.duration_ms / portTICK_PERIOD_MS);

                audio_playing = false;
                xSemaphoreGive(audio_mutex);
            }
        } else {
            // 🔧 空闲超时，检查是否需要停止任务
            idle_count++;
            if (idle_count >= max_idle_cycles) {
                ESP_LOGI(TAG, "Audio task stopping due to inactivity");
                audio_task_handle = NULL; // 清除句柄
                vTaskDelete(NULL); // 删除自己
            }
        }
    }
}



// 非阻塞音调播放 - 异步按需初始化
static void audio_play_tone(float freq, int duration_ms){
    // 🔧 异步初始化音频，第一次使用时才启动
    if (audio_queue == NULL) {
        ESP_LOGI(TAG, "🔊 Async audio initialization...");
        audio_init();
        if (audio_queue == NULL) {
            ESP_LOGE(TAG, "Audio initialization failed");
            return;
        }
    }

    audio_tone_t tone = {
        .frequency = freq,
        .duration_ms = duration_ms
    };

    if (xQueueSend(audio_queue, &tone, 100 / portTICK_PERIOD_MS) != pdTRUE) {
        ESP_LOGW(TAG, "Audio queue full, tone dropped");
    }
}

/* ---------------- Camera ---------------- */
static bool cam_init(void){
    // 打开摄像头驱动详细日志，便于定位崩溃点
    esp_log_level_set("camera", ESP_LOG_DEBUG);

    ESP_LOGI(TAG, "camera init start");

    if (camera_mutex == NULL) {
        camera_mutex = xSemaphoreCreateMutex();
        if (camera_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create camera mutex");
            return false;
        }
    }

    if (xSemaphoreTake(camera_mutex, 5000 / portTICK_PERIOD_MS) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take camera mutex");
        return false;
    }

    // 如果已经初始化，直接返回
    if (camera_enabled) {
        xSemaphoreGive(camera_mutex);
        return true;
    }

    // 🔧 完全按照官方ESP32S3_EYE示例的逻辑
    camera_config_t config = {
        .pin_pwdn = CAM_PIN_PWDN,
        .pin_reset = CAM_PIN_RESET,
        .pin_xclk = CAM_PIN_XCLK,
        .pin_sscb_sda = CAM_PIN_SIOD,   // 🔧 官方正确字段名 sscb_sda
        .pin_sscb_scl = CAM_PIN_SIOC,   // 🔧 官方正确字段名 sscb_scl
        .pin_d7 = CAM_PIN_D7,
        .pin_d6 = CAM_PIN_D6,
        .pin_d5 = CAM_PIN_D5,
        .pin_d4 = CAM_PIN_D4,
        .pin_d3 = CAM_PIN_D3,
        .pin_d2 = CAM_PIN_D2,
        .pin_d1 = CAM_PIN_D1,
        .pin_d0 = CAM_PIN_D0,
        .pin_vsync = CAM_PIN_VSYNC,
        .pin_href = CAM_PIN_HREF,
        .pin_pclk = CAM_PIN_PCLK,

        // 🔧 官方推荐配置，确保摄像头正常工作
        .xclk_freq_hz = 20000000,      // 🔧 官方推荐20MHz
        .ledc_timer = LEDC_TIMER_1,    // 🔧 使用TIMER_1避免与其他功能冲突
        .ledc_channel = LEDC_CHANNEL_1, // 🔧 使用CHANNEL_1避免与背光冲突
        .pixel_format = PIXFORMAT_JPEG,    // 🔧 JPEG：网络传输 + 电脑保存
        .frame_size = FRAMESIZE_HD,      // 1280x720 - 真正的高分辨率！
        .jpeg_quality = 10,            // 🔧 官方推荐质量
        .fb_count = 2,                 // 🔧 官方推荐双缓冲
        .fb_location = CAMERA_FB_IN_PSRAM,
        .grab_mode = CAMERA_GRAB_LATEST      // 🔧 官方推荐LATEST模式
    };

    // 🔧 基于官方测试的PSRAM优化配置
    if (heap_caps_get_free_size(MALLOC_CAP_SPIRAM) > 0) {
        ESP_LOGI(TAG, "PSRAM found, using optimized settings");
        config.jpeg_quality = 12;     // 🔧 官方测试推荐值
        config.fb_count = 2;          // 🔧 官方测试用双缓冲，解决NO-SOI
        config.grab_mode = CAMERA_GRAB_WHEN_EMPTY; // 🔧 官方推荐模式
    } else {
        ESP_LOGW(TAG, "No PSRAM, using conservative settings");
        config.frame_size = FRAMESIZE_SVGA;  // 官方示例值
        config.fb_location = CAMERA_FB_IN_DRAM; // 官方示例值
    }

    // 🔧 修复：不要设置无效的GPIO引脚（-1）
    // ESP32S3_EYE没有PWDN和RESET引脚，跳过GPIO设置

    esp_err_t err = esp_camera_init(&config);
    ESP_LOGI(TAG, "camera init end, err=%d", err);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Camera init failed with error 0x%x", err);
        camera_enabled = false;
        xSemaphoreGive(camera_mutex);
        return false;
    }

    // 🔧 OV5640特定优化配置，解决NO-SOI问题
    sensor_t* sensor = esp_camera_sensor_get();
    if (sensor != NULL) {
        // 确保传感器已从软件掉电状态唤醒 (0x3008 = 0x02)
        if (sensor->set_reg) {
            sensor->set_reg(sensor, 0x3008, 0xFF, 0x02);
            vTaskDelay(10 / portTICK_PERIOD_MS);  // 10ms 稳定延迟
        }
        
        ESP_LOGI(TAG, "Applying OV5640 optimizations...");

        // 设置垂直翻转，改善图像方向
        if (sensor->set_vflip) {
            sensor->set_vflip(sensor, 1);
        }

        // 🔧 高分辨率彩色优化 - 最大化颜色表现
        if (sensor->set_brightness) {
            sensor->set_brightness(sensor, 2);  // 亮度 +2 (最大亮度)
        }
        if (sensor->set_saturation) {
            sensor->set_saturation(sensor, 4);  // 饱和度 +4 (最大饱和度，鲜艳彩色)
        }
        if (sensor->set_contrast) {
            sensor->set_contrast(sensor, 3);    // 对比度 +3 (最大对比度)
        }

        // 🔧 确认UXGA分辨率设置
        if (sensor->set_framesize) {
            sensor->set_framesize(sensor, FRAMESIZE_VGA);      // 确认640x480
            vTaskDelay(100 / portTICK_PERIOD_MS);
        }

        ESP_LOGI(TAG, "OV5640 optimizations applied");
    }

    ESP_LOGI(TAG, "Camera initialized successfully with PSRAM mode");
    camera_enabled = true;

    ESP_LOGI(TAG, "✅ 摄像头保持运行状态，支持拍照和视频");

    xSemaphoreGive(camera_mutex);
    return true;
}



static camera_fb_t* cam_capture(void){
    if (!camera_enabled) {
        ESP_LOGW(TAG, "Camera not enabled");
        return NULL;
    }

    if (xSemaphoreTake(camera_mutex, 5000 / portTICK_PERIOD_MS) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take camera mutex for capture");
        return NULL;
    }

    // 🔧 添加多次重试机制，应对NO-SOI问题
    camera_fb_t* fb = NULL;
    int retry_count = 0;
    const int max_retries = 3;

    while (retry_count < max_retries && fb == NULL) {
        fb = esp_camera_fb_get();
        if (fb == NULL) {
            retry_count++;
            ESP_LOGW(TAG, "Camera capture failed, retry %d/%d", retry_count, max_retries);

            if (retry_count < max_retries) {
                vTaskDelay(100 / portTICK_PERIOD_MS);  // 等待100ms后重试
            }
        } else {
            // 🔧 验证帧数据完整性
            if (fb->len == 0 || fb->buf == NULL) {
                ESP_LOGW(TAG, "Invalid frame buffer, retrying...");
                esp_camera_fb_return(fb);
                fb = NULL;
                retry_count++;
                if (retry_count < max_retries) {
                    vTaskDelay(100 / portTICK_PERIOD_MS);
                }
            }
        }
    }

    if (fb == NULL) {
        ESP_LOGE(TAG, "Camera capture failed after %d retries", max_retries);
        xSemaphoreGive(camera_mutex);
        return NULL;
    }

    ESP_LOGI(TAG, "Camera capture successful: %dx%d, %d bytes",
             fb->width, fb->height, fb->len);

    // 🔧 拍照完成后立即释放摄像头，防止发热
    // 注意：不在这里释放 mutex，由调用者在 cam_fb_return_safe 中处理。
    return fb;
}

static void cam_fb_return_safe(camera_fb_t* fb) {
    if (fb != NULL) {
        esp_camera_fb_return(fb);
    }

    // 🔧 基于官方方案：保持摄像头运行，避免重复初始化开销
    // 官方ESP32-S3 EYE示例从不调用esp_camera_deinit()
    ESP_LOGI(TAG, "📷 摄像头保持运行状态 (官方推荐方案)");

    xSemaphoreGive(camera_mutex);
}

// 🔧 相机诊断和恢复功能 - 专门解决NO-SOI问题 (未使用，注释避免警告)
/*
static bool cam_diagnose_and_recover(void) {
    ESP_LOGI(TAG, "Starting NO-SOI diagnosis and recovery...");

    if (xSemaphoreTake(camera_mutex, 10000 / portTICK_PERIOD_MS) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take camera mutex for diagnosis");
        return false;
    }

    bool recovery_success = false;

    // 步骤1: 检查相机状态
    sensor_t* sensor = esp_camera_sensor_get();
    if (sensor == NULL) {
        ESP_LOGE(TAG, "Camera sensor not available");
        goto cleanup;
    }

    ESP_LOGI(TAG, "Detected sensor PID: 0x%04X", sensor->id.PID);

    // 步骤2: OV5640特定的NO-SOI修复序列
    ESP_LOGI(TAG, "Applying OV5640 NO-SOI fix sequence...");

    // 2.1: 软重置传感器
    if (sensor->reset) {
        ESP_LOGI(TAG, "Performing sensor soft reset...");
        sensor->reset(sensor);
        vTaskDelay(200 / portTICK_PERIOD_MS);  // 增加延时
    }

    // 2.2: 重新初始化JPEG模式
    if (sensor->set_pixformat) {
        ESP_LOGI(TAG, "Reinitializing JPEG mode...");
        sensor->set_pixformat(sensor, PIXFORMAT_JPEG);
        vTaskDelay(100 / portTICK_PERIOD_MS);
    }

    // 2.3: 保持UXGA分辨率
    if (sensor->set_framesize) {
        ESP_LOGI(TAG, "Maintaining UXGA frame size...");
        sensor->set_framesize(sensor, FRAMESIZE_VGA);      // 640x480，高分辨率
        vTaskDelay(100 / portTICK_PERIOD_MS);
    }

    if (sensor->set_quality) {
        ESP_LOGI(TAG, "Setting moderate JPEG quality...");
        sensor->set_quality(sensor, 12);  // 🔥 中等质量，减少发烫
        vTaskDelay(50 / portTICK_PERIOD_MS);
    }

    // 2.4: 重新配置图像选项
    if (sensor->set_vflip) {
        sensor->set_vflip(sensor, 1);
    }
    if (sensor->set_brightness) {
        sensor->set_brightness(sensor, 1);
    }

    // 步骤3: 多次测试拍照，确保JPEG SOI正确
    ESP_LOGI(TAG, "Testing JPEG SOI generation...");
    int test_attempts = 3;
    for (int i = 0; i < test_attempts; i++) {
        vTaskDelay(200 / portTICK_PERIOD_MS);  // 等待传感器稳定

        camera_fb_t* test_fb = esp_camera_fb_get();
        if (test_fb != NULL && test_fb->len > 0) {
            // 检查JPEG SOI标记
            bool has_soi = (test_fb->len >= 3 &&
                           test_fb->buf[0] == 0xFF &&
                           test_fb->buf[1] == 0xD8 &&
                           test_fb->buf[2] == 0xFF);

            ESP_LOGI(TAG, "Test %d: Frame %dx%d, %d bytes, SOI: %s",
                     i+1, test_fb->width, test_fb->height, test_fb->len,
                     has_soi ? "OK" : "MISSING");

            esp_camera_fb_return(test_fb);

            if (has_soi) {
                recovery_success = true;
                break;
            }
        } else {
            ESP_LOGW(TAG, "Test %d: Failed to capture frame", i+1);
            if (test_fb) {
                esp_camera_fb_return(test_fb);
            }
        }
    }

    if (recovery_success) {
        ESP_LOGI(TAG, "NO-SOI recovery successful!");
        // 保持UXGA分辨率，平衡清晰度和性能
        ESP_LOGI(TAG, "Keeping UXGA resolution for balanced performance");
    } else {
        ESP_LOGE(TAG, "NO-SOI recovery failed after %d attempts", test_attempts);
    }

cleanup:
    xSemaphoreGive(camera_mutex);
    return recovery_success;
}
*/

// 🔧 摄像头状态监控任务 (仅用于状态报告)
static void camera_monitor_task(void *pvParameters) {
    ESP_LOGI(TAG, "Camera monitor task started");

    while (1) {
        // 每30秒报告一次状态
        vTaskDelay(30000 / portTICK_PERIOD_MS);

        if (camera_enabled) {
            ESP_LOGI(TAG, "📷 摄像头运行正常，优化配置防发热");
        }
    }
}

/* ---------------- IO ---------------- */
static void io_init(void){
    // 电机GPIO初始化
    gpio_set_direction(MOTOR_IN1, GPIO_MODE_OUTPUT);
    gpio_set_direction(MOTOR_IN2, GPIO_MODE_OUTPUT);
    gpio_set_level(MOTOR_IN1, 0);
    gpio_set_level(MOTOR_IN2, 0);

    // 💡 WS2812 LED初始化将在后面的led_strip_init中完成

    // 🔧 先把背光GPIO拉高，确保即使LEDC初始化失败也有背光
    gpio_set_direction(PIN_TFT_BL, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_TFT_BL, 1);

    // 🔧 背光PWM配置：修复背光不亮问题
    ledc_timer_config_t backlight_timer = {
        .duty_resolution = LEDC_TIMER_8_BIT,
        .freq_hz = 5000,  // 5kHz PWM频率
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .timer_num = TFT_BL_TIMER,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&backlight_timer));

    ledc_channel_config_t backlight_channel = {
        .channel = TFT_BL_CHANNEL,
        .duty = 0,  // 初始关闭背光
        .gpio_num = PIN_TFT_BL,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .hpoint = 0,
        .timer_sel = TFT_BL_TIMER
    };
    ESP_ERROR_CHECK(ledc_channel_config(&backlight_channel));

    ESP_LOGI(TAG, "🔧 硬件引脚分配完成 (4引脚方案):");
    ESP_LOGI(TAG, "🚗 电机+绕组: GPIO3/GPIO46 (DRV8833 IN1/IN2，物理并联)");
    ESP_LOGI(TAG, "💡 WS2812-1: GPIO1 (1颗LED，白闪+彩虹渐变)");
    ESP_LOGI(TAG, "💡 WS2812-48: GPIO48 (4颗LED串联，粉红渐变30秒，平滑效果)");
    ESP_LOGI(TAG, "📺 显示屏: GPIO2/21/41/42/47 (ST7789，使用GPIO2 MOSI)");
    ESP_LOGI(TAG, "🔆 背光: GPIO41 PWM控制 (LEDC_TIMER_2/CHANNEL_2)");

    // 🔧 初始化两个WS2812 LED
    // LED1 (GPIO1) - 白闪+彩虹 (1颗LED)
    led_strip_config_t strip_config_1 = {
        .strip_gpio_num = LED_PIN_1,
        .max_leds = LED_NUM_1,
        .led_pixel_format = LED_PIXEL_FORMAT_GRB,
        .led_model = LED_MODEL_WS2812
    };
    led_strip_rmt_config_t rmt_config_1 = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10 * 1000 * 1000,
        .mem_block_symbols = 64,
    };
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_config_1, &rmt_config_1, &led_strip_1));
    led_strip_clear(led_strip_1);

    // LED48 (GPIO48) - 粉红渐变 (4颗LED串联)
    led_strip_config_t strip_config_48 = {
        .strip_gpio_num = LED_PIN_48,
        .max_leds = LED_NUM_48,
        .led_pixel_format = LED_PIXEL_FORMAT_GRB,
        .led_model = LED_MODEL_WS2812
    };
    led_strip_rmt_config_t rmt_config_48 = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10 * 1000 * 1000,
        .mem_block_symbols = 64,
    };
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_config_48, &rmt_config_48, &led_strip_48));
    led_strip_clear(led_strip_48);

    ESP_LOGI(TAG, "IO system initialized with proper LEDC configuration");
}

// 🔧 背光控制函数 - 统一管理背光亮度
static void backlight_set_brightness(uint8_t brightness) {
    // brightness已经是uint8_t，最大值就是255，不需要检查

    esp_err_t ret = ledc_set_duty(LEDC_LOW_SPEED_MODE, TFT_BL_CHANNEL, brightness);
    if (ret == ESP_OK) {
        ledc_update_duty(LEDC_LOW_SPEED_MODE, TFT_BL_CHANNEL);
        ESP_LOGD(TAG, "🔆 背光亮度设置为: %d/255", brightness);
    } else {
        ESP_LOGE(TAG, "🔆 背光设置失败: %s", esp_err_to_name(ret));
    }
}
// 电机控制 - 添加边界检查和安全控制
static void motor_set(int speed){
    // 严格边界检查
    if (speed > 100) speed = 100;
    if (speed < -100) speed = -100;

    // 安全的方向控制
    if (speed == 0) {
        // 停止电机
        gpio_set_level(MOTOR_IN1, 0);
        gpio_set_level(MOTOR_IN2, 0);
    } else if (speed > 0) {
        // 正向
        gpio_set_level(MOTOR_IN1, 1);
        gpio_set_level(MOTOR_IN2, 0);
    } else {
        // 反向
        gpio_set_level(MOTOR_IN1, 0);
        gpio_set_level(MOTOR_IN2, 1);
    }

    ESP_LOGI(TAG, "Motor speed set to: %d", speed);
}

// 十六进制字符转数字 - 添加安全检查
static int hex_char_to_int(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;  // 无效字符
}

// 验证十六进制颜色格式
static bool is_valid_hex_color(const char* hex) {
    if (!hex || strlen(hex) != 7 || hex[0] != '#') {
        return false;
    }

    for (int i = 1; i < 7; i++) {
        if (hex_char_to_int(hex[i]) == -1) {
            return false;
        }
    }
    return true;
}

// LED颜色控制 - 异步按需初始化
static void led_hex(const char* hex){
    // 🔧 异步初始化GPIO48 LED，第一次使用时才启动
    if (!led_strip_48) {
        ESP_LOGI(TAG, "💡 Async GPIO48 LED initialization...");
        led_strip_config_t strip_config = {
            .strip_gpio_num = LED_PIN_48,
            .max_leds = LED_NUM_48,
            .led_pixel_format = LED_PIXEL_FORMAT_GRB,
            .led_model = LED_MODEL_WS2812
        };
        led_strip_rmt_config_t rmt_config = {
            .clk_src = RMT_CLK_SRC_DEFAULT,
            .resolution_hz = 10 * 1000 * 1000,
            .mem_block_symbols = 64,
        };
        esp_err_t ret = led_strip_new_rmt_device(&strip_config, &rmt_config, &led_strip_48);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "GPIO48 LED initialization failed: %s", esp_err_to_name(ret));
            return;
        }
        led_strip_clear(led_strip_48);
        ESP_LOGI(TAG, "✅ GPIO48 LED initialized on-demand");
    }

    if (!is_valid_hex_color(hex)) {
        ESP_LOGW(TAG, "Invalid hex color format: %s", hex ? hex : "NULL");
        return;
    }

    uint8_t r = hex_char_to_int(hex[1]) * 16 + hex_char_to_int(hex[2]);
    uint8_t g = hex_char_to_int(hex[3]) * 16 + hex_char_to_int(hex[4]);
    uint8_t b = hex_char_to_int(hex[5]) * 16 + hex_char_to_int(hex[6]);

    esp_err_t ret = led_strip_set_pixel(led_strip_48, 0, r, g, b);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set GPIO48 LED pixel: %s", esp_err_to_name(ret));
        return;
    }

    ret = led_strip_refresh(led_strip_48);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to refresh GPIO48 LED strip: %s", esp_err_to_name(ret));
        return;
    }

    ESP_LOGI(TAG, "LED color set to: %s (R:%d G:%d B:%d)", hex, r, g, b);
}

/* ---------------- 🎯 拍照特效系统 ---------------- */

// 🎯 电机+绕组控制 (DRV8833物理并联，简单控制)
static void motor_coil_control(int direction, uint32_t duration_ms) {
    ESP_LOGI(TAG, "🚗🧲 电机+绕组控制: 方向=%d, 时长=%lums", direction, (unsigned long)duration_ms);

    if (direction > 0) {
        // 正转：IN1=1, IN2=0
        gpio_set_level(MOTOR_IN1, 1);
        gpio_set_level(MOTOR_IN2, 0);
    } else if (direction < 0) {
        // 反转：IN1=0, IN2=1
        gpio_set_level(MOTOR_IN1, 0);
        gpio_set_level(MOTOR_IN2, 1);
    } else {
        // 停止：IN1=0, IN2=0
        gpio_set_level(MOTOR_IN1, 0);
        gpio_set_level(MOTOR_IN2, 0);
        ESP_LOGI(TAG, "🛑 电机+绕组已停止");
        return;
    }

    // 保持运行指定时间
    if (duration_ms > 0) {
        vTaskDelay(duration_ms / portTICK_PERIOD_MS);
        // 自动停止
        gpio_set_level(MOTOR_IN1, 0);
        gpio_set_level(MOTOR_IN2, 0);
        ESP_LOGI(TAG, "🛑 电机+绕组运行完成，已停止");
    }
}

// 🎯 GPIO48 LED彩虹渐变效果 (备用函数)
static void led_rainbow_effect(uint32_t duration_ms) {
    ESP_LOGI(TAG, "🌈 GPIO48 LED彩虹渐变开始，时长=%lums", (unsigned long)duration_ms);

    if (!led_strip_48) {
        ESP_LOGW(TAG, "GPIO48 LED strip not initialized");
        return;
    }

    uint32_t steps = duration_ms / 50;  // 每50ms一步
    for (uint32_t i = 0; i < steps; i++) {
        // HSV到RGB转换实现彩虹效果
        float hue = (float)(i * 360) / steps;  // 0-360度
        float saturation = 1.0f;
        float value = 1.0f;

        // 简化的HSV到RGB转换
        float c = value * saturation;
        float x = c * (1 - fabs(fmod(hue / 60.0, 2) - 1));
        float m = value - c;

        float r_f, g_f, b_f;
        if (hue < 60) {
            r_f = c; g_f = x; b_f = 0;
        } else if (hue < 120) {
            r_f = x; g_f = c; b_f = 0;
        } else if (hue < 180) {
            r_f = 0; g_f = c; b_f = x;
        } else if (hue < 240) {
            r_f = 0; g_f = x; b_f = c;
        } else if (hue < 300) {
            r_f = x; g_f = 0; b_f = c;
        } else {
            r_f = c; g_f = 0; b_f = x;
        }

        uint8_t r = (uint8_t)((r_f + m) * 255);
        uint8_t g = (uint8_t)((g_f + m) * 255);
        uint8_t b = (uint8_t)((b_f + m) * 255);

        led_strip_set_pixel(led_strip_48, 0, r, g, b);
        led_strip_refresh(led_strip_48);

        vTaskDelay(50 / portTICK_PERIOD_MS);
    }

    ESP_LOGI(TAG, "🌈 LED彩虹渐变完成");
}



// 🎯 GPIO1 WS2812白色闪烁效果
static void led1_white_blink(uint8_t count, uint32_t interval_ms) {
    ESP_LOGI(TAG, "💡 GPIO1 WS2812白色闪烁: %d次, 间隔=%lums", count, (unsigned long)interval_ms);

    if (!led_strip_1) {
        ESP_LOGW(TAG, "GPIO1 LED strip not initialized");
        return;
    }

    for (uint8_t i = 0; i < count; i++) {
        // 亮白色
        led_strip_set_pixel(led_strip_1, 0, 255, 255, 255);
        led_strip_refresh(led_strip_1);
        vTaskDelay(interval_ms / portTICK_PERIOD_MS);

        // 熄灭
        led_strip_set_pixel(led_strip_1, 0, 0, 0, 0);
        led_strip_refresh(led_strip_1);
        vTaskDelay(interval_ms / portTICK_PERIOD_MS);
    }
}

// 🎯 GPIO1 WS2812彩虹渐变效果
static void led1_rainbow_effect(uint32_t duration_ms) {
    ESP_LOGI(TAG, "🌈 GPIO1 WS2812彩虹渐变开始，时长=%lums", (unsigned long)duration_ms);

    if (!led_strip_1) {
        ESP_LOGW(TAG, "GPIO1 LED strip not initialized");
        return;
    }

    uint32_t steps = duration_ms / 50;  // 每50ms一步
    for (uint32_t i = 0; i < steps; i++) {
        // HSV到RGB转换实现彩虹效果
        float hue = (float)(i * 360) / steps;  // 0-360度
        float saturation = 1.0f;
        float value = 1.0f;

        // 简化的HSV到RGB转换
        float c = value * saturation;
        float x = c * (1 - fabs(fmod(hue / 60.0, 2) - 1));
        float m = value - c;

        float r_f, g_f, b_f;
        if (hue < 60) {
            r_f = c; g_f = x; b_f = 0;
        } else if (hue < 120) {
            r_f = x; g_f = c; b_f = 0;
        } else if (hue < 180) {
            r_f = 0; g_f = c; b_f = x;
        } else if (hue < 240) {
            r_f = 0; g_f = x; b_f = c;
        } else if (hue < 300) {
            r_f = x; g_f = 0; b_f = c;
        } else {
            r_f = c; g_f = 0; b_f = x;
        }

        uint8_t r = (uint8_t)((r_f + m) * 255);
        uint8_t g = (uint8_t)((g_f + m) * 255);
        uint8_t b = (uint8_t)((b_f + m) * 255);

        led_strip_set_pixel(led_strip_1, 0, r, g, b);
        led_strip_refresh(led_strip_1);

        vTaskDelay(50 / portTICK_PERIOD_MS);
    }

    // 最后熄灭GPIO1
    led_strip_set_pixel(led_strip_1, 0, 0, 0, 0);
    led_strip_refresh(led_strip_1);
    ESP_LOGI(TAG, "🌈 GPIO1 WS2812彩虹渐变完成");
}

// 🎯 GPIO48 WS2812粉红色渐亮渐灭效果
static void led48_pink_fade_effect(uint32_t fade_in_ms, uint32_t hold_ms, uint32_t fade_out_ms) {
    ESP_LOGI(TAG, "💖 GPIO48 WS2812粉红色渐变: 渐亮=%lums, 保持=%lums, 渐灭=%lums",
             (unsigned long)fade_in_ms, (unsigned long)hold_ms, (unsigned long)fade_out_ms);

    if (!led_strip_48) {
        ESP_LOGW(TAG, "GPIO48 LED strip not initialized");
        return;
    }

    // 渐亮阶段
    uint32_t fade_in_steps = fade_in_ms / 50;  // 每50ms一步
    for (uint32_t i = 0; i <= fade_in_steps; i++) {
        uint8_t brightness = (uint8_t)(255 * i / fade_in_steps);
        // 粉红色 RGB(255, 105, 180) - 最高亮度
        uint8_t r = (brightness * 255) / 255;  // 红色分量
        uint8_t g = (brightness * 105) / 255;  // 绿色分量
        uint8_t b = (brightness * 180) / 255;  // 蓝色分量
        // 设置4颗LED都是相同颜色
        for (int j = 0; j < LED_NUM_48; j++) {
            led_strip_set_pixel(led_strip_48, j, r, g, b);
        }
        led_strip_refresh(led_strip_48);
        vTaskDelay(50 / portTICK_PERIOD_MS);
    }

    // 保持亮度 (粉红色最高亮度) - 4颗LED
    for (int j = 0; j < LED_NUM_48; j++) {
        led_strip_set_pixel(led_strip_48, j, 255, 105, 180);
    }
    led_strip_refresh(led_strip_48);
    vTaskDelay(hold_ms / portTICK_PERIOD_MS);

    // 渐灭阶段
    uint32_t fade_out_steps = fade_out_ms / 50;
    for (uint32_t i = fade_out_steps; i > 0; i--) {
        uint8_t brightness = (uint8_t)(255 * i / fade_out_steps);
        uint8_t r = (brightness * 255) / 255;  // 粉红色最高亮度
        uint8_t g = (brightness * 105) / 255;
        uint8_t b = (brightness * 180) / 255;
        // 设置4颗LED都是相同颜色
        for (int j = 0; j < LED_NUM_48; j++) {
            led_strip_set_pixel(led_strip_48, j, r, g, b);
        }
        led_strip_refresh(led_strip_48);
        vTaskDelay(50 / portTICK_PERIOD_MS);
    }

    // 完全熄灭 - 4颗LED
    for (int j = 0; j < LED_NUM_48; j++) {
        led_strip_set_pixel(led_strip_48, j, 0, 0, 0);
    }
    led_strip_refresh(led_strip_48);
    ESP_LOGI(TAG, "💖 GPIO48 WS2812粉红色渐变完成");
}



// 🎯 拍照特效主任务
static void photo_effect_task(void *pvParameters) {
    ESP_LOGI(TAG, "🎬 拍照特效任务开始");

    if (xSemaphoreTake(effect_mutex, 5000 / portTICK_PERIOD_MS) != pdTRUE) {
        ESP_LOGE(TAG, "❌ 无法获取特效互斥锁");
        photo_effect_running = false;
        vTaskDelete(NULL);
        return;
    }

    // 🎬 特效序列开始
    ESP_LOGI(TAG, "🎬 开始拍照特效序列...");

    // 1️⃣ 电机+绕组正转1秒 (GPIO3/GPIO46)
    ESP_LOGI(TAG, "1️⃣ 电机+绕组正转1秒");
    motor_coil_control(1, 1000);

    // 2️⃣ 电机+绕组反转1秒 (GPIO3/GPIO46)
    ESP_LOGI(TAG, "2️⃣ 电机+绕组反转1秒");
    motor_coil_control(-1, 1000);

    // 🛑 电机+绕组完全停止
    ESP_LOGI(TAG, "🛑 电机+绕组一个循环完成，全部关闭");
    motor_coil_control(0, 0);

    // 3️⃣ GPIO1 WS2812白色闪烁2次
    ESP_LOGI(TAG, "3️⃣ GPIO1 WS2812白色闪烁2次");
    led1_white_blink(2, 200);  // 闪烁2次，每次200ms

    // 4️⃣ GPIO1 WS2812彩虹渐变
    ESP_LOGI(TAG, "4️⃣ GPIO1 WS2812彩虹渐变");
    led1_rainbow_effect(3000);  // 3秒彩虹渐变

    // 5️⃣ 拍照并显示到屏幕
    ESP_LOGI(TAG, "5️⃣ 拍照并显示到屏幕");
    esp_err_t photo_result = camera_capture_and_display();
    if (photo_result == ESP_OK) {
        ESP_LOGI(TAG, "✅ 拍照并显示成功");
    } else {
        ESP_LOGE(TAG, "❌ 拍照并显示失败");
    }

    // 6️⃣ GPIO48 WS2812粉红渐变 (在拍照显示后执行)
    ESP_LOGI(TAG, "6️⃣ GPIO48 WS2812粉红渐变开始");
    led48_pink_fade_effect(15000, 0, 15000);  // 渐亮15s，无保持，渐灭15s (总共30s)

    ESP_LOGI(TAG, "✅ 拍照特效序列完成");

    // 清理
    photo_effect_running = false;
    xSemaphoreGive(effect_mutex);
    photo_effect_task_handle = NULL;
    vTaskDelete(NULL);
}

// 🎬 拍照并显示函数实现 (基于display_image_handler逻辑)
static esp_err_t camera_capture_and_display(void) {
    ESP_LOGI(TAG, "📸 开始拍照并显示到屏幕");

    // 确保摄像头就绪
    if (!ensure_camera_is_ready()) {
        ESP_LOGE(TAG, "❌ 摄像头初始化失败");
        return ESP_FAIL;
    }

    // 获取摄像头传感器
    sensor_t *s = esp_camera_sensor_get();
    if (!s) {
        ESP_LOGE(TAG, "❌ 无法获取摄像头传感器");
        return ESP_FAIL;
    }

    // 保存当前格式和分辨率
    pixformat_t original_format = s->pixformat;
    framesize_t original_framesize = s->status.framesize;

    // 切换到RGB565格式 + HD分辨率
    if (s->set_pixformat(s, PIXFORMAT_RGB565) != 0) {
        ESP_LOGE(TAG, "❌ 切换到RGB565格式失败");
        return ESP_FAIL;
    }

    if (s->set_framesize(s, FRAMESIZE_HD) != 0) {
        ESP_LOGE(TAG, "❌ 切换到HD分辨率失败");
        s->set_pixformat(s, original_format);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "✅ 摄像头已切换到RGB565+HD模式");

    // 获取RGB565图片
    camera_fb_t *pic = esp_camera_fb_get();
    if (!pic) {
        ESP_LOGE(TAG, "❌ RGB565拍照失败");
        s->set_pixformat(s, original_format);
        s->set_framesize(s, original_framesize);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "✅ RGB565拍照成功: %dx%d, %u bytes", pic->width, pic->height, pic->len);

    // 分配缓冲区并拷贝数据
    uint8_t *rgb_buf = heap_caps_malloc(pic->len, MALLOC_CAP_SPIRAM);
    if (!rgb_buf) {
        ESP_LOGE(TAG, "❌ RGB565缓冲区分配失败: %u bytes", pic->len);
        esp_camera_fb_return(pic);
        s->set_pixformat(s, original_format);
        s->set_framesize(s, original_framesize);
        return ESP_FAIL;
    }

    // 直接内存拷贝
    memcpy(rgb_buf, pic->buf, pic->len);

    // 创建RGB565图片描述符
    lv_image_dsc_t img_dsc = {
        .header.magic = LV_IMAGE_HEADER_MAGIC,
        .header.cf = LV_COLOR_FORMAT_RGB565,
        .header.flags = 0,
        .header.w = pic->width,
        .header.h = pic->height,
        .header.stride = pic->width * 2,  // RGB565 = 2 bytes per pixel
        .header.reserved_2 = 0,
        .data_size = pic->len,
        .data = (const uint8_t*)rgb_buf,
        .reserved = NULL,
        .reserved_2 = NULL
    };

    // 释放摄像头缓冲区
    esp_camera_fb_return(pic);

    // 恢复摄像头格式和分辨率
    s->set_pixformat(s, original_format);
    s->set_framesize(s, original_framesize);
    ESP_LOGI(TAG, "✅ 摄像头格式和分辨率已恢复");

    // 恢复LVGL，切换回UI模式
    esp_err_t lvgl_ret = lvgl_port_resume();
    if (lvgl_ret == ESP_OK) {
        ESP_LOGI(TAG, "✅ LVGL已恢复，切换回UI模式");
    } else {
        ESP_LOGW(TAG, "⚠️ LVGL恢复失败: %s", esp_err_to_name(lvgl_ret));
    }

    // 发送到UI显示
    sisi_ui_display_image(&img_dsc);

    ESP_LOGI(TAG, "📺 ✅ 拍照并显示完成，照片已发送到显示队列");
    return ESP_OK;
}

// 🎯 启动拍照特效 (外部调用接口)
static esp_err_t start_photo_effect(void) {
    if (photo_effect_running) {
        ESP_LOGW(TAG, "⚠️ 拍照特效已在运行中");
        return ESP_ERR_INVALID_STATE;
    }

    // 创建互斥锁
    if (effect_mutex == NULL) {
        effect_mutex = xSemaphoreCreateMutex();
        if (effect_mutex == NULL) {
            ESP_LOGE(TAG, "❌ 创建特效互斥锁失败");
            return ESP_ERR_NO_MEM;
        }
    }

    photo_effect_running = true;

    // 创建特效任务
    BaseType_t result = xTaskCreate(
        photo_effect_task,
        "photo_effect",
        4096,  // 栈大小
        NULL,
        5,     // 优先级
        &photo_effect_task_handle
    );

    if (result != pdPASS) {
        ESP_LOGE(TAG, "❌ 创建拍照特效任务失败");
        photo_effect_running = false;
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "🎬 拍照特效任务已启动");
    return ESP_OK;
}

/* ---------------- 线程安全显示任务 ---------------- */

// 显示消息处理任务 - 线程安全版本，带错误处理
static void display_message_task(void *pvParameters) {
    display_message_t msg;
    while (1) {
        if (xQueueReceive(display_queue, &msg, portMAX_DELAY) == pdPASS) {
            ESP_LOGI(TAG, "📬 [显示任务] 收到消息: 类型='%s'", msg.type);

            if (strcmp(msg.type, "text") == 0) {
                // 文字推送是轻量级操作，且已在sisi_ui内部处理好，可以直接调用
                sisi_ui_update_sisi_text(msg.data);
            // 🧹 清理：删除视频服务器设置
            } else if (strcmp(msg.type, "mode") == 0) {
                if (strcmp(msg.data, "standby") == 0) {
                    sisi_ui_switch_scene(UI_SCENE_INTERACTIVE, NULL);
                } else if (strcmp(msg.data, "text") == 0) {
                    ui_data_t data = {.text1 = "Text Mode"};
                    sisi_ui_switch_scene(UI_SCENE_INTERACTIVE, &data);
                // 🧹 清理：删除视频模式切换
                // } else if (strcmp(msg.data, "video") == 0) {
                //     sisi_ui_switch_scene(UI_SCENE_BOOT_VIDEO, NULL);
                }  // 修复：添加缺失的右大括号
            } else if (strcmp(msg.type, "spectrum") == 0) {
                // 音频频谱是数据更新，不是场景切换，也是安全的
                sisi_ui_update_audio_spectrum((const uint8_t*)msg.data, 8); // 假设8个频段
            }
        }
    }
}

// 发送显示消息到队列 - 线程安全
static bool send_display_message(const char* type, const char* data) {
    if (!display_queue) {
        ESP_LOGE(TAG, "❌ 显示队列未初始化");
        return false;
    }

    display_message_t msg;
    strncpy(msg.type, type, sizeof(msg.type) - 1);
    msg.type[sizeof(msg.type) - 1] = '\0';
    strncpy(msg.data, data, sizeof(msg.data) - 1);
    msg.data[sizeof(msg.data) - 1] = '\0';

    if (xQueueSend(display_queue, &msg, pdMS_TO_TICKS(100)) == pdTRUE) {
        ESP_LOGI(TAG, "✅ 显示消息已发送: %s -> %s", type, data);
        return true;
    } else {
        ESP_LOGE(TAG, "❌ 显示消息发送失败: 队列满");
        return false;
    }
}

/* ---------------- HTTP API处理器 ---------------- */

// 状态页面处理器
static esp_err_t status_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "📊 状态页面请求");

    // 构建状态JSON
    char status_json[512];
    snprintf(status_json, sizeof(status_json),
        "{"
        "\"device\":\"SISIeyes\","
        "\"version\":\"1.0.0\","
        "\"wifi_connected\":%s,"
        "\"camera_enabled\":%s,"
        "\"display_mode\":\"%s\","
        "\"uptime\":%d"
        "}",
        "true",  // WiFi状态
        camera_enabled ? "true" : "false",
        "video",  // 当前显示模式
        (int)(xTaskGetTickCount() * portTICK_PERIOD_MS / 1000)  // 运行时间(秒)
    );

    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_sendstr(req, status_json);
    return ESP_OK;
}

// 控制页面处理器
static esp_err_t control_page_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "🎮 控制页面请求");

    const char* control_html =
        "<!DOCTYPE html><html><head><title>SISIeyes Control</title></head>"
        "<body><h1>SISIeyes Control Panel</h1>"
        "<h2>Display Control</h2>"
        "<button onclick=\"sendCommand('sisi:Hello World')\">Test Text</button><br>"
        "<button onclick=\"sendCommand('video_server:http://192.168.1.100:8080')\">Set Video Server</button><br>"
        "<h2>Camera Control</h2>"
        "<button onclick=\"takePhoto()\">Take Photo</button><br>"
        "<img id=\"photo\" style=\"max-width:300px;\"><br>"
        "<script>"
        "function sendCommand(cmd) {"
        "  fetch('/cmd', {method:'POST', body:cmd})"
        "  .then(r => r.text()).then(t => alert(t));"
        "}"
        "function takePhoto() {"
        "  fetch('/camera/snap', {method:'POST'})"
        "  .then(r => r.blob())"
        "  .then(b => document.getElementById('photo').src = URL.createObjectURL(b));"
        "}"
        "</script></body></html>";

    httpd_resp_set_type(req, "text/html");
    httpd_resp_sendstr(req, control_html);
    return ESP_OK;
}

// 摄像头帧处理器 - 统一API，复用cmd_handler逻辑
static esp_err_t camera_frame_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "📷 统一API摄像头帧请求");

    if (!ensure_camera_is_ready()) {
        httpd_resp_send_err(req, 503, "Camera init failed");
        return ESP_FAIL;
    }

    camera_fb_t *fb = cam_capture();
    if (!fb) {
        ESP_LOGW(TAG, "Frame capture failed");
        httpd_resp_send_err(req, 500, "Frame capture failed");
        return ESP_FAIL;
    }

    // 验证图像数据
    if (fb->len == 0 || fb->buf == NULL) {
        ESP_LOGE(TAG, "Invalid frame buffer data");
        cam_fb_return_safe(fb);
        httpd_resp_send_err(req, 500, "Invalid frame data");
        return ESP_FAIL;
    }

    // 设置响应头
    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_hdr(req, "Cache-Control", "no-cache");

    // 发送图像数据
    esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);

    ESP_LOGI(TAG, "📷 统一API发送帧: %dx%d, %d bytes", fb->width, fb->height, fb->len);
    cam_fb_return_safe(fb);

    // 🔧 基于官方方案：保持摄像头运行，提高响应速度
    ESP_LOGI(TAG, "📷 摄像头保持运行状态 (官方推荐方案)");

    return res;
}

// 摄像头拍照处理器 - 统一API，复用cmd_handler逻辑
static esp_err_t camera_snap_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "📸🎬 拍照请求 + 特效启动");

    // 🎬 启动拍照特效 (异步执行)
    esp_err_t effect_result = start_photo_effect();
    if (effect_result != ESP_OK) {
        ESP_LOGW(TAG, "⚠️ 拍照特效启动失败，但继续拍照: %s", esp_err_to_name(effect_result));
    } else {
        ESP_LOGI(TAG, "🎬 拍照特效已启动 (异步执行)");
    }

    if (!ensure_camera_is_ready()) {
        httpd_resp_send_err(req, 503, "Camera init failed");
        return ESP_FAIL;
    }

    camera_fb_t *fb = cam_capture();
    if (!fb) {
        ESP_LOGW(TAG, "Photo capture failed");
        httpd_resp_send_err(req, 500, "Photo capture failed");
        return ESP_FAIL;
    }

    // 验证图像数据
    if (fb->len == 0 || fb->buf == NULL) {
        ESP_LOGE(TAG, "Invalid photo buffer data");
        cam_fb_return_safe(fb);
        httpd_resp_send_err(req, 500, "Invalid photo data");
        return ESP_FAIL;
    }

    // 设置响应头
    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=sisieyes_photo.jpg");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    // 发送图像数据
    esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);

    ESP_LOGI(TAG, "📸 统一API拍照完成: %dx%d, %d bytes", fb->width, fb->height, fb->len);
    cam_fb_return_safe(fb);

    return res;
}

// 摄像头流处理器
static esp_err_t camera_stream_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "📹 视频流请求");

    if (!camera_enabled) {
        httpd_resp_send_err(req, 503, "Camera not initialized");
        return ESP_FAIL;
    }

    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    char part_buf[64];

    // 设置MJPEG流头
    httpd_resp_set_type(req, "multipart/x-mixed-replace; boundary=--SISIEYES");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_hdr(req, "X-Framerate", "10");

    while (true) {
        fb = cam_capture();
        if (!fb) {
            ESP_LOGE(TAG, "Camera capture failed");
            res = ESP_FAIL;
            break;
        }

        // 发送帧边界
        size_t hlen = snprintf(part_buf, 64,
            "\r\n--SISIEYES\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
            fb->len);
        res = httpd_resp_send_chunk(req, part_buf, hlen);
        if (res != ESP_OK) break;

        // 发送图像数据
        res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
        if (res != ESP_OK) break;

        cam_fb_return_safe(fb);
        fb = NULL;

        // 控制帧率 (10fps)
        vTaskDelay(100 / portTICK_PERIOD_MS);
    }

    if (fb) {
        cam_fb_return_safe(fb);
    }

    return res;
}

// 🔧 显示图片处理器 - ESP-BSP原理：直接从摄像头获取RGB565
static esp_err_t display_image_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "📺 ESP-BSP原理显示图片请求");

    // ESP-BSP原理：不接收外部数据，直接从摄像头获取RGB565
    if (!ensure_camera_is_ready()) {
        httpd_resp_send_err(req, 503, "Camera init failed");
        return ESP_FAIL;
    }

    // 🔧 临时切换摄像头到RGB565模式 (ESP-BSP原理)
    sensor_t *s = esp_camera_sensor_get();
    if (!s) {
        ESP_LOGE(TAG, "❌ 无法获取摄像头传感器");
        httpd_resp_send_err(req, 500, "Camera sensor error");
        return ESP_FAIL;
    }

    // 保存当前格式和分辨率
    pixformat_t original_format = s->pixformat;
    framesize_t original_framesize = s->status.framesize;

    // 切换到RGB565格式 + QVGA分辨率 (ESP-BSP原理适配竖屏)
    if (s->set_pixformat(s, PIXFORMAT_RGB565) != 0) {
        ESP_LOGE(TAG, "❌ 切换到RGB565格式失败");
        httpd_resp_send_err(req, 500, "Failed to set RGB565 format");
        return ESP_FAIL;
    }

    // 设置HD分辨率 (1280x720，高分辨率显示)
    if (s->set_framesize(s, FRAMESIZE_HD) != 0) {
        ESP_LOGE(TAG, "❌ 切换到HD分辨率失败");
        s->set_pixformat(s, original_format);
        httpd_resp_send_err(req, 500, "Failed to set HD framesize");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "✅ 摄像头已切换到RGB565+HD模式 (1280x720 → 172x320竖屏)");

    // 获取RGB565图片
    camera_fb_t *pic = esp_camera_fb_get();
    if (!pic) {
        ESP_LOGE(TAG, "❌ RGB565拍照失败");
        s->set_pixformat(s, original_format);  // 恢复格式
        httpd_resp_send_err(req, 500, "RGB565 capture failed");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "✅ RGB565拍照成功: %dx%d, %u bytes",
             pic->width, pic->height, pic->len);

    // 🔧 分配缓冲区并拷贝数据 (ESP-BSP原理)
    uint8_t *rgb_buf = heap_caps_malloc(pic->len, MALLOC_CAP_SPIRAM);
    if (!rgb_buf) {
        ESP_LOGE(TAG, "❌ RGB565缓冲区分配失败: %u bytes", pic->len);
        esp_camera_fb_return(pic);
        s->set_pixformat(s, original_format);
        s->set_framesize(s, original_framesize);
        httpd_resp_send_err(req, 500, "Memory allocation failed");
        return ESP_FAIL;
    }

    // ESP-BSP核心原理：直接内存拷贝
    memcpy(rgb_buf, pic->buf, pic->len);

    // 创建RGB565图片描述符
    lv_image_dsc_t img_dsc = {
        .header.magic = LV_IMAGE_HEADER_MAGIC,
        .header.cf = LV_COLOR_FORMAT_RGB565,
        .header.flags = 0,
        .header.w = pic->width,
        .header.h = pic->height,
        .header.stride = pic->width * 2,  // RGB565 = 2 bytes per pixel
        .header.reserved_2 = 0,
        .data_size = pic->len,
        .data = (const uint8_t*)rgb_buf,
        .reserved = NULL,
        .reserved_2 = NULL
    };

    // 释放摄像头缓冲区
    esp_camera_fb_return(pic);

    // 恢复摄像头格式和分辨率
    s->set_pixformat(s, original_format);
    s->set_framesize(s, original_framesize);
    ESP_LOGI(TAG, "✅ 摄像头格式和分辨率已恢复");

    // 🔧 关键修复：拍照时恢复LVGL，切换回UI模式
    esp_err_t lvgl_ret = lvgl_port_resume();
    if (lvgl_ret == ESP_OK) {
        ESP_LOGI(TAG, "✅ 拍照时LVGL已恢复，切换回UI模式");
    } else {
        ESP_LOGW(TAG, "⚠️ 拍照时LVGL恢复失败: %s", esp_err_to_name(lvgl_ret));
    }

    // 发送到UI显示 (ESP-BSP原理)
    sisi_ui_display_image(&img_dsc);

    ESP_LOGI(TAG, "📺 ESP-BSP原理图片已发送到显示队列");
    httpd_resp_send(req, "Image sent to display", HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

// 显示文字处理器 - 线程安全版本
static esp_err_t display_text_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "📝 统一API显示文字请求");

    char *buf = NULL;
    size_t content_len = req->content_len;

    if (content_len >= 1024) {
        httpd_resp_send_err(req, 400, "Content too long");
        return ESP_FAIL;
    }

    buf = malloc(content_len + 1);
    if (!buf) {
        httpd_resp_send_err(req, 500, "Memory allocation failed");
        return ESP_FAIL;
    }

    int ret = httpd_req_recv(req, buf, content_len);
    if (ret <= 0) {
        free(buf);
        if (ret == HTTPD_SOCK_ERR_TIMEOUT) {
            httpd_resp_send_408(req);
        }
        return ESP_FAIL;
    }
    buf[content_len] = '\0';

    // 🔧 线程安全：发送到消息队列，让LVGL任务处理
    bool success = send_display_message("text", buf);

    if (success) {
        httpd_resp_sendstr(req, "Text message sent to display queue");
        ESP_LOGI(TAG, "✅ 文字消息已发送到队列: %s", buf);
    } else {
        httpd_resp_sendstr(req, "Failed to send text message");
        ESP_LOGE(TAG, "❌ 文字消息发送失败: %s", buf);
    }

    free(buf);
    return ESP_OK;
}

// 显示模式处理器
static esp_err_t display_mode_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "🎮 显示模式请求");

    char *buf = NULL;
    size_t content_len = req->content_len;

    if (content_len >= 256) {
        httpd_resp_send_err(req, 400, "Content too long");
        return ESP_FAIL;
    }

    buf = malloc(content_len + 1);
    if (!buf) {
        httpd_resp_send_err(req, 500, "Memory allocation failed");
        return ESP_FAIL;
    }

    int ret = httpd_req_recv(req, buf, content_len);
    if (ret <= 0) {
        free(buf);
        if (ret == HTTPD_SOCK_ERR_TIMEOUT) {
            httpd_resp_send_408(req);
        }
        return ESP_FAIL;
    }
    buf[content_len] = '\0';

    // 解析模式
    if (strcmp(buf, "video") == 0) {
        // 切换到视频模式
        ESP_LOGI(TAG, "🎬 切换到视频模式");
        // TODO: 实现视频模式切换
    } else if (strcmp(buf, "text") == 0) {
        // 切换到文字模式
        ESP_LOGI(TAG, "📝 切换到文字模式");
        // TODO: 实现文字模式切换
    } else if (strcmp(buf, "idle") == 0) {
        // 🔧 修复：使用线程安全的消息队列切换到待机模式
        ESP_LOGI(TAG, "💤 切换到待机模式");
        bool success = send_display_message("mode", "idle");
        if (!success) {
            ESP_LOGE(TAG, "❌ 待机模式切换失败");
        }
    }

    httpd_resp_sendstr(req, "Display mode changed");
    free(buf);
    return ESP_OK;
}

// 🧹 删除错误的音频接口，使用原来的audiodata:命令

// 🧹 清理：删除视频服务器处理器

// 原有的命令处理器 - 保持兼容性
static esp_err_t cmd_handler(httpd_req_t *req){
    // 🔧 简单策略：收到任何数据就停视频
    sisi_ui_stop_idle_video();

    char *buf = NULL;
    size_t content_len = req->content_len;

    // 检查请求方法和内容长度
    if (req->method == HTTP_GET) {
        // GET请求，返回系统状态或欢迎信息
        char welcome[256];
        snprintf(welcome, sizeof(welcome),
            "{\"status\":\"SISIeyes Ready\",\"ip\":\"172.20.10.2\",\"endpoints\":[\"/\",\"/control\",\"/cmd\"]}");
        httpd_resp_set_type(req, "application/json");
        httpd_resp_sendstr(req, welcome);
        return ESP_OK;
    }

    if (content_len == 0) {
        httpd_resp_send_err(req, 400, "No data received for POST request");
        return ESP_FAIL;
    }

    if (content_len > HTTP_BUFFER_SIZE) {
        ESP_LOGW(TAG, "Content too large: %d bytes, max: %d", content_len, HTTP_BUFFER_SIZE);
        httpd_resp_send_err(req, 413, "Content too large");
        return ESP_FAIL;
    }

    // 动态分配缓冲区
    buf = malloc(content_len + 1);
    if (!buf) {
        ESP_LOGE(TAG, "Failed to allocate %d bytes for HTTP buffer", content_len + 1);
        httpd_resp_send_err(req, 500, "Memory allocation failed");
        return ESP_FAIL;
    }

    // 流式读取数据
    size_t received = 0;
    while (received < content_len) {
        int ret = httpd_req_recv(req, buf + received, content_len - received);
        if (ret <= 0) {
            if (ret == HTTPD_SOCK_ERR_TIMEOUT) {
                ESP_LOGW(TAG, "HTTP receive timeout");
                httpd_resp_send_err(req, 408, "Request timeout");
            } else {
                ESP_LOGE(TAG, "HTTP receive error: %d", ret);
                httpd_resp_send_err(req, 400, "Receive error");
            }
            free(buf);
            return ESP_FAIL;
        }
        received += ret;
    }

    buf[content_len] = '\0';  // 确保字符串结束
    ESP_LOGI(TAG, "Received command (%d bytes): %.100s%s", content_len, buf, content_len > 100 ? "..." : "");

    esp_err_t result = ESP_OK;

    // 🔧 异步按需拍照功能 - 临时启动摄像头
    if(strcmp(buf,"snap")==0){
        ESP_LOGI(TAG, "📷 Async camera startup for photo capture...");
        if(ensure_camera_is_ready()){
             // 拍照逻辑复用 /camera/snap, 这里可以只返回成功信息
             httpd_resp_sendstr(req, "Camera ready, use /camera/snap");
        } else {
            httpd_resp_send_err(req, 500, "Camera async init failed");
        }
        free(buf);
        return ESP_OK;
    }

    // 🎬 拍照特效测试接口
    if(strcmp(buf,"photo_effect")==0){
        ESP_LOGI(TAG, "🎬 拍照特效测试请求");
        esp_err_t effect_result = start_photo_effect();
        if (effect_result == ESP_OK) {
            httpd_resp_sendstr(req, "Photo effect started successfully");
            ESP_LOGI(TAG, "✅ 拍照特效启动成功");
        } else {
            httpd_resp_send_err(req, 500, "Photo effect start failed");
            ESP_LOGE(TAG, "❌ 拍照特效启动失败: %s", esp_err_to_name(effect_result));
        }
        free(buf);
        return ESP_OK;
    }

    // 电机控制 - 添加输入验证
    if(strncmp(buf,"motor:",6)==0){
        char *endptr;
        long speed_long = strtol(buf+6, &endptr, 10);

        if (endptr == buf+6 || *endptr != '\0') {
            httpd_resp_send_err(req, 400, "Invalid motor speed format");
            result = ESP_FAIL;
            goto cleanup;
        }

        int speed = (int)speed_long;
        motor_set(speed);

        // 🔧 电机控制不阻塞HTTP，由定时器任务处理自动停止
        // TODO: 添加电机定时器任务来处理自动停止

        httpd_resp_sendstr(req, "Motor set");
        result = ESP_OK;
        goto cleanup;
    }

    // 音频数据可视化 - SmartSisi音频频谱数据
    if(strncmp(buf,"audiodata:",10)==0){
        ESP_LOGI(TAG, "🎵 收到音频频谱数据: %s", buf+10);

        // 🔧 简单方案：收到音频数据时停止视频，避免冲突
        sisi_ui_stop_idle_video();

        // 🔥 解析8个频段的赛博朋克音频数据
        uint8_t spectrum_data[8] = {0};
        char *data_str = strdup(buf + 10);  // 复制字符串避免修改原始数据
        char *token = strtok(data_str, ",");
        int i = 0;

        while (token != NULL && i < 8) {  // 🔥 支持8个频段
            spectrum_data[i] = (uint8_t)atoi(token);
            token = strtok(NULL, ",");
            i++;
        }

        free(data_str);

        // 发送到UI模块进行可视化
        sisi_ui_update_audio_spectrum(spectrum_data, 8);  // 🔥 8个频段
        ESP_LOGI(TAG, "🎵 赛博朋克音频数据已更新: [%d,%d,%d,%d,%d,%d,%d,%d]",
                 spectrum_data[0], spectrum_data[1], spectrum_data[2], spectrum_data[3],
                 spectrum_data[4], spectrum_data[5], spectrum_data[6], spectrum_data[7]);

        httpd_resp_sendstr(req, "Audio spectrum data received");
        result = ESP_OK;
        goto cleanup;
    }

    // LED颜色控制 - 使用改进的验证
    if(strncmp(buf,"led:",4)==0){
        if(strcmp(buf+4,"rainbow")==0){
            // GPIO48 LED彩虹效果
            led_rainbow_effect(3000);  // 3秒彩虹渐变
            httpd_resp_sendstr(req, "LED rainbow effect started");
        } else {
            // 十六进制颜色设置
            led_hex(buf+4);
            httpd_resp_sendstr(req, "LED color set");
        }
        result = ESP_OK;
        goto cleanup;
    }

    // 音频播放控制和可视化
    if(strncmp(buf,"audio:",6)==0){
        if(strncmp(buf+6,"tone:",5)==0){
            char *endptr;
            float freq = strtof(buf+11, &endptr);
            if (endptr == buf+11 || freq <= 0) {
                httpd_resp_send_err(req, 400, "Invalid frequency");
                result = ESP_FAIL;
                goto cleanup;
            }
            audio_play_tone(freq, 1000); // 播放1秒
            httpd_resp_sendstr(req, "Audio tone queued");
        } else if(strcmp(buf+6,"stop")==0){
            if (xSemaphoreTake(audio_mutex, 1000 / portTICK_PERIOD_MS) == pdTRUE) {
                audio_playing = false;
                xSemaphoreGive(audio_mutex);
            }
            httpd_resp_sendstr(req, "Audio stopped");
        } else {
            // 🔧 支持音频可视化数据格式: audio:100,150,200,255
            char* audio_data_str = buf + 6;
            ESP_LOGI(TAG, "🎵 音频可视化数据: %s", audio_data_str);

            // 发送到显示消息队列
            bool success = send_display_message("audio", audio_data_str);

            if (success) {
                httpd_resp_sendstr(req, "Audio visualization data sent to display queue");
                ESP_LOGI(TAG, "✅ 音频可视化数据已发送到队列: %s", audio_data_str);
            } else {
                httpd_resp_send_err(req, 500, "Failed to send audio data");
                result = ESP_FAIL;
                goto cleanup;
            }
        }
        result = ESP_OK;
        goto cleanup;
    }

    // 显示控制 - 接收RGB565颜色数据并显示
    if(strncmp(buf,"disp:",5)==0){
        // 🔧 解析颜色参数
        uint16_t color = 0x0000; // 默认黑色
        if (strlen(buf) > 5) {
            char *endptr;
            unsigned long color_val = strtoul(buf + 5, &endptr, 0); // 支持0x前缀
            if (endptr != buf + 5 && color_val <= 0xFFFF) {
                color = (uint16_t)color_val;
            }
        }

        // 🔧 使用PWM控制背光，修复背光不亮问题
        backlight_set_brightness(255); // 最大亮度

        // 🔧 使用官方LCD API填充颜色
        if (panel_handle) {
            uint16_t *color_buffer = malloc(172 * 320 * sizeof(uint16_t));
            if (color_buffer) {
                for (int i = 0; i < 172 * 320; i++) {
                    color_buffer[i] = color;
                }
                esp_lcd_panel_draw_bitmap(panel_handle, 0, 0, 172, 320, color_buffer);
                free(color_buffer);
            }
        }

        // 🔧 不阻塞HTTP，背光由定时器任务处理
        // TODO: 添加背光定时器任务来处理自动关闭

        httpd_resp_sendstr(req, "Display updated");
        result = ESP_OK;
        goto cleanup;
    }

    // 视频帧获取 - 按需获取单帧用于视频流
    if(strcmp(buf,"frame")==0){
        // 摄像头已在系统启动时初始化，直接获取帧
        if(!camera_enabled){
            httpd_resp_send_err(req, 503, "Camera not initialized");
            result = ESP_FAIL;
            goto cleanup;
        }

        camera_fb_t *fb = cam_capture();
        if(!fb){
            ESP_LOGW(TAG, "Frame capture failed");
            httpd_resp_send_err(req, 500, "Frame capture failed");
            result = ESP_FAIL;
            goto cleanup;
        }

        // 验证图像数据
        if (fb->len == 0 || fb->buf == NULL) {
            ESP_LOGE(TAG, "Invalid frame buffer data");
            cam_fb_return_safe(fb);
            httpd_resp_send_err(req, 500, "Invalid frame data");
            result = ESP_FAIL;
            goto cleanup;
        }

        ESP_LOGI(TAG, "Sending frame: %dx%d, %d bytes, format: %d",
                 fb->width, fb->height, fb->len, fb->format);

        httpd_resp_set_type(req, "image/jpeg");
        httpd_resp_send(req, (char*)fb->buf, fb->len);
        cam_fb_return_safe(fb);

        // 🔧 按照官方设计：摄像头保持优化运行，用于连续视频流
        ESP_LOGI(TAG, "Frame captured successfully, camera remains optimized for streaming");
        result = ESP_OK;
        goto cleanup;
    }

    // --- NEW UI HANDLERS ---
    if(strncmp(buf,"text:",5)==0){
        // Expected format: {"text1":"你好","text2":"世界"}
        cJSON *root = cJSON_Parse(buf + 5);
        if (root) {
            ui_data_t data = {0};
            cJSON *item1 = cJSON_GetObjectItem(root, "text1");
            if (cJSON_IsString(item1) && (item1->valuestring != NULL)) {
                data.text1 = item1->valuestring;
            }
            cJSON *item2 = cJSON_GetObjectItem(root, "text2");
             if (cJSON_IsString(item2) && (item2->valuestring != NULL)) {
                data.text2 = item2->valuestring;
            }
            sisi_ui_switch_scene(UI_SCENE_INTERACTIVE, &data);
            cJSON_Delete(root);
            httpd_resp_sendstr(req, "UI switched to INTERACTIVE (text)");
        } else {
            httpd_resp_send_err(req, 400, "Invalid JSON for text update");
        }
        result = ESP_OK;
        goto cleanup;
    }

    // 🧹 删除重复的audiodata处理，使用上面的8频段版本

    if(strncmp(buf,"log:",4)==0){
        ui_data_t data = { .log_text = buf + 4 };
        sisi_ui_switch_scene(UI_SCENE_INTERACTIVE, &data);
        httpd_resp_sendstr(req, "UI switched to INTERACTIVE (log)");
        result = ESP_OK;
        goto cleanup;
    }

    // 🚀 SmartSisi实时文字推送API - 线程安全版本
    if(strncmp(buf,"sisi:",5)==0){
        const char* sisi_text = buf + 5;
        ESP_LOGI(TAG, "📝 SmartSisi文字推送: %s", sisi_text);

        // 🔧 线程安全：发送到消息队列
        bool success = send_display_message("text", sisi_text);

        if (success) {
            httpd_resp_sendstr(req, "SmartSisi text sent to display queue");
            ESP_LOGI(TAG, "✅ SmartSisi文字已发送到队列: %s", sisi_text);
        } else {
            httpd_resp_sendstr(req, "Failed to send SmartSisi text");
            ESP_LOGE(TAG, "❌ SmartSisi文字发送失败: %s", sisi_text);
        }
        result = ESP_OK;
        goto cleanup;
    }

    // 🧹 清理：删除视频服务器URL设置API

    // 待机模式 - DEPRECATED
    if(strcmp(buf,"standby")==0){
        httpd_resp_send_err(req, 404, "Standby mode is disabled for LVGL.");
        result = ESP_FAIL;
        goto cleanup;
    }

    // 系统状态查询
    if(strcmp(buf,"status")==0){
        char status[512];
        snprintf(status, sizeof(status),
            "{\"camera\":%s,\"audio\":\"%s\",\"wifi\":\"%s\",\"free_heap\":%d,\"visualizer\":\"LVGL_ACTIVE\"}",
            camera_enabled ? "true" : "false",
            audio_playing ? "playing" : "idle",
            wifi_initialized ? "connected" : "disconnected",
            (int)esp_get_free_heap_size()
        );
        httpd_resp_set_type(req, "application/json");
        httpd_resp_sendstr(req, status);
        result = ESP_OK;
        goto cleanup;
    }

    httpd_resp_send_err(req, 400, "Unknown command");
    result = ESP_FAIL;

cleanup:
    if (buf) {
        free(buf);
    }
    return result;
}
static void http_start(void){
    // 🔧 按官方资料正确配置HTTP服务器
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.max_uri_handlers = 16;  // 官方推荐设置
    config.server_port = 80;       // 标准HTTP端口
    config.stack_size = 8192;      // 增加栈大小
    config.task_priority = 5;      // 设置任务优先级
    config.max_open_sockets = 7;   // 限制并发连接数
    config.backlog_conn = 5;       // 设置监听队列

    ESP_LOGI(TAG, "🔧 HTTP配置: port=%d, stack=%d, priority=%d, sockets=%d",
             config.server_port, config.stack_size, config.task_priority, config.max_open_sockets);

    httpd_handle_t server = NULL;
    esp_err_t ret = httpd_start(&server, &config);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start HTTP server: %s", esp_err_to_name(ret));
        return;
    }

    // 🔧 统一HTTP API协议 - 与您的摄像头协议保持一致

    // 根路径处理器 - 状态页面
    httpd_uri_t root_uri = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = status_handler,  // 专门的状态处理器
        .user_ctx = NULL
    };

    // 控制页面
    httpd_uri_t control_uri = {
        .uri = "/control",
        .method = HTTP_GET,
        .handler = control_page_handler,  // 控制页面处理器
        .user_ctx = NULL
    };

    // 命令接口 - 主要API
    httpd_uri_t cmd_post_uri = {
        .uri = "/cmd",
        .method = HTTP_POST,
        .handler = cmd_handler,
        .user_ctx = NULL
    };

    // 摄像头API - 与您的协议统一
    httpd_uri_t camera_frame_uri = {
        .uri = "/camera/frame",
        .method = HTTP_GET,
        .handler = camera_frame_handler,
        .user_ctx = NULL
    };

    httpd_uri_t camera_snap_uri = {
        .uri = "/camera/snap",
        .method = HTTP_POST,
        .handler = camera_snap_handler,
        .user_ctx = NULL
    };

    httpd_uri_t camera_stream_uri = {
        .uri = "/camera/stream",
        .method = HTTP_GET,
        .handler = camera_stream_handler,
        .user_ctx = NULL
    };

    // 显示API - 新增
    httpd_uri_t display_text_uri = {
        .uri = "/display/text",
        .method = HTTP_POST,
        .handler = display_text_handler,
        .user_ctx = NULL
    };

    // 🔧 注册图片显示处理器
    httpd_uri_t display_image_uri = {
        .uri = "/display/image",
        .method = HTTP_POST,
        .handler = display_image_handler,
        .user_ctx = NULL
    };

    httpd_uri_t display_mode_uri = {
        .uri = "/display/mode",
        .method = HTTP_POST,
        .handler = display_mode_handler,
        .user_ctx = NULL
    };

    // 🧹 清理：删除视频API

    // 🧹 删除错误的音频接口

    // 注册所有URI处理器
    httpd_uri_t* uris[] = {
        &root_uri,
        &control_uri,
        &cmd_post_uri,
        &camera_frame_uri,
        &camera_snap_uri,
        &camera_stream_uri,
        &display_text_uri,
        &display_image_uri,  // 🔧 添加图片显示处理器
        &display_mode_uri
        // 🧹 删除错误的音频接口
    };

    const char* uri_names[] = {
        "root (/)",
        "control (/control)",
        "command (/cmd)",
        "camera frame (/camera/frame)",
        "camera snap (/camera/snap)",
        "camera stream (/camera/stream)",
        "display text (/display/text)",
        "display image (/display/image)",  // 🔧 添加图片显示处理器名称
        "display mode (/display/mode)"
        // 🧹 删除错误的音频接口名称
    };

    for (int i = 0; i < sizeof(uris) / sizeof(uris[0]); i++) {
        ret = httpd_register_uri_handler(server, uris[i]);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "Failed to register %s handler: %s", uri_names[i], esp_err_to_name(ret));
            return;
        }
        ESP_LOGI(TAG, "✅ 注册 %s 处理器成功", uri_names[i]);
    }

    ESP_LOGI(TAG, "🎉 HTTP server started successfully on port 80");
    ESP_LOGI(TAG, "📡 统一API协议 - 与您的摄像头协议完全一致:");
    ESP_LOGI(TAG, "   GET  /                    - 设备状态 (JSON)");
    ESP_LOGI(TAG, "   GET  /control             - 控制页面 (HTML)");
    ESP_LOGI(TAG, "   POST /cmd                 - 命令接口 (兼容)");
    ESP_LOGI(TAG, "   GET  /camera/frame        - 获取摄像头帧");
    ESP_LOGI(TAG, "   POST /camera/snap         - 拍照");
    ESP_LOGI(TAG, "   GET  /camera/stream       - 摄像头流 (MJPEG)");
    ESP_LOGI(TAG, "   POST /display/text        - 显示文字");
    ESP_LOGI(TAG, "   POST /display/image       - 显示图片（拍照后显示并删除）");
    ESP_LOGI(TAG, "   POST /display/mode        - 切换显示模式");
    // 🧹 清理：删除视频服务器API日志
    ESP_LOGI(TAG, "🔥 统一协议服务器就绪!");

    // 🎵 恢复音频可视化功能 - 旋律动画
    ESP_LOGI(TAG, "🎵 启用旋律动画可视化功能");
    init_visualizer_integration(server);
}

/* ---------------- 旋律动画可视化功能 ---------------- */

// 🎵 动画配置API处理器
static esp_err_t animation_config_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "🎵 动画配置请求");

    char *buf = NULL;
    size_t content_len = req->content_len;

    if (content_len >= 512) {
        httpd_resp_send_err(req, 400, "Content too long");
        return ESP_FAIL;
    }

    if (content_len > 0) {
        buf = malloc(content_len + 1);
        if (!buf) {
            httpd_resp_send_err(req, 500, "Memory allocation failed");
            return ESP_FAIL;
        }

        int ret = httpd_req_recv(req, buf, content_len);
        if (ret <= 0) {
            free(buf);
            httpd_resp_send_err(req, 400, "Failed to receive data");
            return ESP_FAIL;
        }
        buf[content_len] = '\0';

        ESP_LOGI(TAG, "🎵 动画配置数据: %s", buf);
    }

    httpd_resp_sendstr(req, "Animation config received");
    if (buf) free(buf);
    return ESP_OK;
}

// 🎵 音乐同步开始API处理器
static esp_err_t music_sync_start_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "🎵 音乐同步开始请求");

    char *buf = NULL;
    size_t content_len = req->content_len;

    if (content_len > 0 && content_len < 512) {
        buf = malloc(content_len + 1);
        if (buf) {
            int ret = httpd_req_recv(req, buf, content_len);
            if (ret > 0) {
                buf[content_len] = '\0';
                ESP_LOGI(TAG, "🎵 音乐同步数据: %s", buf);
            }
            free(buf);
        }
    }

    httpd_resp_sendstr(req, "Music sync started");
    return ESP_OK;
}

// 🎵 音乐同步停止API处理器
static esp_err_t music_sync_stop_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "🎵 音乐同步停止请求");

    char *buf = NULL;
    size_t content_len = req->content_len;

    if (content_len > 0 && content_len < 512) {
        buf = malloc(content_len + 1);
        if (buf) {
            int ret = httpd_req_recv(req, buf, content_len);
            if (ret > 0) {
                buf[content_len] = '\0';
                ESP_LOGI(TAG, "🎵 音乐停止数据: %s", buf);
            }
            free(buf);
        }
    }

    httpd_resp_sendstr(req, "Music sync stopped");
    return ESP_OK;
}

// 🎵 旋律动画API处理器
static esp_err_t melody_animation_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "🎵 旋律动画请求");

    char *buf = NULL;
    size_t content_len = req->content_len;

    if (content_len >= 512) {
        httpd_resp_send_err(req, 400, "Content too long");
        return ESP_FAIL;
    }

    buf = malloc(content_len + 1);
    if (!buf) {
        httpd_resp_send_err(req, 500, "Memory allocation failed");
        return ESP_FAIL;
    }

    int ret = httpd_req_recv(req, buf, content_len);
    if (ret <= 0) {
        free(buf);
        if (ret == HTTPD_SOCK_ERR_TIMEOUT) {
            httpd_resp_send_408(req);
        }
        return ESP_FAIL;
    }
    buf[content_len] = '\0';

    // 🎵 解析音频数据 (支持JSON和逗号分隔两种格式)
    float audio_bars[4] = {0};
    int bar_count = 0;

    ESP_LOGI(TAG, "🎵 接收到原始数据: %s", buf);

    // 检查是否为JSON格式
    if (buf[0] == '{') {
        // JSON格式解析 (简单解析，提取数字)
        char *ptr = buf;
        while (*ptr && bar_count < 4) {
            if (isdigit((unsigned char)*ptr) || *ptr == '.') {
                audio_bars[bar_count] = atof(ptr);
                bar_count++;
                // 跳过当前数字
                while (*ptr && (isdigit((unsigned char)*ptr) || *ptr == '.')) ptr++;
            } else {
                ptr++;
            }
        }
        ESP_LOGI(TAG, "🎵 JSON格式解析完成，提取到 %d 个数据", bar_count);
    } else {
        // 逗号分隔格式解析
        char* token = strtok(buf, ",");
        while (token != NULL && bar_count < 4) {
            audio_bars[bar_count] = atof(token);
            bar_count++;
            token = strtok(NULL, ",");
        }
        ESP_LOGI(TAG, "🎵 逗号分隔格式解析完成，提取到 %d 个数据", bar_count);
    }

    // 🎵 只使用一个函数处理音频数据，避免冲突
    if (bar_count > 0) {
        // 转换float数据为uint8_t格式给SISI UI
        uint8_t spectrum_data[bar_count];
        for (int i = 0; i < bar_count; i++) {
            // 将float值(0.0-1.0)转换为uint8_t(0-255)
            spectrum_data[i] = (uint8_t)(audio_bars[i] * 255.0f);
        }

        ESP_LOGI(TAG, "🎵 旋律动画数据: [%d, %d, %d, %d]",
                 spectrum_data[0], spectrum_data[1], spectrum_data[2], spectrum_data[3]);

        sisi_ui_update_audio_spectrum(spectrum_data, bar_count);
        ESP_LOGI(TAG, "🎵 音频数据已更新: %d 个频段", bar_count);
    }

    httpd_resp_sendstr(req, "Melody animation data received");
    free(buf);
    return ESP_OK;
}

// 初始化旋律动画可视化集成
static esp_err_t init_visualizer_integration(httpd_handle_t server) {
    ESP_LOGI(TAG, "🎵 初始化旋律动画可视化集成");

    // 注册动画配置API
    httpd_uri_t animation_config_uri = {
        .uri = "/animation/config",
        .method = HTTP_POST,
        .handler = animation_config_handler,
        .user_ctx = NULL
    };

    esp_err_t ret = httpd_register_uri_handler(server, &animation_config_uri);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "✅ 注册动画配置 (/animation/config) 处理器成功");
    } else {
        ESP_LOGE(TAG, "❌ 注册动画配置处理器失败");
        return ret;
    }

    // 注册旋律动画API
    httpd_uri_t melody_uri = {
        .uri = "/melody/animation",
        .method = HTTP_POST,
        .handler = melody_animation_handler,
        .user_ctx = NULL
    };

    ret = httpd_register_uri_handler(server, &melody_uri);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "✅ 注册旋律动画 (/melody/animation) 处理器成功");
    } else {
        ESP_LOGE(TAG, "❌ 注册旋律动画处理器失败");
        return ret;
    }

    // 注册音乐同步开始API
    httpd_uri_t music_sync_start_uri = {
        .uri = "/music/sync_start",
        .method = HTTP_POST,
        .handler = music_sync_start_handler,
        .user_ctx = NULL
    };

    ret = httpd_register_uri_handler(server, &music_sync_start_uri);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "✅ 注册音乐同步开始 (/music/sync_start) 处理器成功");
    } else {
        ESP_LOGE(TAG, "❌ 注册音乐同步开始处理器失败");
        return ret;
    }

    // 注册音乐同步停止API
    httpd_uri_t music_sync_stop_uri = {
        .uri = "/music/sync_stop",
        .method = HTTP_POST,
        .handler = music_sync_stop_handler,
        .user_ctx = NULL
    };

    ret = httpd_register_uri_handler(server, &music_sync_stop_uri);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "✅ 注册音乐同步停止 (/music/sync_stop) 处理器成功");
    } else {
        ESP_LOGE(TAG, "❌ 注册音乐同步停止处理器失败");
        return ret;
    }

    return ESP_OK;
}

// 🗑️ 已删除未使用的 set_audio_data 函数，避免编译警告

// 注释未使用的函数，避免编译警告
// 设置文本显示
// static void set_text_display(const char* text) {
//     if (!text) return;
//     ESP_LOGI(TAG, "🎵 设置文本显示: %s", text);
//     send_display_message("text", text);
// }

// 设置待机模式
// static void set_standby_mode(void) {
//     ESP_LOGI(TAG, "🎵 切换到待机模式");
//     send_display_message("mode", "idle");
// }

/* ---------------- TFT ---------------- */
/* ---------------- TFT Display ---------------- */
// 🔧 旧的SPI函数已删除，使用ESP-IDF官方LCD驱动

// 🔧 旧的tft_set_window函数已删除，使用官方API

// 🔧 旧的填充函数已删除，使用官方API esp_lcd_panel_draw_bitmap()

static void tft_init_full(void){
    ESP_LOGI(TAG, "🔧 使用ESP-IDF官方LCD驱动初始化ST7789");

    // 🔧 配置SPI总线
    ESP_LOGI(TAG, "🔧 配置SPI总线: MOSI=GPIO%d, SCLK=GPIO%d", PIN_TFT_MOSI, PIN_TFT_SCLK);
    spi_bus_config_t buscfg = {
        .sclk_io_num = PIN_TFT_SCLK,
        .mosi_io_num = PIN_TFT_MOSI,
        .miso_io_num = -1,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 16 * TFT_WIDTH * sizeof(uint16_t) + 8,  // 16 lines at a time + command overhead
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI3_HOST, &buscfg, SPI_DMA_CH_AUTO));

    // 🔧 配置LCD Panel IO
    ESP_LOGI(TAG, "🔧 配置LCD Panel IO: CS=GPIO%d, DC=GPIO%d", PIN_TFT_CS, PIN_TFT_DC);
    esp_lcd_panel_io_spi_config_t io_config = {
        .dc_gpio_num = PIN_TFT_DC,
        .cs_gpio_num = PIN_TFT_CS,
        .pclk_hz = 20 * 1000 * 1000,  // 20MHz SPI clock
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
        .spi_mode = 0,  // SPI mode 0
        .trans_queue_depth = 10,  // Reduced queue depth to match reference project
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI3_HOST, &io_config, &io_handle));

    // 🔧 配置LCD Panel
    ESP_LOGI(TAG, "🔧 配置ST7789 Panel");
    esp_lcd_panel_dev_config_t panel_config = {
        .reset_gpio_num = -1,
        .rgb_endian = LCD_RGB_ENDIAN_BGR,
        .bits_per_pixel = 16,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(io_handle, &panel_config, &panel_handle));

    // 🎬 设置全局LCD panel句柄，供AVI播放器使用
    g_lcd_panel = panel_handle;

    // 🔧 使用官方驱动初始化
    ESP_LOGI(TAG, "🔧 重置LCD Panel");
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));

    ESP_LOGI(TAG, "🔧 初始化LCD Panel");
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));

    // 🔧 【最终修正】设置正确的物理偏移量，解决边缘乱码问题
    // 172x320的屏幕在240x320的驱动IC上，X轴有 (240-172)/2 = 34的偏移
    ESP_LOGI(TAG, "🔧 设置显示偏移: X=34, Y=0");
    ESP_ERROR_CHECK(esp_lcd_panel_set_gap(panel_handle, 34, 0));

    ESP_LOGI(TAG, "🔧 设置颜色反转");
    ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel_handle, true));

    // ESP_LOGI(TAG, "设置屏幕为竖屏模式 (重调)");
    // esp_lcd_panel_swap_xy(panel_handle, false);   // 【禁用】冲突的根源！
    // esp_lcd_panel_mirror(panel_handle, false, false); // 【禁用】

    // 🔧 开启显示
    ESP_LOGI(TAG, "🔧 开启显示");
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_handle, true));

    // 🔧 测试背光PWM
    ESP_LOGI(TAG, "🔍 测试背光PWM GPIO%d", PIN_TFT_BL);
    backlight_set_brightness(255);
    ESP_LOGI(TAG, "🔍 背光设置为最大亮度");

    // 🚀 初始化LVGL - 这是关键！
    ESP_LOGI(TAG, "🚀 初始化LVGL...");

    // 初始化esp_lvgl_port
    const lvgl_port_cfg_t lvgl_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    esp_err_t err = lvgl_port_init(&lvgl_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LVGL port init failed: %s", esp_err_to_name(err));
        return;
    }

    // 添加LCD显示设备到LVGL
    const lvgl_port_display_cfg_t disp_cfg = {
        .io_handle = io_handle,
        .panel_handle = panel_handle,
        .buffer_size = TFT_WIDTH * 16,   // Match PARALLEL_LINES strategy: 16 lines buffer
        .double_buffer = true,   // N16R8: Enable double buffer for smooth rendering
        .hres = TFT_WIDTH,
        .vres = TFT_HEIGHT,
        .monochrome = false,
        .rotation = {
            .swap_xy = false,
            .mirror_x = false,
            .mirror_y = false,
        },
        .flags = {
            .buff_dma = true,
            .buff_spiram = true,  // 🔧 新增：使用PSRAM作为缓冲区
#if LVGL_VERSION_MAJOR >= 9
            .swap_bytes = true,   // 🔧 照抄ESP官方：字节交换
#endif
        }
    };

    lv_disp_t *disp = lvgl_port_add_disp(&disp_cfg);
    if (disp == NULL) {
        ESP_LOGE(TAG, "Failed to add display to LVGL");
        return;
    }

    ESP_LOGI(TAG, "✅ LVGL初始化完成");
}





/* ---------------- Main Application ---------------- */
void app_main(void){
    ESP_LOGI(TAG, "=== SISIeyes System Starting ===");

    // 🔧 初始化显示消息队列
    display_queue = xQueueCreate(10, sizeof(display_message_t));
    if (display_queue == NULL) {
        ESP_LOGE(TAG, "❌ 显示消息队列创建失败");
        return;
    }
    ESP_LOGI(TAG, "✅ 显示消息队列创建成功");

    // 初始化NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // 按顺序初始化各个模块
    ESP_LOGI(TAG, "Initializing WiFi...");
    wifi_init();

    // 🔧 初始化SPIFFS文件系统（用于GIF背景视频）
    ESP_LOGI(TAG, "Initializing SPIFFS...");
    ret = init_spiffs();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "❌ SPIFFS初始化失败，GIF背景将不可用");
    }

    ESP_LOGI(TAG, "🔧 异步启动模式：默认只开启显示屏，其他设备按需启动");

    // 🔧 **关键修复：调用完整的io_init()函数，包含LEDC配置**
    ESP_LOGI(TAG, "Initializing GPIO and LEDC...");
    io_init();  // 这里包含了LEDC背光配置！

    // 🔧 音频可视化系统：只接收数据显示，不播放声音
    ESP_LOGI(TAG, "✅ Audio playback system ready (event-driven).");

    // 🔧 等待WiFi连接成功后再启动HTTP服务器
    ESP_LOGI(TAG, "⏳ Waiting for WiFi connection before starting HTTP server...");
    while (!wifi_initialized) {
        vTaskDelay(100 / portTICK_PERIOD_MS);
    }
    ESP_LOGI(TAG, "✅ WiFi connected, now initializing display first...");

    // 🔍 启动前内存检查 - 在显示初始化之前检查
    size_t psram_total = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    size_t psram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    size_t internal_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);

    ESP_LOGI(TAG, "=== 启动前内存状态 ===");
    ESP_LOGI(TAG, "PSRAM总计: %d bytes (%.1f MB)", psram_total, psram_total/1024.0/1024.0);
    ESP_LOGI(TAG, "PSRAM可用: %d bytes (%.1f MB)", psram_free, psram_free/1024.0/1024.0);
    ESP_LOGI(TAG, "内部RAM可用: %d bytes (%.1f KB)", internal_free, internal_free/1024.0);

    ESP_LOGI(TAG, "Initializing TFT Display...");
    tft_init_full();

    ESP_LOGI(TAG, "Starting SISI UI Engine...");
    sisi_ui_init(panel_handle);

    // 🧹 清理：删除视频管理器初始化

    // 🔧 启动显示消息处理任务 - 使用较低优先级，避免冲突
    BaseType_t task_result = xTaskCreatePinnedToCore(
        display_message_task,
        "display_msg",
        8192,  // 增加栈大小
        NULL,
        3,     // 降低优先级，避免与LVGL冲突
        NULL,
        1      // 在核心1运行，与LVGL任务同核心
    );

    if (task_result == pdPASS) {
        ESP_LOGI(TAG, "✅ 显示消息处理任务已启动");
    } else {
        ESP_LOGE(TAG, "❌ 显示消息处理任务启动失败");
        return;  // 如果显示任务启动失败，不要继续
    }

    // 🔧 现在启动HTTP服务器，确保显示任务已经准备好
    ESP_LOGI(TAG, "🚀 显示系统就绪，现在启动HTTP服务器...");
    http_start();
    ESP_LOGI(TAG, "✅ HTTP Server started");

    // 🔧 不初始化摄像头，HTTP请求时再启动
    ESP_LOGI(TAG, "✅ Camera DISABLED by default (async on-demand)");

    ESP_LOGI(TAG, "Starting Camera Status Monitor...");
    xTaskCreatePinnedToCore(
        camera_monitor_task,
        "cam_status",
        8192,  // 🔧 增加栈大小，防止栈溢出
        NULL,
        3,
        NULL,
        0  // 运行在核心0
    );

    ESP_LOGI(TAG, "=== SISIeyes System Ready ===");
    ESP_LOGI(TAG, "Available APIs:");
    ESP_LOGI(TAG, "  POST /cmd with body:");
    ESP_LOGI(TAG, "    snap - Take photo (high quality)");
    ESP_LOGI(TAG, "    🎬 photo_effect - 拍照特效 (电机+绕组+LED)");
    ESP_LOGI(TAG, "    motor:[-100 to 100] - Control motor");
    ESP_LOGI(TAG, "    led:#RRGGBB - Set LED color");
    ESP_LOGI(TAG, "    audio:tone:440 - Play a tone");
    ESP_LOGI(TAG, "    🚀 sisi:你好世界 - SISI实时文字推送");
    ESP_LOGI(TAG, "    status - Get system status");
    ESP_LOGI(TAG, "  POST /camera/snap - 拍照 + 自动特效");
    ESP_LOGI(TAG, "🎬 特效序列: 电机正转3s → 反转3s → 白闪2次 → 彩虹渐变 → 粉红渐变30s");

    // 🔧 不播放启动音效，避免初始化冲突
    ESP_LOGI(TAG, "🔇 Startup sounds disabled to prevent conflicts");

    // 🔥 启用CPU降频模式，减少发热（不动WiFi）
    ESP_LOGI(TAG, "🔥 启用CPU降频模式，减少发热...");

    // 🔧 正常功耗模式，保证摄像头正常工作
    esp_pm_config_t pm_config = {
        .max_freq_mhz = 160,     // 🔧 恢复正常160MHz
        .min_freq_mhz = 80,      // 🔧 最小80MHz
        .light_sleep_enable = false  // 🔧 不启用睡眠，保持WiFi稳定
    };
    esp_pm_configure(&pm_config);

    ESP_LOGI(TAG, "🔧 正常功耗模式：最大160MHz，最小80MHz");

    // 🚨 紧急修复：禁用复杂功能，防止内存冲突
    ESP_LOGI(TAG, "🚨 紧急模式：禁用视频播放器，减少内存使用");

    // 🔧 按官方思路简化：减少并行任务，避免中断冲突
    ESP_LOGI(TAG, "Starting simplified architecture (following official camera examples)...");

    // 🔧 暂时禁用复杂的并行任务，按官方示例只保留HTTP服务
    // 所有功能通过HTTP API直接处理，避免多任务中断冲突
    ESP_LOGI(TAG, "All functions handled via HTTP API to prevent task conflicts");

    // 🧹 清理：删除背景视频启动

    // 🎥 空闲视频系统已在SISI UI初始化时自动启动
    // 🚨 紧急修复：禁用空闲视频系统，减少内存使用
    ESP_LOGI(TAG, "🚨 空闲视频系统已禁用，减少PSRAM使用");

    // 主循环：系统监控 - 降低频率减少发热
    while(1) {
        vTaskDelay(30000 / portTICK_PERIOD_MS);  // 从5秒改为30秒，减少6倍唤醒
        ESP_LOGD(TAG, "System running - Free heap: %lu bytes", (unsigned long)esp_get_free_heap_size());
    }
}

static void wifi_event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data){
    if(event_base==WIFI_EVENT && event_id==WIFI_EVENT_STA_START){
        esp_wifi_connect();
        ESP_LOGI(TAG, "WiFi started, connecting...");
    }else if(event_base==WIFI_EVENT && event_id==WIFI_EVENT_STA_DISCONNECTED){
        wifi_event_sta_disconnected_t* disconnected = (wifi_event_sta_disconnected_t*)event_data;
        ESP_LOGW(TAG, "WiFi disconnected, reason: %d", disconnected->reason);

        if(s_retry_num < WIFI_MAX_RETRY){
            esp_wifi_connect();
            s_retry_num++;
            ESP_LOGI(TAG, "Retry connecting to AP (%d/%d)", s_retry_num, WIFI_MAX_RETRY);
        }else{
            ESP_LOGE(TAG, "WiFi connection failed after %d retries", WIFI_MAX_RETRY);
            if (wifi_event_group) {
                xEventGroupSetBits(wifi_event_group, WIFI_FAIL_BIT);
            }
            // 重置重试计数器，继续尝试（持续重连）
            vTaskDelay(5000 / portTICK_PERIOD_MS);  // 等待5秒后重新开始
            s_retry_num = 0;
            esp_wifi_connect();
            ESP_LOGI(TAG, "Restarting WiFi connection attempts");
        }
    }else if(event_base==IP_EVENT && event_id==IP_EVENT_STA_GOT_IP){
        ip_event_got_ip_t* event = (ip_event_got_ip_t*)event_data;
        ESP_LOGI(TAG, "WiFi connected! IP: " IPSTR, IP2STR(&event->ip_info.ip));
        s_retry_num = 0;
        if (wifi_event_group) {
            xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
        }

        // 🚀 WiFi连接成功后，自动启动视频播放系统
        ESP_LOGI(TAG, "🎬 WiFi连接成功，准备启动自动视频播放...");

        // 延迟5秒后启动，确保系统完全初始化
        // xTaskCreate(auto_start_video_task, "auto_video", 4096, NULL, 5, NULL);  // 暂时禁用自动启动
    }
}

// 🎬 自动启动视频播放任务 - 智能检测版 (暂时禁用，避免编译错误)
/*
static void auto_start_video_task(void* arg) {
    ESP_LOGI(TAG, "🎬 开始自动启动视频播放系统...");

    // 等待5秒，确保系统完全初始化
    vTaskDelay(5000 / portTICK_PERIOD_MS);

    // 🔧 修复：使用线程安全的消息队列发送启动消息
    send_display_message("text", "🚀 系统启动中...");
    vTaskDelay(2000 / portTICK_PERIOD_MS);

    send_display_message("text", "📡 正在搜索视频服务器...");
    vTaskDelay(2000 / portTICK_PERIOD_MS);

    // 🔍 智能检测视频服务器 - 尝试多个可能的IP地址
    const char* possible_servers[] = {
        "http://192.168.1.100:8080",  // 常见局域网IP
        "http://192.168.0.100:8080",  // 另一个常见网段
        "http://172.20.10.1:8080",    // 热点网段
        "http://10.0.0.100:8080",     // 企业网段
        NULL
    };

    bool server_found = false;

    for (int i = 0; possible_servers[i] != NULL; i++) {
        ESP_LOGI(TAG, "🔗 尝试连接视频服务器: %s", possible_servers[i]);

        // 简单的HTTP GET测试连接
        esp_http_client_config_t config = {
            .url = possible_servers[i],
            .method = HTTP_METHOD_GET,
            .timeout_ms = 3000,
        };

        esp_http_client_handle_t client = esp_http_client_init(&config);
        if (client) {
            esp_err_t err = esp_http_client_perform(client);
            if (err == ESP_OK) {
                int status_code = esp_http_client_get_status_code(client);
                if (status_code == 200 || status_code == 404) {  // 404也表示服务器存在
                    ESP_LOGI(TAG, "✅ 找到视频服务器: %s", possible_servers[i]);

                    // 🧹 清理：删除视频服务器设置
                    server_found = true;

                    esp_http_client_cleanup(client);
                    break;
                }
            }
            esp_http_client_cleanup(client);
        }

        vTaskDelay(1000 / portTICK_PERIOD_MS);  // 等待1秒再试下一个
    }

    if (server_found) {
        send_display_message("text", "🎬 视频播放已启动");
        ESP_LOGI(TAG, "✅ 自动视频播放启动完成");
    } else {
        send_display_message("text", "⚠️ 未找到视频服务器");
        ESP_LOGI(TAG, "⚠️ 未找到可用的视频服务器，等待手动设置");

        // 显示待机画面或默认内容
        send_display_message("text", "📺 等待SmartSisi连接...");
    }

    vTaskDelay(3000 / portTICK_PERIOD_MS);

    // 任务完成，删除自己
    vTaskDelete(NULL);
}
*/

// 🚀 核心0专用：命令处理和电机控制任务 - 条件唤醒版 (暂时未使用)
/*
static void command_task(void *pvParameters) {
    ESP_LOGI(TAG, "Command task started on core 0 - event-driven mode");

    while(1) {
        // 🔧 大幅降低唤醒频率，减少CPU负载和发热
        // 从100ms改为5秒，减少50倍CPU唤醒
        vTaskDelay(5000 / portTICK_PERIOD_MS);  // 5秒周期，仅做系统监控

        // 只做必要的系统健康检查
        // 实际的电机/LED/音频控制由HTTP请求直接处理，不需要后台轮询
        ESP_LOGD(TAG, "Command task heartbeat - system healthy");
    }
}
*/



// 🚀 核心1专用：显示屏渲染任务 - 条件唤醒版 (暂时未使用)
/*
static void display_task(void *pvParameters) {
    ESP_LOGI(TAG, "Display task started on core 1 - event-driven mode");

    while(1) {
        // 🔧 大幅降低唤醒频率，减少CPU负载和发热
        // 从50ms改为10秒，减少200倍CPU唤醒
        vTaskDelay(10000 / portTICK_PERIOD_MS);  // 10秒周期，仅做状态检查

        // 显示屏实际控制由HTTP请求直接处理（disp命令）
        // 这里只做必要的状态维护，不需要高频轮询
        ESP_LOGD(TAG, "Display task heartbeat - screen ready");

        // TODO: 未来可改为队列接收模式
        // if (xQueueReceive(video_queue, &frame_data, portMAX_DELAY)) {
        //     display_frame(frame_data);  // 只有收到数据才处理
        // }
    }
}
*/
