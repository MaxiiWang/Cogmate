#!/usr/bin/env python3
"""
Brain Agent - Slash Commands
=============================
实现 /why, /decide, /hub, /conflict 等命令

使用:
    from commands import CommandHandler
    handler = CommandHandler()
    result = handler.execute('/why 为什么我对AI持乐观态度')
"""

from typing import Dict, List, Optional, Tuple
from brain_core import BrainAgent, get_neo4j

# Phase 2 imports
try:
    from phase2 import AbstractionManager, CleanupManager, ResearchEngine, PageIndexBuilder
    PHASE2_AVAILABLE = True
except ImportError:
    PHASE2_AVAILABLE = False


class CommandHandler:
    """Slash 命令处理器"""
    
    def __init__(self):
        self.brain = BrainAgent()
    
    def execute(self, command: str) -> Dict:
        """
        执行 slash 命令
        
        Returns:
            {"command": str, "success": bool, "result": str, "data": any}
        """
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        handlers = {
            "/why": self.cmd_why,
            "/decide": self.cmd_decide,
            "/hub": self.cmd_hub,
            "/conflict": self.cmd_conflict,
            "/status": self.cmd_status,
            "/health": self.cmd_health,
            "/help": self.cmd_help,
            "/today": self.cmd_today,
            # Phase 2 commands
            "/abstract": self.cmd_abstract,
            "/cleanup": self.cmd_cleanup,
            "/research": self.cmd_research,
            "/tree": self.cmd_tree,
            "/source": self.cmd_source,
            # Phase 3 - Visual
            "/visual": self.cmd_visual,
        }
        
        if cmd in handlers:
            return handlers[cmd](args)
        else:
            return {
                "command": cmd,
                "success": False,
                "result": f"未知命令: {cmd}",
                "data": None
            }
    
    def cmd_why(self, query: str) -> Dict:
        """
        /why [问题] - 从知识库寻找决策依据，含图谱路径推理
        """
        if not query:
            return {
                "command": "/why",
                "success": False,
                "result": "请提供问题，例如: /why 为什么我对AI持乐观态度",
                "data": None
            }
        
        # 1. 向量检索相关事实
        search_results = self.brain.query(query, top_k=5)
        relevant_facts = search_results.get("vector_results", [])
        
        if not relevant_facts:
            return {
                "command": "/why",
                "success": True,
                "result": f"🔍 关于「{query}」\n\n知识库中暂无相关记录。",
                "data": {"facts": [], "paths": []}
            }
        
        # 2. 获取图谱路径
        fact_ids = [f["fact_id"] for f in relevant_facts[:3]]
        paths = self._find_paths_between(fact_ids)
        
        # 3. 格式化输出
        lines = [f"🔍 关于「{query}」\n"]
        
        lines.append("📌 **相关记录**:")
        for f in relevant_facts[:5]:
            score_bar = "█" * int(f["score"] * 10) + "░" * (10 - int(f["score"] * 10))
            lines.append(f"  [{f['fact_id'][:8]}] {f['summary'][:50]}...")
            lines.append(f"    相关度: {score_bar} {f['score']:.2f}")
        
        if paths:
            lines.append("\n🕸️ **图谱路径**:")
            for path in paths[:3]:
                lines.append(f"  {path}")
        
        # 4. 检查是否有矛盾
        contradictions = self._find_contradictions(fact_ids)
        if contradictions:
            lines.append("\n⚠️ **存在矛盾观点**:")
            for c in contradictions:
                lines.append(f"  {c}")
        
        return {
            "command": "/why",
            "success": True,
            "result": "\n".join(lines),
            "data": {"facts": relevant_facts, "paths": paths, "contradictions": contradictions}
        }
    
    def cmd_decide(self, topic: str) -> Dict:
        """
        /decide [描述] - 决策辅助，正反证据双向呈现
        """
        if not topic:
            return {
                "command": "/decide",
                "success": False,
                "result": "请提供决策主题，例如: /decide 是否应该辞职",
                "data": None
            }
        
        # 1. 检索相关事实
        search_results = self.brain.query(topic, top_k=10)
        relevant_facts = search_results.get("vector_results", [])
        
        if not relevant_facts:
            return {
                "command": "/decide",
                "success": True,
                "result": f"⚖️ 关于「{topic}」\n\n知识库中暂无相关记录，无法提供决策依据。",
                "data": None
            }
        
        # 2. 分类：支持 vs 反对 vs 中立
        # 简单基于情绪标签和关系类型分类
        supporting = []
        opposing = []
        neutral = []
        
        for f in relevant_facts:
            emotion = f.get("emotion_tag", "中性")
            if emotion in ["积极", "兴奋"]:
                supporting.append(f)
            elif emotion in ["消极", "困惑"]:
                opposing.append(f)
            else:
                neutral.append(f)
        
        # 3. 格式化输出
        lines = [f"⚖️ 决策分析：「{topic}」\n"]
        
        if supporting:
            lines.append("✅ **支持因素**:")
            for f in supporting[:3]:
                lines.append(f"  [{f['fact_id'][:8]}] {f['summary'][:60]}...")
        
        if opposing:
            lines.append("\n❌ **阻碍因素**:")
            for f in opposing[:3]:
                lines.append(f"  [{f['fact_id'][:8]}] {f['summary'][:60]}...")
        
        if neutral:
            lines.append("\n📋 **相关背景**:")
            for f in neutral[:3]:
                lines.append(f"  [{f['fact_id'][:8]}] {f['summary'][:60]}...")
        
        # 4. 决策建议
        lines.append("\n💡 **建议**:")
        if len(supporting) > len(opposing):
            lines.append("  整体证据偏向支持，但请关注阻碍因素。")
        elif len(opposing) > len(supporting):
            lines.append("  整体证据偏向谨慎，建议进一步评估风险。")
        else:
            lines.append("  证据较为均衡，建议补充更多信息后决策。")
        
        return {
            "command": "/decide",
            "success": True,
            "result": "\n".join(lines),
            "data": {"supporting": supporting, "opposing": opposing, "neutral": neutral}
        }
    
    def cmd_hub(self, args: str) -> Dict:
        """
        /hub - 列出图谱中度数最高的知识枢纽节点
        """
        driver = get_neo4j()
        hubs = []
        
        with driver.session() as session:
            result = session.run("""
                MATCH (f:Fact)
                WITH f, COUNT { (f)-[]-() } AS degree
                WHERE degree > 0
                RETURN f.fact_id AS fact_id, f.summary AS summary, 
                       f.content_type AS content_type, degree
                ORDER BY degree DESC
                LIMIT 10
            """)
            
            for record in result:
                hubs.append({
                    "fact_id": record["fact_id"],
                    "summary": record["summary"],
                    "content_type": record["content_type"],
                    "degree": record["degree"]
                })
        
        if not hubs:
            return {
                "command": "/hub",
                "success": True,
                "result": "🕸️ 图谱枢纽节点\n\n当前图谱中没有连接的节点。",
                "data": []
            }
        
        lines = ["🕸️ **图谱枢纽节点** (按连接度排序)\n"]
        for i, h in enumerate(hubs, 1):
            degree_bar = "●" * h["degree"] + "○" * (5 - min(h["degree"], 5))
            lines.append(f"{i}. [{h['fact_id'][:8]}] {degree_bar} 度数:{h['degree']}")
            lines.append(f"   {h['summary'][:50]}...")
            lines.append(f"   类型: {h['content_type']}")
            lines.append("")
        
        return {
            "command": "/hub",
            "success": True,
            "result": "\n".join(lines),
            "data": hubs
        }
    
    def cmd_conflict(self, args: str) -> Dict:
        """
        /conflict - 列出所有矛盾关系
        """
        driver = get_neo4j()
        conflicts = []
        
        with driver.session() as session:
            result = session.run("""
                MATCH (a:Fact)-[r:矛盾]->(b:Fact)
                RETURN a.fact_id AS from_id, a.summary AS from_summary,
                       b.fact_id AS to_id, b.summary AS to_summary,
                       r.confidence AS confidence
                ORDER BY r.confidence DESC
            """)
            
            for record in result:
                conflicts.append({
                    "from_id": record["from_id"],
                    "from_summary": record["from_summary"],
                    "to_id": record["to_id"],
                    "to_summary": record["to_summary"],
                    "confidence": record["confidence"]
                })
        
        if not conflicts:
            return {
                "command": "/conflict",
                "success": True,
                "result": "⚔️ 矛盾关系\n\n当前图谱中没有标记的矛盾关系。\n\n这可能意味着：\n- 知识体系较为一致\n- 或矛盾尚未被发现/标记",
                "data": []
            }
        
        lines = ["⚔️ **矛盾关系列表**\n"]
        for i, c in enumerate(conflicts, 1):
            conf_bar = "█" * c["confidence"] + "░" * (5 - c["confidence"])
            lines.append(f"{i}. [{c['from_id'][:8]}] ⚡ [{c['to_id'][:8]}]")
            lines.append(f"   置信度: {conf_bar} {c['confidence']}/5")
            lines.append(f"   A: {c['from_summary'][:40]}...")
            lines.append(f"   B: {c['to_summary'][:40]}...")
            lines.append("")
        
        return {
            "command": "/conflict",
            "success": True,
            "result": "\n".join(lines),
            "data": conflicts
        }
    
    def cmd_status(self, args: str) -> Dict:
        """
        /status - 系统状态
        """
        stats = self.brain.stats()
        
        # 计算健康度指标
        total_nodes = stats["graph_nodes"]
        total_edges = stats["graph_edges"]
        
        # 孤立节点计算
        driver = get_neo4j()
        with driver.session() as session:
            result = session.run("""
                MATCH (f:Fact)
                WHERE NOT (f)-[]-()
                RETURN count(f) AS orphan_count
            """)
            orphan_count = result.single()["orphan_count"]
        
        orphan_ratio = orphan_count / total_nodes * 100 if total_nodes > 0 else 0
        avg_degree = (total_edges * 2) / total_nodes if total_nodes > 0 else 0
        
        # 健康度评估
        health = "🟢 良好"
        if orphan_ratio > 50 or avg_degree < 1.0:
            health = "🔴 需关注"
        elif orphan_ratio > 20 or avg_degree < 2.0:
            health = "🟡 待改善"
        
        lines = [
            "📊 **系统状态**\n",
            f"📦 事实总数: {stats['total_facts']}",
            f"🕸️ 图谱节点: {stats['graph_nodes']}",
            f"🔗 图谱边数: {stats['graph_edges']}",
            f"",
            f"📈 **健康度指标**",
            f"   孤立节点: {orphan_count} ({orphan_ratio:.1f}%) — 目标 <20%",
            f"   平均度数: {avg_degree:.2f} — 目标 >2.0",
            f"   整体健康: {health}",
        ]
        
        return {
            "command": "/status",
            "success": True,
            "result": "\n".join(lines),
            "data": {
                "stats": stats,
                "orphan_count": orphan_count,
                "orphan_ratio": orphan_ratio,
                "avg_degree": avg_degree,
                "health": health
            }
        }
    
    def cmd_health(self, args: str) -> Dict:
        """
        /health - 图谱健康度报告
        /health verbose - 包含详细度数分布
        """
        try:
            from graph_health import generate_health_report, get_graph_metrics, get_improvement_suggestions
            
            verbose = 'verbose' in args.lower() or '-v' in args
            report = generate_health_report(verbose=verbose)
            
            # 获取改进建议
            metrics = get_graph_metrics()
            suggestions = get_improvement_suggestions(metrics)
            
            if suggestions and suggestions[0] != "✅ 图谱健康度良好，继续保持！":
                report += "\n\n💡 **改进建议**:\n"
                for s in suggestions:
                    report += f"   {s}\n"
            
            return {
                "command": "/health",
                "success": True,
                "result": report,
                "data": metrics
            }
        except Exception as e:
            return {
                "command": "/health",
                "success": False,
                "result": f"生成健康度报告失败: {e}",
                "data": None
            }
    
    def cmd_today(self, args: str) -> Dict:
        """
        /today - 每日晚报
        """
        try:
            from daily_report import generate_daily_report
            report = generate_daily_report()
            return {
                "command": "/today",
                "success": True,
                "result": report,
                "data": None
            }
        except Exception as e:
            return {
                "command": "/today",
                "success": False,
                "result": f"生成晚报失败: {e}",
                "data": None
            }
    
    def cmd_help(self, args: str) -> Dict:
        """
        /help - 命令帮助
        """
        help_text = """📖 **Brain Agent 命令帮助**

**检索与决策**
  `/why [问题]` — 从知识库寻找依据，含图谱路径推理
  `/decide [主题]` — 决策辅助，正反证据双向呈现

**图谱专属**
  `/hub` — 列出高连接度的枢纽节点
  `/conflict` — 列出所有矛盾关系

**抽象层**
  `/abstract` — 列出抽象层记录
  `/abstract scan` — 扫描可提炼的主题簇
  `/abstract generate <n>` — 为第n个候选生成草稿
  `/abstract confirm <id>` — 确认抽象草稿
  `/abstract view <id>` — 查看抽象详情

**知识管理 (Phase 2)**
  `/tree` — 显示知识库树形索引
  `/tree rebuild` — 重建 PageIndex
  `/cleanup` — 扫描清理候选
  `/research [主题]` — 多源深度搜索
  `/source list` — 查看可信数据源

**定时报告**
  `/today` — 今日知识晚报（每日 21:00 自动推送）
  `/health` — 图谱健康度报告（含改进建议）

**可视化**
  `/visual token [时效] [权限]` — 生成访问链接
  `/visual tokens` — 列出有效 token
  `/visual revoke <id|all>` — 撤销 token

**系统**
  `/status` — 查看系统状态
  `/help` — 显示本帮助

**日常使用**
  直接发送内容 → 自动存储
  直接提问 → 自动检索
"""
        return {
            "command": "/help",
            "success": True,
            "result": help_text,
            "data": None
        }
    
    def _find_paths_between(self, fact_ids: List[str]) -> List[str]:
        """查找节点间的图谱路径"""
        if len(fact_ids) < 2:
            return []
        
        driver = get_neo4j()
        paths = []
        
        with driver.session() as session:
            # 查找任意两个节点间的路径
            for i in range(len(fact_ids)):
                for j in range(i + 1, len(fact_ids)):
                    result = session.run("""
                        MATCH path = shortestPath(
                            (a:Fact {fact_id: $id1})-[*..3]-(b:Fact {fact_id: $id2})
                        )
                        RETURN [n IN nodes(path) | n.fact_id] AS node_ids,
                               [r IN relationships(path) | type(r)] AS rel_types
                        LIMIT 1
                    """, id1=fact_ids[i], id2=fact_ids[j])
                    
                    record = result.single()
                    if record:
                        node_ids = record["node_ids"]
                        rel_types = record["rel_types"]
                        path_str = self._format_path(node_ids, rel_types)
                        if path_str:
                            paths.append(path_str)
        
        return paths
    
    def _format_path(self, node_ids: List[str], rel_types: List[str]) -> str:
        """格式化路径为可读字符串"""
        if not node_ids:
            return ""
        
        parts = [f"[{node_ids[0][:8]}]"]
        for i, rel in enumerate(rel_types):
            parts.append(f" -[{rel}]→ [{node_ids[i+1][:8]}]")
        
        return "".join(parts)
    
    def _find_contradictions(self, fact_ids: List[str]) -> List[str]:
        """查找与给定事实相关的矛盾关系"""
        driver = get_neo4j()
        contradictions = []
        
        with driver.session() as session:
            for fid in fact_ids:
                result = session.run("""
                    MATCH (a:Fact {fact_id: $fid})-[r:矛盾]-(b:Fact)
                    RETURN a.summary AS a_summary, b.summary AS b_summary
                """, fid=fid)
                
                for record in result:
                    contradictions.append(
                        f"「{record['a_summary'][:25]}...」⚡「{record['b_summary'][:25]}...」"
                    )
        
        return contradictions
    
    # ==================== Phase 2 Commands ====================
    
    def cmd_abstract(self, args: str) -> Dict:
        """
        /abstract - 抽象层管理
        /abstract list - 列出所有抽象
        /abstract scan - 扫描候选主题簇
        /abstract generate <n> - 为第n个候选簇生成草稿
        /abstract confirm <id> [description] - 确认草稿
        /abstract view <id> - 查看抽象详情
        """
        try:
            from abstraction import (
                list_abstracts, get_qualifying_clusters, infer_cluster_theme,
                create_draft_abstract, confirm_abstract
            )
        except ImportError as e:
            return {"command": "/abstract", "success": False,
                    "result": f"抽象层模块加载失败: {e}", "data": None}
        
        parts = args.strip().split(maxsplit=1)
        action = parts[0] if parts else "list"
        action_args = parts[1] if len(parts) > 1 else ""
        
        if action == "list":
            all_abstracts = list_abstracts()
            if not all_abstracts:
                return {"command": "/abstract", "success": True,
                        "result": "📐 抽象层\n\n当前无抽象层记录。使用 `/abstract scan` 扫描候选。",
                        "data": []}
            
            lines = ["📐 **抽象层记录**\n"]
            for a in all_abstracts:
                status_icon = "✅" if a["status"] == "confirmed" else "📝"
                lines.append(f"{status_icon} [{a['abstract_id'][:8]}] {a['name']}")
                desc = a['description'][:60] if a['description'] else '(无描述)'
                lines.append(f"   {desc}...")
                lines.append(f"   节点数: {len(a['source_fact_ids'])} | 状态: {a['status']}")
                lines.append("")
            
            return {"command": "/abstract", "success": True,
                    "result": "\n".join(lines), "data": all_abstracts}
        
        elif action == "scan":
            clusters = get_qualifying_clusters()
            existing = [a['cluster_theme'] for a in list_abstracts()]
            
            # 过滤已存在的主题
            new_clusters = []
            for c in clusters:
                theme = infer_cluster_theme(c)
                if theme not in existing:
                    c['theme'] = theme
                    new_clusters.append(c)
            
            if not new_clusters:
                return {"command": "/abstract", "success": True,
                        "result": "📐 抽象层扫描\n\n未发现新的候选主题簇（现有主题已覆盖，或簇大小 < 8）。",
                        "data": []}
            
            lines = ["📐 **发现可提炼的主题簇**\n"]
            for i, c in enumerate(new_clusters[:5], 1):
                lines.append(f"{i}. {c['theme']} ({c['size']} 节点)")
                # 显示几个示例节点
                examples = [n['summary'][:30] for n in c['nodes'][:2] if n.get('summary')]
                if examples:
                    lines.append(f"   示例: {examples[0]}...")
                lines.append("")
            
            lines.append("使用 `/abstract generate 1` 为第 1 个簇生成草稿")
            
            # 缓存候选供 generate 使用
            self._abstract_candidates = new_clusters
            
            return {"command": "/abstract", "success": True,
                    "result": "\n".join(lines), "data": new_clusters}
        
        elif action == "generate":
            if not action_args:
                return {"command": "/abstract", "success": False,
                        "result": "用法: /abstract generate <编号>", "data": None}
            
            try:
                idx = int(action_args) - 1
            except ValueError:
                return {"command": "/abstract", "success": False,
                        "result": "请输入有效的数字编号", "data": None}
            
            candidates = getattr(self, '_abstract_candidates', None)
            if not candidates:
                # 重新扫描
                clusters = get_qualifying_clusters()
                existing = [a['cluster_theme'] for a in list_abstracts()]
                candidates = []
                for c in clusters:
                    theme = infer_cluster_theme(c)
                    if theme not in existing:
                        c['theme'] = theme
                        candidates.append(c)
            
            if idx < 0 or idx >= len(candidates):
                return {"command": "/abstract", "success": False,
                        "result": f"编号超出范围（1-{len(candidates)}）", "data": None}
            
            cluster = candidates[idx]
            abstract_id = create_draft_abstract(cluster, cluster['theme'])
            
            return {"command": "/abstract", "success": True,
                    "result": f"📐 已生成草稿\n\n主题: {cluster['theme']}\nID: {abstract_id[:8]}\n节点数: {cluster['size']}\n\n使用 `/abstract confirm {abstract_id[:8]} <规律描述>` 确认",
                    "data": {"id": abstract_id, "theme": cluster['theme']}}
        
        elif action == "confirm":
            parts2 = action_args.split(maxsplit=1)
            if not parts2:
                return {"command": "/abstract", "success": False,
                        "result": "用法: /abstract confirm <id> [规律描述]", "data": None}
            
            aid = parts2[0]
            description = parts2[1] if len(parts2) > 1 else None
            
            success = confirm_abstract(aid, description or "用户确认")
            if success:
                return {"command": "/abstract", "success": True,
                        "result": f"✅ 抽象 [{aid}] 已确认", "data": {"id": aid}}
            else:
                return {"command": "/abstract", "success": False,
                        "result": f"❌ 未找到抽象 [{aid}]（需完整ID或前8位）", "data": None}
        
        elif action == "view":
            if not action_args:
                return {"command": "/abstract", "success": False,
                        "result": "用法: /abstract view <id>", "data": None}
            
            all_abs = list_abstracts()
            target = None
            for a in all_abs:
                if a['abstract_id'].startswith(action_args):
                    target = a
                    break
            
            if not target:
                return {"command": "/abstract", "success": False,
                        "result": f"❌ 未找到抽象 [{action_args}]", "data": None}
            
            lines = [
                f"📐 **{target['name']}**",
                f"ID: {target['abstract_id'][:8]}",
                f"状态: {'✅ 已确认' if target['status'] == 'confirmed' else '📝 草稿'}",
                "",
                "**规律描述**:",
                target['description'] or '(无)',
                "",
                f"**溯源事实**: {len(target['source_fact_ids'])} 个",
            ]
            
            return {"command": "/abstract", "success": True,
                    "result": "\n".join(lines), "data": target}
        
        return {"command": "/abstract", "success": False,
                "result": "用法: /abstract [list|scan|generate <n>|confirm <id>|view <id>]", "data": None}
    
    def cmd_cleanup(self, args: str) -> Dict:
        """
        /cleanup - 清理建议
        /cleanup scan - 扫描候选
        /cleanup delete <ids> - 删除指定项
        """
        if not PHASE2_AVAILABLE:
            return {"command": "/cleanup", "success": False,
                    "result": "Phase 2 模块未加载", "data": None}
        
        cm = CleanupManager()
        parts = args.strip().split()
        action = parts[0] if parts else "scan"
        
        if action == "scan":
            report = cm.generate_cleanup_report()
            return {"command": "/cleanup", "success": True,
                    "result": report, "data": cm.find_cleanup_candidates()}
        
        elif action == "delete" and len(parts) > 1:
            ids_to_delete = parts[1:]
            candidates = cm.find_cleanup_candidates()
            
            if ids_to_delete[0].lower() == "all":
                to_delete = [c["fact_id"] for c in candidates]
            else:
                # 按序号选择
                to_delete = []
                for idx in ids_to_delete:
                    try:
                        i = int(idx) - 1
                        if 0 <= i < len(candidates):
                            to_delete.append(candidates[i]["fact_id"])
                    except ValueError:
                        pass
            
            if to_delete:
                deleted = cm.delete_facts(to_delete)
                return {"command": "/cleanup", "success": True,
                        "result": f"✅ 已删除 {deleted} 条记录", "data": {"deleted": deleted}}
            else:
                return {"command": "/cleanup", "success": False,
                        "result": "❌ 未找到要删除的记录", "data": None}
        
        return {"command": "/cleanup", "success": False,
                "result": "用法: /cleanup [scan|delete <ids>]", "data": None}
    
    def cmd_research(self, topic: str) -> Dict:
        """
        /research <topic> - 多源深度搜索
        """
        if not topic:
            return {"command": "/research", "success": False,
                    "result": "用法: /research <主题>", "data": None}
        
        if not PHASE2_AVAILABLE:
            return {"command": "/research", "success": False,
                    "result": "Phase 2 模块未加载", "data": None}
        
        engine = ResearchEngine()
        prompt = engine.format_research_prompt(topic)
        
        lines = [f"🔬 **深度研究: {topic}**\n"]
        lines.append("**推荐数据源**:")
        for i, s in enumerate(prompt["recommended_sources"], 1):
            lines.append(f"  {i}. {s['name']} ({s['domain']}) [{s['lang']}]")
        
        lines.append("\n**建议搜索词**:")
        for q in prompt["search_queries"]:
            lines.append(f"  • {q}")
        
        lines.append("\n💡 执行搜索后，我会交叉验证并提取高价值信息供你确认。")
        
        return {"command": "/research", "success": True,
                "result": "\n".join(lines), "data": prompt}
    
    def cmd_tree(self, args: str) -> Dict:
        """
        /tree - 显示知识库 PageIndex 树形结构
        /tree rebuild - 重建索引
        """
        if not PHASE2_AVAILABLE:
            return {"command": "/tree", "success": False,
                    "result": "Phase 2 模块未加载", "data": None}
        
        builder = PageIndexBuilder()
        parts = args.strip().split()
        
        if parts and parts[0] == "rebuild":
            tree = builder.build_index()
            return {"command": "/tree", "success": True,
                    "result": f"✅ PageIndex 已重建\n\n{builder.get_tree_view()}",
                    "data": tree}
        
        return {"command": "/tree", "success": True,
                "result": builder.get_tree_view(), "data": None}
    
    def cmd_visual(self, args: str) -> Dict:
        """
        /visual - 可视化访问管理
        /visual token [duration] [permissions] - 生成访问 token
        /visual tokens - 列出有效 token
        /visual revoke <token|all> - 撤销 token
        """
        try:
            from visual_token import (
                generate_token, list_tokens, revoke_token, 
                revoke_all_tokens, get_visual_url
            )
        except ImportError as e:
            return {"command": "/visual", "success": False,
                    "result": f"Token 模块加载失败: {e}", "data": None}
        
        parts = args.strip().split()
        action = parts[0] if parts else "token"
        
        if action == "token":
            # 解析参数
            duration = "7d"
            permissions = "full"
            
            for p in parts[1:]:
                if p in ['readonly', 'read', 'ro']:
                    permissions = 'readonly'
                elif p in ['full', 'write', 'rw']:
                    permissions = 'full'
                elif any(c.isdigit() for c in p):
                    duration = p
            
            result = generate_token(duration, permissions)
            
            # 自动获取公网 IP
            url = get_visual_url(result['token'])
            
            lines = [
                "🔗 **可视化访问链接已生成**",
                "",
                f"**URL**: `{url}`",
                "",
                f"**Token**: `{result['token'][:16]}...`",
                f"**权限**: {'🔒 只读' if permissions == 'readonly' else '✏️ 完整'}",
                f"**有效期**: {duration} (至 {result['expires_at_human']})",
                "",
                "⚠️ 请妥善保管此链接，勿分享给他人",
                "",
                "💡 使用 `/visual tokens` 查看所有有效 token",
                "💡 使用 `/visual revoke <token前8位>` 撤销"
            ]
            
            return {"command": "/visual", "success": True,
                    "result": "\n".join(lines),
                    "data": {"token": result['token'], "url": url}}
        
        elif action == "tokens":
            tokens = list_tokens()
            
            if not tokens:
                return {"command": "/visual", "success": True,
                        "result": "📋 当前无有效的访问 Token\n\n使用 `/visual token` 生成新 token",
                        "data": []}
            
            lines = ["📋 **有效的访问 Token**\n"]
            for t in tokens:
                perm_icon = '🔒' if t['permissions'] == 'readonly' else '✏️'
                lines.append(f"{perm_icon} `{t['token']}`")
                lines.append(f"   过期: {t['expires_at'][:16]} | 访问次数: {t['access_count']}")
                if t['last_access_at']:
                    lines.append(f"   最后访问: {t['last_access_at'][:16]}")
                lines.append("")
            
            return {"command": "/visual", "success": True,
                    "result": "\n".join(lines), "data": tokens}
        
        elif action == "revoke":
            if len(parts) < 2:
                return {"command": "/visual", "success": False,
                        "result": "用法: /visual revoke <token前缀|all>", "data": None}
            
            target = parts[1]
            
            if target == "all":
                count = revoke_all_tokens()
                return {"command": "/visual", "success": True,
                        "result": f"✅ 已撤销 {count} 个 token", "data": {"revoked": count}}
            else:
                # 查找匹配的 token
                tokens = list_tokens()
                matching = [t for t in tokens if t['token_full'].startswith(target)]
                
                if not matching:
                    return {"command": "/visual", "success": False,
                            "result": f"❌ 未找到以 `{target}` 开头的 token", "data": None}
                
                for t in matching:
                    revoke_token(t['token_full'])
                
                return {"command": "/visual", "success": True,
                        "result": f"✅ 已撤销 {len(matching)} 个 token", "data": {"revoked": len(matching)}}
        
        else:
            return {"command": "/visual", "success": False,
                    "result": "用法: /visual [token|tokens|revoke]", "data": None}
    
    def cmd_source(self, args: str) -> Dict:
        """
        /source - 可信源管理
        /source list - 列出所有源
        /source add <domain> - 添加源
        """
        if not PHASE2_AVAILABLE:
            return {"command": "/source", "success": False,
                    "result": "Phase 2 模块未加载", "data": None}
        
        engine = ResearchEngine()
        parts = args.strip().split()
        action = parts[0] if parts else "list"
        
        if action == "list":
            sources = engine.sources.get("sources", {})
            lines = ["📚 **可信数据源白名单**\n"]
            
            for category, source_list in sources.items():
                lines.append(f"**{category}**:")
                for s in source_list:
                    lines.append(f"  • {s['name']} ({s['domain']}) [{s['lang']}]")
                lines.append("")
            
            return {"command": "/source", "success": True,
                    "result": "\n".join(lines), "data": sources}
        
        return {"command": "/source", "success": True,
                "result": "用法: /source [list|add <domain>]", "data": None}


# CLI 测试
if __name__ == "__main__":
    import sys
    handler = CommandHandler()
    
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        result = handler.execute(cmd)
        print(result["result"])
    else:
        # 默认测试
        print(handler.execute("/status")["result"])
        print("\n" + "="*50 + "\n")
        print(handler.execute("/hub")["result"])
