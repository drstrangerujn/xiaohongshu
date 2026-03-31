#!/usr/bin/env python3
"""获取小红书笔记详情"""

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.browser import open_browser
from lib.parser import NetworkDataCollector, parse_note_from_api, parse_note_from_dom
from lib.rate_limiter import rate_limit
from lib.human_sim import random_delay
from lib.watchdog import check_page_anomaly
from lib.logger import log_task, save_screenshot, save_failure_snapshot


@rate_limit("detail")
async def get_detail(account: str, url: str) -> dict:
    """获取笔记详情"""

    async with open_browser(account) as (ctx, page):
        collector = NetworkDataCollector()
        page.on("response", collector.on_response)

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(3, 6)

        # 检查异常
        anomaly = await check_page_anomaly(page)
        if not anomaly["ok"]:
            if anomaly["level"] >= 3:
                snapshots = await save_failure_snapshot(page, "detail")
                raise RuntimeError(
                    f"页面异常 (level {anomaly['level']}): {anomaly['issue']}"
                )

        await save_screenshot(page, "detail")
        await random_delay(1, 3)

        # 尝试从网络响应提取
        api_data = collector.find("note")
        note = None
        if api_data:
            note = parse_note_from_api(api_data)

        # DOM 兜底
        if not note:
            note = await parse_note_from_dom(page)

        if not note:
            snapshots = await save_failure_snapshot(page, "detail_empty")
            raise RuntimeError(f"未能提取笔记内容，快照: {snapshots}")

        note["source_url"] = url
        return note


async def main():
    parser = argparse.ArgumentParser(description="获取小红书笔记详情")
    parser.add_argument("--url", "-u", required=True, help="笔记 URL")
    parser.add_argument("--account", default="default", help="使用的账号")
    parser.add_argument("--output", "-o", help="输出文件路径（JSON）")
    args = parser.parse_args()

    try:
        note = await get_detail(args.account, args.url)

        if args.output:
            with open(args.output, "w") as f:
                json.dump(note, f, ensure_ascii=False, indent=2)
            print(f"已保存到 {args.output}")
        else:
            print(json.dumps(note, ensure_ascii=False, indent=2))

        log_task("detail", {"url": args.url}, "success")

    except Exception as e:
        log_task("detail", {"url": args.url}, "error", error=str(e))
        print(f"获取详情失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
