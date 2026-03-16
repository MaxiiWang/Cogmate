#!/usr/bin/env python3
"""
Namespace Migration Script
==========================
将 Cogmate 从单租户升级为多租户（namespace 隔离）

用法：
    python scripts/migrate_namespace.py

此脚本幂等，可重复运行。
"""

import sqlite3
import sys
from pathlib import Path

# 添加 lib 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from config import SQLITE_PATH, get_neo4j

def migrate_sqlite():
    """迁移 SQLite 数据库"""
    print(f"[SQLite] 连接数据库: {SQLITE_PATH}")
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    
    # 检查 facts 表是否已有 namespace 字段
    cursor.execute("PRAGMA table_info(facts)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'namespace' not in columns:
        print("[SQLite] 添加 facts.namespace 字段...")
        cursor.execute("ALTER TABLE facts ADD COLUMN namespace TEXT DEFAULT 'default'")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_facts_namespace ON facts(namespace)")
        print("[SQLite] ✓ facts 表迁移完成")
    else:
        print("[SQLite] ✓ facts.namespace 已存在，跳过")
    
    # 检查 abstracts 表是否已有 namespace 字段
    cursor.execute("PRAGMA table_info(abstracts)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'namespace' not in columns:
        print("[SQLite] 添加 abstracts.namespace 字段...")
        cursor.execute("ALTER TABLE abstracts ADD COLUMN namespace TEXT DEFAULT 'default'")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_abstracts_namespace ON abstracts(namespace)")
        print("[SQLite] ✓ abstracts 表迁移完成")
    else:
        print("[SQLite] ✓ abstracts.namespace 已存在，跳过")
    
    # 检查 associations 表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='associations'")
    if cursor.fetchone():
        # 检查 associations 表是否已有 namespace 字段
        cursor.execute("PRAGMA table_info(associations)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'namespace' not in columns:
            print("[SQLite] 添加 associations.namespace 字段...")
            cursor.execute("ALTER TABLE associations ADD COLUMN namespace TEXT DEFAULT 'default'")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_associations_namespace ON associations(namespace)")
            print("[SQLite] ✓ associations 表迁移完成")
        else:
            print("[SQLite] ✓ associations.namespace 已存在，跳过")
    else:
        print("[SQLite] ✓ associations 表不存在，跳过")
    
    # 创建 profiles 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            namespace TEXT PRIMARY KEY,
            type TEXT NOT NULL DEFAULT 'human',
            config TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            last_active TEXT
        )
    """)
    
    # 插入默认 profile
    cursor.execute("""
        INSERT OR IGNORE INTO profiles (namespace, type, config)
        VALUES ('default', 'human', '{}')
    """)
    
    conn.commit()
    conn.close()
    print("[SQLite] ✓ 迁移完成")


def migrate_neo4j():
    """迁移 Neo4j 数据库"""
    print("[Neo4j] 连接数据库...")
    
    try:
        driver = get_neo4j()
        with driver.session() as session:
            # 检查是否已有 namespace 属性
            result = session.run("""
                MATCH (f:Fact)
                WHERE f.namespace IS NULL
                RETURN count(f) as count
            """)
            count = result.single()["count"]
            
            if count > 0:
                print(f"[Neo4j] 更新 {count} 个节点添加 namespace 属性...")
                session.run("""
                    MATCH (f:Fact)
                    WHERE f.namespace IS NULL
                    SET f.namespace = 'default'
                """)
                print("[Neo4j] ✓ 节点迁移完成")
            else:
                print("[Neo4j] ✓ 所有节点已有 namespace，跳过")
            
            # 创建索引
            session.run("""
                CREATE INDEX fact_namespace IF NOT EXISTS
                FOR (f:Fact) ON (f.namespace)
            """)
            print("[Neo4j] ✓ 索引创建完成")
        
        driver.close()
    except Exception as e:
        print(f"[Neo4j] ⚠ 迁移失败: {e}")
        print("[Neo4j] 如果 Neo4j 未运行，稍后手动执行迁移")


def migrate_qdrant():
    """Qdrant 不需要迁移，新 namespace 会创建新 Collection"""
    print("[Qdrant] ✓ 无需迁移（新 namespace 自动创建新 Collection）")


def main():
    print("=" * 50)
    print("Cogmate Namespace 迁移工具")
    print("=" * 50)
    print()
    
    migrate_sqlite()
    print()
    migrate_neo4j()
    print()
    migrate_qdrant()
    
    print()
    print("=" * 50)
    print("✓ 迁移完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
