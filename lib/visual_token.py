#!/usr/bin/env python3
"""
Visual Token Manager
====================
可视化访问 Token 管理模块

功能：
    - Token 生成（带时效）
    - Token 验证
    - Token 撤销
    - 访问记录
"""

import uuid
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from pathlib import Path

# Centralized configuration
from config import get_sqlite, VISUAL_PUBLIC_URL, setup_logging

logger = setup_logging("visual_token")

# 默认有效期
DEFAULT_DURATION = timedelta(days=7)

# 默认问答次数限制
DEFAULT_QA_LIMIT = 20

# 时间单位映射
DURATION_MAP = {
    'h': 'hours',
    'd': 'days',
    'w': 'weeks',
    'm': 'minutes'
}


def parse_duration(duration_str: str) -> timedelta:
    """
    解析时间字符串
    
    Examples:
        '1h' -> 1 hour
        '24h' -> 24 hours
        '7d' -> 7 days
        '1w' -> 1 week
    """
    if not duration_str:
        return DEFAULT_DURATION
    
    duration_str = duration_str.lower().strip()
    
    # 提取数字和单位
    num = ''
    unit = ''
    for c in duration_str:
        if c.isdigit():
            num += c
        else:
            unit += c
    
    if not num:
        num = '1'
    
    num = int(num)
    unit = unit.strip() or 'd'
    
    if unit in DURATION_MAP:
        return timedelta(**{DURATION_MAP[unit]: num})
    elif unit == 'hour' or unit == 'hours':
        return timedelta(hours=num)
    elif unit == 'day' or unit == 'days':
        return timedelta(days=num)
    elif unit == 'week' or unit == 'weeks':
        return timedelta(weeks=num)
    else:
        return DEFAULT_DURATION


"""
Token Scope 定义：
- 'full': 全量访问（含私有内容），仅限自己使用
- 'qa_public': 问答服务，只用公开信息生成回答，不返回原始 facts
- 'browse_public': 公开浏览，可查看非私有的图谱和 facts
"""
VALID_SCOPES = ['full', 'qa_public', 'browse_public']
SCOPE_LABELS = {
    'full': '🔓 全量访问',
    'qa_public': '💬 问答服务',
    'browse_public': '👁️ 公开浏览'
}


def generate_token(
    duration: str = '7d',
    permissions: str = 'full',
    scope: str = None,
    note: str = None,
    qa_limit: int = None
) -> Dict:
    """
    生成新的访问 Token
    
    Args:
        duration: 有效期 (1h, 24h, 7d, etc.)
        permissions: 'full' 或 'readonly' (legacy)
        scope: 'full' | 'qa_public' | 'browse_public'
        note: 备注
    
    Returns:
        {
            'token': str,
            'expires_at': str,
            'permissions': str,
            'scope': str,
            'url_param': str
        }
    """
    # scope 优先，向后兼容 permissions
    if scope is None:
        scope = 'full' if permissions == 'full' else 'browse_public'
    if scope not in VALID_SCOPES:
        scope = 'browse_public'  # 默认最小权限
    
    # 问答限制：qa_public 默认有限制，full 默认无限制
    if qa_limit is None:
        qa_limit = DEFAULT_QA_LIMIT if scope == 'qa_public' else 0  # 0 表示无限制
    
    # 生成 token: uuid + 随机后缀
    token = f"{uuid.uuid4().hex[:16]}{secrets.token_hex(8)}"
    
    # 计算过期时间
    now = datetime.now()
    expires_at = now + parse_duration(duration)
    
    # 存入数据库
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO visual_tokens (token, created_at, expires_at, permissions, scope, note, qa_limit, qa_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
    ''', (
        token,
        now.isoformat(),
        expires_at.isoformat(),
        permissions,
        scope,
        note,
        qa_limit
    ))
    
    conn.commit()
    conn.close()
    
    return {
        'token': token,
        'created_at': now.isoformat(),
        'expires_at': expires_at.isoformat(),
        'expires_at_human': expires_at.strftime('%Y-%m-%d %H:%M'),
        'permissions': permissions,
        'scope': scope,
        'scope_label': SCOPE_LABELS.get(scope, scope),
        'duration': duration,
        'qa_limit': qa_limit
    }


def verify_token(token: str, ip: str = None) -> Tuple[bool, Optional[Dict]]:
    """
    验证 Token 有效性
    
    Args:
        token: Token 字符串
        ip: 访问者 IP（可选，用于记录）
    
    Returns:
        (valid, token_info) - valid 为 True 时返回 token 信息
    """
    if not token:
        return False, None
    
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT token, expires_at, permissions, revoked, access_count, scope, qa_limit, qa_count
        FROM visual_tokens
        WHERE token = ?
    ''', (token,))
    
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return False, {'error': 'token_not_found'}
    
    token_str, expires_at, permissions, revoked, access_count, scope, qa_limit, qa_count = row
    # 向后兼容：旧 token 没有 scope 字段
    if scope is None:
        scope = 'full' if permissions == 'full' else 'browse_public'
    # 向后兼容：旧 token 没有 qa_limit/qa_count 字段
    if qa_limit is None:
        qa_limit = DEFAULT_QA_LIMIT if scope == 'qa_public' else 0
    if qa_count is None:
        qa_count = 0
    
    # 检查是否已撤销
    if revoked:
        conn.close()
        return False, {'error': 'token_revoked'}
    
    # 检查是否过期
    expires_dt = datetime.fromisoformat(expires_at)
    if datetime.now() > expires_dt:
        conn.close()
        return False, {'error': 'token_expired', 'expired_at': expires_at}
    
    # 更新访问记录
    cursor.execute('''
        UPDATE visual_tokens
        SET access_count = access_count + 1,
            last_access_at = ?,
            last_access_ip = ?
        WHERE token = ?
    ''', (datetime.now().isoformat(), ip, token))
    
    conn.commit()
    conn.close()
    
    return True, {
        'token': token_str,
        'expires_at': expires_at,
        'permissions': permissions,
        'scope': scope,
        'scope_label': SCOPE_LABELS.get(scope, scope),
        'access_count': access_count + 1,
        'qa_limit': qa_limit,
        'qa_count': qa_count
    }


