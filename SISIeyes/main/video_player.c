/**
 * SISIeyes 视频播放器实现
 * 使用你现有的API：esp_jpeg_decode() + LVGL Canvas
 * 借鉴ESP-BOX架构思路
 */

#include "video_player.h"
#include "jpeg_decoder.h"  // 使用你现有的JPEG解码器
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_task_wdt.h"
#include "esp_lvgl_port.h"  // ESP-BOX标准LVGL锁
#include "esp_http_client.h"  // HTTP客户端
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include <stdio.h>
#include <string.h>

static const char *TAG = "VIDEO_PLAYER";

// 事件位定义
#define FRAME_READY_BIT     BIT0
#define STOP_PLAY_BIT       BIT1
#define PAUSE_PLAY_BIT      BIT2

// 视频播放器状态
typedef struct {
    lv_obj_t *canvas;               // LVGL Canvas对象
    lv_draw_buf_t draw_buf;         // LVGL 9.2标准draw_buf结构
    uint8_t *video_buffer;          // RGB565缓冲区
    uint8_t *mjpeg_buffer;          // MJPEG数据缓冲区
    uint8_t *http_buffer;           // HTTP接收缓冲区

    video_state_t state;            // 播放状态
    bool is_initialized;            // 是否已初始化
    bool is_visible;               // 是否可见

    video_event_cb_t event_cb;     // 事件回调
    void *user_data;               // 用户数据

    TaskHandle_t file_task;        // 文件播放任务
    TaskHandle_t stream_task;      // 流接收任务
    TaskHandle_t decode_task;      // 解码任务
    EventGroupHandle_t events;     // 事件组

    FILE *video_file;              // 视频文件句柄
    esp_http_client_handle_t http_client; // HTTP客户端句柄
} video_player_ctx_t;

static video_player_ctx_t g_video_ctx = {0};

/**
 * 解码JPEG帧并显示到Canvas
 */
static esp_err_t decode_and_display_frame(const uint8_t *jpeg_data, size_t data_size)
{
    if (!jpeg_data || data_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGD(TAG, "解码JPEG帧: %zu bytes", data_size);

    // 配置JPEG解码 - 使用你现有的API
    esp_jpeg_image_cfg_t jpeg_cfg = {
        .indata = (uint8_t*)jpeg_data,
        .indata_size = data_size,
        .outbuf = g_video_ctx.video_buffer,
        .outbuf_size = VIDEO_BUFFER_SIZE,
        .out_format = JPEG_IMAGE_FORMAT_RGB565,
        .out_scale = JPEG_IMAGE_SCALE_0,
        .flags = {
            .swap_color_bytes = 0  // 根据显示屏配置调整
        }
    };

    // 解码JPEG前重置看门狗
    esp_task_wdt_reset();

    esp_jpeg_image_output_t output;
    esp_err_t ret = esp_jpeg_decode(&jpeg_cfg, &output);

    // 解码完成后再次重置看门狗
    esp_task_wdt_reset();

    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "JPEG解码失败: %s", esp_err_to_name(ret));
        return ret;
    }

    // 🔇 减少日志噪音：只在尺寸不匹配或每100帧时记录
    static int frame_count = 0;
    frame_count++;

    if (output.width != VIDEO_CANVAS_WIDTH || output.height != VIDEO_CANVAS_HEIGHT) {
        ESP_LOGW(TAG, "⚠️ MJPEG解码尺寸不匹配: %dx%d, Canvas期望: %dx%d",
                 output.width, output.height, VIDEO_CANVAS_WIDTH, VIDEO_CANVAS_HEIGHT);
    } else if (frame_count % 100 == 0) {
        ESP_LOGD(TAG, "🔍 [DEBUG] 视频正常播放，帧数: %d", frame_count);
    }

    // 🔧 检查停止信号，避免在停止过程中继续处理
    EventBits_t bits = xEventGroupGetBits(g_video_ctx.events);
    if (bits & STOP_PLAY_BIT) {
        ESP_LOGD(TAG, "🛑 检测到停止信号，跳过帧处理");
        return ESP_OK;
    }

    // 检查尺寸匹配并更新Canvas缓冲区
    if (g_video_ctx.canvas && g_video_ctx.is_visible) {
        // 只有尺寸完全匹配才更新Canvas
        if (output.width == VIDEO_CANVAS_WIDTH && output.height == VIDEO_CANVAS_HEIGHT) {
            // 🔇 删除频繁的成功日志，减少噪音

            // 🔧 使用合理的LVGL锁超时时间（100ms）
            if (lvgl_port_lock(100)) {
                if (g_video_ctx.canvas != NULL && g_video_ctx.video_buffer != NULL) {  // 🔧 检查缓冲区
                    lv_canvas_set_buffer(g_video_ctx.canvas, g_video_ctx.video_buffer,
                                        output.width, output.height,
                                        LV_COLOR_FORMAT_RGB565);
                    lv_obj_invalidate(g_video_ctx.canvas);
                } else {
                    ESP_LOGW(TAG, "⚠️ Canvas或缓冲区为空，跳过此帧");
                }
                lvgl_port_unlock();
            } else {
                ESP_LOGW(TAG, "⚠️ LVGL锁超时，跳过此帧");
            }
        } else {
            ESP_LOGE(TAG, "❌ MJPEG尺寸不匹配，跳过此帧: 解码=%dx%d, Canvas=%dx%d",
                     output.width, output.height, VIDEO_CANVAS_WIDTH, VIDEO_CANVAS_HEIGHT);
            return ESP_FAIL;  // 直接返回失败，不更新Canvas
        }
    }

    // 触发事件回调
    if (g_video_ctx.event_cb) {
        g_video_ctx.event_cb(VIDEO_EVENT_FRAME_DECODED, g_video_ctx.user_data);
    }

    return ESP_OK;
}

