#include "esp_http_server_patch.h"
#include "esp_log.h"

static const char *TAG = "HTTP_PATCH";

BaseType_t xTaskCreatePinnedToCoreWithCaps(
    TaskFunction_t pxTaskCode,
    const char * const pcName,
    const uint32_t ulStackDepth,
    void * const pvParameters,
    UBaseType_t uxPriority,
    TaskHandle_t * const pxCreatedTask,
    const BaseType_t xCoreID,
    UBaseType_t uxMemoryCaps)
{
    ESP_LOGD(TAG, "使用兼容性函数创建任务: %s", pcName);
    
    // 如果不需要特殊内存能力，使用标准API
    if (uxMemoryCaps == 0 || uxMemoryCaps == MALLOC_CAP_DEFAULT) {
        return xTaskCreatePinnedToCore(
            pxTaskCode, pcName, ulStackDepth, pvParameters, 
            uxPriority, pxCreatedTask, xCoreID
        );
    }
    
    ESP_LOGD(TAG, "使用PSRAM创建任务: %s", pcName);
    
    // 对于需要特殊内存能力的情况，使用静态分配
    StackType_t *pxStackBuffer = (StackType_t *)heap_caps_malloc(
        ulStackDepth * sizeof(StackType_t), uxMemoryCaps
    );
    
    if (pxStackBuffer == NULL) {
        ESP_LOGE(TAG, "无法为任务 %s 分配栈内存", pcName);
        return pdFAIL;
    }
    
    StaticTask_t *pxTaskBuffer = (StaticTask_t *)heap_caps_malloc(
        sizeof(StaticTask_t), MALLOC_CAP_INTERNAL
    );
    
    if (pxTaskBuffer == NULL) {
        ESP_LOGE(TAG, "无法为任务 %s 分配TCB内存", pcName);
        heap_caps_free(pxStackBuffer);
        return pdFAIL;
    }
    
    TaskHandle_t xHandle = xTaskCreateStaticPinnedToCore(
        pxTaskCode, pcName, ulStackDepth, pvParameters,
        uxPriority, pxStackBuffer, pxTaskBuffer, xCoreID
    );
    
    if (pxCreatedTask != NULL) {
        *pxCreatedTask = xHandle;
    }
    
    if (xHandle != NULL) {
        ESP_LOGD(TAG, "成功创建任务: %s", pcName);
        return pdPASS;
    } else {
        ESP_LOGE(TAG, "创建任务失败: %s", pcName);
        heap_caps_free(pxStackBuffer);
        heap_caps_free(pxTaskBuffer);
        return pdFAIL;
    }
}

void vTaskDeleteWithCaps(TaskHandle_t xTaskToDelete)
{
    ESP_LOGD(TAG, "删除任务");
    // 注意：这里不会自动释放heap_caps_malloc分配的内存
    // 在实际使用中需要手动管理这些内存
    vTaskDelete(xTaskToDelete);
}

BaseType_t xTaskGetCoreID(TaskHandle_t xTask)
{
#if CONFIG_FREERTOS_NUMBER_OF_CORES > 1
    if (xTask == NULL) {
        xTask = xTaskGetCurrentTaskHandle();
    }
    
    // 在多核系统中，尝试获取任务亲和性
    // 这是一个简化的实现
    return tskNO_AFFINITY;  // 返回无亲和性
#else
    (void)xTask;  // 避免未使用参数警告
    return 0;  // 单核系统总是返回0
#endif
}

TaskHandle_t xTaskGetCurrentTaskHandleForCore(BaseType_t xCoreID)
{
#if CONFIG_FREERTOS_NUMBER_OF_CORES > 1
    // 在多核系统中，这个函数比较复杂
    // 简化实现：返回当前任务句柄
    (void)xCoreID;  // 避免未使用参数警告
    return xTaskGetCurrentTaskHandle();
#else
    (void)xCoreID;  // 避免未使用参数警告
    return xTaskGetCurrentTaskHandle();
#endif
}