def check_qa_limit(token: str) -> Tuple[bool, int, int]:
    """
    检查问答次数限制
    
    Returns:
        (can_ask, remaining, limit)
        - can_ask: 是否还能问答
        - remaining: 剩余次数 (-1 表示无限制)
        - limit: 总限制 (0 表示无限制)
    """
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT qa_limit, qa_count FROM visual_tokens WHERE token = ?
    ''', (token,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return False, 0, 0
    
    qa_limit, qa_count = row
    if qa_limit is None:
        qa_limit = DEFAULT_QA_LIMIT
    if qa_count is None:
        qa_count = 0
    
    # 0 表示无限制
    if qa_limit == 0:
        return True, -1, 0
    
    remaining = qa_limit - qa_count
    return remaining > 0, remaining, qa_limit


def increment_qa_count(token: str) -> bool:
    """
    增加问答计数
    
    Returns:
        是否成功（如果已达限制则返回 False）
    """
    can_ask, remaining, limit = check_qa_limit(token)
    if not can_ask:
        return False
    
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE visual_tokens 
        SET qa_count = COALESCE(qa_count, 0) + 1
        WHERE token = ?
    ''', (token,))
    
    conn.commit()
    conn.close()
    return True


def get_qa_stats(token: str) -> Dict:
    """获取问答统计"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT qa_limit, qa_count FROM visual_tokens WHERE token = ?
    ''', (token,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {'error': 'token_not_found'}
    
    qa_limit, qa_count = row
    qa_limit = qa_limit if qa_limit is not None else DEFAULT_QA_LIMIT
    qa_count = qa_count if qa_count is not None else 0
    
    return {
        'limit': qa_limit,
        'used': qa_count,
        'remaining': qa_limit - qa_count if qa_limit > 0 else -1,
        'unlimited': qa_limit == 0
    }


def revoke_token(token: str) -> bool:
    """撤销指定 Token"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE visual_tokens
        SET revoked = 1
        WHERE token = ? OR token LIKE ?
    ''', (token, f"{token}%"))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0


def revoke_all_tokens() -> int:
    """撤销所有有效 Token"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE visual_tokens
        SET revoked = 1
        WHERE revoked = 0
    ''')
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected


def list_tokens(include_revoked: bool = False) -> List[Dict]:
    """列出所有 Token"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    if include_revoked:
        cursor.execute('''
            SELECT token, created_at, expires_at, permissions, 
                   access_count, last_access_at, revoked, note, scope
            FROM visual_tokens
            ORDER BY created_at DESC
        ''')
    else:
        cursor.execute('''
            SELECT token, created_at, expires_at, permissions, 
                   access_count, last_access_at, revoked, note, scope
            FROM visual_tokens
            WHERE revoked = 0 AND expires_at > ?
            ORDER BY created_at DESC
        ''', (datetime.now().isoformat(),))
    
    results = []
    for row in cursor.fetchall():
        scope = row[8] if len(row) > 8 and row[8] else 'full'
        results.append({
            'token': row[0][:8] + '...',  # 只显示前8位
            'token_full': row[0],
            'created_at': row[1],
            'expires_at': row[2],
            'permissions': row[3],
            'access_count': row[4],
            'last_access_at': row[5],
            'revoked': bool(row[6]),
            'note': row[7],
            'scope': scope,
            'scope_label': SCOPE_LABELS.get(scope, scope)
        })
    
    conn.close()
    return results


def cleanup_expired_tokens() -> int:
    """清理过期 Token"""
    conn = get_sqlite()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM visual_tokens
        WHERE expires_at < ? AND revoked = 1
    ''', (datetime.now().isoformat(),))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected


def get_visual_url(token: str, base_url: str = None) -> str:
    """生成完整的访问 URL"""
    if not base_url:
        base_url = VISUAL_PUBLIC_URL
    return f"{base_url}?token={token}"


if __name__ == "__main__":
    # 测试
    print("===== Token 管理测试 =====")
    
    # 生成 token
    result = generate_token('24h', 'full', 'test token')
    print(f"生成: {result['token'][:16]}...")
    print(f"过期: {result['expires_at_human']}")
    
    # 验证
    valid, info = verify_token(result['token'])
    print(f"验证: {valid}, 权限: {info.get('permissions')}")
    
    # 列出
    tokens = list_tokens()
    print(f"有效 Token 数: {len(tokens)}")
