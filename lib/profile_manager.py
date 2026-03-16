#!/usr/bin/env python3
"""
Profile Manager
===============
管理 Cogmate 的多租户 Profile（命名空间）

每个 Profile 代表一个独立的身份/角色，拥有独立的知识库。
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from config import SQLITE_PATH, PROFILES_DIR, setup_logging

logger = setup_logging("profile_manager")


# 默认 Profile 配置模板
DEFAULT_HUMAN_PROFILE = {
    "namespace": "default",
    "type": "human",
    "identity": {
        "name": "Your Name",
        "title": "知识探索者",
        "bio": "我的个人知识管理系统",
        "avatar": ""
    },
    "preferences": {
        "default_content_type": "观点",
        "default_emotion": "中性",
        "auto_discover_relations": True,
        "daily_report_enabled": True,
        "daily_report_time": "20:00"
    }
}

DEFAULT_CHARACTER_PROFILE = {
    "namespace": "",
    "type": "character",
    "identity": {
        "name": "",
        "title": "",
        "bio": "",
        "avatar": ""
    },
    "persona": {
        "background": "",
        "traits": [],
        "speaking_style": "",
        "greeting": "",
        "forbidden_topics": [],
        "temperature": 0.8
    },
    "memory_config": {
        "remember_user": True,
        "auto_associate": True
    },
    "preferences": {
        "default_content_type": "观点",
        "daily_report_enabled": False
    }
}


class ProfileManager:
    """Profile 管理器"""
    
    def __init__(self):
        self.profiles_dir = Path(PROFILES_DIR)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保 default profile 存在
        self._ensure_default_profile()
    
    def _ensure_default_profile(self):
        """确保默认 profile 存在"""
        default_path = self.profiles_dir / "default.json"
        if not default_path.exists():
            self.save_profile_config("default", DEFAULT_HUMAN_PROFILE)
    
    def _get_db_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(SQLITE_PATH)
    
    def list_profiles(self) -> List[Dict[str, Any]]:
        """列出所有 Profile"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT namespace, type, created_at, last_active
            FROM profiles
            ORDER BY created_at DESC
        """)
        
        profiles = []
        for row in cursor.fetchall():
            profile = {
                "namespace": row[0],
                "type": row[1],
                "created_at": row[2],
                "last_active": row[3]
            }
            # 加载配置文件
            config = self.load_profile_config(row[0])
            if config:
                profile["identity"] = config.get("identity", {})
            profiles.append(profile)
        
        conn.close()
        return profiles
    
    def get_profile(self, namespace: str) -> Optional[Dict[str, Any]]:
        """获取指定 Profile"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT namespace, type, config, created_at, last_active
            FROM profiles
            WHERE namespace = ?
        """, (namespace,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # 加载配置文件
        config = self.load_profile_config(namespace)
        if not config:
            config = {}
        
        return {
            "namespace": row[0],
            "type": row[1],
            "db_config": json.loads(row[2]) if row[2] else {},
            "created_at": row[3],
            "last_active": row[4],
            **config
        }
    
    def create_profile(
        self,
        namespace: str,
        profile_type: str = "human",
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """创建新 Profile"""
        if self.get_profile(namespace):
            logger.warning(f"Profile '{namespace}' 已存在")
            return False
        
        # 验证 namespace 格式
        if not namespace or not namespace.replace("_", "").replace("-", "").isalnum():
            logger.error(f"无效的 namespace: {namespace}")
            return False
        
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO profiles (namespace, type, config, created_at)
                VALUES (?, ?, ?, ?)
            """, (namespace, profile_type, json.dumps(config or {}), datetime.now().isoformat()))
            
            conn.commit()
            
            # 创建配置文件
            if profile_type == "character":
                default_config = DEFAULT_CHARACTER_PROFILE.copy()
            else:
                default_config = DEFAULT_HUMAN_PROFILE.copy()
            
            default_config["namespace"] = namespace
            if config:
                self._deep_update(default_config, config)
            
            self.save_profile_config(namespace, default_config)
            
            logger.info(f"创建 Profile: {namespace} (type={profile_type})")
            return True
            
        except Exception as e:
            logger.error(f"创建 Profile 失败: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def update_profile(self, namespace: str, config: Dict[str, Any]) -> bool:
        """更新 Profile 配置"""
        if not self.get_profile(namespace):
            logger.warning(f"Profile '{namespace}' 不存在")
            return False
        
        # 加载现有配置
        existing = self.load_profile_config(namespace) or {}
        self._deep_update(existing, config)
        
        # 保存
        self.save_profile_config(namespace, existing)
        
        # 更新数据库
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE profiles
            SET last_active = ?
            WHERE namespace = ?
        """, (datetime.now().isoformat(), namespace))
        conn.commit()
        conn.close()
        
        logger.info(f"更新 Profile: {namespace}")
        return True
    
    def delete_profile(self, namespace: str, delete_data: bool = False) -> bool:
        """删除 Profile
        
        Args:
            namespace: Profile 名称
            delete_data: 是否同时删除该 namespace 的所有数据（危险！）
        """
        if namespace == "default":
            logger.error("不能删除 default profile")
            return False
        
        if not self.get_profile(namespace):
            logger.warning(f"Profile '{namespace}' 不存在")
            return False
        
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            if delete_data:
                # 删除该 namespace 的所有数据
                cursor.execute("DELETE FROM facts WHERE namespace = ?", (namespace,))
                cursor.execute("DELETE FROM abstracts WHERE namespace = ?", (namespace,))
                cursor.execute("DELETE FROM associations WHERE namespace = ?", (namespace,))
                logger.warning(f"已删除 namespace '{namespace}' 的所有数据")
            
            # 删除 profile 记录
            cursor.execute("DELETE FROM profiles WHERE namespace = ?", (namespace,))
            conn.commit()
            
            # 删除配置文件
            config_path = self.profiles_dir / f"{namespace}.json"
            if config_path.exists():
                config_path.unlink()
            
            logger.info(f"删除 Profile: {namespace}")
            return True
            
        except Exception as e:
            logger.error(f"删除 Profile 失败: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def touch_profile(self, namespace: str):
        """更新 Profile 的最后活跃时间"""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE profiles
            SET last_active = ?
            WHERE namespace = ?
        """, (datetime.now().isoformat(), namespace))
        conn.commit()
        conn.close()
    
    def load_profile_config(self, namespace: str) -> Optional[Dict[str, Any]]:
        """加载 Profile 配置文件"""
        config_path = self.profiles_dir / f"{namespace}.json"
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return None
    
    def save_profile_config(self, namespace: str, config: Dict[str, Any]):
        """保存 Profile 配置文件"""
        config_path = self.profiles_dir / f"{namespace}.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def get_persona_prompt(self, namespace: str) -> Optional[str]:
        """获取角色的 persona prompt（用于注入到对话）"""
        config = self.load_profile_config(namespace)
        if not config or config.get("type") != "character":
            return None
        
        persona = config.get("persona", {})
        identity = config.get("identity", {})
        
        parts = []
        
        if identity.get("name"):
            parts.append(f"你是 {identity['name']}")
            if identity.get("title"):
                parts.append(f"，{identity['title']}。")
            else:
                parts.append("。")
        
        if persona.get("background"):
            parts.append(f"\n\n背景：{persona['background']}")
        
        if persona.get("traits"):
            parts.append(f"\n\n性格特征：{', '.join(persona['traits'])}")
        
        if persona.get("speaking_style"):
            parts.append(f"\n\n说话风格：{persona['speaking_style']}")
        
        if persona.get("forbidden_topics"):
            parts.append(f"\n\n禁止讨论的话题：{', '.join(persona['forbidden_topics'])}")
        
        return "".join(parts) if parts else None
    
    def _deep_update(self, base: dict, update: dict):
        """深度更新字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value


# 单例
_profile_manager = None

def get_profile_manager() -> ProfileManager:
    """获取 ProfileManager 单例"""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ProfileManager()
    return _profile_manager
