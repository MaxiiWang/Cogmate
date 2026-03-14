# Brain Visual - 可视化方案设计

_创建日期: 2026-03-11_

---

## 1. 项目概述

### 1.1 目标

让「模拟世界」可以被**看见**——将知识图谱、抽象层、时间演变可视化呈现，支持交互式探索。

### 1.2 用户场景

| 场景 | 需求 | 对应视图 |
|------|------|----------|
| 探索知识全貌 | 看整体结构、发现主题簇 | Globe View |
| 理解抽象规律 | 查看规律层级、溯源事实 | Tree View |
| 回顾知识演变 | 按时间线浏览、找认知转折点 | Timeline View |
| 日常查询辅助 | 快速定位节点、查看关联 | 全局搜索 |

---

## 2. 技术架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│                   cogmate-visual                       │
│  (React SPA + Three.js + D3.js)                     │
├─────────────────────────────────────────────────────┤
│                    Nginx / Vercel                    │
├─────────────────────────────────────────────────────┤
│                  REST API Layer                      │
│  /api/visual/graph                                   │
│  /api/visual/tree                                    │
│  /api/visual/timeline                                │
│  /api/visual/search                                  │
├─────────────────────────────────────────────────────┤
│                 Cogmate Core                     │
│  (Python + SQLite + Qdrant + Neo4j)                 │
└─────────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 层级 | 技术 | 理由 |
|------|------|------|
| 前端框架 | React 18 + TypeScript | 生态成熟、组件化 |
| 3D 渲染 | Three.js + react-three-fiber | Globe View 需要 |
| 2D 可视化 | D3.js | Tree/Timeline 灵活度高 |
| 状态管理 | Zustand | 轻量、简洁 |
| 样式 | Tailwind CSS | 快速开发 |
| 构建工具 | Vite | 快速、现代 |
| API 服务 | FastAPI (Python) | 与 Cogmate 同语言 |

### 2.3 部署方案

**方案 A: 本地 Docker（推荐初期）**
```yaml
services:
  cogmate-visual:
    build: .
    ports:
      - "3000:3000"
    environment:
      - API_BASE_URL=http://localhost:8000
  
  cogmate-api:
    build: ./api
    ports:
      - "8000:8000"
```

**方案 B: Vercel + 本地 API**
- 前端部署到 Vercel（免费）
- API 通过 ngrok 暴露或部署到 VPS

---

## 3. API 设计

### 3.1 端点清单

**所有端点需要 token 参数验证**

```
# === 认证 ===
POST /api/visual/auth/verify
     验证 token 有效性
     Body: { "token": "xxx" }
     Response: { "valid": true, "expires_at": "...", "permissions": "full|readonly" }

# === 数据查询 ===
GET  /api/visual/graph?token=xxx
     获取完整图谱数据（节点 + 边）
     Query: &limit=500&offset=0

GET  /api/visual/graph/node/:id?token=xxx
     获取单个节点详情 + 关联

GET  /api/visual/tree?token=xxx
     获取抽象层树形结构

GET  /api/visual/tree/:id?token=xxx
     获取单个抽象详情 + 溯源链

GET  /api/visual/timeline?token=xxx
     获取时间线数据
     Query: &from=2026-01-01&to=2026-03-11&granularity=day

GET  /api/visual/search?token=xxx&q=keyword
     全局搜索
     Query: &type=fact|abstract

GET  /api/visual/health?token=xxx
     健康度数据

GET  /api/visual/stats?token=xxx
     统计概览

# === 交互 ===
POST /api/visual/chat
     对话交互
     Body: { "token": "xxx", "message": "...", "context": {...} }

POST /api/visual/action
     执行操作（需 full 权限）
     Body: { "token": "xxx", "action": "create_relation", "params": {...} }
```

### 3.2 数据格式

**图谱数据**
```json
{
  "nodes": [
    {
      "id": "fact_id",
      "label": "summary",
      "type": "事件|观点|情绪|资讯|决策",
      "timestamp": "2026-03-11",
      "degree": 5,
      "cluster": "主题簇名"
    }
  ],
  "edges": [
    {
      "source": "fact_id_1",
      "target": "fact_id_2",
      "type": "支持|矛盾|延伸|因果",
      "confidence": 4
    }
  ],
  "stats": {
    "total_nodes": 51,
    "total_edges": 49
  }
}
```

**树形数据**
```json
{
  "abstracts": [
    {
      "id": "abstract_id",
      "name": "规律名称",
      "description": "描述",
      "status": "confirmed",
      "source_facts": ["fact_id_1", "fact_id_2"],
      "counter_examples": []
    }
  ]
}
```

---

## 4. 视图设计

### 4.1 Globe View（3D 知识球）

**核心交互**
- 🖱️ 拖拽旋转球体
- 🔍 滚轮缩放
- 👆 点击节点 → 弹出详情卡片
- 🔗 悬停边 → 显示关系类型

