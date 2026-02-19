#include "sisi_ui.h"
#include "video_player.h"  // 🎥 新增：视频播放器
#include "freertos/FreeRTOS.h"
#include "freertos/timers.h"
#include <math.h>  // 🌀 数学函数：sin, cos, M_PI
// 🧹 清理：删除视频相关头文件
// #include "video_frames.h"  // 已删除：视频帧定义
// #include "avi_player_esp32.h"  // 已删除：AVI播放器
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_system.h"
#include "esp_random.h"  // 添加ESP随机数生成头文件
#include "esp_task_wdt.h"  // 添加看门狗头文件
#include "lvgl.h"
#include "jpeg_decoder.h"  // ESP32专用JPEG解码器
#include "cJSON.h"
// 视频播放通过HTTP流实现，不需要本地资源文件 // 我们的视频数据
#include <string.h>
#include <stdlib.h>
#include <math.h>  // 🌌 3D宇宙变换需要数学函数
#include <inttypes.h>  // 🔧 修复：添加PRId32格式符支持
#include "esp_lvgl_port.h"  // 保证可见锁API
#include "lvgl.h"   // 包含 lv_font_t 定义
// 直接声明字体，避免头文件路径问题
extern const lv_font_t font_puhui_30_4;
extern const lv_font_t* font_emoji_32_init(void);

// 引入LVGL官方中文字体 - 只有在menuconfig中启用后才可用
#if LV_FONT_SIMSUN_16_CJK
LV_FONT_DECLARE(lv_font_simsun_16_cjk);
#endif

#define TAG "SISI_UI"
#define LOG_LINE_COUNT 1  // 只显示1行日志，浅层显示

// 🔧 修复：添加TFT尺寸定义
#define TFT_WIDTH   172
#define TFT_HEIGHT  320
#define DEFAULT_CHAR_HEIGHT_PX 40  // 备用常量，真正行距运行时计算
// === 新增：竖排文字布局参数 ===
#define CHAR_ZOOM            256   // 保持原始字体大小 (1×)
#define TARGET_LINES_PER_COL 7     // 每列理想显示 7 行
// ★ 列间距/列宽改为 **动态计算**，以下占位默认值仅避免编译错误
#define COLUMN_GAP_PX        8     // 默认列间距 (运行时会被覆盖)
#define COLUMN_WIDTH_PX      40    // 默认列宽   (运行时会被覆盖)
// 运行时计算后的最终宽度，通过全局变量给 draw_page 使用
static int g_column_gap_px = COLUMN_GAP_PX;
static int g_column_width_px = COLUMN_WIDTH_PX;
static int g_container_width_px = (COLUMN_WIDTH_PX * 2 + COLUMN_GAP_PX);

// 🔒 简易锁宏，防止忘记解锁
#define LV_PORT_LOCK(timeout_ms)   do { if(!lvgl_port_lock(timeout_ms)){ ESP_LOGW(TAG, "⚠️ LVGL锁超时"); return; } } while(0)
#define LV_PORT_TRYLOCK(timeout_ms)  lvgl_port_lock(timeout_ms)
#define LV_PORT_UNLOCK()           lvgl_port_unlock()

// 🎥 空闲视频配置
#define IDLE_TIMEOUT_MS     (60 * 1000)  // 60秒无活动后播放空闲视频（延长显示时间）
#define DEFAULT_IDLE_VIDEO  "/spiffs/idle.mjp"  // 默认空闲视频文件

// --- 全局UI状态和对象 ---
static ui_scene_t current_scene = UI_SCENE_NONE;
static lv_obj_t* screen_container; // 一个容器来管理所有UI元素，方便整体删除

// 🎥 空闲视频管理
static TimerHandle_t idle_timer = NULL;
static bool idle_video_playing = false;
static char idle_video_path[256] = DEFAULT_IDLE_VIDEO;
static bool video_player_initialized = false;

// 场景2: 交互场景对象
static lv_obj_t *label_left;
static lv_obj_t *label_right;
static lv_obj_t *log_labels[LOG_LINE_COUNT];
static char log_buffer[LOG_LINE_COUNT][64] = {0};

// 场景3: 🎵 赛博朋克音频可视化对象
static lv_obj_t *spectrum_canvas = NULL;
static uint8_t audio_spectrum_data[8] = {0};  // 8个频段
static lv_timer_t* spectrum_timer = NULL;   // 画布刷新定时器

// 🎵 赛博朋克动画对象 - 全局变量，供多个函数访问
static lv_obj_t *stars[10] = {NULL};     // 🌟 10颗星星
static lv_obj_t *missiles[3] = {NULL};   // 🚀 3个导弹
static lv_obj_t *satellites[2] = {NULL}; // 🛰️ 2个卫星
static bool animation_objects_created = false;

// 图片显示对象 - 使用Canvas而不是Image
static lv_obj_t *image_canvas = NULL;
// 已移除未使用的rgb_buffer变量

// 文字渐变显示相关
// 暂时未使用的变量 (为了避免编译警告)
// static char* full_text = NULL;  // 完整文字
// static int text_offset = 0;     // 当前显示偏移
// static lv_timer_t* text_timer = NULL;  // 文字切换定时器

// 任务句柄 - 傅里叶螺旋和音频跟随
// static TaskHandle_t missile_task_handle = NULL;
// 🔧 旧的视频任务句柄已删除，使用新的video_sys系统

// LV_FONT_DECLARE(lv_font_chinese_38);  // 删除大字体声明

// -------- 专业音乐可视化全局 ----------
#define SPECTRUM_BARS_COUNT 24  // 🎵 24个频谱条，更细腻的频谱显示
static lv_obj_t *spectrum_bars[SPECTRUM_BARS_COUNT] = {NULL};  // 频谱柱状图对象

// 🎵 专业音乐可视化参数 - 充分利用屏幕空间
static const int bar_width = 6;        // 频谱条宽度（更细，显示更多条）
static const int bar_spacing = 1;      // 频谱条间距（更紧密）
static const int bar_max_height = 80;  // 频谱条最大高度（屏幕1/4，优雅美观）
static const int start_x = 2;          // 起始X位置（居中对齐）
static const int spectrum_base_y = 320; // 频谱条基准Y位置（屏幕底部，固定不动）

// 🔧 修复：添加动画超时机制
static uint32_t last_audio_time = 0;   // 最后一次音频数据时间
static const uint32_t ANIMATION_TIMEOUT_MS = 10000;  // 10秒超时
// 🎵 赛博朋克音频可视化系统 - 全局定义
// animation_objects_created 已在上面定义

// 🔧 使用LVGL官方的lv_lock/lv_unlock线程安全机制

// 🚀 分页竖排显示相关全局变量（提前声明，供clear_current_scene引用）
#define PAGE_INTERVAL_MS 5000  // 翻页间隔(ms) - 调整为 5 秒，更长显示时间
static lv_timer_t* page_timer = NULL;
static const char* page_text_buf = NULL;
static int total_pages = 0;
static int current_page = 0;
static int lines_per_page = 0;
static lv_obj_t* page_cont = NULL;

// 文字叠加层对象(可选弹窗)
static lv_obj_t* text_overlay = NULL;
static lv_timer_t* text_overlay_timer = NULL;

// 🎬 简化视频系统：esp_lcd_tjpgd_reference策略
// 🧹 清理：删除复杂的视频系统结构体
// 保留简单的显示模式枚举用于未来HAGL集成
typedef enum {
    DISPLAY_MODE_UI,      // LVGL UI模式（文本、照片）
    DISPLAY_MODE_MUSIC,   // 音频可视化模式
    DISPLAY_MODE_VIDEO    // 视频播放模式（未来用HAGL实现）
} display_mode_t;

// 🗑️ 已删除未使用的 current_display_mode 变量

// 🧹 清理：删除视频系统相关的前向声明


// 异步场景切换所需的数据结构和回调函数
typedef struct {
    ui_scene_t scene;
    ui_data_t data; // 直接包含数据，而不是指针
    bool has_data;
} async_switch_data_t;

static void _async_ui_switch_scene_cb(void* user_data);
static void _async_ui_init_cb(void* user_data);

// --- 私有函数声明 ---
static void clear_current_scene();
// 注释未使用的渐变函数声明
// static void fade_to_black(void);
// static void fade_from_black(void);
static char *create_vertical_text(const char *input);
static void show_vertical_pages_cycle(const char* sisi_text);
static void draw_page(int page_idx);
static int utf8_next_len(const char* p);

// 🧹 清理：删除视频场景声明
// static void create_boot_video_scene();  // 已删除
static void create_interactive_scene(const ui_data_t* data);
static void create_music_scene(const ui_data_t* data);

// 前向声明：后面才定义，先让编译器知道
static void music_canvas_refresh_cb(lv_timer_t *t);

// HTTP视频流通过esp_http_client直接获取JPEG数据
// LVGL内置TJPGD解码器会自动处理JPEG格式

// --- 核心公有函数 ---
void sisi_ui_init(esp_lcd_panel_handle_t panel_handle) {
    ESP_LOGI(TAG, "🚀 SISI UI初始化 - 发送异步请求");

    // 🔧 LVGL官方线程安全机制会自动初始化

    lv_async_call(_async_ui_init_cb, NULL);
    // 🔧 等待一帧时间，确保异步调用有机会执行
    vTaskDelay(pdMS_TO_TICKS(50));
}

