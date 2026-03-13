#!/usr/bin/env python3
"""
Brain Agent CLI - 简化命令行接口
================================

快速操作:
    # 自动处理（推荐）
    brain process "我之前对MES系统的判断是什么？"
    brain process "今天客户说系统太难用了"
    
    # 存储（自动识别类型）
    brain store "今天客户说系统太难用了"
    brain store "决定暂缓投资黄金" --type 决策
    
    # 检索
    brain query "客户反馈"
    brain query "投资决策" --top 10
    
    # 状态
    brain stats
    brain list
    
    # 关联
    brain relate <fact_id1> <fact_id2> --type 支持
    brain similar <fact_id>
"""

import argparse
import json
import sys
from brain_core import BrainAgent
from intent_handler import IntentHandler
from privacy import (
    set_fact_private, set_abstract_private, get_privacy_status,
    list_private_entities, get_privacy_stats
)
from visual_token import generate_token, list_tokens, revoke_token, get_visual_url, SCOPE_LABELS


def cmd_store(args):
    """存储新事实"""
    brain = BrainAgent()
    fact_id = brain.store(
        content=args.content,
        content_type=args.type,
        emotion_tag=args.emotion,
        context=args.context,
        source_type=args.source,
        source_url=args.url,
        valid_until=getattr(args, 'valid_until', None),
        temporal_type=getattr(args, 'temporal', 'permanent')
    )
    
    short_id = fact_id[:8]
    temporal_label = {"permanent": "永久", "time_bound": "时效", "historical": "历史", "prediction": "预测"}.get(args.temporal, "")
    valid_str = f" | 有效至: {args.valid_until}" if getattr(args, 'valid_until', None) else ""
    print(f"✅ {args.content[:40]}{'...' if len(args.content) > 40 else ''}")
    print(f"   ID: {short_id} | 类型: {args.type} | 情绪: {args.emotion} | 时态: {temporal_label}{valid_str}")
    
    # 查找相似内容提示关联
    similar = brain.find_similar(fact_id, top_k=3)
    if similar:
        print(f"\n🔗 可能相关:")
        for s in similar:
            print(f"   [{s['score']:.2f}] {s['summary'][:50]}...")


def cmd_query(args):
    """检索知识库"""
    brain = BrainAgent()
    results = brain.query(
        query_text=args.text,
        top_k=args.top,
        min_score=args.min_score,
        include_graph=not args.no_graph
    )
    
    print(f"🔍 「{args.text}」")
    print(f"   找到 {results['total']} 条相关记录\n")
    
    if not results["vector_results"]:
        print("   (无结果)")
        return
    
    print("── 语义匹配 ──")
    for r in results["vector_results"]:
        short_id = r["fact_id"][:8]
        ts = r["timestamp"][:10] if r.get("timestamp") else "N/A"
        print(f"📌 [{short_id}] {ts} | {r['content_type']}")
        print(f"   {r['summary']}")
        if r.get("context"):
            print(f"   情境: {r['context']}")
        print()
    
    if results["graph_results"]:
        print("── 图谱关联 ──")
        for rel in results["graph_results"]:
            from_id = rel["from_id"][:8]
            to_id = rel["to_id"][:8]
            conf = rel.get("confidence", "?")
            print(f"🕸️ {from_id} -[{rel['relation_type']}, 置信:{conf}]→ {to_id}")


def cmd_stats(args):
    """显示统计信息"""
    brain = BrainAgent()
    stats = brain.stats()
    
    print("📊 知识库状态")
    print(f"   总事实数: {stats['total_facts']}")
    print(f"   图谱节点: {stats['graph_nodes']}")
    print(f"   图谱关联: {stats['graph_edges']}")
    
    if stats["by_type"]:
        print("\n   按类型:")
        for t, c in stats["by_type"].items():
            print(f"   · {t}: {c}")


def cmd_list(args):
    """列出最近的事实"""
    brain = BrainAgent()
    facts = brain.list_facts(limit=args.limit, offset=args.offset)
    
    print(f"📋 最近 {len(facts)} 条记录\n")
    
    for f in facts:
        short_id = f["fact_id"][:8]
        ts = f["timestamp"][:10] if f.get("timestamp") else "N/A"
        print(f"[{short_id}] {ts} | {f['content_type']} | {f['emotion_tag']}")
        print(f"   {f['summary']}")
        print()