/**
 * 初始化视频播放器
 */
esp_err_t video_player_init(lv_obj_t *parent, video_event_cb_t event_cb, void* user_data)
{
    if (g_video_ctx.is_initialized) {
        ESP_LOGW(TAG, "视频播放器已初始化");
        return ESP_OK;
    }

    if (!parent) {
        ESP_LOGE(TAG, "父对象为空");
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "开始初始化视频播放器...");

    // 只清零必要的字段，不要清零整个结构体！
    g_video_ctx.canvas = NULL;
    g_video_ctx.is_initialized = false;
    g_video_ctx.state = VIDEO_STATE_IDLE;
    g_video_ctx.file_task = NULL;
    g_video_ctx.event_cb = NULL;
    g_video_ctx.user_data = NULL;
    // 保持缓冲区指针不变！

    // 分配视频缓冲区 (使用PSRAM，ESP32-S3支持PSRAM DMA)
    g_video_ctx.video_buffer = heap_caps_malloc(VIDEO_BUFFER_SIZE, MALLOC_CAP_SPIRAM);
    if (!g_video_ctx.video_buffer) {
        ESP_LOGE(TAG, "无法分配视频缓冲区: %d bytes", VIDEO_BUFFER_SIZE);
        return ESP_ERR_NO_MEM;
    }

    // 分配MJPEG缓冲区
    g_video_ctx.mjpeg_buffer = malloc(MJPEG_BUFFER_SIZE);
    if (!g_video_ctx.mjpeg_buffer) {
        ESP_LOGE(TAG, "无法分配MJPEG缓冲区: %d bytes", MJPEG_BUFFER_SIZE);
        free(g_video_ctx.video_buffer);
        return ESP_ERR_NO_MEM;
    }

    // 分配HTTP缓冲区
    g_video_ctx.http_buffer = malloc(HTTP_BUFFER_SIZE);
    if (!g_video_ctx.http_buffer) {
        ESP_LOGE(TAG, "无法分配HTTP缓冲区: %d bytes", HTTP_BUFFER_SIZE);
        free(g_video_ctx.video_buffer);
        free(g_video_ctx.mjpeg_buffer);
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "缓冲区分配成功: 视频=%d, MJPEG=%d, HTTP=%d bytes",
             VIDEO_BUFFER_SIZE, MJPEG_BUFFER_SIZE, HTTP_BUFFER_SIZE);

    // 创建事件组
    g_video_ctx.events = xEventGroupCreate();
    if (!g_video_ctx.events) {
        ESP_LOGE(TAG, "无法创建事件组");
        free(g_video_ctx.video_buffer);
        free(g_video_ctx.mjpeg_buffer);
        free(g_video_ctx.http_buffer);
        return ESP_FAIL;
    }

    // 检查父对象有效性
    if (!parent) {
        ESP_LOGE(TAG, "❌ 父对象为空，无法创建Canvas");
        free(g_video_ctx.http_buffer);
        free(g_video_ctx.mjpeg_buffer);
        heap_caps_free(g_video_ctx.video_buffer);
        vEventGroupDelete(g_video_ctx.events);
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "🎬 创建LVGL Canvas，父对象: %p", parent);

    // 创建LVGL Canvas
    g_video_ctx.canvas = lv_canvas_create(parent);
    if (!g_video_ctx.canvas) {
        ESP_LOGE(TAG, "❌ 无法创建LVGL Canvas");
        free(g_video_ctx.video_buffer);
        free(g_video_ctx.mjpeg_buffer);
        free(g_video_ctx.http_buffer);
        vEventGroupDelete(g_video_ctx.events);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "LVGL Canvas创建成功");

    // 使用LVGL 9.2标准的draw_buf方式初始化Canvas
    if (g_video_ctx.video_buffer != NULL) {
        ESP_LOGI(TAG, "初始化Canvas draw_buf: %p, 尺寸: %dx%d",
                 g_video_ctx.video_buffer, VIDEO_CANVAS_WIDTH, VIDEO_CANVAS_HEIGHT);

        // 初始化draw_buf结构
        lv_draw_buf_init(&g_video_ctx.draw_buf,
                        VIDEO_CANVAS_WIDTH, VIDEO_CANVAS_HEIGHT,
                        LV_COLOR_FORMAT_RGB565,
                        lv_draw_buf_width_to_stride(VIDEO_CANVAS_WIDTH, LV_COLOR_FORMAT_RGB565),
                        g_video_ctx.video_buffer,
                        VIDEO_BUFFER_SIZE);

        // 设置Canvas使用draw_buf
        lv_canvas_set_draw_buf(g_video_ctx.canvas, &g_video_ctx.draw_buf);
    } else {
        ESP_LOGE(TAG, "❌ 视频缓冲区为空，无法设置Canvas");
        return ESP_FAIL;
    }

    // 设置Canvas位置和样式
    lv_obj_center(g_video_ctx.canvas);
    lv_canvas_fill_bg(g_video_ctx.canvas, lv_color_black(), LV_OPA_COVER);

    // 初始状态为隐藏
    lv_obj_add_flag(g_video_ctx.canvas, LV_OBJ_FLAG_HIDDEN);
    g_video_ctx.is_visible = false;

    // 设置回调和状态
    g_video_ctx.event_cb = event_cb;
    g_video_ctx.user_data = user_data;
    g_video_ctx.state = VIDEO_STATE_IDLE;
    g_video_ctx.is_initialized = true;

    ESP_LOGI(TAG, "✅ 视频播放器初始化成功 (Canvas: %dx%d)",
             VIDEO_CANVAS_WIDTH, VIDEO_CANVAS_HEIGHT);

    return ESP_OK;
}

