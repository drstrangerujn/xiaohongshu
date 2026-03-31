"""频率控制装饰器"""

import asyncio
import functools
import json
import random
import time
from datetime import date
from pathlib import Path


def _counter_file():
    return Path(__file__).resolve().parent.parent / "data" / "logs" / "rate_counter.json"


def _load_counters() -> dict:
    f = _counter_file()
    if f.exists():
        data = json.loads(f.read_text())
        # 过期的天数不管
        if data.get("date") == str(date.today()):
            return data
    return {"date": str(date.today()), "counts": {}}


def _save_counters(data: dict):
    f = _counter_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data))


def get_remaining(operation: str) -> dict:
    """查看某个操作今日剩余配额"""
    config_file = Path(__file__).resolve().parent.parent / "config.json"
    config = json.loads(config_file.read_text())
    limits = config.get("rate_limits", {}).get(operation, {})
    daily_limit = limits.get("daily_limit", 999)

    counters = _load_counters()
    used = counters.get("counts", {}).get(operation, 0)
    return {"used": used, "limit": daily_limit, "remaining": daily_limit - used}


def rate_limit(operation: str):
    """频率控制装饰器，从 config.json 读取对应操作的限制"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            config_file = Path(__file__).resolve().parent.parent / "config.json"
            config = json.loads(config_file.read_text())
            limits = config.get("rate_limits", {}).get(operation, {})
            min_delay = limits.get("min_delay", 3)
            max_delay = limits.get("max_delay", 15)
            daily_limit = limits.get("daily_limit", 100)

            # 检查日配额
            counters = _load_counters()
            used = counters.get("counts", {}).get(operation, 0)
            if used >= daily_limit:
                raise RuntimeError(
                    f"{operation} 今日已达上限 {daily_limit} 次，明天再来"
                )

            # 随机延迟（正态分布，集中在中间值）
            mean = (min_delay + max_delay) / 2
            std = (max_delay - min_delay) / 4
            delay = max(min_delay, min(max_delay, random.gauss(mean, std)))
            await asyncio.sleep(delay)

            # 执行
            result = await func(*args, **kwargs)

            # 计数
            counters = _load_counters()
            counts = counters.setdefault("counts", {})
            counts[operation] = counts.get(operation, 0) + 1
            _save_counters(counters)

            return result
        return wrapper
    return decorator
