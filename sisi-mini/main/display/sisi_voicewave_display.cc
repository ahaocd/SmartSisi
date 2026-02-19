#include "sisi_voicewave_display.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <string.h>   // For memset
#include <algorithm>  // For std::max, std::min
#include <cmath>      // For sinf

static const char *TAG = "SisiVoicewaveDisplay";

SisiVoicewaveDisplay::SisiVoicewaveDisplay() 
    : buffer(nullptr), 
      buffer_size(0),
      i2c_bus_(nullptr),
      i2c_device_(nullptr),
      current_line_type_(WaveLineType::LINE_GRAPH), // 默认折线
      current_animation_mode_(WaveAnimationMode::UP_DOWN), // 默认呼吸动画
      animation_frame_count_(0)
{
    buffer_size = (SISI_OLED_WIDTH * SISI_OLED_HEIGHT) / 8;
    buffer = new uint8_t[buffer_size];
    // 初始化互斥锁
    i2c_mutex_ = xSemaphoreCreateMutex();
}

SisiVoicewaveDisplay::~SisiVoicewaveDisplay() {
    if (buffer) {
        delete[] buffer;
    }
    // 删除互斥锁
    if (i2c_mutex_) {
        vSemaphoreDelete(i2c_mutex_);
    }
}

void SisiVoicewaveDisplay::SetI2cBus(i2c_master_bus_handle_t i2c_bus, i2c_master_dev_handle_t i2c_device) {
    i2c_device_ = i2c_device;
}

bool SisiVoicewaveDisplay::init() {
    ESP_LOGI(TAG, "🚀 开始初始化0.43寸OLED显示屏...");
    
    if (i2c_device_ == nullptr) {
        ESP_LOGI(TAG, "📡 正在创建I2C设备连接...");
        
        // 创建I2C设备 (使用已存在的I2C总线)
        i2c_device_config_t dev_cfg = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = 0x3C,
            .scl_speed_hz = 100000,  // 100kHz
        };
        
        // 获取全局I2C总线句柄
        extern i2c_master_bus_handle_t g_display_i2c_bus;
        if (g_display_i2c_bus == nullptr) {
            ESP_LOGE(TAG, "❌ 全局I2C总线未初始化!");
            return false;
        }
        ESP_LOGI(TAG, "✅ 全局I2C总线已找到");
        
        esp_err_t ret = i2c_master_bus_add_device(g_display_i2c_bus, &dev_cfg, &i2c_device_);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "❌ 添加I2C设备失败: %s", esp_err_to_name(ret));
            return false;
        }
        
        ESP_LOGI(TAG, "✅ I2C设备创建成功 (地址: 0x3C)");
    }
    
    // OLEDs need a moment to stabilize power after the bus is initialized.
    vTaskDelay(pdMS_TO_TICKS(100));

    // SH1106/SSD1306 compatible initialization sequence  
    ESP_LOGI(TAG, "🔧 开始OLED初始化序列...");
    
    esp_err_t ret;
    int failed_commands = 0;
    
    #define SAFE_SEND_CMD(cmd, desc) do { \
        ret = send_cmd(cmd); \
        if (ret != ESP_OK) { \
            ESP_LOGE(TAG, "❌ 命令失败 0x%02X (%s): %s", cmd, desc, esp_err_to_name(ret)); \
            failed_commands++; \
        } else { \
            ESP_LOGD(TAG, "✅ 命令成功 0x%02X (%s)", cmd, desc); \
        } \
    } while(0)
    
    SAFE_SEND_CMD(0xAE, "Display OFF");
    SAFE_SEND_CMD(0xD5, "Set Display Clock Divide Ratio");
    SAFE_SEND_CMD(0x80, "Suggested ratio");
    SAFE_SEND_CMD(0xA8, "Set MUX Ratio");
    SAFE_SEND_CMD(0x27, "70x40 -> MUX ratio 39");
    SAFE_SEND_CMD(0xD3, "Set display offset");
    SAFE_SEND_CMD(0x00, "No offset");
    SAFE_SEND_CMD(0x40, "Set start line address");
    SAFE_SEND_CMD(0x8D, "Charge Pump Setting");
    SAFE_SEND_CMD(0x14, "Enable charge pump");
    SAFE_SEND_CMD(0xA1, "Set segment remap");
    SAFE_SEND_CMD(0xC8, "Set COM Output Scan Direction");
    SAFE_SEND_CMD(0xDA, "Set COM Pins Hardware Configuration");
    SAFE_SEND_CMD(0x12, "Alternative COM pin config");
    SAFE_SEND_CMD(0x81, "Contrast Control");
    SAFE_SEND_CMD(0xCF, "Set contrast");
    SAFE_SEND_CMD(0xD9, "Set Pre-charge Period");
    SAFE_SEND_CMD(0xF1, "Set pre-charge");
    SAFE_SEND_CMD(0xDB, "Set VCOMH Deselect Level");
    SAFE_SEND_CMD(0x40, "Set VCOMH");
    SAFE_SEND_CMD(0xA4, "Resume to RAM content display");
    SAFE_SEND_CMD(0xA6, "Set Normal Display");
    
    if (failed_commands > 3) {
        ESP_LOGE(TAG, "❌ 初始化失败: %d 个命令失败", failed_commands);
        return false;
    }
    
    // Clear the display
    clear();
    
    SAFE_SEND_CMD(0xAF, "Display ON");
    
    ESP_LOGI(TAG, "✅ 0.43寸OLED初始化完成! 失败命令数: %d", failed_commands);
    return true;
}

