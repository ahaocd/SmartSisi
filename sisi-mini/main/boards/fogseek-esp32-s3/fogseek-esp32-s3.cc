#include "wifi_board.h"
#include "audio_codecs/no_audio_codec.h"
#include "display/display.h"
#include "system_reset.h"
#include "application.h"
#include "config.h"
#include "iot/thing_manager.h"
#include "led/simple_gpio_led.h"
#include "button.h"

#include <functional>

#include <wifi_station.h>
#include <driver/rtc_io.h>
#include <esp_sleep.h>
#include <esp_log.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <esp_adc/adc_oneshot.h>

#define TAG "FOGSEEK_ESP32_S3"

enum class FogSeekPowerState {
    USB_CHARGING,
    USB_DONE,
    USB_NO_BATTERY,
    BATTERY_POWER,
    LOW_BATTERY,
    NO_POWER,
};

class FogSeekPowerManagerLite {
public:
    using PowerStateCallback = std::function<void(FogSeekPowerState)>;

    void Initialize(gpio_num_t hold_gpio, gpio_num_t charging_gpio, gpio_num_t done_gpio, gpio_num_t adc_gpio) {
        hold_gpio_ = hold_gpio;
        charging_gpio_ = charging_gpio;
        done_gpio_ = done_gpio;
        adc_gpio_ = adc_gpio;

        gpio_config_t hold_conf = {};
        hold_conf.intr_type = GPIO_INTR_DISABLE;
        hold_conf.mode = GPIO_MODE_OUTPUT;
        hold_conf.pin_bit_mask = (1ULL << hold_gpio_);
        hold_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
        hold_conf.pull_up_en = GPIO_PULLUP_DISABLE;
        gpio_config(&hold_conf);
        gpio_set_level(hold_gpio_, 1);

        gpio_config_t charge_conf = {};
        charge_conf.intr_type = GPIO_INTR_DISABLE;
        charge_conf.mode = GPIO_MODE_INPUT;
        charge_conf.pin_bit_mask = (1ULL << charging_gpio_) | (1ULL << done_gpio_);
        charge_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
        charge_conf.pull_up_en = GPIO_PULLUP_ENABLE;
        gpio_config(&charge_conf);

        if (adc_gpio_ >= GPIO_NUM_1 && adc_gpio_ <= GPIO_NUM_10) {
            adc_channel_ = static_cast<adc_channel_t>(adc_gpio_ - 1);
            adc_oneshot_unit_init_cfg_t init_config = {
                .unit_id = ADC_UNIT_1,
                .ulp_mode = ADC_ULP_MODE_DISABLE,
            };
            if (adc_oneshot_new_unit(&init_config, &adc_handle_) == ESP_OK) {
                adc_oneshot_chan_cfg_t chan_config = {
                    .atten = ADC_ATTEN_DB_12,
                    .bitwidth = ADC_BITWIDTH_12,
                };
                adc_oneshot_config_channel(adc_handle_, adc_channel_, &chan_config);
            }
        }

        ESP_LOGI("FogSeekPower", "Pins: hold=%d charging=%d done=%d adc=%d",
                 (int)hold_gpio_, (int)charging_gpio_, (int)done_gpio_, (int)adc_gpio_);

        UpdatePowerState();
    }

    void Start() {
        if (timer_handle_ != nullptr) {
            return;
        }
        esp_timer_create_args_t timer_args = {};
        timer_args.callback = &FogSeekPowerManagerLite::TimerCallback;
        timer_args.arg = this;
        timer_args.name = "fogseek_power_state";
        esp_timer_create(&timer_args, &timer_handle_);
        esp_timer_start_periodic(timer_handle_, 5 * 1000 * 1000);
    }

    void SetCallback(PowerStateCallback cb) {
        callback_ = cb;
    }

    FogSeekPowerState GetPowerState() const { return power_state_; }

    uint8_t GetBatteryLevel() const { return battery_level_; }

    bool IsCharging() const {
        return power_state_ == FogSeekPowerState::USB_CHARGING;
    }

    bool IsDischarging() const {
        return power_state_ == FogSeekPowerState::BATTERY_POWER ||
               power_state_ == FogSeekPowerState::LOW_BATTERY;
    }

private:
    static void TimerCallback(void* arg) {
        auto self = static_cast<FogSeekPowerManagerLite*>(arg);
        self->UpdatePowerState();
    }

