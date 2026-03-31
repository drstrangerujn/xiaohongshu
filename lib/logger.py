"""任务日志 + 截图 + 失败快照"""

import json
import os
import time
from datetime import datetime
from pathlib import Path


def _data_dir():
    return Path(__file__).resolve().parent.parent / "data"


def log_task(command: str, args: dict, status: str, error: str = None, extra: dict = None):
    """写一条任务日志到 JSONL"""
    entry = {
        "task_id": f"{command}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "command": command,
        "args": args,
        "time": datetime.now().isoformat(),
        "status": status,
    }
    if error:
        entry["error"] = error
    if extra:
        entry.update(extra)

    log_file = _data_dir() / "logs" / f"{datetime.now().strftime('%Y%m%d')}.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry["task_id"]


async def save_screenshot(page, name: str) -> str:
    """截图保存到 snapshots/"""
    path = _data_dir() / "snapshots" / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path))
    return str(path)


async def save_failure_snapshot(page, name: str) -> dict:
    """失败时保存截图 + HTML + 控制台错误"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = _data_dir() / "snapshots" / f"fail_{name}_{ts}"

    paths = {}

    # 截图
    png_path = f"{base}.png"
    try:
        await page.screenshot(path=png_path)
        paths["screenshot"] = png_path
    except Exception:
        pass

    # HTML 快照
    html_path = f"{base}.html"
    try:
        content = await page.content()
        with open(html_path, "w") as f:
            f.write(content)
        paths["html"] = html_path
    except Exception:
        pass

    return paths
