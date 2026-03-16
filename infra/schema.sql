-- Brain Agent SQLite Schema
-- 事实层元数据 + 抽象层 + 系统配置

-- 事实层元数据（主表）
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    summary TEXT NOT NULL,
    full_content TEXT,
    content_type TEXT CHECK(content_type IN ('事件', '观点', '情绪', '资讯', '决策')) NOT NULL,
    emotion_tag TEXT CHECK(emotion_tag IN ('积极', '消极', '中性', '困惑', '兴奋')),
    context TEXT,
    source_type TEXT CHECK(source_type IN ('user_input', 'user_confirmed_web')) NOT NULL DEFAULT 'user_input',
    source_url TEXT,
    last_retrieved_at TEXT,
    retrieval_count INTEGER DEFAULT 0,
    namespace TEXT DEFAULT 'default',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 关联记录（与 Neo4j 边同步）
CREATE TABLE IF NOT EXISTS associations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_fact_id TEXT NOT NULL,
    to_fact_id TEXT NOT NULL,
    relation_type TEXT CHECK(relation_type IN ('支持', '矛盾', '延伸', '触发', '因果')) NOT NULL,
    confidence INTEGER CHECK(confidence BETWEEN 1 AND 5) NOT NULL,
    created_by TEXT CHECK(created_by IN ('auto', 'manual')) NOT NULL DEFAULT 'auto',
    confirmed_by_user INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (from_fact_id) REFERENCES facts(fact_id),
    FOREIGN KEY (to_fact_id) REFERENCES facts(fact_id),
    UNIQUE(from_fact_id, to_fact_id, relation_type)
);

-- 抽象层
CREATE TABLE IF NOT EXISTS abstracts (
    abstract_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    supporting_fact_ids TEXT NOT NULL, -- JSON array
    counter_example_ids TEXT, -- JSON array
    page_index_path TEXT, -- 树索引路径，如 "/认知/决策模式"
    confirmed_by_user INTEGER DEFAULT 0,
    namespace TEXT DEFAULT 'default',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 可信数据源白名单
CREATE TABLE IF NOT EXISTS trusted_sources (
    domain TEXT PRIMARY KEY,
    category TEXT,
    added_at TEXT DEFAULT (datetime('now'))
);

-- 插入默认可信源
INSERT OR IGNORE INTO trusted_sources (domain, category) VALUES
    ('bloomberg.com', '财经'),
    ('reuters.com', '财经'),
    ('ft.com', '财经'),
    ('caixin.com', '财经'),
    ('yicai.com', '财经'),
    ('arxiv.org', '科技'),
    ('github.com', '科技'),
    ('techcrunch.com', '科技'),
    ('mit.edu', '科技'),
    ('mckinsey.com', '咨询'),
    ('hbr.org', '咨询'),
    ('bcg.com', '咨询'),
    ('deloitte.com', '咨询'),
    ('isa.org', '工业'),
    ('automation.com', '工业'),
    ('manufacturingtomorrow.com', '工业');

-- 系统状态
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Namespace profiles
CREATE TABLE IF NOT EXISTS profiles (
    namespace TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'human',  -- human | character
    config JSON,
    created_at TEXT DEFAULT (datetime('now')),
    last_active TEXT
);

-- 插入默认 profile
INSERT OR IGNORE INTO profiles (namespace, type) VALUES ('default', 'human');

-- 索引
CREATE INDEX IF NOT EXISTS idx_facts_timestamp ON facts(timestamp);
CREATE INDEX IF NOT EXISTS idx_facts_content_type ON facts(content_type);
CREATE INDEX IF NOT EXISTS idx_facts_source_type ON facts(source_type);
CREATE INDEX IF NOT EXISTS idx_facts_namespace ON facts(namespace);
CREATE INDEX IF NOT EXISTS idx_associations_from ON associations(from_fact_id);
CREATE INDEX IF NOT EXISTS idx_associations_to ON associations(to_fact_id);
CREATE INDEX IF NOT EXISTS idx_abstracts_page_index ON abstracts(page_index_path);
CREATE INDEX IF NOT EXISTS idx_abstracts_namespace ON abstracts(namespace);