void SisiVoicewaveDisplay::set_line_type(WaveLineType type) {
    current_line_type_ = type;
}

void SisiVoicewaveDisplay::set_animation_mode(WaveAnimationMode mode) {
    current_animation_mode_ = mode;
}

esp_err_t SisiVoicewaveDisplay::send_cmd(uint8_t cmd) {
    if (i2c_device_ == nullptr) {
        return ESP_ERR_INVALID_STATE;
    }
    
    // 获取互斥锁
    if (xSemaphoreTake(i2c_mutex_, pdMS_TO_TICKS(100)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    uint8_t data[] = {0x00, cmd};  // 0x00 indicates command
    esp_err_t ret = i2c_master_transmit(i2c_device_, data, sizeof(data), 2000 / portTICK_PERIOD_MS);
    
    // 释放互斥锁
    xSemaphoreGive(i2c_mutex_);
    
    return ret;
}

esp_err_t SisiVoicewaveDisplay::send_data(const uint8_t* data, size_t size) {
    if (i2c_device_ == nullptr || data == nullptr || size == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // 获取互斥锁
    if (xSemaphoreTake(i2c_mutex_, pdMS_TO_TICKS(100)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    // Prepare data with control byte (0x40 indicates data)
    size_t total_size = size + 1;
    uint8_t* tx_data = (uint8_t*)malloc(total_size);
    if (tx_data == nullptr) {
        // 释放互斥锁
        xSemaphoreGive(i2c_mutex_);
        return ESP_ERR_NO_MEM;
    }
    
    tx_data[0] = 0x40;  // Data control byte
    memcpy(tx_data + 1, data, size);
    
    esp_err_t ret = i2c_master_transmit(i2c_device_, tx_data, total_size, 2000 / portTICK_PERIOD_MS);
    
    free(tx_data);
    
    // 释放互斥锁
    xSemaphoreGive(i2c_mutex_);
    
    return ret;
}

esp_err_t SisiVoicewaveDisplay::clear() {
    if (buffer == nullptr) {
        return ESP_ERR_INVALID_STATE;
    }
    
    memset(buffer, 0, buffer_size);
    return send_buffer_to_display();
}

esp_err_t SisiVoicewaveDisplay::send_buffer_to_display() {
    if (buffer == nullptr || i2c_device_ == nullptr) {
        return ESP_ERR_INVALID_STATE;
    }

    // Calculate pages (each page is 8 pixels high)
    int pages = SISI_OLED_HEIGHT / 8;
    int bytes_per_page = SISI_OLED_WIDTH;
    
    for (int page = 0; page < pages; page++) {
        // Set page address
        esp_err_t ret = send_cmd(0xB0 + page);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "Failed to set page %d: %s", page, esp_err_to_name(ret));
            return ret;
        }
        
        // Set column address (with offset for centered display)
        ret = send_cmd(0x00 + ((SISI_OLED_COLUMN_OFFSET) & 0x0F));  // Lower nibble
        if (ret != ESP_OK) return ret;
        
        ret = send_cmd(0x10 + ((SISI_OLED_COLUMN_OFFSET) >> 4));    // Higher nibble
        if (ret != ESP_OK) return ret;
        
        // Send page data
        uint8_t* page_data = buffer + (page * bytes_per_page);
        ret = send_data(page_data, bytes_per_page);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "Failed to send page %d data: %s", page, esp_err_to_name(ret));
            return ret;
        }
    }
    
    return ESP_OK;
}

// Helper function to set pixel in buffer
static void draw_pixel(uint8_t* buffer, int x, int y) {
    if (x < 0 || x >= SISI_OLED_WIDTH || y < 0 || y >= SISI_OLED_HEIGHT) {
        return;
    }
    
    int page = y / 8;
    int bit = y % 8;
    int index = page * SISI_OLED_WIDTH + x;
    
    buffer[index] |= (1 << bit);
}

// Helper function to draw line using Bresenham's algorithm
static void draw_line(uint8_t* buffer, int x0, int y0, int x1, int y1) {
    int dx = abs(x1 - x0);
    int dy = abs(y1 - y0);
    int sx = (x0 < x1) ? 1 : -1;
    int sy = (y0 < y1) ? 1 : -1;
    int err = dx - dy;
    
    while (true) {
        draw_pixel(buffer, x0, y0);
        
        if (x0 == x1 && y0 == y1) break;
        
        int e2 = 2 * err;
        if (e2 > -dy) { err -= dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}

// 待机时的小波浪动画 - 根据您的要求
void SisiVoicewaveDisplay::render_idle_animation() {
    // 清空缓冲区
    memset(buffer, 0, buffer_size);

    // --- 待机动画：随机美学 "老电视" 滚动波浪线 ---
    static float frame_offset = 0.0f;
    static float noise_factor = 0.0f;
    
    float amplitude1 = (SISI_DISPLAY_AREA_Y_HEIGHT / 4.0f) * (0.8f + 0.2f * sinf(frame_offset * 0.5f));
    float amplitude2 = (SISI_DISPLAY_AREA_Y_HEIGHT / 5.0f) * (0.8f + 0.2f * cosf(frame_offset * 0.7f));
    float center_y = SISI_DISPLAY_AREA_Y_HEIGHT / 2.0f;

    for (int x = 0; x < SISI_OLED_WIDTH; x++) {
        float y_sin1 = sinf((float)x * 0.1f + frame_offset);
        float y_sin2 = cosf((float)x * 0.07f + frame_offset * 1.5f);
        float random_noise = ((float)rand() / RAND_MAX - 0.5f) * (2.0f + 2.0f * sinf(noise_factor));
        
        int y = (int)(center_y + y_sin1 * amplitude1 + y_sin2 * amplitude2 + random_noise);
        draw_pixel(buffer, x, y);

        // 模拟扫描线效果
        if (x % 3 == 0) {
             int y2 = y + (rand() % 3 - 1);
             draw_pixel(buffer, x, y2);
        }
    }

    frame_offset += 0.08f;
    noise_factor += 0.05f;
    if (frame_offset > 2.0f * 3.14159f) frame_offset -= 2.0f * 3.14159f;
    if (noise_factor > 2.0f * 3.14159f) noise_factor -= 2.0f * 3.14159f;

    // 将缓冲区发送到显示屏
    send_buffer_to_display();
}

// 音频驱动的波形可视化 - 根据您的要求，显示逻辑由音频输入驱动
void SisiVoicewaveDisplay::render_spectrum_visualization(const std::vector<float>& spectrum_data) {
    // 清空缓冲区
    memset(buffer, 0, buffer_size);

    if (spectrum_data.empty() || spectrum_data.size() < 2) {
        // 如果没有有效的音频数据，显示待机动画
        render_idle_animation();
        return;
    }

    // --- 根据音频频谱数据绘制波形 ---
    int num_bars = std::min((int)spectrum_data.size(), SISI_OLED_WIDTH / 2);
    int bar_width = SISI_OLED_WIDTH / num_bars;
    
    for (int i = 0; i < num_bars; i++) {
        float normalized_value = std::max(0.0f, std::min(1.0f, spectrum_data[i]));
        int bar_height = (int)(normalized_value * SISI_DISPLAY_AREA_Y_HEIGHT);
        int x_start = i * bar_width;
        
        for (int x = x_start; x < x_start + bar_width - 1 && x < SISI_OLED_WIDTH; x++) {
            for (int y = SISI_DISPLAY_AREA_Y_HEIGHT - bar_height; y < SISI_DISPLAY_AREA_Y_HEIGHT; y++) {
                    draw_pixel(buffer, x, y);
            }
        }
    }

    // 将缓冲区发送到显示屏
    send_buffer_to_display();
}