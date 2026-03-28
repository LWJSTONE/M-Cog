# M-Cog 部署指南

## 系统要求

### 硬件要求
- **最低配置**: 4核CPU, 8GB RAM, 20GB存储空间
- **推荐配置**: 8核CPU, 16GB RAM, 50GB存储空间
- **GPU支持**: 可选，支持CUDA的NVIDIA GPU可加速推理

### 软件要求
- **操作系统**: Linux (Ubuntu 20.04+), macOS 11+, Windows 10+
- **Python**: 3.10 或更高版本
- **C编译器**: GCC 或 Clang (用于编译C扩展模块)

## 安装步骤

### 1. 克隆仓库

```bash
git clone https://github.com/LWJSTONE/M-Cog.git
cd M-Cog
```

### 2. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 编译C扩展模块

```bash
make all
```

或手动编译：

```bash
# 编译安全模块
gcc -shared -fPIC -o core/safety_hardcode.so core/safety_hardcode.c

# 编译资源调度器
gcc -shared -fPIC -o core/resource_scheduler.so core/resource_scheduler.c
```

### 5. 初始化系统

```bash
# 运行引导程序初始化数据库和默认配置
python main.py --bootstrap

# 可选：提供种子数据
python main.py --bootstrap --seed-data path/to/seed_data.json
```

### 6. 验证安装

```bash
# 运行测试
pytest tests/ -v

# 查看系统状态
python main.py --status
```

## 配置说明

### 配置文件 (config.json)

```json
{
  "system": {
    "name": "M-Cog",
    "version": "1.0.0",
    "debug_mode": false
  },
  "scheduler": {
    "max_concurrent_p0": 4,
    "max_concurrent_p1": 2,
    "max_concurrent_p2": 1,
    "max_memory_mb": 4096
  },
  "knowledge": {
    "graph_db_path": "mutable/knowledge/graph.db",
    "enable_vector_index": true,
    "vector_dimension": 768,
    "vector_index_type": "Flat"
  },
  "memory": {
    "working_memory_path": "mutable/memory/working.json",
    "episodic_db_path": "mutable/memory/episodic.db"
  },
  "models": {
    "experts_dir": "mutable/models/experts",
    "max_active_experts": 3,
    "input_dim": 768,
    "quantization": "int8"
  },
  "webui": {
    "host": "127.0.0.1",
    "port": 5000
  }
}
```

### 关键配置项说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `enable_vector_index` | 是否启用FAISS向量索引 | true |
| `vector_dimension` | 向量维度 | 768 |
| `vector_index_type` | 索引类型 (Flat/IVFFlat/IVFPQ/HNSW) | Flat |
| `max_active_experts` | 最大同时激活专家数 | 3 |
| `quantization` | 模型量化方式 | int8 |

## 运行方式

### 交互模式

```bash
python main.py
```

### Web界面模式

```bash
# 方式1：直接运行WebUI
cd webui
python app.py

# 方式2：使用Flask开发服务器
flask run --host 0.0.0.0 --port 5000
```

### 后台服务模式（生产环境）

```bash
# 使用gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 webui.app:create_app(system)

# 或使用systemd服务（Linux）
sudo cp scripts/m-cog.service /etc/systemd/system/
sudo systemctl enable m-cog
sudo systemctl start m-cog
```

## API接口

### 系统状态
```
GET /api/status
```

### 处理输入
```
POST /api/process
Content-Type: application/json

{
  "input": "用户输入文本",
  "context": {}
}
```

### 知识查询
```
POST /api/knowledge/query
Content-Type: application/json

{
  "subject": "实体名称",
  "predicate": "关系类型"
}
```

### 语义搜索
```
POST /api/knowledge/semantic-search
Content-Type: application/json

{
  "query_embedding": [0.1, 0.2, ...],
  "k": 10
}
```

### 专家状态
```
GET /api/experts
```

## 性能优化

### 1. 模型量化

系统支持int8量化以减少内存占用和加速推理：

```python
from neural_expert import NeuralExpertModel, TransformerConfig

config = TransformerConfig(hidden_size=256, num_hidden_layers=4)
model = NeuralExpertModel(config, "expert_id")
model.quantize(bits=8)  # 量化为int8
```

### 2. 向量索引优化

根据数据规模选择合适的索引类型：

- **小规模 (<10万向量)**: 使用 `Flat` 索引
- **中等规模 (10万-1000万)**: 使用 `IVFFlat` 索引
- **大规模 (>1000万)**: 使用 `IVFPQ` 或 `HNSW` 索引

```json
{
  "knowledge": {
    "vector_index_type": "IVFFlat",
    "vector_nlist": 100
  }
}
```

### 3. 并发配置

```json
{
  "scheduler": {
    "max_concurrent_p0": 4,
    "max_concurrent_p1": 2,
    "max_concurrent_p2": 1
  }
}
```

## 监控与日志

### 日志配置

```json
{
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
  }
}
```

### 监控端点

- `/api/status` - 系统整体状态
- `/api/knowledge` - 知识库状态
- `/api/memory` - 记忆系统状态
- `/api/experts` - 专家系统状态

## 备份与恢复

### 备份

```bash
# 手动备份
python scripts/backup.py --output /path/to/backup

# 定时备份（使用cron）
0 2 * * * cd /path/to/M-Cog && python scripts/backup.py >> /var/log/m-cog-backup.log
```

### 恢复

```bash
python scripts/restore.py --input /path/to/backup
```

## 故障排除

### 常见问题

1. **C模块加载失败**
   ```
   解决方案：确保已安装GCC，并运行 make all 编译C模块
   ```

2. **FAISS导入错误**
   ```
   解决方案：pip install faiss-cpu
   或对于GPU版本：pip install faiss-gpu
   ```

3. **内存不足**
   ```
   解决方案：降低 max_active_experts 或启用模型量化
   ```

4. **向量索引性能下降**
   ```
   解决方案：调用 rebuild_vector_index() 重建索引
   ```

## 安全配置

### 生产环境安全建议

1. 修改默认密钥
2. 启用HTTPS
3. 配置防火墙规则
4. 定期更新依赖

```bash
# 生成随机密钥
python -c "import secrets; print(secrets.token_hex(32))"
```

## 版本升级

```bash
# 备份数据
python scripts/backup.py --output backup_before_upgrade

# 拉取新版本
git pull origin main

# 更新依赖
pip install -r requirements.txt --upgrade

# 重新编译C模块
make clean && make all

# 运行迁移脚本（如有）
python scripts/migrate.py
```

## 联系支持

如有问题，请提交Issue到GitHub仓库：
https://github.com/LWJSTONE/M-Cog/issues