**视觉设计**
- 节点颜色 = 内容类型（事件绿、观点蓝、情绪紫、资讯橙、决策红）
- 节点大小 = 度数（连接越多越大）
- 边颜色 = 关系类型（矛盾红色高亮）
- 主题簇聚集在球面相邻区域

**布局算法**
1. 使用 ForceGraph3D 力导向布局
2. 投影到球面（normalize 到球壳）
3. 同主题簇节点施加额外吸引力

### 4.2 Tree View（抽象层树）

**结构**
```
模拟世界
├── Max个人认知与决策 (16节点)
│   └── [溯源事实列表]
├── AI产业影响与技术趋势 (11节点)
│   └── [溯源事实列表]
└── 地缘冲突与避险资产 (8节点)
    └── [溯源事实列表]
```

**核心交互**
- 📂 点击展开/折叠
- 📌 点击抽象 → 显示规律描述
- 🔗 点击溯源事实 → 跳转 Globe View 定位

**视觉设计**
- 抽象层节点用金色
- 事实层节点按类型着色
- 反例用橙色边框标记

### 4.3 Timeline View（时间轴）

**核心交互**
- 📅 时间范围选择器
- 🔍 粒度切换（日/周/月）
- 👆 点击节点 → 显示详情
- ⭐ 高亮「认知转折点」

**认知转折点定义**
- 首次引入矛盾关系的事实
- 触发新抽象层记录的关键事实
- 高连接度事实（度数 ≥ 4）

**视觉设计**
- 时间轴横向
- 节点垂直堆叠（按类型分组）
- 转折点用星标 + 发光效果

---

## 5. 开发计划（更新版）

### Phase 3.1: 基础设施 + Token 机制（4天）

