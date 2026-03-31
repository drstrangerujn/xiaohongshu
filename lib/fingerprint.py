"""账号级浏览器画像——首次生成，后续固定复用"""

import json
import random
from pathlib import Path

# 真实 UA 池（Chrome on Windows/Mac，保持更新）
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

_VIEWPORTS = [
    {"width": 1280, "height": 800},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
]


def get_or_create_profile(account: str = "default") -> dict:
    """获取账号画像，不存在则生成一个并保存"""
    profile_dir = Path(__file__).resolve().parent.parent / "data" / "profiles" / account
    fp_file = profile_dir / "fingerprint.json"

    if fp_file.exists():
        return json.loads(fp_file.read_text())

    # 首次生成
    fp = {
        "user_agent": random.choice(_UA_POOL),
        "viewport": random.choice(_VIEWPORTS),
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
    }

    profile_dir.mkdir(parents=True, exist_ok=True)
    fp_file.write_text(json.dumps(fp, indent=2))
    return fp
