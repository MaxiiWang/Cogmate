"""
Simulation React Module
=======================
处理来自 CogNexus 的 Simulation 采访请求

功能:
1. 接收 Simulation 问题（narrative / predictive）
2. 从本地知识库检索相关知识
3. 加载 Agent persona/voice
4. 通过 LLM 生成角色化回应
5. 返回结构化结果
"""

import json
import re
from typing import List, Dict, Optional, Any
from pathlib import Path

from config import setup_logging
from cogmate_core import CogmateAgent

logger = setup_logging("sim_react")


def _load_system_prompt(namespace: str) -> str:
    """加载 Agent 的系统提示（persona 或 voice profile）"""
    try:
        from profile_manager import ProfileManager
        pm = ProfileManager()
        config = pm.load_profile_config(namespace)

        if config and config.get("type") == "character":
            # Character Agent: 使用 persona
            persona = config.get("persona", {})
            identity = config.get("identity", {})
            return _build_character_prompt(identity, persona)
        else:
            # Human Agent: 使用 voice profile
            return _build_human_prompt(namespace)
    except Exception as e:
        logger.warning(f"加载系统提示失败: {e}")
        return "你是一个知识代理，基于你的知识库给出客观分析和判断。"


def _build_character_prompt(identity: Dict, persona: Dict) -> str:
    """构建 Character Agent 的系统提示"""
    parts = []

    name = identity.get("name", "")
    title = identity.get("title", "")
    if name:
        parts.append(f"你是{name}。")
    if title:
        parts.append(f"身份：{title}")

    based_on = persona.get("based_on", [])
    if based_on:
        parts.append(f"原型：{', '.join(based_on)}")

    era = persona.get("era", "")
    if era:
        parts.append(f"时代：{era}")

    background = persona.get("background", "")
    if background:
        parts.append(f"背景：{background}")

    traits = persona.get("traits", [])
    if traits:
        parts.append(f"性格：{', '.join(traits)}")

    speaking_style = persona.get("speaking_style", "")
    if speaking_style:
        parts.append(f"说话风格：{speaking_style}")

    core_beliefs = persona.get("core_beliefs", [])
    if core_beliefs:
        parts.append("核心信念：" + "；".join(core_beliefs[:5]))

    parts.append("\n请始终以你的身份和风格回应，保持角色一致性。")

    return "\n".join(parts)


def _build_human_prompt(namespace: str) -> str:
    """构建 Human Agent 的系统提示"""
    # 尝试加载 voice profile
    voice_path = Path.home() / ".openclaw/workspace/MAX_VOICE.md"
    voice_content = ""
    if voice_path.exists():
        try:
            raw = voice_path.read_text()
            lines = [l for l in raw.split('\n')
                     if l.strip() and not l.startswith('#') and not l.startswith('_') and not l.startswith('---')]
            voice_content = '\n'.join(lines)
        except:
            pass

    if voice_content:
        return (
            "你是一个个人知识代理，代表你的 owner 进行分析和判断。\n"
            f"Owner 的思维风格：\n{voice_content}\n\n"
            "请基于知识库内容，用符合 owner 思维风格的方式回应。"
        )
    else:
        return "你是一个个人知识代理，基于知识库内容进行客观分析和判断。"


def _build_api_url(base_url: str) -> str:
    """根据不同 provider 构建 chat completions URL"""
    base = base_url.rstrip('/')
    if '/chat/completions' in base:
        return base
    elif base.endswith('/api/v3') or base.endswith('/v1'):
        return f"{base}/chat/completions"
    else:
        return f"{base}/v1/chat/completions"


def _call_external_llm(base_url: str, api_key: str, model: str,
                       system: str, user: str, max_tokens: int = 800) -> Optional[str]:
    """调用外部 LLM API（支持 OpenAI 兼容接口）"""
    import httpx
    api_url = _build_api_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
    return None


