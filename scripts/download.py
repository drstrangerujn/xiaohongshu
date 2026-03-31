#!/usr/bin/env python3
"""下载小红书笔记的图片/视频"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.browser import open_browser
from lib.auth import _dismiss_cookie_banner
from lib.parser import NetworkDataCollector, parse_note_from_api, parse_note_from_dom
from lib.rate_limiter import rate_limit
from lib.human_sim import random_delay
from lib.logger import log_task


def _data_dir():
    return Path(__file__).resolve().parent.parent / "data"


def _download_db():
    """简单用 JSONL 记录下载历史，够用"""
    return _data_dir() / "downloads" / ".download_history.jsonl"


def _is_downloaded(url: str) -> bool:
    db = _download_db()
    if not db.exists():
        return False
    url_hash = hashlib.md5(url.encode()).hexdigest()
    with open(db) as f:
        for line in f:
            if url_hash in line:
                return True
    return False


def _record_download(url: str, path: str, media_type: str, note_url: str):
    db = _download_db()
    db.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "url_hash": hashlib.md5(url.encode()).hexdigest(),
        "url": url,
        "path": path,
        "type": media_type,
        "note_url": note_url,
    }
    with open(db, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


@rate_limit("download")
async def download_note(account: str, url: str, output_dir: str) -> dict:
    """下载笔记的所有媒体文件"""

    async with open_browser(account) as (ctx, page):
        collector = NetworkDataCollector()
        page.on("response", collector.on_response)

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(3, 6)
        await _dismiss_cookie_banner(page)

        # 提取笔记数据
        api_data = collector.find("note")
        note = None
        if api_data:
            note = parse_note_from_api(api_data)
        if not note:
            note = await parse_note_from_dom(page)
        if not note:
            raise RuntimeError("未能解析笔记内容")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 用笔记 ID 或标题做子目录
        note_id = note.get("id", "unknown")
        title = note.get("title", "untitled")[:30].replace("/", "_")
        note_dir = out / f"{note_id}_{title}"
        note_dir.mkdir(parents=True, exist_ok=True)

        downloaded = []

        # 下载图片
        for i, img_url in enumerate(note.get("images", [])):
            if not img_url or _is_downloaded(img_url):
                continue

            ext = "jpg"
            if ".png" in img_url:
                ext = "png"
            elif ".webp" in img_url:
                ext = "webp"
            filename = f"img_{i:02d}.{ext}"
            filepath = note_dir / filename

            try:
                resp = await page.context.request.get(img_url)
                if resp.ok:
                    body = await resp.body()
                    filepath.write_bytes(body)
                    _record_download(img_url, str(filepath), "image", url)
                    downloaded.append(str(filepath))
                    await random_delay(1, 3)
            except Exception as e:
                print(f"下载图片失败 ({img_url}): {e}", file=sys.stderr)

        # 下载视频
        video_url = note.get("video")
        if video_url and not _is_downloaded(video_url):
            filepath = note_dir / "video.mp4"
            try:
                resp = await page.context.request.get(video_url)
                if resp.ok:
                    body = await resp.body()
                    filepath.write_bytes(body)
                    _record_download(video_url, str(filepath), "video", url)
                    downloaded.append(str(filepath))
            except Exception as e:
                print(f"下载视频失败: {e}", file=sys.stderr)

        # 保存笔记元数据
        meta_path = note_dir / "meta.json"
        with open(meta_path, "w") as f:
            json.dump(note, f, ensure_ascii=False, indent=2)

        return {
            "note_id": note_id,
            "title": note.get("title", ""),
            "downloaded": downloaded,
            "meta": str(meta_path),
        }


async def main():
    parser = argparse.ArgumentParser(description="下载小红书笔记图片/视频")
    parser.add_argument("--url", "-u", required=True, help="笔记 URL")
    parser.add_argument("--output", "-o", default=str(_data_dir() / "downloads"), help="保存目录")
    parser.add_argument("--account", default="default", help="使用的账号")
    args = parser.parse_args()

    try:
        result = await download_note(args.account, args.url, args.output)
        print(f"笔记: {result['title']}")
        print(f"下载了 {len(result['downloaded'])} 个文件:")
        for f in result["downloaded"]:
            print(f"  {f}")
        print(f"元数据: {result['meta']}")

        log_task("download", {"url": args.url}, "success",
                 extra={"file_count": len(result["downloaded"])})

    except Exception as e:
        log_task("download", {"url": args.url}, "error", error=str(e))
        print(f"下载失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
