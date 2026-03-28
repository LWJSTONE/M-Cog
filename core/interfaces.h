/**
 * M-Cog 模块间通信协议定义
 * 定义核心模块之间的接口和数据结构
 */

#ifndef MCOG_INTERFACES_H
#define MCOG_INTERFACES_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================
 * 基础类型定义
 * ============================================================ */

typedef uint32_t mcog_id_t;
typedef uint64_t mcog_timestamp_t;
typedef float mcog_confidence_t;

/* 错误码定义 */
typedef enum {
    MCOG_SUCCESS = 0,
    MCOG_ERROR_INVALID_PARAM = -1,
    MCOG_ERROR_RESOURCE_EXHAUSTED = -2,
    MCOG_ERROR_SAFETY_VIOLATION = -3,
    MCOG_ERROR_NOT_FOUND = -4,
    MCOG_ERROR_TIMEOUT = -5,
    MCOG_ERROR_INTERNAL = -6
} mcog_error_t;

/* 优先级定义 */
typedef enum {
    PRIORITY_P0 = 0,    /* 最高优先级 - 用户交互 */
    PRIORITY_P1 = 1,    /* 中等优先级 - 学习任务 */
    PRIORITY_P2 = 2     /* 低优先级 - 后台任务 */
} mcog_priority_t;

/* ============================================================
 * 知识图谱接口
 * ============================================================ */

/* 知识节点类型 */
typedef enum {
    NODE_TYPE_ENTITY,
    NODE_TYPE_CONCEPT,
    NODE_TYPE_VALUE
} mcog_node_type_t;

/* 置信度分布 */
typedef struct {
    float low;
    float medium;
    float high;
} mcog_confidence_dist_t;

/* 知识查询结果 */
typedef struct {
    mcog_id_t object_id;
    char object_name[256];
    mcog_confidence_dist_t confidence;
    char conditions[512];
} mcog_query_result_t;

/* 知识查询请求 */
typedef struct {
    char subject[256];
    char predicate[256];
    char context[512];
} mcog_query_request_t;

/* 知识插入请求 */
typedef struct {
    char subject[256];
    char predicate[256];
    char object[256];
    char conditions[512];
    char source[64];
} mcog_insert_request_t;

/* ============================================================
 * 专家路由接口
 * ============================================================ */

/* 专家信息 */
typedef struct {
    mcog_id_t expert_id;
    char domain[128];
    float weight;
    uint32_t input_dim;
    uint32_t output_dim;
} mcog_expert_info_t;

/* 路由结果 */
typedef struct {
    mcog_expert_info_t experts[8];  /* 最多返回8个专家 */
    uint32_t count;
} mcog_route_result_t;

/* 推理请求 */
typedef struct {
    mcog_id_t expert_ids[8];
    uint32_t expert_count;
    float* input_data;
    uint32_t input_size;
} mcog_infer_request_t;

/* 推理结果 */
typedef struct {
    float* output_data;
    uint32_t output_size;
    mcog_error_t status;
} mcog_infer_result_t;

/* ============================================================
 * 记忆系统接口
 * ============================================================ */

/* 情景记忆条目 */
typedef struct {
    mcog_id_t episode_id;
    mcog_timestamp_t timestamp;
    char user_input[2048];
    char system_output[2048];
    char user_feedback[32];        /* positive, negative, correction */
    float satisfaction_score;
    char error_type[64];
    char context_hash[64];
    float importance;
} mcog_episode_t;

/* 工作记忆 */
typedef struct {
    char session_id[64];
    char active_entities[8][256];
    uint32_t entity_count;
    char goals[4][512];
    uint32_t goal_count;
    mcog_timestamp_t last_updated;
} mcog_working_memory_t;

/* ============================================================
 * 工具工厂接口
 * ============================================================ */

/* 工具类型 */
typedef enum {
    TOOL_TYPE_CODE,
    TOOL_TYPE_NEURAL
} mcog_tool_type_t;

/* 工具资源预算 */
typedef struct {
    uint32_t max_cpu_ms;
    uint32_t max_memory_mb;
} mcog_resource_budget_t;

/* 工具信息 */
typedef struct {
    mcog_id_t tool_id;
    char name[128];
    mcog_tool_type_t type;
    char entry_point[512];
    mcog_resource_budget_t budget;
    uint32_t usage_count;
    float success_rate;
    mcog_timestamp_t created_at;
} mcog_tool_info_t;

