# Brain Agent 安装指南

本指南帮助你从零开始搭建 Brain Agent 个人知识管理系统。

## 系统要求

- **操作系统**: Linux / macOS / Windows (WSL2)
- **Python**: 3.10+
- **Docker**: 20.0+ (用于数据库)
- **内存**: 建议 4GB+（Neo4j 需要）
- **磁盘**: 建议 10GB+（向量索引会增长）

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/brain-agent.git
cd brain-agent
```

### 2. 创建 Python 虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows
```

### 3. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

依赖包括：
- `qdrant-client` - Qdrant 向量数据库客户端
- `neo4j` - Neo4j 图数据库驱动
- `sentence-transformers` - BGE-M3 向量模型
- `fastapi`, `uvicorn` - API 服务（可视化用）
- `httpx` - HTTP 客户端
- `python-dotenv` - 环境变量管理

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# 必需：数据库配置
BRAIN_NEO4J_URI=bolt://localhost:7687
BRAIN_NEO4J_USER=neo4j
BRAIN_NEO4J_PASSWORD=your_secure_password  # 请修改！

BRAIN_QDRANT_HOST=localhost
BRAIN_QDRANT_PORT=6333
BRAIN_COLLECTION_NAME=facts

# 可选：LLM API（用于抽象层、挑战机制）
ANTHROPIC_API_KEY=sk-ant-xxx

# 可选：可视化公开 URL
VISUAL_PUBLIC_URL=http://localhost:8000
```

### 5. 启动数据库

```bash
cd infra
sudo docker compose up -d
```

等待约 30 秒让数据库完全启动。

验证数据库状态：

```bash
# Qdrant
curl http://localhost:6333/collections

# Neo4j（浏览器访问）
# http://localhost:7474
# 用户名: neo4j
# 密码: 你在 .env 中设置的密码
```

### 6. 初始化 Qdrant 集合

```bash
chmod +x infra/init_qdrant.sh
./infra/init_qdrant.sh
```

这会创建 `facts` 集合，使用 BGE-M3 的 1024 维向量。

### 7. 初始化 SQLite

首次运行 CLI 会自动创建 SQLite 数据库：

```bash
./brain stats
```

### 8. 验证安装

```bash
# 存储一条测试数据
./brain store "这是一条测试数据"

# 检索
./brain query "测试"

# 查看统计
./brain stats
```

如果看到类似输出，说明安装成功：

```
🧠 Brain Agent 状态
━━━━━━━━━━━━━━━━━━━━
📊 SQLite:  1 条记录
🔍 Qdrant:  1 向量
🕸️  Neo4j:   1 节点 | 0 边
```

---

## 可视化界面

可视化功能已集成在项目中。

### 1. 安装额外依赖

```bash
pip install -r visual/requirements.txt
```

### 2. 启动服务

```bash
chmod +x visual/start.sh
./visual/start.sh
```

或手动启动：

```bash
cd visual
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

### 3. 生成访问 Token

```bash
./brain visual --duration 7d --scope full
```

或使用 Python：

```python
from lib.visual_token import generate_token
result = generate_token(duration='7d', scope='full')
print(f"访问链接: http://localhost:8000?token={result['token']}")
```

### 4. 访问界面

打开浏览器访问生成的链接，即可看到：

- **Globe View** - 3D 知识图谱
- **Tree View** - 抽象层树形图  
- **Timeline View** - 时间线视图
- **Chat Panel** - 对话交互

---

## AI Agent 集成

### OpenClaw 用户

将 `AGENT.md` 复制到你的 OpenClaw workspace：

```bash
cp AGENT.md ~/.openclaw/workspace/BRAIN_AGENT.md
```

Agent 会自动读取并继承所有指令。

### 定时任务配置

使用 OpenClaw 的 cron 功能配置定时任务：

```bash
# 在 OpenClaw 中添加定时任务
openclaw cron add --schedule "0 9 * * *" --task "执行晨间回顾"
openclaw cron add --schedule "0 20 * * *" --task "执行晚间报告"
openclaw cron add --schedule "0 20 * * 0" --task "生成周报"
```

或直接编辑 `~/.openclaw/workspace/HEARTBEAT.md`。

### 其他 Agent 框架

核心 API 位于 `lib/brain_core.py`，可以集成到任何 Agent 框架：

```python
from brain_agent.lib.brain_core import BrainAgent

# 初始化
brain = BrainAgent()

# 在 Agent 的工具函数中使用
def store_knowledge(content: str, content_type: str = "观点"):
    return brain.store(content, content_type=content_type)

def query_knowledge(query: str, top_k: int = 5):
    return brain.query(query, top_k=top_k)
```

---

## 故障排除

### Qdrant 连接失败

```bash
# 检查容器状态
sudo docker ps | grep qdrant

# 查看日志
sudo docker logs brain-qdrant

# 重启
sudo docker restart brain-qdrant
```

### Neo4j 连接失败

```bash
# 检查容器状态
sudo docker ps | grep neo4j

# 查看日志
sudo docker logs brain-neo4j

# 常见问题：密码不匹配
# 解决：删除数据卷重新初始化
sudo docker compose down -v
sudo docker compose up -d
```

### 向量模型下载慢

首次运行会下载 BGE-M3 模型（约 2GB）。可以手动下载：

```bash
# 使用 huggingface-cli
huggingface-cli download BAAI/bge-m3 --local-dir ~/.cache/huggingface/hub/models--BAAI--bge-m3

# 或设置镜像
export HF_ENDPOINT=https://hf-mirror.com
```

### 内存不足

Neo4j 默认使用较多内存。可以在 `docker-compose.yml` 中限制：

```yaml
neo4j:
  environment:
    - NEO4J_server_memory_heap_max__size=512m
```

---

## 升级指南

```bash
cd brain-agent
git pull origin main

# 重新安装依赖
pip install -r requirements.txt

# 数据库迁移（如果有）
# 查看 CHANGELOG.md 了解是否需要迁移
```

---

## 下一步

1. 阅读 [SPEC.md](SPEC.md) 了解完整设计
2. 阅读 [AGENT.md](AGENT.md) 配置你的 AI Agent
3. 开始记录你的第一条知识！

```bash
./brain store "开始使用 Brain Agent 管理知识"
```
