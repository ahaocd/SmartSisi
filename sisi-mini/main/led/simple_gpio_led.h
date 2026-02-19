#ifndef SIMPLE_GPIO_LED_H_
#define SIMPLE_GPIO_LED_H_

#include "led.h"
#include <driver/gpio.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/timers.h>

// 简单GPIO LED类（用于普通LED，不是WS2812）
class SimpleGpioLed : public Led {
public:
    SimpleGpioLed(gpio_num_t gpio);
    ~SimpleGpioLed();

    void SetColor(uint8_t r, uint8_t g, uint8_t b);
    void TurnOn();
    void TurnOff();
    void BlinkOnce();
    void Blink(int times, int interval_ms);
    void StartContinuousBlink(int interval_ms);
    void StartBreathingEffect();  // 快速闪烁效果（AI说话时）
    virtual void OnStateChanged() override;

private:
    gpio_num_t gpio_;
    bool is_on_;
    TimerHandle_t blink_timer_;
    int blink_count_;
    bool blink_state_;
    
    static void BlinkTimerCallback(TimerHandle_t timer);
};

#endif // SIMPLE_GPIO_LED_H_
