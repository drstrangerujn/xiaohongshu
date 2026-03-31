"""数据提取：网络层优先，DOM 兜底"""

import json
import re
from typing import Optional


class NetworkDataCollector:
    """拦截网络响应，收集结构化数据"""

    def __init__(self):
        self.responses = []

    async def on_response(self, response):
        url = response.url
        # 小红书常见 API 路径
        api_patterns = [
            "/api/sns/web/v1/search",
            "/api/sns/web/v1/feed",
            "/api/sns/web/v2/note",
            "/api/sns/web/v1/note",
            "/api/sns/web/v1/comment",
        ]
        for pattern in api_patterns:
            if pattern in url:
                try:
                    data = await response.json()
                    self.responses.append({
                        "url": url,
                        "pattern": pattern,
                        "data": data,
                    })
                except Exception:
                    pass
                break

    def find(self, pattern: str) -> Optional[dict]:
        """找到匹配 pattern 的第一个响应"""
        for r in self.responses:
            if pattern in r["pattern"]:
                return r["data"]
        return None

    def find_all(self, pattern: str) -> list:
        """找到匹配 pattern 的所有响应"""
        return [r["data"] for r in self.responses if pattern in r["pattern"]]


def parse_search_from_api(data: dict) -> list:
    """从搜索 API 响应中提取笔记列表"""
    notes = []
    try:
        items = data.get("data", {}).get("items", [])
        for item in items:
            note_card = item.get("note_card", item.get("model_type", {}))
            if not note_card:
                continue

            note = {
                "id": item.get("id", ""),
                "title": note_card.get("display_title", ""),
                "desc": note_card.get("desc", ""),
                "type": note_card.get("type", ""),
                "liked_count": note_card.get("interact_info", {}).get("liked_count", ""),
                "user": {
                    "nickname": note_card.get("user", {}).get("nickname", ""),
                    "user_id": note_card.get("user", {}).get("user_id", ""),
                },
                "cover": note_card.get("cover", {}).get("url_default", ""),
                "url": f"https://www.xiaohongshu.com/explore/{item.get('id', '')}",
            }
            notes.append(note)
    except Exception:
        pass
    return notes


def parse_note_from_api(data: dict) -> Optional[dict]:
    """从笔记详情 API 响应中提取信息"""
    try:
        items = data.get("data", {}).get("items", [])
        if not items:
            return None
        item = items[0]
        note = item.get("note_card", {})

        images = []
        for img in note.get("image_list", []):
            url = img.get("url_default", "") or img.get("info_list", [{}])[-1].get("url", "")
            if url:
                images.append(url)

        video = None
        video_info = note.get("video", {})
        if video_info:
            for key in ["h264", "h265", "av1"]:
                streams = video_info.get("media", {}).get("stream", {}).get(key, [])
                if streams:
                    video = streams[0].get("master_url", "")
                    break

        return {
            "id": note.get("note_id", item.get("id", "")),
            "title": note.get("display_title", ""),
            "desc": note.get("desc", ""),
            "type": note.get("type", ""),
            "tags": [t.get("name", "") for t in note.get("tag_list", [])],
            "images": images,
            "video": video,
            "liked_count": note.get("interact_info", {}).get("liked_count", ""),
            "collected_count": note.get("interact_info", {}).get("collected_count", ""),
            "comment_count": note.get("interact_info", {}).get("comment_count", ""),
            "share_count": note.get("interact_info", {}).get("share_count", ""),
            "user": {
                "nickname": note.get("user", {}).get("nickname", ""),
                "user_id": note.get("user", {}).get("user_id", ""),
            },
            "time": note.get("time", ""),
            "url": f"https://www.xiaohongshu.com/explore/{note.get('note_id', '')}",
        }
    except Exception:
        return None


async def parse_search_from_dom(page) -> list:
    """DOM 兜底：从页面 DOM 提取搜索结果"""
    notes = []
    try:
        # 常见的搜索结果容器选择器
        card_selectors = [
            'section.note-item',
            '[class*="note-item"]',
            'div[data-note-id]',
            '.feeds-page .note-item',
        ]

        cards = None
        for sel in card_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                cards = loc
                break

        if not cards:
            return notes

        count = await cards.count()
        for i in range(min(count, 50)):
            card = cards.nth(i)
            try:
                title_el = card.locator('[class*="title"], a.title, .note-title').first
                title = await title_el.inner_text() if await title_el.count() > 0 else ""

                author_el = card.locator('[class*="author"], .author-name, [class*="nickname"]').first
                author = await author_el.inner_text() if await author_el.count() > 0 else ""

                link_el = card.locator("a[href*='/explore/']").first
                href = await link_el.get_attribute("href") if await link_el.count() > 0 else ""
                note_id = href.split("/explore/")[-1].split("?")[0] if "/explore/" in href else ""

                like_el = card.locator('[class*="like"], [class*="count"]').first
                likes = await like_el.inner_text() if await like_el.count() > 0 else ""

                notes.append({
                    "id": note_id,
                    "title": title.strip(),
                    "user": {"nickname": author.strip()},
                    "liked_count": likes.strip(),
                    "url": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else href,
                })
            except Exception:
                continue
    except Exception:
        pass

    return notes


async def parse_note_from_dom(page) -> Optional[dict]:
    """DOM 兜底：从详情页 DOM 提取笔记信息"""
    try:
        note = {}

        # 标题
        for sel in ['#detail-title', '[class*="title"]', 'h1']:
            el = page.locator(sel).first
            if await el.count() > 0:
                note["title"] = (await el.inner_text()).strip()
                break

        # 正文
        for sel in ['#detail-desc', '[class*="desc"]', '[class*="content"]']:
            el = page.locator(sel).first
            if await el.count() > 0:
                note["desc"] = (await el.inner_text()).strip()
                break

        # 图片
        images = []
        img_els = page.locator('[class*="slide"] img, .note-image img, [class*="carousel"] img')
        count = await img_els.count()
        for i in range(count):
            src = await img_els.nth(i).get_attribute("src")
            if src and "http" in src:
                images.append(src)
        note["images"] = images

        # 互动数据
        for key, patterns in {
            "liked_count": ["点赞", "like"],
            "collected_count": ["收藏", "collect"],
            "comment_count": ["评论", "comment"],
        }.items():
            for pat in patterns:
                els = page.locator(f'[class*="{pat}"] span, [class*="{pat}"]')
                if await els.count() > 0:
                    text = await els.first.inner_text()
                    # 提取数字
                    nums = re.findall(r'[\d.]+[万w]?', text)
                    note[key] = nums[0] if nums else text.strip()
                    break

        # 作者
        for sel in ['[class*="author"] [class*="name"]', '[class*="nickname"]']:
            el = page.locator(sel).first
            if await el.count() > 0:
                note["user"] = {"nickname": (await el.inner_text()).strip()}
                break

        return note if note.get("title") or note.get("desc") else None

    except Exception:
        return None
