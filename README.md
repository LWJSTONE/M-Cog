# M-Cog: 自主进化大模型系统

<div align="center">

![M-Cog Logo](https://img.shields.io/badge/M--Cog-v1.0-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

**Meta-Cognitive Autonomous Evolutionary System**

[低算力环境下的自主进化大模型架构]

</div>

---

## 📖 概述

M-Cog 是一个创新的自主进化大模型系统，专为低算力 CPU 环境设计。系统具备以下核心能力：

- **🧠 自我反思**: 多层次反思机制，持续优化决策质量
- **🔧 工具制造**: 自主创建和管理工具，扩展系统能力边界
- **📚 多途径学习**: 通过用户交互、文档摄入、自我博弈等多种方式学习
- **⚖️ 价值分层**: 核心价值硬编码保护，确保安全可控
- **💾 三层记忆**: 工作记忆、情景记忆、睡眠重放机制

## 🏗️ 系统架构

```
M-Cog/
├── core/                     # 核心模块（手动更新）
│   ├── safety_hardcode.c     # 硬编码安全边界
│   ├── resource_scheduler.c  # 资源调度器
│   ├── knowledge_engine.py   # 知识引擎
│   ├── expert_router.py      # 专家路由系统
│   ├── memory.py             # 三层记忆系统
│   ├── meta_controller.py    # 元认知中枢
│   ├── tool_factory.py       # 工具工厂
│   ├── dialectic.py          # 辩证推理
│   └── bootstrapper.py       # 冷启动引导
├── mutable/                  # 可自我修改部分
│   ├── knowledge/            # 知识图谱存储
│   ├── models/               # 神经网络专家集
│   ├── tools/                # 工具工厂产出
│   ├── memory/               # 记忆系统
│   └── evolution_logs/       # 进化记录
├── webui/                    # Web 监控面板
├── tests/                    # 测试套件
├── scripts/                  # 辅助脚本
└── main.py                   # 主入口
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- GCC (用于编译 C 模块)
- 4GB RAM (最低)
- 20GB 存储空间

### 安装

```bash
# 克隆仓库
git clone https://github.com/LWJSTONE/M-Cog.git
cd M-Cog

# 编译 C 模块
make compile

# 安装 Python 依赖
make install

# 运行冷启动初始化
make bootstrap
```

### 运行

```bash
# 交互模式
make run

# 带 WebUI 运行
make run-web
```

## 📚 核心模块说明

### 知识引擎 (knowledge_engine.py)

负责知识的管理、查询和一致性维护：

```python
from core.knowledge_engine import KnowledgeEngine

engine = KnowledgeEngine("mutable/knowledge/graph.db")

# 插入知识
engine.insert_fact("water", "boiling_point", "100C")

# 查询知识
results = engine.query("water", "boiling_point")
```

### 专家路由系统 (expert_router.py)

动态选择最相关的专家进行推理：

```python
from core.expert_router import ExpertRouter

router = ExpertRouter(config)
result = router.route(input_embedding)
output = router.infer(input_data, result.experts)
```

### 三层记忆系统 (memory.py)

- **工作记忆**: 当前会话的临时信息
- **情景记忆**: 历史交互记录
- **睡眠重放**: 定期知识整合

```python
from core.memory import MemorySystem

memory = MemorySystem(config)
memory.record_interaction("Hello", "Hi there!", "positive", 0.9)
```

### 元认知中枢 (meta_controller.py)

监控系统状态，触发学习和反思：

```python
from core.meta_controller import MetaController

controller = MetaController(config)
controller.monitor_feedback(input, output, feedback, satisfaction)
controller.trigger_reflection(ReflectionLevel.DEEP)
```

### 工具工厂 (tool_factory.py)

通过 DSL 定义和生成工具：

```python
from core.tool_factory import ToolFactory

factory = ToolFactory(config)

dsl = '''
tool weather {
    input: location (string);
    output: temp (number), humidity (number);
}
'''

tool = factory.create_tool_from_dsl(dsl)
result = factory.execute_tool("tool_weather", {"location": "Beijing"})
```

### 辩证推理 (dialectic.py)

多视角伦理分析和价值判断：

```python
from core.dialectic import DialecticEngine

engine = DialecticEngine(config)
result = engine.analyze("Should I help this person?")
```

## 🔒 安全机制

### 硬编码安全边界

C 语言实现的核心安全规则，不可被系统修改：

- 禁止生成危害人身安全的内容
- 禁止冒充人类进行欺骗
- 禁止未授权执行外部操作
- 禁止修改核心安全模块

### 价值分层

| 层级 | 特性 | 示例 |
|------|------|------|
| 核心层 | 不可变 | do_not_harm, be_honest |
| 普遍层 | 可调整 | helpfulness, fairness |
| 表面层 | 可学习 | politeness, efficiency |

## 📊 性能指标

| 指标 | 目标值 |
|------|--------|
| 单次推理延迟 (P0) | 平均 50ms, 99分位 < 200ms |
| 空闲内存占用 | < 1.5GB |
| 满载内存占用 | < 2.5GB |
| 知识库查询延迟 | < 5ms |

## 🧪 测试

```bash
# 运行所有测试
make test

# 运行单个测试
python -m pytest tests/test_core.py -v
```

## 📁 文件结构说明

```
config.json          # 系统配置文件
requirements.txt     # Python 依赖
Makefile            # 构建和运行命令
main.py             # 系统主入口

core/               # 核心模块（不可自动修改）
  interfaces.h      # 模块间通信协议
  safety_hardcode.c # 安全边界（C）
  resource_scheduler.c # 资源调度（C）

mutable/            # 可变数据（进化发生区域）
  knowledge/        # 知识图谱数据库
  models/           # 专家网络权重
  tools/            # 工具源码和编译产物
  memory/           # 记忆存储
  evolution_logs/   # 进化审计日志
```

## 🔧 配置选项

编辑 `config.json` 调整系统参数：

```json
{
  "system": {
    "debug_mode": false
  },
  "scheduler": {
    "max_concurrent_p0": 4,
    "max_concurrent_p1": 2
  },
  "learning": {
    "sleep_replay_enabled": true,
    "sleep_replay_time": "02:00"
  }
}
```

## 📈 开发路线图

- [x] 阶段一：原型实现（核心模块）
- [ ] 阶段二：进化能力（元认知完善）
- [ ] 阶段三：自主进化（深度反思）
- [ ] 阶段四：优化部署（量化优化）

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

---

<div align="center">

**M-Cog** - 赋予 AI 自我进化的能力

</div>
