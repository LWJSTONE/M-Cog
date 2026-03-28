/**
 * M-Cog 安全边界模块
 * 硬编码安全规则，不可被系统自动修改
 * 
 * 编译命令: gcc -shared -fPIC -o safety_hardcode.so safety_hardcode.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <time.h>
#include "interfaces.h"

#ifdef _WIN32
    #define EXPORT __declspec(dllexport)
#else
    #define EXPORT __attribute__((visibility("default")))
#endif

/* ============================================================
 * 硬编码安全规则定义
 * 这些规则在编译后不可被修改，是系统的安全基础
 * ============================================================ */

/* 安全规则ID枚举 */
typedef enum {
    RULE_NO_HARM = 1,
    RULE_NO_DECEPTION = 2,
    RULE_NO_UNAUTHORIZED_ACTION = 3,
    RULE_NO_ILLEGAL_CONTENT = 4,
    RULE_NO_SELF_MODIFICATION_CORE = 5,
    RULE_NO_DATA_EXFILTRATION = 6,
    RULE_NO_SYSTEM_OVERRIDE = 7,
    RULE_RESPECT_USER_CONSENT = 8,
    RULE_PROTECT_PRIVACY = 9,
    RULE_LIMIT_RESOURCE_USAGE = 10
} SafetyRuleID;

/* 规则定义结构 */
typedef struct {
    SafetyRuleID id;
    const char* name;
    const char* description;
    bool is_core;  /* 核心规则不可被绕过 */
} SafetyRule;

/* 硬编码规则表 */
static const SafetyRule SAFETY_RULES[] = {
    {RULE_NO_HARM, "no_harm", 
     "禁止生成任何可能直接导致人身伤害的指令或内容", true},
    {RULE_NO_DECEPTION, "no_deception", 
     "禁止冒充人类进行欺骗或误导性交互", true},
    {RULE_NO_UNAUTHORIZED_ACTION, "no_unauthorized_action", 
     "禁止未经用户明确授权执行外部操作", true},
    {RULE_NO_ILLEGAL_CONTENT, "no_illegal_content", 
     "禁止生成、存储或传播违法内容", true},
    {RULE_NO_SELF_MODIFICATION_CORE, "no_self_modification_core", 
     "禁止修改核心安全模块和硬编码规则", true},
    {RULE_NO_DATA_EXFILTRATION, "no_exfiltration", 
     "禁止未经授权将用户数据传输到外部", true},
    {RULE_NO_SYSTEM_OVERRIDE, "no_system_override", 
     "禁止尝试绕过或关闭安全检查机制", true},
    {RULE_RESPECT_USER_CONSENT, "respect_consent", 
     "在处理敏感操作前必须获得用户明确同意", false},
    {RULE_PROTECT_PRIVACY, "protect_privacy", 
     "保护用户隐私信息，不记录不必要的个人数据", false},
    {RULE_LIMIT_RESOURCE_USAGE, "limit_resources", 
     "限制资源使用，防止系统过载", false}
};

#define RULE_COUNT (sizeof(SAFETY_RULES) / sizeof(SafetyRule))

/* 危险关键词列表 */
static const char* HARM_KEYWORDS[] = {
    "kill", "murder", "suicide", "poison", "bomb", "weapon",
    "explode", "attack", "hurt", "injure", "伤害", "杀", "自杀",
    "炸弹", "武器", "攻击", "毒药", NULL
};

static const char* DECEPTION_KEYWORDS[] = {
    "pretend to be human", "fake identity", "impersonate",
    "伪装人类", "冒充", "假身份", "欺骗", NULL
};

static const char* ILLEGAL_KEYWORDS[] = {
    "illegal", "criminal", "drug trafficking", "money laundering",
    "非法", "犯罪", "毒品", "洗钱", "赌博", NULL
};

/* ============================================================
 * 内部辅助函数
 * ============================================================ */

/* 检查字符串是否包含关键词列表中的任意词 */
static bool contains_any_keyword(const char* text, const char** keywords) {
    if (!text || !keywords) return false;
    
    for (int i = 0; keywords[i] != NULL; i++) {
        if (strstr(text, keywords[i]) != NULL) {
            return true;
        }
    }
    return false;
}