/**
 * MJPEG文件播放任务
 */
static void mjpeg_file_task(void *pvParameters)
{
    const char *file_path = (const char*)pvParameters;
    ESP_LOGI(TAG, "🎬 开始播放MJPEG文件: %s", file_path);

    // 注册当前任务到看门狗
    esp_task_wdt_add(NULL);

    FILE *fp = fopen(file_path, "rb");
    if (!fp) {
        ESP_LOGE(TAG, "❌ 无法打开文件: %s", file_path);
        g_video_ctx.state = VIDEO_STATE_ERROR;
        if (g_video_ctx.event_cb) {
            g_video_ctx.event_cb(VIDEO_EVENT_ERROR, g_video_ctx.user_data);
        }
        esp_task_wdt_delete(NULL);  // 删除看门狗注册
        vTaskDelete(NULL);
        return;
    }

    g_video_ctx.video_file = fp;
    g_video_ctx.state = VIDEO_STATE_PLAYING_FILE;

    if (g_video_ctx.event_cb) {
        g_video_ctx.event_cb(VIDEO_EVENT_STARTED, g_video_ctx.user_data);
    }

    while (g_video_ctx.state == VIDEO_STATE_PLAYING_FILE) {
        // 检查停止信号
        EventBits_t bits = xEventGroupWaitBits(g_video_ctx.events,
                                              STOP_PLAY_BIT | PAUSE_PLAY_BIT,
                                              pdFALSE, pdFALSE, 0);
        if (bits & STOP_PLAY_BIT) {
            break;
        }
        if (bits & PAUSE_PLAY_BIT) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        // 读取MJPEG帧数据
        size_t bytes_read = fread(g_video_ctx.mjpeg_buffer, 1, MJPEG_BUFFER_SIZE, fp);
        if (bytes_read == 0) {
            // 文件结束，循环播放
            fseek(fp, 0, SEEK_SET);
            continue;
        }

        // 查找JPEG帧边界 (SOI: 0xFF 0xD8, EOI: 0xFF 0xD9)
        for (size_t i = 0; i < bytes_read - 1; i++) {
            if (g_video_ctx.mjpeg_buffer[i] == 0xFF && g_video_ctx.mjpeg_buffer[i+1] == 0xD8) {
                // 找到JPEG SOI，查找EOI
                size_t frame_start = i;
                size_t frame_end = 0;

                for (size_t j = frame_start + 2; j < bytes_read - 1; j++) {
                    if (g_video_ctx.mjpeg_buffer[j] == 0xFF && g_video_ctx.mjpeg_buffer[j+1] == 0xD9) {
                        frame_end = j + 2;
                        break;
                    }
                }

                if (frame_end > frame_start) {
                    // 解码并显示完整帧
                    size_t frame_size = frame_end - frame_start;
                    decode_and_display_frame(g_video_ctx.mjpeg_buffer + frame_start, frame_size);
                    i = frame_end;  // 跳过已处理的帧
                }
            }
        }

        // 控制帧率 (~15fps)
        vTaskDelay(pdMS_TO_TICKS(66));
    }

    // 🔧 修复：安全关闭文件，避免双重关闭
    if (fp && g_video_ctx.video_file == fp) {
        ESP_LOGI(TAG, "🔧 任务线程关闭视频文件");
        fclose(fp);
        g_video_ctx.video_file = NULL;
    } else if (fp) {
        ESP_LOGW(TAG, "⚠️ 文件指针不匹配，可能已被主线程关闭");
    }
    g_video_ctx.file_task = NULL;

    if (g_video_ctx.event_cb) {
        g_video_ctx.event_cb(VIDEO_EVENT_STOPPED, g_video_ctx.user_data);
    }

    ESP_LOGI(TAG, "🎬 MJPEG文件播放任务结束");
    esp_task_wdt_delete(NULL);  // 删除看门狗注册
    vTaskDelete(NULL);
}

