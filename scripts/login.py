#!/usr/bin/env python3
"""扫码登录小红书"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import qr_login, check_login


async def main():
    parser = argparse.ArgumentParser(description="小红书扫码登录")
    parser.add_argument("--account", default="default", help="账号名称")
    parser.add_argument("--check", action="store_true", help="只检查登录状态，不登录")
    args = parser.parse_args()

    if args.check:
        result = check_login(args.account)
        print(f"账号: {args.account}")
        print(f"状态: {'已登录' if result['logged_in'] else '未登录'}")
        print(f"详情: {result['detail']}")
        return

    # 先检查是否已登录
    status = await check_login(args.account)
    if status["logged_in"]:
        print(f"账号 {args.account} 已经登录了")
        return

    # 执行扫码登录
    result = await qr_login(args.account)
    if result["success"]:
        print(f"\n登录成功! Profile 已保存。")
    else:
        print(f"\n登录失败: {result['detail']}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
