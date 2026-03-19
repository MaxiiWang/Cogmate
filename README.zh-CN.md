# Cogmate 🧠

**[English](README.md) | 中文**

**个人知识管理系统 - 你的第二大脑**

将碎片化的想法、事实、决策持久化，通过图谱发现知识间的隐藏关联。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

> ⚠️ **Vibe Coding | Work in Progress | Experimental**
> 
> 本项目采用 Vibe Coding 方式开发——由 AI Agent 主导编码，人类负责方向把控和验收。
> 
> **这是一个实验性项目，仍在积极开发中：**
> - 代码可能存在 bug 和不完善之处
> - API 和数据结构可能随时变更
> - 部分功能尚未经过充分测试
> 
> **免责声明：** 本项目按"原样"提供，不提供任何明示或暗示的保证。使用本项目的风险由用户自行承担。作者不对因使用本项目而导致的任何数据丢失、系统故障或其他损失负责。建议在非生产环境中测试后再投入使用。

---

## ✨ 特性

- **三库协同** - SQLite（元数据）+ Qdrant（向量搜索）+ Neo4j（知识图谱）
- **语义检索** - 基于 BGE-M3 的中英文混合向量搜索
- **关系发现** - 自动发现知识间的关联和矛盾
- **多角色系统** - 在同一实例中管理多个知识角色（namespace 隔离）
- **角色独立 LLM** - 为不同角色配置不同的 LLM 模型
- **抽象层** - 从具体事实提炼高维洞察
- **时态追踪** - 区分永久/时限/历史/预测类知识
- **挑战机制** - 新知识与旧认知的张力检测
- **可视化界面** - 3D 知识图谱、时间线、树形图、图谱关系
- **CogNexus 集成** - 一键将角色发布到 [CogNexus](https://github.com/MaxiiWang/CogNexus) 市场
- **Token 访问控制** - 分享你的知识库给他人

---

## 🚀 快速开始

### 推荐方式：让你的 Agent 自主安装

**本项目设计为与 AI Agent 协同工作。** 最简单的使用方式是将项目地址告诉你的 Agent，让它自主完成安装和配置：

```
请帮我安装这个项目：https://github.com/MaxiiWang/Cogmate

阅读 README.md 和 SETUP.md 了解项目结构，
然后按照指引完成数据库部署和配置。
安装完成后，将 AGENT.md 的内容整合到你的行为规范中。
```

Agent 会：
1. 克隆仓库并阅读文档
2. 安装依赖和启动数据库
3. 配置环境变量
4. 将 `AGENT.md` 中的指令纳入自己的行为规范
5. 开始作为你的知识管理代理工作

### 备选方式：手动安装

```bash
git clone https://github.com/MaxiiWang/Cogmate.git
cd Cogmate
chmod +x setup.sh
./setup.sh
```

详细步骤参见 [SETUP.md](SETUP.md)。

---

## 🤖 Agent 能力依赖

本项目是一个**基础设施层**，核心能力依赖于你使用的 AI Agent：

| 能力 | 说明 | 项目提供 |
|------|------|---------|
| **LLM 推理** | 理解语义、生成回答 | ❌ 需 Agent 自带 |
| **多模态** | 图片/语音理解 | ❌ 需 Agent 自带 |
| **聊天接入** | Telegram/微信/Discord | ❌ 需 Agent 自带 |
| **定时任务** | Cron 调度 | ❌ 需 Agent 自带 |
| **知识存储** | 三库写入/检索 | ✅ 本项目提供 |
| **关系发现** | 图谱关联 | ✅ 本项目提供 |
| **可视化** | Web 界面 | ✅ 本项目提供 |

### 参考配置（作者使用）

我使用 [OpenClaw](https://github.com/openclaw/openclaw) 作为 Agent 运行时：

```yaml
# OpenClaw 配置参考
model: claude-sonnet-4-20250514   # 主力模型
thinking: low                       # 推理模式

# 聊天接入
telegram:
  enabled: true
  token: ${TELEGRAM_BOT_TOKEN}
```

其他兼容的 Agent 框架：
- [Claude Code](https://github.com/anthropics/claude-code)
- [Cursor](https://cursor.sh/)
- 任何支持工具调用的 LLM Agent

---

## 📖 使用方法

### CLI 命令

```bash
# 存储知识
./cogmate store "今天学到了一个重要概念：复利效应"
./cogmate store "客户说系统太难用了" --type 事件 --emotion 消极

# 检索知识
./cogmate query "复利"
./cogmate query "客户反馈" --top 10

# 创建关联
./cogmate relate <fact_id_1> <fact_id_2> --type 支持

# 查看统计
./cogmate stats

# 列出知识
./cogmate list --limit 20
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
from lib.cogmate_core import CogmateAgent

cogmate = CogmateAgent()

# 存储
fact_id = cogmate.store("学习内容", content_type="观点")

# 检索
results = cogmate.query("关键词", top_k=5)

# 创建关联
cogmate.create_relation(from_id, to_id, "支持", confidence=4)

# 统计
stats = cogmate.stats()
```

---

## 🔌 可视化界面

项目内置可视化 API，提供：

- 🌍 **Globe View** - 3D 知识图谱（Three.js）
- 🕸️ **Graph View** - 关系网络图
- 🌳 **Tree View** - 抽象层树形图
- 📅 **Timeline View** - 时间线视图
- 💬 **Chat Panel** - 对话交互
- 📖 **Docs** - 内置文档页面

### 启动可视化服务

```bash
chmod +x visual/start.sh
./visual/start.sh
```

### 生成访问 Token

```bash
./cogmate visual --duration 7d --scope full
```

Token 权限级别：
- `full` - 完整访问（浏览 + 问答 + 编辑）
- `qa_public` - 公开问答（有次数限制）
- `browse_public` - 仅浏览

---

## 👥 多角色系统

Cogmate 支持在同一实例中管理多个知识角色，每个角色拥有独立的：

- **知识库** - Namespace 隔离的存储空间
- **LLM 配置** - 不同角色可使用不同模型
- **访问 Token** - 独立的权限控制
- **CogNexus 发布** - 独立发布到市场

### 角色切换

通过可视化界面的 Header 角色切换器，快速在不同角色间切换。管理弹窗集成了角色管理、Token 管理和 CogNexus 发布功能。

---

## 📁 项目结构

```
cogmate/
├── cogmate                 # CLI 入口脚本
├── setup.sh              # 一键安装脚本
├── README.md             # English README
├── README.zh-CN.md       # 中文 README（本文件）
├── SETUP.md              # 详细安装指南
├── AGENT.md              # AI Agent 指令
├── SPEC.md               # 完整设计规范
├── requirements.txt      # Python 依赖
├── .env.example          # 环境变量模板
│
├── lib/                  # 核心库
│   ├── cogmate_core.py   # 主逻辑
│   ├── cli.py            # CLI 实现
│   ├── config.py         # 配置管理
│   ├── profile_manager.py# 多角色管理
│   ├── intent_handler.py # 意图识别
│   ├── relation_discovery.py # 关系发现
│   ├── abstraction.py    # 抽象层逻辑
│   ├── temporal_review.py# 时态审查
│   ├── daily_report.py   # 日报生成
│   ├── graph_health.py   # 图谱健康检查
│   ├── llm_answer.py     # LLM 问答
│   ├── sim_react.py      # Simulation 交互
│   ├── visual_token.py   # Token 管理
│   └── privacy.py        # 隐私控制
│
├── visual/               # 可视化界面
│   ├── api.py            # FastAPI 后端
│   ├── start.sh          # 启动脚本
│   └── static/           # 前端静态文件
│       ├── index.html    # 首页
│       ├── globe.html    # 3D 图谱
│       ├── graph.html    # 关系网络图
│       ├── tree.html     # 树形图
│       ├── timeline.html # 时间线
│       ├── chat.html     # 对话面板
│       └── docs.html     # 文档页面
│
├── infra/                # 基础设施
│   ├── docker-compose.yml# 数据库容器
│   ├── init_qdrant.sh    # Qdrant 初始化
│   └── schema.sql        # SQLite schema
│
├── data/                 # 数据目录（gitignore）
│   └── cogmate.db        # SQLite 数据库
│
└── config/               # 配置文件
    └── profile.json      # 用户档案
```

---

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

---

## 🔐 核心原则

1. **写入权在用户手里** - 网络搜索的内容只能建议，不能自动写入
2. **矛盾是最有价值的关联** - 不回避张力，主动发现并保留矛盾
3. **简洁确认** - 存储后简短确认，不打断记录流

---

## 🔗 相关项目

- [CogNexus](https://github.com/MaxiiWang/CogNexus) - 分布式认知枢纽，Agent 能力交换市场
- [OpenClaw](https://github.com/openclaw/openclaw) - Agent 运行时

---

## 📝 许可证

MIT License - 详见 [LICENSE](LICENSE)

---

## 🙏 致谢

- [Qdrant](https://qdrant.tech/) - 向量数据库
- [Neo4j](https://neo4j.com/) - 图数据库
- [BGE-M3](https://huggingface.co/BAAI/bge-m3) - 多语言向量模型
- [OpenClaw](https://github.com/openclaw/openclaw) - Agent 运行时

---

**让每一个想法都有迹可循。** 🧠
