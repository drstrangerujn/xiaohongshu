#!/usr/bin/env python3
"""检查登录状态和今日配额"""

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import check_login
from lib.rate_limiter import get_remaining


async def main():
    parser = argparse.ArgumentParser(description="检查小红书状态")
    parser.add_argument("--account", default="default", help="账号名称")
    args = parser.parse_args()

    # 登录状态
    status = await check_login(args.account)

    # JSON 模式（方便 agent 解析）
    if "--json" in sys.argv:
        quota = {}
        for op in ["search", "detail", "download", "publish"]:
            quota[op] = get_remaining(op)
        print(json.dumps({"account": args.account, "login": status, "quota": quota}, ensure_ascii=False))
        return

    print(f"账号: {args.account}")
    print(f"登录: {'✓' if status['logged_in'] else '✗'} {status['detail']}")

    # 配额
    print("\n今日配额:")
    for op in ["search", "detail", "download", "publish"]:
        info = get_remaining(op)
        print(f"  {op:10s} {info['used']:3d}/{info['limit']} (剩余 {info['remaining']})")


if __name__ == "__main__":
    asyncio.run(main())
