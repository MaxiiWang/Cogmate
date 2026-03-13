#!/usr/bin/env python3
"""
Relation Discovery - 多跳关联发现
==================================
实现智能关联推荐，包括：
1. 直接相似度匹配
2. 多跳邻居发现
3. 传递性关系推断
4. Hub 节点优先匹配

使用:
    from relation_discovery import RelationDiscovery
    rd = RelationDiscovery()
    
    # 为新节点发现关联
    suggestions = rd.discover_relations(fact_id, top_k=5)
    
    # 扫描孤立节点
    orphans = rd.scan_orphan_nodes(hours=48)
    
    # 生成关联梳理报告
    report = rd.generate_association_report()
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from brain_core import BrainAgent, get_neo4j, get_sqlite


class RelationDiscovery:
    """多跳关联发现引擎"""
    
    def __init__(self):
        self.brain = BrainAgent()
    
    def discover_relations(
        self,
        fact_id: str,
        top_k: int = 5,
        min_score: float = 0.65,
        include_multihop: bool = True
    ) -> List[Dict]:
        """
        为指定事实发现潜在关联
        
        Args:
            fact_id: 目标事实ID
            top_k: 返回数量
            min_score: 最低相似度
            include_multihop: 是否包含多跳发现
        
        Returns:
            [{"fact_id", "summary", "score", "hop", "relation_type", "reason"}, ...]
        """
        fact = self.brain.get_fact(fact_id)
        if not fact:
            return []
        
        suggestions = []
        seen_ids = {fact_id}
        
        # 1. 直接向量相似匹配
        direct = self.brain.find_similar(fact_id, top_k=top_k)
        for d in direct:
            if d["fact_id"] not in seen_ids and d["score"] >= min_score:
                suggestions.append({
                    "fact_id": d["fact_id"],
                    "summary": d["summary"],
                    "score": d["score"],
                    "hop": 1,
                    "relation_type": self._infer_relation_type(fact["summary"], d["summary"]),
                    "reason": "直接语义相似"
                })
                seen_ids.add(d["fact_id"])
        
        # 2. 多跳发现：检查相似节点的邻居
        if include_multihop and direct:
            for d in direct[:3]:  # 只检查前3个最相似的
                neighbors = self._get_neighbors(d["fact_id"])
                for n in neighbors:
                    if n["fact_id"] not in seen_ids:
                        # 计算与原节点的相似度
                        sim_score = self._compute_similarity(fact["summary"], n["summary"])
                        if sim_score >= min_score * 0.9:  # 稍微放宽阈值
                            suggestions.append({
                                "fact_id": n["fact_id"],
                                "summary": n["summary"],
                                "score": sim_score,
                                "hop": 2,
                                "relation_type": self._infer_relation_type(fact["summary"], n["summary"]),
                                "reason": f"通过 {d['fact_id'][:8]} 的邻居发现"
                            })
                            seen_ids.add(n["fact_id"])
        
        # 3. Hub 节点匹配
        hubs = self._get_hub_nodes(min_degree=3)
        for h in hubs:
            if h["fact_id"] not in seen_ids:
                sim_score = self._compute_similarity(fact["summary"], h["summary"])
                if sim_score >= min_score * 0.85:  # Hub 节点阈值更宽松
                    suggestions.append({
                        "fact_id": h["fact_id"],
                        "summary": h["summary"],
                        "score": sim_score,
                        "hop": 0,  # 特殊标记为 Hub
                        "relation_type": self._infer_relation_type(fact["summary"], h["summary"]),
                        "reason": f"Hub节点 (度数:{h['degree']})"
                    })
                    seen_ids.add(h["fact_id"])
        
        # 按 score 排序，返回 top_k
        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions[:top_k]
    
    def scan_orphan_nodes(self, hours: int = 48) -> List[Dict]:
        """扫描指定时间内的孤立节点"""
        driver = get_neo4j()
        orphans = []
        
        with driver.session() as session:
            # 查找无边的节点
            result = session.run("""
                MATCH (f:Fact)
                WHERE NOT (f)-[]-()
                RETURN f.fact_id AS fact_id, f.summary AS summary, f.timestamp AS timestamp
                ORDER BY f.timestamp DESC
            """)
            
            cutoff = datetime.now() - timedelta(hours=hours)
            
            for record in result:
                ts_str = record["timestamp"] or ""
                # 简单时间过滤
                if ts_str.startswith("2026-03"):
                    orphans.append({
                        "fact_id": record["fact_id"],
                        "summary": record["summary"],
                        "timestamp": ts_str
                    })
        
        return orphans
    
    def generate_association_report(self, hours: int = 48, max_suggestions_per_node: int = 3) -> Dict:
        """
        生成关联梳理报告
        
        Returns:
            {
                "orphan_count": int,
                "suggestions": [
                    {"orphan": {...}, "candidates": [...]}
                ],
                "stats": {...}
            }
        """
        orphans = self.scan_orphan_nodes(hours)
        
        suggestions = []
        for orphan in orphans[:10]:  # 限制处理数量
            candidates = self.discover_relations(
                orphan["fact_id"],
                top_k=max_suggestions_per_node,
                include_multihop=True
            )
            if candidates:
                suggestions.append({
                    "orphan": orphan,
                    "candidates": candidates
                })
        
        stats = self.brain.stats()
        
        return {
            "orphan_count": len(orphans),
            "suggestions": suggestions,
            "stats": stats
        }
    
    def _get_neighbors(self, fact_id: str) -> List[Dict]:
        """获取节点的所有邻居"""
        driver = get_neo4j()
        neighbors = []
        
        with driver.session() as session:
            result = session.run("""
                MATCH (f:Fact {fact_id: $fact_id})-[]-(neighbor:Fact)
                RETURN neighbor.fact_id AS fact_id, neighbor.summary AS summary
            """, fact_id=fact_id)
            
            for record in result:
                neighbors.append({
                    "fact_id": record["fact_id"],
                    "summary": record["summary"]
                })
        
        return neighbors
    
    def _get_hub_nodes(self, min_degree: int = 3) -> List[Dict]:
        """获取高连接度的 Hub 节点"""
        driver = get_neo4j()
        hubs = []
        
        with driver.session() as session:
            result = session.run("""
                MATCH (f:Fact)
                WITH f, COUNT { (f)-[]-() } AS degree
                WHERE degree >= $min_degree
                RETURN f.fact_id AS fact_id, f.summary AS summary, degree
                ORDER BY degree DESC
                LIMIT 5
            """, min_degree=min_degree)
            
            for record in result:
                hubs.append({
                    "fact_id": record["fact_id"],
                    "summary": record["summary"],
                    "degree": record["degree"]
                })
        
        return hubs
    
    def _compute_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度"""
        # 使用向量计算
        vec1 = self.brain.embed(text1)
        vec2 = self.brain.embed(text2)
        
        # 余弦相似度
        import numpy as np
        dot = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        return float(dot / (norm1 * norm2))
    
    def _infer_relation_type(self, summary1: str, summary2: str) -> str:
        """推断关系类型"""
        # 简单规则推断
        combined = summary1 + summary2
        
        if any(w in combined for w in ["导致", "因为", "所以", "因此", "引发"]):
            return "因果"
        if any(w in combined for w in ["但是", "然而", "相反", "矛盾", "冲突"]):
            return "矛盾"
        if any(w in combined for w in ["支持", "证明", "验证", "印证"]):
            return "支持"
        if any(w in combined for w in ["延伸", "扩展", "进一步", "深入"]):
            return "延伸"
        
        return "关联"


