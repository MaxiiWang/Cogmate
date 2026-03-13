"""
隐私控制模块 - 管理模拟世界的公开/私有边界
"""
import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime

# Centralized configuration
from config import get_sqlite as get_db, setup_logging

logger = setup_logging("privacy")


def set_fact_private(fact_id: str, private: bool = True) -> bool:
    """设置单条 fact 的隐私状态"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE facts SET is_private = ?, updated_at = ? WHERE fact_id LIKE ?",
        (1 if private else 0, datetime.now().isoformat(), f"{fact_id}%")
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def set_abstract_private(abstract_id: str, private: bool = True, cascade: bool = True) -> Tuple[bool, List[str]]:
    """
    设置抽象层的隐私状态
    cascade=True 时同步私有化所有关联的下级 facts
    返回: (是否成功, 受影响的 fact_ids 列表)
    """
    conn = get_db()
    cur = conn.cursor()
    
    # 查找抽象层记录
    cur.execute(
        "SELECT abstract_id, source_fact_ids FROM abstracts WHERE abstract_id LIKE ?",
        (f"{abstract_id}%",)
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, []
    
    full_abstract_id, source_fact_ids = row
    affected_facts = []
    
    # 更新抽象层本身
    cur.execute(
        "UPDATE abstracts SET is_private = ?, updated_at = ? WHERE abstract_id = ?",
        (1 if private else 0, datetime.now().isoformat(), full_abstract_id)
    )
    
    # 级联更新关联 facts
    if cascade and source_fact_ids:
        # 支持 JSON 数组格式和逗号分隔格式
        import json
        try:
            fact_ids = json.loads(source_fact_ids) if source_fact_ids.startswith('[') else source_fact_ids.split(',')
            fact_ids = [fid.strip().strip('"') for fid in fact_ids if fid.strip()]
        except:
            fact_ids = [fid.strip() for fid in source_fact_ids.split(',') if fid.strip()]
        
        for fid in fact_ids:
            cur.execute(
                "UPDATE facts SET is_private = ?, updated_at = ? WHERE fact_id = ?",
                (1 if private else 0, datetime.now().isoformat(), fid)
            )
            if cur.rowcount > 0:
                affected_facts.append(fid)
    
    conn.commit()
    conn.close()
    return True, affected_facts


def get_privacy_status(entity_id: str) -> Optional[dict]:
    """查询实体的隐私状态"""
    conn = get_db()
    cur = conn.cursor()
    
    # 先查 facts
    cur.execute(
        "SELECT fact_id, summary, is_private FROM facts WHERE fact_id LIKE ?",
        (f"{entity_id}%",)
    )
    row = cur.fetchone()
    if row:
        conn.close()
        return {
            "type": "fact",
            "id": row[0],
            "summary": row[1][:50] + "..." if len(row[1]) > 50 else row[1],
            "is_private": bool(row[2])
        }
    
    # 再查 abstracts
    cur.execute(
        "SELECT abstract_id, name, is_private FROM abstracts WHERE abstract_id LIKE ?",
        (f"{entity_id}%",)
    )
    row = cur.fetchone()
    if row:
        conn.close()
        return {
            "type": "abstract",
            "id": row[0],
            "name": row[1],
            "is_private": bool(row[2])
        }
    
    conn.close()
    return None


def list_private_entities() -> dict:
    """列出所有私有实体"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT fact_id, summary FROM facts WHERE is_private = 1")
    private_facts = [{"id": r[0][:8], "summary": r[1][:40] + "..."} for r in cur.fetchall()]
    
    cur.execute("SELECT abstract_id, name FROM abstracts WHERE is_private = 1")
    private_abstracts = [{"id": r[0][:8], "name": r[1]} for r in cur.fetchall()]
    
    conn.close()
    return {
        "facts": private_facts,
        "abstracts": private_abstracts
    }


def filter_public_facts(fact_ids: List[str]) -> List[str]:
    """从 fact_id 列表中过滤出公开的"""
    if not fact_ids:
        return []
    conn = get_db()
    cur = conn.cursor()
    placeholders = ','.join(['?'] * len(fact_ids))
    cur.execute(
        f"SELECT fact_id FROM facts WHERE fact_id IN ({placeholders}) AND is_private = 0",
        fact_ids
    )
    result = [r[0] for r in cur.fetchall()]
    conn.close()
    return result


def get_public_facts_for_search(limit: int = 100) -> List[dict]:
    """获取所有公开 facts 用于搜索"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT fact_id, summary, content_type, timestamp 
        FROM facts 
        WHERE is_private = 0 
        ORDER BY timestamp DESC 
        LIMIT ?
    """, (limit,))
    result = [{
        "id": r[0],
        "summary": r[1],
        "type": r[2],
        "timestamp": r[3]
    } for r in cur.fetchall()]
    conn.close()
    return result


def get_privacy_stats() -> dict:
    """获取隐私统计"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM facts")
    total_facts = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM facts WHERE is_private = 1")
    private_facts = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM abstracts")
    total_abstracts = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM abstracts WHERE is_private = 1")
    private_abstracts = cur.fetchone()[0]
    
    conn.close()
    return {
        "facts": {"total": total_facts, "private": private_facts, "public": total_facts - private_facts},
        "abstracts": {"total": total_abstracts, "private": private_abstracts, "public": total_abstracts - private_abstracts}
    }