def cmd_relate(args):
    """创建关联"""
    brain = BrainAgent()
    success = brain.create_relation(
        from_fact_id=args.from_id,
        to_fact_id=args.to_id,
        relation_type=args.type.upper(),
        confidence=args.confidence,
        created_by="manual"
    )
    
    if success:
        print(f"✅ 已创建关联: {args.from_id[:8]} -[{args.type}]→ {args.to_id[:8]}")
    else:
        print("❌ 创建失败，请检查 fact_id 是否存在")


def cmd_similar(args):
    """查找相似事实"""
    brain = BrainAgent()
    similar = brain.find_similar(args.fact_id, top_k=args.top)
    
    if not similar:
        print("未找到相似内容")
        return
    
    print(f"🔗 与 {args.fact_id[:8]} 相似的内容:\n")
    for s in similar:
        short_id = s["fact_id"][:8]
        print(f"   [{s['score']:.2f}] {short_id}")
        print(f"   {s['summary'][:60]}...")
        print()


def cmd_process(args):
    """自动识别意图并处理"""
    handler = IntentHandler()
    
    # 显示识别的意图
    intent, conf = handler.classify_intent(args.text)
    print(f"[意图: {intent} ({conf:.0%})]\n")
    
    # 处理
    result = handler.process(args.text)
    print(result)


def cmd_classify(args):
    """仅识别意图，不执行"""
    handler = IntentHandler()
    intent, conf = handler.classify_intent(args.text)
    print(f"意图: {intent}")
    print(f"置信度: {conf:.0%}")


def cmd_private(args):
    """设置实体为私有"""
    entity_id = args.entity_id
    
    # 先检查是什么类型
    status = get_privacy_status(entity_id)
    if not status:
        print(f"❌ 未找到: {entity_id}")
        return
    
    if status["type"] == "fact":
        if set_fact_private(entity_id, True):
            print(f"🔒 已设为私有: [{status['id'][:8]}] {status['summary']}")
        else:
            print("❌ 设置失败")
    else:  # abstract
        success, affected = set_abstract_private(entity_id, True, cascade=args.cascade)
        if success:
            print(f"🔒 已设为私有: [{status['id'][:8]}] {status['name']}")
            if args.cascade and affected:
                print(f"   📥 级联私有化 {len(affected)} 条关联事实")
        else:
            print("❌ 设置失败")


def cmd_public(args):
    """设置实体为公开"""
    entity_id = args.entity_id
    
    status = get_privacy_status(entity_id)
    if not status:
        print(f"❌ 未找到: {entity_id}")
        return
    
    if status["type"] == "fact":
        if set_fact_private(entity_id, False):
            print(f"🔓 已设为公开: [{status['id'][:8]}] {status['summary']}")
        else:
            print("❌ 设置失败")
    else:  # abstract
        success, affected = set_abstract_private(entity_id, False, cascade=args.cascade)
        if success:
            print(f"🔓 已设为公开: [{status['id'][:8]}] {status['name']}")
            if args.cascade and affected:
                print(f"   📤 级联公开化 {len(affected)} 条关联事实")
        else:
            print("❌ 设置失败")


def cmd_private_list(args):
    """列出所有私有实体"""
    entities = list_private_entities()
    
    print("🔒 私有实体\n")
    
    if entities["abstracts"]:
        print("── 抽象层 ──")
        for a in entities["abstracts"]:
            print(f"   [{a['id']}] {a['name']}")
    
    if entities["facts"]:
        print("\n── 事实 ──")
        for f in entities["facts"]:
            print(f"   [{f['id']}] {f['summary']}")
    
    if not entities["abstracts"] and not entities["facts"]:
        print("   (无私有内容)")


def cmd_private_stats(args):
    """显示隐私统计"""
    stats = get_privacy_stats()
    
    print("📊 隐私统计\n")
    print(f"事实层:")
    print(f"   总计: {stats['facts']['total']}")
    print(f"   公开: {stats['facts']['public']} 🌐")
    print(f"   私有: {stats['facts']['private']} 🔒")
    
    print(f"\n抽象层:")
    print(f"   总计: {stats['abstracts']['total']}")
    print(f"   公开: {stats['abstracts']['public']} 🌐")
    print(f"   私有: {stats['abstracts']['private']} 🔒")


