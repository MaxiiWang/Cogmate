#!/usr/bin/env python3
"""
Temporal Review Module
======================
时态审查 - 检测即将过期或已过期的记录

功能：
    - 扫描所有带 valid_until 的记录
    - 检测即将过期（30天内）和已过期的记录
    - 生成审查报告
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

from config import get_sqlite, setup_logging

logger = setup_logging("temporal_review")


def get_expiring_facts(days_ahead: int = 30) -> List[Dict]:
    """获取即将在指定天数内过期的记录"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    future = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    cursor.execute("""
        SELECT fact_id, summary, content_type, valid_until, temporal_type, timestamp
        FROM facts
        WHERE valid_until IS NOT NULL
          AND valid_until >= ?
          AND valid_until <= ?
        ORDER BY valid_until ASC
    """, (today, future))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            "fact_id": row[0],
            "summary": row[1],
            "content_type": row[2],
            "valid_until": row[3],
            "temporal_type": row[4],
            "timestamp": row[5]
        })
    
    conn.close()
    return results


def get_expired_facts() -> List[Dict]:
    """获取已过期的记录"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("""
        SELECT fact_id, summary, content_type, valid_until, temporal_type, timestamp
        FROM facts
        WHERE valid_until IS NOT NULL
          AND valid_until < ?
        ORDER BY valid_until DESC
    """, (today,))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            "fact_id": row[0],
            "summary": row[1],
            "content_type": row[2],
            "valid_until": row[3],
            "temporal_type": row[4],
            "timestamp": row[5]
        })
    
    conn.close()
    return results


def get_time_bound_facts() -> List[Dict]:
    """获取所有时效性记录（用于审查）"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT fact_id, summary, content_type, valid_until, temporal_type, timestamp
        FROM facts
        WHERE temporal_type = 'time_bound' OR valid_until IS NOT NULL
        ORDER BY timestamp DESC
    """)
    
    results = []
    for row in cursor.fetchall():
        results.append({
            "fact_id": row[0],
            "summary": row[1],
            "content_type": row[2],
            "valid_until": row[3],
            "temporal_type": row[4],
            "timestamp": row[5]
        })
    
    conn.close()
    return results


def update_validity(fact_id: str, valid_until: str = None, temporal_type: str = None):
    """更新记录的有效期"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if valid_until is not None:
        updates.append("valid_until = ?")
        params.append(valid_until)
    
    if temporal_type is not None:
        updates.append("temporal_type = ?")
        params.append(temporal_type)
    
    if updates:
        params.append(fact_id)
        cursor.execute(f"""
            UPDATE facts SET {', '.join(updates)}
            WHERE fact_id = ?
        """, params)
        conn.commit()
    
    conn.close()


def generate_temporal_report() -> str:
    """生成时态审查报告"""
    expired = get_expired_facts()
    expiring = get_expiring_facts(days_ahead=30)
    
    lines = ["📅 **时态审查报告**\n"]
    
    # 已过期
    if expired:
        lines.append(f"⚠️ **已过期**: {len(expired)} 条\n")
        for f in expired[:5]:
            fid = f['fact_id'][:8]
            summary = f['summary'][:40] if f['summary'] else '无摘要'
            valid = f['valid_until']
            lines.append(f"   `{fid}` [{valid}] {summary}...")
        if len(expired) > 5:
            lines.append(f"   ...还有 {len(expired) - 5} 条")
        lines.append("")
    
    # 即将过期
    if expiring:
        lines.append(f"🔔 **30天内过期**: {len(expiring)} 条\n")
        for f in expiring[:5]:
            fid = f['fact_id'][:8]
            summary = f['summary'][:40] if f['summary'] else '无摘要'
            valid = f['valid_until']
            lines.append(f"   `{fid}` [{valid}] {summary}...")
        if len(expiring) > 5:
            lines.append(f"   ...还有 {len(expiring) - 5} 条")
        lines.append("")
    
    if not expired and not expiring:
        lines.append("✅ 无过期或即将过期的记录")
    
    lines.append("\n---")
    lines.append("回复 `审查 <fact_id>` 更新有效期")
    lines.append("回复 `延期 <fact_id> <新日期>` 延长有效期")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print(generate_temporal_report())
