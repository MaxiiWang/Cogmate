#!/usr/bin/env python3
"""
Research Module - 深度调研功能
==============================
支持 URL 和主题的深度研究，与模拟世界交叉比对
"""

import os
import re
import json
import httpx
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field

import trafilatura
from trafilatura.settings import use_config

from config import (
    get_qdrant, get_embedder, get_sqlite, get_neo4j,
    setup_logging, ANTHROPIC_API_KEY, LLM_MODEL
)

logger = setup_logging("research")

# Trafilatura 配置
TRAFILATURA_CONFIG = use_config()
TRAFILATURA_CONFIG.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")


@dataclass
class ResearchFinding:
    """单条研究发现"""
    content: str
    category: str  # consistent, incremental, contradictory
    related_fact_id: Optional[str] = None
    related_fact_content: Optional[str] = None
    similarity: float = 0.0
    source_url: str = ""


@dataclass
class ResearchReport:
    """研究报告"""
    title: str
    url: str
    summary: str
    findings: List[ResearchFinding] = field(default_factory=list)
    raw_content: str = ""
    pages_analyzed: int = 1


def extract_url_content(url: str) -> Tuple[str, str]:
    """提取 URL 内容，返回 (title, content)"""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return "", ""
        
        # 提取标题
        title = trafilatura.extract(downloaded, include_comments=False, 
                                    include_tables=True, output_format='txt',
                                    config=TRAFILATURA_CONFIG)
        
        # 提取正文
        content = trafilatura.extract(downloaded, include_comments=False,
                                      include_tables=True, include_links=True,
                                      config=TRAFILATURA_CONFIG)
        
        # 尝试从 HTML 中提取标题
        import re
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', downloaded, re.IGNORECASE)
        page_title = title_match.group(1).strip() if title_match else url
        
        return page_title, content or ""
    except Exception as e:
        logger.error(f"提取 URL 内容失败: {e}")
        return "", ""


