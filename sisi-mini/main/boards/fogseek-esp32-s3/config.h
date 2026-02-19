#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

// Buttons (FogSeek supplier pinout)
#define BOOT_BUTTON_GPIO GPIO_NUM_0
#define CTRL_BUTTON_GPIO GPIO_NUM_8

// Power/charging (FogSeek supplier pinout)
#define PWR_HOLD_GPIO GPIO_NUM_18
#define PWR_CHARGE_DONE_GPIO GPIO_NUM_9
#define PWR_CHARGING_GPIO GPIO_NUM_46
#define BATTERY_ADC_GPIO GPIO_NUM_3


#define AUDIO_INPUT_SAMPLE_RATE  16000
#define AUDIO_OUTPUT_SAMPLE_RATE 16000
// A/B debug switch:
// false = disable reference channel (disable device AEC path) to verify
// whether current stutter comes from invalid/mismatched reference wiring.
#define AUDIO_INPUT_REFERENCE    false

// 麦克风输入（根据引脚图）
#define AUDIO_I2S_MIC_GPIO_DIN  GPIO_NUM_2

// 扬声器输出（根据引脚图）
#define AUDIO_I2S_SPK_GPIO_DOUT GPIO_NUM_1
#define AUDIO_I2S_SPK_GPIO_BCLK GPIO_NUM_39
#define AUDIO_I2S_SPK_GPIO_LRCK GPIO_NUM_38

// LED指示灯（根据引脚图确认）
// FogSeek板使用普通LED，不是WS2812
#define BUILTIN_LED_GPIO        GPIO_NUM_16
#define BUILTIN_LED2_GPIO       GPIO_NUM_17

// 电源管理（关键！）
#define POWER_CONTROL_GPIO      GPIO_NUM_18

// 电池电量检测
#define ADC_IN_GPIO             GPIO_NUM_3

// USB（原生USB，无需修改）
// GPIO19 = USB_DM
// GPIO20 = USB_DP

// 串口调试（无需修改）
// GPIO1  = U0RXD
// GPIO46 = U0TXD

// 按键配置（FogSeek板特殊设计）
// 开关按键（POWER_BTN）可飞线到GPIO3用于检测双击重启
// #define POWER_BUTTON_GPIO       GPIO_NUM_3  // 可选：飞线连接POWER_BTN检测双击
// 注意：无BOOT键（原生USB自动下载）
// 注意：无音量键（通过语音/网络控制）

#endif // _BOARD_CONFIG_H_
