#include "simple_gpio_led.h"
#include "application.h"
#include <esp_log.h>

#define TAG "SimpleGpioLed"

SimpleGpioLed::SimpleGpioLed(gpio_num_t gpio)
    : gpio_(gpio), is_on_(false), blink_count_(0), blink_state_(false) {
    // 配置GPIO为输出
    gpio_config_t io_conf = {};
    io_conf.intr_type = GPIO_INTR_DISABLE;
    io_conf.mode = GPIO_MODE_OUTPUT;
    io_conf.pin_bit_mask = (1ULL << gpio);
    io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
    gpio_config(&io_conf);
    
    // 初始化为关闭
    gpio_set_level(gpio_, 0);
    
    // 创建闪烁定时器
    blink_timer_ = xTimerCreate("led_blink", pdMS_TO_TICKS(100), pdTRUE, this, BlinkTimerCallback);
    
    ESP_LOGI(TAG, "Simple GPIO LED initialized on GPIO%d", gpio);
}

SimpleGpioLed::~SimpleGpioLed() {
    if (blink_timer_) {
        xTimerDelete(blink_timer_, 0);
    }
    gpio_set_level(gpio_, 0);
}

void SimpleGpioLed::SetColor(uint8_t r, uint8_t g, uint8_t b) {
    // 普通LED忽略颜色，只要RGB任意一个>0就认为是亮
    is_on_ = (r > 0 || g > 0 || b > 0);
}

void SimpleGpioLed::TurnOn() {
    xTimerStop(blink_timer_, 0);
    gpio_set_level(gpio_, 1);
    ESP_LOGI(TAG, "GPIO%d LED ON", gpio_);
}

void SimpleGpioLed::TurnOff() {
    xTimerStop(blink_timer_, 0);
    gpio_set_level(gpio_, 0);
    ESP_LOGI(TAG, "GPIO%d LED OFF", gpio_);
}

void SimpleGpioLed::BlinkOnce() {
    Blink(1, 100);
}

void SimpleGpioLed::Blink(int times, int interval_ms) {
    blink_count_ = times * 2;  // 每次闪烁包含亮和灭
    xTimerChangePeriod(blink_timer_, pdMS_TO_TICKS(interval_ms), 0);
    xTimerStart(blink_timer_, 0);
    ESP_LOGI(TAG, "GPIO%d LED Blink %d times, interval %dms", gpio_, times, interval_ms);
}

void SimpleGpioLed::StartContinuousBlink(int interval_ms) {
    blink_count_ = -1;  // -1表示无限闪烁
    xTimerChangePeriod(blink_timer_, pdMS_TO_TICKS(interval_ms), 0);
    xTimerStart(blink_timer_, 0);
    ESP_LOGI(TAG, "GPIO%d LED Continuous Blink, interval %dms", gpio_, interval_ms);
}

void SimpleGpioLed::StartBreathingEffect() {
    blink_count_ = -1;  // 无限循环
    xTimerChangePeriod(blink_timer_, pdMS_TO_TICKS(50), 0);  // 50ms快速闪烁
    xTimerStart(blink_timer_, 0);
    ESP_LOGI(TAG, "GPIO%d LED Fast Blink started (50ms interval)", gpio_);
}

void SimpleGpioLed::BlinkTimerCallback(TimerHandle_t timer) {
    auto* led = static_cast<SimpleGpioLed*>(pvTimerGetTimerID(timer));
    
    // 普通闪烁模式：完全开关
    led->blink_state_ = !led->blink_state_;
    gpio_set_level(led->gpio_, led->blink_state_ ? 1 : 0);
    
    // 如果不是无限闪烁，减少计数
    if (led->blink_count_ > 0) {
        led->blink_count_--;
        if (led->blink_count_ == 0) {
            xTimerStop(timer, 0);
            gpio_set_level(led->gpio_, 0);  // 停止时关闭LED
        }
    }
}

void SimpleGpioLed::OnStateChanged() {
    auto& app = Application::GetInstance();
    auto device_state = app.GetDeviceState();
    
    ESP_LOGI(TAG, "State changed: %d", device_state);
    
    switch (device_state) {
        case kDeviceStateStarting:
            StartContinuousBlink(200);  // 中速闪 - 开机启动
            break;
        case kDeviceStateWifiConfiguring:
            StartContinuousBlink(500);  // 慢闪 - WiFi配网
            break;
        case kDeviceStateIdle:
            TurnOff();  // 灭 - 待机
            break;
        case kDeviceStateConnecting:
            StartContinuousBlink(100);  // 快闪 - 连接WiFi/服务器
            break;
        case kDeviceStateListening:
            TurnOn();  // 常亮 - 等待说话/检测到说话
            break;
        case kDeviceStateSpeaking:
            StartBreathingEffect();  // 呼吸效果 - AI说话（快速在微弱和全亮之间切换）
            break;
        case kDeviceStateUpgrading:
            StartContinuousBlink(50);  // 超快闪 - 固件升级
            break;
        case kDeviceStateActivating:
            StartContinuousBlink(400);  // 很慢闪 - 激活中
            break;
        default:
            ESP_LOGW(TAG, "Unknown state: %d", device_state);
            break;
    }
}
