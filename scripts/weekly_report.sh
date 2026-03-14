#!/bin/bash
# 每周报告 (周日 20:00)
# 图谱健康 + 深度挑战 Stress Test

cd ~/.openclaw/workspace/cogmate/lib
export COGMATE_NEO4J_PASSWORD="brainagent2026"

# 读取 Anthropic API Key + Brave API Key
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

# Brave API Key
if [ -z "$BRAVE_API_KEY" ] && [ -f "$AUTH_FILE" ]; then
    export BRAVE_API_KEY=$(python3 -c "
import json
with open('$AUTH_FILE') as f:
    data = json.load(f)
    for p in data.get('profiles', []):
        if p.get('id') == 'brave':
            print(p.get('key', ''))
            break
" 2>/dev/null)
fi

# 生成报告
REPORT=$(python3 -c "from weekly_challenge import generate_weekly_report; print(generate_weekly_report())" 2>/dev/null)

if [ -n "$REPORT" ]; then
    openclaw message send --channel telegram --target 5769860070 --message "$REPORT"
fi

# 重建 PageIndex
python3 -c "from phase2 import PageIndexBuilder; b = PageIndexBuilder(); b.build_index(); print('PageIndex rebuilt')" 2>/dev/null