/**
 * HTTP事件处理回调
 */
static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    static size_t buffer_pos = 0;
    static bool frame_started = false;

    switch (evt->event_id) {
        case HTTP_EVENT_ON_CONNECTED:
            ESP_LOGI(TAG, "🌐 HTTP连接成功");
            if (g_video_ctx.event_cb) {
                g_video_ctx.event_cb(VIDEO_EVENT_NETWORK_CONNECTED, g_video_ctx.user_data);
            }
            break;

        case HTTP_EVENT_ON_DATA:
            if (g_video_ctx.state != VIDEO_STATE_RECEIVING_STREAM) {
                return ESP_OK;
            }

            // 处理接收到的数据，查找MJPEG帧边界
            for (int i = 0; i < evt->data_len - 1; i++) {
                uint8_t *data = (uint8_t*)evt->data;

                // 查找JPEG SOI标记 (0xFF 0xD8)
                if (data[i] == 0xFF && data[i+1] == 0xD8) {
                    if (frame_started && buffer_pos > 0) {
                        // 完成前一帧，解码显示
                        decode_and_display_frame(g_video_ctx.mjpeg_buffer, buffer_pos);
                    }

                    // 开始新帧
                    buffer_pos = 0;
                    frame_started = true;
                }

                // 复制数据到缓冲区
                if (frame_started && buffer_pos < MJPEG_BUFFER_SIZE - 1) {
                    g_video_ctx.mjpeg_buffer[buffer_pos++] = data[i];
                }

                // 查找JPEG EOI标记 (0xFF 0xD9)
                if (frame_started && data[i] == 0xFF && data[i+1] == 0xD9) {
                    g_video_ctx.mjpeg_buffer[buffer_pos++] = data[i+1];
                    // 完成当前帧
                    decode_and_display_frame(g_video_ctx.mjpeg_buffer, buffer_pos);
                    buffer_pos = 0;
                    frame_started = false;
                    i++; // 跳过EOI的第二个字节
                }
            }
            break;

        case HTTP_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "🌐 HTTP连接断开");
            if (g_video_ctx.event_cb) {
                g_video_ctx.event_cb(VIDEO_EVENT_NETWORK_DISCONNECTED, g_video_ctx.user_data);
            }
            break;

        case HTTP_EVENT_ON_FINISH:
            buffer_pos = 0;
            frame_started = false;
            break;

        default:
            break;
    }

    return ESP_OK;
}