| 任务 | 时间 |
|------|------|
| 初始化 cogmate-visual 仓库 | 0.5天 |
| FastAPI 后端骨架 | 0.5天 |
| **Token 机制实现** | 1天 |
| - visual_tokens 表 | |
| - Token 生成/验证/撤销 | |
| - /visual 命令实现 | |
| /api/visual/* 端点实现 | 1天 |
| Docker 配置 | 0.5天 |
| 前端项目初始化 | 0.5天 |

### Phase 3.2: Globe View（4天）

| 任务 | 时间 |
|------|------|
| Three.js 球体基础 | 1天 |
| 节点渲染 + 力导向布局 | 1天 |
| 边渲染 + 矛盾高亮 | 0.5天 |
| 交互（点击、悬停、缩放） | 1天 |
| 过滤控件 | 0.5天 |

### Phase 3.3: Tree View（2天）

| 任务 | 时间 |
|------|------|
| D3.js 树形布局 | 0.5天 |
| 展开/折叠交互 | 0.5天 |
| 溯源链展示 | 0.5天 |
| 跨视图跳转 | 0.5天 |

### Phase 3.4: Timeline View（2天）

| 任务 | 时间 |
|------|------|
| D3.js 时间轴 | 0.5天 |
| 粒度切换 | 0.5天 |
| 转折点检测 + 高亮 | 0.5天 |
| 跨视图跳转 | 0.5天 |

### Phase 3.5: Chat Panel 交互功能（3天）

| 任务 | 时间 |
|------|------|
| Chat UI 组件 | 0.5天 |
| /api/visual/chat 端点 | 1天 |
| - 集成 IntentHandler | |
| - 上下文感知（当前节点）| |
| 操作确认流程 | 1天 |
| - 创建关联 | |
| - 添加备注 | |
| 权限控制（只读/完整）| 0.5天 |

### Phase 3.6: 集成发布（2天）

| 任务 | 时间 |
|------|------|
| 三视图统一导航 | 0.5天 |
| Token 登录页面 | 0.5天 |
| README + 文档 | 0.5天 |
| Docker 镜像发布 | 0.5天 |

**总计: 约 17 天**

---

## 6. 文件结构

```
cogmate-visual/
├── api/                    # FastAPI 后端
│   ├── main.py
│   ├── routers/
│   │   ├── graph.py
│   │   ├── tree.py
│   │   ├── timeline.py
│   │   └── search.py
│   └── requirements.txt
│
├── web/                    # React 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── GlobeView/
│   │   │   ├── TreeView/
│   │   │   ├── TimelineView/
│   │   │   └── common/
│   │   ├── hooks/
│   │   ├── stores/
│   │   ├── api/
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── docker-compose.yml
├── Dockerfile
└── README.md
```

---

## 7. 安全考虑：临时 Token 访问机制

### 7.1 需求背景

- 需要从其他设备远程访问可视化界面
- 不能将知识库完全暴露到公网
- 需要时间限制的访问控制

### 7.2 Token 机制设计

**生成命令**
```
/visual token [有效期]
/visual token 1h    # 1小时有效
/visual token 24h   # 24小时有效
/visual token 7d    # 7天有效（默认）
```

**返回示例**
```
🔗 可视化访问链接已生成

URL: https://your-server:3000?token=abc123xyz
有效期: 24小时 (至 2026-03-12 10:49)

⚠️ 请妥善保管此链接，勿分享给他人
```

**Token 存储结构**
```sql
CREATE TABLE visual_tokens (
    token TEXT PRIMARY KEY,
    created_at TEXT,
    expires_at TEXT,
    access_count INTEGER DEFAULT 0,
    last_access_at TEXT,
    revoked INTEGER DEFAULT 0
);
```

**验证流程**
```
请求 → 检查 token 参数 → 
  ├─ 无 token → 返回 401 + 登录页面
  ├─ token 无效/过期 → 返回 403
  └─ token 有效 → 放行 + 记录访问
```

**Token 管理命令**
```
/visual token         # 生成新 token（默认7天）
/visual token 24h     # 生成24小时 token
/visual tokens        # 列出所有有效 token
/visual revoke <id>   # 撤销指定 token
/visual revoke all    # 撤销所有 token
```

### 7.3 安全措施

- Token 使用 UUID + 随机后缀，不可猜测
- 过期自动失效，定期清理
- 支持手动撤销
- 记录访问日志（IP、时间、次数）
- 可选：单 token 单设备绑定

---

## 8. 可视化界面交互功能

### 8.1 需求背景

- 在可视化界面上直接提问，无需切换到 Telegram
- 查看节点时可以追问相关问题
- 支持基本操作（添加关联、标记等）

### 8.2 交互界面设计

**Chat Panel（侧边栏）**
```
┌─────────────────────────────────┐
│  🧠 Brain Assistant             │
├─────────────────────────────────┤
│                                 │
│  [节点详情卡片]                  │
│  Max副业规划中：...              │
│                                 │
│  ─────────────────────────────  │
│                                 │
│  你: 这个决策的依据是什么？       │
│                                 │
│  Brain: 根据知识库，主要依据：    │
│  📌 [1314bbc0] 离职触发条件...   │
│  📌 [3ada8da5] 决策困境...       │
│                                 │
├─────────────────────────────────┤
│  [输入框] 输入问题...      [发送] │
└─────────────────────────────────┘
```

### 8.3 支持的交互类型

**查询类（只读）**
| 交互 | 示例 | 处理 |
|------|------|------|
| 自由提问 | "为什么我对AI持乐观态度？" | → IntentHandler |
| 节点追问 | 点击节点 → "展开关联" | → 图谱查询 |
| 搜索 | 输入关键词 | → 向量搜索 |
| 路径查询 | "A和B有什么关系？" | → /why 逻辑 |

**操作类（需确认）**
| 交互 | 示例 | 处理 |
|------|------|------|
| 建议关联 | 拖拽两节点 → "创建关联？" | → 确认后写入 |
| 添加备注 | 右键节点 → "添加备注" | → 更新 context |
| 标记重要 | 星标节点 | → 添加标签 |

### 8.4 API 设计

**Chat 端点**
```
POST /api/visual/chat
{
  "message": "为什么我对AI持乐观态度？",
  "context": {
    "current_node": "fact_id",  // 可选，当前选中节点
    "view": "globe"              // 当前视图
  },
  "token": "access_token"
}

Response:
{
  "response": "根据知识库...",
  "facts": [...],               // 相关事实
  "suggested_actions": [...]    // 建议操作
}
```

**操作端点**
```
POST /api/visual/action
{
  "action": "create_relation",
  "params": {
    "from": "fact_id_1",
    "to": "fact_id_2",
    "type": "支持",
    "confidence": 4
  },
  "token": "access_token"
}
```

### 8.5 实现方案

**方案 A: REST API（推荐初期）**
- 简单，易于实现
- 请求-响应模式
- 适合低频交互

**方案 B: WebSocket（后续可选）**
- 实时双向通信
- 支持流式输出
- 适合高频交互

### 8.6 权限控制

| Token 类型 | 查询 | 操作 |
|------------|------|------|
| 只读 token | ✅ | ❌ |
| 完整 token | ✅ | ✅ |

生成时指定：
```
/visual token 24h readonly   # 只读
/visual token 24h full       # 完整权限（默认）
```

---

## 9. 扩展预留

- [ ] 协作模式（多人查看同一图谱）
- [ ] 导出功能（PNG/SVG/JSON）
- [ ] 嵌入模式（iframe 嵌入其他页面）
- [ ] 移动端适配
- [ ] 深色模式

---

## 9. 决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 前端框架 | React / Vue / Svelte | React | 生态最成熟，Three.js 集成方便 |
| 3D 库 | Three.js / Babylon.js | Three.js | 更轻量，社区资源丰富 |
| 状态管理 | Redux / Zustand / Jotai | Zustand | 简洁够用 |
| API | 嵌入 OpenClaw / 独立服务 | 独立 FastAPI | 解耦，可独立部署 |