    void UpdatePowerState() {
        int adc_value = -1;
        if (adc_handle_ != nullptr) {
            if (adc_oneshot_read(adc_handle_, adc_channel_, &adc_value) == ESP_OK) {
                battery_level_ = MapBatteryLevel(adc_value);
            }
        }

        bool is_charging = gpio_get_level(charging_gpio_) == 0;
        bool is_done = gpio_get_level(done_gpio_) == 0;
        bool battery_present = battery_level_ > 5;

        FogSeekPowerState new_state = power_state_;
        if (is_charging) {
            new_state = FogSeekPowerState::USB_CHARGING;
        } else if (is_done) {
            new_state = FogSeekPowerState::USB_DONE;
        } else if (!battery_present && (is_charging || is_done)) {
            new_state = FogSeekPowerState::USB_NO_BATTERY;
        } else if (battery_present) {
            new_state = (battery_level_ <= 15) ? FogSeekPowerState::LOW_BATTERY
                                               : FogSeekPowerState::BATTERY_POWER;
        } else {
            new_state = FogSeekPowerState::NO_POWER;
        }

        if (new_state != power_state_) {
            ESP_LOGI("FogSeekPower",
                     "State %s -> %s (chg=%d done=%d adc=%d batt=%u%%)",
                     PowerStateToString(power_state_),
                     PowerStateToString(new_state),
                     is_charging ? 1 : 0,
                     is_done ? 1 : 0,
                     adc_value,
                     battery_level_);
            power_state_ = new_state;
            if (callback_) {
                callback_(power_state_);
            }
        }
    }

    static uint8_t MapBatteryLevel(int adc_value) {
        // Rough mapping; adjust if needed for your divider.
        const int min_adc = 1800;
        const int max_adc = 2600;
        if (adc_value <= min_adc) {
            return 0;
        }
        if (adc_value >= max_adc) {
            return 100;
        }
        return static_cast<uint8_t>((adc_value - min_adc) * 100 / (max_adc - min_adc));
    }

    static const char* PowerStateToString(FogSeekPowerState state) {
        switch (state) {
            case FogSeekPowerState::USB_CHARGING: return "USB_CHARGING";
            case FogSeekPowerState::USB_DONE: return "USB_DONE";
            case FogSeekPowerState::USB_NO_BATTERY: return "USB_NO_BATTERY";
            case FogSeekPowerState::BATTERY_POWER: return "BATTERY_POWER";
            case FogSeekPowerState::LOW_BATTERY: return "LOW_BATTERY";
            case FogSeekPowerState::NO_POWER:
            default: return "NO_POWER";
        }
    }

    gpio_num_t hold_gpio_ = GPIO_NUM_NC;
    gpio_num_t charging_gpio_ = GPIO_NUM_NC;
    gpio_num_t done_gpio_ = GPIO_NUM_NC;
    gpio_num_t adc_gpio_ = GPIO_NUM_NC;

    adc_oneshot_unit_handle_t adc_handle_ = nullptr;
    adc_channel_t adc_channel_ = ADC_CHANNEL_0;

    esp_timer_handle_t timer_handle_ = nullptr;
    PowerStateCallback callback_ = nullptr;

    FogSeekPowerState power_state_ = FogSeekPowerState::NO_POWER;
    uint8_t battery_level_ = 0;
};

class FogSeekDualLed : public Led {
public:
    FogSeekDualLed(gpio_num_t red_gpio, gpio_num_t green_gpio)
        : red_(red_gpio), green_(green_gpio) {}

    void UpdatePowerState(FogSeekPowerState state) {
        power_state_ = state;
        ESP_LOGI("FogSeekLed", "Power state update: %s", PowerStateToString(power_state_));
        ApplyPowerStateLed();
    }

    void OnStateChanged() override {
        auto& app = Application::GetInstance();
        auto state = app.GetDeviceState();
        ESP_LOGI("FogSeekLed", "OnStateChanged: device=%s, power=%s",
                 DeviceStateToString(state), PowerStateToString(power_state_));
        ApplyDeviceStateLed(state);
        ApplyPowerStateLed();
    }

private:
    void ApplyDeviceStateLed(DeviceState state) {
        switch (state) {
            case kDeviceStateStarting:
            case kDeviceStateWifiConfiguring:
            case kDeviceStateConnecting:
            case kDeviceStateUpgrading:
            case kDeviceStateActivating:
                ESP_LOGI("FogSeekLed", "Device pattern: NET_WAIT (green blink 200ms)");
                green_.StartContinuousBlink(200);
                break;
            case kDeviceStateIdle:
                ESP_LOGI("FogSeekLed", "Device pattern: IDLE (green breathing)");
                green_.StartBreathingEffect();
                break;
            case kDeviceStateListening:
                ESP_LOGI("FogSeekLed", "Device pattern: LISTENING (green on)");
                green_.TurnOn();
                break;
            case kDeviceStateSpeaking:
                ESP_LOGI("FogSeekLed", "Device pattern: SPEAKING (green blink 800ms)");
                green_.StartContinuousBlink(800);
                break;
            case kDeviceStateFatalError:
                ESP_LOGI("FogSeekLed", "Device pattern: FATAL_ERROR (green blink 100ms)");
                green_.StartContinuousBlink(100);
                break;
            case kDeviceStateUnknown:
            default:
                ESP_LOGI("FogSeekLed", "Device pattern: UNKNOWN (green off)");
                green_.TurnOff();
                break;
        }
    }

