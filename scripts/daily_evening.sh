#!/bin/bash
# 每日晚报 (21:00)
# 生成报告并通过 OpenClaw 发送到 Telegram

cd ~/.openclaw/workspace/cogmate/lib
export COGMATE_NEO4J_PASSWORD="brainagent2026"

# 读取 Anthropic API Key
AUTH_FILE="$HOME/.openclaw/agents/main/agent/auth-profiles.json"
if [ -z "$ANTHROPIC_API_KEY" ] && [ -f "$AUTH_FILE" ]; then
    export ANTHROPIC_API_KEY=$(python3 -c "
import json
with open('$AUTH_FILE') as f:
    data = json.load(f)
    for p in data.get('profiles', []):
        if p.get('id') == 'anthropic':
            print(p.get('key', ''))
            break
" 2>/dev/null)
fi

# 生成报告
REPORT=$(python3 -c "from daily_report import generate_daily_report; print(generate_daily_report())" 2>/dev/null)

if [ -n "$REPORT" ]; then
    # 通过 openclaw 发送到 Telegram
    openclaw message send --channel telegram --target 5769860070 --message "$REPORT"
fi
