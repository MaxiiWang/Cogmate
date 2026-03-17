#!/usr/bin/env python3
"""
Cogmate Visual API
================
可视化后端 API 服务

启动: cd visual && python -m uvicorn api:app --reload --port 8000
"""

import sys
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

# 添加 lib 模块路径（相对于 visual 目录）
LIB_PATH = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB_PATH))

from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

# Centralized configuration
from config import (
    SQLITE_PATH, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    get_neo4j, get_sqlite, setup_logging
)

logger = setup_logging("visual_api")

app = FastAPI(
    title="Cogmate Visual API",
    description="模拟世界可视化后端",
    version="0.1.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Token 验证 ====================

class TokenInfo(BaseModel):
    token: str
    expires_at: str
    permissions: str
    scope: str = "full"
    scope_label: str = "🔓 全量访问"
    access_count: int
    qa_limit: int = 0
    qa_count: int = 0
    namespace: str = "default"


async def verify_token(
    token: str = Query(None, description="访问 Token"),
    ns: str = Query("default", description="Namespace"),
    request: Request = None
) -> TokenInfo:
    """Token 验证依赖（含 namespace 校验）"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    from visual_token import verify_token as vt
    
    # 获取客户端 IP
    client_ip = None
    if request:
        client_ip = request.client.host if request.client else None
    
    # 校验 token 并检查 namespace 绑定
    valid, info = vt(token, client_ip, namespace=ns)
    
    if not valid:
        error = info.get('error', 'invalid_token')
        if error == 'token_expired':
            raise HTTPException(status_code=401, detail="Token expired")
        elif error == 'token_revoked':
            raise HTTPException(status_code=401, detail="Token revoked")
        elif error == 'namespace_mismatch':
            raise HTTPException(status_code=403, detail=info.get('message', 'Namespace mismatch'))
        else:
            raise HTTPException(status_code=401, detail="Invalid token")
    
    return TokenInfo(**info)


def can_see_private(token_info: TokenInfo) -> bool:
    """检查是否能查看私有内容"""
    return token_info.scope == "full"


def can_browse(token_info: TokenInfo) -> bool:
    """检查是否能浏览（full 或 browse_public）"""
    return token_info.scope in ["full", "browse_public"]


def can_ask(token_info: TokenInfo) -> bool:
    """检查是否能问答（full 或 qa_public）"""
    return token_info.scope in ["full", "qa_public"]


def require_full_permission(token_info: TokenInfo = Depends(verify_token)):
    """需要完整权限的依赖"""
    if token_info.permissions != 'full':
        raise HTTPException(status_code=403, detail="Full permission required")
    return token_info


def get_private_fact_ids() -> set:
    """获取所有私有 fact_id（用于过滤）"""
    conn = get_sqlite()
    cursor = conn.cursor()
    cursor.execute("SELECT fact_id FROM facts WHERE is_private = 1")
    private_ids = set(r[0] for r in cursor.fetchall())
    conn.close()
    return private_ids


def get_private_abstract_ids() -> set:
    """获取所有私有 abstract_id（用于过滤）"""
    conn = get_sqlite()
    cursor = conn.cursor()
    cursor.execute("SELECT abstract_id FROM abstracts WHERE is_private = 1")
    private_ids = set(r[0] for r in cursor.fetchall())
    conn.close()
    return private_ids


# ==================== 静态文件 ====================

STATIC_DIR = Path(__file__).parent / "static"

# Mount static files
app.mount("/js", StaticFiles(directory=STATIC_DIR / "js"), name="js")
app.mount("/css", StaticFiles(directory=STATIC_DIR / "css"), name="css")

@app.get("/favicon.svg")
async def favicon():
    """Favicon"""
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")

# ==================== 路由 ====================

@app.get("/")
async def root():
    """首页 - 返回 Dashboard（无需 token）"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"name": "Cogmate Visual API", "version": "0.1.0"}


# ==================== 公开端点（无需 Token）====================

@app.get("/api/public/info")
async def public_info():
    """公开信息（无需 token）"""
    return {
        "name": "Max 的模拟世界",
        "description": "一个三层架构的个人知识管理系统，将碎片化想法持久化并发现知识间的隐藏关联。",
        "features": [
            "📝 事实层 - 记录事件、观点、决策",
            "🕸️ 关联层 - 发现知识间的联系",
            "📐 抽象层 - 提炼规律与模式"
        ],
        "access_levels": {
            "qa_public": "💬 问答服务 - 基于公开知识回答问题",
            "browse_public": "👁️ 公开浏览 - 查看公开的知识图谱",
            "full": "🔓 全量访问 - 完整访问所有内容"
        }
    }


@app.get("/api/public/profile")
async def get_profile(ns: str = "default"):
    """获取个人资料（公开，支持 namespace）"""
    try:
        # 先尝试从 namespace profile 获取
        from profile_manager import ProfileManager
        pm = ProfileManager()
        ns_config = pm.load_profile_config(ns)
        
        if ns_config and ns_config.get("identity"):
            identity = ns_config["identity"]
            return {
                "name": identity.get("name", ""),
                "title": identity.get("title", ""),
                "bio": identity.get("bio", ""),
                "avatar": identity.get("avatar", "")
            }
        
        # fallback 到默认 profile 表
        import sqlite3
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM profile")
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        logger.error(f"获取 profile 失败: {e}")
        return {"name": "", "title": "", "bio": "", "avatar": ""}


@app.put("/api/profile")
async def update_profile(request: Request, token: str = Query(...)):
    """更新个人资料（需要 full token）"""
    # 验证 token
    token_info = verify_token(token)
    if not token_info or token_info.get("scope") != "full":
        raise HTTPException(status_code=403, detail="需要 full 权限")
    
    data = await request.json()
    allowed_keys = ["name", "title", "bio", "avatar"]
    
    try:
        import sqlite3
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        for key, value in data.items():
            if key in allowed_keys:
                cursor.execute(
                    "INSERT OR REPLACE INTO profile (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                    (key, value)
                )
        conn.commit()
        conn.close()
        return {"success": True, "message": "资料已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/check")
async def auth_check(token: str = Query(None)):
    """验证 Token 并返回权限详情"""
    if not token:
        return {
            "valid": False,
            "scope": "none",
            "permissions": {
                "chat": False,
                "browse": False,
                "full_access": False
            }
        }
    
    from visual_token import verify_token as vt, get_qa_stats
    
    valid, info = vt(token, None)
    
    if not valid:
        return {
            "valid": False,
            "error": info.get('error', 'invalid'),
            "scope": "none",
            "permissions": {
                "chat": False,
                "browse": False,
                "full_access": False
            }
        }
    
    scope = info.get('scope', 'full')
    qa_stats = get_qa_stats(token)
    
    return {
        "valid": True,
        "scope": scope,
        "scope_label": info.get('scope_label', scope),
        "expires_at": info.get('expires_at'),
        "permissions": {
            "chat": scope in ['full', 'qa_public'],
            "browse": scope in ['full', 'browse_public'],
            "full_access": scope == 'full'
        },
        "qa_stats": {
            "limit": qa_stats.get('limit', 0),
            "used": qa_stats.get('used', 0),
            "remaining": qa_stats.get('remaining', -1),
            "unlimited": qa_stats.get('unlimited', False)
        }
    }


@app.get("/chat.html")
async def chat_page():
    """Chat 页面"""
    return FileResponse(STATIC_DIR / "chat.html")


@app.get("/globe")
async def globe_view():
    """Globe View - 3D 知识球 (deprecated, redirect to graph)"""
    return FileResponse(STATIC_DIR / "graph.html")


@app.get("/graph")
async def graph_view():
    """Graph View - 2D 力导向图"""
    graph_file = STATIC_DIR / "graph.html"
    if graph_file.exists():
        return FileResponse(graph_file)
    return {"error": "Graph view not found"}


@app.get("/tree")
async def tree_view():
    """Tree View - 抽象层树形视图"""
    tree_file = STATIC_DIR / "tree.html"
    if tree_file.exists():
        return FileResponse(tree_file)
    return {"error": "Tree view not found"}


@app.get("/timeline")
async def timeline_view():
    """Timeline View - 时间线视图"""
    timeline_file = STATIC_DIR / "timeline.html"
    if timeline_file.exists():
        return FileResponse(timeline_file)
    return {"error": "Timeline view not found"}


@app.get("/guide")
async def guide_view():
    """文档页面"""
    docs_file = STATIC_DIR / "docs.html"
    if docs_file.exists():
        return FileResponse(docs_file)
    return {"error": "Docs not found"}


@app.get("/api/visual/auth/verify")
async def auth_verify(token: str = Query(...)):
    """验证 Token"""
    try:
        token_info = await verify_token(token)
        return {
            "valid": True,
            "expires_at": token_info.expires_at,
            "permissions": token_info.permissions
        }
    except HTTPException as e:
        return {"valid": False, "error": e.detail}


@app.get("/api/visual/stats")
async def get_stats(token_info: TokenInfo = Depends(verify_token), ns: str = "default"):
    """获取统计概览"""
    from cogmate_core import CogmateAgent

    cogmate = CogmateAgent(namespace=ns)
    stats = cogmate.stats()

    return {
        "namespace": ns,
        "total_facts": stats["total_facts"],
        "graph_nodes": stats["graph_nodes"],
        "graph_edges": stats["graph_edges"],
        "by_type": stats.get("by_type", {}),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/visual/health")
async def get_health(token_info: TokenInfo = Depends(verify_token), ns: str = "default"):
    """获取健康度数据"""
    from graph_health import get_graph_metrics, evaluate_health

    metrics = get_graph_metrics()
    health = evaluate_health(metrics)

    return {
        "namespace": ns,
        "metrics": metrics,
        "health": health
    }


# ==================== Hub 集成接口 ====================

@app.get("/health")
async def health_check():
    """健康检查（无需 Token，供 Hub 状态检测）"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/hub/profile")
async def get_hub_profile(ns: str = "default"):
    """获取 Hub 集成所需的个人资料"""
    try:
        import sqlite3
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM profile")
        rows = cursor.fetchall()
        conn.close()
        profile = {row[0]: row[1] for row in rows}

        # 获取统计信息（按 namespace 过滤）
        conn2 = get_sqlite()
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT COUNT(*) FROM facts WHERE namespace = ?", (ns,))
        fact_count = cursor2.fetchone()[0]
        conn2.close()

        # 尝试获取 namespace profile
        ns_profile = {}
        identity = {}
        try:
            from profile_manager import ProfileManager
            pm = ProfileManager()
            ns_data = pm.load_profile_config(ns)
            if ns_data:
                ns_profile = ns_data
                identity = ns_data.get("identity", {})
        except Exception as e:
            logger.warning(f"加载 namespace profile 失败: {e}")

        return {
            "namespace": ns,
            "name": identity.get("name") or profile.get("name", ""),
            "title": identity.get("title") or profile.get("title", ""),
            "bio": identity.get("bio") or profile.get("bio", ""),
            "avatar": identity.get("avatar") or profile.get("avatar", ""),
            "stats": {
                "facts": fact_count
            },
            "api_version": "1.0"
        }
    except Exception as e:
        logger.error(f"获取 Hub profile 失败: {e}")
        return {"name": "", "title": "", "bio": "", "avatar": "", "stats": {}, "api_version": "1.0"}


@app.get("/api/hub/profiles")
async def list_hub_profiles():
    """列出所有可发布的角色（供 CogNexus 使用）"""
    try:
        from profile_manager import ProfileManager
        pm = ProfileManager()
        profiles = pm.list_profiles()
        
        result = []
        for p in profiles:
            # 获取每个角色的知识库统计
            conn = get_sqlite()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM facts WHERE namespace = ?", (p["namespace"],))
            fact_count = cursor.fetchone()[0]
            conn.close()
            
            # 从 identity 中读取 name 和 title
            identity = p.get("identity", {})
            
            result.append({
                "namespace": p["namespace"],
                "type": p["type"],
                "name": identity.get("name", p["namespace"]),
                "title": identity.get("title", ""),
                "avatar": identity.get("avatar", ""),
                "fact_count": fact_count
            })
        
        return {"profiles": result, "total": len(result)}
    except Exception as e:
        logger.error(f"列出角色失败: {e}")
        return {"profiles": [], "total": 0, "error": str(e)}


class PublishRequest(BaseModel):
    namespace: str
    cognexus_url: str
    username: str
    password: str
    token_config: dict = {
        "count": 10,
        "scope": "qa_public",
        "duration": "30d",
        "unit_price": 5
    }


@app.post("/api/hub/publish")
async def publish_to_cognexus(request: PublishRequest):
    """发布角色到 CogNexus"""
    import httpx
    from profile_manager import ProfileManager
    from visual_token import generate_token
    
    ns = request.namespace
    
    # 1. 获取角色信息
    pm = ProfileManager()
    profiles = pm.list_profiles()
    profile_data = None
    for p in profiles:
        if p["namespace"] == ns:
            identity = p.get("identity", {})
            profile_data = {
                "name": identity.get("name", ns),
                "title": identity.get("title", ""),
                "type": p["type"],
                "avatar": identity.get("avatar", ""),
                "bio": identity.get("bio", identity.get("title", ""))
            }
            break
    
    if not profile_data:
        return {"success": False, "error": f"角色 {ns} 不存在"}
    
    # 获取知识库统计
    conn = get_sqlite()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM facts WHERE namespace = ?", (ns,))
    fact_count = cursor.fetchone()[0]
    conn.close()
    profile_data["fact_count"] = fact_count
    
    # 2. 登录 CogNexus
    cognexus_url = request.cognexus_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 登录获取 token
            login_res = await client.post(
                f"{cognexus_url}/api/auth/login",
                json={"username": request.username, "password": request.password}
            )
            if login_res.status_code != 200:
                return {"success": False, "error": "CogNexus 登录失败，请检查用户名密码"}
            
            login_data = login_res.json()
            cog_token = login_data.get("token")
            if not cog_token:
                return {"success": False, "error": "CogNexus 登录失败，未获取到 token"}
            
            # 3. 创建 Tokens
            token_config = request.token_config
            count = token_config.get("count", 10)
            scope = token_config.get("scope", "qa_public")
            duration = token_config.get("duration", "30d")
            unit_price = token_config.get("unit_price", 5)
            
            # 根据 scope 设置 qa_limit
            qa_limit = 20 if scope == "qa_public" else -1
            
            tokens = []
            for _ in range(count):
                result = generate_token(
                    scope=scope,
                    duration=duration,
                    namespace=ns
                )
                # generate_token 直接返回 {token, expires_at, ...}
                if result and result.get("token"):
                    tokens.append({
                        "value": result["token"],
                        "scope": scope,
                        "qa_limit": qa_limit,
                        "unit_price": unit_price
                    })
            
            if not tokens:
                return {"success": False, "error": "Token 创建失败"}
            
            # 4. 推送到 CogNexus
            # 获取本机地址
            import socket
            local_ip = socket.gethostbyname(socket.gethostname())
            source_url = f"http://{local_ip}:8000"
            # 优先使用配置的外部地址
            # TODO: 从配置读取
            source_url = "http://124.221.254.71:8000"
            
            import_res = await client.post(
                f"{cognexus_url}/api/agents/import",
                headers={"Authorization": f"Bearer {cog_token}"},
                json={
                    "source_url": source_url,
                    "namespace": ns,
                    "profile": profile_data,
                    "tokens": tokens
                }
            )
            
            if import_res.status_code != 200:
                return {"success": False, "error": f"推送失败: {import_res.text}"}
            
            import_data = import_res.json()
            
            return {
                "success": True,
                "agent_id": import_data.get("agent_id"),
                "agent_url": f"{cognexus_url}{import_data.get('agent_url', '')}",
                "tokens_created": len(tokens),
                "created": import_data.get("created", True)
            }
            
    except httpx.RequestError as e:
        return {"success": False, "error": f"网络错误: {str(e)}"}
    except Exception as e:
        logger.error(f"发布失败: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/hub/token/validate")
async def validate_hub_token(token: str = Query(..., description="要验证的 Token")):
    """验证 Token 并返回详细信息（供 Hub 使用）"""
    from visual_token import verify_token as vt, get_qa_stats
    
    valid, info = vt(token, None)
    
    if not valid:
        return {
            "valid": False,
            "error": info.get("error", "invalid_token") if info else "invalid_token"
        }
    
    scope = info.get("scope", "full")
    qa_stats = get_qa_stats(token)
    
    # 权限映射
    permissions = []
    if scope in ["full", "qa_public"]:
        permissions.append("chat")
    if scope in ["full", "browse_public"]:
        permissions.append("read")
    if scope == "full":
        permissions.append("react")
    
    # scope 标签
    scope_labels = {
        "full": "完整访问",
        "qa_public": "公开问答",
        "browse_public": "公开浏览"
    }
    
    return {
        "valid": True,
        "scope": scope,
        "scope_label": scope_labels.get(scope, scope),
        "permissions": permissions,
        "expires_at": info.get("expires_at"),
        "usage": {
            "qa_limit": qa_stats.get("limit", 0),
            "qa_used": qa_stats.get("used", 0),
            "qa_remaining": qa_stats.get("remaining", -1),
            "unlimited": qa_stats.get("unlimited", False)
        }
    }


# ==================== Simulation React API ====================

class SimulationReactRequest(BaseModel):
    simulation_id: str
    round_id: str = ""
    prompt: str
    prompt_type: str = "predictive"   # "narrative" | "predictive"
    description: str = ""
    outcome_options: list = ["yes", "no"]
    previous_context: str = ""


@app.post("/api/simulation/react")
async def simulation_react(
    request: SimulationReactRequest,
    token_info: TokenInfo = Depends(verify_token),
    ns: str = "default"
):
    """
    Agent 对 Simulation 问题进行反应

    统一端点: Character 和 Human Agent 都自动生成
    - narrative: 自由文本回应 + 关键点提取
    - predictive: 结构化立场 + 置信度
    """
    from sim_react import react

    result = react(
        prompt=request.prompt,
        prompt_type=request.prompt_type,
        namespace=ns,
        description=request.description,
        outcome_options=request.outcome_options,
        previous_context=request.previous_context
    )

    return result


# ==================== Visual Data API ====================

@app.get("/api/visual/graph")
async def get_graph(
    token_info: TokenInfo = Depends(verify_token),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    ns: str = "default"
):
    """获取图谱数据（根据 scope 过滤私有内容）"""
    if not can_browse(token_info):
        raise HTTPException(status_code=403, detail="Browse permission required")

    from neo4j import GraphDatabase

    include_private = can_see_private(token_info)

    # 如果需要过滤，获取私有 fact_ids
    private_ids = set() if include_private else get_private_fact_ids()

    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    nodes = []
    edges = []

    with driver.session() as session:
        # 获取节点（按 namespace 过滤）
        node_result = session.run('''
            MATCH (f:Fact)
            WHERE f.namespace = $namespace
            OPTIONAL MATCH (f)-[r]-()
            WITH f, count(r) as degree
            RETURN f.fact_id as id, f.summary as label,
                   f.content_type as type, f.timestamp as timestamp,
                   degree
            ORDER BY f.timestamp DESC
            SKIP $offset LIMIT $limit
        ''', offset=offset, limit=limit, namespace=ns)
        
        for record in node_result:
            # 跳过私有节点
            if record["id"] in private_ids:
                continue
            full_label = record["label"] or ""
            nodes.append({
                "id": record["id"],
                "label": full_label[:50] + ("..." if len(full_label) > 50 else ""),
                "full_content": full_label,  # 完整内容用于详情面板
                "type": record["type"],
                "timestamp": record["timestamp"],
                "degree": record["degree"]
            })
        
        # 获取边（按 namespace 过滤，过滤涉及私有节点的边）
        edge_result = session.run('''
            MATCH (a:Fact)-[r]->(b:Fact)
            WHERE a.namespace = $namespace AND b.namespace = $namespace
            RETURN a.fact_id as source, b.fact_id as target,
                   type(r) as type, r.confidence as confidence
        ''', namespace=ns)
        
        for record in edge_result:
            # 跳过涉及私有节点的边
            if record["source"] in private_ids or record["target"] in private_ids:
                continue
            edges.append({
                "source": record["source"],
                "target": record["target"],
                "type": record["type"],
                "confidence": record["confidence"]
            })
    
    driver.close()
    
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges)
        },
        "scope": token_info.scope,
        "filtered": not include_private
    }


@app.get("/api/visual/graph/node/{node_id}")
async def get_node(
    node_id: str,
    token_info: TokenInfo = Depends(verify_token),
    ns: str = "default"
):
    """获取单个节点详情"""
    from cogmate_core import CogmateAgent

    cogmate = CogmateAgent(namespace=ns)
    fact = cogmate.get_fact(node_id)
    
    if not fact:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # 获取关联
    results = cogmate.query(fact.get('summary', ''), top_k=5)
    
    return {
        "node": fact,
        "relations": results.get("graph_results", [])
    }


@app.get("/api/visual/tree")
async def get_tree(token_info: TokenInfo = Depends(verify_token), ns: str = "default"):
    """获取抽象层树形结构（根据 scope 过滤私有内容）"""
    if not can_browse(token_info):
        raise HTTPException(status_code=403, detail="Browse permission required")
    
    from abstraction import list_abstracts
    import sqlite3
    
    include_private = can_see_private(token_info)
    abstracts = list_abstracts(namespace=ns)
    
    # 过滤私有抽象层
    if not include_private:
        private_abstract_ids = get_private_abstract_ids()
        abstracts = [a for a in abstracts if a["abstract_id"] not in private_abstract_ids]
    
    return {
        "abstracts": [
            {
                "id": a["abstract_id"][:8],
                "name": a["name"],
                "description": a["description"][:200] if a["description"] else "",
                "status": a["status"],
                "source_count": len(a["source_fact_ids"]),
                "source_facts": a["source_fact_ids"][:10]  # 限制数量
            }
            for a in abstracts
        ],
        "scope": token_info.scope,
        "filtered": not include_private
    }


@app.get("/api/visual/timeline")
async def get_timeline(
    token_info: TokenInfo = Depends(verify_token),
    start: str = Query(None),
    end: str = Query(None),
    granularity: str = Query("day"),
    ns: str = "default"
):
    """获取时间线数据（根据 scope 过滤私有内容）"""
    if not can_browse(token_info):
        raise HTTPException(status_code=403, detail="Browse permission required")
    
    import sqlite3
    
    include_private = can_see_private(token_info)
    
    db_path = Path.home() / ".openclaw/workspace/cogmate/data/cogmate.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 根据 scope 决定是否过滤
    if include_private:
        query = '''
            SELECT fact_id, summary, content_type, timestamp, created_at
            FROM facts
            WHERE namespace = ?
            ORDER BY created_at DESC
        '''
        cursor.execute(query, (ns,))
    else:
        query = '''
            SELECT fact_id, summary, content_type, timestamp, created_at
            FROM facts
            WHERE is_private = 0 AND namespace = ?
            ORDER BY created_at DESC
        '''
        cursor.execute(query, (ns,))
    
    facts = []
    for row in cursor.fetchall():
        full_label = row[1] or ""
        facts.append({
            "id": row[0][:8],
            "full_id": row[0],  # 完整 ID
            "label": full_label[:50] + ("..." if len(full_label) > 50 else ""),
            "full_content": full_label,  # 完整内容用于详情面板
            "type": row[2],
            "timestamp": row[3],
            "created_at": row[4]
        })
    
    conn.close()
    
    return {
        "facts": facts,
        "granularity": granularity,
        "scope": token_info.scope,
        "filtered": not include_private
    }


@app.get("/api/visual/search")
async def search(
    q: str = Query(..., min_length=1),
    token_info: TokenInfo = Depends(verify_token)
):
    """全局搜索（根据 scope 过滤私有内容）"""
    if not can_browse(token_info):
        raise HTTPException(status_code=403, detail="Browse permission required")
    
    from cogmate_core import CogmateAgent
    import sqlite3
    
    include_private = can_see_private(token_info)
    
    cogmate = CogmateAgent()
    results = cogmate.query(q, top_k=20)  # 多取一些以备过滤
    
    vector_results = results.get("vector_results", [])
    
    # 过滤私有内容
    if not include_private:
        db_path = Path.home() / ".openclaw/workspace/cogmate/data/cogmate.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        fact_ids = [r["fact_id"] for r in vector_results]
        if fact_ids:
            placeholders = ','.join(['?'] * len(fact_ids))
            cursor.execute(
                f"SELECT fact_id FROM facts WHERE fact_id IN ({placeholders}) AND is_private = 0",
                fact_ids
            )
            public_ids = set(r[0] for r in cursor.fetchall())
            vector_results = [r for r in vector_results if r["fact_id"] in public_ids]
        
        conn.close()
    
    # 限制返回数量
    vector_results = vector_results[:10]
    
    return {
        "query": q,
        "results": vector_results,
        "total": len(vector_results),
        "scope": token_info.scope,
        "filtered": not include_private
    }


# ==================== Chat 交互 ====================

class ChatRequest(BaseModel):
    message: str
    context: Optional[dict] = None


class ActionRequest(BaseModel):
    action: str
    params: dict


@app.post("/api/visual/chat")
async def chat(
    request: ChatRequest,
    token_info: TokenInfo = Depends(verify_token)
):
    """对话交互（内部使用，需 full 权限）"""
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required for chat")
    
    from intent_handler import IntentHandler
    
    handler = IntentHandler()
    response = handler.process(request.message)
    
    return {
        "response": response,
        "context": request.context
    }


# ==================== 问答 API（对外服务）====================

class AskRequest(BaseModel):
    question: str
    max_sources: int = 5


class AskResponse(BaseModel):
    answer: str
    sources_count: int
    scope: str
    qa_remaining: int = -1  # -1 表示无限制


@app.post("/api/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    token_info: TokenInfo = Depends(verify_token),
    ns: str = "default"
):
    """
    问答服务 API
    
    - scope=full: 使用全部知识回答
    - scope=qa_public: 只使用公开知识回答（限制20次）
    - scope=browse_public: 不支持问答，返回 403
    """
    if not can_ask(token_info):
        raise HTTPException(
            status_code=403, 
            detail="This token only allows browsing, not Q&A"
        )
    
    from cogmate_core import CogmateAgent
    from visual_token import check_qa_limit, increment_qa_count
    import sqlite3
    
    # 检查问答次数限制
    can_continue, remaining, limit = check_qa_limit(token_info.token)
    if not can_continue:
        raise HTTPException(
            status_code=429,
            detail=f"Q&A limit exceeded. This token allows {limit} questions."
        )
    
    cogmate = CogmateAgent(namespace=ns)
    
    # 根据 scope 决定是否过滤私有内容
    include_private = can_see_private(token_info)
    
    # 语义搜索
    results = cogmate.query(
        query_text=request.question,
        top_k=request.max_sources * 2,  # 多取一些以备过滤
        min_score=0.5
    )
    
    # 过滤私有内容（如果需要）
    vector_results = results.get("vector_results", [])
    if not include_private:
        # 查询哪些 fact_id 是私有的
        db_path = Path.home() / ".openclaw/workspace/cogmate/data/cogmate.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        fact_ids = [r["fact_id"] for r in vector_results]
        if fact_ids:
            placeholders = ','.join(['?'] * len(fact_ids))
            cursor.execute(
                f"SELECT fact_id FROM facts WHERE fact_id IN ({placeholders}) AND is_private = 0",
                fact_ids
            )
            public_ids = set(r[0] for r in cursor.fetchall())
            vector_results = [r for r in vector_results if r["fact_id"] in public_ids]
        
        conn.close()
    
    # 限制数量
    vector_results = vector_results[:request.max_sources]
    
    # 构建 context
    if not vector_results:
        # 即使没找到也计入次数
        increment_qa_count(token_info.token)
        new_remaining = remaining - 1 if remaining > 0 else -1
        return AskResponse(
            answer="抱歉，在知识库中没有找到相关信息。",
            sources_count=0,
            scope=token_info.scope,
            qa_remaining=new_remaining
        )
    
    # 使用 LLM 生成回答（传入 namespace 用于 persona 注入）
    from llm_answer import generate_answer
    answer = generate_answer(request.question, vector_results, namespace=ns)
    
    # 增加问答计数
    increment_qa_count(token_info.token)
    new_remaining = remaining - 1 if remaining > 0 else -1
    
    return AskResponse(
        answer=answer,
        sources_count=len(vector_results),
        scope=token_info.scope,
        qa_remaining=new_remaining
    )


@app.get("/api/ask")
async def ask_get(
    q: str = Query(..., description="问题"),
    token_info: TokenInfo = Depends(verify_token),
    ns: str = "default"
):
    """GET 方式问答（便于测试）"""
    request = AskRequest(question=q)
    return await ask(request, token_info, ns=ns)


from fastapi.responses import StreamingResponse


@app.get("/api/ask/stream")
async def ask_stream(
    q: str = Query(..., description="问题"),
    token_info: TokenInfo = Depends(verify_token),
    ns: str = "default"
):
    """流式问答 API（Server-Sent Events）"""
    if not can_ask(token_info):
        raise HTTPException(
            status_code=403, 
            detail="This token only allows browsing, not Q&A"
        )
    
    from cogmate_core import CogmateAgent
    from visual_token import check_qa_limit, increment_qa_count
    from llm_answer import generate_answer
    import sqlite3
    
    # 检查问答次数限制
    can_continue, remaining, limit = check_qa_limit(token_info.token)
    if not can_continue:
        async def error_stream():
            yield f"data: {json.dumps({'error': 'limit_exceeded', 'message': f'问答次数已用完（限制 {limit} 次）'})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")
    
    cogmate = CogmateAgent(namespace=ns)
    include_private = can_see_private(token_info)
    
    # 语义搜索
    results = cogmate.query(query_text=q, top_k=10, min_score=0.5)
    vector_results = results.get("vector_results", [])
    
    # 过滤私有内容
    if not include_private:
        db_path = Path.home() / ".openclaw/workspace/cogmate/data/cogmate.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        fact_ids = [r["fact_id"] for r in vector_results]
        if fact_ids:
            placeholders = ','.join(['?'] * len(fact_ids))
            cursor.execute(
                f"SELECT fact_id FROM facts WHERE fact_id IN ({placeholders}) AND is_private = 0",
                fact_ids
            )
            public_ids = set(r[0] for r in cursor.fetchall())
            vector_results = [r for r in vector_results if r["fact_id"] in public_ids]
        conn.close()
    
    vector_results = vector_results[:5]
    
    # 增加问答计数
    increment_qa_count(token_info.token)
    new_remaining = remaining - 1 if remaining > 0 else -1
    
    async def event_stream():
        import json
        
        # 发送元数据
        yield f"data: {json.dumps({'type': 'meta', 'sources_count': len(vector_results), 'qa_remaining': new_remaining})}\n\n"
        
        if not vector_results:
            yield f"data: {json.dumps({'type': 'content', 'text': '抱歉，在知识库中没有找到相关信息。'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        
        # 流式生成回答（传入 namespace 用于 persona 注入）
        try:
            stream_gen = generate_answer(q, vector_results, stream=True, namespace=ns)
            for chunk in stream_gen:
                yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/ask/stats")
async def ask_stats(
    token_info: TokenInfo = Depends(verify_token)
):
    """查询问答次数统计"""
    from visual_token import get_qa_stats
    
    stats = get_qa_stats(token_info.token)
    return {
        "scope": token_info.scope,
        **stats
    }


# ==================== 隐私控制 API ====================

class PrivacyRequest(BaseModel):
    entity_id: str
    is_private: bool
    cascade: bool = False


@app.post("/api/visual/privacy")
async def set_privacy(
    request: PrivacyRequest,
    token_info: TokenInfo = Depends(verify_token)
):
    """设置实体隐私状态（仅 full 权限）"""
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from privacy import set_fact_private, set_abstract_private, get_privacy_status
    
    # 先检查实体类型
    status = get_privacy_status(request.entity_id)
    if not status:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    if status["type"] == "fact":
        success = set_fact_private(request.entity_id, request.is_private)
        return {
            "success": success,
            "entity_type": "fact",
            "entity_id": status["id"],
            "is_private": request.is_private
        }
    else:  # abstract
        success, affected = set_abstract_private(
            request.entity_id, 
            request.is_private, 
            cascade=request.cascade
        )
        return {
            "success": success,
            "entity_type": "abstract",
            "entity_id": status["id"],
            "is_private": request.is_private,
            "cascade": request.cascade,
            "affected_facts": len(affected) if affected else 0
        }


@app.get("/api/visual/privacy/{entity_id}")
async def get_privacy(
    entity_id: str,
    token_info: TokenInfo = Depends(verify_token)
):
    """获取实体隐私状态"""
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from privacy import get_privacy_status
    
    status = get_privacy_status(entity_id)
    if not status:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    return status


@app.get("/api/visual/privacy-stats")
async def get_privacy_stats(
    token_info: TokenInfo = Depends(verify_token)
):
    """获取隐私统计"""
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from privacy import get_privacy_stats as _get_stats
    return _get_stats()


# ==================== Token 管理 API ====================

class CreateTokenRequest(BaseModel):
    scope: str = "qa_public"
    duration: str = "7d"
    qa_limit: int = None
    note: str = None


@app.get("/api/tokens")
async def list_tokens_api(
    token_info: TokenInfo = Depends(verify_token),
    ns: str = "default"
):
    """列出当前 namespace 的 Token（仅 full 权限）"""
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from visual_token import list_tokens, get_qa_stats, get_visual_url
    
    # 只返回当前 namespace 的 token
    tokens = list_tokens(namespace=ns)
    result = []
    ns_param = f"&ns={ns}" if ns != "default" else ""
    for t in tokens:
        qa_stats = get_qa_stats(t['token_full'])
        result.append({
            'token_short': t['token'],
            'token_full': t['token_full'],
            'scope': t['scope'],
            'scope_label': t['scope_label'],
            'created_at': t['created_at'],
            'expires_at': t['expires_at'],
            'access_count': t['access_count'],
            'note': t['note'],
            'namespace': t.get('namespace', 'default'),
            'qa_limit': qa_stats.get('limit', 0),
            'qa_used': qa_stats.get('used', 0),
            'qa_unlimited': qa_stats.get('unlimited', False),
            'url': get_visual_url(t['token_full']) + ns_param
        })
    
    return {"tokens": result, "namespace": ns}


@app.post("/api/tokens")
async def create_token_api(
    request: CreateTokenRequest,
    token_info: TokenInfo = Depends(verify_token),
    ns: str = "default"
):
    """创建新 Token（仅 full 权限，绑定当前 namespace）"""
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from visual_token import generate_token, get_visual_url
    
    # 验证 scope
    valid_scopes = ['full', 'qa_public', 'browse_public']
    if request.scope not in valid_scopes:
        raise HTTPException(status_code=400, detail=f"Invalid scope. Must be one of: {valid_scopes}")
    
    # 创建 token 时绑定到当前 namespace
    result = generate_token(
        duration=request.duration,
        scope=request.scope,
        qa_limit=request.qa_limit,
        note=request.note,
        namespace=ns
    )
    
    ns_param = f"&ns={ns}" if ns != "default" else ""
    return {
        'success': True,
        'token': result['token'],
        'scope': result['scope'],
        'scope_label': result['scope_label'],
        'expires_at': result['expires_at'],
        'qa_limit': result['qa_limit'],
        'namespace': ns,
        'url': get_visual_url(result['token']) + ns_param
    }


@app.delete("/api/tokens/{token_id}")
async def revoke_token_api(
    token_id: str,
    token_info: TokenInfo = Depends(verify_token)
):
    """撤销 Token（仅 full 权限）"""
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from visual_token import revoke_token
    
    success = revoke_token(token_id)
    return {"success": success}


@app.post("/api/visual/action")
async def action(
    request: ActionRequest,
    token_info: TokenInfo = Depends(require_full_permission)
):
    """执行操作（需要完整权限）"""
    from cogmate_core import CogmateAgent
    
    cogmate = CogmateAgent()
    
    if request.action == "create_relation":
        params = request.params
        result = cogmate.create_relation(
            params["from_id"],
            params["to_id"],
            params.get("relation_type", "RELATES_TO"),
            params.get("confidence", 3)
        )
        return {"success": True, "result": result}
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")


# ==================== Profile/Namespace 管理 ====================

@app.get("/api/profiles")
async def list_profiles_api(
    token_info: TokenInfo = Depends(verify_token)
):
    """列出所有 Profiles/Namespaces（任何有效 token 均可查看列表）"""
    
    from profile_manager import ProfileManager
    from cogmate_core import CogmateAgent
    
    pm = ProfileManager()
    profiles = pm.list_profiles()
    
    result = []
    for p in profiles:
        # 获取每个 namespace 的统计
        try:
            cogmate = CogmateAgent(namespace=p['namespace'])
            stats = cogmate.stats()
            fact_count = stats.get('total_facts', 0)
        except:
            fact_count = 0
        
        identity = p.get('identity', {})
        result.append({
            'namespace': p['namespace'],
            'type': p['type'],
            'name': identity.get('name', p['namespace']),
            'title': identity.get('title', ''),
            'created_at': p.get('created_at', ''),
            'last_active': p.get('last_active', ''),
            'fact_count': fact_count
        })
    
    return {"profiles": result}


class CreateProfileRequest(BaseModel):
    namespace: str
    type: str = "character"
    name: str = ""
    title: str = ""
    bio: str = ""


@app.post("/api/profiles")
async def create_profile_api(
    request: CreateProfileRequest,
    token_info: TokenInfo = Depends(verify_token)
):
    """创建新 Profile/Namespace（仅 default namespace 的 full 权限）"""
    if token_info.namespace != "default":
        raise HTTPException(status_code=403, detail="只能从 default namespace 管理角色")
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from profile_manager import ProfileManager
    
    pm = ProfileManager()
    
    # 构建配置
    config = {
        "identity": {
            "name": request.name or request.namespace,
            "title": request.title,
            "bio": request.bio,
            "avatar": ""
        }
    }
    
    success = pm.create_profile(
        namespace=request.namespace,
        profile_type=request.type,
        config=config
    )
    
    if success:
        # 更新配置文件
        full_config = pm.load_profile_config(request.namespace)
        if full_config:
            full_config["identity"] = config["identity"]
            pm.save_profile_config(request.namespace, full_config)
        
        return {"success": True, "namespace": request.namespace}
    else:
        raise HTTPException(status_code=400, detail="创建失败，可能 namespace 已存在或格式无效")


@app.get("/api/profiles/{namespace}")
async def get_profile_api(
    namespace: str,
    token_info: TokenInfo = Depends(verify_token)
):
    """获取单个 Profile 详情"""
    if token_info.namespace != "default":
        raise HTTPException(status_code=403, detail="只能从 default namespace 管理角色")
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from profile_manager import ProfileManager
    
    pm = ProfileManager()
    config = pm.load_profile_config(namespace)
    
    if not config:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return config


class UpdateProfileRequest(BaseModel):
    name: str = None
    title: str = None
    bio: str = None
    persona: dict = None


@app.put("/api/profiles/{namespace}")
async def update_profile_api(
    namespace: str,
    request: UpdateProfileRequest,
    token_info: TokenInfo = Depends(verify_token)
):
    """更新 Profile"""
    if token_info.namespace != "default":
        raise HTTPException(status_code=403, detail="只能从 default namespace 管理角色")
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from profile_manager import ProfileManager
    
    pm = ProfileManager()
    config = pm.load_profile_config(namespace)
    
    if not config:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    # 更新 identity
    if "identity" not in config:
        config["identity"] = {}
    
    if request.name is not None:
        config["identity"]["name"] = request.name
    if request.title is not None:
        config["identity"]["title"] = request.title
    if request.bio is not None:
        config["identity"]["bio"] = request.bio
    
    # 更新 persona（仅 character 类型）
    if request.persona and config.get("type") == "character":
        if "persona" not in config:
            config["persona"] = {}
        config["persona"].update(request.persona)
    
    pm.save_profile_config(namespace, config)

    return {"success": True}


@app.get("/api/profiles/{namespace}/llm")
async def get_profile_llm(
    namespace: str,
    token_info: TokenInfo = Depends(verify_token)
):
    """获取 Profile 的 LLM 配置（API Key 脱敏）"""
    if token_info.namespace != "default":
        raise HTTPException(status_code=403, detail="只能从 default namespace 管理角色")
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")

    from profile_manager import ProfileManager
    pm = ProfileManager()
    config = pm.load_profile_config(namespace)
    if not config:
        raise HTTPException(status_code=404, detail="Profile not found")

    llm = config.get("llm", {})
    return {
        "base_url": llm.get("base_url", ""),
        "model": llm.get("model", ""),
        "has_key": bool(llm.get("api_key"))
    }


@app.put("/api/profiles/{namespace}/llm")
async def update_profile_llm(
    namespace: str,
    request: Request,
    token_info: TokenInfo = Depends(verify_token)
):
    """更新 Profile 的 LLM 配置"""
    if token_info.namespace != "default":
        raise HTTPException(status_code=403, detail="只能从 default namespace 管理角色")
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")

    from profile_manager import ProfileManager
    pm = ProfileManager()
    config = pm.load_profile_config(namespace)
    if not config:
        raise HTTPException(status_code=404, detail="Profile not found")

    data = await request.json()

    # 清除配置
    if data.get("clear"):
        config["llm"] = {}
        pm.save_profile_config(namespace, config)
        return {"success": True}

    llm = config.get("llm", {})
    if data.get("base_url") is not None:
        llm["base_url"] = data["base_url"]
    if data.get("model") is not None:
        llm["model"] = data["model"]
    if data.get("api_key") and data["api_key"] != "":
        llm["api_key"] = data["api_key"]

    config["llm"] = llm
    pm.save_profile_config(namespace, config)
    return {"success": True}


@app.delete("/api/profiles/{namespace}")
async def delete_profile_api(
    namespace: str,
    delete_data: bool = False,
    token_info: TokenInfo = Depends(verify_token)
):
    """删除 Profile（谨慎！）"""
    if token_info.namespace != "default":
        raise HTTPException(status_code=403, detail="只能从 default namespace 管理角色")
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    if namespace == "default":
        raise HTTPException(status_code=400, detail="不能删除 default profile")
    
    from profile_manager import ProfileManager
    
    pm = ProfileManager()
    success = pm.delete_profile(namespace, delete_data=delete_data)
    
    if success:
        return {"success": True}
    else:
        raise HTTPException(status_code=400, detail="删除失败")


@app.get("/api/profiles/{namespace}/tokens")
async def list_profile_tokens_api(
    namespace: str,
    token_info: TokenInfo = Depends(verify_token)
):
    """获取指定 namespace 的 Token 列表（仅 default namespace 的 full 权限）"""
    if token_info.namespace != "default":
        raise HTTPException(status_code=403, detail="只能从 default namespace 管理角色")
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from visual_token import list_tokens, get_qa_stats, get_visual_url
    
    tokens = list_tokens(namespace=namespace)
    result = []
    ns_param = f"&ns={namespace}" if namespace != "default" else ""
    
    for t in tokens:
        qa_stats = get_qa_stats(t['token_full'])
        result.append({
            'token_short': t['token'],
            'token_full': t['token_full'],
            'scope': t['scope'],
            'scope_label': t['scope_label'],
            'expires_at': t['expires_at'],
            'url': get_visual_url(t['token_full']) + ns_param
        })
    
    return {"tokens": result, "namespace": namespace}


class CreateProfileTokenRequest(BaseModel):
    scope: str = "full"
    duration: str = "30d"


@app.post("/api/profiles/{namespace}/token")
async def create_profile_token_api(
    namespace: str,
    request: CreateProfileTokenRequest,
    token_info: TokenInfo = Depends(verify_token)
):
    """为指定 namespace 创建 Token（仅 default namespace 的 full 权限）"""
    if token_info.namespace != "default":
        raise HTTPException(status_code=403, detail="只能从 default namespace 管理角色")
    if not can_see_private(token_info):
        raise HTTPException(status_code=403, detail="Full access required")
    
    from profile_manager import ProfileManager
    from visual_token import generate_token, get_visual_url
    
    pm = ProfileManager()
    if not pm.get_profile(namespace):
        raise HTTPException(status_code=404, detail="Profile not found")
    
    result = generate_token(
        duration=request.duration,
        scope=request.scope,
        namespace=namespace,
        note=f"从 default 创建"
    )
    
    ns_param = f"&ns={namespace}" if namespace != "default" else ""
    return {
        'success': True,
        'token': result['token'],
        'namespace': namespace,
        'scope': result['scope'],
        'expires_at': result['expires_at'],
        'url': get_visual_url(result['token']) + ns_param
    }


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
