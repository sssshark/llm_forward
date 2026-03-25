# LLM Forward 中转服务

一个用于转发大模型 API 请求并提取 token 使用信息的中转服务。

## 功能特性

- ✅ 请求转发：将客户端请求转发到上游 API（如阿里云通义千问）
- ✅ Token 统计：自动提取和记录每次请求的 token 使用情况
- ✅ 数据监控：记录请求耗时和消息数量
- ✅ 日志记录：完整的请求和响应日志
- ✅ 统计接口：提供 token 使用统计查询接口
- ✅ 健康检查：服务健康状态监控

## 项目结构

```
llm_forward/
├── app/
│   └── main.py          # 主服务代码
├── requirements.txt     # Python 依赖
├── LICENSE             # 许可证
└── README.md           # 说明文档
```

## 快速开始

### 1. 安装依赖

```bash
cd llm_forward
pip install -r requirements.txt
```

### 2. 配置上游 API

可通过环境变量配置：

```bash
export LLM_FORWARD_API_BASE="https://ark.cn-beijing.volces.com/api/coding/v3"
export LLM_FORWARD_API_KEY="your_api_key_here"
```

或直接编辑 `app/main.py` 文件，修改默认配置值。

### 3. 启动服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

服务将在 `http://localhost:8000` 启动。

## API 接口

### 1. 聊天完成接口

**POST** `/chat/completions`

转发聊天完成请求到上游 API（支持流式和非流式）。

**请求示例：**
```bash
# 流式请求（默认）
curl -X POST POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-max",
    "messages": [
      {"role": "user", "content": "你好！"}
    ],
    "stream": true
  }'

# 非流式请求
curl -X POST POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-max",
    "messages": [
      {"role": "user", "content": "你好！"}
    ],
    "stream": false
  }'
```

### 2. 健康检查接口

**GET** `/health`

检查服务健康状态。

**响应示例：**
```json
{
  "status": "healthy",
  "service": "llm_forward"
}
```

### 3. Token 统计接口

**GET** `/token-stats`

获取 token 使用统计信息。

**响应示例：**
```json
{
  "total_requests": 150,
  "total_tokens": 45000,
  "stats": [
    {
      "timestamp": "2026-03-25T15:30:00",
      "prompt_tokens": 100,
      "completion_tokens": 50,
      "total_tokens": 150
    }
  ]
}
```

## Token 使用信息

每次请求后，服务会自动记录以下信息：

- `timestamp`: 请求时间戳
- `prompt_tokens`: 输入 token 数量
- `completion_tokens`: 输出 token 数量
- `total_tokens`: 总 token 数量

这些信息会保存在 `logs/token_usage.jsonl` 文件中，每行一条 JSON 记录。

## 日志文件

- `logs/llm_forward.log`: 服务运行日志，包含所有请求和错误信息
- `logs/token_usage.jsonl`: Token 使用统计，每行一条 JSON 记录

## 使用示例

### Python 客户端示例

```python
import requests

# 通过中转服务发送请求
response = requests.post(
    "http://localhost:8000/chat/completions",
    headers={"Content-Type": "application/json"},
    json={
        "model": "qwen-max",
        "messages": [
            {"role": "user", "content": "你好！"}
        ],
        "stream": False
    }
)

print(response.json())
```

### 查询 Token 统计

```bash
curl http://localhost:8000/token-stats
```

## 配置说明

优先使用环境变量配置，也可在 `app/main.py` 中修改默认值。支持以下环境变量：

| 变量名 | 说明 | 示例 |
|--------|------|------|
| LLM_FORWARD_API_BASE | 上游 API 地址 | https://ark.cn-beijing.volces.com/api/coding/v3 |
| LLM_FORWARD_API_KEY | API 密钥 | sk-xxxxx |

### 启动脚本配置（可选）

`start.sh` 支持通过环境变量配置服务监听地址和端口：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| HOST | 服务监听地址 | 0.0.0.0 |
| PORT | 服务监听端口 | 8000 |

## 注意事项

1. 确保环境变量 `LLM_FORWARD_API_BASE` 和 `LLM_FORWARD_API_KEY` 已正确配置
2. 服务需要有访问上游 API 的网络权限
3. 日志文件会持续增长，建议定期清理或归档
4. 生产环境建议使用进程管理工具（如 systemd、supervisor）

## 故障排查

### 服务无法启动

- 检查 Python 依赖是否已安装：`pip install -r requirements.txt`
- 确认端口 8000 未被占用
- 查看日志文件 `logs/llm_forward.log` 了解详细错误信息

### 请求转发失败

- 确认上游 API 密钥有效
- 检查网络连接是否正常
- 查看 `logs/llm_forward.log` 中的错误信息

### Token 统计不准确

- 确保流式请求中包含 `stream_options: {"include_usage": True}`
- 查看日志确认是否正确解析 usage 信息

## 许可证

MIT License
