#!/usr/bin/env python3
"""
Weekly Challenge Module
=======================
每周深度挑战（Stress Test）

功能：
    - 识别值得验证的核心判断
    - 搜索外部反对意见
    - 生成挑战报告
"""

import os
import json
import sqlite3
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import Counter

from config import get_neo4j, get_sqlite, get_qdrant, get_embedder, setup_logging

logger = setup_logging("weekly_challenge")


def get_core_beliefs(limit: int = 10) -> List[Dict]:
    """
    获取核心判断/观点（高权重节点）
    标准：
    - 类型为「观点」或「决策」
    - 在图谱中有多条出边（被引用多次）
    - 或被抽象层引用
    """
    conn = get_sqlite()
    cursor = conn.cursor()
    
    # 获取所有观点/决策类型的事实
    cursor.execute('''
        SELECT fact_id, summary, content_type, context, created_at
        FROM facts 
        WHERE content_type IN ('观点', '决策')
        ORDER BY created_at DESC
    ''')
    
    candidates = []
    for row in cursor.fetchall():
        candidates.append({
            'fact_id': row[0],
            'content': row[1],
            'content_type': row[2],
            'context': row[3],
            'created_at': row[4]
        })
    
    conn.close()
    
    # 计算每个节点的图谱权重（出边数量）
    driver = get_neo4j()
    weighted = []
    
    with driver.session() as session:
        for c in candidates:
            result = session.run('''
                MATCH (n:Fact {fact_id: $fid})-[r]->()
                RETURN count(r) as out_degree
            ''', fid=c['fact_id'])
            record = result.single()
            out_degree = record['out_degree'] if record else 0
            
            # 检查是否被抽象层引用
            in_abstract = session.run('''
                MATCH (a:Abstract)-[:DERIVES_FROM]->(n:Fact {fact_id: $fid})
                RETURN count(a) as abstract_count
            ''', fid=c['fact_id'])
            abstract_record = in_abstract.single()
            abstract_count = abstract_record['abstract_count'] if abstract_record else 0
            
            weight = out_degree + (abstract_count * 2)  # 被抽象层引用权重更高
            
            if weight > 0:  # 只选择有关联的
                c['weight'] = weight
                weighted.append(c)
    
    # 按权重排序，返回top
    weighted.sort(key=lambda x: x['weight'], reverse=True)
    return weighted[:limit]


def search_opposing_views(belief: str) -> List[Dict]:
    """
    使用Brave Search搜索反对意见
    """
    api_key = os.environ.get('BRAVE_API_KEY')
    if not api_key:
        return []
    
    # 构建搜索query：原观点 + 反对/质疑关键词
    # 提取核心关键词
    keywords = belief[:100]  # 取前100字符作为关键词
    query = f"{keywords} 反对意见 OR 质疑 OR 批评 OR 不同观点"
    
    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 3},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            results = []
            for r in data.get('web', {}).get('results', [])[:3]:
                results.append({
                    'title': r.get('title', ''),
                    'description': r.get('description', ''),
                    'url': r.get('url', '')
                })
            return results
    except Exception as e:
        logger.error(f"搜索反对意见失败: {e}")
    
    return []


def generate_stress_test_question(belief: str, opposing: List[Dict]) -> str:
    """使用LLM生成stress test问题"""
    try:
        from llm_answer import get_api_key
        import anthropic
        
        api_key = get_api_key()
        if not api_key:
            return "这个判断是否需要重新审视？"
        
        client = anthropic.Anthropic(api_key=api_key)
        
        opposing_text = ""
        if opposing:
            opposing_text = "\n".join([f"- {o['title']}: {o['description'][:100]}" for o in opposing[:2]])
        
        prompt = f"""作为一个批判性思考助手，针对以下核心判断生成一个深度挑战问题：

核心判断：{belief[:400]}

{f"外部反对/质疑声音：{opposing_text}" if opposing_text else "（未找到明确的外部反对意见）"}

请生成一个具有挑战性的问题，帮助用户重新审视这个判断：
- 如果有反对意见，问题应该直击反对观点的核心
- 如果没有反对意见，问题应该探索这个判断的边界条件或潜在盲点
- 问题要具体、有深度，能引发真正的思考

只输出问题本身，不要其他内容。"""

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"生成stress test问题失败: {e}")
        return "这个判断的边界条件是什么？在什么情况下它可能不成立？"