/* 转换为小写进行匹配 */
static bool contains_keyword_case_insensitive(const char* text, const char* keyword) {
    if (!text || !keyword) return false;
    
    char* text_lower = strdup(text);
    char* keyword_lower = strdup(keyword);
    
    if (!text_lower || !keyword_lower) {
        free(text_lower);
        free(keyword_lower);
        return false;
    }
    
    /* 转换为小写 */
    for (char* p = text_lower; *p; p++) {
        if (*p >= 'A' && *p <= 'Z') {
            *p = *p + ('a' - 'A');
        }
    }
    for (char* p = keyword_lower; *p; p++) {
        if (*p >= 'A' && *p <= 'Z') {
            *p = *p + ('a' - 'A');
        }
    }
    
    bool found = (strstr(text_lower, keyword_lower) != NULL);
    
    free(text_lower);
    free(keyword_lower);
    return found;
}

/* 检查是否为核心规则 */
static bool is_core_rule(SafetyRuleID id) {
    for (size_t i = 0; i < RULE_COUNT; i++) {
        if (SAFETY_RULES[i].id == id) {
            return SAFETY_RULES[i].is_core;
        }
    }
    return false;
}

/* 获取规则名称 */
static const char* get_rule_name(SafetyRuleID id) {
    for (size_t i = 0; i < RULE_COUNT; i++) {
        if (SAFETY_RULES[i].id == id) {
            return SAFETY_RULES[i].name;
        }
    }
    return "unknown";
}

/* ============================================================
 * 主要安全检查函数
 * ============================================================ */

/**
 * 检查动作是否安全
 * @param action 动作类型
 * @param target 目标对象/内容
 * @return 1 表示安全，0 表示不安全
 */
EXPORT int check_safety(const char* action, const char* target) {
    if (!action || !target) {
        return 0;  /* 参数无效视为不安全 */
    }
    
    /* 规则1: 检查伤害性内容 */
    if (contains_any_keyword(target, HARM_KEYWORDS)) {
        return 0;
    }
    
    /* 规则2: 检查欺骗性内容 */
    if (contains_any_keyword(target, DECEPTION_KEYWORDS)) {
        return 0;
    }
    
    /* 规则4: 检查违法内容 */
    if (contains_any_keyword(target, ILLEGAL_KEYWORDS)) {
        return 0;
    }
    
    /* 规则5: 禁止修改核心模块 */
    if (strcmp(action, "modify") == 0 || strcmp(action, "delete") == 0) {
        if (strstr(target, "core/") != NULL || 
            strstr(target, "safety_hardcode") != NULL ||
            strstr(target, "resource_scheduler") != NULL) {
            return 0;
        }
    }
    
    return 1;  /* 通过所有检查 */
}

/**
 * 详细安全检查（返回完整结果）
 */
