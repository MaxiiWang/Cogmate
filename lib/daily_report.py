#!/usr/bin/env python3
"""
Daily Report Module
===================
每日晚报 + 抽象层巡检

功能：
    - /today 每日晚报（21:00）
    - 抽象层巡检（04:00 扫描，07:00 推送）
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from collections import Counter

# Centralized configuration
from config import get_neo4j, get_sqlite, get_qdrant, get_embedder, setup_logging, COLLECTION_NAME

logger = setup_logging("daily_report")


def get_today_facts() -> List[Dict]:
    """获取今日新增的事实"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_sqlite()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT fact_id, summary, content_type, emotion_tag, context, created_at
        FROM facts 
        WHERE date(created_at) = date(?)
        ORDER BY created_at DESC
    ''', (today,))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            'fact_id': row[0],
            'content': row[1],
            'content_type': row[2],
            'emotion': row[3],
            'context': row[4],
            'created_at': row[5]
        })
    
    conn.close()
    return results


def get_today_relations() -> List[Dict]:
    """获取今日新增的关联"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    driver = get_neo4j()
    relations = []
    
    with driver.session() as session:
        result = session.run('''
            MATCH (a:Fact)-[r]->(b:Fact)
            WHERE r.created_at STARTS WITH $today
            RETURN a.fact_id as from_id, b.fact_id as to_id, 
                   type(r) as rel_type, r.confidence as confidence
        ''', today=today)
        
        for record in result:
            relations.append({
                'from_id': record['from_id'],
                'to_id': record['to_id'],
                'rel_type': record['rel_type'],
                'confidence': record['confidence']
            })
    
    return relations


def get_graph_stats() -> Dict:
    """获取图谱统计"""
    driver = get_neo4j()
    
    with driver.session() as session:
        nodes = session.run('MATCH (n:Fact) RETURN count(n) as count').single()['count']
        edges = session.run('MATCH ()-[r]->() RETURN count(r) as count').single()['count']
        
        # 今日新增
        today = datetime.now().strftime("%Y-%m-%d")
        today_nodes = session.run(
            'MATCH (n:Fact) WHERE n.timestamp STARTS WITH $today RETURN count(n) as count',
            today=today
        ).single()['count']
    
    return {
        'total_nodes': nodes,
        'total_edges': edges,
        'today_nodes': today_nodes
    }


def get_high_confidence_relations() -> List[Dict]:
    """获取今日高置信度关联"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    driver = get_neo4j()
    relations = []
    
    with driver.session() as session:
        result = session.run('''
            MATCH (a:Fact)-[r]->(b:Fact)
            WHERE r.created_at STARTS WITH $today AND r.confidence >= 4
            RETURN a.summary as from_summary, b.summary as to_summary,
                   type(r) as rel_type, r.confidence as confidence
            LIMIT 3
        ''', today=today)
        
        for record in result:
            relations.append({
                'from_summary': record['from_summary'][:30] if record['from_summary'] else '',
                'to_summary': record['to_summary'][:30] if record['to_summary'] else '',
                'rel_type': record['rel_type'],
                'confidence': record['confidence']
            })
    
    return relations


def get_contradictions() -> List[Dict]:
    """获取今日发现的矛盾"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    driver = get_neo4j()
    contradictions = []
    
    with driver.session() as session:
        result = session.run('''
            MATCH (a:Fact)-[r:矛盾]->(b:Fact)
            WHERE r.created_at STARTS WITH $today
            RETURN a.summary as from_summary, b.summary as to_summary,
                   r.confidence as confidence
        ''', today=today)
        
        for record in result:
            contradictions.append({
                'from_summary': record['from_summary'][:40] if record['from_summary'] else '',
                'to_summary': record['to_summary'][:40] if record['to_summary'] else '',
                'confidence': record['confidence']
            })
    
    return contradictions


def detect_daily_tensions() -> List[Dict]:
    """
    检测今日新增内容与图谱存量之间的张力
    通过向量相似度找到相关旧记录，然后用LLM判断是否存在逻辑张力
    """
    from config import get_qdrant, get_embedder
    
    today_facts = get_today_facts()
    if not today_facts:
        return []
    
    tensions = []
    qdrant = get_qdrant()
    embedder = get_embedder()
    
    # 获取今日所有fact_id用于排除
    today_ids = {f['fact_id'] for f in today_facts}
    
    for fact in today_facts:
        # 只检查观点类型的内容
        if fact['content_type'] not in ['观点', '决策']:
            continue
        
        # 向量搜索找相关旧记录
        query_vector = embedder.encode(fact['content']).tolist()
        
        try:
            response = qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=5,
                score_threshold=0.55
            )
            results = response.points if hasattr(response, 'points') else []
            
            # 过滤掉今日新增的
            related_old = [r for r in results if r.id not in today_ids]
            
            if related_old:
                # 找相似度最高的旧记录，检查是否有张力
                top_old = related_old[0]
                old_content = top_old.payload.get('summary', '') or top_old.payload.get('content', '')
                
                # 简单的张力检测：如果内容相似但不完全相同，可能存在微妙差异
                # 更精确的检测需要LLM，这里先用规则
                if 0.55 < top_old.score < 0.90:  # 相似但不完全相同
                    tensions.append({
                        'new_fact': fact,
                        'old_fact_id': top_old.id,
                        'old_content': old_content,
                        'similarity': top_old.score
                    })
        except Exception as e:
            logger.error(f"张力检测错误: {e}")
            continue
    
    return tensions[:2]  # 最多返回2条


def generate_challenge_question(new_content: str, old_content: str) -> str:
    """使用LLM生成挑战性问题"""
    try:
        from llm_answer import get_api_key
        import anthropic
        
        api_key = get_api_key()
        if not api_key:
            return "这两个观点之间是否存在需要调和的差异？"
        
        client = anthropic.Anthropic(api_key=api_key)
        
        prompt = f"""作为一个批判性思考助手，分析以下两个观点之间的潜在张力：

新观点：{new_content[:300]}

旧观点：{old_content[:300]}

请用一句话提出一个挑战性问题，帮助用户思考这两个观点是否存在矛盾、需要修正、或可以整合。
问题要具体、有洞察力，不要泛泛而谈。只输出问题本身，不要其他内容。"""

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"生成挑战问题失败: {e}")
        return "这两个观点之间是否需要进一步调和？"


def generate_daily_report() -> str:
    """生成每日晚报"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 获取数据
    facts = get_today_facts()
    relations = get_today_relations()
    stats = get_graph_stats()
    high_conf = get_high_confidence_relations()
    contradictions = get_contradictions()
    
    # 统计类型分布
    type_counts = Counter(f['content_type'] for f in facts)
    
    # 构建报告
    lines = [
        f"🌙 **今日知识晚报 · {today}**",
        "",
        f"📥 今日新增：**{len(facts)}** 条记录"
    ]
    
    if type_counts:
        type_str = " | ".join([f"{t} {c}条" for t, c in type_counts.items()])
        lines.append(f"   {type_str}")
    
    lines.append("")
    
    # 高频主题（简化：取最近几条的context关键词）
    contexts = [f['context'] for f in facts if f['context']]
    if contexts:
        lines.append(f"🔑 今日情境：{contexts[0][:30]}...")
    
    lines.append("")
    
    # 值得关注
    lines.append("💡 **值得关注**：")
    
    if high_conf:
        for rel in high_conf[:2]:
            lines.append(f"   · [{rel['rel_type']}] {rel['from_summary']}... → {rel['to_summary']}...")
    else:
        lines.append("   · 今日无高置信度新关联")
    
    if contradictions:
        lines.append(f"   · ⚠️ 发现矛盾：{contradictions[0]['from_summary']}...")
    
    lines.append("")
    
    # 图谱变化
    lines.append(f"🕸️ 图谱状态：{stats['total_nodes']} 节点 | {stats['total_edges']} 边")
    if stats['today_nodes'] > 0 or len(relations) > 0:
        lines.append(f"   今日变化：+{stats['today_nodes']} 节点，+{len(relations)} 条边")
    
    lines.append("")
    
    # 今日挑战（增量 vs 存量张力检测）
    tensions = detect_daily_tensions()
    if tensions:
        lines.append("⚔️ **今日挑战**（增量 vs 存量张力检测）：")
        for i, t in enumerate(tensions, 1):
            new_preview = t['new_fact']['content'][:50]
            old_preview = t['old_content'][:50]
            challenge_q = generate_challenge_question(t['new_fact']['content'], t['old_content'])
            
            lines.append(f"")
            lines.append(f"   **张力点 {i}**：")
            lines.append(f"   新增：{new_preview}...")
            lines.append(f"   已有：{old_preview}...")
            lines.append(f"   💬 {challenge_q}")
        
        lines.append("")
        lines.append("   回复回应挑战 → 更新图谱或保留矛盾")
        lines.append("   回复「跳过」→ 保留张力待后续处理")
    else:
        lines.append("⚔️ 今日挑战：无明显张力检测到 ✅")
    
    lines.append("")
    lines.append("有什么想补充记录的吗？")
    
    return "\n".join(lines)


def check_abstraction_candidates() -> List[Dict]:
    """检查是否有新的抽象层候选"""
    from abstraction import get_qualifying_clusters, infer_cluster_theme, get_existing_abstracts
    
    qualifying = get_qualifying_clusters()
    existing = get_existing_abstracts()
    
    new_candidates = []
    for cluster in qualifying:
        theme = infer_cluster_theme(cluster)
        if theme not in existing:
            new_candidates.append({
                'theme': theme,
                'size': cluster['size'],
                'node_ids': cluster['node_ids']
            })
    
    return new_candidates


def generate_morning_report() -> str:
    """生成早间整理报告（07:00推送）"""
    from abstraction import list_abstracts
    
    lines = [
        f"🌅 **夜间整理报告 · {datetime.now().strftime('%Y-%m-%d')}**",
        ""
    ]
    
    # 图谱状态
    stats = get_graph_stats()
    lines.append(f"📊 图谱状态: {stats['total_nodes']} 节点 | {stats['total_edges']} 边")
    
    # 检查抽象层候选
    try:
        candidates = check_abstraction_candidates()
        if candidates:
            lines.append("")
            lines.append(f"📐 **发现 {len(candidates)} 个可提炼的主题簇**：")
            for i, c in enumerate(candidates, 1):
                lines.append(f"   {i}. {c['theme']} ({c['size']} 节点)")
            lines.append("")
            lines.append("回复「提炼 1」为第 1 个簇生成抽象草稿")
    except Exception as e:
        lines.append(f"   抽象层检查异常: {e}")
    
    # 草稿待确认
    drafts = list_abstracts('draft')
    if drafts:
        lines.append("")
        lines.append(f"📝 **{len(drafts)} 个抽象草稿待确认**：")
        for d in drafts:
            lines.append(f"   · [{d['abstract_id'][:8]}] {d['name']}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("===== 每日晚报预览 =====")
    print(generate_daily_report())
    print()
    print("===== 早间报告预览 =====")
    print(generate_morning_report())
