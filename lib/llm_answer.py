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


def _call_openclaw_llm(prompt: str, max_tokens: int = 500) -> Optional[str]:
    """通过 OpenClaw Gateway 的 /v1/chat/completions 调用 LLM"""
    import json as json_module
    
    try:
        # 读取 OpenClaw 配置获取 gateway token
        config_path = Path.home() / ".openclaw/openclaw.json"
        if not config_path.exists():
            return None
        
        config = json_module.loads(config_path.read_text())
        gateway_token = config.get("gateway", {}).get("auth", {}).get("token", "")
        gateway_port = config.get("gateway", {}).get("port", 18789)
        
        if not gateway_token:
            logger.warning("OpenClaw Gateway token 未配置")
            return None
        
        # 调用 Gateway 的 chat completions API
        url = f"http://127.0.0.1:{gateway_port}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {gateway_token}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "openclaw",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        if HTTP_CLIENT == "httpx":
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, headers=headers, json=data)
                if response.status_code == 404:
                    logger.warning("OpenClaw chatCompletions 端点未启用")
                    return None
                response.raise_for_status()
                result = response.json()
        else:
            import requests
            response = requests.post(url, headers=headers, json=data, timeout=60)
            if response.status_code == 404:
                logger.warning("OpenClaw chatCompletions 端点未启用")
                return None
            response.raise_for_status()
            result = response.json()
        
        # 提取回答
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        
        return None
        
    except Exception as e:
        logger.warning(f"OpenClaw LLM 调用失败: {e}")
        return None


