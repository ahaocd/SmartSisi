#ifndef ESP_HTTP_SERVER_PATCH_H
#define ESP_HTTP_SERVER_PATCH_H

// 在包含HTTP服务器头文件之前定义兼容性函数
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_heap_caps.h"

#ifdef __cplusplus
extern "C" {
#endif

// 兼容性函数声明
BaseType_t xTaskCreatePinnedToCoreWithCaps(
    TaskFunction_t pxTaskCode,
    const char * const pcName,
    const uint32_t ulStackDepth,
    void * const pvParameters,
    UBaseType_t uxPriority,
    TaskHandle_t * const pxCreatedTask,
    const BaseType_t xCoreID,
    UBaseType_t uxMemoryCaps);

void vTaskDeleteWithCaps(TaskHandle_t xTaskToDelete);
BaseType_t xTaskGetCoreID(TaskHandle_t xTask);
TaskHandle_t xTaskGetCurrentTaskHandleForCore(BaseType_t xCoreID);

#ifdef __cplusplus
}
#endif

#endif // ESP_HTTP_SERVER_PATCH_H
