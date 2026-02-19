#ifndef TRACE_FIX_H
#define TRACE_FIX_H

// 若 FreeRTOS 版本较旧且未定义 traceISR_EXIT_TO_SCHEDULER，
// 这里提供一个空实现以避免隐式声明编译错误。
#ifndef traceISR_EXIT_TO_SCHEDULER
#define traceISR_EXIT_TO_SCHEDULER()
#endif

#endif // TRACE_FIX_H 