# Cogmate 🧠

**English | [中文](README.zh-CN.md)**

**Personal Knowledge Management System - Your Second Brain**

Persist fragmented thoughts, facts, and decisions. Discover hidden connections through knowledge graphs.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

> ⚠️ **Vibe Coding | Work in Progress | Experimental**
> 
> This project is developed using Vibe Coding — AI Agents lead the coding, humans steer direction and review.
> 
> **This is an experimental project under active development:**
> - Code may contain bugs and rough edges
> - APIs and data structures may change at any time
> - Some features have not been thoroughly tested
> 
> **Disclaimer:** This project is provided "as-is" without warranty of any kind. Use at your own risk. The author is not responsible for any data loss, system failures, or other damages resulting from the use of this project. Test in a non-production environment before deploying.

---

## ✨ Features

- **Triple-Store Architecture** - SQLite (metadata) + Qdrant (vector search) + Neo4j (knowledge graph)
- **Semantic Search** - Bilingual (Chinese/English) vector search powered by BGE-M3
- **Relation Discovery** - Automatically find connections and contradictions between knowledge
- **Multi-Profile System** - Manage multiple knowledge personas in one instance (namespace-isolated)
- **Per-Profile LLM** - Configure different LLM models for different profiles
- **Abstraction Layer** - Distill high-level insights from concrete facts
- **Temporal Tracking** - Distinguish permanent / time-bound / historical / predictive knowledge
- **Challenge Mechanism** - Detect tension between new knowledge and existing beliefs
- **Visual Interface** - 3D knowledge globe, timeline, tree view, graph network
- **CogNexus Integration** - One-click publish profiles to the [CogNexus](https://github.com/MaxiiWang/CogNexus) marketplace
- **Token Access Control** - Share your knowledge base with others via scoped tokens

---

## 🚀 Quick Start

### Recommended: Let Your Agent Install It

**This project is designed to work with AI Agents.** The easiest way to get started is to hand the repo URL to your agent:

```
Please install this project: https://github.com/MaxiiWang/Cogmate

Read README.md and SETUP.md to understand the project structure,
then follow the guide to deploy databases and configure.
After setup, integrate AGENT.md into your behavior rules.
```

Your agent will:
1. Clone the repo and read the docs
2. Install dependencies and start databases
3. Configure environment variables
4. Integrate `AGENT.md` instructions into its behavior
5. Start working as your knowledge management agent

### Alternative: Manual Installation

```bash
git clone https://github.com/MaxiiWang/Cogmate.git
cd Cogmate
chmod +x setup.sh
./setup.sh
```

See [SETUP.md](SETUP.md) for detailed steps.

---

## 🤖 Agent Capability Dependencies

This project is an **infrastructure layer** — core capabilities depend on your AI Agent:

| Capability | Description | Provided by Project |
|------------|-------------|-------------------|
| **LLM Reasoning** | Semantic understanding, response generation | ❌ Requires Agent |
| **Multimodal** | Image/voice understanding | ❌ Requires Agent |
| **Chat Integration** | Telegram/WeChat/Discord | ❌ Requires Agent |
| **Scheduled Tasks** | Cron scheduling | ❌ Requires Agent |
| **Knowledge Storage** | Triple-store read/write | ✅ Provided |
| **Relation Discovery** | Graph-based connections | ✅ Provided |
| **Visualization** | Web interface | ✅ Provided |

### Reference Setup (Author's Config)

I use [OpenClaw](https://github.com/openclaw/openclaw) as the Agent runtime:

```yaml
# OpenClaw config reference
model: claude-sonnet-4-20250514   # Primary model
thinking: low                       # Reasoning mode

# Chat integration
telegram:
  enabled: true
  token: ${TELEGRAM_BOT_TOKEN}
```

Other compatible Agent frameworks:
- [Claude Code](https://github.com/anthropics/claude-code)
- [Cursor](https://cursor.sh/)
- Any LLM Agent with tool-calling support

---

## 📖 Usage

### CLI Commands

```bash
# Store knowledge
./cogmate store "Learned an important concept today: compound interest effect"
./cogmate store "Client says the system is too hard to use" --type event --emotion negative

# Query knowledge
./cogmate query "compound interest"
./cogmate query "client feedback" --top 10

# Create relations
./cogmate relate <fact_id_1> <fact_id_2> --type supports

# View statistics
./cogmate stats

# List knowledge
./cogmate list --limit 20
```

### Knowledge Types

| Type | Description | Example |
|------|-------------|---------|
| Event | Something that happened | "Had a meeting about the new plan today" |
| Opinion | Personal viewpoint | "I think remote work is more productive" |
| Emotion | Emotional state | "Feeling anxious about this project" |
| Info | External information | "GPT-5 expected next year" |
| Decision | A decision made | "Decided to start exercising next week" |

### Python API

```python
from lib.cogmate_core import CogmateAgent

cogmate = CogmateAgent()

# Store
fact_id = cogmate.store("Learning content", content_type="opinion")

# Query
results = cogmate.query("keyword", top_k=5)

# Create relation
cogmate.create_relation(from_id, to_id, "supports", confidence=4)

# Statistics
stats = cogmate.stats()
```

---

## 🔌 Visual Interface

Built-in visualization API with:

- 🌍 **Globe View** - 3D knowledge graph (Three.js)
- 🕸️ **Graph View** - Relation network graph
- 🌳 **Tree View** - Abstraction layer tree
- 📅 **Timeline View** - Chronological timeline
- 💬 **Chat Panel** - Conversational interaction
- 📖 **Docs** - Built-in documentation page

### Start the Visual Server

```bash
chmod +x visual/start.sh
./visual/start.sh
```

### Generate Access Tokens

```bash
./cogmate visual --duration 7d --scope full
```

Token permission levels:
- `full` - Full access (browse + Q&A + edit)
- `qa_public` - Public Q&A (rate-limited)
- `browse_public` - Browse only

---

## 👥 Multi-Profile System

Cogmate supports multiple knowledge profiles within a single instance, each with:

- **Isolated Knowledge Base** - Namespace-separated storage
- **Independent LLM Config** - Different models per profile
- **Separate Access Tokens** - Independent permission control
- **CogNexus Publishing** - Publish each profile independently to the marketplace

Switch between profiles via the header profile switcher in the visual interface. The management modal integrates profile management, token management, and CogNexus publishing.

---

## 📁 Project Structure

```
cogmate/
├── cogmate               # CLI entry script
├── setup.sh              # One-click setup
├── README.md             # English README (this file)
├── README.zh-CN.md       # 中文 README
├── SETUP.md              # Detailed setup guide
├── AGENT.md              # AI Agent instructions
├── SPEC.md               # Full design specification
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
│
├── lib/                  # Core library
│   ├── cogmate_core.py   # Main logic
│   ├── cli.py            # CLI implementation
│   ├── config.py         # Configuration
│   ├── profile_manager.py# Multi-profile management
│   ├── intent_handler.py # Intent recognition
│   ├── relation_discovery.py # Relation discovery
│   ├── abstraction.py    # Abstraction layer
│   ├── temporal_review.py# Temporal review
│   ├── daily_report.py   # Daily report generation
│   ├── graph_health.py   # Graph health check
│   ├── llm_answer.py     # LLM Q&A
│   ├── sim_react.py      # Simulation interaction
│   ├── visual_token.py   # Token management
│   └── privacy.py        # Privacy controls
│
├── visual/               # Visual interface
│   ├── api.py            # FastAPI backend
│   ├── start.sh          # Start script
│   └── static/           # Frontend static files
│       ├── index.html    # Home page
│       ├── globe.html    # 3D globe
│       ├── graph.html    # Relation graph
│       ├── tree.html     # Tree view
│       ├── timeline.html # Timeline
│       ├── chat.html     # Chat panel
│       └── docs.html     # Documentation
│
├── infra/                # Infrastructure
│   ├── docker-compose.yml# Database containers
│   ├── init_qdrant.sh    # Qdrant initialization
│   └── schema.sql        # SQLite schema
│
├── data/                 # Data directory (gitignored)
│   └── cogmate.db        # SQLite database
│
└── config/               # Configuration files
    └── profile.json      # User profile
```

---

## ⚙️ Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Database connections
BRAIN_NEO4J_URI=bolt://localhost:7687
BRAIN_NEO4J_USER=neo4j
BRAIN_NEO4J_PASSWORD=your_password

BRAIN_QDRANT_HOST=localhost
BRAIN_QDRANT_PORT=6333

# Optional: LLM API (for abstraction layer and challenge mechanism)
ANTHROPIC_API_KEY=sk-ant-xxx
```

### User Profile

Edit `config/profile.json`:

```json
{
  "name": "Your Name",
  "title": "One-line description",
  "bio": "Knowledge base description"
}
```

---

## 🔐 Core Principles

1. **User Owns the Write Gate** - Web search results can only be suggested, never auto-written
2. **Contradictions Are the Most Valuable Relations** - Embrace tension, actively discover and preserve contradictions
3. **Concise Confirmations** - Brief acknowledgment after storage, don't interrupt the recording flow

---

## 🔗 Related Projects

- [CogNexus](https://github.com/MaxiiWang/CogNexus) - Distributed Cognitive Hub, Agent capability marketplace
- [OpenClaw](https://github.com/openclaw/openclaw) - Agent runtime

---

## 📝 License

MIT License - See [LICENSE](LICENSE)

---

## 🙏 Acknowledgments

- [Qdrant](https://qdrant.tech/) - Vector database
- [Neo4j](https://neo4j.com/) - Graph database
- [BGE-M3](https://huggingface.co/BAAI/bge-m3) - Multilingual vector model
- [OpenClaw](https://github.com/openclaw/openclaw) - Agent runtime

---

**Make every thought traceable.** 🧠