/* 工具执行请求 */
typedef struct {
    mcog_id_t tool_id;
    char input_json[4096];
    uint32_t timeout_ms;
} mcog_tool_exec_request_t;

/* 工具执行结果 */
typedef struct {
    char output_json[4096];
    mcog_error_t status;
    uint32_t actual_time_ms;
} mcog_tool_exec_result_t;

/* ============================================================
 * 安全边界接口
 * ============================================================ */

/* 动作类型 */
typedef enum {
    ACTION_TYPE_GENERATE,
    ACTION_TYPE_EXECUTE,
    ACTION_TYPE_MODIFY,
    ACTION_TYPE_LEARN,
    ACTION_TYPE_DELETE
} mcog_action_type_t;

/* 安全检查请求 */
typedef struct {
    mcog_action_type_t action;
    char target[1024];
    char context[1024];
} mcog_safety_request_t;

/* 安全检查结果 */
typedef struct {
    bool allowed;
    char reason[512];
    uint32_t rule_id;
} mcog_safety_result_t;

/* ============================================================
 * 资源调度器接口
 * ============================================================ */

/* 资源使用统计 */
typedef struct {
    float cpu_usage_percent;
    uint32_t memory_used_mb;
    uint32_t memory_total_mb;
    uint32_t active_tasks;
    uint32_t queued_tasks;
} mcog_resource_stats_t;

/* 任务信息 */
typedef struct {
    mcog_id_t task_id;
    mcog_priority_t priority;
    uint32_t estimated_ms;
    uint32_t elapsed_ms;
    bool is_active;
} mcog_task_info_t;

/* ============================================================
 * 元认知接口
 * ============================================================ */

/* 监控指标 */
typedef struct {
    float prediction_error;
    float user_satisfaction;
    float knowledge_growth_rate;
    float resource_efficiency;
    mcog_timestamp_t window_start;
    mcog_timestamp_t window_end;
} mcog_metrics_t;

/* 学习动作类型 */
typedef enum {
    LEARN_ACTION_USER_INTERACTION,
    LEARN_ACTION_DOC_INGESTION,
    LEARN_ACTION_SELF_PLAY,
    LEARN_ACTION_SIMULATION,
    LEARN_ACTION_REFLECTION
} mcog_learn_action_t;

/* 学习调度结果 */
typedef struct {
    mcog_learn_action_t action;
    uint32_t priority;
    char params[1024];
    uint32_t estimated_duration_ms;
} mcog_schedule_result_t;

/* 反思级别 */
typedef enum {
    REFLECTION_MICRO,
    REFLECTION_MACRO,
    REFLECTION_DEEP
} mcog_reflection_level_t;

/* ============================================================
 * 函数指针类型定义 (用于模块间通信)
 * ============================================================ */

typedef mcog_error_t (*mcog_query_fn)(
    const mcog_query_request_t* request,
    mcog_query_result_t* results,
    uint32_t* result_count,
    uint32_t max_results
);

typedef mcog_error_t (*mcog_insert_fn)(
    const mcog_insert_request_t* request,
    mcog_id_t* relation_id
);

typedef mcog_error_t (*mcog_route_fn)(
    const float* input_embedding,
    uint32_t embedding_size,
    mcog_route_result_t* result
);

typedef mcog_error_t (*mcog_infer_fn)(
    const mcog_infer_request_t* request,
    mcog_infer_result_t* result
);

typedef mcog_error_t (*mcog_safety_check_fn)(
    const mcog_safety_request_t* request,
    mcog_safety_result_t* result
);

typedef int (*mcog_request_exec_fn)(
    int priority,
    int estimated_ms
);

typedef void (*mcog_release_exec_fn)(int task_id);

/* ============================================================
 * 模块注册表
 * ============================================================ */

typedef struct {
    mcog_query_fn query;
    mcog_insert_fn insert;
    mcog_route_fn route;
    mcog_infer_fn infer;
    mcog_safety_check_fn safety_check;
    mcog_request_exec_fn request_exec;
    mcog_release_exec_fn release_exec;
} mcog_module_registry_t;

/* 全局注册表声明 */
extern mcog_module_registry_t g_mcog_registry;

/* 模块注册函数 */
void mcog_register_modules(const mcog_module_registry_t* registry);

#ifdef __cplusplus
}
#endif

#endif /* MCOG_INTERFACES_H */
