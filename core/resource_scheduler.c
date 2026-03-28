/**
 * M-Cog 资源调度器
 * 基于 C 语言的高效资源管理和任务调度
 * 
 * 编译命令: gcc -shared -fPIC -o resource_scheduler.so resource_scheduler.c -lpthread
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <time.h>
#include <pthread.h>
#include <unistd.h>
#include <sys/resource.h>
#include "interfaces.h"

#ifdef _WIN32
    #define EXPORT __declspec(dllexport)
    #include <windows.h>
#else
    #define EXPORT __attribute__((visibility("default")))
#endif

/* ============================================================
 * 配置常量
 * ============================================================ */

#define MAX_TASKS 256
#define MAX_QUEUE_SIZE 1024
#define MONITOR_INTERVAL_MS 10
#define P0_RESERVE_PERCENT 30

/* 任务状态 */
typedef enum {
    TASK_STATE_IDLE,
    TASK_STATE_QUEUED,
    TASK_STATE_RUNNING,
    TASK_STATE_COMPLETED,
    TASK_STATE_TIMEOUT,
    TASK_STATE_CANCELLED
} TaskState;

/* 任务结构 */
typedef struct {
    mcog_id_t task_id;
    mcog_priority_t priority;
    uint32_t estimated_ms;
    uint32_t elapsed_ms;
    TaskState state;
    time_t start_time;
    time_t end_time;
    void* user_data;
    bool is_active;
} Task;

/* 优先级队列 */
typedef struct {
    Task tasks[MAX_QUEUE_SIZE];
    int head;
    int tail;
    int count;
    pthread_mutex_t mutex;
} PriorityQueue;

/* 调度器状态 */
typedef struct {
    PriorityQueue queues[3];  /* P0, P1, P2 */
    Task active_tasks[MAX_TASKS];
    int active_count;
    mcog_resource_stats_t stats;
    pthread_t monitor_thread;
    pthread_mutex_t global_mutex;
    bool running;
    uint32_t next_task_id;
    
    /* 配置参数 */
    uint32_t max_concurrent_p0;
    uint32_t max_concurrent_p1;
    uint32_t max_concurrent_p2;
    uint32_t max_memory_mb;
} Scheduler;

/* 全局调度器实例 */
static Scheduler g_scheduler = {0};

/* ============================================================
 * 队列操作函数
 * ============================================================ */

static void queue_init(PriorityQueue* queue) {
    memset(queue, 0, sizeof(PriorityQueue));
    pthread_mutex_init(&queue->mutex, NULL);
}

static bool queue_push(PriorityQueue* queue, const Task* task) {
    bool success = false;
    pthread_mutex_lock(&queue->mutex);
    
    if (queue->count < MAX_QUEUE_SIZE) {
        queue->tasks[queue->tail] = *task;
        queue->tail = (queue->tail + 1) % MAX_QUEUE_SIZE;
        queue->count++;
        success = true;
    }
    
    pthread_mutex_unlock(&queue->mutex);
    return success;
}

static bool queue_pop(PriorityQueue* queue, Task* task) {
    bool success = false;
    pthread_mutex_lock(&queue->mutex);
    
    if (queue->count > 0) {
        *task = queue->tasks[queue->head];
        queue->head = (queue->head + 1) % MAX_QUEUE_SIZE;
        queue->count--;
        success = true;
    }
    
    pthread_mutex_unlock(&queue->mutex);
    return success;
}

static int queue_count(PriorityQueue* queue) {
    int count;
    pthread_mutex_lock(&queue->mutex);
    count = queue->count;
    pthread_mutex_unlock(&queue->mutex);
    return count;
}

/* ============================================================
 * 资源监控函数
 * ============================================================ */

