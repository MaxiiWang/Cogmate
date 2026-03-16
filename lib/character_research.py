#!/usr/bin/env python3
"""
Character Research Module - 角色调研与 Persona 生成
====================================================
基于历史人物/虚构角色进行调研，生成角色设定
"""

import json
import os
import httpx
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from config import (
    setup_logging, ANTHROPIC_API_KEY, LLM_MODEL
)
from research import extract_url_content

logger = setup_logging("character_research")

# Brave Search API
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")


def search_brave(query: str, count: int = 5) -> List[Dict]:
    """使用 Brave Search API 搜索"""
    if not BRAVE_API_KEY:
        logger.warning("BRAVE_API_KEY 未配置，尝试使用备用搜索")
        return search_duckduckgo(query, count)
    
    try:
        client = httpx.Client(timeout=30.0)
        response = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": BRAVE_API_KEY},
            params={"q": query, "count": count}
        )
        
        if response.status_code != 200:
            logger.warning(f"Brave Search 失败: {response.status_code}")
            return search_duckduckgo(query, count)
        
        data = response.json()
        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", "")
            })
        return results
        
    except Exception as e:
        logger.error(f"Brave Search 错误: {e}")
        return search_duckduckgo(query, count)


def search_duckduckgo(query: str, count: int = 5) -> List[Dict]:
    """备用搜索：使用 DuckDuckGo HTML 搜索"""
    try:
        client = httpx.Client(timeout=30.0, follow_redirects=True)
        response = client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; research bot)"}
        )
        
        if response.status_code != 200:
            return []
        
        import re
        results = []
        
        # 简单解析 DuckDuckGo HTML 结果
        pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, response.text)
        
        for url, title in matches[:count]:
            # DuckDuckGo 的 URL 需要解码
            if url.startswith("//duckduckgo.com/l/?uddg="):
                import urllib.parse
                url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
            results.append({
                "title": title.strip(),
                "url": url,
                "description": ""
            })
        
        return results
        
    except Exception as e:
        logger.error(f"DuckDuckGo 搜索错误: {e}")
        return []


@dataclass
class CharacterPersona:
    """角色 Persona 数据结构"""
    based_on: List[str] = field(default_factory=list)
    background: str = ""
    era: str = ""
    traits: List[str] = field(default_factory=list)
    speaking_style: str = ""
    core_beliefs: List[str] = field(default_factory=list)
    famous_quotes: List[str] = field(default_factory=list)
    greeting: str = ""
    
    def to_dict(self) -> dict:
        return {
            "based_on": self.based_on,
            "background": self.background,
            "era": self.era,
            "traits": self.traits,
            "speaking_style": self.speaking_style,
            "core_beliefs": self.core_beliefs,
            "famous_quotes": self.famous_quotes,
            "greeting": self.greeting
        }


def search_character_info(character_name: str, max_results: int = 5) -> List[Dict]:
    """搜索角色相关信息"""
    queries = [
        f"{character_name} 生平 背景",
        f"{character_name} 思想 观点 名言",
        f"{character_name} 性格 特点"
    ]
    
    all_results = []
    seen_urls = set()
    
    for query in queries:
        results = search_brave(query, count=max_results)
        for r in results:
            if r.get('url') not in seen_urls:
                seen_urls.add(r.get('url'))
                all_results.append(r)
    
    return all_results[:max_results * 2]  # 限制总数


def fetch_character_content(search_results: List[Dict], max_pages: int = 3) -> str:
    """从搜索结果中提取内容"""
    contents = []
    pages_fetched = 0
    
    for result in search_results:
        if pages_fetched >= max_pages:
            break
            
        url = result.get('url', '')
        if not url:
            continue
        
        logger.info(f"提取内容: {url}")
        title, content = extract_url_content(url)
        
        if content and len(content) > 200:
            contents.append(f"## 来源: {title}\n{content[:3000]}")
            pages_fetched += 1
    
    return "\n\n---\n\n".join(contents)


def generate_persona_from_content(
    character_names: List[str],
    content: str,
    model: str = None
) -> CharacterPersona:
    """基于调研内容生成 Persona"""
    
    if not ANTHROPIC_API_KEY:
        logger.warning("未配置 ANTHROPIC_API_KEY，使用默认 Persona")
        return CharacterPersona(
            based_on=character_names,
            background=f"基于 {', '.join(character_names)} 的角色",
            traits=["智慧", "博学"],
            speaking_style="典雅、富有哲理",
            greeting=f"你好，我是基于 {', '.join(character_names)} 的角色。"
        )
    
    model = model or LLM_MODEL
    names_str = "、".join(character_names)
    
    prompt = f"""基于以下关于「{names_str}」的调研资料，生成一个角色 Persona 设定。

调研资料:
{content[:8000]}

请生成 JSON 格式的角色设定，包含以下字段:
- background: 角色背景故事（200-400字，第一人称）
- era: 所处年代
- traits: 性格特征列表（3-6个词）
- speaking_style: 说话风格描述（如何用语、常用句式、语气特点）
- core_beliefs: 核心信念/观点列表（3-5条）
- famous_quotes: 标志性语录（2-4条，原文）
- greeting: 开场白（角色第一次与用户对话时说的话，要符合角色风格）

要求:
1. 忠于历史/原作设定
2. 说话风格要有辨识度
3. greeting 要自然，体现角色特点
4. 如果是多个人物，融合他们的共同特质

只返回 JSON，不要其他内容。"""

    try:
        client = httpx.Client(timeout=60.0)
        response = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": model,
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        
        if response.status_code != 200:
            logger.error(f"LLM API 错误: {response.status_code}")
            raise Exception(f"API error: {response.status_code}")
        
        result = response.json()
        content_text = result["content"][0]["text"]
        
        # 提取 JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', content_text)
        if json_match:
            persona_data = json.loads(json_match.group())
            
            return CharacterPersona(
                based_on=character_names,
                background=persona_data.get("background", ""),
                era=persona_data.get("era", ""),
                traits=persona_data.get("traits", []),
                speaking_style=persona_data.get("speaking_style", ""),
                core_beliefs=persona_data.get("core_beliefs", []),
                famous_quotes=persona_data.get("famous_quotes", []),
                greeting=persona_data.get("greeting", "")
            )
        else:
            raise Exception("无法从响应中提取 JSON")
            
    except Exception as e:
        logger.error(f"生成 Persona 失败: {e}")
        # 返回基本 Persona
        return CharacterPersona(
            based_on=character_names,
            background=f"基于 {names_str} 的角色",
            traits=["智慧"],
            speaking_style="典雅",
            greeting=f"你好，我是 {names_str}。"
        )


