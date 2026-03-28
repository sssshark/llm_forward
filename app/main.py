"""
大模型请求转发服务
用于转发请求并提取 token 使用信息
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, AsyncGenerator
from pathlib import Path


# 配置日志
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'llm_forward.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="llm forward Service")


LLM_FORWARD_API_BASE = os.getenv("LLM_FORWARD_API_BASE", "https://coding.dashscope.aliyuncs.com/v1")
LLM_FORWARD_API_KEY = os.getenv("LLM_FORWARD_API_KEY", "")


# Token 使用统计存储
token_usage_log = log_dir / 'token_usage.jsonl'

logger.info("服务启动")

async def log_token_usage(response_data: Dict[str, Any]):
    """记录 token 使用信息"""
    usage_info = {
        "timestamp": datetime.now().isoformat(),
        "prompt_tokens": response_data.get("usage", {}).get("prompt_tokens", 0),
        "completion_tokens": response_data.get("usage", {}).get("completion_tokens", 0),
        "total_tokens": response_data.get("usage", {}).get("total_tokens", 0)
    }

    # 写入日志文件
    with open(token_usage_log, 'a', encoding='utf-8') as f:
        f.write(json.dumps(usage_info, ensure_ascii=False) + '\n')

    logger.info(f"Token 使用统计: {usage_info}")
    return usage_info


def build_headers(request_headers):
    """构建转发请求的 headers"""
    headers = {}
    for key, value in request_headers.items():
        if key.lower() not in ['host', 'content-length', 'content-encoding', 'transfer-encoding', 'authorization']:
            headers[key] = value
    headers['Authorization'] = f'Bearer {LLM_FORWARD_API_KEY}'
    return headers


async def forward_request_stream(request_data: Dict[str, Any], url, headers) -> AsyncGenerator[str, None]:
    """转发请求到 LLM API 并流式返回响应"""
    request_data["stream_options"] = {"include_usage": True}

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream('POST', url, json=request_data, headers=headers) as response:
                # 如果响应状态码不是 2xx，记录错误详情
                if not response.is_success:
                    error_bytes = await response.aread()
                    error_text = error_bytes.decode('utf-8')
                    logger.error(f"流式请求失败 - 状态码: {response.status_code}, 响应: {error_text}")
                    error_msg = f'data: {{"error": "API返回错误: {response.status_code} - {error_text}"}}\n\n'
                    yield error_msg.encode('utf-8')
                    return

                response.raise_for_status()

                async for chunk in response.aiter_bytes():
                    chunk_str = chunk.decode("utf-8")
                    json_str = chunk_str.split("data: ")
                    for item in json_str:
                        if item and "[DONE]" not in item:
                            try:
                                data = json.loads(item)
                                if "usage" in data and data["usage"] is not None:
                                    await log_token_usage(data)
                                else:
                                    logger.error(f"大模型没有返回usage字段")
                            except json.JSONDecodeError as e:
                                logger.warning(f"JSON 解析失败: {e}, 原始内容: {item}")

                    yield chunk
    except httpx.HTTPStatusError as e:
        logger.error(f"流式请求HTTP错误 - 状态码: {e.response.status_code}, 响应: {e.response.text}")
        error_msg = f'data: {{"error": "HTTP错误: {e.response.status_code} - {e.response.text[:200]}"}}\n\n'
        yield error_msg.encode('utf-8')
    except httpx.HTTPError as e:
        logger.error(f"流式请求转发失败: {type(e).__name__}: {e}")
        error_msg = f'data: {{"error": "请求失败: {type(e).__name__}: {str(e)}"}}\n\n'
        yield error_msg.encode('utf-8')
    except Exception as e:
        logger.exception(f"流式请求未知错误")
        error_msg = f'data: {{"error": "未知错误: {type(e).__name__}: {str(e)}"}}\n\n'
        yield error_msg.encode('utf-8')


async def forward_request(request_data: Dict[str, Any], url, headers):
    """转发请求到 LLM API（非流式）"""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=request_data, headers=headers)

            logger.info(f"响应状态码: {response.status_code}")
            logger.info(f"响应 headers: {dict(response.headers)}")
            logger.info(f"响应内容: {response.text[:1000]}")

            # 如果响应状态码不是 2xx，记录详细错误
            if not response.is_success:
                logger.error(f"API请求失败 - 状态码: {response.status_code}, 响应: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"API错误: {response.status_code} - {response.text[:500]}"
                )

            # 解析响应
            try:
                response_data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"响应 JSON 解析失败: {e}")
                logger.error(f"响应内容: {response.text}")
                raise HTTPException(status_code=500, detail=f"API 返回了非 JSON 格式的响应: {response.text[:200]}")

            # 记录 token 使用信息
            if "usage" in response_data:
                await log_token_usage(response_data)

            return JSONResponse(content=response_data, status_code=response.status_code)
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP错误 - 状态码: {e.response.status_code}, 响应: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"API错误: {e.response.status_code} - {e.response.text[:500]}")
    except httpx.HTTPError as e:
        logger.error(f"请求转发失败: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"请求转发失败: {type(e).__name__}: {str(e)}")
    except Exception as e:
        logger.exception(f"未知错误")
        raise HTTPException(status_code=500, detail=f"未知错误: {type(e).__name__}: {str(e)}")


@app.post("/chat/completions")
async def chat_completions(request: Request):
    """转发聊天完成请求"""
    logger.info("/chat/completions")

    request_data = await request.json()

    model = request_data.get("model", "unknown")
    stream = request_data.get("stream", False)

    logger.info(f"收到聊天完成请求 - 模型: {model}, 流式: {stream}")

    endpoint = "chat/completions"
    # 移除 base 末尾的斜杠，避免双斜杠
    base = LLM_FORWARD_API_BASE.rstrip('/')
    url = f"{base}/{endpoint}"
    headers = build_headers(request.headers)

    logger.info(f"转发的 headers: {headers}")
    logger.info(f"请求 URL: {url}")
    logger.info(f"是否流式请求: {stream}")
    logger.info(f"请求数据: {json.dumps(request_data, ensure_ascii=False)[:500]}")

    # 如果是流式请求，使用 StreamingResponse
    if stream:
        return StreamingResponse(
            forward_request_stream(request_data, url, headers),
            media_type="text/event-stream"
        )

    # 非流式请求
    return await forward_request(request_data, url, headers)


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "service": "llm-forward"}


@app.get("/token-stats")
async def get_token_stats():
    """获取 token 使用统计"""
    if not token_usage_log.exists():
        return {"total_requests": 0, "total_tokens": 0, "stats": []}

    stats = []
    total_tokens = 0

    with open(token_usage_log, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                stats.append(data)
                total_tokens += data.get("total_tokens", 0)
            except json.JSONDecodeError:
                continue

    return {
        "total_requests": len(stats),
        "total_tokens": total_tokens,
        "stats": stats[-100:]  # 返回最近 100 条记录
    }


@app.delete("/token-stats")
async def clear_token_stats():
    """清空 token 使用统计"""
    if token_usage_log.exists():
        token_usage_log.unlink()
        logger.info("Token 使用统计已清空")
        return {"message": "Token 使用统计已清空"}
    return {"message": "文件不存在，无需清空"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