def cmd_token(args):
    """Token 管理"""
    if args.action == "create":
        result = generate_token(
            duration=args.duration,
            scope=args.scope,
            note=args.note,
            qa_limit=args.qa_limit
        )
        print(f"✅ Token 已生成\n")
        print(f"   Scope: {result['scope_label']}")
        qa_limit_str = "无限制" if result['qa_limit'] == 0 else f"{result['qa_limit']} 次"
        print(f"   问答限制: {qa_limit_str}")
        print(f"   有效期: {result['duration']} (至 {result['expires_at_human']})")
        print(f"   Token: {result['token']}")
        print(f"\n   访问链接: {get_visual_url(result['token'])}")
    
    elif args.action == "list":
        from visual_token import get_qa_stats
        tokens = list_tokens()
        if not tokens:
            print("无有效 Token")
            return
        
        print("📋 有效 Token\n")
        for t in tokens:
            print(f"   [{t['token']}] {t['scope_label']}")
            # 获取 Q&A 统计
            qa_stats = get_qa_stats(t['token_full'])
            if qa_stats.get('unlimited'):
                qa_str = "问答: 无限制"
            else:
                qa_str = f"问答: {qa_stats.get('used', 0)}/{qa_stats.get('limit', 20)}"
            print(f"      过期: {t['expires_at'][:16]} | 访问: {t['access_count']}次 | {qa_str}")
            if t['note']:
                print(f"      备注: {t['note']}")
            print()
    
    elif args.action == "revoke":
        if revoke_token(args.token_id):
            print(f"✅ Token 已撤销: {args.token_id}")
        else:
            print(f"❌ 未找到: {args.token_id}")


def cmd_research(args):
    """深度调研"""
    from research import research_url, research_topic, format_report
    
    target = args.target
    deep = not args.shallow
    
    if target.startswith("topic:"):
        topic = target[6:].strip()
        print(f"🔍 正在研究主题: {topic}...")
        report = research_topic(topic)
    elif target.startswith("http"):
        print(f"🔍 正在深度分析: {target}...")
        report = research_url(target, deep=deep)
    else:
        # 默认当作主题处理
        print(f"🔍 正在研究主题: {target}...")
        report = research_topic(target)
    
    print(format_report(report))


def cmd_delete(args):
    """删除事实（三库同步）"""
    brain = BrainAgent()
    
    # 先显示要删除的内容
    fact = brain.get_fact(args.fact_id) if len(args.fact_id) >= 36 else None
    if not fact:
        # 尝试短ID
        full_id = brain._resolve_short_id(args.fact_id)
        if full_id:
            fact = brain.get_fact(full_id)
    
    if not fact:
        print(f"❌ 未找到: {args.fact_id}")
        return
    
    print(f"将删除:")
    print(f"  [{fact['fact_id'][:8]}] {fact['summary'][:50]}...")
    
    if not args.force:
        confirm = input("确认删除? (y/N): ")
        if confirm.lower() != 'y':
            print("已取消")
            return
    
    if brain.delete(fact['fact_id']):
        print(f"✅ 已从三库中删除")
    else:
        print(f"❌ 删除失败")


