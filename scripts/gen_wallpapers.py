#!/usr/bin/env python3
"""登录页壁纸多档资产生成（构建期工具，Pillow；不进运行时依赖）。

依据 docs/UI_REORG_PLAN.md 3.1「分辨率适配（业界通行做法）」：
- 分发端自缩放多档：1920 / 2560 / 3840 宽；格式 WebP 优先 + JPEG 兜底；
- 5504 原图直接作最高档随包（字节原样，不重编码）；
- 源图 = docs/深色.jpg（dark）、docs/浅色.jpg（light），同构图成对。

产出 frontend/public/wallpapers/，命名 wallpaper-{dark|light}-{宽}.{ext}。
重采样 Image.LANCZOS；WebP quality 82 / method 6；JPEG quality 88（渐进式）。

用法：python scripts/gen_wallpapers.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = {
    "dark": ROOT / "docs" / "深色.jpg",
    "light": ROOT / "docs" / "浅色.jpg",
}
OUT = ROOT / "frontend" / "public" / "wallpapers"
WIDTHS = (1920, 2560, 3840)
WEBP_QUALITY = 82
JPEG_QUALITY = 88


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: list[tuple[Path, int]] = []

    for theme, src in SRC.items():
        if not src.is_file():
            print(f"ERROR: 源图缺失 {src}", file=sys.stderr)
            return 1
        with Image.open(src) as im:
            im.load()
            w, h = im.size
            # 5504 原图直接作最高档随包（复制字节，不重编码）
            orig = OUT / f"wallpaper-{theme}-{w}.jpg"
            shutil.copyfile(src, orig)
            manifest.append((orig, orig.stat().st_size))

            for tw in WIDTHS:
                th = round(tw * h / w)  # 保持源图纵横比（5504×3040）
                scaled = im.resize((tw, th), Image.LANCZOS)
                webp = OUT / f"wallpaper-{theme}-{tw}.webp"
                scaled.save(webp, "WEBP", quality=WEBP_QUALITY, method=6)
                manifest.append((webp, webp.stat().st_size))
                jpg = OUT / f"wallpaper-{theme}-{tw}.jpg"
                scaled.save(jpg, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
                manifest.append((jpg, jpg.stat().st_size))

    print(f"产出 {len(manifest)} 个文件 → {OUT}")
    for path, size in sorted(manifest):
        print(f"  {path.name:<34} {size:>9,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
