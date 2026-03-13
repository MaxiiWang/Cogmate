#!/bin/bash
# Brain Visual API 启动脚本
# 用法: ./visual/start.sh [port]

PORT=${1:-8000}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

echo "🎨 启动 Brain Visual API..."
echo "   端口: $PORT"
echo "   访问: http://localhost:$PORT"
echo ""

python -m uvicorn api:app --host 0.0.0.0 --port $PORT
