"""显式连接选定供应商，输出统一模型片段；密钥只从指定环境变量读取。"""

import argparse
import asyncio
import math
import os

from aurora_core.json_data import encode_json
from aurora_model_adapter import ModelConfig, ModelRequest, ResponseBuffer
from aurora_model_adapter.adapters import create_litellm


async def run(args: argparse.Namespace) -> None:
    """一次流式请求受总时限约束；退出流后关闭独立客户端。"""
    api_key = os.environ.get(args.credential_env)
    if not api_key:
        raise ValueError(f"运行期凭证未提供：{args.credential_env}")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("timeout 必须为有限正数")
    client = await create_litellm(ModelConfig(args.model, args.base_url), api_key=api_key)
    try:
        request: ModelRequest = {"messages": [{"role": "user", "content": args.text}]}
        buffer = ResponseBuffer()
        async with asyncio.timeout(args.timeout):
            async with client.stream(request) as chunks:
                async for chunk in chunks:
                    buffer.append(chunk)
                    print(encode_json(chunk), flush=True)
        print(encode_json(buffer.result()), flush=True)
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="LiteLLM 模型名称，使用 openai/、anthropic/ 或 deepseek/ 前缀")
    parser.add_argument("--credential-env", required=True, help="保存运行期密钥的环境变量名称")
    parser.add_argument("--base-url", help="可选供应商或兼容网关地址")
    parser.add_argument("--text", default="请用一句话回复你好。", help="本次发送给模型的文本")
    parser.add_argument("--timeout", type=float, default=60, help="本次请求总时限，单位为秒")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
