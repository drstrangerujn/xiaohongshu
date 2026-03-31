#!/usr/bin/env python3
"""扫码登录小红书"""

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import qr_login, check_login


async def main():
    parser = argparse.ArgumentParser(description="小红书扫码登录")
    parser.add_argument("--account", default="default", help="账号名称")
    parser.add_argument("--check", action="store_true", help="只检查登录状态")
    parser.add_argument("--port", type=int, default=18088, help="二维码 HTTP 服务端口")
    args = parser.parse_args()

    if args.check:
        result = await check_login(args.account)
        print(json.dumps(result, ensure_ascii=False))
        return

    # 先检查
    status = await check_login(args.account)
    if status["logged_in"]:
        print(json.dumps({"status": "already_logged_in", "detail": "已登录，无需扫码"}, ensure_ascii=False))
        return

    # 扫码登录（内部会自动推送二维码、启动 HTTP 服务）
    result = await qr_login(args.account, serve_port=args.port)

    # 最终输出
    output = {
        "success": result["success"],
        "detail": result["detail"],
        "qr_url": result.get("qr_url"),
        "push": result.get("push", {}),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
