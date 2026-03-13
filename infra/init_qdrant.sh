#!/bin/bash
# 创建 facts collection（向量维度 1536 = OpenAI ada-002 / 1024 = 其他常见模型）
# 先用 1536，后续可调整

curl -X PUT http://localhost:6333/collections/facts \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 1536,
      "distance": "Cosine"
    },
    "on_disk_payload": true
  }'

echo ""
echo "Qdrant collection 'facts' created."
