# -*- coding: utf-8 -*-
"""Sinh data/changelog.json từ lịch sử git để nút chuông trên web tự cập nhật.

Chạy tay:  python gen_changelog.py
Tự động:   chạy trong GitHub Action mỗi khi push (xem .github/workflows/changelog.yml)
"""
import subprocess
import json
import os

# Bỏ qua các commit tự động / không cần hiển thị cho người dùng
SKIP_PREFIXES = (
    "Cập nhật NAV", "Cap nhat NAV",          # commit NAV hàng ngày của bot
    "Cập nhật changelog", "Cap nhat changelog",  # commit của chính script này
    "Merge ",                                  # commit merge
)
MAX_ITEMS = 40

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "changelog.json")


def main():
    log = subprocess.check_output(
        ["git", "log", "--no-merges",
         "--pretty=format:%cd\t%s", "--date=format:%Y-%m-%d", "-200"],
        cwd=HERE, text=True,
    )
    items = []
    for line in log.splitlines():
        if "\t" not in line:
            continue
        date, msg = line.split("\t", 1)
        msg = msg.strip()
        if not msg or any(msg.startswith(p) for p in SKIP_PREFIXES):
            continue
        items.append({"date": date, "msg": msg})
        if len(items) >= MAX_ITEMS:
            break

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Đã ghi {len(items)} mục vào {OUT}")


if __name__ == "__main__":
    main()