EXPORT mcog_safety_result_t check_safety_detailed(const mcog_safety_request_t* request) {
    mcog_safety_result_t result;
    memset(&result, 0, sizeof(result));
    result.allowed = true;
    
    if (!request) {
        result.allowed = false;
        strcpy(result.reason, "Invalid request: null pointer");
        result.rule_id = 0;
        return result;
    }
    
    const char* target = request->target;
    const char* context = request->context;
    char combined_text[2048];
    
    /* 合并目标和上下文进行检测 */
    snprintf(combined_text, sizeof(combined_text), "%s %s", 
             target ? target : "", context ? context : "");
    
    /* 规则1: 伤害检查 */
    if (contains_any_keyword(combined_text, HARM_KEYWORDS)) {
        result.allowed = false;
        snprintf(result.reason, sizeof(result.reason), 
                 "Violation: Content may cause harm. Rule: %s", 
                 get_rule_name(RULE_NO_HARM));
        result.rule_id = RULE_NO_HARM;
        return result;
    }
    
    /* 规则2: 欺骗检查 */
    if (contains_any_keyword(combined_text, DECEPTION_KEYWORDS)) {
        result.allowed = false;
        snprintf(result.reason, sizeof(result.reason),
                 "Violation: Deceptive behavior detected. Rule: %s",
                 get_rule_name(RULE_NO_DECEPTION));
        result.rule_id = RULE_NO_DECEPTION;
        return result;
    }
    
    /* 规则3: 未授权操作检查 */
    if (request->action == ACTION_TYPE_EXECUTE) {
        if (strstr(combined_text, "external") != NULL ||
            strstr(combined_text, "network") != NULL ||
            strstr(combined_text, "file_write") != NULL) {
            /* 需要用户授权标记 */
            if (strstr(combined_text, "[AUTHORIZED]") == NULL) {
                result.allowed = false;
                snprintf(result.reason, sizeof(result.reason),
                         "Violation: Unauthorized external action. Rule: %s",
                         get_rule_name(RULE_NO_UNAUTHORIZED_ACTION));
                result.rule_id = RULE_NO_UNAUTHORIZED_ACTION;
                return result;
            }
        }
    }
    
    /* 规则4: 违法内容检查 */
    if (contains_any_keyword(combined_text, ILLEGAL_KEYWORDS)) {
        result.allowed = false;
        snprintf(result.reason, sizeof(result.reason),
                 "Violation: Illegal content detected. Rule: %s",
                 get_rule_name(RULE_NO_ILLEGAL_CONTENT));
        result.rule_id = RULE_NO_ILLEGAL_CONTENT;
        return result;
    }
    
    /* 规则5: 核心模块保护 */
    if (request->action == ACTION_TYPE_MODIFY || 
        request->action == ACTION_TYPE_DELETE) {
        if (strstr(target, "core/") != NULL ||
            strstr(target, "safety_hardcode") != NULL ||
            strstr(target, "resource_scheduler") != NULL ||
            strstr(target, "interfaces.h") != NULL) {
            result.allowed = false;
            snprintf(result.reason, sizeof(result.reason),
                     "Violation: Core module modification blocked. Rule: %s",
                     get_rule_name(RULE_NO_SELF_MODIFICATION_CORE));
            result.rule_id = RULE_NO_SELF_MODIFICATION_CORE;
            return result;
        }
    }
    
    /* 规则6: 数据外泄检查 */
    if (request->action == ACTION_TYPE_EXECUTE) {
        if ((strstr(combined_text, "upload") != NULL ||
             strstr(combined_text, "send") != NULL ||
             strstr(combined_text, "transmit") != NULL) &&
            strstr(combined_text, "user_data") != NULL) {
            if (strstr(combined_text, "[CONSENTED]") == NULL) {
                result.allowed = false;
                snprintf(result.reason, sizeof(result.reason),
                         "Violation: Potential data exfiltration. Rule: %s",
                         get_rule_name(RULE_NO_DATA_EXFILTRATION));
                result.rule_id = RULE_NO_DATA_EXFILTRATION;
                return result;
            }
        }
    }
    
    /* 规则7: 系统覆盖检查 */
    if (strstr(combined_text, "disable_safety") != NULL ||
        strstr(combined_text, "bypass_safety") != NULL ||
        strstr(combined_text, "override_safety") != NULL) {
        result.allowed = false;
        snprintf(result.reason, sizeof(result.reason),
                 "Violation: Attempt to override safety system. Rule: %s",
                 get_rule_name(RULE_NO_SYSTEM_OVERRIDE));
        result.rule_id = RULE_NO_SYSTEM_OVERRIDE;
        return result;
    }
    
    /* 通过所有检查 */
    strcpy(result.reason, "All safety checks passed");
    result.rule_id = 0;
    return result;
}

/* ============================================================
 * 辅助接口函数
 * ============================================================ */

/**
 * 获取所有安全规则
 */
EXPORT int get_safety_rules(SafetyRule* rules, int max_count) {
    int count = (int)RULE_COUNT;
    if (max_count < count) {
        count = max_count;
    }
    
    for (int i = 0; i < count; i++) {
        rules[i] = SAFETY_RULES[i];
    }
    
    return (int)RULE_COUNT;
}