// 异步初始化回调
static void _async_ui_init_cb(void* user_data) {
    ESP_LOGI(TAG, "🔄 [LVGL上下文] 执行UI初始化");
    
    lv_obj_clean(lv_screen_active());

    screen_container = lv_obj_create(lv_screen_active());
    if (!screen_container) {
        ESP_LOGE(TAG, "❌ screen_container创建失败");
        return;
    }
    lv_obj_set_size(screen_container, 172, 320);
    lv_obj_center(screen_container);
    lv_obj_set_style_bg_opa(screen_container, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(screen_container, 0, 0);
    lv_obj_set_style_pad_all(screen_container, 0, 0);

    ESP_LOGI(TAG, "✅ screen_container初始化完成");

    // 🔧 修复：设置屏幕根对象为黑色背景，避免蓝白相间
    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_black(), 0);
    lv_obj_set_style_bg_opa(lv_screen_active(), LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(lv_screen_active(), 0, 0);
    lv_obj_set_style_outline_width(lv_screen_active(), 0, 0);
    lv_obj_set_style_pad_all(lv_screen_active(), 0, 0);
    lv_obj_set_style_margin_all(lv_screen_active(), 0, 0);

    // 🧹 清理：删除自动视频场景切换

    // 🎥 启动空闲视频系统
    esp_err_t ret = sisi_ui_start_idle_video(NULL);  // 使用默认视频文件
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "🎬 空闲视频系统已启动");
    } else {
        ESP_LOGW(TAG, "⚠️ 空闲视频系统启动失败，将在有视频文件时重试");
    }

    ESP_LOGI(TAG, "✅ SISI UI初始化完成 - 等待场景切换");
}

void sisi_ui_switch_scene(ui_scene_t new_scene, const ui_data_t* data) {
    // 这是"信使"函数，它只负责打包数据并发送异步请求
    // 绝对不直接操作UI或加锁！

    // 1. 分配内存来存储场景数据。这个内存将在异步回调中被释放。
    async_switch_data_t* p_data = (async_switch_data_t*)malloc(sizeof(async_switch_data_t));
    if (p_data == NULL) {
        ESP_LOGE(TAG, "❌ 无法为异步场景切换分配内存");
        return;
    }

    // 2. 填充数据
    p_data->scene = new_scene;
    if (data) {
        p_data->data = *data; // 复制数据内容
        p_data->has_data = true;
    } else {
        p_data->has_data = false;
    }

    // 3. 发送异步调用请求，让LVGL线程在安全的时候执行
    ESP_LOGI(TAG, "📬 发送异步场景切换请求: %d", (int)new_scene);
    lv_async_call(_async_ui_switch_scene_cb, p_data);
}

// 这是真正执行UI操作的函数，它总是在安全的LVGL线程中被调用
static void _async_ui_switch_scene_cb(void* user_data) {
    async_switch_data_t* p_data = (async_switch_data_t*)user_data;
    if (p_data == NULL) return;

    ui_scene_t new_scene = p_data->scene;
    const ui_data_t* data_ptr = p_data->has_data ? &p_data->data : NULL;

    ESP_LOGI(TAG, "🔄 [LVGL上下文] 执行场景切换: %d -> %d", (int)current_scene, (int)new_scene);

    // 清理当前场景
    clear_current_scene();
    current_scene = new_scene;

    // 创建新场景
    switch (new_scene) {
        case UI_SCENE_INTERACTIVE:
            create_interactive_scene(data_ptr);
            break;
        case UI_SCENE_MUSIC_VIS:
            create_music_scene(data_ptr);
            break;
        default:
            // 默认等待界面
            if (screen_container && lv_obj_is_valid(screen_container)) {
                 lv_obj_set_style_bg_color(screen_container, lv_color_black(), 0);
                 lv_obj_set_style_bg_opa(screen_container, LV_OPA_COVER, 0);

                 lv_obj_t* wait_label = lv_label_create(screen_container);
                 lv_obj_set_style_text_font(wait_label, &font_puhui_30_4, 0);
                 lv_obj_set_style_text_color(wait_label, lv_color_white(), 0);
                 lv_obj_set_style_text_align(wait_label, LV_TEXT_ALIGN_CENTER, 0);
                 lv_obj_align(wait_label, LV_ALIGN_CENTER, 0, 0);
                 lv_label_set_text(wait_label, "Ready");
                 lv_obj_set_style_transform_zoom(wait_label, 512, 0);
            }
            break;
    }
    
    // 释放为参数分配的内存
    free(p_data);
}

// --- 场景管理和动画 ---
// 注释未使用的回调函数，避免编译警告
// static void fade_anim_cb(void* obj, int32_t v) {
//     lv_obj_t* target = (lv_obj_t*)obj;
//     if (target && lv_obj_is_valid(target)) {
//         lv_obj_set_style_bg_opa(target, (lv_opa_t)v, 0);
//     }
// }

// 正确的缩放动画回调函数
#if 0 // 未使用动画回调
static void scale_anim_cb(void* obj, int32_t v) {}
static void rotation_anim_cb(void* obj, int32_t v) {}
#endif

// 🔧 移除未使用的函数以避免编译警告

// 注释未使用的渐变函数，避免编译警告
// static void fade_to_black(void) {
//     if (!screen_container) return;
//     lv_anim_t a;
//     lv_anim_init(&a);
//     lv_anim_set_var(&a, screen_container);
//     lv_anim_set_values(&a, LV_OPA_COVER, LV_OPA_TRANSP);
//     lv_anim_set_exec_cb(&a, fade_anim_cb);
//     lv_anim_set_time(&a, 300);
//     lv_anim_start(&a);
//     vTaskDelay(pdMS_TO_TICKS(350));
// }

// static void fade_from_black(void) {
//     if (!screen_container) return;
//     lv_anim_t a;
//     lv_anim_init(&a);
//     lv_anim_set_var(&a, screen_container);
//     lv_anim_set_values(&a, LV_OPA_TRANSP, LV_OPA_COVER);
//     lv_anim_set_exec_cb(&a, fade_anim_cb);
//     lv_anim_set_time(&a, 300);
//     lv_anim_start(&a);
// }

// --- 场景管理 ---
static void clear_current_scene() {
    LV_PORT_LOCK(100);
    ESP_LOGI(TAG, "🧹 [DEBUG] 开始清理场景: %d", (int)current_scene);

    // 🔧 安全清理：先停止所有定时器，避免访问已删除对象
    if (spectrum_timer) {
        ESP_LOGI(TAG, "🛑 [DEBUG] 正在删除频谱定时器...");
        lv_timer_del(spectrum_timer);
        spectrum_timer = NULL;
        ESP_LOGI(TAG, "✅ [DEBUG] 频谱定时器已删除");
    } else {
        ESP_LOGI(TAG, "ℹ️ [DEBUG] 频谱定时器为空，跳过删除");
    }

    if (page_timer) {
        lv_timer_del(page_timer);
        page_timer = NULL;
    }
    if (page_text_buf) {
        free((void*)page_text_buf);
        page_text_buf = NULL;
    }
    // 🧹 清理：删除视频系统清理代码

    // 🎵 清理赛博朋克动画数据
    if (animation_objects_created) {
        ESP_LOGI(TAG, "🎵 清理赛博朋克动画数据...");

        // 🧹 清理星星对象
        for (int i = 0; i < 10; i++) {
            if (stars[i]) {
                lv_obj_del(stars[i]);
                stars[i] = NULL;
            }
        }

        // 🧹 清理导弹对象
        for (int i = 0; i < 3; i++) {
            if (missiles[i]) {
                lv_obj_del(missiles[i]);
                missiles[i] = NULL;
            }
        }

        // 🧹 清理旋律条对象（防止第二次调用崩溃）
        for (int i = 0; i < 24; i++) {
            if (spectrum_bars[i]) {
                lv_obj_del(spectrum_bars[i]);
                spectrum_bars[i] = NULL;
            }
        }
        ESP_LOGI(TAG, "✅ 旋律条对象已清理");

        // 🧹 重置动画状态（静态计数器会在下次创建时自动重置）
        animation_objects_created = false;
        ESP_LOGI(TAG, "✅ 赛博朋克动画数据清理完成");
    }

    // 🔧 彻底清理：清理所有文字和UI对象，确保不残留
    if (screen_container && lv_obj_is_valid(screen_container)) {
        ESP_LOGI(TAG, "🧹 [DEBUG] 正在彻底清理screen_container...");
        lv_obj_clean(screen_container);  // 清理所有子对象
        ESP_LOGI(TAG, "✅ [DEBUG] screen_container清理完成");
    } else {
        ESP_LOGW(TAG, "⚠️ [DEBUG] screen_container无效，跳过清理");
    }

    // 🔧 文字容器由LVGL自动管理，不需要手动清理

    // 🔧 不要清理lv_screen_active()，因为图片对象可能直接创建在上面
    
    // 🔧 图片Canvas独立管理 - 不在场景切换时删除
    // image_canvas 由定时器自动管理，不需要在场景切换时删除
    // ESP_LOGI(TAG, "🖼️ 图片Canvas保持独立，不受场景切换影响");

    // 重置所有静态UI对象指针
    label_left = NULL;
    label_right = NULL;
    spectrum_canvas = NULL;
    page_cont = NULL;
    text_overlay = NULL;

    // 🔧 清空频谱条指针，避免重复访问
    for (int i = 0; i < SPECTRUM_BARS_COUNT; i++) {
        spectrum_bars[i] = NULL;
    }

    // 🔧 清空星空动画对象指针
    ESP_LOGI(TAG, "🌟 [DEBUG] 清理星空动画对象指针");
    // 注意：实际对象已经通过lv_obj_clean(screen_container)删除了
    // 🧹 清理：删除视频系统相关清理代码
    image_canvas = NULL;  // 确保指针被重置

    current_scene = UI_SCENE_NONE;
    LV_PORT_UNLOCK();
    ESP_LOGI(TAG, "✅ 场景清理完成（包含残留对象和定时器）");
}

// HTTP视频流播放相关
#include "esp_http_client.h"
#include "esp_task_wdt.h"  // 🔧 添加看门狗头文件
#include "esp_lvgl_port.h"  // 🔧 添加LVGL端口头文件
#include "freertos/timers.h"  // 🔧 添加FreeRTOS定时器头文件

// 🔧 旧的视频URL变量已删除，使用video_sys.fg_url

// 🔧 线程安全的图像更新结构
typedef struct {
    lv_image_dsc_t img_dsc;
    uint8_t* jpeg_data;
    size_t data_size;
} video_frame_data_t;

// 🔧 删除未使用的异步回调函数 - 现在直接在HTTP任务中更新

// 设置视频服务器URL - 立即启动视频流
// 🔧 双层视频系统：设置前景视频服务器
// 🧹 清理：删除视频服务器设置函数