def _call_llm(system: str, user: str, max_tokens: int = 800, namespace: str = "default") -> Optional[str]:
    """
    调用 LLM，优先级:
    1. Profile LLM 配置（config/profiles/{ns}.json 中的 llm 字段）
    2. 环境变量（LLM_BASE_URL, LLM_API_KEY, LLM_MODEL）
    3. OpenClaw Gateway（fallback）
    """
    import os

    # 1. 优先使用 Profile 的 LLM 配置
    try:
        from profile_manager import ProfileManager
        pm = ProfileManager()
        config = pm.load_profile_config(namespace)
        if config and config.get("llm"):
            llm = config["llm"]
            if llm.get("base_url") and llm.get("api_key") and llm.get("model"):
                result = _call_external_llm(llm["base_url"], llm["api_key"], llm["model"], system, user, max_tokens)
                if result:
                    return result
    except Exception as e:
        logger.warning(f"Profile LLM 配置调用失败: {e}")

    # 2. 环境变量配置的外部 LLM
    ext_base = os.environ.get("LLM_BASE_URL")
    ext_key = os.environ.get("LLM_API_KEY")
    ext_model = os.environ.get("LLM_MODEL")

    if ext_base and ext_key and ext_model:
        try:
            result = _call_external_llm(ext_base, ext_key, ext_model, system, user, max_tokens)
            if result:
                return result
        except Exception as e:
            logger.error(f"外部 LLM 调用失败: {e}")

    # 3. Fallback: OpenClaw Gateway
    try:
        config_path = Path.home() / ".openclaw/openclaw.json"
        if not config_path.exists():
            return None

        config = json.loads(config_path.read_text())
        gateway_token = config.get("gateway", {}).get("auth", {}).get("token", "")
        gateway_port = config.get("gateway", {}).get("port", 18789)

        if not gateway_token:
            return None

        url = f"http://127.0.0.1:{gateway_port}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {gateway_token}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "openclaw",
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        }

        try:
            import httpx
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()
                choices = result.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except ImportError:
            import requests
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            result = response.json()
            choices = result.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")

        return None
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return None


def _extract_key_points(text: str, namespace: str = "default") -> List[str]:
    """从文本中提取关键点（简单规则 + LLM fallback）"""
    # 尝试 LLM 提取
    result = _call_llm(
        system="从以下文本中提取 3-5 个关键要点，每个要点一行。只返回要点列表，不需要其他文字。",
        user=text,
        max_tokens=200,
        namespace=namespace
    )
    if result:
        points = [
            line.strip().lstrip("•-·123456789.、）) ")
            for line in result.strip().split('\n')
            if line.strip() and len(line.strip()) > 2
        ]
        if points:
            return points[:5]

    # Fallback: 按句子切分取前 3 个有意义的
    sentences = re.split(r'[。！？\n]', text)
    points = [s.strip() for s in sentences if len(s.strip()) > 10][:3]
    return points if points else [text[:100]]


def _detect_sentiment(text: str) -> str:
    """简单情感检测"""
    positive_words = {"支持", "赞成", "乐观", "积极", "利好", "看好", "有利"}
    negative_words = {"反对", "悲观", "消极", "利空", "看空", "担忧", "风险"}

    pos = sum(1 for w in positive_words if w in text)
    neg = sum(1 for w in negative_words if w in text)

    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    elif pos > 0 and neg > 0:
        return "mixed"
    return "neutral"


