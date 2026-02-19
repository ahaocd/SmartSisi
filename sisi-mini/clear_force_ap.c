#include <stdio.h>
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_system.h"

void app_main(void)
{
    // 初始化 NVS
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        // NVS 分区被格式化，重新初始化
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    // 打开NVS命名空间
    printf("打开NVS命名空间'wifi'\n");
    nvs_handle_t nvs_handle;
    err = nvs_open("wifi", NVS_READWRITE, &nvs_handle);
    if (err != ESP_OK) {
        printf("错误：无法打开NVS命名空间 (%s)\n", esp_err_to_name(err));
        return;
    }

    // 设置force_ap为0
    printf("设置force_ap = 0\n");
    err = nvs_set_i32(nvs_handle, "force_ap", 0);
    if (err != ESP_OK) {
        printf("错误：无法写入force_ap (%s)\n", esp_err_to_name(err));
        nvs_close(nvs_handle);
        return;
    }

    // 提交更改
    printf("提交更改\n");
    err = nvs_commit(nvs_handle);
    if (err != ESP_OK) {
        printf("错误：无法提交更改 (%s)\n", esp_err_to_name(err));
        nvs_close(nvs_handle);
        return;
    }

    nvs_close(nvs_handle);
    printf("force_ap标志已清除！设备将重启\n");
    
    // 延迟2秒后重启
    vTaskDelay(2000 / portTICK_PERIOD_MS);
    esp_restart();
} 