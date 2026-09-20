#!/usr/bin/env python3
"""
把图书馆的藏书替换成真实教材

原来的 60 本（Book_Title_1 … Magazine_Title_20）是课程作业的占位数据，
没有实际意义。这里替换成本人桌面「教材」文件夹里的真实书目。

同时清理掉 30 个虚拟用户（U001~U030）—— 网站上线后，
借阅人应该是站点的真实账号，虚拟用户没有意义了。

用法：
    python3 tools/reset_catalog.py              # 预览将要写入的内容
    python3 tools/reset_catalog.py --apply      # 真正写入
"""

import argparse
import json
import os
import sys

DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "library_data.json"
)

# ---------------------------------------------------------------
# 真实教材清单
#
# 来源：~/Desktop/教材/ 下的电子书
# 同一本书的中英文版、上下册分别建档（确实是不同的书）
# ---------------------------------------------------------------
CATALOG = [
    # ---- 数学 ----
    ("B001", "离散数学及其应用（第8版）", "Kenneth H. Rosen", 3),
    ("B002", "Discrete Mathematics and Its Applications (8th Edition)", "Kenneth H. Rosen", 2),
    ("B003", "微积分（上册）", "James Stewart", 3),
    ("B004", "微积分（下册）", "James Stewart", 3),
    ("B005", "Calculus (7th Edition)", "James Stewart", 2),
    ("B006", "线性代数及其应用（第5版）", "David C. Lay", 3),
    ("B007", "线性代数及其应用·答案手册", "David C. Lay", 2),

    # ---- 计算机 ----
    ("B008", "计算机组成与设计：硬件软件接口（RISC-V版·第5版）",
     "David A. Patterson / John L. Hennessy", 3),
    ("B009", "计算机科学概论（第13版）", "J. Glenn Brookshear", 3),
    ("B010", "计算机科学概论（第13版）·习题与答案", "J. Glenn Brookshear", 2),
    ("B011", "Head First Java（第二版）", "Kathy Sierra / Bert Bates", 3),

    # ---- 通识 ----
    ("B012", "毛泽东思想和中国特色社会主义理论体系概论（2023年版）", "本书编写组", 5),
]


def make_book(resource_id, title, author, total):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="真正写入（不加此参数只预览）")
    parser.add_argument("--keep-users", action="store_true",
                        help="保留虚拟用户 U001~U030（默认会清掉）")
    args = parser.parse_args()

    path = os.path.normpath(DATA_FILE)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"users": [], "books": []}

    old_books = data.get("books", [])
    old_users = data.get("users", [])

    # ---- 新藏书 ----
    data["books"] = [make_book(*item) for item in CATALOG]

    # ---- 用户：只保留真实账号（站点账号的用户名不是 U0xx 形式）----
    if args.keep_users:
        kept_users = old_users
    else:
        kept_users = [u for u in old_users if not u["user_id"].startswith("U0")]

    data["users"] = kept_users

    print("=" * 56)
    print("  藏书替换预览")
    print("=" * 56)
    print(f"\n图书：{len(old_books)} 本  →  {len(data['books'])} 本\n")
    for b in data["books"]:
        print(f"  {b['resource_id']}  {b['title']}")
        print(f"        {b['author']}   共 {b['total_copies']} 册")

    removed = len(old_users) - len(kept_users)
    print(f"\n用户：{len(old_users)} 个  →  {len(kept_users)} 个"
          + (f"（清掉 {removed} 个虚拟用户）" if removed else ""))
    for u in kept_users:
        print(f"  {u['user_id']}  {u['name']}")

    if not args.apply:
        print("\n（预览模式，未写入。加 --apply 才会真正保存）")
        return

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已写入 {path}")
    print("   ⚠️ 图书管理服务会读同一个文件，如果服务在跑，需要重启它才生效")


if __name__ == "__main__":
    sys.exit(main())
