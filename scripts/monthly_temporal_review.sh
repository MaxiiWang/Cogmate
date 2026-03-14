#!/bin/bash
# 月度时态审查 (每月1日 09:00)
# 检测即将过期和已过期的记录

cd ~/.openclaw/workspace/cogmate/lib
export COGMATE_NEO4J_PASSWORD="brainagent2026"

# 生成报告
REPORT=$(python3 -c "from temporal_review import generate_temporal_report; print(generate_temporal_report())" 2>/dev/null)

if [ -n "$REPORT" ] && [[ "$REPORT" != *"无过期"* ]]; then
    # 只有在有内容时才推送
    openclaw message send --channel telegram --target 5769860070 --message "$REPORT"
fi
