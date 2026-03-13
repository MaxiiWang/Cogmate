# Brain Agent 🧠

**个人知识管理系统 - 你的第二大脑**

将碎片化的想法、事实、决策持久化，通过图谱发现知识间的隐藏关联。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ 特性

- **三库协同** - SQLite（元数据）+ Qdrant（向量搜索）+ Neo4j（知识图谱）
- **语义检索** - 基于 BGE-M3 的中英文混合向量搜索
- **关系发现** - 自动发现知识间的关联和矛盾
- **抽象层** - 从具体事实提炼高维洞察
- **时态追踪** - 区分永久/时限/历史/预测类知识
- **挑战机制** - 新知识与旧认知的张力检测
- **可视化界面** - 3D 知识图谱浏览
- **Token 访问控制** - 分享你的知识库给他人

## 🚀 快速开始

### 方式一：一键安装

```bash
git clone https://github.com/yourusername/brain-agent.git
cd brain-agent
chmod +x setup.sh
./setup.sh
```

### 方式二：手动安装

参见 [SETUP.md](SETUP.md) 获取详细步骤。

### 验证安装

```bash
./brain stats
```

输出示例：
```
🧠 Brain Agent 状态
━━━━━━━━━━━━━━━━━━━━
📊 SQLite:  0 条记录
🔍 Qdrant:  0 向量
🕸️  Neo4j:   0 节点 | 0 边
```

## 📖 使用方法

### CLI 命令

```bash
# 存储知识
./brain store "今天学到了一个重要概念：复利效应"
./brain store "客户说系统太难用了" --type 事件 --emotion 消极

# 检索知识
./brain query "复利"
./brain query "客户反馈" --top 10

# 创建关联
./brain relate <fact_id_1> <fact_id_2> --type 支持

# 查看统计
./brain stats

# 列出知识
./brain list --limit 20
```

### 知识类型

| 类型 | 说明 | 示例 |
|------|------|------|
| 事件 | 发生的事情 | "今天开会讨论了新方案" |
| 观点 | 个人看法 | "我认为远程办公效率更高" |
| 情绪 | 情感状态 | "对这个项目感到焦虑" |
| 资讯 | 外部信息 | "GPT-5 预计明年发布" |
| 决策 | 做出的决定 | "决定下周开始健身" |

### Python API

```python
from lib.brain_core import BrainAgent

brain = BrainAgent()

# 存储
fact_id = brain.store("学习内容", content_type="观点")

# 检索
results = brain.query("关键词", top_k=5)

# 创建关联
brain.create_relation(from_id, to_id, "支持", confidence=4)

# 统计
stats = brain.stats()
```

## 🤖 AI Agent 集成

本项目专为 AI Agent（如 Claude、GPT）设计，可作为其长期记忆和知识库。

### OpenClaw 集成

将 `AGENT.md` 放入你的 OpenClaw workspace，Agent 会自动继承所有指令和行为规范。

```bash
cp AGENT.md ~/.openclaw/workspace/
```

### 定时任务

项目包含预设的定时任务脚本：

| 脚本 | 频率 | 功能 |
|------|------|------|
| `daily_morning.sh` | 每天 09:00 | 晨间知识回顾 |
| `daily_evening.sh` | 每天 20:00 | 晚间知识整理 |
| `weekly_report.sh` | 每周日 20:00 | 周报生成 |
| `monthly_temporal_review.sh` | 每月 1 日 | 时效性知识审查 |

详见 [AGENT.md](AGENT.md) 了解如何配置。

## 🔌 可视化界面

项目内置可视化 API，提供：

- 🌍 **Globe View** - 3D 知识图谱（Three.js）
- 🌳 **Tree View** - 抽象层树形图
- 📅 **Timeline View** - 时间线视图
- 💬 **Chat Panel** - 对话交互

### 启动可视化服务

```bash
chmod +x visual/start.sh
./visual/start.sh
```

或手动启动：

```bash
cd visual && python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000`

### 生成访问 Token

```bash
./brain visual --duration 7d --scope full
```

输出示例：
```
🔗 访问链接: http://localhost:8000?token=abc123...
```

Token 权限级别：
- `full` - 完整访问（浏览 + 问答 + 编辑）
- `qa_public` - 公开问答（有次数限制）
- `browse_public` - 仅浏览

## 📁 项目结构

```
brain-agent/
├── brain                 # CLI 入口脚本
├── setup.sh              # 一键安装脚本
├── README.md             # 本文件
├── SETUP.md              # 详细安装指南
├── AGENT.md              # AI Agent 指令
├── SPEC.md               # 完整设计规范
├── requirements.txt      # Python 依赖
├── .env.example          # 环境变量模板
│
├── lib/                  # 核心库
│   ├── brain_core.py     # 主逻辑
│   ├── cli.py            # CLI 实现
│   ├── config.py         # 配置管理
│   ├── intent_handler.py # 意图识别
│   ├── abstraction.py    # 抽象层逻辑
│   ├── temporal_review.py# 时态审查
│   ├── daily_report.py   # 日报生成
│   └── visual_token.py   # Token 管理
│
├── visual/               # 可视化界面
│   ├── api.py            # FastAPI 后端
│   ├── start.sh          # 启动脚本
│   └── static/           # 前端静态文件
│       ├── index.html    # 主页
│       ├── globe.html    # 3D 图谱
│       ├── tree.html     # 树形图
│       ├── timeline.html # 时间线
│       └── chat.html     # 对话面板
│
├── infra/                # 基础设施
│   ├── docker-compose.yml# 数据库容器
│   ├── init_qdrant.sh    # Qdrant 初始化
│   └── schema.sql        # SQLite schema
│
├── scripts/              # 定时任务脚本
│   ├── daily_morning.sh
│   ├── daily_evening.sh
│   ├── weekly_report.sh
│   └── monthly_temporal_review.sh
│
├── data/                 # 数据目录（gitignore）
│   └── brain.db          # SQLite 数据库
│
└── config/               # 配置文件
    └── profile.json      # 用户档案
```

## ⚙️ 配置

### 环境变量

复制 `.env.example` 为 `.env` 并配置：

```bash
# 数据库连接
BRAIN_NEO4J_URI=bolt://localhost:7687
BRAIN_NEO4J_USER=neo4j
BRAIN_NEO4J_PASSWORD=your_password

BRAIN_QDRANT_HOST=localhost
BRAIN_QDRANT_PORT=6333

# 可选：LLM API（用于抽象层和挑战机制）
ANTHROPIC_API_KEY=sk-ant-xxx
```

### 用户档案

编辑 `config/profile.json` 设置你的信息：

```json
{
  "name": "你的名字",
  "title": "一句话介绍",
  "bio": "知识库描述"
}
```

## 🔐 核心原则

1. **写入权在用户手里** - 网络搜索的内容只能建议，不能自动写入
2. **矛盾是最有价值的关联** - 不回避张力，主动发现并保留矛盾
3. **简洁确认** - 存储后简短确认，不打断记录流

## 🛠️ 开发

```bash
# 运行测试
python -m pytest tests/

# 代码风格
black lib/
```

## 📝 许可证

MIT License - 详见 [LICENSE](LICENSE)

## 🙏 致谢

- [Qdrant](https://qdrant.tech/) - 向量数据库
- [Neo4j](https://neo4j.com/) - 图数据库
- [BGE-M3](https://huggingface.co/BAAI/bge-m3) - 多语言向量模型
- [OpenClaw](https://github.com/openclaw/openclaw) - Agent 运行时

---

**让每一个想法都有迹可循。** 🧠
