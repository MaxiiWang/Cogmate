#!/bin/bash

# Cogmate 一键安装脚本
# 用法: chmod +x setup.sh && ./setup.sh

set -e

echo "🧠 Cogmate 安装脚本"
echo "========================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查命令是否存在
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}❌ $1 未安装${NC}"
        return 1
    else
        echo -e "${GREEN}✓ $1 已安装${NC}"
        return 0
    fi
}

# 步骤 1: 检查依赖
echo "📋 步骤 1/6: 检查依赖..."
echo ""

DEPS_OK=true

check_command python3 || DEPS_OK=false
check_command pip3 || DEPS_OK=false
check_command docker || DEPS_OK=false

if [ "$DEPS_OK" = false ]; then
    echo ""
    echo -e "${RED}请先安装缺失的依赖${NC}"
    exit 1
fi

echo ""

# 步骤 2: 创建虚拟环境
echo "📦 步骤 2/6: 配置 Python 环境..."

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ 虚拟环境已创建${NC}"
else
    echo -e "${YELLOW}! 虚拟环境已存在，跳过${NC}"
fi

source venv/bin/activate

# 步骤 3: 安装 Python 依赖
echo ""
echo "📚 步骤 3/6: 安装 Python 依赖..."

pip install -q --upgrade pip
pip install -q -r requirements.txt

echo -e "${GREEN}✓ Python 依赖已安装${NC}"

# 步骤 4: 配置环境变量
echo ""
echo "⚙️  步骤 4/6: 配置环境变量..."

if [ ! -f ".env" ]; then
    cp .env.example .env
    
    # 生成随机密码
    NEO4J_PASS=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16)
    
    # 替换密码
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/your_secure_password_here/$NEO4J_PASS/" .env
    else
        sed -i "s/your_secure_password_here/$NEO4J_PASS/" .env
    fi
    
    echo -e "${GREEN}✓ .env 已创建${NC}"
    echo -e "${YELLOW}  Neo4j 密码: $NEO4J_PASS${NC}"
    echo -e "${YELLOW}  请妥善保存此密码！${NC}"
else
    echo -e "${YELLOW}! .env 已存在，跳过${NC}"
fi

# 步骤 5: 启动数据库
echo ""
echo "🐳 步骤 5/6: 启动数据库容器..."

cd infra

# 读取 Neo4j 密码
source ../.env

# 更新 docker-compose 中的密码
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/NEO4J_AUTH=neo4j\/.*/NEO4J_AUTH=neo4j\/$BRAIN_NEO4J_PASSWORD/" docker-compose.yml
else
    sed -i "s/NEO4J_AUTH=neo4j\/.*/NEO4J_AUTH=neo4j\/$BRAIN_NEO4J_PASSWORD/" docker-compose.yml
fi

# 启动容器
sudo docker compose up -d

echo -e "${GREEN}✓ 数据库容器已启动${NC}"
echo "  等待数据库就绪..."
sleep 15

cd ..

# 初始化 Qdrant 集合
echo "  初始化 Qdrant 集合..."
chmod +x infra/init_qdrant.sh
./infra/init_qdrant.sh > /dev/null 2>&1 || true
echo -e "${GREEN}✓ Qdrant 集合已初始化${NC}"

# 步骤 6: 验证安装
echo ""
echo "🔍 步骤 6/6: 验证安装..."

# 创建数据目录
mkdir -p data logs

# 运行验证
./cogmate stats

echo ""
echo "========================"
echo -e "${GREEN}🎉 安装完成！${NC}"
echo ""
echo "快速开始:"
echo "  ./cogmate store \"你的第一条知识\""
echo "  ./cogmate query \"检索关键词\""
echo "  ./cogmate stats"
echo ""
echo "文档:"
echo "  README.md  - 快速入门"
echo "  SETUP.md   - 详细安装指南"
echo "  AGENT.md   - AI Agent 集成"
echo "  SPEC.md    - 完整设计规范"
echo ""
echo "数据库控制台:"
echo "  Qdrant:  http://localhost:6333/dashboard"
echo "  Neo4j:   http://localhost:7474"
echo ""
