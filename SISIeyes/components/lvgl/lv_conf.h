/* Minimal LVGL configuration for SISIeyes --------------------------------*/
#pragma once

/*-----------------
 * OS SETTINGS
 *----------------*/
/* 🔧 启用FreeRTOS支持，提供lv_lock/lv_unlock线程安全机制 */
#define LV_USE_OS               LV_OS_FREERTOS
#define LV_USE_FREERTOS_TASK_NOTIFY 1

/*-----------------
 * MEMORY SETTINGS
 *----------------*/
/* 🔧 修复：使用ESP32-S3统一内存管理器，解决PSRAM兼容性问题 */
#define LV_USE_STDLIB_MALLOC    LV_STDLIB_CLIB  /* 使用标准C库malloc */
#define LV_USE_STDLIB_STRING    LV_STDLIB_CLIB  /* 使用标准C库字符串函数 */
#define LV_USE_STDLIB_SPRINTF   LV_STDLIB_CLIB  /* 使用标准C库sprintf */

/*-----------------
 * COLOR SETTINGS
 *----------------*/
#define LV_COLOR_DEPTH          16      /*RGB565*/
#define LV_COLOR_16_SWAP        1       /*🔧 照抄ESP官方：Swap bytes to match ST7789 (BGR)*/

/*-----------------
 * 🔧 照抄ESP官方BSP配置
 *----------------*/
#define LV_USE_PERF_MONITOR     1       /* 性能监控 */
#define LV_MEMCPY_MEMSET_STD    1       /* 使用标准memcpy */
#define LV_USE_CLIB_MALLOC      1       /* 使用标准malloc */
#define LV_USE_CLIB_SPRINTF     1       /* 使用标准sprintf */
#define LV_USE_CLIB_STRING      1       /* 使用标准string */

/*-----------------
 * 🔧 启用Canvas和绘图功能
 *----------------*/
#define LV_USE_CANVAS           1       /* 启用Canvas */
#define LV_USE_DRAW_SW          1       /* 启用软件绘图 */

/*-----------------
 * 🔧 启用图片解码器
 *----------------*/
#define LV_USE_IMG              1       /* 启用图片支持 */
#define LV_IMG_CACHE_DEF_SIZE   1       /* 图片缓存大小 */

/*-----------------
 * TEXT SETTINGS
 *----------------*/
/* Select a character encoding for strings.
 * Your IDE or editor should have the same character encoding
 * - LV_TXT_ENC_UTF8
 * - LV_TXT_ENC_ASCII
 */
#define LV_TXT_ENC LV_TXT_ENC_UTF8

/*-----------------
 * FONT SETTINGS
 *----------------*/
#define LV_USE_FONT_MONTSERRAT  1
#define LV_FONT_MONTSERRAT_14   1
#define LV_FONT_MONTSERRAT_16   0
#define LV_FONT_MONTSERRAT_18   0
#define LV_FONT_MONTSERRAT_20   0
#define LV_FONT_MONTSERRAT_38   0       /* 关闭 38pt 内置英文字体，节省 Flash */
#define LV_FONT_MONTSERRAT_48   0       /* 关闭 48pt 内置英文字体，节省 Flash */
#define LV_FONT_DEFAULT         &lv_font_montserrat_14   /* 使用内置14px字体，避免链接错误 */
#define LV_FONT_FMT_TXT_LARGE   1       /* 启用大字体支持 */
#define LV_FONT_SIMSUN_16_CJK   0       /* 关闭额外 SimSun 字库，避免重复 */

/* 关闭官方精简版 Source Han Sans，改用全量 38pt 字库 */
/* #define CONFIG_LV_FONT_SOURCE_HAN_SANS_SC_16_CJK 0 */
#define LV_FONT_SOURCE_HAN_SANS_SC_16_CJK 0

/* 
 * 🚀 新增：全量 38 号中文字体 (lv_font_chinese_38.c)
 * 使用前向声明（forward declaration）来避免在lv_conf.h中包含完整的LVGL头文件，
 * 这解决了 "unknown type name 'lv_font_t'" 的编译错误。
 */
struct _lv_font_t;
// extern struct _lv_font_t font_puhui_30_4;  // 删除自定义字体声明

/* ---------- 自定义字体表 ---------- */
/* #define LV_FONT_DEFAULT         (&lv_font_chinese_38)   // 已替换为中文字体 */
/* Emoji字体声明 */
// #define LV_FONT_CUSTOM_DECLARE LV_FONT_DECLARE(font_puhui_30_4)  // 删除自定义字体

/*-----------------
 * WIDGETS
 *----------------*/
#define LV_USE_CANVAS           1       /* 启用 Canvas 组件 */

/*-----------------
 * FILE SYSTEM
 *----------------*/