#ifdef _WIN32
static float get_cpu_usage(void) {
    /* Windows 实现 */
    static FILETIME prev_sys_idle, prev_sys_kernel, prev_sys_user;
    FILETIME sys_idle, sys_kernel, sys_user;
    
    GetSystemTimes(&sys_idle, &sys_kernel, &sys_user);
    
    uint64_t idle = ((uint64_t)sys_idle.dwHighDateTime << 32) | sys_idle.dwLowDateTime;
    uint64_t kernel = ((uint64_t)sys_kernel.dwHighDateTime << 32) | sys_kernel.dwLowDateTime;
    uint64_t user = ((uint64_t)sys_user.dwHighDateTime << 32) | sys_user.dwLowDateTime;
    
    uint64_t prev_idle = ((uint64_t)prev_sys_idle.dwHighDateTime << 32) | prev_sys_idle.dwLowDateTime;
    uint64_t prev_kernel = ((uint64_t)prev_sys_kernel.dwHighDateTime << 32) | prev_sys_kernel.dwLowDateTime;
    uint64_t prev_user = ((uint64_t)prev_sys_user.dwHighDateTime << 32) | prev_sys_user.dwLowDateTime;
    
    uint64_t sys_total = (kernel - prev_kernel) + (user - prev_user);
    uint64_t total = sys_total + (idle - prev_idle);
    
    prev_sys_idle = sys_idle;
    prev_sys_kernel = sys_kernel;
    prev_sys_user = sys_user;
    
    return total > 0 ? (float)sys_total / total * 100.0f : 0.0f;
}

static uint32_t get_memory_usage_mb(void) {
    MEMORYSTATUSEX status;
    status.dwLength = sizeof(status);
    GlobalMemoryStatusEx(&status);
    return (uint32_t)(status.ullTotalPhys - status.ullAvailPhys) / (1024 * 1024);
}

static uint32_t get_total_memory_mb(void) {
    MEMORYSTATUSEX status;
    status.dwLength = sizeof(status);
    GlobalMemoryStatusEx(&status);
    return (uint32_t)(status.ullTotalPhys / (1024 * 1024));
}
#else
static float get_cpu_usage(void) {
    /* Linux 实现 - 读取 /proc/stat */
    static unsigned long long prev_user, prev_nice, prev_system, prev_idle;
    unsigned long long user, nice, system, idle;
    float usage = 0.0f;
    
    FILE* fp = fopen("/proc/stat", "r");
    if (fp) {
        if (fscanf(fp, "cpu %llu %llu %llu %llu", 
                   &user, &nice, &system, &idle) == 4) {
            unsigned long long total = (user - prev_user) + (nice - prev_nice) + 
                                       (system - prev_system);
            unsigned long long total_all = total + (idle - prev_idle);
            
            if (total_all > 0) {
                usage = (float)total / total_all * 100.0f;
            }
            
            prev_user = user;
            prev_nice = nice;
            prev_system = system;
            prev_idle = idle;
        }
        fclose(fp);
    }
    return usage;
}

static uint32_t get_memory_usage_mb(void) {
    FILE* fp = fopen("/proc/meminfo", "r");
    if (!fp) return 0;
    
    unsigned long total = 0, free = 0, buffers = 0, cached = 0;
    char line[256];
    
    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "MemTotal: %lu kB", &total) == 1) continue;
        if (sscanf(line, "MemFree: %lu kB", &free) == 1) continue;
        if (sscanf(line, "Buffers: %lu kB", &buffers) == 1) continue;
        if (sscanf(line, "Cached: %lu kB", &cached) == 1) continue;
    }
    fclose(fp);
    
    unsigned long used = total - free - buffers - cached;
    return (uint32_t)(used / 1024);
}

static uint32_t get_total_memory_mb(void) {
    FILE* fp = fopen("/proc/meminfo", "r");
    if (!fp) return 0;
    
    unsigned long total = 0;
    char line[256];
    
    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "MemTotal: %lu kB", &total) == 1) break;
    }
    fclose(fp);
    
    return (uint32_t)(total / 1024);
}
#endif

/* ============================================================
 * 监控线程
 * ============================================================ */

