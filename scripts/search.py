#!/usr/bin/env python3
"""搜索小红书笔记"""

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.browser import open_browser
from lib.auth import _dismiss_popups
from lib.rate_limiter import rate_limit
from lib.human_sim import random_delay, scroll_to_bottom
from lib.logger import log_task, save_screenshot


@rate_limit("search")
async def do_search(account: str, keyword: str, sort: str = "general", limit: int = 20) -> list:
    """执行搜索，返回笔记列表"""

    async with open_browser(account) as (ctx, page):
        collected_api = []

        async def on_response(response):
            url = response.url
            if '/api/sns/web/v1/search/notes' in url or '/api/sns/web/v1/homefeed' in url:
                try:
                    data = await response.json()
                    collected_api.append({"url": url, "data": data})
                except Exception:
                    pass

        page.on("response", on_response)

        # 先进首页建立 session
        await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
        await random_delay(2, 4)
        await _dismiss_popups(page)
        await asyncio.sleep(1)

        # 在首页搜索栏输入关键词
        search_input = page.locator('#search-input')
        if await search_input.count() > 0:
            await search_input.click()
            await search_input.type(keyword, delay=80)
            await asyncio.sleep(1)
            await _dismiss_popups(page)

            # 点搜索图标
            search_icon = page.locator('.search-icon')
            if await search_icon.count() > 0 and await search_icon.is_visible():
                await search_icon.click()

            await asyncio.sleep(3)
            await _dismiss_popups(page)

        # 等待搜索结果页加载（可能跳也可能不跳）
        try:
            await page.wait_for_url("**/search_result**", timeout=5000)
        except Exception:
            pass

        await random_delay(2, 4)
        await _dismiss_popups(page)

        await save_screenshot(page, f"search_{keyword}")

        # 如果需要更多结果，滚动加载
        for _ in range(min(limit // 10, 5)):
            await scroll_to_bottom(page, max_scrolls=2)
            await random_delay(1, 3)

        # 方法1: 从 API 响应提取（最优）
        notes = []
        for api in collected_api:
            data = api["data"]
            items = data.get("data", {}).get("items", [])
            for item in items:
                nc = item.get("note_card", {})
                if not nc:
                    nc = item
                note_id = item.get("id", nc.get("note_id", ""))
                if not note_id or any(n["id"] == note_id for n in notes):
                    continue
                notes.append({
                    "id": note_id,
                    "title": nc.get("display_title", ""),
                    "desc": nc.get("desc", "")[:100],
                    "type": nc.get("type", ""),
                    "liked_count": nc.get("interact_info", {}).get("liked_count", ""),
                    "user": {
                        "nickname": nc.get("user", {}).get("nickname", ""),
                        "user_id": nc.get("user", {}).get("user_id", ""),
                    },
                    "cover": nc.get("cover", {}).get("url_default", ""),
                    "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                })

        # 方法2: 从 DOM 提取（兜底）
        if not notes:
            notes = await _extract_notes_from_dom(page)

        # 如果有关键词，过滤相关结果（首页推荐流可能不完全匹配）
        if keyword and notes:
            keyword_lower = keyword.lower()
            matched = [n for n in notes if keyword_lower in (n.get("title", "") + n.get("desc", "")).lower()]
            # 如果匹配的太少就不过滤（可能是推荐流）
            if len(matched) >= 3:
                notes = matched

        return notes[:limit]


async def _extract_notes_from_dom(page) -> list:
    """从页面 DOM 提取笔记列表"""
    return await page.evaluate('''
        () => {
            const results = [];
            document.querySelectorAll("a[href*='/explore/']").forEach(a => {
                const section = a.closest("section") || a.parentElement;
                if (!section) return;
                const href = a.getAttribute("href");
                const id = href ? href.split("/explore/")[1]?.split("?")[0] : "";
                if (!id || results.find(r => r.id === id)) return;

                // 提取文本
                const allText = section.innerText || "";
                const lines = allText.split("\\n").filter(l => l.trim());

                // 找标题（通常是最长的非数字行）
                let title = "";
                let author = "";
                let likes = "";
                for (const line of lines) {
                    const t = line.trim();
                    if (!t) continue;
                    if (/^\\d+[\\s万w]*$/.test(t)) {
                        if (!likes) likes = t;
                        continue;
                    }
                    if (!title && t.length > 2) {
                        title = t;
                    } else if (!author && t.length > 0 && t.length < 20) {
                        author = t;
                    }
                }

                results.push({
                    id: id,
                    title: title.substring(0, 60),
                    desc: "",
                    type: "",
                    liked_count: likes,
                    user: { nickname: author, user_id: "" },
                    cover: "",
                    url: "https://www.xiaohongshu.com/explore/" + id
                });
            });
            return results;
        }
    ''')


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
