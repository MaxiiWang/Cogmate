#!/usr/bin/env python3
"""
Intent Handler - 意图处理层
============================
根据 SPEC.md 规范处理 STORE/QUERY/AMBIGUOUS 意图

使用:
    from intent_handler import IntentHandler
    handler = IntentHandler()
    
    # 自动识别意图并处理
    response = handler.process("我之前对MES系统的判断是什么？")
    
    # 指定意图处理
    response = handler.handle_query("MES系统")
    response = handler.handle_store("今天客户说系统太难用了")
"""

import re
from typing import Dict, Any, Optional, Tuple, List
from brain_core import BrainAgent


class IntentHandler:
    """意图处理器"""
    
    # 检索信号词
    QUERY_SIGNALS = [
        "是什么", "为什么", "怎么", "有没有", "之前", "上次",
        "什么时候", "哪些", "多少", "如何", "？", "?",
        "记得", "记录", "说过", "提到", "关于"
    ]
    
    # 存储信号词（陈述性）
    STORE_SIGNALS = [
        "今天", "刚刚", "决定", "发现", "觉得", "认为",
        "读完", "看完", "听说", "了解到"
    ]
    
    # /why 自动触发信号词
    WHY_SIGNALS = [
        "为什么我", "为什么会", "什么原因", "怎么会",
        "原因是什么", "为何", "何以", "缘由"
    ]
    
    # /decide 自动触发信号词
    DECIDE_SIGNALS = [
        "该不该", "要不要", "应不应该", "选A还是B", "选择",
        "纠结", "犹豫", "两难", "怎么选", "如何抉择",
        "利弊", "权衡", "做还是不做"
    ]
    
    def __init__(self):
        self.brain = BrainAgent()
    
    def classify_intent(self, text: str) -> Tuple[str, float]:
        """
        识别意图
        
        Returns:
            (intent, confidence): STORE/QUERY/QUERY_WHY/QUERY_DECIDE/AMBIGUOUS, 置信度 0-1
        """
        text_lower = text.lower()
        
        # 检查是否包含检索信号词
        query_score = sum(1 for s in self.QUERY_SIGNALS if s in text)
        store_score = sum(1 for s in self.STORE_SIGNALS if s in text)
        
        # 检查 /why 信号
        why_score = sum(1 for s in self.WHY_SIGNALS if s in text)
        
        # 检查 /decide 信号
        decide_score = sum(1 for s in self.DECIDE_SIGNALS if s in text)
        
        # 疑问句强信号
        if text.endswith("？") or text.endswith("?"):
            query_score += 2
        
        # 短文本（<10字）且无明确信号 → AMBIGUOUS
        if len(text) < 10 and query_score == 0 and store_score == 0:
            return ("AMBIGUOUS", 0.5)
        
        # 优先检查 WHY 和 DECIDE（更具体的意图）
        if why_score > 0 and why_score >= decide_score:
            confidence = min(0.9, 0.6 + why_score * 0.1)
            return ("QUERY_WHY", confidence)
        
        if decide_score > 0:
            confidence = min(0.9, 0.6 + decide_score * 0.1)
            return ("QUERY_DECIDE", confidence)
        
        # 一般查询判断
        if query_score > store_score:
            confidence = min(0.9, 0.5 + query_score * 0.1)
            return ("QUERY", confidence)
        elif store_score > query_score:
            confidence = min(0.9, 0.5 + store_score * 0.1)
            return ("STORE", confidence)
        else:
            return ("AMBIGUOUS", 0.5)
    
    def process(self, text: str) -> str:
        """
        自动识别意图并处理
        
        Args:
            text: 用户输入
        
        Returns:
            格式化的响应文本
        """
        intent, confidence = self.classify_intent(text)
        
        # 记录最后识别的意图（供调试）
        self._last_intent = (intent, confidence)
        
        if intent == "QUERY_WHY":
            return self.handle_why(text)
        elif intent == "QUERY_DECIDE":
            return self.handle_decide(text)
        elif intent == "QUERY":
            return self.handle_query(text)
        elif intent == "STORE":
            return self.handle_store(text)
        else:  # AMBIGUOUS
            return self.handle_ambiguous(text)
    
    def handle_query(self, query_text: str, top_k: int = 5) -> str:
        """
        处理 QUERY 意图
        
        输出格式（按 SPEC）:
        🔍 [查询主题]
        
        📌 [FACT#XXX] [日期] [摘要]
        
        🕸️ 图谱关联：FACT#XXX -[关系]→ FACT#YYY
        
        💡 知识库结果有限，需要搜索外部资料吗？（如结果不足）
        """
        results = self.brain.query(query_text, top_k=top_k, min_score=0.5)
        
        lines = [f"🔍 「{query_text}」\n"]
        
        # 向量检索结果
        if results["vector_results"]:
            lines.append("── 语义匹配 ──")
            for r in results["vector_results"]:
                short_id = r["fact_id"][:8]
                ts = r.get("timestamp", "")[:10] if r.get("timestamp") else ""
                content_type = r.get("content_type", "")
                emotion = r.get("emotion_tag", "")
                
                # 主行
                lines.append(f"📌 [{short_id}] {ts} | {content_type}")
                lines.append(f"   {r['summary']}")
                
                # 情境（如有）
                if r.get("context"):
                    lines.append(f"   情境: {r['context']}")
                
                # 相似度
                lines.append(f"   相似度: {r['score']:.2f}")
                lines.append("")
        else:
            lines.append("📭 知识库中暂无相关内容。")
            lines.append("")
        
        # 图谱关联
        if results["graph_results"]:
            lines.append("── 图谱关联 ──")
            seen_relations = set()
            for rel in results["graph_results"]:
                from_id = rel["from_id"][:8]
                to_id = rel["to_id"][:8]
                rel_type = rel.get("relation_type", "RELATES_TO")
                conf = rel.get("confidence", "?")
                
                # 去重
                rel_key = f"{from_id}-{to_id}"
                if rel_key in seen_relations:
                    continue
                seen_relations.add(rel_key)
                
                # 矛盾关系特殊标记
                if rel_type in ["矛盾", "CONTRADICTION"]:
                    lines.append(f"⚠️ {from_id} -[{rel_type}, 置信:{conf}]→ {to_id}")
                else:
                    lines.append(f"🕸️ {from_id} -[{rel_type}, 置信:{conf}]→ {to_id}")
            lines.append("")
        
        # 结果不足标记（供上层判断是否需要网络搜索）
        total = results["total"]
        self._last_query_sufficient = total >= 3
        
        if total == 0:
            lines.append("📭 知识库无相关记录")
        elif total < 3:
            lines.append("💡 知识库结果有限")
        
        return "\n".join(lines)
    
    def handle_why(self, question: str) -> str:
        """
        处理 QUERY_WHY 意图 - 自动调用 /why 逻辑
        从知识库寻找决策依据，含图谱路径推理
        """
        from commands import CommandHandler
        cmd_handler = CommandHandler()
        result = cmd_handler.cmd_why(question)
        
        if result["success"]:
            return f"[自动识别为「为什么」类问题]\n\n{result['result']}"
        else:
            # fallback 到普通查询
            return self.handle_query(question)
    
    def handle_decide(self, question: str) -> str:
        """
        处理 QUERY_DECIDE 意图 - 自动调用 /decide 逻辑
        决策辅助，正反证据双向呈现
        """
        from commands import CommandHandler
        cmd_handler = CommandHandler()
        result = cmd_handler.cmd_decide(question)
        
        if result["success"]:
            return f"[自动识别为决策类问题]\n\n{result['result']}"
        else:
            # fallback 到普通查询
            return self.handle_query(question)
    
    def needs_web_search(self) -> bool:
        """检查上次查询是否需要网络搜索补充"""
        return not getattr(self, '_last_query_sufficient', True)
    
    def handle_store(
        self,
        content: str,
        content_type: Optional[str] = None,
        emotion_tag: Optional[str] = None,
        context: Optional[str] = None
    ) -> str:
        """
        处理 STORE 意图
        
        输出格式（按 SPEC - 简洁）:
        ✅ [一句话摘要]
        🔗 与 FACT#XXX 相关，是否确认关联？（如发现关联）
        """
        # 自动推断内容类型
        if content_type is None:
            content_type = self._infer_content_type(content)
        
        # 自动推断情绪
        if emotion_tag is None:
            emotion_tag = self._infer_emotion(content)
        
        # 存储
        fact_id = self.brain.store(
            content=content,
            content_type=content_type,
            emotion_tag=emotion_tag,
            context=context
        )
        
        short_id = fact_id[:8]
        
        # 简洁确认
        lines = [f"✅ {content[:50]}{'...' if len(content) > 50 else ''}"]
        lines.append(f"   [{short_id}] {content_type} | {emotion_tag}")
        
        # 查找关联候选
        similar = self.brain.find_similar(fact_id, top_k=3)
        high_similar = [s for s in similar if s["score"] > 0.7]
        
        if high_similar:
            top = high_similar[0]
            top_id = top["fact_id"][:8]
            lines.append(f"\n🔗 与 [{top_id}] 相关（{top['score']:.2f}）")
            lines.append(f"   「{top['summary'][:40]}...」")
            lines.append("   确认关联？")
        
        return "\n".join(lines)
    
    def handle_ambiguous(self, text: str) -> str:
        """
        处理 AMBIGUOUS 意图
        先检索，有结果则呈现，无结果则引导存储
        """
        results = self.brain.query(text, top_k=3, min_score=0.5)
        
        if results["total"] > 0:
            # 有结果，按 QUERY 处理，但追加存储提示
            response = self.handle_query(text, top_k=3)
            response += "\n---\n这也是你想记录的新内容吗？回复「记录」可存入。"
            return response
        else:
            # 无结果，引导存储
            lines = [
                f"🔍 「{text}」",
                "",
                "📭 知识库中暂无相关内容。",
                "",
                "这是你想记录的新观察吗？",
                "回复「记录」存入，或补充更多内容后再发。"
            ]
            return "\n".join(lines)
    
    def _infer_content_type(self, content: str) -> str:
        """推断内容类型"""
        # 决策信号
        if any(w in content for w in ["决定", "选择", "打算", "计划"]):
            return "决策"
        # 情绪信号
        if any(w in content for w in ["感觉", "心情", "开心", "难过", "焦虑", "兴奋"]):
            return "情绪"
        # 事件信号（时间词）
        if any(w in content for w in ["今天", "昨天", "刚刚", "上周", "发生"]):
            return "事件"
        # 资讯信号
        if any(w in content for w in ["据说", "报道", "数据显示", "研究表明"]):
            return "资讯"
        # 默认观点
        return "观点"
    
    def _infer_emotion(self, content: str) -> str:
        """推断情绪标签"""
        positive = ["好", "棒", "成功", "开心", "兴奋", "满意", "喜欢"]
        negative = ["差", "糟", "失败", "难过", "焦虑", "担心", "讨厌", "问题"]
        confused = ["不懂", "困惑", "奇怪", "为什么", "不确定"]
        
        pos_count = sum(1 for w in positive if w in content)
        neg_count = sum(1 for w in negative if w in content)
        conf_count = sum(1 for w in confused if w in content)
        
        if conf_count > 0:
            return "困惑"
        if pos_count > neg_count:
            return "积极"
        if neg_count > pos_count:
            return "消极"
        return "中性"


# CLI 测试
if __name__ == "__main__":
    import sys
    
    handler = IntentHandler()
    
    if len(sys.argv) < 2:
        print("Usage: python intent_handler.py <text>")
        print("       python intent_handler.py --classify <text>")
        sys.exit(1)
    
    if sys.argv[1] == "--classify":
        text = " ".join(sys.argv[2:])
        intent, conf = handler.classify_intent(text)
        print(f"意图: {intent} (置信度: {conf:.2f})")
    else:
        text = " ".join(sys.argv[1:])
        print(handler.process(text))
