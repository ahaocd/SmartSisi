#pragma once
#include "lvgl.h"
#include "esp_lcd_panel_ops.h"

// 外部字体声明
extern const lv_font_t lv_font_simsun_16_cjk;

// 定义UI场景的枚举类型
typedef enum {
    UI_SCENE_NONE,
    UI_SCENE_BOOT_VIDEO,
    UI_SCENE_INTERACTIVE,
    UI_SCENE_MUSIC_VIS,
} ui_scene_t;

// 数据结构体，用于在切换场景时传递数据
typedef struct {
    const char* text1;
    const char* text2;
    const char* log_text;
    uint8_t* audio_data;
    uint8_t audio_data_size;
} ui_data_t;

void sisi_ui_init(esp_lcd_panel_handle_t panel_handle);
void sisi_ui_switch_scene(ui_scene_t new_scene, const ui_data_t* data);

void sisi_ui_update_text(const char* text1, const char* text2);
void sisi_ui_update_audio_data(uint8_t *data, uint8_t size);
void sisi_ui_add_log(const char* log_text);

// 🚀 SISI实时文字推送API
void sisi_ui_update_sisi_text(const char* sisi_text);

// 🎵 音频频谱数据更新API
void sisi_ui_update_audio_spectrum(const uint8_t* spectrum_data, size_t data_size);

// 📺 图片显示API
void sisi_ui_display_image(const lv_image_dsc_t* img_dsc);

// 🎥 视频播放器测试API
esp_err_t sisi_ui_test_video_player(void);
esp_err_t sisi_ui_test_video_file(const char* file_path);
esp_err_t sisi_ui_test_video_stream(const char* stream_url);
esp_err_t sisi_ui_test_video_frame(void);

// 🎥 空闲视频播放管理API
esp_err_t sisi_ui_start_idle_video(const char* video_file_path);
esp_err_t sisi_ui_stop_idle_video(void);
void sisi_ui_reset_idle_timer(void);  // 重置空闲计时器