def discover_subpages(url: str, html_content: str = None, max_pages: int = 8) -> List[str]:
    """发现主站的子页面"""
    try:
        if not html_content:
            html_content = trafilatura.fetch_url(url)
        if not html_content:
            return []
        
        # 解析基础 URL
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # 提取所有链接
        links = re.findall(r'href=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        
        # 过滤和规范化链接
        valid_pages = set()
        priority_keywords = ['about', 'feature', 'doc', 'guide', 'overview', 'intro', 
                           'product', 'service', 'blog', 'article', 'team', 'mission']
        
        for link in links:
            # 跳过锚点、JS、外部链接等
            if link.startswith('#') or link.startswith('javascript:'):
                continue
            if link.startswith('mailto:') or link.startswith('tel:'):
                continue
            
            # 构建完整 URL
            if link.startswith('http'):
                full_url = link
            elif link.startswith('//'):
                full_url = f"{parsed.scheme}:{link}"
            elif link.startswith('/'):
                full_url = f"{base_url}{link}"
            else:
                full_url = urljoin(url, link)
            
            # 只保留同域名链接
            link_parsed = urlparse(full_url)
            if link_parsed.netloc != parsed.netloc:
                continue
            
            # 跳过资源文件
            if any(full_url.lower().endswith(ext) for ext in ['.css', '.js', '.png', '.jpg', '.gif', '.svg', '.pdf']):
                continue
            
            valid_pages.add(full_url)
        
        # 按优先级排序
        def priority_score(u):
            score = 0
            u_lower = u.lower()
            for kw in priority_keywords:
                if kw in u_lower:
                    score += 1
            # 短路径优先
            score += max(0, 5 - u.count('/'))
            return -score
        
        sorted_pages = sorted(valid_pages, key=priority_score)
        return sorted_pages[:max_pages]
    
    except Exception as e:
        logger.error(f"发现子页面失败: {e}")
        return []


def llm_analyze(content: str, task: str) -> str:
    """
    调用 LLM 进行分析
    注意：此函数在 CLI 模式下可能无法工作（需要 API key）
    在 OpenClaw Agent 模式下，分析由 Agent 自身完成
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY 未配置，跳过 LLM 分析")
        return ""
    
    try:
        client = httpx.Client(timeout=60)
        response = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": LLM_MODEL,
                "max_tokens": 2000,
                "messages": [
                    {"role": "user", "content": f"{task}\n\n内容:\n{content[:8000]}"}
                ],
                "system": "你是一个专业的研究分析助手。请用中文回复。"
            }
        )
        data = response.json()
        if "content" in data and len(data["content"]) > 0:
            return data["content"][0]["text"]
        return ""
    except Exception as e:
        logger.error(f"LLM 分析失败: {e}")
        return ""


def extract_key_points(content: str) -> List[str]:
    """提取核心观点"""
    prompt = """请从以下内容中提取 3-6 个核心观点或事实。
每个观点用一句话概括，要具体、有信息量。
格式：每行一个观点，不要编号或bullet。"""
    
    result = llm_analyze(content, prompt)
    if not result:
        return []
    
    # 解析结果
    points = [line.strip() for line in result.split('\n') if line.strip()]
    # 过滤太短或太长的
    points = [p for p in points if 10 < len(p) < 200]
    return points[:6]


def cross_reference(points: List[str], source_url: str) -> List[ResearchFinding]:
    """与模拟世界交叉比对"""
    findings = []
    
    try:
        qdrant = get_qdrant()
        embedder = get_embedder()
        
        for point in points:
            # 向量搜索
            query_vector = embedder.encode(point).tolist()
            
            try:
                response = qdrant.query_points(
                    collection_name="brain_facts",
                    query=query_vector,
                    limit=3,
                    score_threshold=0.5
                )
                results = response.points if hasattr(response, 'points') else []
            except Exception as e:
                logger.error(f"Qdrant 搜索失败: {e}")
                results = []
            
            if results:
                top = results[0]
                top_content = top.payload.get('content', '')
                
                if top.score >= 0.85:
                    # 高度相似 = 一致
                    category = "consistent"
                elif top.score >= 0.65:
                    # 中等相似 = 可能矛盾或增量，需要 LLM 判断
                    relation = llm_judge_relation(point, top_content)
                    category = relation
                else:
                    # 低相似 = 增量
                    category = "incremental"
                
                findings.append(ResearchFinding(
                    content=point,
                    category=category,
                    related_fact_id=str(top.id)[:8],
                    related_fact_content=top_content[:100],
                    similarity=top.score,
                    source_url=source_url
                ))
            else:
                # 没有相关内容 = 增量
                findings.append(ResearchFinding(
                    content=point,
                    category="incremental",
                    source_url=source_url
                ))
    
    except Exception as e:
        logger.error(f"交叉比对失败: {e}")
        # 如果比对失败，所有都标记为增量
        for point in points:
            findings.append(ResearchFinding(
                content=point,
                category="incremental",
                source_url=source_url
            ))
    
    return findings


def llm_judge_relation(new_content: str, existing_content: str) -> str:
    """用 LLM 判断两个内容的关系"""
    prompt = f"""比较以下两段内容的关系：

新发现: {new_content}

现有记录: {existing_content}

请判断关系类型（只回复一个词）：
- consistent: 新发现支持/印证现有记录
- incremental: 新发现是新增信息，与现有记录不冲突
- contradictory: 新发现与现有记录矛盾/冲突"""
    
    result = llm_analyze(new_content, prompt)
    result = result.strip().lower()
    
    if 'consistent' in result:
        return 'consistent'
    elif 'contradictory' in result or '矛盾' in result:
        return 'contradictory'
    else:
        return 'incremental'


def generate_summary(content: str) -> str:
    """生成内容摘要"""
    prompt = "用 2-3 句话概括以下内容的核心要点："
    return llm_analyze(content, prompt)


def research_url(url: str, deep: bool = True) -> ResearchReport:
    """
    研究单个 URL
    
    Args:
        url: 目标 URL
        deep: 是否深度探索子页面
    
    Returns:
        ResearchReport
    """
    logger.info(f"开始研究: {url}")
    
    # 提取主页内容
    title, main_content = extract_url_content(url)
    if not main_content:
        return ResearchReport(
            title="提取失败",
            url=url,
            summary="无法提取网页内容",
            raw_content=""
        )
    
    all_content = main_content
    pages_analyzed = 1
    
    # 深度模式：探索子页面
    if deep:
        html = trafilatura.fetch_url(url)
        subpages = discover_subpages(url, html)
        logger.info(f"发现 {len(subpages)} 个子页面")
        
        for suburl in subpages[:5]:  # 最多探索 5 个子页面
            _, sub_content = extract_url_content(suburl)
            if sub_content:
                all_content += f"\n\n--- {suburl} ---\n{sub_content}"
                pages_analyzed += 1
    
    # 生成摘要
    summary = generate_summary(all_content)
    
    # 提取核心观点
    key_points = extract_key_points(all_content)
    logger.info(f"提取了 {len(key_points)} 个核心观点")
    
    # 交叉比对
    findings = cross_reference(key_points, url)
    
    return ResearchReport(
        title=title,
        url=url,
        summary=summary,
        findings=findings,
        raw_content=all_content[:5000],
        pages_analyzed=pages_analyzed
    )


def research_topic(topic: str) -> ResearchReport:
    """
    研究主题（通过搜索）
    
    Args:
        topic: 研究主题
    
    Returns:
        ResearchReport
    """
    # 使用 Brave Search
    try:
        brave_api_key = os.environ.get('BRAVE_API_KEY', '')
        if not brave_api_key:
            return ResearchReport(
                title=topic,
                url="",
                summary="Brave Search API 未配置",
                raw_content=""
            )
        
        client = httpx.Client(timeout=30)
        response = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": brave_api_key},
            params={"q": topic, "count": 5}
        )
        data = response.json()
        
        all_content = ""
        urls_analyzed = []
        
        for result in data.get("web", {}).get("results", [])[:3]:
            result_url = result.get("url", "")
            _, content = extract_url_content(result_url)
            if content:
                all_content += f"\n\n--- {result_url} ---\n{content}"
                urls_analyzed.append(result_url)
        
        if not all_content:
            return ResearchReport(
                title=topic,
                url="",
                summary="搜索结果无法提取内容",
                raw_content=""
            )
        
        # 生成摘要
        summary = generate_summary(all_content)
        
        # 提取核心观点
        key_points = extract_key_points(all_content)
        
        # 交叉比对
        findings = cross_reference(key_points, ", ".join(urls_analyzed))
        
        return ResearchReport(
            title=f"主题研究: {topic}",
            url=", ".join(urls_analyzed),
            summary=summary,
            findings=findings,
            raw_content=all_content[:5000],
            pages_analyzed=len(urls_analyzed)
        )
    
    except Exception as e:
        logger.error(f"主题研究失败: {e}")
        return ResearchReport(
            title=topic,
            url="",
            summary=f"研究失败: {str(e)}",
            raw_content=""
        )


def format_report(report: ResearchReport) -> str:
    """格式化研究报告为 Telegram 消息"""
    lines = []
    lines.append(f"📑 **Research Report: {report.title[:50]}**")
    lines.append("")
    lines.append(f"🔗 {report.url[:80]}")
    lines.append(f"📄 分析了 {report.pages_analyzed} 个页面")
    lines.append("")
    lines.append("## 摘要")
    lines.append(report.summary)
    lines.append("")
    lines.append("## 发现")
    lines.append("")
    
    # 按类别分组
    consistent = [f for f in report.findings if f.category == 'consistent']
    incremental = [f for f in report.findings if f.category == 'incremental']
    contradictory = [f for f in report.findings if f.category == 'contradictory']
    
    idx = 1
    
    if consistent:
        lines.append("### ✅ 一致（支持现有认知）")
        for f in consistent:
            lines.append(f"{idx}. {f.content}")
            if f.related_fact_id:
                lines.append(f"   ← 关联: `{f.related_fact_id}` (相似度 {f.similarity:.0%})")
            idx += 1
        lines.append("")
    
    if incremental:
        lines.append("### ➕ 增量（新信息）")
        for f in incremental:
            lines.append(f"{idx}. {f.content}")
            idx += 1
        lines.append("")
    
    if contradictory:
        lines.append("### ⚠️ 矛盾（与现有认知冲突）")
        for f in contradictory:
            lines.append(f"{idx}. {f.content}")
            if f.related_fact_id:
                lines.append(f"   ⚔️ 与 `{f.related_fact_id}` 冲突")
                lines.append(f"   现有: {f.related_fact_content}")
            idx += 1
        lines.append("")
    
    lines.append("---")
    lines.append("**操作**: 回复数字存入对应条目")
    lines.append("- `2,3,5` 存入多条")
    lines.append("- `all` 存入全部增量")
    lines.append("- `skip` 跳过本次")
    
    if contradictory:
        lines.append("")
        lines.append("**矛盾处理**: 回复 `conflict N` 处理第 N 条矛盾")
    
    return "\n".join(lines)


def fetch_url_content(url: str, deep: bool = True) -> Dict:
    """
    仅提取 URL 内容，不进行 LLM 分析（供 Agent 使用）
    
    Returns:
        {
            "title": str,
            "url": str,
            "content": str,
            "pages_analyzed": int,
            "subpages": list
        }
    """
    logger.info(f"提取内容: {url}")
    
    # 提取主页内容
    title, main_content = extract_url_content(url)
    if not main_content:
        return {
            "title": "提取失败",
            "url": url,
            "content": "",
            "pages_analyzed": 0,
            "subpages": []
        }
    
    all_content = main_content
    pages_analyzed = 1
    subpages = []
    
    # 深度模式：探索子页面
    if deep:
        html = trafilatura.fetch_url(url)
        discovered = discover_subpages(url, html)
        logger.info(f"发现 {len(discovered)} 个子页面")
        
        for suburl in discovered[:5]:
            _, sub_content = extract_url_content(suburl)
            if sub_content:
                all_content += f"\n\n--- {suburl} ---\n{sub_content}"
                pages_analyzed += 1
                subpages.append(suburl)
    
    return {
        "title": title,
        "url": url,
        "content": all_content,
        "pages_analyzed": pages_analyzed,
        "subpages": subpages
    }


def find_related_facts(content: str, limit: int = 5) -> List[Dict]:
    """
    在模拟世界中查找与内容相关的事实
    
    Returns:
        List of {"id": str, "content": str, "similarity": float}
    """
    try:
        qdrant = get_qdrant()
        embedder = get_embedder()
        
        # 取内容摘要进行搜索
        search_text = content[:1000]
        query_vector = embedder.encode(search_text).tolist()
        
        response = qdrant.query_points(
            collection_name="brain_facts",
            query=query_vector,
            limit=limit,
            score_threshold=0.5
        )
        results = response.points if hasattr(response, 'points') else []
        
        return [
            {
                "id": str(r.id)[:8],
                "content": r.payload.get('content', '')[:200],
                "similarity": r.score
            }
            for r in results
        ]
    except Exception as e:
        logger.error(f"查找相关事实失败: {e}")
        return []


if __name__ == "__main__":
    # 测试
    import sys
    if len(sys.argv) > 1:
        url = sys.argv[1]
        report = research_url(url)
        print(format_report(report))