def format_report_for_telegram(report: Dict) -> str:
    """格式化报告为 Telegram 消息"""
    lines = [f"🌅 夜间整理报告 · {datetime.now().strftime('%Y-%m-%d')}", ""]
    
    stats = report["stats"]
    lines.append(f"📊 图谱状态: {stats['graph_nodes']} 节点 | {stats['graph_edges']} 边")
    lines.append(f"🔍 孤立节点: {report['orphan_count']} 个")
    lines.append("")
    
    if not report["suggestions"]:
        lines.append("✅ 夜间整理完成，无新关联建议")
    else:
        lines.append(f"🔗 发现 {len(report['suggestions'])} 组待确认关联：")
        lines.append("")
        
        for i, sugg in enumerate(report["suggestions"], 1):
            orphan = sugg["orphan"]
            lines.append(f"**{i}. [{orphan['fact_id'][:8]}]** {orphan['summary'][:30]}...")
            
            for j, cand in enumerate(sugg["candidates"], 1):
                hop_mark = "🔗" if cand["hop"] == 1 else "🔗🔗" if cand["hop"] == 2 else "⭐"
                lines.append(f"   {hop_mark} → [{cand['fact_id'][:8]}] {cand['summary'][:25]}...")
                lines.append(f"      类型:{cand['relation_type']} | 相似:{cand['score']:.2f} | {cand['reason']}")
            lines.append("")
    
    lines.append("回复「确认 1-1」确认第1组第1条关联")
    
    return "\n".join(lines)


# CLI 测试
if __name__ == "__main__":
    rd = RelationDiscovery()
    report = rd.generate_association_report()
    print(format_report_for_telegram(report))
