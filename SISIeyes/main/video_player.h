/**
 * SISIeyes 视频播放器
 * 基于你现有的API：esp_jpeg_decode() + LVGL Canvas
 * 借鉴ESP-BOX架构思路，100%使用你的组件
 */

#pragma once

#include "esp_err.h"
#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

// 视频播放器配置 - 适配你的1.47寸显示屏
#define VIDEO_CANVAS_WIDTH  172
#define VIDEO_CANVAS_HEIGHT 320
#define VIDEO_BUFFER_SIZE   (VIDEO_CANVAS_WIDTH * VIDEO_CANVAS_HEIGHT * 4) // 双倍缓冲区
#define MJPEG_BUFFER_SIZE   (200 * 1024) // 200KB MJPEG缓冲区
#define HTTP_BUFFER_SIZE    (32 * 1024)  // 32KB HTTP接收缓冲区

// 视频播放器状态
typedef enum {
    VIDEO_STATE_IDLE,
    VIDEO_STATE_PLAYING_FILE,
    VIDEO_STATE_RECEIVING_STREAM,
    VIDEO_STATE_PAUSED,
    VIDEO_STATE_ERROR
} video_state_t;

// 视频播放器事件
typedef enum {
    VIDEO_EVENT_STARTED,
    VIDEO_EVENT_FRAME_DECODED,
    VIDEO_EVENT_STOPPED,
    VIDEO_EVENT_ERROR,
    VIDEO_EVENT_NETWORK_CONNECTED,
    VIDEO_EVENT_NETWORK_DISCONNECTED
} video_event_t;

// 事件回调函数
typedef void (*video_event_cb_t)(video_event_t event, void* user_data);

/**
 * 初始化视频播放器
 * @param parent LVGL父对象
 * @param event_cb 事件回调函数 (可选)
 * @param user_data 用户数据 (可选)
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t video_player_init(lv_obj_t *parent, video_event_cb_t event_cb, void* user_data);

/**
 * 播放本地MJPEG文件
 * @param file_path 文件路径 (如: "/spiffs/video.mjp")
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t video_player_play_file(const char *file_path);

/**
 * 开始接收网络MJPEG流
 * @param stream_url 流媒体URL (如: "http://192.168.1.100:8080/video")
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t video_player_start_stream(const char *stream_url);

/**
 * 更新单个JPEG帧 (用于外部数据源)
 * @param jpeg_data JPEG数据
 * @param data_size 数据大小
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t video_player_update_frame(const uint8_t *jpeg_data, size_t data_size);

/**
 * 暂停播放
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t video_player_pause(void);

/**
 * 恢复播放
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t video_player_resume(void);

/**
 * 停止播放
 * @return ESP_OK 成功，其他值失败
 */
esp_err_t video_player_stop(void);

/**
 * 获取播放状态
 * @return 当前播放状态
 */
video_state_t video_player_get_state(void);

/**
 * 显示/隐藏视频Canvas
 * @param visible true显示，false隐藏
 */
void video_player_set_visible(bool visible);

/**
 * 获取Canvas对象
 * @return LVGL Canvas对象指针
 */
lv_obj_t* video_player_get_canvas(void);

/**
 * 反初始化播放器
 */
void video_player_deinit(void);

#ifdef __cplusplus
}
#endif