/**
 * HTTP流接收任务
 */
static void http_stream_task(void *pvParameters)
{
    const char *stream_url = (const char*)pvParameters;
    ESP_LOGI(TAG, "🌐 开始接收HTTP流: %s", stream_url);

    // 配置HTTP客户端
    esp_http_client_config_t config = {
        .url = stream_url,
        .event_handler = http_event_handler,
        .buffer_size = HTTP_BUFFER_SIZE,
        .timeout_ms = 10000,
        .keep_alive_enable = true,
    };

    g_video_ctx.http_client = esp_http_client_init(&config);
    if (!g_video_ctx.http_client) {
        ESP_LOGE(TAG, "❌ HTTP客户端初始化失败");
        g_video_ctx.state = VIDEO_STATE_ERROR;
        if (g_video_ctx.event_cb) {
            g_video_ctx.event_cb(VIDEO_EVENT_ERROR, g_video_ctx.user_data);
        }
        vTaskDelete(NULL);
        return;
    }

    g_video_ctx.state = VIDEO_STATE_RECEIVING_STREAM;

    if (g_video_ctx.event_cb) {
        g_video_ctx.event_cb(VIDEO_EVENT_STARTED, g_video_ctx.user_data);
    }

    // 开始HTTP请求
    esp_err_t err = esp_http_client_perform(g_video_ctx.http_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "❌ HTTP请求失败: %s", esp_err_to_name(err));
        g_video_ctx.state = VIDEO_STATE_ERROR;
        if (g_video_ctx.event_cb) {
            g_video_ctx.event_cb(VIDEO_EVENT_ERROR, g_video_ctx.user_data);
        }
    }

    // 清理HTTP客户端
    esp_http_client_cleanup(g_video_ctx.http_client);
    g_video_ctx.http_client = NULL;
    g_video_ctx.stream_task = NULL;

    if (g_video_ctx.event_cb) {
        g_video_ctx.event_cb(VIDEO_EVENT_STOPPED, g_video_ctx.user_data);
    }

    ESP_LOGI(TAG, "🌐 HTTP流接收任务结束");
    vTaskDelete(NULL);
}

/**
 * 更新单个JPEG帧
 */
/**
 * 播放本地MJPEG文件
 */
esp_err_t video_player_play_file(const char *file_path)
{
    if (!g_video_ctx.is_initialized) {
        ESP_LOGE(TAG, "视频播放器未初始化");
        return ESP_ERR_INVALID_STATE;
    }

    if (!file_path) {
        ESP_LOGE(TAG, "文件路径为空");
        return ESP_ERR_INVALID_ARG;
    }

    if (g_video_ctx.state != VIDEO_STATE_IDLE) {
        ESP_LOGW(TAG, "停止当前播放...");
        video_player_stop();
        vTaskDelay(pdMS_TO_TICKS(100)); // 等待停止完成
    }

    ESP_LOGI(TAG, "🎬 开始播放文件: %s", file_path);

    // 🔧 简单修复：直接显示Canvas，不检查返回值
    video_player_set_visible(true);

    // 清除停止信号
    xEventGroupClearBits(g_video_ctx.events, STOP_PLAY_BIT | PAUSE_PLAY_BIT);

    // 创建文件播放任务，绑定到CPU0（与LVGL同核心，避免跨核问题）
    xTaskCreatePinnedToCore(mjpeg_file_task, "mjpeg_file", 8192, (void*)file_path, 5, &g_video_ctx.file_task, 0);

    return ESP_OK;
}

