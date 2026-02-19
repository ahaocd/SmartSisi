#include <stdio.h>
#include <string.h>
#include <nvs_flash.h>
#include <esp_log.h>
#include <esp_system.h>
#include <ssid_manager.h>

static const char *TAG = "INIT_WIFI";

// 使用constructor属性确保在程序启动时自动运行
extern "C" void init_wifi_config(void) __attribute__((constructor));

extern "C" void init_wifi_config(void) {
    esp_err_t err;
    nvs_handle_t nvs_handle;
    
    // 初始化NVS
    err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGI(TAG, "重新初始化NVS分区");
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    
    // 打开wifi命名空间
    err = nvs_open("wifi", NVS_READWRITE, &nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "无法打开wifi命名空间: %s", esp_err_to_name(err));
        return;
    }
    
    // 设置force_ap为0以禁用强制配网模式
    err = nvs_set_i32(nvs_handle, "force_ap", 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "无法设置force_ap: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "成功设置force_ap=0");
    }
    
    // 添加iPhone15热点配置
    const char* ssid = "iPhone15";  // 替换为您的WiFi名称
    const char* password = "88888888";  // 修改为默认密码
    
    // 保存SSID和密码
    try {
        SSIDManager ssid_manager;
        ESP_LOGI(TAG, "尝试添加SSID: %s", ssid);
        if (ssid_manager.AddSSID(ssid, password) != ESP_OK) {
            ESP_LOGE(TAG, "无法添加SSID %s", ssid);
        } else {
            ESP_LOGI(TAG, "成功添加SSID %s", ssid);
        }
    } catch (...) {
        ESP_LOGE(TAG, "SSIDManager初始化或添加SSID时发生异常");
    }
    
    // 提交更改并关闭NVS
    err = nvs_commit(nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "无法提交NVS更改: %s", esp_err_to_name(err));
    }
    
    nvs_close(nvs_handle);
    ESP_LOGI(TAG, "WiFi初始化完成");
} 