def research_character(
    character_names: List[str],
    depth: str = "normal",  # normal | deep
    preview: bool = False
) -> Dict:
    """
    完整的角色调研流程
    
    Args:
        character_names: 参考人物列表
        depth: 调研深度 (normal: 3页, deep: 6页)
        preview: 预览模式，不写入
    
    Returns:
        {
            "persona": CharacterPersona,
            "sources": List[str],
            "raw_content": str (如果 preview=True)
        }
    """
    logger.info(f"开始调研角色: {character_names}")
    
    max_pages = 6 if depth == "deep" else 3
    
    # 1. 搜索
    all_results = []
    for name in character_names:
        results = search_character_info(name, max_results=4)
        all_results.extend(results)
    
    if not all_results:
        logger.warning("未找到搜索结果")
        return {
            "persona": CharacterPersona(based_on=character_names),
            "sources": [],
            "error": "未找到相关资料"
        }
    
    # 2. 提取内容
    content = fetch_character_content(all_results, max_pages=max_pages)
    sources = [r.get('url', '') for r in all_results[:max_pages]]
    
    if not content:
        logger.warning("未能提取到内容")
        return {
            "persona": CharacterPersona(based_on=character_names),
            "sources": sources,
            "error": "无法提取页面内容"
        }
    
    # 3. 生成 Persona
    persona = generate_persona_from_content(character_names, content)
    
    result = {
        "persona": persona,
        "sources": sources
    }
    
    if preview:
        result["raw_content"] = content[:5000]
    
    return result


def apply_persona_to_profile(
    namespace: str,
    persona: CharacterPersona,
    character_names: List[str]
) -> bool:
    """将生成的 Persona 应用到 Profile"""
    from profile_manager import ProfileManager
    
    pm = ProfileManager()
    config = pm.load_profile_config(namespace)
    
    if not config:
        logger.error(f"Profile {namespace} 不存在")
        return False
    
    # 更新 identity
    if not config.get("identity"):
        config["identity"] = {}
    
    # 如果 name 为空，使用第一个角色名
    if not config["identity"].get("name"):
        config["identity"]["name"] = character_names[0]
    
    # 生成 title
    if persona.era:
        config["identity"]["title"] = f"{persona.era}的智者"
    
    # 更新 persona
    config["persona"] = persona.to_dict()
    
    # 确保类型是 character
    config["type"] = "character"
    
    pm.save_profile_config(namespace, config)
    logger.info(f"Persona 已应用到 {namespace}")
    
    return True


def store_initial_knowledge(
    namespace: str,
    persona: CharacterPersona
) -> int:
    """将角色的核心信念和语录写入知识库"""
    from cogmate_core import CogmateAgent
    
    cogmate = CogmateAgent(namespace=namespace)
    stored_count = 0
    
    # 存储背景
    if persona.background:
        cogmate.store(
            content=persona.background,
            content_type="观点",
            context="角色背景设定",
            source_type="user_input"
        )
        stored_count += 1
    
    # 存储核心信念
    for belief in persona.core_beliefs:
        cogmate.store(
            content=belief,
            content_type="观点",
            context="核心信念",
            source_type="user_input"
        )
        stored_count += 1
    
    # 存储名言
    for quote in persona.famous_quotes:
        cogmate.store(
            content=quote,
            content_type="观点",
            context="标志性语录",
            source_type="user_input"
        )
        stored_count += 1
    
    logger.info(f"已存储 {stored_count} 条初始知识到 {namespace}")
    return stored_count


# CLI 入口
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python character_research.py <character_name> [--preview]")
        sys.exit(1)
    
    name = sys.argv[1]
    preview = "--preview" in sys.argv
    
    result = research_character([name], preview=preview)
    
    print("\n=== 角色 Persona ===\n")
    persona = result["persona"]
    print(f"基于: {', '.join(persona.based_on)}")
    print(f"年代: {persona.era}")
    print(f"性格: {', '.join(persona.traits)}")
    print(f"说话风格: {persona.speaking_style}")
    print(f"\n背景:\n{persona.background}")
    print(f"\n核心信念:")
    for b in persona.core_beliefs:
        print(f"  - {b}")
    print(f"\n名言:")
    for q in persona.famous_quotes:
        print(f"  「{q}」")
    print(f"\n开场白: {persona.greeting}")
    
    print(f"\n来源: {len(result['sources'])} 个页面")