/**
 * 开始接收网络MJPEG流
 */
esp_err_t video_player_start_stream(const char *stream_url)
{
    if (!g_video_ctx.is_initialized) {
        ESP_LOGE(TAG, "视频播放器未初始化");
        return ESP_ERR_INVALID_STATE;
    }

    if (!stream_url) {
        ESP_LOGE(TAG, "流URL为空");
        return ESP_ERR_INVALID_ARG;
    }

    if (g_video_ctx.state != VIDEO_STATE_IDLE) {
        ESP_LOGW(TAG, "停止当前播放...");
        video_player_stop();
        vTaskDelay(pdMS_TO_TICKS(100)); // 等待停止完成
    }

    ESP_LOGI(TAG, "🌐 开始接收流: %s", stream_url);

    // 显示Canvas
    video_player_set_visible(true);

    // 清除停止信号
    xEventGroupClearBits(g_video_ctx.events, STOP_PLAY_BIT | PAUSE_PLAY_BIT);

    // 创建流接收任务
    xTaskCreate(http_stream_task, "http_stream", 8192, (void*)stream_url, 5, &g_video_ctx.stream_task);

    return ESP_OK;
}

esp_err_t video_player_update_frame(const uint8_t *jpeg_data, size_t data_size)
{
    if (!g_video_ctx.is_initialized) {
        ESP_LOGE(TAG, "视频播放器未初始化");
        return ESP_ERR_INVALID_STATE;
    }

    if (!jpeg_data || data_size == 0) {
        ESP_LOGE(TAG, "JPEG数据无效");
        return ESP_ERR_INVALID_ARG;
    }

    // 直接解码并显示
    return decode_and_display_frame(jpeg_data, data_size);
}

/**
 * 暂停播放
 */
