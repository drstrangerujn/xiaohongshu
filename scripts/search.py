#!/usr/bin/env python3
"""搜索小红书笔记"""

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.browser import open_browser
from lib.parser import NetworkDataCollector, parse_search_from_api, parse_search_from_dom
from lib.rate_limiter import rate_limit
from lib.human_sim import random_delay, scroll_to_bottom
from lib.watchdog import check_page_anomaly
from lib.logger import log_task, save_screenshot, save_failure_snapshot


@rate_limit("search")
async def do_search(account: str, keyword: str, sort: str = "general", limit: int = 20) -> list:
    """执行搜索，返回笔记列表"""

    async with open_browser(account) as (ctx, page):
        collector = NetworkDataCollector()
        page.on("response", collector.on_response)

        # 打开搜索页
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_note"
        if sort == "latest":
            search_url += "&sort=time_descending"
        elif sort == "popular":
            search_url += "&sort=general"

        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(3, 6)

        # 检查异常
        anomaly = await check_page_anomaly(page)
        if not anomaly["ok"]:
            if anomaly["level"] >= 3:
                raise RuntimeError(f"页面异常 (level {anomaly['level']}): {anomaly['issue']}")
            # level 1-2 继续尝试

        await save_screenshot(page, f"search_{keyword}")

        # 先等一下，让网络请求回来
        await random_delay(2, 4)

        # 尝试从网络响应提取
        api_data = collector.find("search")
        notes = []
        if api_data:
            notes = parse_search_from_api(api_data)

        # 不够就翻页
        while len(notes) < limit:
            await scroll_to_bottom(page, max_scrolls=3)
            await random_delay(2, 4)

            # 检查网络响应是否有新数据
            all_api_data = collector.find_all("search")
            if all_api_data:
                notes = []
                for d in all_api_data:
                    notes.extend(parse_search_from_api(d))
            else:
                break

            # 有没有触底
            no_more = page.locator('[class*="no-more"], [class*="empty"]')
            if await no_more.count() > 0:
                break

        # 如果 API 没数据，用 DOM 兜底
        if not notes:
            notes = await parse_search_from_dom(page)

        return notes[:limit]


async def main():
    parser = argparse.ArgumentParser(description="搜索小红书笔记")
    parser.add_argument("--keyword", "-k", required=True, help="搜索关键词")
    parser.add_argument("--sort", choices=["general", "latest", "popular"], default="general", help="排序方式")
    parser.add_argument("--limit", "-n", type=int, default=20, help="最多返回条数")
    parser.add_argument("--account", default="default", help="使用的账号")
    parser.add_argument("--output", "-o", help="输出文件路径（JSONL）")
    args = parser.parse_args()

    try:
        notes = await do_search(args.account, args.keyword, args.sort, args.limit)

        if args.output:
            with open(args.output, "a") as f:
                for note in notes:
                    f.write(json.dumps(note, ensure_ascii=False) + "\n")
            print(f"已保存 {len(notes)} 条到 {args.output}")
        else:
            print(json.dumps(notes, ensure_ascii=False, indent=2))

        log_task("search", {"keyword": args.keyword, "sort": args.sort}, "success",
                 extra={"result_count": len(notes)})

    except Exception as e:
        log_task("search", {"keyword": args.keyword}, "error", error=str(e))
        print(f"搜索失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
