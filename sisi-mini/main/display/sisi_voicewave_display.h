#include <cstdint>
#include <vector>
#include "driver/i2c_master.h"
// 前向声明FreeRTOS类型，避免包含顺序问题
struct QueueDefinition;
typedef struct QueueDefinition *SemaphoreHandle_t;

// 定义硬件参数 - 根据规格图：0.42"OLED 70x40 dots
#define SISI_OLED_WIDTH 70
#define SISI_OLED_HEIGHT 40
#define SISI_OLED_COLUMN_OFFSET 28 // For 70x40 displays on a 128x64 controller (e.g., SH1106)

// 定义频谱数据的点数
#define SISI_SPECTRUM_POINTS 8

// 定义显示区域 - 只使用屏幕上方30个像素
#define SISI_DISPLAY_AREA_Y_START 0
#define SISI_DISPLAY_AREA_Y_HEIGHT 30

// 复刻 VoiceWaveView 的模式定义
enum class WaveLineType {
    BAR_CHART,
    LINE_GRAPH
};

enum class WaveAnimationMode {
    STATIC,      // 仅数据驱动
    UP_DOWN,     // 呼吸动画
    LEFT_RIGHT   // (暂不实现，需要更复杂的数据结构)
};


class SisiVoicewaveDisplay {
public:
    SisiVoicewaveDisplay();
    ~SisiVoicewaveDisplay();

    // 设置外部I2C总线
    void SetI2cBus(i2c_master_bus_handle_t i2c_bus, i2c_master_dev_handle_t i2c_device);

    bool init();
    
    // 新增的模式设置接口
    void set_line_type(WaveLineType type);
    void set_animation_mode(WaveAnimationMode mode);

    // 音频驱动的显示接口 - 根据您的要求，显示逻辑应该由音频输入驱动
    void render_idle_animation();  // 待机时的小波浪动画
    void render_spectrum_visualization(const std::vector<float>& spectrum_data);  // 音频驱动的波形显示

private:
    esp_err_t send_cmd(uint8_t cmd);
    esp_err_t send_data(const uint8_t* data, size_t size);
    esp_err_t clear();
    esp_err_t send_buffer_to_display();

    // 显示缓冲区
    uint8_t* buffer;
    size_t buffer_size;

    // I2C设备句柄
    i2c_master_bus_handle_t i2c_bus_;
    i2c_master_dev_handle_t i2c_device_;
    
    // 添加互斥锁成员变量
    SemaphoreHandle_t i2c_mutex_;
    
    // 新增的模式状态变量
    WaveLineType current_line_type_;
    WaveAnimationMode current_animation_mode_;
    uint32_t animation_frame_count_; // 用于动画计算
};