static void* monitor_thread_func(void* arg) {
    Scheduler* sched = (Scheduler*)arg;
    
    while (sched->running) {
        /* 更新资源统计 */
        pthread_mutex_lock(&sched->global_mutex);
        
        sched->stats.cpu_usage_percent = get_cpu_usage();
        sched->stats.memory_used_mb = get_memory_usage_mb();
        sched->stats.memory_total_mb = get_total_memory_mb();
        sched->stats.queued_tasks = queue_count(&sched->queues[0]) +
                                    queue_count(&sched->queues[1]) +
                                    queue_count(&sched->queues[2]);
        sched->stats.active_tasks = sched->active_count;
        
        /* 检查超时任务 */
        time_t current_time = time(NULL);
        for (int i = 0; i < sched->active_count; i++) {
            Task* task = &sched->active_tasks[i];
            if (task->is_active && task->state == TASK_STATE_RUNNING) {
                uint32_t elapsed = (uint32_t)(current_time - task->start_time) * 1000;
                task->elapsed_ms = elapsed;
                
                /* 检查超时 */
                if (elapsed > task->estimated_ms * 2) {
                    task->state = TASK_STATE_TIMEOUT;
                    task->is_active = false;
                    printf("[SCHEDULER] Task %u timed out (elapsed: %u ms, estimated: %u ms)\n",
                           task->task_id, elapsed, task->estimated_ms);
                }
            }
        }
        
        pthread_mutex_unlock(&sched->global_mutex);
        
        /* 等待下一个监控周期 */
        #ifdef _WIN32
        Sleep(MONITOR_INTERVAL_MS);
        #else
        usleep(MONITOR_INTERVAL_MS * 1000);
        #endif
    }
    
    return NULL;
}

/* ============================================================
 * 公共接口实现
 * ============================================================ */

/**
 * 初始化资源调度器
 */
EXPORT int init_scheduler(void) {
    memset(&g_scheduler, 0, sizeof(Scheduler));
    
    /* 初始化队列 */
    for (int i = 0; i < 3; i++) {
        queue_init(&g_scheduler.queues[i]);
    }
    
    pthread_mutex_init(&g_scheduler.global_mutex, NULL);
    
    /* 设置默认配置 */
    g_scheduler.max_concurrent_p0 = 4;
    g_scheduler.max_concurrent_p1 = 2;
    g_scheduler.max_concurrent_p2 = 1;
    g_scheduler.max_memory_mb = 4096;
    g_scheduler.running = true;
    g_scheduler.next_task_id = 1;
    
    /* 启动监控线程 */
    if (pthread_create(&g_scheduler.monitor_thread, NULL, 
                       monitor_thread_func, &g_scheduler) != 0) {
        fprintf(stderr, "[SCHEDULER] Failed to create monitor thread\n");
        return -1;
    }
    
    printf("[SCHEDULER] Resource scheduler initialized\n");
    printf("[SCHEDULER] Max concurrent: P0=%u, P1=%u, P2=%u\n",
           g_scheduler.max_concurrent_p0,
           g_scheduler.max_concurrent_p1,
           g_scheduler.max_concurrent_p2);
    
    return 0;
}

/**
 * 请求执行任务
 * @param priority 优先级 (0=P0, 1=P1, 2=P2)
 * @param estimated_ms 预估执行时间(毫秒)
 * @return 任务ID，失败返回-1
 */
EXPORT int request_execution(int priority, int estimated_ms) {
    if (priority < 0 || priority > 2) {
        fprintf(stderr, "[SCHEDULER] Invalid priority: %d\n", priority);
        return -1;
    }
    
    pthread_mutex_lock(&g_scheduler.global_mutex);
    
    /* 检查是否可以立即执行 */
    bool can_execute = false;
    uint32_t active_p0 = 0, active_p1 = 0, active_p2 = 0;
    
    for (int i = 0; i < g_scheduler.active_count; i++) {
        if (g_scheduler.active_tasks[i].is_active) {
            switch (g_scheduler.active_tasks[i].priority) {
                case PRIORITY_P0: active_p0++; break;
                case PRIORITY_P1: active_p1++; break;
                case PRIORITY_P2: active_p2++; break;
            }
        }
    }
    
    /* P0 任务预留检查 */
    float cpu_reserve = 100.0f - g_scheduler.stats.cpu_usage_percent;
    if (cpu_reserve < P0_RESERVE_PERCENT && priority > PRIORITY_P0) {
        /* CPU 资源不足，非P0任务需要排队 */
        can_execute = false;
    } else {
        switch (priority) {
            case PRIORITY_P0:
                can_execute = (active_p0 < g_scheduler.max_concurrent_p0);
                break;
            case PRIORITY_P1:
                can_execute = (active_p1 < g_scheduler.max_concurrent_p1);
                break;
            case PRIORITY_P2:
                can_execute = (active_p2 < g_scheduler.max_concurrent_p2);
                break;
        }
    }
    
    /* 创建任务 */
    Task task = {0};
    task.task_id = g_scheduler.next_task_id++;
    task.priority = (mcog_priority_t)priority;
    task.estimated_ms = (uint32_t)estimated_ms;
    task.elapsed_ms = 0;
    
    if (can_execute && g_scheduler.active_count < MAX_TASKS) {
        /* 立即执行 */
        task.state = TASK_STATE_RUNNING;
        task.start_time = time(NULL);
        task.is_active = true;
        g_scheduler.active_tasks[g_scheduler.active_count++] = task;
        
        printf("[SCHEDULER] Task %u started immediately (priority=P%d, estimated=%u ms)\n",
               task.task_id, priority, estimated_ms);
    } else {
        /* 加入队列 */
        task.state = TASK_STATE_QUEUED;
        task.is_active = false;
        
        if (queue_push(&g_scheduler.queues[priority], &task)) {
            printf("[SCHEDULER] Task %u queued (priority=P%d, queue_size=%d)\n",
                   task.task_id, priority, queue_count(&g_scheduler.queues[priority]));
        } else {
            pthread_mutex_unlock(&g_scheduler.global_mutex);
            fprintf(stderr, "[SCHEDULER] Queue full for priority %d\n", priority);
            return -1;
        }
    }
    
    pthread_mutex_unlock(&g_scheduler.global_mutex);
    return (int)task.task_id;
}

