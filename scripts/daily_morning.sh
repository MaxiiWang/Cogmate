#!/bin/bash
# 早间整理报告 (07:00)
# 关联梳理 + 抽象层巡检

cd ~/.openclaw/workspace/brain-agent/lib
export BRAIN_NEO4J_PASSWORD="brainagent2026"

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
REPORT=$(python3 -c "from daily_report import generate_morning_report; print(generate_morning_report())" 2>/dev/null)

if [ -n "$REPORT" ]; then
    openclaw message send --channel telegram --target 5769860070 --message "$REPORT"
fi