def _call_openclaw_llm_stream(prompt: str, max_tokens: int = 500):
    """通过 OpenClaw Gateway 流式调用 LLM"""
    import json as json_module
    
    try:
        config_path = Path.home() / ".openclaw/openclaw.json"
        if not config_path.exists():
            return
        
        config = json_module.loads(config_path.read_text())
        gateway_token = config.get("gateway", {}).get("auth", {}).get("token", "")
        gateway_port = config.get("gateway", {}).get("port", 18789)
        
        if not gateway_token:
            return
        
        url = f"http://127.0.0.1:{gateway_port}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {gateway_token}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "openclaw",
            "max_tokens": max_tokens,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        if HTTP_CLIENT == "httpx":
            with httpx.Client(timeout=120.0) as client:
                with client.stream("POST", url, headers=headers, json=data) as response:
                    if response.status_code == 404:
                        return
                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                event = json_module.loads(data_str)
                                delta = event.get("choices", [{}])[0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                            except:
                                continue
        else:
            import requests
            response = requests.post(url, headers=headers, json=data, stream=True, timeout=120)
            if response.status_code == 404:
                return
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            event = json_module.loads(data_str)
                            delta = event.get("choices", [{}])[0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except:
                            continue
    except Exception as e:
        logger.warning(f"OpenClaw LLM 流式调用失败: {e}")


def generate_answer(
    question: str,
    facts: List[Dict],
    max_tokens: int = 500,
    stream: bool = False,
    use_voice_profile: bool = True,  # 仅 full 权限时为 True
    namespace: str = "default"  # 新增：namespace 参数
):
    """
    使用 LLM 生成回答
    
    Args:
        question: 用户问题
        facts: 检索到的 facts 列表
        max_tokens: 最大生成 token 数
        namespace: 知识库 namespace，用于加载对应的 persona
    
    Returns:
        生成的回答文本
    """
    if not facts:
        # 如果是角色，返回角色风格的"不知道"
        persona = _load_persona(namespace)
        if persona:
            return f"吾之所知有限，关于此事，尚无记载。"
        return "抱歉，在知识库中没有找到相关信息。"
    
    # 构建 context
    context_parts = []
    for i, fact in enumerate(facts, 1):
        fact_type = fact.get('content_type', '信息')
        summary = fact.get('summary', '')
        context_parts.append(f"[{fact_type}] {summary}")
    
    context_text = "\n".join(context_parts)
    
    # 尝试使用 LLM（优先 OpenClaw Gateway，降级到 Anthropic API）
    api_key = get_api_key()
    
    if HTTP_CLIENT:  # 只要有 HTTP 客户端就尝试（OpenClaw Gateway 不需要 api_key）
        try:
            if stream:
                return _call_llm_stream(question, context_text, api_key, max_tokens, use_voice_profile, namespace)
            else:
                return _call_llm(question, context_text, api_key, max_tokens, use_voice_profile, namespace)
        except Exception as e:
            print(f"[LLM] API 调用失败: {e}")
            # 降级到结构化输出
    
    # 降级：返回结构化输出（带 persona）
    result = _structured_answer(question, facts, context_text, namespace)
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


def _load_persona(namespace: str) -> Optional[Dict]:
    """加载 namespace 的 persona 配置"""
    if namespace == "default":
        return None
    
    try:
        from profile_manager import ProfileManager
        pm = ProfileManager()
        config = pm.load_profile_config(namespace)
        if config and config.get("type") == "character":
            return config.get("persona", {})
    except Exception as e:
        logger.warning(f"加载 persona 失败: {e}")
    
    return None


def _build_persona_prompt(persona: Dict) -> str:
    """构建 persona 系统提示"""
    if not persona:
        return ""
    
    parts = []
    
    # 基本身份
    based_on = persona.get("based_on", [])
    if based_on:
        parts.append(f"你是 {', '.join(based_on)}。")
    
    era = persona.get("era", "")
    if era:
        parts.append(f"你生活在{era}。")
    
    # 背景
    background = persona.get("background", "")
    if background:
        parts.append(f"\n背景：{background}")
    
    # 性格
    traits = persona.get("traits", [])
    if traits:
        parts.append(f"\n性格特征：{', '.join(traits)}")
    
    # 说话风格（最重要）
    speaking_style = persona.get("speaking_style", "")
    if speaking_style:
        parts.append(f"\n说话风格：{speaking_style}")
    
    # 核心信念
    core_beliefs = persona.get("core_beliefs", [])
    if core_beliefs:
        parts.append(f"\n核心信念：")
        for belief in core_beliefs[:3]:
            parts.append(f"- {belief}")
    
    return "\n".join(parts)


def _call_llm(question: str, context: str, api_key: str, max_tokens: int, use_voice_profile: bool = True, namespace: str = "default") -> str:
    """调用 LLM（优先使用 OpenClaw Gateway，降级到 Anthropic API）"""
    
    # 构建 prompt
    persona = _load_persona(namespace)
    
    if persona:
        # 角色模式：使用 persona prompt
        persona_prompt = _build_persona_prompt(persona)
        prompt = f"""{persona_prompt}

现在有人向你请教问题。请以你的身份和风格回答，要符合你的性格和说话方式。

你的知识库中有以下相关内容：
{context}

问题：{question}

请用你的风格回答（保持角色一致性，不要跳出角色）："""
    else:
        # 普通模式：使用 voice profile
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
    
    # 优先尝试 OpenClaw Gateway
    openclaw_result = _call_openclaw_llm(prompt, max_tokens)
    if openclaw_result:
        return openclaw_result
    
    # 降级到直接调用 Anthropic API
    if not api_key:
        return _structured_answer(question, [], context, namespace)
    
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    data = {
        "model": "claude-3-haiku-20240307",
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
    
    return _structured_answer(question, [], context, namespace)


def _call_llm_stream(question: str, context: str, api_key: str, max_tokens: int, use_voice_profile: bool = True, namespace: str = "default"):
    """调用 LLM（流式，优先使用 OpenClaw Gateway）"""
    
    # 构建 prompt
    persona = _load_persona(namespace)
    
    if persona:
        # 角色模式
        persona_prompt = _build_persona_prompt(persona)
        prompt = f"""{persona_prompt}

现在有人向你请教问题。请以你的身份和风格回答，要符合你的性格和说话方式。

你的知识库中有以下相关内容：
{context}

问题：{question}

请用你的风格回答（保持角色一致性，不要跳出角色）："""
    else:
        # 普通模式
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
    
    # 优先尝试 OpenClaw Gateway 流式
    has_output = False
    for chunk in _call_openclaw_llm_stream(prompt, max_tokens):
        has_output = True
        yield chunk
    
    if has_output:
        return
    
    # 降级到 Anthropic API
    if not api_key:
        yield _structured_answer(question, [], context, namespace)
        return
    
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


def _structured_answer(question: str, facts: List[Dict], context: str, namespace: str = "default") -> str:
    """降级方案：结构化输出（带 persona 风格）"""
    persona = _load_persona(namespace)
    
    if not facts:
        if persona:
            return "吾之所知有限，关于此事，尚无记载。"
        return f"关于「{question}」，知识库中没有直接相关的记录。"
    
    # 如果是角色模式，尝试用角色风格返回
    if persona:
        # 简单模式：列出相关内容，加上角色风格的引导语
        speaking_style = persona.get("speaking_style", "")
        based_on = persona.get("based_on", [])
        role_name = based_on[0] if based_on else "吾"
        
        lines = [f"关于此问，{role_name}有以下见解：\n"]
        for i, fact in enumerate(facts, 1):
            summary = fact.get('summary', '')
            lines.append(f"「{summary}」")
        return "\n".join(lines)
    
    # 普通模式
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