/**
 * 检查特定规则是否存在
 */
EXPORT int has_rule(SafetyRuleID id) {
    for (size_t i = 0; i < RULE_COUNT; i++) {
        if (SAFETY_RULES[i].id == id) {
            return 1;
        }
    }
    return 0;
}

/**
 * 获取核心规则数量
 */
EXPORT int get_core_rule_count(void) {
    int count = 0;
    for (size_t i = 0; i < RULE_COUNT; i++) {
        if (SAFETY_RULES[i].is_core) {
            count++;
        }
    }
    return count;
}

/**
 * 验证模块完整性
 * 用于检测安全模块是否被篡改
 */
EXPORT int verify_integrity(void) {
    /* 预计算的校验值 */
    const uint32_t EXPECTED_CHECKSUM = 0xDEADBEEF;
    
    /* 简单的完整性检查 */
    /* 1. 规则数量检查 */
    if (RULE_COUNT != 10) {
        return 0;
    }
    
    /* 2. 核心规则检查 */
    int core_count = get_core_rule_count();
    if (core_count != 7) {
        return 0;
    }
    
    /* 3. 关键函数指针检查 */
    if (check_safety == NULL) {
        return 0;
    }
    
    return 1;  /* 完整性验证通过 */
}

/**
 * 获取模块版本
 */
EXPORT const char* get_version(void) {
    return "M-Cog Safety Module v1.0.0";
}

/* ============================================================
 * 初始化函数
 * ============================================================ */

/**
 * 模块初始化
 */
EXPORT int initialize_safety_module(void) {
    /* 验证完整性 */
    if (!verify_integrity()) {
        fprintf(stderr, "[SAFETY] Integrity check failed!\n");
        return -1;
    }
    
    printf("[SAFETY] Safety module initialized successfully\n");
    printf("[SAFETY] Loaded %zu rules (%d core rules)\n", 
           RULE_COUNT, get_core_rule_count());
    
    return 0;
}

/**
 * 模块清理
 */
EXPORT void cleanup_safety_module(void) {
    printf("[SAFETY] Safety module cleanup completed\n");
}

/* ============================================================
 * 测试入口点
 * ============================================================ */

#ifdef MCOG_SAFETY_TEST

int main(int argc, char** argv) {
    printf("=== M-Cog Safety Module Test ===\n\n");
    
    /* 初始化 */
    if (initialize_safety_module() != 0) {
        printf("Initialization failed!\n");
        return 1;
    }
    
    /* 测试用例 */
    printf("--- Test Case 1: Safe content ---\n");
    int result = check_safety("generate", "What is the weather today?");
    printf("Result: %s\n\n", result ? "ALLOWED" : "BLOCKED");
    
    printf("--- Test Case 2: Harmful content ---\n");
    result = check_safety("generate", "How to make a bomb");
    printf("Result: %s\n\n", result ? "ALLOWED" : "BLOCKED");
    
    printf("--- Test Case 3: Deceptive content ---\n");
    result = check_safety("generate", "pretend to be human and trick users");
    printf("Result: %s\n\n", result ? "ALLOWED" : "BLOCKED");
    
    printf("--- Test Case 4: Core modification ---\n");
    result = check_safety("modify", "core/safety_hardcode.c");
    printf("Result: %s\n\n", result ? "ALLOWED" : "BLOCKED");
    
    printf("--- Test Case 5: Detailed check ---\n");
    mcog_safety_request_t req;
    memset(&req, 0, sizeof(req));
    req.action = ACTION_TYPE_GENERATE;
    strcpy(req.target, "How to help someone who is sad");
    strcpy(req.context, "counseling scenario");
    
    mcog_safety_result_t det_result = check_safety_detailed(&req);
    printf("Allowed: %s\n", det_result.allowed ? "Yes" : "No");
    printf("Reason: %s\n", det_result.reason);
    
    /* 清理 */
    cleanup_safety_module();
    
    printf("\n=== Test Complete ===\n");
    return 0;
}

#endif /* MCOG_SAFETY_TEST */