def main():
    parser = argparse.ArgumentParser(
        description="Brain Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # store
    p_store = subparsers.add_parser("store", help="存储新事实")
    p_store.add_argument("content", help="事实内容")
    p_store.add_argument("--type", "-t", default="观点",
                        choices=["事件", "观点", "情绪", "资讯", "决策"],
                        help="内容类型")
    p_store.add_argument("--emotion", "-e", default="中性",
                        choices=["积极", "消极", "中性", "困惑", "兴奋"],
                        help="情绪标签")
    p_store.add_argument("--context", "-c", help="触发情境")
    p_store.add_argument("--source", "-s", default="user_input",
                        choices=["user_input", "user_confirmed_web"],
                        help="来源类型")
    p_store.add_argument("--url", "-u", help="来源URL")
    p_store.add_argument("--valid-until", help="有效期截止日期 (YYYY-MM 或 YYYY-MM-DD)")
    p_store.add_argument("--temporal", default="permanent",
                        choices=["permanent", "time_bound", "historical", "prediction"],
                        help="时态类型: permanent(永久) time_bound(时效) historical(历史) prediction(预测)")
    p_store.set_defaults(func=cmd_store)
    
    # query
    p_query = subparsers.add_parser("query", help="检索知识库")
    p_query.add_argument("text", help="查询文本")
    p_query.add_argument("--top", "-k", type=int, default=5, help="返回数量")
    p_query.add_argument("--min-score", type=float, default=0.5, help="最低相似度")
    p_query.add_argument("--no-graph", action="store_true", help="不查询图谱")
    p_query.set_defaults(func=cmd_query)
    
    # stats
    p_stats = subparsers.add_parser("stats", help="系统状态")
    p_stats.set_defaults(func=cmd_stats)
    
    # list
    p_list = subparsers.add_parser("list", help="列出事实")
    p_list.add_argument("--limit", "-n", type=int, default=10, help="数量")
    p_list.add_argument("--offset", type=int, default=0, help="偏移")
    p_list.set_defaults(func=cmd_list)
    
    # relate
    p_relate = subparsers.add_parser("relate", help="创建关联")
    p_relate.add_argument("from_id", help="起始事实ID")
    p_relate.add_argument("to_id", help="目标事实ID")
    p_relate.add_argument("--type", "-t", default="RELATES_TO",
                         choices=["支持", "矛盾", "延伸", "触发", "因果", "RELATES_TO"],
                         help="关系类型")
    p_relate.add_argument("--confidence", "-c", type=int, default=3,
                         choices=[1, 2, 3, 4, 5], help="置信度")
    p_relate.set_defaults(func=cmd_relate)
    
    # similar
    p_similar = subparsers.add_parser("similar", help="查找相似")
    p_similar.add_argument("fact_id", help="事实ID")
    p_similar.add_argument("--top", "-k", type=int, default=5, help="返回数量")
    p_similar.set_defaults(func=cmd_similar)
    
    # process (自动意图处理)
    p_process = subparsers.add_parser("process", help="自动识别意图并处理")
    p_process.add_argument("text", help="输入文本")
    p_process.set_defaults(func=cmd_process)
    
    # classify (仅识别意图)
    p_classify = subparsers.add_parser("classify", help="识别意图")
    p_classify.add_argument("text", help="输入文本")
    p_classify.set_defaults(func=cmd_classify)
    
    # delete (三库同步删除)
    p_delete = subparsers.add_parser("delete", help="删除事实（三库同步）")
    p_delete.add_argument("fact_id", help="事实ID（完整或前8位）")
    p_delete.add_argument("--force", "-f", action="store_true", help="跳过确认")
    p_delete.set_defaults(func=cmd_delete)
    
    # private (设为私有)
    p_private = subparsers.add_parser("private", help="设置实体为私有")
    p_private.add_argument("entity_id", help="实体ID（fact 或 abstract）")
    p_private.add_argument("--cascade", "-c", action="store_true",
                          help="抽象层级联私有化关联事实")
    p_private.set_defaults(func=cmd_private)
    
    # public (设为公开)
    p_public = subparsers.add_parser("public", help="设置实体为公开")
    p_public.add_argument("entity_id", help="实体ID（fact 或 abstract）")
    p_public.add_argument("--cascade", "-c", action="store_true",
                         help="抽象层级联公开化关联事实")
    p_public.set_defaults(func=cmd_public)
    
    # private-list
    p_plist = subparsers.add_parser("private-list", help="列出私有实体")
    p_plist.set_defaults(func=cmd_private_list)
    
    # private-stats
    p_pstats = subparsers.add_parser("private-stats", help="隐私统计")
    p_pstats.set_defaults(func=cmd_private_stats)
    
    # token
    p_token = subparsers.add_parser("token", help="Token 管理")
    p_token.add_argument("action", choices=["create", "list", "revoke"], help="操作")
    p_token.add_argument("--scope", "-s", default="browse_public",
                        choices=["full", "qa_public", "browse_public"],
                        help="权限范围: full=全量, qa_public=问答, browse_public=浏览")
    p_token.add_argument("--duration", "-d", default="7d", help="有效期 (1h, 7d, 1w)")
    p_token.add_argument("--qa-limit", "-q", type=int, default=None,
                        help="问答次数限制 (默认: qa_public=20, full=无限制)")
    p_token.add_argument("--note", "-n", help="备注")
    p_token.add_argument("--token-id", "-t", help="撤销时指定的 Token ID")
    p_token.set_defaults(func=cmd_token)
    
    # research
    p_research = subparsers.add_parser("research", help="深度调研")
    p_research.add_argument("target", help="URL 或 topic:主题")
    p_research.add_argument("--shallow", action="store_true", help="浅层模式（不探索子页面）")
    p_research.set_defaults(func=cmd_research)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
