#!/usr/bin/env python3
"""
Abstraction Layer Module
========================
抽象层管理：从事实簇中提炼规律

功能：
    - 主题簇检测
    - 抽象草稿生成
    - 用户确认流程
    - 溯源链管理
"""

import uuid
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

# Centralized configuration
from config import get_neo4j, get_sqlite, setup_logging

logger = setup_logging("abstraction")

# 触发阈值
MIN_CLUSTER_SIZE = 8


def detect_clusters() -> List[Dict]:
    """
    检测图谱中的主题簇
    返回: [{'nodes': [...], 'size': N, 'theme': '...'}]
    """
    driver = get_neo4j()
    
    with driver.session() as session:
        # 获取所有节点
        nodes_result = session.run('''
            MATCH (f:Fact) 
            RETURN f.fact_id as id, f.summary as summary, f.content_type as type
        ''')
        nodes = {r['id']: {'summary': r['summary'], 'type': r['type']} for r in nodes_result}
        
        # 获取所有边
        edges_result = session.run('MATCH (a:Fact)-[r]->(b:Fact) RETURN a.fact_id as from_id, b.fact_id as to_id')
        
        # 构建无向邻接表
        adj = defaultdict(set)
        for r in edges_result:
            adj[r['from_id']].add(r['to_id'])
            adj[r['to_id']].add(r['from_id'])
    
    driver.close()
    
    # BFS 找连通分量
    visited = set()
    clusters = []
    
    for node_id in nodes:
        if node_id in visited:
            continue
        cluster_ids = []
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            cluster_ids.append(current)
            for neighbor in adj[current]:
                if neighbor not in visited:
                    queue.append(neighbor)
        
        cluster_nodes = [{'id': nid, **nodes[nid]} for nid in cluster_ids]
        clusters.append({
            'nodes': cluster_nodes,
            'size': len(cluster_nodes),
            'node_ids': cluster_ids
        })
    
    # 按大小排序
    clusters.sort(key=lambda x: x['size'], reverse=True)
    return clusters


def get_qualifying_clusters() -> List[Dict]:
    """获取符合抽象层触发条件的簇 (≥ MIN_CLUSTER_SIZE)"""
    clusters = detect_clusters()
    return [c for c in clusters if c['size'] >= MIN_CLUSTER_SIZE]


def infer_cluster_theme(cluster: Dict) -> str:
    """根据簇内容推断主题名称"""
    nodes = cluster['nodes']
    types = [n['type'] for n in nodes]
    summaries = [n['summary'] or '' for n in nodes]
    
    # 简单关键词提取
    all_text = ' '.join(summaries)
    
    # 基于内容的主题推断
    if 'Max' in all_text and ('迷茫' in all_text or '决策' in all_text or '副业' in all_text):
        return "Max个人认知与决策"
    elif 'AI' in all_text or 'LLM' in all_text or '编程' in all_text:
        return "AI产业影响与技术趋势"
    elif '伊朗' in all_text or '战争' in all_text or '黄金' in all_text:
        return "地缘冲突与避险资产"
    elif '石油' in all_text or '原油' in all_text:
        return "能源与宏观经济"
    elif '消费' in all_text:
        return "消费主义与价值观"
    else:
        return f"主题簇({cluster['size']}节点)"


def get_existing_abstracts() -> List[str]:
    """获取已存在的抽象层主题"""
    conn = get_sqlite()
    cursor = conn.cursor()
    cursor.execute("SELECT cluster_theme FROM abstracts WHERE status != 'archived'")
    themes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return themes


def create_draft_abstract(cluster: Dict, theme: str) -> str:
    """
    创建抽象层草稿
    返回: abstract_id
    """
    abstract_id = str(uuid.uuid4())
    node_ids = cluster['node_ids']
    
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO abstracts (
            abstract_id, name, description, cluster_theme, 
            source_fact_ids, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)
    ''', (
        abstract_id,
        theme,
        f"[待用户确认] 基于 {len(node_ids)} 个事实提炼的规律草稿",
        theme,
        json.dumps(node_ids),
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()
    
    return abstract_id


def confirm_abstract(abstract_id: str, description: str) -> bool:
    """用户确认抽象层记录"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE abstracts 
        SET status = 'confirmed', 
            description = ?,
            confirmed_at = ?,
            updated_at = ?
        WHERE abstract_id = ?
    ''', (
        description,
        datetime.now().isoformat(),
        datetime.now().isoformat(),
        abstract_id
    ))
    
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success


def list_abstracts(status: Optional[str] = None) -> List[Dict]:
    """列出抽象层记录"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    if status:
        cursor.execute('''
            SELECT abstract_id, name, description, cluster_theme, 
                   source_fact_ids, status, created_at, confirmed_at
            FROM abstracts WHERE status = ?
        ''', (status,))
    else:
        cursor.execute('''
            SELECT abstract_id, name, description, cluster_theme, 
                   source_fact_ids, status, created_at, confirmed_at
            FROM abstracts
        ''')
    
    results = []
    for row in cursor.fetchall():
        results.append({
            'abstract_id': row[0],
            'name': row[1],
            'description': row[2],
            'cluster_theme': row[3],
            'source_fact_ids': json.loads(row[4]) if row[4] else [],
            'status': row[5],
            'created_at': row[6],
            'confirmed_at': row[7]
        })
    
    conn.close()
    return results


def add_counter_example(abstract_id: str, fact_id: str) -> bool:
    """添加反例"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('SELECT counter_example_ids FROM abstracts WHERE abstract_id = ?', (abstract_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    
    counter_examples = json.loads(row[0]) if row[0] else []
    if fact_id not in counter_examples:
        counter_examples.append(fact_id)
    
    cursor.execute('''
        UPDATE abstracts SET counter_example_ids = ?, updated_at = ?
        WHERE abstract_id = ?
    ''', (json.dumps(counter_examples), datetime.now().isoformat(), abstract_id))
    
    conn.commit()
    conn.close()
    return True


if __name__ == "__main__":
    # 测试
    print("🔍 检测主题簇...")
    clusters = detect_clusters()
    print(f"   总簇数: {len(clusters)}")
    
    qualifying = get_qualifying_clusters()
    print(f"   符合条件: {len(qualifying)}")
    
    for c in qualifying:
        theme = infer_cluster_theme(c)
        print(f"   - {theme}: {c['size']} 节点")