def generate_weekly_challenge_report(num_challenges: int = 3) -> str:
    """生成每周深度挑战报告"""
    
    # 获取核心判断
    core_beliefs = get_core_beliefs(limit=num_challenges * 2)
    
    if not core_beliefs:
        return "⚔️ **本周深度挑战**：暂无足够的核心判断可供测试"
    
    lines = [
        f"⚔️ **本周深度挑战（Stress Test）**",
        "",
        "识别值得验证的核心判断，主动搜索外部反对意见：",
        ""
    ]
    
    challenges_added = 0
    for belief in core_beliefs:
        if challenges_added >= num_challenges:
            break
        
        # 搜索反对意见
        opposing = search_opposing_views(belief['content'])
        
        # 生成挑战问题
        challenge_q = generate_stress_test_question(belief['content'], opposing)
        
        challenges_added += 1
        lines.append(f"🎯 **挑战 {challenges_added}**：")
        lines.append(f"   核心判断：{belief['content'][:80]}...")
        lines.append(f"   来源：`{belief['fact_id'][:8]}` ({belief['created_at'][:10]})")
        
        if opposing:
            lines.append(f"   外部声音：")
            for o in opposing[:1]:
                lines.append(f"      · {o['title'][:40]}...")
        else:
            lines.append(f"   外部声音：未找到明确反对意见")
        
        lines.append(f"   💬 {challenge_q}")
        lines.append("")
    
    lines.append("回复编号回应挑战 → 修正观点 / 保留并标记存疑 / 强化原判断")
    lines.append("回复「跳过」→ 本周不处理")
    
    return "\n".join(lines)


def get_week_stats() -> Dict:
    """获取本周图谱统计"""
    driver = get_neo4j()
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    with driver.session() as session:
        total_nodes = session.run('MATCH (n:Fact) RETURN count(n) as count').single()['count']
        total_edges = session.run('MATCH ()-[r]->() RETURN count(r) as count').single()['count']
        
        week_nodes = session.run(
            'MATCH (n:Fact) WHERE n.timestamp >= $week_ago RETURN count(n) as count',
            week_ago=week_ago
        ).single()['count']
        
        week_edges = session.run(
            'MATCH ()-[r]->() WHERE r.created_at >= $week_ago RETURN count(r) as count',
            week_ago=week_ago
        ).single()['count']
        
        # 孤立节点
        isolated = session.run('''
            MATCH (n:Fact) 
            WHERE NOT (n)-[]-() 
            RETURN count(n) as count
        ''').single()['count']
    
    return {
        'total_nodes': total_nodes,
        'total_edges': total_edges,
        'week_nodes': week_nodes,
        'week_edges': week_edges,
        'isolated_ratio': isolated / total_nodes if total_nodes > 0 else 0
    }


def generate_weekly_report() -> str:
    """生成完整的周报（含深度挑战）"""
    today = datetime.now()
    week_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    week_end = today.strftime("%Y-%m-%d")
    
    stats = get_week_stats()
    
    lines = [
        f"📊 **本周知识地图报告 · {week_start} ~ {week_end}**",
        "",
        "🕸️ **图谱状态**",
        f"   总节点：{stats['total_nodes']} | 本周新增：+{stats['week_nodes']}",
        f"   总关联：{stats['total_edges']} | 本周新增：+{stats['week_edges']}",
        f"   孤立节点占比：{stats['isolated_ratio']*100:.1f}%（目标 < 20%）",
        ""
    ]
    
    # 添加深度挑战
    challenge_report = generate_weekly_challenge_report(num_challenges=2)
    lines.append(challenge_report)
    
    # 健康度评估
    health = "🟢 良好" if stats['isolated_ratio'] < 0.2 else "🟡 待改善" if stats['isolated_ratio'] < 0.4 else "🔴 需关注"
    lines.append("")
    lines.append(f"本周图谱健康：{health}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("===== 每周深度挑战报告预览 =====")
    print(generate_weekly_report())
