"""
图书管理系统 Web 版 —— Flask 应用入口

2026-09 更新：接入全站账号系统
    不再有「选择我是谁」—— 直接用登录的站点账号当借阅人。
    会话与 Node 端共用 MySQL 的 sessions 表，无需服务间调用。

设计要点：

1. **不改动 src/ 下的原有代码**
   组员的模型层和数据结构层原封不动复用，Web 化工作全收在 webapp/ 里。

2. **屏蔽模型层遗留的 print()**
   src/ 下有大量 print（main.py 57 处、tree.py 36 处…），
   直接跑 Web 服务会刷爆日志。这里把 stdout 重定向掉，
   Flask 自己的日志走 stderr，不受影响。

运行：
    python webapp/app.py                       # 开发模式
    gunicorn -w 1 -b 127.0.0.1:5001 app:app    # 生产模式
"""

import io
import json
import os
import sys

# ---- 屏蔽 src/ 下遗留的 print（必须在导入业务模块之前执行）----
sys.stdout = io.StringIO()

from flask import (                                             # noqa: E402
    Flask, Response, g, jsonify, render_template, request,
)
from werkzeug.exceptions import HTTPException                   # noqa: E402

from auth import current_account, login_redirect                # noqa: E402
from service import get_service, ServiceError                   # noqa: E402

app = Flask(__name__, static_url_path="/library/static")

# 公版书全文的存放目录（由 tools/fetch_gutenberg.py 下载）
BOOKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "data", "books")

# 「哪些书有全文」的映射表，由 tools/reset_catalog.py 生成
#
# 为什么不直接写在 library_data.json 里：图书系统的 Book.to_dict()
# 只输出固定字段，自定义键会在保存→读取时被丢掉（实际踩过）。
# 所以单独存一份，也就不需要改动组员的数据模型。
READABLE_MAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "data", "readable.json")


def load_readable_map():
    path = os.path.normpath(READABLE_MAP_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"读取 readable.json 失败：{e}", file=sys.stderr)
        return {}


# ================= 登录守卫 =================
#
# 除静态资源外，整个模块都要求登录。
# 未登录直接跳到统一的登录页 /login，登录后会跳回来。

@app.before_request
def require_login():
    if request.path.startswith("/library/static/"):
        return None                      # 静态资源放行

    account = current_account()
    if account is None:
        return login_redirect()

    g.account = account                  # 后续路由直接用 g.account


def is_admin():
    return getattr(g, "account", {}).get("role") == "admin"


def require_admin():
    """非管理员则抛出业务异常"""
    if not is_admin():
        raise ServiceError("需要管理员权限")


# ================= 统一错误处理 =================

@app.errorhandler(ServiceError)
def handle_service_error(err):
    return jsonify({"ok": False, "error": str(err)}), 400


@app.errorhandler(Exception)
def handle_unexpected(err):
    """兜底：未预期的异常也返回 JSON。必须放行 HTTPException，否则 404 会变成 500"""
    if isinstance(err, HTTPException):
        return err
    app.logger.exception("未处理的异常")
    return jsonify({"ok": False, "error": "服务器内部错误"}), 500


# ================= 页面 =================

@app.route("/library/")
@app.route("/library")
def index():
    return render_template("index.html")


# ================= 查询 =================

@app.route("/library/api/state")
def api_state():
    """
    页面初始化：当前账号 + 图书列表 + 我的借阅 +（管理员才有的）操作历史
    """
    svc = get_service()
    account = g.account

    # 确保当前账号在图书系统里有档案（首次访问自动建立）
    svc.ensure_user(account["username"], account["nickname"])

    # 给有全文的书补上 readable 标记，前端据此显示「阅读」按钮
    readable_map = load_readable_map()
    books = svc.list_books()
    for b in books:
        if b["resource_id"] in readable_map:
            b["readable"] = True

    data = {
        "account": account,
        "books": books,
        "myLoans": svc.my_loans(account["username"]),
    }

    if is_admin():
        data["history"] = svc.history()   # 操作历史是全局的，仅管理员可见

    return jsonify(data)


# ================= 借还 =================

@app.route("/library/api/borrow", methods=["POST"])
def api_borrow():
    data = request.get_json(silent=True) or {}
    svc = get_service()
    account = g.account
    svc.ensure_user(account["username"], account["nickname"])

    result = svc.borrow(
        account["username"],
        data.get("title"),
        join_waitlist=bool(data.get("join_waitlist")),
    )
    return jsonify(result)