def _parse_prediction(text: str) -> Dict:
    """从回应中解析 PREDICTION JSON"""
    # 尝试找 ---PREDICTION--- 标记
    if "---PREDICTION---" in text:
        parts = text.split("---PREDICTION---")
        full_text = parts[0].strip()
        pred_text = parts[1].strip()
    else:
        # 尝试找最后一个 JSON block
        full_text = text
        pred_text = text

    # 提取 JSON
    json_match = re.search(r'\{[^{}]*"stance"[^{}]*\}', pred_text, re.DOTALL)
    if json_match:
        try:
            prediction = json.loads(json_match.group())
            return {
                "full_text": full_text if full_text != text else text.replace(json_match.group(), "").strip(),
                "stance": prediction.get("stance", ""),
                "confidence": float(prediction.get("confidence", 0.5)),
                "brief_reasoning": prediction.get("brief_reasoning", "")
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: 无法解析
    return {
        "full_text": text,
        "stance": "",
        "confidence": 0.3,
        "brief_reasoning": "无法解析预测结果"
    }


def react_narrative(
    prompt: str,
    namespace: str = "default",
    description: str = "",
    previous_context: str = ""
) -> Dict[str, Any]:
    """
    叙事型反应：生成自由文本回应

    返回: {prompt_type, response_text, key_points, sentiment, knowledge_depth}
    """
    cogmate = CogmateAgent(namespace=namespace)

    # 搜索相关知识
    results = cogmate.query(prompt, top_k=10, min_score=0.4)
    relevant_facts = results.get("vector_results", [])

    facts_context = "\n".join([
        f"- {f['summary']} (相关度: {f['score']:.2f})"
        for f in relevant_facts[:8]
    ])

    system_prompt = _load_system_prompt(namespace)

    from datetime import datetime as _dt
    now_str = _dt.now().strftime("%Y年%m月%d日")

    user_prompt = f"""当前日期: {now_str}

{prompt}

背景信息:
{description}

前序发展:
{previous_context if previous_context else "（无）"}

你的相关知识:
{facts_context if facts_context else "（无直接相关知识）"}

请以你的身份和视角做出回应。注意基于当前日期和你的知识做判断，不要使用过时的数据。"""

    response = _call_llm(system=system_prompt, user=user_prompt, max_tokens=800, namespace=namespace)

    if not response:
        response = f"基于已有知识，我对此的看法是：{'、'.join([f['summary'][:30] for f in relevant_facts[:3]])}" if relevant_facts else "关于这个问题，我暂时没有足够的信息来做出判断。"

    key_points = _extract_key_points(response, namespace=namespace)
    sentiment = _detect_sentiment(response)

    return {
        "prompt_type": "narrative",
        "response_text": response,
        "key_points": key_points,
        "sentiment": sentiment,
        "knowledge_depth": len(relevant_facts)
    }


def react_predictive(
    prompt: str,
    namespace: str = "default",
    description: str = "",
    outcome_options: List[str] = None,
    previous_context: str = ""
) -> Dict[str, Any]:
    """
    预测型反应：生成结构化立场 + 置信度

    返回: {prompt_type, response_text, stance, confidence, brief_reasoning, knowledge_depth}
    """
    if outcome_options is None:
        outcome_options = ["yes", "no"]

    cogmate = CogmateAgent(namespace=namespace)

    # 搜索相关知识
    results = cogmate.query(prompt, top_k=10, min_score=0.4)
    relevant_facts = results.get("vector_results", [])

    facts_context = "\n".join([
        f"- {f['summary']} (相关度: {f['score']:.2f})"
        for f in relevant_facts[:8]
    ])

    system_prompt = _load_system_prompt(namespace)
    options_str = " / ".join(outcome_options)

    from datetime import datetime as _dt
    now_str = _dt.now().strftime("%Y年%m月%d日")

    user_prompt = f"""当前日期: {now_str}

{prompt}

背景信息:
{description}

前序发展:
{previous_context if previous_context else "（无）"}

你的相关知识:
{facts_context if facts_context else "（无直接相关知识）"}

请基于当前日期和你的知识进行分析，不要使用过时的数据。先简要说明你的分析，然后给出预测:

---PREDICTION---
{{
  "stance": "<{options_str}>",
  "confidence": <0.0-1.0>,
  "brief_reasoning": "<一句话理由>"
}}"""

    response = _call_llm(system=system_prompt, user=user_prompt, max_tokens=800, namespace=namespace)

    if not response:
        # Fallback: 默认回应
        return {
            "prompt_type": "predictive",
            "response_text": "无法生成预测分析。",
            "stance": outcome_options[0],
            "confidence": 0.1,
            "brief_reasoning": "LLM 不可用，默认低置信度回应",
            "knowledge_depth": len(relevant_facts)
        }

    parsed = _parse_prediction(response)

    # 验证 stance 在选项中
    if parsed["stance"] not in outcome_options:
        # 尝试模糊匹配
        for opt in outcome_options:
            if opt.lower() in parsed["stance"].lower() or parsed["stance"].lower() in opt.lower():
                parsed["stance"] = opt
                break
        else:
            parsed["stance"] = outcome_options[0]
            parsed["confidence"] = min(parsed["confidence"], 0.2)

    parsed["confidence"] = max(0.0, min(1.0, parsed["confidence"]))

    return {
        "prompt_type": "predictive",
        "response_text": parsed["full_text"],
        "stance": parsed["stance"],
        "confidence": parsed["confidence"],
        "brief_reasoning": parsed["brief_reasoning"],
        "knowledge_depth": len(relevant_facts)
    }


def react(
    prompt: str,
    prompt_type: str = "predictive",
    namespace: str = "default",
    description: str = "",
    outcome_options: List[str] = None,
    previous_context: str = ""
) -> Dict[str, Any]:
    """
    统一入口: 根据 prompt_type 路由到对应处理函数
    """
    if prompt_type == "narrative":
        return react_narrative(
            prompt=prompt,
            namespace=namespace,
            description=description,
            previous_context=previous_context
        )
    else:
        return react_predictive(
            prompt=prompt,
            namespace=namespace,
            description=description,
            outcome_options=outcome_options,
            previous_context=previous_context
        )