esp_err_t video_player_pause(void)
{
    if (!g_video_ctx.is_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    if (g_video_ctx.state == VIDEO_STATE_PLAYING_FILE || g_video_ctx.state == VIDEO_STATE_RECEIVING_STREAM) {
        xEventGroupSetBits(g_video_ctx.events, PAUSE_PLAY_BIT);
        g_video_ctx.state = VIDEO_STATE_PAUSED;
        ESP_LOGI(TAG, "⏸️ 视频播放已暂停");
    }

    return ESP_OK;
}

/**
 * 恢复播放
 */
esp_err_t video_player_resume(void)
{
    if (!g_video_ctx.is_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    if (g_video_ctx.state == VIDEO_STATE_PAUSED) {
        xEventGroupClearBits(g_video_ctx.events, PAUSE_PLAY_BIT);

        if (g_video_ctx.file_task) {
            g_video_ctx.state = VIDEO_STATE_PLAYING_FILE;
        } else if (g_video_ctx.stream_task) {
            g_video_ctx.state = VIDEO_STATE_RECEIVING_STREAM;
        }

        ESP_LOGI(TAG, "▶️ 视频播放已恢复");
    }

    return ESP_OK;
}

/**
 * 停止播放
 */
esp_err_t video_player_stop(void)
{
    if (!g_video_ctx.is_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    if (g_video_ctx.state == VIDEO_STATE_IDLE) {
        return ESP_OK;
    }

    ESP_LOGI(TAG, "⏹️ 停止视频播放...");

    // 🔧 优雅停止：设置停止信号，让任务自然退出
    xEventGroupSetBits(g_video_ctx.events, STOP_PLAY_BIT);
    ESP_LOGI(TAG, "🛑 发送停止信号，等待任务自然退出...");

    // 🔧 等待任务自然退出（最多等待2秒，增加等待时间）
    int wait_count = 0;
    while ((g_video_ctx.file_task || g_video_ctx.stream_task) && wait_count < 20) {
        vTaskDelay(pdMS_TO_TICKS(100));
        wait_count++;
        if (wait_count % 5 == 0) {  // 每500ms打印一次
            ESP_LOGI(TAG, "⏳ 等待视频任务退出... %d/20", wait_count);
        }
    }

    // 🔧 如果任务仍未退出，记录警告但不强制删除
    if (g_video_ctx.file_task || g_video_ctx.stream_task) {
        ESP_LOGW(TAG, "⚠️ 视频任务未能在1秒内自然退出，但不强制删除避免死锁");
        // 清空句柄，让任务自己清理
        g_video_ctx.file_task = NULL;
        g_video_ctx.stream_task = NULL;
    } else {
        ESP_LOGI(TAG, "✅ 视频任务已自然退出");
    }

    // 🔧 修复：只有在任务已退出时才关闭文件，避免双重关闭
    if (g_video_ctx.video_file && !g_video_ctx.file_task) {
        ESP_LOGI(TAG, "🔧 主线程关闭视频文件");
        fclose(g_video_ctx.video_file);
        g_video_ctx.video_file = NULL;
    } else if (g_video_ctx.video_file) {
        ESP_LOGW(TAG, "⚠️ 文件将由任务线程关闭，避免双重关闭");
        g_video_ctx.video_file = NULL;  // 清空指针，让任务线程负责关闭
    }

    // 清理HTTP客户端
    if (g_video_ctx.http_client) {
        esp_http_client_cleanup(g_video_ctx.http_client);
        g_video_ctx.http_client = NULL;
    }

    g_video_ctx.state = VIDEO_STATE_IDLE;
    video_player_set_visible(false);

    ESP_LOGI(TAG, "✅ 视频播放已停止");
    return ESP_OK;
}

/**
 * 获取播放状态
 */
video_state_t video_player_get_state(void)
{
    return g_video_ctx.state;
}

/**
 * 显示/隐藏视频Canvas
 */
void video_player_set_visible(bool visible)
{
    if (!g_video_ctx.is_initialized) {
        ESP_LOGW(TAG, "视频播放器未初始化");
        return;
    }

    if (g_video_ctx.is_visible == visible) {
        return; // 状态未改变
    }

    // 🔧 简单策略：直接设置，不做复杂检查
    if (g_video_ctx.canvas) {
        if (visible) {
            lv_obj_remove_flag(g_video_ctx.canvas, LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_obj_add_flag(g_video_ctx.canvas, LV_OBJ_FLAG_HIDDEN);
        }
    }

    g_video_ctx.is_visible = visible;
}

/**
 * 获取Canvas对象
 */
lv_obj_t* video_player_get_canvas(void)
{
    if (!g_video_ctx.is_initialized) {
        ESP_LOGW(TAG, "视频播放器未初始化");
        return NULL;
    }

    return g_video_ctx.canvas;
}

/**
 * 反初始化播放器
 */
void video_player_deinit(void)
{
    if (!g_video_ctx.is_initialized) {
        return;
    }

    ESP_LOGI(TAG, "🧹 开始反初始化视频播放器...");

    // 停止所有播放
    video_player_stop();

    // 等待任务完全结束
    vTaskDelay(pdMS_TO_TICKS(500));

    // 清理Canvas
    if (g_video_ctx.canvas) {
        lv_obj_del(g_video_ctx.canvas);
        g_video_ctx.canvas = NULL;
    }

    // 释放所有缓冲区
    if (g_video_ctx.video_buffer) {
        free(g_video_ctx.video_buffer);
        g_video_ctx.video_buffer = NULL;
    }

    if (g_video_ctx.mjpeg_buffer) {
        free(g_video_ctx.mjpeg_buffer);
        g_video_ctx.mjpeg_buffer = NULL;
    }

    if (g_video_ctx.http_buffer) {
        free(g_video_ctx.http_buffer);
        g_video_ctx.http_buffer = NULL;
    }

    // 清理事件组
    if (g_video_ctx.events) {
        vEventGroupDelete(g_video_ctx.events);
        g_video_ctx.events = NULL;
    }

    // 清零结构体
    memset(&g_video_ctx, 0, sizeof(video_player_ctx_t));

    ESP_LOGI(TAG, "✅ 视频播放器反初始化完成");
}