#define LV_USE_FS_STDIO         0       /* 禁用标准文件系统 */
#define LV_USE_FS_POSIX         0       /* 禁用POSIX文件系统 */
#define LV_USE_FS_WIN32         0       /* 禁用Win32文件系统 */
#define LV_USE_FS_FATFS         0       /* 禁用FATFS文件系统 */
#define LV_USE_FS_LITTLEFS      0       /* 禁用LittleFS文件系统 - 修复编译错误 */
#define LV_USE_FS_MEMFS         0       /* 禁用内存文件系统 */

/*-----------------
 * FFMPEG SUPPORT - ESP32不支持，改用JPEG序列
 *----------------*/
#define LV_USE_FFMPEG           0       /* 禁用FFMPEG - ESP32不支持 */

/*-----------------
 * JPEG DECODER SUPPORT - ESP32视频播放必需
 *----------------*/
#define LV_USE_TJPGD            1       /* 启用TJPGD JPEG解码器 - 视频播放必需 */
#define LV_USE_LIBJPEG_TURBO    0       /* 禁用libjpeg-turbo - ESP32不支持 */

/*-----------------
 * ANIMATION IMAGE SUPPORT - ESP32视频播放方式
 *----------------*/
#define LV_USE_ANIMIMG          1       /* 启用动画图像 - ESP32视频播放 */
#if LV_USE_FFMPEG
    #define LV_FFMPEG_DUMP_FORMAT       0
    #define LV_FFMPEG_PLAYER_USE_LV_FS  1   /* 使用LVGL文件系统 */
#endif

/*-----------------
 * DISPLAY DRIVERS
 *----------------*/
#define LV_USE_ST7789           0       /* 临时禁用ST7789驱动，避免编译冲突 */
#define LV_USE_GENERIC_MIPI     0

/*-----------------
 * DRAWING
 *----------------*/
#define LV_USE_DRAW_SW          1       /* 启用软件渲染 */
#define LV_USE_DRAW_SW_RECT     1       /* 启用矩形绘制 */
#define LV_DRAW_SW_DRAW_UNIT_CNT 1      /* 单线程绘制 */

/*-----------------
 * DEMO MODULES
 *----------------*/
#define LV_USE_DEMO            1
#define LV_USE_DEMO_WIDGETS    0        /* 禁用widgets演示 */

/*-----------------
 * EXAMPLE BUILD
 *----------------*/
/* 彻底关闭 LVGL 的示例源码编译，避免上千个 .c 文件拖慢编译 */
#ifndef LV_BUILD_EXAMPLES
#define LV_BUILD_EXAMPLES 0
#endif

/*-----------------
 * MISC SETTINGS
 *----------------*/
#define LV_USE_PERF_MONITOR     0
#define LV_COLOR_FORMAT_DEFAULT LV_COLOR_FORMAT_RGB565

/*-----------------
 * ASSERT SETTINGS
 *----------------*/
/* 🔧 启用调试断言 - 验证内存管理器修复效果 */
#include "esp_log.h"
#define LV_USE_ASSERT_NULL      1       /* 启用NULL检查 - 调试Canvas问题 */
#define LV_USE_ASSERT_MALLOC    1       /* 启用内存分配检查 - 调试spec_attr问题 */
#define LV_USE_ASSERT_STYLE     0       /* 禁用样式检查 */
#define LV_USE_ASSERT_MEM_INTEGRITY 1   /* 启用内存完整性检查 - 调试内存管理器 */
#define LV_USE_ASSERT_OBJ       1       /* 启用对象检查 - 调试Canvas创建 */
#define LV_ASSERT_HANDLER       do { ESP_LOGE("LVGL", "Assert triggered at %s:%d", __FILE__, __LINE__); abort(); } while(0);

/*-----------------
 * FONT RENDERING
 *----------------*/
#define LV_USE_FONT_COMPRESSED  1       /* 启用字体压缩 */
#define LV_USE_FONT_SUBPX       0       /* 禁用子像素渲染 */

/*==================
 * DEMO USAGE
 *=================*/

/*Show some widget.*/
#define LV_USE_DEMO_WIDGETS    0
#if LV_USE_DEMO_WIDGETS
    #define LV_DEMO_WIDGETS_SLIDESHOW 0
#endif

/*Demonstrate the usage of encoder and keyboard.*/
/**************************************************************************/

/*-----------------
 * PLATFORM / DRIVER SETTINGS
 *----------------*/
#define LV_USE_LINUX     0
#define LV_USE_WAYLAND   0
#define LV_USE_NUTTX     0
#define LV_USE_WIN32     0
#define LV_USE_SDL       0
#define LV_USE_PTHREAD   0
#define LV_USE_WMDRM     0
/* ESP-IDF 仅需 FreeRTOS 驱动 */

/*-----------------
 * MEMORY PLACEMENT FOR LARGE CONST (FONTS/IMAGES)
 *----------------*/
#undef LV_ATTRIBUTE_LARGE_CONST
#define LV_ATTRIBUTE_LARGE_CONST  __attribute__((section(".rodata"))) 

#ifndef LV_DRAW_SW_SHARP_ANTIALIAS
#define LV_DRAW_SW_SHARP_ANTIALIAS 1
#endif 