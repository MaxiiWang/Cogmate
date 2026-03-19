#!/usr/bin/env python3
"""
Graph Health Monitor
====================
图谱健康度监控模块

功能：
    - 孤立节点检测
    - 平均度数计算
    - 矛盾关系统计
    - 健康度评估
    - 趋势追踪
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Centralized configuration
from config import get_neo4j, get_sqlite, setup_logging

logger = setup_logging("graph_health")

# 健康度阈值
THRESHOLDS = {
    'orphan_ratio_good': 0.10,      # < 10% 优秀
    'orphan_ratio_warn': 0.20,      # < 20% 正常，>= 20% 需关注
    'avg_degree_good': 3.0,         # >= 3.0 优秀
    'avg_degree_warn': 2.0,         # >= 2.0 正常，< 2.0 需关注
    'contradiction_ratio_warn': 0.10  # >= 10% 需关注
}


def get_graph_metrics(namespace: str = "default") -> Dict:
    """
    获取图谱健康度指标
    
    Args:
        namespace: 只统计指定 namespace 的节点，默认 "default"
    
    Returns:
        {
            'total_nodes': int,
            'total_edges': int,
            'orphan_count': int,
            'orphan_ratio': float,
            'avg_degree': float,
            'contradiction_count': int,
            'contradiction_ratio': float,
            'hub_nodes': list,  # 高连接度节点
            'timestamp': str,
            'namespace': str
        }
    """
    driver = get_neo4j()
    
    with driver.session() as session:
        # 基础统计（按 namespace 过滤）
        total_nodes = session.run(
            'MATCH (n:Fact) WHERE n.namespace = $ns RETURN count(n) as c',
            ns=namespace
        ).single()['c']
        total_edges = session.run(
            'MATCH (a:Fact)-[r]->(b:Fact) WHERE a.namespace = $ns AND b.namespace = $ns RETURN count(r) as c',
            ns=namespace
        ).single()['c']
        
        # 孤立节点（同 namespace 内无连接）
        orphan_count = session.run('''
            MATCH (n:Fact)
            WHERE n.namespace = $ns AND NOT (n)-[]-(:Fact {namespace: $ns})
            RETURN count(n) as c
        ''', ns=namespace).single()['c']
        
        # 矛盾关系
        contradiction_count = session.run('''
            MATCH (a:Fact)-[r:矛盾]->(b:Fact)
            WHERE a.namespace = $ns AND b.namespace = $ns
            RETURN count(r) as c
        ''', ns=namespace).single()['c']
        
        # Hub 节点（度数 >= 4）
        hub_result = session.run('''
            MATCH (n:Fact)
            WHERE n.namespace = $ns
            OPTIONAL MATCH (n)-[r]-(:Fact {namespace: $ns})
            WITH n, count(r) as degree
            WHERE degree >= 4
            RETURN n.fact_id as id, n.summary as summary, degree
            ORDER BY degree DESC
            LIMIT 5
        ''', ns=namespace)
        hub_nodes = [
            {'id': r['id'][:8], 'summary': r['summary'][:40] if r['summary'] else '', 'degree': r['degree']}
            for r in hub_result
        ]
        
        # 度数分布
        degree_result = session.run('''
            MATCH (n:Fact)
            WHERE n.namespace = $ns
            OPTIONAL MATCH (n)-[r]-(:Fact {namespace: $ns})
            WITH n, count(r) as degree
            RETURN degree, count(*) as cnt
            ORDER BY degree
        ''', ns=namespace)
        degree_distribution = {r['degree']: r['cnt'] for r in degree_result}
    
    # 不要 close driver，它是共享连接池
    
    # 计算比率
    orphan_ratio = orphan_count / total_nodes if total_nodes > 0 else 0
    avg_degree = (total_edges * 2) / total_nodes if total_nodes > 0 else 0
    contradiction_ratio = contradiction_count / total_edges if total_edges > 0 else 0
    
    return {
        'total_nodes': total_nodes,
        'total_edges': total_edges,
        'orphan_count': orphan_count,
        'orphan_ratio': orphan_ratio,
        'avg_degree': avg_degree,
        'contradiction_count': contradiction_count,
        'contradiction_ratio': contradiction_ratio,
        'hub_nodes': hub_nodes,
        'degree_distribution': degree_distribution,
        'timestamp': datetime.now().isoformat(),
        'namespace': namespace
    }


def evaluate_health(metrics: Dict) -> Dict:
    """
    评估图谱健康度
    
    Returns:
        {
            'overall': 'good' | 'warning' | 'critical',
            'overall_icon': str,
            'details': [
                {'metric': str, 'status': str, 'value': str, 'target': str}
            ]
        }
    """
    details = []
    issues = 0
    critical = 0
    
    # 1. 孤立节点比率
    orphan_ratio = metrics['orphan_ratio']
    if orphan_ratio < THRESHOLDS['orphan_ratio_good']:
        status = 'good'
    elif orphan_ratio < THRESHOLDS['orphan_ratio_warn']:
        status = 'warning'
        issues += 1
    else:
        status = 'critical'
        critical += 1
    
    details.append({
        'metric': '孤立节点占比',
        'status': status,
        'value': f"{orphan_ratio:.1%}",
        'target': f"< {THRESHOLDS['orphan_ratio_warn']:.0%}",
        'icon': '🟢' if status == 'good' else ('🟡' if status == 'warning' else '🔴')
    })
    
    # 2. 平均度数
    avg_degree = metrics['avg_degree']
    if avg_degree >= THRESHOLDS['avg_degree_good']:
        status = 'good'
    elif avg_degree >= THRESHOLDS['avg_degree_warn']:
        status = 'warning'
        issues += 1
    else:
        status = 'critical'
        critical += 1
    
    details.append({
        'metric': '平均节点度数',
        'status': status,
        'value': f"{avg_degree:.2f}",
        'target': f"> {THRESHOLDS['avg_degree_warn']:.1f}",
        'icon': '🟢' if status == 'good' else ('🟡' if status == 'warning' else '🔴')
    })
    
    # 3. 矛盾关系比率
    contradiction_ratio = metrics['contradiction_ratio']
    if contradiction_ratio < THRESHOLDS['contradiction_ratio_warn']:
        status = 'good'
    else:
        status = 'warning'
        issues += 1
    
    details.append({
        'metric': '矛盾关系占比',
        'status': status,
        'value': f"{contradiction_ratio:.1%}",
        'target': f"< {THRESHOLDS['contradiction_ratio_warn']:.0%}",
        'icon': '🟢' if status == 'good' else '🟡'
    })
    
    # 总体评估
    if critical > 0:
        overall = 'critical'
        overall_icon = '🔴'
    elif issues > 0:
        overall = 'warning'
        overall_icon = '🟡'
    else:
        overall = 'good'
        overall_icon = '🟢'
    
    return {
        'overall': overall,
        'overall_icon': overall_icon,
        'details': details,
        'issues': issues,
        'critical': critical
    }


def save_health_snapshot(metrics: Dict) -> None:
    """保存健康度快照到 system_state"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO system_state (key, value, updated_at)
        VALUES ('health_snapshot', ?, ?)
    ''', (json.dumps(metrics), datetime.now().isoformat()))
    
    conn.commit()
    conn.close()


def get_health_history(days: int = 7) -> List[Dict]:
    """获取历史健康度数据（如果有）"""
    # TODO: 实现历史记录存储
    return []


def generate_health_report(verbose: bool = False, namespace: str = "default") -> str:
    """
    生成图谱健康度报告
    
    Args:
        verbose: 是否包含详细信息
        namespace: 只统计指定 namespace，默认 "default"
    
    Returns:
        格式化的报告文本
    """
    metrics = get_graph_metrics(namespace=namespace)
    health = evaluate_health(metrics)
    
    ns_label = f" [{namespace}]" if namespace != "default" else ""
    lines = [
        f"🕸️ **图谱健康度报告**{ns_label}",
        f"",
        f"📊 **基础统计**",
        f"   节点总数: {metrics['total_nodes']}",
        f"   边总数: {metrics['total_edges']}",
        f"   孤立节点: {metrics['orphan_count']}",
        f"   矛盾关系: {metrics['contradiction_count']}",
        f"",
        f"📈 **健康度指标**",
    ]
    
    for d in health['details']:
        lines.append(f"   {d['icon']} {d['metric']}: {d['value']} (目标 {d['target']})")
    
    lines.append(f"")
    lines.append(f"🏥 **整体健康度**: {health['overall_icon']} {health['overall'].upper()}")
    
    # Hub 节点
    if metrics['hub_nodes']:
        lines.append(f"")
        lines.append(f"🔗 **枢纽节点** (度数≥4):")
        for hub in metrics['hub_nodes'][:3]:
            lines.append(f"   [{hub['id']}] 度数:{hub['degree']} | {hub['summary']}...")
    
    # 详细度数分布
    if verbose and metrics.get('degree_distribution'):
        lines.append(f"")
        lines.append(f"📊 **度数分布**:")
        dist = metrics['degree_distribution']
        for degree in sorted(dist.keys()):
            bar = '█' * min(dist[degree], 20)
            lines.append(f"   度数{degree}: {bar} ({dist[degree]})")
    
    # 保存快照
    save_health_snapshot(metrics)
    
    return "\n".join(lines)


def get_improvement_suggestions(metrics: Dict) -> List[str]:
    """根据健康度指标给出改进建议"""
    suggestions = []
    
    if metrics['orphan_ratio'] >= THRESHOLDS['orphan_ratio_warn']:
        suggestions.append(f"⚠️ 孤立节点占比 {metrics['orphan_ratio']:.1%}，建议运行 `/connect` 发现关联")
    
    if metrics['avg_degree'] < THRESHOLDS['avg_degree_warn']:
        suggestions.append(f"⚠️ 平均度数 {metrics['avg_degree']:.2f} 偏低，建议增加知识关联")
    
    if metrics['contradiction_count'] > 0:
        suggestions.append(f"💡 存在 {metrics['contradiction_count']} 个矛盾关系，运行 `/conflict` 查看详情")
    
    if not suggestions:
        suggestions.append("✅ 图谱健康度良好，继续保持！")
    
    return suggestions


if __name__ == "__main__":
    print(generate_health_report(verbose=True))
