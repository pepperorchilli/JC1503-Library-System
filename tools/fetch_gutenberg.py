#!/usr/bin/env python3
"""
下载公版书全文（Project Gutenberg）

为什么用公版书：
    桌面「教材」目录里的 PDF 来自 Z-Library 等盗版站，
    把全文放到公网服务器上属于侵权（详见对话记录）。
    公版书的著作权已过期，可以合法地全文公开。

下载到 data/books/<GutenbergID>.txt，
书目信息（书名/作者）由 reset_catalog.py 写在脚本里。

用法：
    python3 tools/fetch_gutenberg.py           # 下载缺失的书
    python3 tools/fetch_gutenberg.py --force   # 重新下载全部
"""

import argparse
import os
import subprocess
import sys

BOOKS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "books"
)

# Gutenberg ID → 文件名用 ID 即可，书名在 reset_catalog.py 里
GUTENBERG_IDS = [
    # ---- 中文经典 ----
    24264,   # 紅樓夢
    23950,   # 三國志演義
    25288,   # 山海經
    25501,   # 易經
    23873,   # 詩經
    24048,   # 禮記
    23841,   # 漢書
    24230,   # 今古奇觀
    12479,   # 三字經
    24068,   # 燕丹子
    # ---- 英文经典 ----
    1342,    # Pride and Prejudice
    11,      # Alice's Adventures in Wonderland
    84,      # Frankenstein
    1661,    # The Adventures of Sherlock Holmes
    1513,    # Romeo and Juliet
    98,      # A Tale of Two Cities
]

URL_TEMPLATE = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"


def download(book_id, force=False):
    dest = os.path.join(BOOKS_DIR, f"{book_id}.txt")

    if os.path.exists(dest) and not force:
        size = os.path.getsize(dest)
        print(f"  ⏭  #{book_id} 已存在（{size // 1024} KB）")
        return True

    url = URL_TEMPLATE.format(id=book_id)

    # 用 curl 而不是 Python 的 urllib：
    # 本机装了代理工具，会在证书链里插入自签证书，
    # Python 的 SSL 验证会失败，而 curl 走系统信任链不受影响。
    try:
        subprocess.run(
            ["curl", "-sfL", "--max-time", "90", "-o", dest, url],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"  ❌ #{book_id} 下载失败（curl 退出码 {e.returncode}）")
        return False
    except FileNotFoundError:
        print("  ❌ 找不到 curl 命令")
        return False

    size = os.path.getsize(dest) if os.path.exists(dest) else 0
    if size < 1000:
        print(f"  ❌ #{book_id} 内容异常（只有 {size} 字节）")
        return False

    print(f"  ✅ #{book_id}  {size // 1024} KB")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="重新下载全部")
    args = parser.parse_args()

    os.makedirs(BOOKS_DIR, exist_ok=True)

    print("=" * 56)
    print("  下载公版书（Project Gutenberg）")
    print("=" * 56)
    print()

    ok = sum(1 for bid in GUTENBERG_IDS if download(bid, args.force))

    total = sum(
        os.path.getsize(os.path.join(BOOKS_DIR, f))
        for f in os.listdir(BOOKS_DIR)
        if f.endswith(".txt")
    )

    print()
    print(f"完成：{ok}/{len(GUTENBERG_IDS)} 本，合计 {total / 1024 / 1024:.1f} MB")
    print(f"存放位置：{os.path.normpath(BOOKS_DIR)}")
    print()
    print("接下来跑 reset_catalog.py 把书目写进图书馆：")
    print("    python3 tools/reset_catalog.py --apply")

    return 0 if ok == len(GUTENBERG_IDS) else 1


if __name__ == "__main__":
    sys.exit(main())
