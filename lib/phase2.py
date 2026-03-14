#!/usr/bin/env python3
"""
Cogmate - Phase 2 Features
==============================
1. 抽象层管理 (AbstractionManager)
2. 事实清理建议 (CleanupManager)
3. 多源深度搜索 (/research)
4. PageIndex 自动构建

使用:
    from phase2 import AbstractionManager, CleanupManager, ResearchEngine, PageIndexBuilder
"""

import json
import uuid
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from cogmate_core import CogmateAgent
from config import get_sqlite, get_neo4j, setup_logging, PROJECT_ROOT

logger = setup_logging("phase2")

# 配置
CONFIG_PATH = PROJECT_ROOT / "config/sources.json"
ABSTRACTION_THRESHOLD = 5  # 主题簇节点数触发阈值
CLEANUP_DAYS = 60  # 清理阈值天数


class AbstractionManager:
    """抽象层管理器"""
    
    def __init__(self):
        self.cogmate = CogmateAgent()
        self.threshold = ABSTRACTION_THRESHOLD
    
    def find_abstraction_candidates(self) -> List[Dict]:
        """
        查找可以提炼抽象的主题簇
        
        Returns:
            [{"cluster_name", "fact_ids", "summaries", "suggested_abstraction"}, ...]
        """
        driver = get_neo4j()
        candidates = []
        
        with driver.session() as session:
            # 使用社区检测找主题簇
            # 简化版：按连通分量分组
            result = session.run("""
                MATCH (f:Fact)
                WITH f
                OPTIONAL MATCH (f)-[*1..2]-(connected:Fact)
                WITH f, collect(DISTINCT connected) + [f] AS cluster
                WITH cluster, size(cluster) AS cluster_size
                WHERE cluster_size >= $threshold
                UNWIND cluster AS node
                WITH cluster, collect(DISTINCT node.fact_id) AS fact_ids, 
                     collect(DISTINCT node.summary) AS summaries,
                     collect(DISTINCT node.content_type) AS types
                WHERE size(fact_ids) >= $threshold
                RETURN fact_ids, summaries, types
                LIMIT 10
            """, threshold=self.threshold)
            
            seen_clusters = set()
            for record in result:
                fact_ids = record["fact_ids"]
                cluster_key = tuple(sorted(fact_ids[:3]))  # 用前3个ID作为簇标识
                
                if cluster_key not in seen_clusters and len(fact_ids) >= self.threshold:
                    seen_clusters.add(cluster_key)
                    candidates.append({
                        "fact_ids": fact_ids,
                        "summaries": record["summaries"],
                        "types": record["types"],
                        "size": len(fact_ids)
                    })
        
        return candidates
    
    def generate_abstraction_draft(self, fact_ids: List[str], summaries: List[str]) -> Dict:
        """
        为主题簇生成抽象层草稿
        
        Returns:
            {"name", "description", "domain", "confidence"}
        """
        # 合并摘要分析主题
        combined = " | ".join(summaries[:10])
        
        # 简单的主题提取（实际应用中可用LLM增强）
        # 这里用关键词频率估计
        keywords = {}
        for s in summaries:
            for word in s.split():
                if len(word) > 2:
                    keywords[word] = keywords.get(word, 0) + 1
        
        top_keywords = sorted(keywords.items(), key=lambda x: -x[1])[:5]
        domain = top_keywords[0][0] if top_keywords else "未分类"
        
        # 生成草稿描述
        description = f"基于 {len(fact_ids)} 个相关事实的规律提炼（待确认）"
        
        return {
            "name": f"{domain}相关规律",
            "description": description,
            "domain": domain,
            "source_fact_ids": fact_ids,
            "confidence": 3
        }
    
    def save_draft(self, draft: Dict) -> str:
        """保存草稿到数据库"""
        conn = get_sqlite()
        cursor = conn.cursor()
        
        abstraction_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO abstractions 
            (abstraction_id, name, description, domain, source_fact_ids, 
             confidence, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?)
        """, (
            abstraction_id,
            draft["name"],
            draft["description"],
            draft["domain"],
            json.dumps(draft["source_fact_ids"]),
            draft["confidence"],
            now, now
        ))
        
        conn.commit()
        conn.close()
        return abstraction_id
    
    def confirm_abstraction(self, abstraction_id: str, 
                           name: Optional[str] = None,
                           description: Optional[str] = None) -> bool:
        """确认抽象层记录"""
        conn = get_sqlite()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        if name or description:
            updates = []
            params = []
            if name:
                updates.append("name = ?")
                params.append(name)
            if description:
                updates.append("description = ?")
                params.append(description)
            updates.append("status = 'confirmed'")
            updates.append("confirmed_at = ?")
            params.append(now)
            updates.append("updated_at = ?")
            params.append(now)
            params.append(abstraction_id)
            
            cursor.execute(f"""
                UPDATE abstractions SET {', '.join(updates)}
                WHERE abstraction_id = ?
            """, params)
        else:
            cursor.execute("""
                UPDATE abstractions 
                SET status = 'confirmed', confirmed_at = ?, updated_at = ?
                WHERE abstraction_id = ?
            """, (now, now, abstraction_id))
        
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    
    def list_abstractions(self, status: Optional[str] = None) -> List[Dict]:
        """列出抽象层记录"""
        conn = get_sqlite()
        cursor = conn.cursor()
        
        if status:
            cursor.execute(
                "SELECT * FROM abstractions WHERE status = ? ORDER BY created_at DESC",
                (status,)
            )
        else:
            cursor.execute("SELECT * FROM abstractions ORDER BY created_at DESC")
        
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(zip(columns, row)) for row in rows]


class CleanupManager:
    """事实清理管理器"""
    
    def __init__(self):
        self.cogmate = CogmateAgent()
        self.cleanup_days = CLEANUP_DAYS
    
    def find_cleanup_candidates(self) -> List[Dict]:
        """
        查找符合清理条件的事实
        
        条件：
        1. 超过 60 天未被检索
        2. 图谱中为孤立节点
        3. 未被任何抽象层引用
        """
        conn = get_sqlite()
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=self.cleanup_days)).isoformat()
        
        # 查询长期未使用的事实
        cursor.execute("""
            SELECT fact_id, summary, content_type, source_type, 
                   source_url, created_at, last_retrieved_at, retrieval_count
            FROM facts
            WHERE (last_retrieved_at IS NULL OR last_retrieved_at < ?)
            AND created_at < ?
            ORDER BY created_at ASC
        """, (cutoff_date, cutoff_date))
        
        columns = [desc[0] for desc in cursor.description]
        candidates = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        
        # 过滤：只保留孤立节点
        driver = get_neo4j()
        orphan_candidates = []
        
        with driver.session() as session:
            for c in candidates:
                result = session.run("""
                    MATCH (f:Fact {fact_id: $fid})
                    WHERE NOT (f)-[]-()
                    RETURN f.fact_id AS fid
                """, fid=c["fact_id"])
                
                if result.single():
                    # 检查是否被抽象层引用
                    conn2 = get_sqlite()
                    cursor2 = conn2.cursor()
                    cursor2.execute(
                        "SELECT 1 FROM abstractions WHERE source_fact_ids LIKE ?",
                        (f'%{c["fact_id"]}%',)
                    )
                    if not cursor2.fetchone():
                        orphan_candidates.append(c)
                    conn2.close()
        
        return orphan_candidates
    
    def delete_facts(self, fact_ids: List[str]) -> int:
        """删除指定事实（三库同步）"""
        deleted = 0
        for fid in fact_ids:
            if self.cogmate.delete(fid):
                deleted += 1
        return deleted
    
    def generate_cleanup_report(self) -> str:
        """生成清理建议报告"""
        candidates = self.find_cleanup_candidates()
        
        if not candidates:
            return "✅ 无清理建议\n\n所有事实都在活跃使用中或有关联。"
        
        lines = [f"🗑️ **清理建议** ({len(candidates)} 条符合条件)\n"]
        lines.append("以下事实超过60天未被使用，且无任何关联：\n")
        
        for i, c in enumerate(candidates[:10], 1):
            source = c.get("source_type", "unknown")
            url = c.get("source_url", "")
            lines.append(f"{i}. [{c['fact_id'][:8]}] {c['created_at'][:10]}")
            lines.append(f"   来源: {source}" + (f" ({url})" if url else ""))
            lines.append(f"   摘要: {c['summary'][:50]}...")
            lines.append("")
        
        if len(candidates) > 10:
            lines.append(f"... 还有 {len(candidates) - 10} 条")
        
        lines.append("\n回复「清理 1 2 3」删除选中项，「清理全部」全部删除，「跳过」保留。")
        
        return "\n".join(lines)


class ResearchEngine:
    """多源深度搜索引擎"""
    
    def __init__(self):
        self.sources = self._load_sources()
        self.max_sources = 5
    
    def _load_sources(self) -> Dict:
        """加载数据源配置"""
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                return json.load(f)
        return {"sources": {}, "cross_validation_rules": {}}
    
    def get_sources_for_topic(self, topic: str) -> List[Dict]:
        """根据主题选择合适的数据源"""
        all_sources = []
        
        # 根据关键词匹配领域
        topic_lower = topic.lower()
        
        domain_hints = {
            "财经": ["财经_综合", "财经_中文", "投资_理财"],
            "投资": ["投资_理财", "财经_综合", "财经_中文"],
            "科技": ["科技_综合", "科技_中文", "AI_专业"],
            "ai": ["AI_专业", "科技_综合", "学术_通用"],
            "工业": ["工业_制造", "咨询_研究"],
            "制造": ["工业_制造", "咨询_研究"],
        }
        
        matched_domains = []
        for keyword, domains in domain_hints.items():
            if keyword in topic_lower:
                matched_domains.extend(domains)
        
        # 如果没匹配到，使用默认域
        if not matched_domains:
            matched_domains = ["科技_综合", "财经_综合", "咨询_研究", "学术_通用"]
        
        # 去重并获取源
        seen_domains = set()
        for domain in matched_domains:
            if domain not in seen_domains and domain in self.sources.get("sources", {}):
                seen_domains.add(domain)
                all_sources.extend(self.sources["sources"][domain])
        
        # 按权重排序并返回 top N
        weights = self.sources.get("cross_validation_rules", {}).get("weight", {})
        all_sources.sort(key=lambda x: -weights.get(x.get("type", "news"), 1.0))
        
        return all_sources[:self.max_sources]
    
    def format_research_prompt(self, topic: str) -> Dict:
        """生成研究搜索提示"""
        sources = self.get_sources_for_topic(topic)
        
        return {
            "topic": topic,
            "recommended_sources": sources,
            "search_queries": [
                f"{topic}",
                f"{topic} analysis",
                f"{topic} 2026",
            ],
            "cross_validation": True
        }


class PageIndexBuilder:
    """PageIndex 自动构建器"""
    
    def __init__(self):
        self.cogmate = CogmateAgent()
    
    def build_index(self) -> Dict:
        """
        基于图谱自动构建 PageIndex
        
        Returns:
            {"root": {...}, "nodes": [...]}
        """
        driver = get_neo4j()
        
        # 获取所有节点及其领域
        nodes_by_domain = {}
        
        with driver.session() as session:
            result = session.run("""
                MATCH (f:Fact)
                RETURN f.fact_id AS fact_id, f.summary AS summary, 
                       f.content_type AS content_type
            """)
            
            for record in result:
                fid = record["fact_id"]
                summary = record["summary"] or ""
                ctype = record["content_type"] or "未分类"
                
                # 简单的领域推断
                domain = self._infer_domain(summary)
                
                if domain not in nodes_by_domain:
                    nodes_by_domain[domain] = []
                nodes_by_domain[domain].append({
                    "fact_id": fid,
                    "summary": summary[:50],
                    "content_type": ctype
                })
        
        # 构建树结构
        tree = {
            "root": {"name": "知识库", "children": []},
            "domains": {}
        }
        
        for domain, facts in nodes_by_domain.items():
            tree["domains"][domain] = {
                "name": domain,
                "count": len(facts),
                "facts": facts
            }
            tree["root"]["children"].append({
                "name": domain,
                "count": len(facts)
            })
        
        # 保存到数据库
        self._save_index(tree)
        
        return tree
    
    def _infer_domain(self, summary: str) -> str:
        """推断摘要所属领域"""
        domain_keywords = {
            "AI/技术": ["AI", "编程", "代码", "技术", "模型", "算法", "Cursor", "OpenClaw"],
            "经济/金融": ["经济", "金融", "投资", "股票", "基金", "黄金", "美元", "通胀", "油价"],
            "战争/地缘": ["战争", "军事", "伊朗", "俄罗斯", "冲突", "地缘"],
            "个人/职业": ["副业", "工作", "职业", "辞职", "收入", "迷茫"],
            "认知/思维": ["规律", "模式", "框架", "分析", "思考", "决策"],
        }
        
        for domain, keywords in domain_keywords.items():
            for kw in keywords:
                if kw in summary:
                    return domain
        
        return "其他"
    
    def _save_index(self, tree: Dict):
        """保存索引到数据库"""
        conn = get_sqlite()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # 清空旧索引
        cursor.execute("DELETE FROM page_index")
        
        # 插入根节点
        root_id = "root"
        cursor.execute("""
            INSERT INTO page_index (node_id, parent_id, name, node_type, level, created_at)
            VALUES (?, NULL, ?, 'root', 0, ?)
        """, (root_id, tree["root"]["name"], now))
        
        # 插入领域节点
        for i, (domain, data) in enumerate(tree["domains"].items()):
            domain_id = f"domain_{i}"
            cursor.execute("""
                INSERT INTO page_index (node_id, parent_id, name, node_type, level, sort_order, created_at)
                VALUES (?, ?, ?, 'category', 1, ?, ?)
            """, (domain_id, root_id, domain, i, now))
            
            # 插入事实引用
            for j, fact in enumerate(data["facts"]):
                fact_node_id = f"{domain_id}_{j}"
                cursor.execute("""
                    INSERT INTO page_index (node_id, parent_id, name, node_type, ref_id, level, sort_order, created_at)
                    VALUES (?, ?, ?, 'fact', ?, 2, ?, ?)
                """, (fact_node_id, domain_id, fact["summary"], fact["fact_id"], j, now))
        
        conn.commit()
        conn.close()
    
    def get_tree_view(self) -> str:
        """获取树形视图文本"""
        conn = get_sqlite()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT node_id, parent_id, name, node_type, ref_id, level
            FROM page_index
            ORDER BY level, sort_order
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return "📚 PageIndex 为空，请先运行 build_index()"
        
        lines = ["📚 **知识库索引**\n"]
        
        # 按层级组织
        by_parent = {}
        for row in rows:
            parent = row[1] or "none"
            if parent not in by_parent:
                by_parent[parent] = []
            by_parent[parent].append(row)
        
        def render_node(node_id, indent=0):
            children = by_parent.get(node_id, [])
            for node in children:
                nid, pid, name, ntype, ref_id, level = node
                prefix = "  " * indent
                if ntype == "root":
                    lines.append(f"{prefix}📁 {name}")
                elif ntype == "category":
                    count = len(by_parent.get(nid, []))
                    lines.append(f"{prefix}📂 {name} ({count})")
                else:
                    lines.append(f"{prefix}📄 {name[:30]}...")
                render_node(nid, indent + 1)
        
        render_node("none")
        
        return "\n".join(lines)


# 测试
if __name__ == "__main__":
    print("=== 测试 PageIndex ===")
    builder = PageIndexBuilder()
    tree = builder.build_index()
    print(f"领域数: {len(tree['domains'])}")
    print(builder.get_tree_view())
