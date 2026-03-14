#!/usr/bin/env python3
"""
Cogmate Core Library
========================
三库协同的核心数据操作模块

依赖:
    pip install sentence-transformers qdrant-client neo4j

使用:
    from brain_core import CogmateAgent
    cogmate = CogmateAgent()
    
    # 存储
    fact_id = cogmate.store("今天客户说系统太难用了", content_type="事件")
    
    # 检索
    results = cogmate.query("客户反馈")
"""

import uuid
import json
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# Centralized configuration
from config import (
    SQLITE_PATH, EMBEDDING_DIM, COLLECTION_NAME,
    get_embedder, get_qdrant, get_neo4j, get_sqlite,
    setup_logging
)

logger = setup_logging("brain_core")


class CogmateAgent:
    """Cogmate 核心类 - 三库协同操作"""
    
    def __init__(self, lazy_load: bool = True):
        """
        初始化 Cogmate
        
        Args:
            lazy_load: 是否延迟加载模型（默认 True，首次使用时才加载）
        """
        self.lazy_load = lazy_load
        if not lazy_load:
            # 立即加载所有组件
            get_embedder()
            get_qdrant()
            get_neo4j()
    
    def embed(self, text: str) -> List[float]:
        """生成文本的 embedding 向量"""
        embedder = get_embedder()
        vector = embedder.encode(text, normalize_embeddings=True)
        return vector.tolist()
    
    def store(
        self,
        content: str,
        content_type: str = "观点",
        emotion_tag: str = "中性",
        context: Optional[str] = None,
        source_type: str = "user_input",
        source_url: Optional[str] = None,
        valid_until: Optional[str] = None,
        temporal_type: str = "permanent"
    ) -> str:
        """
        存储新事实 - 三库同步写入
        
        Args:
            content: 事实内容（会作为 summary）
            content_type: 事件|观点|情绪|资讯|决策
            emotion_tag: 积极|消极|中性|困惑|兴奋
            context: 触发情境描述
            source_type: user_input|user_confirmed_web
            source_url: 来源URL（仅网络来源需要）
            valid_until: 有效期截止日期 (YYYY-MM 或 YYYY-MM-DD)
            temporal_type: permanent|time_bound|historical|prediction
        
        Returns:
            fact_id: 新创建的事实ID
        """
        fact_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # 1. 生成 embedding
        vector = self.embed(content)
        
        # 2. 写入 Qdrant
        self._store_qdrant(fact_id, content, content_type, emotion_tag, 
                          context, source_type, source_url, timestamp, vector)
        
        # 3. 写入 Neo4j
        self._store_neo4j(fact_id, content, content_type, timestamp, source_type)
        
        # 4. 写入 SQLite（包含时态信息）
        self._store_sqlite(fact_id, content, content_type, emotion_tag,
                          context, source_type, source_url, timestamp,
                          valid_until, temporal_type)
        
        return fact_id
    
    def _store_qdrant(self, fact_id: str, summary: str, content_type: str,
                      emotion_tag: str, context: str, source_type: str,
                      source_url: str, timestamp: str, vector: List[float]):
        """写入 Qdrant 向量数据库"""
        from qdrant_client.models import PointStruct
        
        client = get_qdrant()
        point = PointStruct(
            id=fact_id,
            vector=vector,
            payload={
                "fact_id": fact_id,
                "summary": summary,
                "content_type": content_type,
                "emotion_tag": emotion_tag,
                "context": context,
                "source_type": source_type,
                "source_url": source_url,
                "timestamp": timestamp
            }
        )
        client.upsert(collection_name=COLLECTION_NAME, points=[point])
    
    def _store_neo4j(self, fact_id: str, summary: str, content_type: str,
                     timestamp: str, source_type: str):
        """写入 Neo4j 图数据库"""
        driver = get_neo4j()
        with driver.session() as session:
            session.run("""
                CREATE (f:Fact {
                    fact_id: $fact_id,
                    summary: $summary,
                    content_type: $content_type,
                    timestamp: $timestamp,
                    source_type: $source_type
                })
            """, fact_id=fact_id, summary=summary, content_type=content_type,
                timestamp=timestamp, source_type=source_type)
    
    def _store_sqlite(self, fact_id: str, summary: str, content_type: str,
                      emotion_tag: str, context: str, source_type: str,
                      source_url: str, timestamp: str,
                      valid_until: str = None, temporal_type: str = "permanent"):
        """写入 SQLite 元数据库"""
        conn = get_sqlite()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO facts (fact_id, summary, content_type, emotion_tag,
                              context, source_type, source_url, timestamp,
                              valid_until, temporal_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fact_id, summary, content_type, emotion_tag, context,
              source_type, source_url, timestamp, valid_until, temporal_type))
        conn.commit()
        conn.close()
    
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        min_score: float = 0.5,
        include_graph: bool = True
    ) -> Dict[str, Any]:
        """
        检索知识库
        
        Args:
            query_text: 查询文本
            top_k: 返回最相似的 K 条结果
            min_score: 最低相似度阈值
            include_graph: 是否包含图谱关联查询
        
        Returns:
            {
                "vector_results": [...],  # 向量检索结果
                "graph_results": [...],   # 图谱关联结果
                "total": int
            }
        """
        # 1. 向量检索
        vector_results = self._query_qdrant(query_text, top_k, min_score)
        
        # 2. 图谱查询（基于向量检索结果的 fact_id）
        graph_results = []
        if include_graph and vector_results:
            fact_ids = [r["fact_id"] for r in vector_results]
            graph_results = self._query_neo4j_relations(fact_ids)
        
        return {
            "vector_results": vector_results,
            "graph_results": graph_results,
            "total": len(vector_results)
        }
    
    def _query_qdrant(self, query_text: str, top_k: int, min_score: float) -> List[Dict]:
        """向量检索"""
        vector = self.embed(query_text)
        client = get_qdrant()
        
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=top_k,
            score_threshold=min_score,
            with_payload=True
        )
        
        return [
            {
                "fact_id": r.id,
                "score": r.score,
                **r.payload
            }
            for r in response.points
        ]
    
    def _query_neo4j_relations(self, fact_ids: List[str]) -> List[Dict]:
        """查询图谱中的关联关系"""
        driver = get_neo4j()
        relations = []
        
        with driver.session() as session:
            # 查询与这些事实相关的所有边
            result = session.run("""
                MATCH (a:Fact)-[r]->(b:Fact)
                WHERE a.fact_id IN $fact_ids OR b.fact_id IN $fact_ids
                RETURN a.fact_id AS from_id, a.summary AS from_summary,
                       type(r) AS relation_type, r.confidence AS confidence,
                       b.fact_id AS to_id, b.summary AS to_summary
            """, fact_ids=fact_ids)
            
            for record in result:
                relations.append({
                    "from_id": record["from_id"],
                    "from_summary": record["from_summary"],
                    "relation_type": record["relation_type"],
                    "confidence": record["confidence"],
                    "to_id": record["to_id"],
                    "to_summary": record["to_summary"]
                })
        
        return relations
    
    def resolve_short_id(self, short_id: str) -> Optional[str]:
        """
        将短ID解析为完整UUID
        
        Args:
            short_id: 8位或更短的ID前缀，或完整UUID
        
        Returns:
            完整的fact_id，如果找不到返回None
        """
        # 如果已经是完整UUID格式，直接返回
        if len(short_id) == 36 and short_id.count('-') == 4:
            return short_id
        
        conn = get_sqlite()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT fact_id FROM facts WHERE fact_id LIKE ?",
            (f"{short_id}%",)
        )
        rows = cursor.fetchall()
        conn.close()
        
        if len(rows) == 1:
            return rows[0][0]
        elif len(rows) > 1:
            # 多个匹配，尝试精确匹配
            for row in rows:
                if row[0].startswith(short_id):
                    return row[0]
        return None
    
    def create_relation(
        self,
        from_fact_id: str,
        to_fact_id: str,
        relation_type: str = "RELATES_TO",
        confidence: int = 3,
        created_by: str = "manual"
    ) -> bool:
        """
        在图谱中创建关联
        
        Args:
            from_fact_id: 起始事实ID（支持短ID）
            to_fact_id: 目标事实ID（支持短ID）
            relation_type: 支持|矛盾|延伸|触发|因果
            confidence: 置信度 1-5
            created_by: auto|manual
        
        Returns:
            是否成功
        """
        # 解析短ID
        full_from_id = self.resolve_short_id(from_fact_id)
        full_to_id = self.resolve_short_id(to_fact_id)
        
        if not full_from_id or not full_to_id:
            return False
        
        driver = get_neo4j()
        timestamp = datetime.now().isoformat()
        
        with driver.session() as session:
            result = session.run(f"""
                MATCH (a:Fact {{fact_id: $from_id}}), (b:Fact {{fact_id: $to_id}})
                CREATE (a)-[r:{relation_type} {{
                    confidence: $confidence,
                    created_by: $created_by,
                    created_at: $timestamp
                }}]->(b)
                RETURN r
            """, from_id=full_from_id, to_id=full_to_id,
                confidence=confidence, created_by=created_by, timestamp=timestamp)
            
            return result.single() is not None
    
    def get_fact(self, fact_id: str) -> Optional[Dict]:
        """根据 ID 获取单条事实"""
        conn = get_sqlite()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM facts WHERE fact_id = ?", (fact_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            columns = ["fact_id", "summary", "content_type", "emotion_tag",
                      "context", "source_type", "source_url", "timestamp"]
            return dict(zip(columns, row))
        return None
    
    def list_facts(self, limit: int = 20, offset: int = 0) -> List[Dict]:
        """列出最近的事实"""
        conn = get_sqlite()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM facts 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = cursor.fetchall()
        conn.close()
        
        columns = ["fact_id", "summary", "content_type", "emotion_tag",
                  "context", "source_type", "source_url", "timestamp"]
        return [dict(zip(columns, row)) for row in rows]
    
    def stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        # SQLite 统计
        conn = get_sqlite()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM facts")
        fact_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT content_type, COUNT(*) 
            FROM facts 
            GROUP BY content_type
        """)
        type_counts = dict(cursor.fetchall())
        conn.close()
        
        # Neo4j 统计
        driver = get_neo4j()
        with driver.session() as session:
            result = session.run("MATCH (n:Fact) RETURN COUNT(n) AS count")
            node_count = result.single()["count"]
            
            result = session.run("MATCH ()-[r]->() RETURN COUNT(r) AS count")
            edge_count = result.single()["count"]
        
        return {
            "total_facts": fact_count,
            "by_type": type_counts,
            "graph_nodes": node_count,
            "graph_edges": edge_count
        }
    
    def find_similar(self, fact_id: str, top_k: int = 5) -> List[Dict]:
        """找到与指定事实相似的其他事实（用于关联推荐）"""
        fact = self.get_fact(fact_id)
        if not fact:
            return []
        
        results = self._query_qdrant(fact["summary"], top_k + 1, 0.5)
        # 排除自己
        return [r for r in results if r["fact_id"] != fact_id][:top_k]
    
    def delete(self, fact_id: str) -> bool:
        """
        删除事实 - 三库同步删除
        
        Args:
            fact_id: 事实ID（支持完整ID或前8位短ID）
        
        Returns:
            是否成功删除
        """
        # 支持短ID查找
        if len(fact_id) < 36:
            full_id = self._resolve_short_id(fact_id)
            if not full_id:
                return False
            fact_id = full_id
        
        try:
            # 1. 删除 Qdrant
            self._delete_qdrant(fact_id)
            
            # 2. 删除 Neo4j（节点及其所有关联边）
            self._delete_neo4j(fact_id)
            
            # 3. 删除 SQLite
            self._delete_sqlite(fact_id)
            
            return True
        except Exception as e:
            print(f"删除失败: {e}")
            return False
    
    def _resolve_short_id(self, short_id: str) -> Optional[str]:
        """根据短ID找到完整ID"""
        conn = get_sqlite()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT fact_id FROM facts WHERE fact_id LIKE ?",
            (f"{short_id}%",)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    
    def _delete_qdrant(self, fact_id: str):
        """从 Qdrant 删除"""
        from qdrant_client.models import PointIdsList
        client = get_qdrant()
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=PointIdsList(points=[fact_id])
        )
    
    def _delete_neo4j(self, fact_id: str):
        """从 Neo4j 删除节点及其所有关联边"""
        driver = get_neo4j()
        with driver.session() as session:
            # DETACH DELETE 会同时删除节点和所有连接的边
            session.run("""
                MATCH (f:Fact {fact_id: $fact_id})
                DETACH DELETE f
            """, fact_id=fact_id)
    
    def _delete_sqlite(self, fact_id: str):
        """从 SQLite 删除"""
        conn = get_sqlite()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM facts WHERE fact_id = ?", (fact_id,))
        # 同时删除关联记录（如果有）
        cursor.execute("DELETE FROM associations WHERE from_fact_id = ? OR to_fact_id = ?", 
                      (fact_id, fact_id))
        conn.commit()
        conn.close()
    
    def delete_batch(self, fact_ids: List[str]) -> int:
        """批量删除，返回成功删除的数量"""
        deleted = 0
        for fid in fact_ids:
            if self.delete(fid):
                deleted += 1
        return deleted


# CLI 入口
if __name__ == "__main__":
    import sys
    
    cogmate = CogmateAgent()
    
    if len(sys.argv) < 2:
        print("Usage: python brain_core.py <command> [args]")
        print("Commands:")
        print("  store <content> [--type TYPE] [--emotion EMOTION]")
        print("  query <text>")
        print("  stats")
        print("  list [limit]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "store":
        content = sys.argv[2] if len(sys.argv) > 2 else input("Content: ")
        fact_id = cogmate.store(content)
        print(f"✅ 已存储: {fact_id[:8]}...")
    
    elif cmd == "query":
        query_text = sys.argv[2] if len(sys.argv) > 2 else input("Query: ")
        results = cogmate.query(query_text)
        print(f"找到 {results['total']} 条结果:")
        for r in results["vector_results"]:
            print(f"  [{r['score']:.2f}] {r['summary'][:50]}...")
    
    elif cmd == "stats":
        stats = cogmate.stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    elif cmd == "list":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        facts = cogmate.list_facts(limit)
        for f in facts:
            print(f"[{f['content_type']}] {f['summary'][:60]}...")
