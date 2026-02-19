#ifndef FREERTOS_COMPAT_H
#define FREERTOS_COMPAT_H

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_heap_caps.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief 兼容性函数：创建具有内存能力的固定核心任务
 * 
 * 这是为了解决ESP-IDF v5.4.1中xTaskCreatePinnedToCoreWithCaps函数缺失的问题
 */
static inline BaseType_t xTaskCreatePinnedToCoreWithCaps(
    TaskFunction_t pxTaskCode,
    const char * const pcName,
    const uint32_t ulStackDepth,
    void * const pvParameters,
    UBaseType_t uxPriority,
    TaskHandle_t * const pxCreatedTask,
    const BaseType_t xCoreID,
    UBaseType_t uxMemoryCaps)
{
    // 如果不需要特殊内存能力，使用标准API
    if (uxMemoryCaps == 0 || uxMemoryCaps == MALLOC_CAP_DEFAULT) {
        return xTaskCreatePinnedToCore(
            pxTaskCode, pcName, ulStackDepth, pvParameters, 
            uxPriority, pxCreatedTask, xCoreID
        );
    }
    
    // 对于需要特殊内存能力的情况，使用静态分配
    StackType_t *pxStackBuffer = (StackType_t *)heap_caps_malloc(
        ulStackDepth * sizeof(StackType_t), uxMemoryCaps
    );
    
    if (pxStackBuffer == NULL) {
        return pdFAIL;
    }
    
    StaticTask_t *pxTaskBuffer = (StaticTask_t *)heap_caps_malloc(
        sizeof(StaticTask_t), MALLOC_CAP_INTERNAL
    );
    
    if (pxTaskBuffer == NULL) {
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
    
    return (xHandle != NULL) ? pdPASS : pdFAIL;
}

/**
 * @brief 兼容性函数：删除具有内存能力的任务
 */
static inline void vTaskDeleteWithCaps(TaskHandle_t xTaskToDelete)
{
    // 简单调用标准删除函数
    // 注意：这里不会自动释放heap_caps_malloc分配的内存
    // 在实际使用中需要手动管理这些内存
    vTaskDelete(xTaskToDelete);
}

/**
 * @brief 兼容性函数：获取任务核心ID
 */
static inline BaseType_t xTaskGetCoreID(TaskHandle_t xTask)
{
#if CONFIG_FREERTOS_NUMBER_OF_CORES > 1
    if (xTask == NULL) {
        xTask = xTaskGetCurrentTaskHandle();
    }
    
    // 在多核系统中，尝试获取任务亲和性
    // 这是一个简化的实现
    return tskNO_AFFINITY;  // 返回无亲和性
#else
    return 0;  // 单核系统总是返回0
#endif
}

/**
 * @brief 兼容性函数：获取指定核心的当前任务句柄
 */
static inline TaskHandle_t xTaskGetCurrentTaskHandleForCore(BaseType_t xCoreID)
{
#if CONFIG_FREERTOS_NUMBER_OF_CORES > 1
    // 在多核系统中，这个函数比较复杂
    // 简化实现：返回当前任务句柄
    return xTaskGetCurrentTaskHandle();
#else
    (void)xCoreID;  // 避免未使用参数警告
    return xTaskGetCurrentTaskHandle();
#endif
}

#ifdef __cplusplus
}
#endif

#endif // FREERTOS_COMPAT_H
