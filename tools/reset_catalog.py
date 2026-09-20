#!/usr/bin/env python3
"""
重置图书馆藏书

两类书：

  1. 教材 —— 桌面「教材」目录里的真实书目，**只登记书目信息**。
     这些 PDF 来自 Z-Library 等盗版站，把全文放到公网属于侵权，
     所以只上架书名/作者，不放内容。

  2. 公版书 —— Project Gutenberg 的经典著作，著作权已过期，
     **可以合法地全文公开**。全文由 tools/fetch_gutenberg.py 下载到
     data/books/，读者可以在线阅读。

同时清理掉 30 个虚拟用户（U001~U030）—— 网站上线后，
借阅人应该是站点的真实账号。

用法：
    python3 tools/reset_catalog.py              # 预览
    python3 tools/reset_catalog.py --apply      # 写入
"""

import argparse
import json
import os
import sys

DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "library_data.json"
)
BOOKS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "books"
)

# ---------------------------------------------------------------
# 书目
#   (编号, 书名, 作者, 总册数, GutenbergID)
#   GutenbergID 为 None 表示没有全文，只有书目
# ---------------------------------------------------------------
CATALOG = [
    # ==================== 教材（仅书目）====================
    ("B001", "离散数学及其应用（第8版）", "Kenneth H. Rosen", 3, None),
    ("B002", "Discrete Mathematics and Its Applications (8th Edition)", "Kenneth H. Rosen", 2, None),
    ("B003", "微积分（上册）", "James Stewart", 3, None),
    ("B004", "微积分（下册）", "James Stewart", 3, None),
    ("B005", "Calculus (7th Edition)", "James Stewart", 2, None),
    ("B006", "线性代数及其应用（第5版）", "David C. Lay", 3, None),
    ("B007", "线性代数及其应用·答案手册", "David C. Lay", 2, None),
    ("B008", "计算机组成与设计：硬件软件接口（RISC-V版·第5版）",
     "David A. Patterson / John L. Hennessy", 3, None),
    ("B009", "计算机科学概论（第13版）", "J. Glenn Brookshear", 3, None),
    ("B010", "计算机科学概论（第13版）·习题与答案", "J. Glenn Brookshear", 2, None),
    ("B011", "Head First Java（第二版）", "Kathy Sierra / Bert Bates", 3, None),
    ("B012", "毛泽东思想和中国特色社会主义理论体系概论（2023年版）", "本书编写组", 5, None),

    # ==================== 中文公版书（可全文阅读）====================
    ("G001", "紅樓夢", "曹雪芹", 99, 24264),
    ("G002", "三國志演義", "羅貫中", 99, 23950),
    ("G003", "漢書", "班固", 99, 23841),
    ("G004", "禮記", "（先秦）", 99, 24048),
    ("G005", "詩經", "（先秦）", 99, 23873),
    ("G006", "易經", "（先秦）", 99, 25501),
    ("G007", "山海經", "（先秦）", 99, 25288),
    ("G008", "今古奇觀", "抱甕老人", 99, 24230),
    ("G009", "燕丹子", "（漢）", 99, 24068),
    ("G010", "三字經", "王應麟", 99, 12479),

    # ==================== 英文公版书（可全文阅读）====================
    ("G011", "Pride and Prejudice", "Jane Austen", 99, 1342),
    ("G012", "Alice's Adventures in Wonderland", "Lewis Carroll", 99, 11),
    ("G013", "Frankenstein", "Mary Shelley", 99, 84),
    ("G014", "The Adventures of Sherlock Holmes", "Arthur Conan Doyle", 99, 1661),
    ("G015", "Romeo and Juliet", "William Shakespeare", 99, 1513),
    ("G016", "A Tale of Two Cities", "Charles Dickens", 99, 98),
]


def make_book(resource_id, title, author, total, gut_id):
    """
    注意：这里**不能**往 book 里塞自定义字段。

    图书系统的 Book.to_dict() 只输出固定字段，加载时走 from_dict()，
    额外的键会在「保存→读取」过程中被丢掉（实际踩过这个坑）。
    所以「哪些书有全文」单独写在 data/readable.json 里，
    由 Flask 读那份映射表 —— 也就不需要改组员的数据模型。
    """
    return {
        "resource_id": resource_id,
        "title": title,
        "total_copies": total,
        "available_copies": total,
        "waitlist": [],
        "type": "Book",
        "is_available_status": total > 0,
        "author": author,
        "isbn": "-",
        "is_fiction_book": False,
    }


def make_readable_map():
    """resource_id → 全文文件信息（供 Flask 在线阅读用）"""
    result = {}
    for resource_id, title, _author, _total, gut_id in CATALOG:
        if not gut_id:
            continue
        result[resource_id] = {
            "file": f"{gut_id}.txt",
            "source": f"Project Gutenberg #{gut_id}",
            "source_url": f"https://www.gutenberg.org/ebooks/{gut_id}",
            "title": title,
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正写入")
    parser.add_argument("--keep-users", action="store_true",
                        help="保留虚拟用户 U001~U030")
    args = parser.parse_args()

    path = os.path.normpath(DATA_FILE)
    books_path = os.path.normpath(BOOKS_DIR)

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"users": [], "books": []}

    old_books = data.get("books", [])
    old_users = data.get("users", [])

    data["books"] = [make_book(*item) for item in CATALOG]

    if args.keep_users:
        kept_users = old_users
    else:
        kept_users = [u for u in old_users if not u["user_id"].startswith("U0")]
    data["users"] = kept_users

    readable_map = make_readable_map()

    # ---------- 预览 ----------
    textbooks = [b for b in data["books"] if b["resource_id"] not in readable_map]
    readable = [b for b in data["books"] if b["resource_id"] in readable_map]

    print("=" * 60)
    print("  藏书重置预览")
    print("=" * 60)

    print(f"\n【教材 · 仅书目】{len(textbooks)} 本")
    for b in textbooks:
        print(f"  {b['resource_id']}  {b['title']}")

    print(f"\n【公版书 · 可全文阅读】{len(readable)} 本")
    missing = 0
    for b in readable:
        fp = os.path.join(books_path, readable_map[b["resource_id"]]["file"])
        exists = os.path.exists(fp)
        if not exists:
            missing += 1
        size = f"{os.path.getsize(fp) // 1024}KB" if exists else "❌ 文件缺失"
        print(f"  {b['resource_id']}  {b['title'][:34]:<36} {size}")

    if missing:
        print(f"\n  ⚠️ 有 {missing} 本缺全文文件，先跑 tools/fetch_gutenberg.py")

    removed = len(old_users) - len(kept_users)
    print(f"\n【用户】{len(old_users)} → {len(kept_users)}"
          + (f"（清掉 {removed} 个虚拟用户）" if removed else ""))
    for u in kept_users:
        print(f"  {u['user_id']}  {u['name']}")

    print(f"\n合计：{len(old_books)} 本 → {len(data['books'])} 本")

    if not args.apply:
        print("\n（预览模式，未写入。加 --apply 才会真正保存）")
        return 0

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 藏书已写入 {path}")

    # 全文映射单独存一份（不能塞进 library_data.json，见 make_book 的注释）
    readable_path = os.path.normpath(
        os.path.join(os.path.dirname(path), "readable.json")
    )
    with open(readable_path, "w", encoding="utf-8") as f:
        json.dump(readable_map, f, ensure_ascii=False, indent=2)
    print(f"✅ 全文映射已写入 {readable_path}（{len(readable_map)} 本可在线阅读）")

    print("\n   ⚠️ 图书管理服务若在运行，需重启才生效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