// 🧹 清理：删除AVI背景播放系统函数

// 🧹 清理：删除AVI定时器回调函数

// 🎵 音频频谱数据接收 - 驱动赛博朋克可视化
void sisi_ui_update_audio_spectrum(const uint8_t* spectrum_data, size_t data_size) {
    if (!spectrum_data || data_size < 8) {  // 🔥 要求8个频段
        ESP_LOGW(TAG, "⚠️ 音频频谱数据无效，需要8个频段");
        return;
    }

    // 更新全局音频频谱数据 - 赛博朋克动画需要8个频段
    size_t copy_size = (data_size > sizeof(audio_spectrum_data)) ? sizeof(audio_spectrum_data) : data_size;
    memcpy(audio_spectrum_data, spectrum_data, copy_size);

    ESP_LOGI(TAG, "🎵 赛博朋克音频数据更新: [%d, %d, %d, %d, %d, %d, %d, %d]",
             (int)audio_spectrum_data[0], (int)audio_spectrum_data[1],
             (int)audio_spectrum_data[2], (int)audio_spectrum_data[3],
             (int)audio_spectrum_data[4], (int)audio_spectrum_data[5],
             (int)audio_spectrum_data[6], (int)audio_spectrum_data[7]);

    // 🚀 如果音频强度足够，自动切换到导弹动画场景
    int audio_intensity = (audio_spectrum_data[0] + audio_spectrum_data[1] + audio_spectrum_data[2] + audio_spectrum_data[3] +
                          audio_spectrum_data[4] + audio_spectrum_data[5] + audio_spectrum_data[6] + audio_spectrum_data[7]) / 8;

    ESP_LOGI(TAG, "🎵 当前场景: %d, 音频强度: %d", current_scene, audio_intensity);

    // 🔧 修复：记录音频数据时间
    uint32_t current_time = xTaskGetTickCount() * portTICK_PERIOD_MS;
    if (audio_intensity > 15) {
        last_audio_time = current_time;  // 更新最后音频时间
    }

    // 🔧 修复：添加动画退出逻辑（强度不足或超时）
    if (current_scene == UI_SCENE_MUSIC_VIS) {
        bool should_exit = false;

        if (audio_intensity <= 15) {
            ESP_LOGI(TAG, "🔇 音频强度不足，退出动画");
            should_exit = true;
        } else if (current_time - last_audio_time > ANIMATION_TIMEOUT_MS) {
            ESP_LOGI(TAG, "⏰ 动画超时，退出动画");
            should_exit = true;
        }

        if (should_exit) {
            ESP_LOGI(TAG, "🔄 切换到空闲场景");
            sisi_ui_switch_scene(UI_SCENE_NONE, NULL);
            return;  // 退出后不再处理
        }
    }

    if (current_scene != UI_SCENE_MUSIC_VIS && audio_intensity > 15) {  // 统一阈值为15
        ESP_LOGI(TAG, "🎵 音频强度足够，启动赛博朋克可视化");

        // 🛡️ 先停止空闲视频，避免冲突
        if (idle_video_playing) {
            ESP_LOGI(TAG, "🛑 停止空闲视频，准备启动动画");
            sisi_ui_stop_idle_video();
            vTaskDelay(pdMS_TO_TICKS(200));  // 等待停止完成
        }

        ui_data_t ui_data = {
            .audio_data = audio_spectrum_data,
            .audio_data_size = copy_size
        };

        sisi_ui_switch_scene(UI_SCENE_MUSIC_VIS, &ui_data);
    }
}



// --- 场景2: 导弹交互 ---
static void create_interactive_scene(const ui_data_t* data) {
    // 创建星空背景画布 - 移除边框和填充
    lv_obj_t* bg_canvas = lv_canvas_create(screen_container);
    lv_obj_set_size(bg_canvas, lv_disp_get_hor_res(NULL), lv_disp_get_ver_res(NULL));
    lv_obj_center(bg_canvas);

    // 移除默认样式，避免白色边框
    lv_obj_set_style_border_width(bg_canvas, 0, 0);
    lv_obj_set_style_bg_opa(bg_canvas, LV_OPA_TRANSP, 0);
    lv_obj_set_style_pad_all(bg_canvas, 0, 0);

    // 创建文本和日志 - 使用LVGL内置字体
    // (这里只是框架，"导弹"动画在后台任务里实现)
    label_left = lv_label_create(screen_container);
    lv_obj_set_style_text_font(label_left, &font_puhui_30_4, 0);  // 使用阿里巴巴普惠体字体
    lv_obj_set_style_text_color(label_left, lv_color_white(), 0);
    lv_obj_set_style_text_align(label_left, LV_TEXT_ALIGN_CENTER, 0);  // 居中对齐

    /* 改用 LVGL 自带的居中 API, 让文字根据内容自动居中 */
    lv_obj_center(label_left);
    /* 若需要限制最大宽度，可取消注释下一行
       lv_obj_set_width(label_left, 160); */

    // 不使用滚动模式，使用自定义渐变切换
    lv_label_set_long_mode(label_left, LV_LABEL_LONG_WRAP);
    // 默认不显示任何文字，等待SISI推送
    if (data && data->text1) {
        char* v_text = create_vertical_text(data->text1);
        lv_label_set_text(label_left, v_text);
        free(v_text);
    } else {
        lv_label_set_text(label_left, "");  // 空白，等待SISI文字
    }

    // 不创建右侧文本，避免重叠
    label_right = NULL;
    
    // 暂时禁用日志显示，避免LVGL断言错误
    for (int i = 0; i < LOG_LINE_COUNT; i++) {
         log_labels[i] = NULL;  // 不创建日志标签
    }

    // 更新数据
    if(data) {
        if(data->text1) {
            char* v_text = create_vertical_text(data->text1);
            lv_label_set_text(label_left, v_text);
            free(v_text);
        }
        if(data->text2) {
            char* v_text = create_vertical_text(data->text2);
            lv_label_set_text(label_right, v_text);
            free(v_text);
        }
        if(data->log_text) {
            for (int i = LOG_LINE_COUNT - 1; i > 0; i--) {
                strcpy(log_buffer[i], log_buffer[i - 1]);
                lv_label_set_text(log_labels[i], log_buffer[i]);
            }
            strncpy(log_buffer[0], data->log_text, sizeof(log_buffer[0]) - 1);
            log_buffer[0][sizeof(log_buffer[0]) - 1] = '\0';
            lv_label_set_text(log_labels[0], log_buffer[0]);
        }
    }
    // 导弹动画已禁用
}