    void ApplyPowerStateLed() {
        switch (power_state_) {
            case FogSeekPowerState::USB_CHARGING:
                ESP_LOGI("FogSeekLed", "Power pattern: USB_CHARGING (red breathing)");
                red_.StartBreathingEffect();
                break;
            case FogSeekPowerState::USB_DONE:
                ESP_LOGI("FogSeekLed", "Power pattern: USB_DONE (red on)");
                red_.TurnOn();
                break;
            case FogSeekPowerState::LOW_BATTERY:
                ESP_LOGI("FogSeekLed", "Power pattern: LOW_BATTERY (red blink 100ms)");
                red_.StartContinuousBlink(100);
                break;
            case FogSeekPowerState::USB_NO_BATTERY:
            case FogSeekPowerState::BATTERY_POWER:
                ESP_LOGI("FogSeekLed", "Power pattern: BATTERY_OK (red off)");
                red_.TurnOff();
                break;
            case FogSeekPowerState::NO_POWER:
            default:
                ESP_LOGI("FogSeekLed", "Power pattern: NO_POWER (all off)");
                red_.TurnOff();
                green_.TurnOff();
                break;
        }
    }

    static const char* PowerStateToString(FogSeekPowerState state) {
        switch (state) {
            case FogSeekPowerState::USB_CHARGING: return "USB_CHARGING";
            case FogSeekPowerState::USB_DONE: return "USB_DONE";
            case FogSeekPowerState::USB_NO_BATTERY: return "USB_NO_BATTERY";
            case FogSeekPowerState::BATTERY_POWER: return "BATTERY_POWER";
            case FogSeekPowerState::LOW_BATTERY: return "LOW_BATTERY";
            case FogSeekPowerState::NO_POWER:
            default: return "NO_POWER";
        }
    }

    static const char* DeviceStateToString(DeviceState state) {
        switch (state) {
            case kDeviceStateUnknown: return "unknown";
            case kDeviceStateStarting: return "starting";
            case kDeviceStateWifiConfiguring: return "configuring";
            case kDeviceStateIdle: return "idle";
            case kDeviceStateConnecting: return "connecting";
            case kDeviceStateListening: return "listening";
            case kDeviceStateSpeaking: return "speaking";
            case kDeviceStateUpgrading: return "upgrading";
            case kDeviceStateActivating: return "activating";
            case kDeviceStateFatalError: return "fatal_error";
            default: return "invalid_state";
        }
    }

    SimpleGpioLed red_;
    SimpleGpioLed green_;
    FogSeekPowerState power_state_ = FogSeekPowerState::NO_POWER;
};

class FogSeekESP32S3 : public WifiBoard {
private:
    Display* display_;
    FogSeekPowerManagerLite power_manager_;
    FogSeekDualLed led_controller_;
    Button ctrl_button_;

    void InitializePowerManager() {
        power_manager_.Initialize(PWR_HOLD_GPIO, PWR_CHARGING_GPIO, PWR_CHARGE_DONE_GPIO, BATTERY_ADC_GPIO);
        power_manager_.SetCallback([this](FogSeekPowerState state) {
            led_controller_.UpdatePowerState(state);
        });
        power_manager_.Start();
    }

    void InitializeButtons() {
        ctrl_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            app.ToggleChatState(); // single click: interrupt
        });
        ctrl_button_.OnLongPress([this]() {
            esp_restart(); // long press: restart
        });
    }

    void InitializeIot() {
        auto& thing_manager = iot::ThingManager::GetInstance();
        thing_manager.AddThing(iot::CreateThing("Speaker"));
        thing_manager.AddThing(iot::CreateThing("Battery"));
    }

public:
    FogSeekESP32S3()
        : led_controller_(BUILTIN_LED_GPIO, BUILTIN_LED2_GPIO),
          ctrl_button_(CTRL_BUTTON_GPIO) {
        InitializePowerManager();

        // FogSeek board has no display
        display_ = new NoDisplay();

        InitializeIot();
        InitializeButtons();

        ESP_LOGI(TAG, "FogSeek ESP32-S3 board initialized");
    }

    virtual Led* GetLed() override {
        return &led_controller_;
    }

    virtual AudioCodec* GetAudioCodec() override {
        // Use I2S mic and I2S speaker (FogSeek pinout)
        static NoAudioCodecDuplex audio_codec(
            AUDIO_INPUT_SAMPLE_RATE,
            AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_SPK_GPIO_BCLK,  // GPIO39
            AUDIO_I2S_SPK_GPIO_LRCK,  // GPIO38
            AUDIO_I2S_SPK_GPIO_DOUT,  // GPIO1
            AUDIO_I2S_MIC_GPIO_DIN,   // GPIO2
            AUDIO_INPUT_REFERENCE
        );
        return &audio_codec;
    }

    virtual Display* GetDisplay() override {
        return display_;
    }

    virtual bool GetBatteryLevel(int& level, bool& charging, bool& discharging) override {
        charging = power_manager_.IsCharging();
        discharging = power_manager_.IsDischarging();
        level = power_manager_.GetBatteryLevel();
        return true;
    }

    virtual void StartNetwork() override {
        auto& app = Application::GetInstance();
        app.SetDeviceState(kDeviceStateConnecting);
        WifiBoard::StartNetwork();
    }
};

DECLARE_BOARD(FogSeekESP32S3);
