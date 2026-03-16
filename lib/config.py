"""
Cogmate - Centralized Configuration

All sensitive values are read from environment variables.
See .env.example for configuration template.
"""

import os
import logging
from pathlib import Path
from typing import Optional

# ===== Paths =====
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
PROFILES_DIR = CONFIG_DIR / "profiles"
SQLITE_PATH = Path(os.environ.get(
    "BRAIN_SQLITE_PATH",
    str(DATA_DIR / "cogmate.db")
))

# ===== Neo4j =====
NEO4J_URI = os.environ.get("BRAIN_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("BRAIN_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("BRAIN_NEO4J_PASSWORD", "changeme")

# ===== Qdrant =====
QDRANT_HOST = os.environ.get("BRAIN_QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("BRAIN_QDRANT_PORT", "6333"))
COLLECTION_NAME = os.environ.get("BRAIN_COLLECTION_NAME", "facts")

# ===== Embedding =====
EMBEDDING_MODEL = os.environ.get("BRAIN_EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = int(os.environ.get("BRAIN_EMBEDDING_DIM", "1024"))

# ===== Visual API =====
VISUAL_HOST = os.environ.get("BRAIN_VISUAL_HOST", "0.0.0.0")
VISUAL_PORT = int(os.environ.get("BRAIN_VISUAL_PORT", "8000"))
VISUAL_PUBLIC_URL = os.environ.get("BRAIN_VISUAL_PUBLIC_URL", "http://localhost:8000")

# ===== LLM =====
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.environ.get("BRAIN_LLM_MODEL", "claude-3-haiku-20240307")

# ===== Logging =====
LOG_LEVEL = os.environ.get("BRAIN_LOG_LEVEL", "INFO")

def setup_logging(name: str = "cogmate") -> logging.Logger:
    """Setup logging for a module."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "[%(name)s] %(levelname)s: %(message)s"
        ))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    return logger


# ===== Connection Helpers =====

_embedder = None
_qdrant_client = None
_neo4j_driver = None


def get_embedder():
    """Get or create the embedding model (singleton)."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        logger = setup_logging("config")
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def get_qdrant():
    """Get or create Qdrant client (singleton)."""
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _qdrant_client


def get_neo4j():
    """Get or create Neo4j driver (singleton)."""
    global _neo4j_driver
    if _neo4j_driver is None:
        from neo4j import GraphDatabase
        # Support no-auth mode when password is empty or "none"
        if NEO4J_PASSWORD and NEO4J_PASSWORD.lower() != "none":
            _neo4j_driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
        else:
            _neo4j_driver = GraphDatabase.driver(NEO4J_URI)
    return _neo4j_driver


def get_sqlite():
    """Get SQLite connection (creates new connection each call)."""
    import sqlite3
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(SQLITE_PATH)


def get_collection_name(namespace: str = "default") -> str:
    """Get Qdrant collection name for a namespace."""
    if namespace == "default":
        return COLLECTION_NAME
    return f"{COLLECTION_NAME}_{namespace}"


def ensure_namespace_schema():
    """Ensure the database has namespace support (run migration if needed)."""
    import sqlite3
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    # Check if namespace column exists on facts
    cursor.execute("PRAGMA table_info(facts)")
    columns = [row[1] for row in cursor.fetchall()]
    if "namespace" not in columns:
        # Run migration
        conn.close()
        from pathlib import Path as _Path
        import importlib.util
        migrate_script = _Path(__file__).parent.parent / "scripts" / "migrate_namespace.py"
        if migrate_script.exists():
            spec = importlib.util.spec_from_file_location("migrate_namespace", migrate_script)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.migrate()
    else:
        conn.close()


def close_connections():
    """Close all database connections."""
    global _neo4j_driver, _qdrant_client
    if _neo4j_driver:
        _neo4j_driver.close()
        _neo4j_driver = None
    if _qdrant_client:
        _qdrant_client = None