/**
 * 释放执行资源
 */
EXPORT void release_execution(int task_id) {
    if (task_id <= 0) return;
    
    pthread_mutex_lock(&g_scheduler.global_mutex);
    
    /* 查找并释放任务 */
    for (int i = 0; i < g_scheduler.active_count; i++) {
        if (g_scheduler.active_tasks[i].task_id == (mcog_id_t)task_id) {
            g_scheduler.active_tasks[i].state = TASK_STATE_COMPLETED;
            g_scheduler.active_tasks[i].is_active = false;
            g_scheduler.active_tasks[i].end_time = time(NULL);
            
            printf("[SCHEDULER] Task %u completed (elapsed: %u ms)\n",
                   task_id, g_scheduler.active_tasks[i].elapsed_ms);
            
            /* 尝试从队列中调度下一个任务 */
            for (int p = 0; p < 3; p++) {
                Task next_task;
                if (queue_pop(&g_scheduler.queues[p], &next_task)) {
                    next_task.state = TASK_STATE_RUNNING;
                    next_task.start_time = time(NULL);
                    next_task.is_active = true;
                    g_scheduler.active_tasks[i] = next_task;
                    
                    printf("[SCHEDULER] Task %u started from queue (priority=P%d)\n",
                           next_task.task_id, p);
                    break;
                }
            }
            
            break;
        }
    }
    
    pthread_mutex_unlock(&g_scheduler.global_mutex);
}

/**
 * 获取资源统计信息
 */
EXPORT mcog_resource_stats_t get_resource_stats(void) {
    mcog_resource_stats_t stats;
    pthread_mutex_lock(&g_scheduler.global_mutex);
    stats = g_scheduler.stats;
    pthread_mutex_unlock(&g_scheduler.global_mutex);
    return stats;
}

/**
 * 获取任务信息
 */
EXPORT mcog_task_info_t get_task_info(mcog_id_t task_id) {
    mcog_task_info_t info = {0};
    
    pthread_mutex_lock(&g_scheduler.global_mutex);
    
    for (int i = 0; i < g_scheduler.active_count; i++) {
        if (g_scheduler.active_tasks[i].task_id == task_id) {
            Task* task = &g_scheduler.active_tasks[i];
            info.task_id = task->task_id;
            info.priority = task->priority;
            info.estimated_ms = task->estimated_ms;
            info.elapsed_ms = task->elapsed_ms;
            info.is_active = task->is_active;
            break;
        }
    }
    
    pthread_mutex_unlock(&g_scheduler.global_mutex);
    return info;
}

/**
 * 取消任务
 */
