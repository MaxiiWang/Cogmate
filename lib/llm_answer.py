"""
LLM 问答增强模块
===============
使用 LLM 生成更自然的回答
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional

# Centralized configuration
from config import ANTHROPIC_API_KEY, LLM_MODEL, setup_logging

logger = setup_logging("llm_answer")

# 尝试导入 httpx，如果没有则使用 requests
try:
    import httpx
    HTTP_CLIENT = "httpx"
except ImportError:
    try:
        import requests
        HTTP_CLIENT = "requests"
    except ImportError:
        HTTP_CLIENT = None


def get_api_key() -> Optional[str]:
    """获取 API Key"""
    return ANTHROPIC_API_KEY or os.environ.get('OPENAI_API_KEY')


def generate_answer(
    question: str,
    facts: List[Dict],
    max_tokens: int = 500,
    stream: bool = False,
    use_voice_profile: bool = True  # 仅 full 权限时为 True
):
    """
    使用 LLM 生成回答
    
    Args:
        question: 用户问题
        facts: 检索到的 facts 列表
        max_tokens: 最大生成 token 数
    
    Returns:
        生成的回答文本
    """
    if not facts:
        return "抱歉，在知识库中没有找到相关信息。"
    
    # 构建 context
    context_parts = []
    for i, fact in enumerate(facts, 1):
        fact_type = fact.get('content_type', '信息')
        summary = fact.get('summary', '')
        context_parts.append(f"[{fact_type}] {summary}")
    
    context_text = "\n".join(context_parts)
    
    # 尝试使用 LLM
    api_key = get_api_key()
    
    if api_key and HTTP_CLIENT:
        try:
            if stream:
                return _call_llm_stream(question, context_text, api_key, max_tokens, use_voice_profile)
            else:
                return _call_llm(question, context_text, api_key, max_tokens, use_voice_profile)
        except Exception as e:
            print(f"[LLM] API 调用失败: {e}")
            # 降级到结构化输出
    
    # 降级：返回结构化输出
    result = _structured_answer(question, facts, context_text)
    if stream:
        # 流式模式下返回生成器
        def fake_stream():
            yield result
        return fake_stream()
    return result


def _load_voice_profile() -> str:
    """加载认知画像"""
    voice_path = Path.home() / ".openclaw/workspace/MAX_VOICE.md"
    if voice_path.exists():
        content = voice_path.read_text()
        # 提取核心内容，跳过标题和元信息
        lines = []
        for line in content.split('\n'):
            if line.startswith('#') or line.startswith('_') or line.startswith('---'):
                continue
            if line.strip():
                lines.append(line)
        return '\n'.join(lines)
    return ""


def _call_llm(question: str, context: str, api_key: str, max_tokens: int, use_voice_profile: bool = True) -> str:
    """调用 Anthropic API"""
    
    voice_section = ""
    if use_voice_profile:
        voice_profile = _load_voice_profile()
        voice_section = f"""
回答风格参考（模拟知识库主人的表达习惯）：
{voice_profile}
""" if voice_profile else ""
    
    prompt = f"""基于以下知识库内容回答问题。请用简洁自然的语言回答，不要简单罗列，而是整合信息给出有洞察的回答。
{voice_section}
知识库内容：
{context}

问题：{question}

回答："""
    
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    data = {
        "model": "claude-3-haiku-20240307",  # 使用 Haiku 以控制成本
        "max_tokens": max_tokens,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    if HTTP_CLIENT == "httpx":
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            result = response.json()
    else:
        import requests
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
    
    # 提取回答
    if "content" in result and len(result["content"]) > 0:
        return result["content"][0].get("text", "")
    
    return _structured_answer(question, [], context)


def _call_llm_stream(question: str, context: str, api_key: str, max_tokens: int, use_voice_profile: bool = True):
    """调用 Anthropic API（流式）"""
    
    voice_section = ""
    if use_voice_profile:
        voice_profile = _load_voice_profile()
        voice_section = f"""
回答风格参考（模拟知识库主人的表达习惯）：
{voice_profile}
""" if voice_profile else ""
    
    prompt = f"""基于以下知识库内容回答问题。请用简洁自然的语言回答，不要简单罗列，而是整合信息给出有洞察的回答。
{voice_section}
知识库内容：
{context}

问题：{question}

回答："""
    
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    data = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": max_tokens,
        "stream": True,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    if HTTP_CLIENT == "httpx":
        import httpx
        with httpx.Client(timeout=60.0) as client:
            with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        try:
                            event_data = json.loads(line[6:])
                            if event_data.get("type") == "content_block_delta":
                                delta = event_data.get("delta", {})
                                if "text" in delta:
                                    yield delta["text"]
                        except json.JSONDecodeError:
                            continue
    else:
        import requests
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            stream=True,
            timeout=60
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith("data: "):
                    try:
                        event_data = json.loads(line[6:])
                        if event_data.get("type") == "content_block_delta":
                            delta = event_data.get("delta", {})
                            if "text" in delta:
                                yield delta["text"]
                    except json.JSONDecodeError:
                        continue


def _structured_answer(question: str, facts: List[Dict], context: str) -> str:
    """降级方案：结构化输出"""
    if not facts:
        return f"关于「{question}」，知识库中没有直接相关的记录。"
    
    lines = [f"关于「{question}」，知识库中有 {len(facts)} 条相关记录：\n"]
    
    for i, fact in enumerate(facts, 1):
        fact_type = fact.get('content_type', '信息')
        summary = fact.get('summary', '')
        lines.append(f"{i}. **[{fact_type}]** {summary}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 测试
    test_facts = [
        {"content_type": "观点", "summary": "日本货币政策容忍日元贬值"},
        {"content_type": "事件", "summary": "2024年日银干预汇市"}
    ]
    print(generate_answer("日元为什么贬值？", test_facts))