@app.route("/library/api/return", methods=["POST"])
def api_return():
    data = request.get_json(silent=True) or {}
    result = get_service().return_book(g.account["username"], data.get("title"))
    return jsonify(result)


# ================= 管理员操作 =================

@app.route("/library/api/books", methods=["POST"])
def api_add_book():
    require_admin()
    data = request.get_json(silent=True) or {}
    result = get_service().add_book(
        kind=data.get("kind", "Book"),
        resource_id=data.get("resource_id"),
        title=data.get("title"),
        total_copies=data.get("total_copies"),
        author=data.get("author"),
        isbn=data.get("isbn"),
        issue_number=data.get("issue_number"),
    )
    return jsonify(result)


@app.route("/library/api/books/delete", methods=["POST"])
def api_delete_book():
    require_admin()
    data = request.get_json(silent=True) or {}
    return jsonify(get_service().delete_book(data.get("title")))


@app.route("/library/api/undo", methods=["POST"])
def api_undo():
    require_admin()
    return jsonify(get_service().undo())


@app.route("/library/api/history")
def api_history():
    require_admin()
    return jsonify(get_service().history())


# ================= 在线阅读（公版书）=================
#
# 只有公版书有全文 —— 教材那些 PDF 来自盗版站，只登记书目不放内容。
# 详见 tools/fetch_gutenberg.py 顶部的说明。

def find_book(resource_id):
    """按编号找书（书目在 BST 里是按书名索引的，所以遍历一遍）"""
    for b in get_service().list_books():
        if b.get("resource_id") == resource_id:
            return b
    return None


@app.route("/library/read/<resource_id>")
def read_book(resource_id):
    book = find_book(resource_id)
    if not book:
        raise ServiceError(f"找不到编号为 {resource_id} 的书")

    info = load_readable_map().get(resource_id)
    if not info:
        raise ServiceError(f"《{book['title']}》只有书目信息，没有可阅读的全文")

    title = book["title"]
    # 用标题里有没有汉字判断该用哪种排版（中文首行缩进，英文不缩进）
    is_chinese = any('一' <= ch <= '鿿' for ch in title)

    return render_template(
        "reader.html",
        title=title,
        author=book.get("author", ""),
        source=info.get("source"),
        source_url=info.get("source_url"),
        resource_id=resource_id,
        is_chinese=is_chinese,
    )


@app.route("/library/api/book/<resource_id>/text")
def api_book_text(resource_id):
    info = load_readable_map().get(resource_id)
    if not info or not info.get("file"):
        return jsonify({"error": "这本书没有可阅读的全文"}), 404

    path = os.path.normpath(os.path.join(BOOKS_DIR, info["file"]))

    # 防目录穿越：拼出来的路径必须还在 books 目录里
    if not path.startswith(os.path.normpath(BOOKS_DIR) + os.sep):
        return jsonify({"error": "非法路径"}), 400
    if not os.path.isfile(path):
        return jsonify({"error": "正文文件缺失，请先跑 tools/fetch_gutenberg.py"}), 404

    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()

    # 剥掉 Project Gutenberg 的版权头尾，只留正文
    text = strip_gutenberg_boilerplate(text)

    return Response(text, mimetype="text/plain; charset=utf-8")


def strip_gutenberg_boilerplate(text):
    """
    Gutenberg 的 txt 在正文前后各有一段英文版权声明，
    用 *** START/END OF THE PROJECT GUTENBERG EBOOK *** 标记包着。
    阅读器里没必要显示，切掉。
    """
    start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"

    start = text.find(start_marker)
    if start != -1:
        nl = text.find("\n", start)
        text = text[nl + 1:] if nl != -1 else text

    end = text.find(end_marker)
    if end != -1:
        text = text[:end]

    return text.strip()


# ================= 启动 =================

if __name__ == "__main__":
    # 默认 5001 而非 Flask 惯用的 5000 —— macOS 的「AirPlay 接收器」会占用 5000
    port = int(os.environ.get("LIBRARY_PORT", 5001))
    print(f"图书管理系统已启动: http://localhost:{port}/library/", file=sys.stderr)
    app.run(host="0.0.0.0", port=port, debug=False)