EXPORT int cancel_task(mcog_id_t task_id) {
    pthread_mutex_lock(&g_scheduler.global_mutex);
    
    int result = -1;
    
    /* 检查活动任务 */
    for (int i = 0; i < g_scheduler.active_count; i++) {
        if (g_scheduler.active_tasks[i].task_id == task_id) {
            g_scheduler.active_tasks[i].state = TASK_STATE_CANCELLED;
            g_scheduler.active_tasks[i].is_active = false;
            result = 0;
            printf("[SCHEDULER] Task %u cancelled\n", task_id);
            break;
        }
    }
    
    /* TODO: 检查队列中的任务 */
    
    pthread_mutex_unlock(&g_scheduler.global_mutex);
    return result;
}

/**
 * 设置调度器配置
 */
EXPORT int set_scheduler_config(uint32_t max_p0, uint32_t max_p1, 
                                uint32_t max_p2, uint32_t max_mem_mb) {
    pthread_mutex_lock(&g_scheduler.global_mutex);
    
    g_scheduler.max_concurrent_p0 = max_p0;
    g_scheduler.max_concurrent_p1 = max_p1;
    g_scheduler.max_concurrent_p2 = max_p2;
    g_scheduler.max_memory_mb = max_mem_mb;
    
    printf("[SCHEDULER] Config updated: P0=%u, P1=%u, P2=%u, Mem=%u MB\n",
           max_p0, max_p1, max_p2, max_mem_mb);
    
    pthread_mutex_unlock(&g_scheduler.global_mutex);
    return 0;
}

/**
 * 关闭调度器
 */
EXPORT void shutdown_scheduler(void) {
    printf("[SCHEDULER] Shutting down...\n");
    
    g_scheduler.running = false;
    
    /* 等待监控线程结束 */
    pthread_join(g_scheduler.monitor_thread, NULL);
    
    /* 销毁互斥锁 */
    pthread_mutex_destroy(&g_scheduler.global_mutex);
    for (int i = 0; i < 3; i++) {
        pthread_mutex_destroy(&g_scheduler.queues[i].mutex);
    }
    
    printf("[SCHEDULER] Shutdown complete\n");
}

/**
 * 获取版本信息
 */
EXPORT const char* get_scheduler_version(void) {
    return "M-Cog Resource Scheduler v1.0.0";
}

/* ============================================================
 * 测试入口点
 * ============================================================ */

#ifdef MCOG_SCHEDULER_TEST

int main(int argc, char** argv) {
    printf("=== M-Cog Resource Scheduler Test ===\n\n");
    
    /* 初始化 */
    if (init_scheduler() != 0) {
        printf("Initialization failed!\n");
        return 1;
    }
    
    /* 获取初始资源状态 */
    printf("--- Initial Resource Stats ---\n");
    mcog_resource_stats_t stats = get_resource_stats();
    printf("CPU Usage: %.1f%%\n", stats.cpu_usage_percent);
    printf("Memory: %u / %u MB\n", stats.memory_used_mb, stats.memory_total_mb);
    printf("Queued Tasks: %u\n", stats.queued_tasks);
    printf("Active Tasks: %u\n\n", stats.active_tasks);
    
    /* 测试任务请求 */
    printf("--- Task Submission Test ---\n");
    int task1 = request_execution(0, 100);  /* P0 task */
    int task2 = request_execution(1, 500);  /* P1 task */
    int task3 = request_execution(2, 1000); /* P2 task */
    int task4 = request_execution(0, 50);   /* P0 task */
    
    printf("Tasks created: %d, %d, %d, %d\n\n", task1, task2, task3, task4);
    
    /* 模拟任务执行 */
    printf("--- Simulating Execution ---\n");
    #ifdef _WIN32
    Sleep(100);
    #else
    usleep(100000);
    #endif
    
    /* 释放任务 */
    release_execution(task1);
    release_execution(task2);
    release_execution(task3);
    release_execution(task4);
    
    /* 最终资源状态 */
    printf("\n--- Final Resource Stats ---\n");
    stats = get_resource_stats();
    printf("CPU Usage: %.1f%%\n", stats.cpu_usage_percent);
    printf("Memory: %u / %u MB\n", stats.memory_used_mb, stats.memory_total_mb);
    
    /* 关闭 */
    shutdown_scheduler();
    
    printf("\n=== Test Complete ===\n");
    return 0;
}

#endif /* MCOG_SCHEDULER_TEST */