// --- 场景3: 🎵 赛博朋克音频可视化 ---
static void create_music_scene(const ui_data_t* data) {
    ESP_LOGI(TAG, "🎵 创建赛博朋克音频可视化场景");

    // 🎵 创建赛博朋克Canvas (使用8MB PSRAM)
    int canvas_width = lv_disp_get_hor_res(NULL);
    int canvas_height = lv_disp_get_ver_res(NULL);

    spectrum_canvas = lv_canvas_create(screen_container);
    lv_obj_set_size(spectrum_canvas, canvas_width, canvas_height);
    lv_obj_align(spectrum_canvas, LV_ALIGN_CENTER, 0, 0);

    // 🎵 创建赛博朋克背景 (深空黑色)
    lv_color_t space_bg = lv_color_black();
    lv_obj_set_style_bg_color(spectrum_canvas, space_bg, 0);
    lv_obj_set_style_bg_opa(spectrum_canvas, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(spectrum_canvas, 0, 0);
    lv_obj_set_style_pad_all(spectrum_canvas, 0, 0);

    ESP_LOGI(TAG, "✅ 赛博朋克场景创建成功: %dx%d", canvas_width, canvas_height);

    // 🎵 赛博朋克动画初始化完成

    // 更新初始音频数据
    if (data && data->audio_data) {
        memcpy(audio_spectrum_data, data->audio_data, data->audio_data_size);
        ESP_LOGI(TAG, "🌀 初始音频数据: [%d, %d, %d, %d]",
                 (int)audio_spectrum_data[0], (int)audio_spectrum_data[1],
                 (int)audio_spectrum_data[2], (int)audio_spectrum_data[3]);
    }

    // 创建16个频谱条用于频谱可视化
    // 🔧 使用全局定义的参数，不重复定义

    // 🎵 创建24个专业音乐频谱条
    for (int i = 0; i < SPECTRUM_BARS_COUNT; i++) {
        spectrum_bars[i] = lv_bar_create(screen_container);
        lv_obj_set_size(spectrum_bars[i], bar_width, bar_max_height);

        // 🎵 精确计算位置：底部固定，向上延伸
        int x_pos = start_x + i * (bar_width + bar_spacing);
        int y_pos = spectrum_base_y - bar_max_height;  // 初始位置：底部向上最大高度
        lv_obj_set_pos(spectrum_bars[i], x_pos, y_pos);
        lv_bar_set_range(spectrum_bars[i], 0, 255);

        // 🎵 现代化设计：轻微圆角，更美观
        lv_obj_set_style_radius(spectrum_bars[i], 1, 0);  // 1像素圆角

        // 🎵 根据频段位置设置渐变色彩
        float freq_ratio = (float)i / (SPECTRUM_BARS_COUNT - 1);  // 0.0 到 1.0
        uint16_t hue = (uint16_t)(freq_ratio * 300);  // 0°(红) 到 300°(紫)
        lv_color_t bar_color = lv_color_hsv_to_rgb(hue, 90, 100);  // 高饱和度，高亮度

        lv_obj_set_style_bg_color(spectrum_bars[i], bar_color, LV_PART_INDICATOR);
        lv_obj_set_style_bg_color(spectrum_bars[i], lv_color_hex(0x0a0a1a), LV_PART_MAIN);  // 深色背景
        lv_obj_set_style_bg_opa(spectrum_bars[i], LV_OPA_100, LV_PART_INDICATOR);

        // 🌟 发光效果：细边框
        lv_obj_set_style_border_width(spectrum_bars[i], 1, 0);
        lv_obj_set_style_border_color(spectrum_bars[i], bar_color, 0);
        lv_obj_set_style_border_opa(spectrum_bars[i], LV_OPA_60, 0);

        lv_bar_set_value(spectrum_bars[i], 0, LV_ANIM_OFF);
    }

    // 在LVGL线程创建定时器刷新 UI，可根据需要调整帧率（这里 ~30 FPS）
    spectrum_timer = lv_timer_create(music_canvas_refresh_cb, 33, NULL);

    // 立即刷新一次
    music_canvas_refresh_cb(spectrum_timer);
    ESP_LOGI(TAG, "✅ 3D宇宙旋律动画场景创建完成");
}

// 🔧 使用LVGL官方的lv_lock()/lv_unlock()，无需自定义实现

// 🚀 动画对象已在文件顶部定义

// 🎵 赛博朋克动画初始化完成标记
static void create_cyberpunk_animation(void) {
    if (animation_objects_created) {
        ESP_LOGW(TAG, "⚠️ 赛博朋克动画已初始化，跳过重复创建");
        return;
    }

    ESP_LOGI(TAG, "🎵 初始化赛博朋克动画...");
    animation_objects_created = true;
    ESP_LOGI(TAG, "✅ 赛博朋克动画初始化完成");
}

// 🌀 傅里叶螺旋定时器回调
static void music_canvas_refresh_cb(lv_timer_t *t)
{
    static uint16_t hue = 0;
    static int frame_count = 0;

    // 🎵 确保赛博朋克动画已初始化
    if (!animation_objects_created) {
        create_cyberpunk_animation();
        return;
    }

    // 🌀 傅里叶螺旋背景渐变
    int spiral_hue = 240 + (hue / 6) % 60;  // 240°-300° (蓝到紫)
    lv_color_t space_bg = lv_color_hsv_to_rgb(spiral_hue, 80, 5);  // 深空背景
    if (spectrum_canvas && lv_obj_is_valid(spectrum_canvas)) {
        lv_obj_set_style_bg_color(spectrum_canvas, space_bg, 0);
    }
    hue = (hue + 1) % 360;

    // 🎵 计算音频强度 - 使用8个频段
    int audio_intensity = (audio_spectrum_data[0] + audio_spectrum_data[1] + audio_spectrum_data[2] + audio_spectrum_data[3] +
                          audio_spectrum_data[4] + audio_spectrum_data[5] + audio_spectrum_data[6] + audio_spectrum_data[7]) / 8;

    // 🚀 3D星空宇宙动画（赛博朋克增强版）
    static float time_factor = 0.0f;
    // 🌟 动画对象现在是全局变量，在文件顶部定义
    static int star_count = 0;
    static int missile_count = 0;
    static int satellite_count = 0;
    static bool first_run = true;

    // 🧹 首次运行时重置计数器（防止第二次调用时的状态残留）
    if (first_run) {
        star_count = 0;
        missile_count = 0;
        satellite_count = 0;
        first_run = false;
        ESP_LOGI(TAG, "🧹 动画计数器已重置");
    }

    time_factor += 0.05f;  // 减慢时间，更平滑

    // 🌟 无条件创建星空效果：总是显示美丽的星空
    if (star_count < 10) {  // 🔧 无条件创建所有星星
        // 🌟 创建10颗星星就够了
        for (int i = 0; i < 10 && star_count < 10; i++) {
            if (!stars[i]) {
                stars[i] = lv_obj_create(spectrum_canvas);
                if (stars[i]) {
                    // 🌟 不同大小的星星
                    int star_size = (i % 4) + 1;  // 1-4像素
                    lv_obj_set_size(stars[i], star_size, star_size);

                    int x = rand() % 172;
                    int y = rand() % 200;  // 上半部分
                    lv_obj_set_pos(stars[i], x, y);

                    // ⭐ 白色闪烁星星
                    lv_color_t star_color = lv_color_white();
                    lv_obj_set_style_bg_color(stars[i], star_color, 0);
                    lv_obj_set_style_radius(stars[i], star_size/2, 0);
                    lv_obj_set_style_border_width(stars[i], 0, 0);
                    star_count++;
                }
            }
        }

        // ⭐ 宇宙星空效果：10颗星星，闪烁飘动
        for (int i = 0; i < 10; i++) {
            if (stars[i] && lv_obj_is_valid(stars[i])) {
                // ⭐ 星星闪烁：根据音频强度和宇宙规律
                int brightness = 100 + (int)(audio_intensity * 0.6f + 80 * sin(time_factor * 2 + i * 0.5f));
                brightness = brightness > 255 ? 255 : (brightness < 50 ? 50 : brightness);
                lv_obj_set_style_bg_opa(stars[i], brightness, 0);

                // ⭐ 星星缓慢飘动：宇宙微风效果
                int current_x = lv_obj_get_x(stars[i]);
                int current_y = lv_obj_get_y(stars[i]);

                // 🌌 宇宙飘动：根据时间因子
                float drift_x = sin(time_factor * 0.1f + i * 0.3f) * 0.8f;
                float drift_y = cos(time_factor * 0.15f + i * 0.2f) * 0.5f;

                int new_x = current_x + (int)drift_x;
                int new_y = current_y + (int)drift_y;

                // 边界检查：星星飞出屏幕就重新生成
                if (new_x < 0 || new_x >= 172 || new_y < 0 || new_y >= 200) {
                    new_x = rand() % 172;
                    new_y = rand() % 200;
                }

                lv_obj_set_pos(stars[i], new_x, new_y);
            }
        }
    }

    // 🚀 无条件创建导弹效果：总是有导弹飞行
    if ((rand() % 3 == 0) || missile_count < 5) {  // 🔧 高频率创建导弹，无音频强度限制
        for (int i = 0; i < 3; i++) {  // 🚀 只创建3个导弹
            if (!missiles[i]) {
                missiles[i] = lv_obj_create(spectrum_canvas);
                if (missiles[i]) {
                    // 🚀 导弹形状：细长型，像真实导弹
                    lv_obj_set_size(missiles[i], 4, 16);  // 4像素宽，16像素长

                    // 🚀 导弹起始位置：屏幕底部随机位置
                    int start_x = 20 + rand() % 130;  // 避免边缘
                    int start_y = 250 + rand() % 50;   // 底部区域
                    lv_obj_set_pos(missiles[i], start_x, start_y);

                    // 🌸 粉红色导弹
                    lv_obj_set_style_bg_color(missiles[i], lv_color_make(255, 105, 180), 0);

                    // 🚀 导弹形状：尖头效果
                    lv_obj_set_style_radius(missiles[i], 8, 0);  // 更圆润，像导弹头
                    lv_obj_set_style_border_width(missiles[i], 1, 0);
                    lv_obj_set_style_border_color(missiles[i], lv_color_make(255, 255, 255), 0);  // 白色边框
                    missile_count++;
                }
                break;  // 一次只创建一个
            }
        }
    }

    // 🛰️ 卫星效果：3D空间变换
    if (audio_intensity > 50 && satellite_count < 2 && (rand() % 20 == 0)) {
        for (int i = 0; i < 2; i++) {
            if (!satellites[i]) {
                satellites[i] = lv_obj_create(spectrum_canvas);
                if (satellites[i]) {
                    lv_obj_set_size(satellites[i], 4, 4);  // 中等大小
                    int x = 50 + rand() % 72;  // 中间区域
                    int y = 30 + rand() % 100;
                    lv_obj_set_pos(satellites[i], x, y);
                    lv_obj_set_style_bg_color(satellites[i], lv_color_make(0, 255, 255), 0);  // 青色卫星
                    lv_obj_set_style_radius(satellites[i], 2, 0);
                    lv_obj_set_style_border_width(satellites[i], 1, 0);
                    lv_obj_set_style_border_color(satellites[i], lv_color_white(), 0);
                    satellite_count++;
                }
                break;
            }
        }
    }

    // 🚀 粉红色导弹根据旋律飞行动画
    for (int i = 0; i < 3; i++) {  // 🔧 只处理3个导弹
        if (missiles[i] && lv_obj_is_valid(missiles[i])) {
            // 🚀 根据音频强度计算飞行速度
            float flight_speed = 2.0f + audio_intensity * 0.03f;  // 基础速度 + 音频加速
            int current_x = lv_obj_get_x(missiles[i]);
            int current_y = lv_obj_get_y(missiles[i]);

            // 🚀 真实导弹轨迹：主要向上 + 轻微弧线
            int new_x = current_x + (int)(3 * sin(time_factor * 2 + i * 0.5f));  // 轻微弧线
            int new_y = current_y - (int)flight_speed;  // 向上飞行

            // 🌸 飞行时颜色变化：粉红色渐变
            uint8_t alpha = 200 + (int)(55 * sin(time_factor * 4 + i));  // 透明度变化
            lv_obj_set_style_bg_opa(missiles[i], alpha, 0);

            // 🚀 边界检查，飞出屏幕就删除
            if (new_x > 172 || new_x < 0 || new_y < -20) {  // 允许飞出顶部一点
                lv_obj_del(missiles[i]);
                missiles[i] = NULL;
                missile_count--;
            } else {
                lv_obj_set_pos(missiles[i], new_x, new_y);
            }
        }
    }

    // 🛰️ 卫星3D空间变换动画
    for (int i = 0; i < 2; i++) {
        if (satellites[i] && lv_obj_is_valid(satellites[i])) {
            // 🛰️ 3D轨道运动
            float orbit_radius = 30 + audio_intensity * 0.2f;
            int center_x = 86;  // 屏幕中心
            int center_y = 100;

            int orbit_x = center_x + (int)(orbit_radius * cos(time_factor * 0.8f + i * 3.14f));
            int orbit_y = center_y + (int)(orbit_radius * 0.6f * sin(time_factor * 0.8f + i * 3.14f));

            // 🛰️ 边界检查
            if (orbit_x >= 0 && orbit_x < 172 && orbit_y >= 0 && orbit_y < 200) {
                lv_obj_set_pos(satellites[i], orbit_x, orbit_y);

                // 🛰️ 根据距离调整大小（3D深度效果）
                float distance_factor = 0.5f + 0.5f * sin(time_factor * 0.8f + i * 3.14f);
                int size = 3 + (int)(3 * distance_factor);
                lv_obj_set_size(satellites[i], size, size);
            }
        }
    }

    // 🎵 调试日志：每10秒显示一次旋律条高度变化
    static int debug_counter = 0;
    if (debug_counter % 1000 == 0) {  // 每1000帧打印一次（约10秒）
        ESP_LOGI(TAG, "🎵 [10秒] Spectrum: intensity=%d, heights=[%d,%d,%d,%d]",
                 audio_intensity,
                 spectrum_bars[0] ? (int)lv_obj_get_height(spectrum_bars[0]) : 0,
                 spectrum_bars[1] ? (int)lv_obj_get_height(spectrum_bars[1]) : 0,
                 spectrum_bars[2] ? (int)lv_obj_get_height(spectrum_bars[2]) : 0,
                 spectrum_bars[3] ? (int)lv_obj_get_height(spectrum_bars[3]) : 0);
    }
    debug_counter++;

    ESP_LOGD(TAG, "🌟 3D宇宙动画: 强度=%d, 时间=%.2f", audio_intensity, time_factor);

    // 🎵 专业音乐频谱条 - 24个条，智能频段映射，动态律动
    static float bar_momentum[SPECTRUM_BARS_COUNT] = {0};  // 频谱条动量，实现平滑过渡
    static uint8_t bar_peak[SPECTRUM_BARS_COUNT] = {0};    // 峰值保持，增强视觉冲击
    static int peak_hold_time[SPECTRUM_BARS_COUNT] = {0};  // 峰值保持时间

    for (int i = 0; i < SPECTRUM_BARS_COUNT; i++) {
        if (spectrum_bars[i] && lv_obj_is_valid(spectrum_bars[i])) {
            // 🎵 智能频段映射：24个条映射到8个频段，使用增强插值算法
            float freq_position = (float)i / (SPECTRUM_BARS_COUNT - 1) * 7.0f;  // 0.0 到 7.0
            int base_index = (int)freq_position;
            float fraction = freq_position - base_index;

            // 边界检查
            if (base_index >= 7) {
                base_index = 7;
                fraction = 0.0f;
            }

            // 增强插值：添加随机变化，让相邻条有差异
            uint8_t value1 = audio_spectrum_data[base_index];
            uint8_t value2 = (base_index < 7) ? audio_spectrum_data[base_index + 1] : value1;

            // 基础线性插值
            float base_interpolated = value1 * (1.0f - fraction) + value2 * fraction;

            // 添加微小的随机变化，让相邻条不完全相同
            float variation = sin(time_factor * 2.0f + i * 0.5f) * 5.0f;  // ±5的变化
            float final_value = base_interpolated + variation;

            // 确保在有效范围内
            uint8_t interpolated_value = (uint8_t)fmax(0, fmin(255, final_value));

            // 🎵 快速响应：增强音乐节拍感
            float target_intensity = (float)interpolated_value / 255.0f;
            bar_momentum[i] = bar_momentum[i] * 0.3f + target_intensity * 0.7f;  // 快速响应

            // 🎵 峰值检测和保持：增强节拍感
            if (interpolated_value > bar_peak[i]) {
                bar_peak[i] = interpolated_value;
                peak_hold_time[i] = 15;  // 保持15帧（约0.5秒）
            } else if (peak_hold_time[i] > 0) {
                peak_hold_time[i]--;
            } else {
                bar_peak[i] = (uint8_t)(bar_peak[i] * 0.95f);  // 峰值缓慢衰减
            }

            // 🎵 计算最终显示高度：结合平滑值和峰值，极大增强对比度
            float final_intensity = fmax(bar_momentum[i], (float)bar_peak[i] / 255.0f);

            // 🎵 真正的音乐可视化：从0开始，根据强度动态变长
            // 移除最小高度限制，让旋律条真正从底部开始

            // 🎵 优化动态映射：保持可见性和美感
            final_intensity = sqrt(final_intensity);  // 平方根映射，保持小值可见性

            // 🎵 确保每个频段有独特表现
            float band_factor = 0.9f + (float)i * 0.02f;  // 0.9-1.38的范围
            final_intensity = final_intensity * band_factor;

            // 🎵 保持最小可见高度，增强美感
            if (final_intensity < 0.15f && final_intensity > 0.01f) {
                final_intensity = 0.15f;  // 最小15%高度，保持可见
            }

            int bar_height = (int)(final_intensity * bar_max_height);

            // 🎵 确保最小高度：至少5像素，让用户能看到
            if (bar_height < 5 && final_intensity > 0.01f) {
                bar_height = 5;
            }

            // 🎵 固定底部位置：Y坐标 = 屏幕底部 - 当前高度
            int x_pos = start_x + i * (bar_width + bar_spacing);
            int y_pos = spectrum_base_y - bar_height;  // 底部固定，只改变高度
            lv_obj_set_pos(spectrum_bars[i], x_pos, y_pos);
            lv_obj_set_height(spectrum_bars[i], bar_height);
            lv_bar_set_value(spectrum_bars[i], (int)(final_intensity * 255), LV_ANIM_OFF);

            // 🌈 动态色彩：根据强度和频段位置调整颜色
            float freq_ratio = (float)i / (SPECTRUM_BARS_COUNT - 1);
            uint16_t base_hue = (uint16_t)(freq_ratio * 300);  // 基础色相
            uint16_t dynamic_hue = (base_hue + (int)(final_intensity * 60)) % 360;  // 强度影响色相
            uint8_t saturation = 70 + (uint8_t)(final_intensity * 30);  // 强度影响饱和度
            uint8_t brightness = 80 + (uint8_t)(final_intensity * 75);  // 强度影响亮度

            lv_color_t dynamic_color = lv_color_hsv_to_rgb(dynamic_hue, saturation, brightness);
            lv_obj_set_style_bg_color(spectrum_bars[i], dynamic_color, LV_PART_INDICATOR);

            // 🌟 峰值高亮：峰值时增强边框发光
            uint8_t border_opa = 40 + (uint8_t)(final_intensity * 60);
            lv_obj_set_style_border_opa(spectrum_bars[i], border_opa, 0);
        }
    }

    // 🧹 删除重复代码，统一处理16个频谱条

    // 🌀 TODO: 在这里添加傅里叶螺旋绘制逻辑

    frame_count++;
}

// UTF-8字符长度计算函数
static int utf8_next_len(const char* p) {
    if (!p || !*p) return 0;
    if ((*p & 0xF8) == 0xF0) return 4;      // 4字节字符
    else if ((*p & 0xF0) == 0xE0) return 3; // 3字节字符（中文）
    else if ((*p & 0xE0) == 0xC0) return 2; // 2字节字符
    else return 1;                          // 1字节字符（ASCII）
}

static char *create_vertical_text(const char *input) {
    if (!input) return NULL;
    size_t input_len = strlen(input);
    if (input_len == 0) return lv_strdup("");

    // 172x320竖屏，38号字体，大约能显示12-15个字符高度
    // 增加显示字符数量，确保完整显示文字内容
    int max_chars = 20;  // 每列最多20行，确保完整显示

    char *vertical_text = malloc(input_len * 2 + 1);
    if (!vertical_text) return NULL;

    char *p_out = vertical_text;
    const char *p_in = input;
    int char_count = 0;

    while (*p_in && char_count < max_chars) {
        int char_len = 1;
        if ((*p_in & 0xF8) == 0xF0) char_len = 4;
        else if ((*p_in & 0xF0) == 0xE0) char_len = 3;
        else if ((*p_in & 0xE0) == 0xC0) char_len = 2;

        memcpy(p_out, p_in, char_len);
        p_in += char_len;
        p_out += char_len;
        char_count++;

        if (*p_in != '\0' && char_count < max_chars) {
            *p_out = '\n';
            p_out++;
        }
    }
    *p_out = '\0';
    return vertical_text;
}

// 文字叠加层定时器回调
static void text_overlay_timer_cb(lv_timer_t* timer) {
    if (text_overlay) {
        lv_obj_del(text_overlay);
        text_overlay = NULL;
        ESP_LOGI(TAG, "🕐 文字叠加层自动清除");
    }

    if (text_overlay_timer) {
        lv_timer_del(text_overlay_timer);
        text_overlay_timer = NULL;
    }
}

// 显示文字叠加层（不清除视频）
void sisi_ui_show_text_overlay(const char* text, int duration_ms) {
    if (!text || strlen(text) == 0) {
        return;
    }

    ESP_LOGI(TAG, "📝 显示文字叠加: %s (持续%dms)", text, (int)duration_ms);

    // 清除之前的叠加层
    if (text_overlay) {
        lv_obj_del(text_overlay);
        text_overlay = NULL;
    }

    if (text_overlay_timer) {
        lv_timer_del(text_overlay_timer);
        text_overlay_timer = NULL;
    }

    // 创建文字叠加层 - 修复LVGL 9.3 API
    text_overlay = lv_label_create(lv_screen_active());

    // 转换为竖排文字
    char* v_text = create_vertical_text(text);
    if (v_text) {
        lv_label_set_text(text_overlay, v_text);
        free(v_text);
    } else {
        lv_label_set_text(text_overlay, text);
    }

    // 设置半透明背景
    lv_obj_set_style_bg_opa(text_overlay, LV_OPA_80, 0);
    lv_obj_set_style_bg_color(text_overlay, lv_color_black(), 0);
    lv_obj_set_style_text_color(text_overlay, lv_color_white(), 0);
    lv_obj_set_style_text_font(text_overlay, &font_puhui_30_4, 0);
    lv_obj_set_style_text_align(text_overlay, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_pad_all(text_overlay, 10, 0);
    lv_obj_set_style_radius(text_overlay, 5, 0);

    // 让标签宽度自适应（竖排时≈字体宽）再整体居中
    lv_obj_set_width(text_overlay, LV_SIZE_CONTENT);
    lv_label_set_long_mode(text_overlay, LV_LABEL_LONG_WRAP);

    lv_obj_set_style_text_align(text_overlay, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_center(text_overlay);

    // 设置定时器自动清除
    if (duration_ms > 0) {
        text_overlay_timer = lv_timer_create(text_overlay_timer_cb, duration_ms, NULL);
    }
}

// 🚀 SmartSisi实时文字推送实现 - 简化版：纯白色、放大、居中
void sisi_ui_update_sisi_text(const char* sisi_text) {
    if (!sisi_text) return;

    // 🎥 重置空闲计时器 - 有新的文字活动
    sisi_ui_reset_idle_timer();

    LV_PORT_LOCK(500);

    ESP_LOGI("SISI_UI", "📝 收到SmartSisi文字推送: %s", sisi_text);
    ESP_LOGI("SISI_UI", "📝 文本长度: %d 字符，开始显示处理", strlen(sisi_text));

    // 🔍 调试：检查LVGL实际获取到的屏幕分辨率
    lv_coord_t hor_res = lv_disp_get_hor_res(NULL);
    lv_coord_t ver_res = lv_disp_get_ver_res(NULL);
    ESP_LOGI("SISI_UI", "🔍 LVGL屏幕分辨率: %ldx%ld", (long)hor_res, (long)ver_res);

    // 🔧 修复：不要清除screen_container，只清除其内容
    if (screen_container) {
        lv_obj_clean(screen_container);
    } else {
        lv_obj_clean(lv_screen_active());
    }
    show_vertical_pages_cycle(sisi_text);

    // 统一背景色
    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_black(), 0);
    lv_obj_set_style_bg_opa(lv_screen_active(), LV_OPA_COVER, 0);

    LV_PORT_UNLOCK();

    ESP_LOGI("SISI_UI", "✅ SISI文字显示完成");
}



// 实现其他更新函数
void sisi_ui_update_text(const char* text1, const char* text2) {
    if (current_scene != UI_SCENE_INTERACTIVE) return;

    // 🎥 重置空闲计时器 - 有新的文字活动
    sisi_ui_reset_idle_timer();

    if (text1 && label_left) {
        char* v_text1 = create_vertical_text(text1);
        lv_label_set_text(label_left, v_text1);
        free(v_text1);
    }
    if (text2 && label_right) {
        char* v_text2 = create_vertical_text(text2);
        lv_label_set_text(label_right, v_text2);
        free(v_text2);
    }
}

// 🎵 音频数据更新 - 驱动3D宇宙旋律动画
void sisi_ui_update_audio_data(uint8_t *data, uint8_t size) {
    if (!data) {
        ESP_LOGW(TAG, "⚠️ 音频数据为空");
        return;
    }

    // 🔧 不限制场景 - 音频数据随时可以更新
    size_t copy_size = (size < 8) ? size : 8;  // 🔧 修复：支持8个频段
    memcpy(audio_spectrum_data, data, copy_size);

    // 计算音频强度 - 使用8个频段
    int audio_intensity = (audio_spectrum_data[0] + audio_spectrum_data[1] + audio_spectrum_data[2] + audio_spectrum_data[3] +
                          audio_spectrum_data[4] + audio_spectrum_data[5] + audio_spectrum_data[6] + audio_spectrum_data[7]) / 8;

    ESP_LOGI(TAG, "🎵 音频数据更新: [%d, %d, %d, %d, %d, %d, %d, %d], 强度: %d, 当前场景: %d",
             (int)audio_spectrum_data[0], (int)audio_spectrum_data[1], (int)audio_spectrum_data[2], (int)audio_spectrum_data[3],
             (int)audio_spectrum_data[4], (int)audio_spectrum_data[5], (int)audio_spectrum_data[6], (int)audio_spectrum_data[7],
             (int)audio_intensity, (int)current_scene);

    // 🔧 防止重复场景切换 - 只在必要时切换
    if (current_scene != UI_SCENE_MUSIC_VIS && audio_intensity > 15) {  // 降低到15，更容易触发
        ESP_LOGI(TAG, "🌌 音频强度足够，自动切换到3D宇宙旋律动画场景");

        ui_data_t ui_data = {
            .audio_data = audio_spectrum_data,
            .audio_data_size = 4
        };

        sisi_ui_switch_scene(UI_SCENE_MUSIC_VIS, &ui_data);
        return;
    }

    // 🔧 如果已经在音乐场景，不重复切换
    if (current_scene == UI_SCENE_MUSIC_VIS) {
        ESP_LOGD(TAG, "🎵 已在音乐场景，更新音频数据");
        return;
    }

    // 🔧 强制刷新音频可视化显示
    if (spectrum_canvas && current_scene == UI_SCENE_MUSIC_VIS) {
        lv_obj_invalidate(spectrum_canvas);
        lv_refr_now(NULL);
    }
}

void sisi_ui_add_log(const char* log_text) {
    if (!log_text || current_scene != UI_SCENE_INTERACTIVE) return;

    // 🎥 重置空闲计时器 - 有新的日志活动
    sisi_ui_reset_idle_timer();

    // 滚动日志
    for (int i = LOG_LINE_COUNT - 1; i > 0; i--) {
        strcpy(log_buffer[i], log_buffer[i - 1]);
        if (log_labels[i]) {
            lv_label_set_text(log_labels[i], log_buffer[i]);
        }
    }

    // 添加新日志
    strncpy(log_buffer[0], log_text, sizeof(log_buffer[0]) - 1);
    log_buffer[0][sizeof(log_buffer[0]) - 1] = '\0';
    if (log_labels[0]) {
        lv_label_set_text(log_labels[0], log_buffer[0]);
    }
}

/* --------------------------------------------------
 * 临时桩函数：防止链接器报找不到任务入口。
 * 后续可替换为真实的导弹动画和可视化实现。
 * -------------------------------------------------- */
#ifndef SISI_UI_TASK_STUBS
#define SISI_UI_TASK_STUBS
// static void missile_animation_task(void* arg)
// {
//     /* TODO: 实现导弹动画。当前仅保持任务存活 10ms 然后删除自身，避免占用资源 */
//     vTaskDelay(pdMS_TO_TICKS(10));
//     vTaskDelete(NULL);
// }

#endif

// 预声明（已提前声明变量）
static void draw_page(int page_idx);

// 翻页定时器回调函数
static void page_timer_cb(lv_timer_t* timer) {
    if (total_pages <= 1) return;

    current_page = (current_page + 1) % total_pages;
    draw_page(current_page);
    ESP_LOGD(TAG, "📄 自动翻页到第%d页", current_page + 1);
}

// 显示单页（复用已有代码，但读取 page_text_buf）
static void draw_page(int page_idx){
    if(!page_cont || !page_text_buf) return;

    /* ⚠️ 注意：LVGL 任务栈仅 4 KB，原先在栈上分配 8 KB+ 的二维数组会导致栈溢出 → Guru Meditation。
     * 此处改为 **堆分配**，用完立即释放，避免破坏 SPI/LVGL 运行环境。
     */
    char (*lines)[16] = (char (*)[16])malloc(sizeof(char)*16*512); // 512 行 × 16 字节
    if(!lines){
        ESP_LOGE("SISI_UI", "❌ 内存不足，无法分页显示");
        return;
    }

    int line_cnt = 0;
    const char* p = page_text_buf;
    while(*p){
        int l = utf8_next_len(p);
        if(l > 0 && l < 16) {
            strncpy(lines[line_cnt], p, l);
            lines[line_cnt][l] = '\0';
            line_cnt++;
            p += l;
        } else {
            p++;
        }
        if(line_cnt >= 500) break;
    }

    int page_size = lines_per_page;
    int start     = page_idx * page_size;
    if(start >= line_cnt) start = 0;

    char col_left[512]  = "";
    char col_right[512] = "";
    int  lines_per_col  = lines_per_page / 2;

    for(int i = 0; i < page_size && (start + i) < line_cnt; i++){
        strcat((i < lines_per_col) ? col_left : col_right, lines[start + i]);
        strcat((i < lines_per_col) ? col_left : col_right, "\n");
    }

    /* --- 更新标签文本 --- */
    lv_obj_t* l = lv_obj_get_child(page_cont, 0);
    lv_obj_t* r = lv_obj_get_child(page_cont, 1);
    lv_label_set_text(l, col_left);
    lv_label_set_text(r, col_right);

    /* --- 根据右列内容显/隐对象，防止空列留白 --- */
    if(strlen(col_right)==0){
        /* 只有一列：隐藏右列，并让左列充满宽度且文字居中 */
        lv_obj_add_flag(r, LV_OBJ_FLAG_HIDDEN);

        lv_obj_set_width(l, g_container_width_px);                 // 占满容器宽度
        lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, 0); // 文字水平居中
    } else {
        /* 两列：左右各固定宽度，文本水平居中 */
        lv_obj_clear_flag(r, LV_OBJ_FLAG_HIDDEN);

        lv_obj_set_width(l, g_column_width_px);
        lv_obj_set_width(r, g_column_width_px);
        lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_set_style_text_align(r, LV_TEXT_ALIGN_CENTER, 0);
    }

    /* 释放临时行缓冲区，避免 PSRAM 泄漏 */
    free(lines);
}

static void show_vertical_pages_cycle(const char* sisi_text){
    // 释放上一次内存
    if(page_text_buf){free((void*)page_text_buf); page_text_buf=NULL;}
    if(page_timer){lv_timer_del(page_timer); page_timer=NULL;}
    if(page_cont){lv_obj_del(page_cont); page_cont=NULL;}

    // 保存文本副本
    page_text_buf = strdup(sisi_text);

    /* ---------------- 使用固定目标行数 ---------------- */
    int base_line_height = lv_font_get_line_height(&font_puhui_30_4);
    if(base_line_height<=0) base_line_height = DEFAULT_CHAR_HEIGHT_PX;

    int actual_line_height = (base_line_height * CHAR_ZOOM) / 256;  // 缩放后真实行高 (现为 base_line_height)
    lines_per_page = TARGET_LINES_PER_COL * 2;  // 固定每列 7 行

    /* ---------- 动态计算列宽/间距 ---------- */
    g_column_width_px   = base_line_height + 4;   // 字符宽度加微量留白
    g_column_gap_px     = base_line_height / 2;   // 约半个字宽
    g_container_width_px = g_column_width_px * 2 + g_column_gap_px;

    /* 精确统计 UTF-8 字符数（逐字符步进，不依赖 lv_txt 内部 API） */
    int total_lines = 0;
    const char* p_cnt = sisi_text;
    while(*p_cnt){
        total_lines++;
        p_cnt += utf8_next_len(p_cnt);
    }
    ESP_LOGI("SISI_UI", "📄 分页计算: lines_per_page=%d (每列%d行), total_lines=%d, 行高=%d", lines_per_page, TARGET_LINES_PER_COL, total_lines, actual_line_height);
    /* -------------------------------------------- */
    total_pages = (total_lines + lines_per_page -1)/lines_per_page;

    // 🔧 修复：使用screen_container作为父容器，确保172x320约束
    lv_obj_t* parent = screen_container ? screen_container : lv_screen_active();
    page_cont = lv_obj_create(parent);
    // --- 样式：无背景、无边框、无内边距 ---
    lv_obj_set_style_bg_opa(page_cont, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(page_cont, 0, 0);
    lv_obj_set_style_pad_all(page_cont, 0, 0);
    
    // 🔧 修复：使用LVGL v9 API关闭滚动条，而不是设置宽度
    lv_obj_set_scrollbar_mode(page_cont, LV_SCROLLBAR_MODE_OFF);

    lv_obj_set_flex_flow(page_cont, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(page_cont, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    // 强制清除Flex布局的行列间距
    lv_obj_set_style_pad_row(page_cont, 0, 0);
    lv_obj_set_style_pad_column(page_cont, g_column_gap_px, 0);   // 运行时列间距
    // 🔧 设置容器宽度为动态计算值，使列整体居中
    lv_obj_set_size(page_cont, g_container_width_px, 320);

    for(int i=0;i<2;i++){
        lv_obj_t* lab = lv_label_create(page_cont);
        lv_obj_set_style_text_font(lab, &font_puhui_30_4, 0);
        lv_obj_set_style_transform_zoom(lab, CHAR_ZOOM, 0);  // 保持原始大小

        // 标签样式：纯白字体、透明背景、无边框
        lv_obj_set_style_text_color(lab, lv_color_white(), 0);
        lv_obj_set_style_bg_opa(lab, LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_width(lab, 0, 0);
        // 关闭标签可能出现的滚动条
        lv_obj_clear_flag(lab, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_scrollbar_mode(lab, LV_SCROLLBAR_MODE_OFF);
        // 🔧 修复：给标签最大可能的宽度，确保30号字体完整显示
        lv_obj_set_width(lab, g_column_width_px);
        lv_label_set_long_mode(lab, LV_LABEL_LONG_WRAP);  // 改为换行模式，不裁剪
        lv_label_set_text(lab, "");
    }

    /* ---------- 容器定位 ---------- */
    // 🔧 修复：容器已经是全屏尺寸，直接放在屏幕中央，让内容在容器内部居中
    lv_obj_align(page_cont, LV_ALIGN_CENTER, 0, 0);

    // 🔧 调试信息
    ESP_LOGI("SISI_UI", "🔍 容器布局: 总行数=%d, 实际行高=%d, 容器宽度=%d",
             lines_per_page, actual_line_height, g_container_width_px);

    current_page = 0;
    draw_page(0);
    // 🔧 **恢复自动翻页**：多页文字自动翻页显示
    if(total_pages>1){
        page_timer = lv_timer_create(page_timer_cb, PAGE_INTERVAL_MS, NULL);
        ESP_LOGI(TAG, "📝 文字显示完成，共%d页，启动自动翻页", total_pages);
    } else {
        ESP_LOGI(TAG, "📝 文字显示完成，共%d页，持续显示", total_pages);
    }
}

// 前向声明
static void image_delete_timer_cb(lv_timer_t* timer);

// 📺 图片显示API - ESP-BSP原理适配竖屏 (智能格式检测)
void sisi_ui_display_image(const lv_image_dsc_t* img_dsc) {
    if (!img_dsc || !img_dsc->data || img_dsc->data_size == 0) {
        ESP_LOGE(TAG, "❌ 图片数据无效");
        return;
    }

    ESP_LOGI(TAG, "📺 开始智能图片显示: %u bytes", (unsigned int)img_dsc->data_size);

    // 🔍 智能检测格式：JPEG vs RGB565
    const uint8_t* data = img_dsc->data;
    bool is_jpeg = (img_dsc->data_size >= 2 && data[0] == 0xFF && data[1] == 0xD8);

    uint8_t* rgb_source_buffer = NULL;
    int img_width, img_height;

    if (is_jpeg) {
        ESP_LOGI(TAG, "🔍 检测到JPEG格式，需要解码");

        // 🔧 分配解码缓冲区 - 使用PSRAM (ESP32-S3支持PSRAM DMA)
        const size_t decode_size = 1280 * 720 * 2;
        rgb_source_buffer = heap_caps_calloc(decode_size, 1, MALLOC_CAP_SPIRAM);
        if (!rgb_source_buffer) {
            ESP_LOGE(TAG, "❌ 解码缓冲区分配失败: %d bytes", decode_size);
            free((void*)img_dsc->data);
            return;
        }

        // JPEG解码到RGB565
        esp_jpeg_image_cfg_t jpeg_cfg = {
            .indata = (uint8_t*)img_dsc->data,
            .indata_size = img_dsc->data_size,
            .outbuf = rgb_source_buffer,
            .outbuf_size = decode_size,
            .out_format = JPEG_IMAGE_FORMAT_RGB565,
            .out_scale = JPEG_IMAGE_SCALE_0,
            .flags = {
#if CONFIG_LV_COLOR_16_SWAP
                .swap_color_bytes = 1
#else
                .swap_color_bytes = 0
#endif
            }
        };

        esp_jpeg_image_output_t outimg;

        // 重置看门狗，防止JPEG解码超时
        esp_task_wdt_reset();

        esp_err_t ret = esp_jpeg_decode(&jpeg_cfg, &outimg);

        // 解码完成后再次重置看门狗
        esp_task_wdt_reset();

        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "❌ JPEG解码失败: %s", esp_err_to_name(ret));
            free(rgb_source_buffer);
            free((void*)img_dsc->data);
            return;
        }

        img_width = outimg.width;
        img_height = outimg.height;
        ESP_LOGI(TAG, "✅ JPEG解码成功: %dx%d", img_width, img_height);

    } else {
        ESP_LOGI(TAG, "🔍 检测到RGB565格式，ESP-BSP原理直接处理");

        // 🔧 根据数据大小推断分辨率
        if (img_dsc->data_size == 640 * 480 * 2) {
            img_width = 640; img_height = 480;
        } else if (img_dsc->data_size == 320 * 240 * 2) {
            img_width = 320; img_height = 240;
        } else {
            ESP_LOGE(TAG, "❌ 不支持的RGB565尺寸: %u bytes", (unsigned int)img_dsc->data_size);
            free((void*)img_dsc->data);
            return;
        }

        // ESP-BSP原理：直接使用原始数据
        rgb_source_buffer = (uint8_t*)img_dsc->data;
    }

    // 🔧 精确修改：分配能装下640×480图片的缓冲区
    const size_t display_buffer_size = img_width * img_height * 2;  // 640×480×2 = 614,400 bytes

    uint8_t* display_buffer = heap_caps_calloc(display_buffer_size, 1, MALLOC_CAP_DEFAULT);
    if (!display_buffer) {
        ESP_LOGE(TAG, "❌ 显示缓冲区分配失败: %d bytes (%dx%d)", display_buffer_size, img_width, img_height);
        if (is_jpeg) free(rgb_source_buffer);
        free((void*)img_dsc->data);
        return;
    }
    ESP_LOGI(TAG, "✅ 原图尺寸缓冲区分配成功: %d bytes (%dx%d)", display_buffer_size, img_width, img_height);

    // 🔧 ESP-BSP官方原理：JPEG解码到原图尺寸缓冲区
    ESP_LOGI(TAG, "🔄 JPEG解码1/4缩放: %dx%d -> %dx%d", img_width, img_height, img_width/4, img_height/4);

    // 配置JPEG解码器，1/4缩放输出 (640×480 → 160×120)
    esp_jpeg_image_cfg_t jpeg_cfg = {
        .indata = (uint8_t*)img_dsc->data,
        .indata_size = img_dsc->data_size,
        .outbuf = display_buffer,
        .outbuf_size = display_buffer_size,
        .out_format = JPEG_IMAGE_FORMAT_RGB565,
        .out_scale = JPEG_IMAGE_SCALE_1_4,  // 1/4缩放
        .flags = {
            .swap_color_bytes = 0,  // ST7789颜色修复：不交换字节
        }
    };

    esp_jpeg_image_output_t outimg;

    // 重置看门狗，防止第二次JPEG解码超时
    esp_task_wdt_reset();

    esp_err_t decode_ret = esp_jpeg_decode(&jpeg_cfg, &outimg);

    // 解码完成后再次重置看门狗
    esp_task_wdt_reset();

    if (decode_ret != ESP_OK) {
        ESP_LOGE(TAG, "❌ JPEG解码失败: %s", esp_err_to_name(decode_ret));
        free(display_buffer);
        free(rgb_source_buffer);
        return;
    }

    ESP_LOGI(TAG, "✅ JPEG 1/4缩放解码成功: %dx%d", outimg.width, outimg.height);

    // 🔧 注意：你的显示屏已配置BGR+swap_bytes，无需额外字节交换

    // 释放临时缓冲区
    if (is_jpeg) {
        free(rgb_source_buffer);
    }

    // 🔧 ESP-BSP原理：线程安全Canvas操作
    LV_PORT_LOCK(100);

    // 🔧 ESP-BSP原理：清理旧Canvas（如果存在）
    if (image_canvas && lv_obj_is_valid(image_canvas)) {
        lv_obj_del(image_canvas);
        image_canvas = NULL;
        ESP_LOGI(TAG, "🖼️ 旧图片Canvas已删除");
    }

    // 🔧 ESP-BSP原理：在屏幕顶层创建Canvas，不受场景切换影响
    image_canvas = lv_canvas_create(lv_scr_act());
    if (!image_canvas) {
        ESP_LOGE(TAG, "❌ Canvas创建失败");
        LV_PORT_UNLOCK();
        free(display_buffer);
        free((void*)img_dsc->data);
        return;
    }

    // 🔧 ESP-BSP官方API：用解码后的实际尺寸设置Canvas
    lv_canvas_set_buffer(image_canvas, display_buffer, outimg.width, outimg.height, LV_COLOR_FORMAT_RGB565);

    // 🔧 ST7789颜色处理：BGR + 颜色反转适配
    // 你的显示屏配置：LCD_RGB_ENDIAN_BGR + invert_color = true
    // 需要特殊的颜色处理，不完全遵循ESP-BSP

    // 🔧 ESP-BSP标准设置：居中显示原图
    lv_obj_center(image_canvas);  // ESP-BSP标准API
    lv_obj_invalidate(image_canvas);  // 关键！强制刷新
    lv_obj_move_foreground(image_canvas);

    ESP_LOGI(TAG, "🔧 ESP-BSP Canvas设置: %dx%d, 居中显示", outimg.width, outimg.height);

    // 🔧 刷新显示 + 颜色验证 (LVGL标准API)
    lv_obj_invalidate(image_canvas);  // 标准刷新API

    // 🔍 颜色验证：检查前几个像素
    uint16_t* pixels = (uint16_t*)display_buffer;
    ESP_LOGI(TAG, "🎨 颜色验证: 前3像素 = 0x%04X, 0x%04X, 0x%04X",
             pixels[0], pixels[1], pixels[2]);
    ESP_LOGI(TAG, "✅ 竖屏Canvas刷新完成 (172×320)");
    ESP_LOGI(TAG, "✅ Canvas刷新完成");

    LV_PORT_UNLOCK();

    ESP_LOGI(TAG, "✅ ESP-BSP 1/4缩放显示成功: %dx%d", outimg.width, outimg.height);
    ESP_LOGI(TAG, "🖼️ 图片将在3秒后自动删除");

    // 释放原始数据
    free((void*)img_dsc->data);

    // 🔧 3秒后删除图片 (快速显示)
    lv_timer_create(image_delete_timer_cb, 3000, image_canvas);
}



// 🔧 修复：图片删除定时器回调函数，同时释放图片数据
static void image_delete_timer_cb(lv_timer_t* timer) {
    lv_obj_t* canvas = (lv_obj_t*)lv_timer_get_user_data(timer);
    if (canvas && lv_obj_is_valid(canvas)) {
        lv_obj_del(canvas);
        ESP_LOGI(TAG, "✅ 图片Canvas已删除");
    }

    // 删除定时器
    lv_timer_del(timer);
}

/**
 * 视频播放器事件回调
 */
static void video_event_callback(video_event_t event, void* user_data)
{
    switch (event) {
        case VIDEO_EVENT_STARTED:
            ESP_LOGI(TAG, "🎬 视频播放开始");
            break;
        case VIDEO_EVENT_FRAME_DECODED:
            ESP_LOGD(TAG, "🖼️ 视频帧解码完成");
            break;
        case VIDEO_EVENT_STOPPED:
            ESP_LOGI(TAG, "⏹️ 视频播放停止");
            break;
        case VIDEO_EVENT_ERROR:
            ESP_LOGE(TAG, "❌ 视频播放错误");
            break;
        case VIDEO_EVENT_NETWORK_CONNECTED:
            ESP_LOGI(TAG, "🌐 网络连接成功");
            break;
        case VIDEO_EVENT_NETWORK_DISCONNECTED:
            ESP_LOGW(TAG, "🌐 网络连接断开");
            break;
    }
}

// 🎥 视频播放器基础测试
esp_err_t sisi_ui_test_video_player(void)
{
    ESP_LOGI(TAG, "🧪 开始测试视频播放器基础功能...");

    // 确保屏幕对象有效
    lv_obj_t *screen = lv_screen_active();
    if (!screen) {
        ESP_LOGE(TAG, "❌ 无法获取活动屏幕对象");
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "✅ 活动屏幕对象: %p", screen);

    // 初始化视频播放器
    esp_err_t ret = video_player_init(screen, video_event_callback, NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "❌ 视频播放器初始化失败: %s", esp_err_to_name(ret));
        return ret;
    }

    // 显示视频Canvas
    video_player_set_visible(true);

    ESP_LOGI(TAG, "✅ 视频播放器基础测试完成");
    ESP_LOGI(TAG, "📺 Canvas已显示，可以调用其他测试函数");

    return ESP_OK;
}

// 🎥 测试文件播放
esp_err_t sisi_ui_test_video_file(const char* file_path)
{
    if (!file_path) {
        file_path = "/spiffs/test.mjp";  // 默认测试文件
    }

    ESP_LOGI(TAG, "🧪 测试MJPEG文件播放: %s", file_path);

    esp_err_t ret = video_player_play_file(file_path);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "❌ 文件播放启动失败: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "✅ 文件播放测试启动成功");
    return ESP_OK;
}

// 🎥 测试网络流接收
esp_err_t sisi_ui_test_video_stream(const char* stream_url)
{
    if (!stream_url) {
        stream_url = "http://192.168.1.100:8080/video";  // 默认测试URL
    }

    ESP_LOGI(TAG, "🧪 测试网络MJPEG流: %s", stream_url);

    esp_err_t ret = video_player_start_stream(stream_url);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "❌ 网络流启动失败: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "✅ 网络流测试启动成功");
    return ESP_OK;
}

// 🎥 测试单帧显示
esp_err_t sisi_ui_test_video_frame(void)
{
    ESP_LOGI(TAG, "🧪 测试单帧JPEG显示...");

    // 创建一个最小的测试JPEG (黑色图像)
    const uint8_t test_jpeg[] = {
        0xFF, 0xD8,  // SOI
        0xFF, 0xE0,  // APP0
        0x00, 0x10,  // Length
        0x4A, 0x46, 0x49, 0x46, 0x00,  // "JFIF"
        0x01, 0x01,  // Version
        0x01,        // Units
        0x00, 0x48,  // X density
        0x00, 0x48,  // Y density
        0x00, 0x00,  // Thumbnail
        0xFF, 0xD9   // EOI
    };

    esp_err_t ret = video_player_update_frame(test_jpeg, sizeof(test_jpeg));
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "❌ 单帧显示失败: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "✅ 单帧显示测试完成");
    return ESP_OK;
}

/**
 * 空闲定时器回调 - 启动空闲视频播放
 */
static void idle_timer_callback(TimerHandle_t xTimer)
{
    ESP_LOGI(TAG, "⏰ [DEBUG] 空闲定时器触发，当前场景: %d", (int)current_scene);

    // 🔧 修复：有数据时不启动视频，无数据时启动视频
    if (current_scene == UI_SCENE_MUSIC_VIS) {
        ESP_LOGI(TAG, "⏰ [DEBUG] 当前在动画场景，跳过空闲视频启动");
        return;
    }

    ESP_LOGI(TAG, "⏰ [DEBUG] 空闲超时，开始播放空闲视频: %s", idle_video_path);

    // 🔧 修复：使用screen_container作为视频父对象，避免层级冲突
    lv_obj_t *video_parent = screen_container ? screen_container : lv_screen_active();
    esp_err_t ret = video_player_init(video_parent, video_event_callback, NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "❌ 视频播放器初始化失败: %s", esp_err_to_name(ret));
        return;
    }
    video_player_initialized = true;

    // 停止当前播放（如果有）
    video_player_stop();
    vTaskDelay(pdMS_TO_TICKS(100));

    // 开始播放空闲视频
    ret = video_player_play_file(idle_video_path);
    if (ret == ESP_OK) {
        idle_video_playing = true;
        video_player_set_visible(true);
        ESP_LOGI(TAG, "🎬 空闲视频播放开始");
    } else {
        ESP_LOGE(TAG, "❌ 空闲视频播放失败: %s", esp_err_to_name(ret));
    }
}

/**
 * 启动空闲视频播放系统
 */
esp_err_t sisi_ui_start_idle_video(const char* video_file_path)
{
    if (video_file_path) {
        strncpy(idle_video_path, video_file_path, sizeof(idle_video_path) - 1);
        idle_video_path[sizeof(idle_video_path) - 1] = '\0';
    }

    ESP_LOGI(TAG, "🎥 启动空闲视频系统: %s", idle_video_path);

    // 创建空闲定时器
    if (idle_timer == NULL) {
        idle_timer = xTimerCreate("idle_timer",
                                 pdMS_TO_TICKS(IDLE_TIMEOUT_MS),
                                 pdFALSE,  // 单次触发
                                 NULL,
                                 idle_timer_callback);

        if (idle_timer == NULL) {
            ESP_LOGE(TAG, "❌ 空闲定时器创建失败");
            return ESP_FAIL;
        }
    }

    // 启动定时器
    xTimerStart(idle_timer, 0);

    ESP_LOGI(TAG, "✅ 空闲视频系统启动成功，%d秒后开始播放", IDLE_TIMEOUT_MS / 1000);
    return ESP_OK;
}

/**
 * 停止空闲视频播放
 */
esp_err_t sisi_ui_stop_idle_video(void)
{
    ESP_LOGI(TAG, "⏹️ 停止空闲视频播放");

    // 停止定时器
    if (idle_timer) {
        xTimerStop(idle_timer, 0);
    }

    // 停止视频播放
    if (idle_video_playing) {
        video_player_stop();
        video_player_set_visible(false);
        idle_video_playing = false;
        ESP_LOGI(TAG, "✅ 空闲视频已停止");
    }

    return ESP_OK;
}

/**
 * 重置空闲计时器 - 有活动时调用
 */
void sisi_ui_reset_idle_timer(void)
{
    // 如果正在播放空闲视频，先停止
    if (idle_video_playing) {
        sisi_ui_stop_idle_video();
    }

    // 重新启动定时器
    if (idle_timer) {
        xTimerReset(idle_timer, 0);
        ESP_LOGD(TAG, "🔄 空闲计时器已重置");
    }
}