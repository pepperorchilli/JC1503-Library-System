"""
图书管理系统 Web 版 —— Flask 应用入口

设计要点见 ../技术文档.md，这里只说三件事：

1. **不改动 src/ 下的原有代码**
   组员的模型层和数据结构层原封不动复用，Web 化的工作全部收在 webapp/ 里。
   这样 fork 和上游的差异最小，以后同步同学的更新不会冲突。

2. **屏蔽模型层遗留的 print()**
   src/ 下的代码有大量 print（main.py 57 处、tree.py 36 处、bst.py 20 处……），
   直接跑 Web 服务会把日志刷爆。这里把 stdout 重定向掉，
   Flask 自己的日志走 stderr，不受影响。
   ⚠️ 这是权宜之计，彻底清理 print 留作后续改进。

3. **异常映射**
   Service 层抛 ServiceError，这里统一转成 HTTP 400 + JSON，前端直接展示 message。

运行：
    python webapp/app.py          # 开发模式，:5000
    gunicorn -w 2 -b 0.0.0.0:5000 app:app    # 生产模式
"""

import io
import os
import sys

# ---- 屏蔽 src/ 下遗留的 print（必须在导入业务模块之前执行）----
sys.stdout = io.StringIO()

from flask import Flask, jsonify, render_template, request   # noqa: E402
from werkzeug.exceptions import HTTPException                # noqa: E402

from service import get_service, ServiceError                # noqa: E402

# static_url_path 必须显式指定：默认是 /static，但整个模块挂在 /library/ 下
app = Flask(__name__, static_url_path="/library/static")


# ================= 统一错误处理 =================

@app.errorhandler(ServiceError)
def handle_service_error(err):
    """Service 层的业务异常 → 400 + 可读消息"""
    return jsonify({"ok": False, "error": str(err)}), 400


@app.errorhandler(Exception)
def handle_unexpected(err):
    """
    兜底：未预期的异常也返回 JSON，而不是 HTML 错误页。

    ⚠️ 必须放行 HTTPException —— 否则 404 / 405 这类正常的 HTTP 错误
    会被这里吞掉统一变成 500，掩盖真正的问题。
    """
    if isinstance(err, HTTPException):
        return err
    app.logger.exception("未处理的异常")
    return jsonify({"ok": False, "error": "服务器内部错误"}), 500


# ================= 页面 =================

@app.route("/library/")
@app.route("/library")
def index():
    return render_template("index.html")


# ================= 查询接口 =================

@app.route("/library/api/state")
def api_state():
    """页面初始化：一次性拿到图书 + 用户 + 历史"""
    svc = get_service()
    return jsonify({
        "books": svc.list_books(),
        "users": svc.list_users(),
        "history": svc.history(),
    })


@app.route("/library/api/books")
def api_books():
    return jsonify(get_service().list_books())


@app.route("/library/api/users")
def api_users():
    return jsonify(get_service().list_users())


@app.route("/library/api/history")
def api_history():
    return jsonify(get_service().history())


# ================= 用户操作 =================

@app.route("/library/api/users", methods=["POST"])
def api_add_user():
    data = request.get_json(silent=True) or {}
    result = get_service().add_user(data.get("user_id"), data.get("name"))
    return jsonify(result)


@app.route("/library/api/users/delete", methods=["POST"])
def api_delete_user():
    data = request.get_json(silent=True) or {}
    result = get_service().delete_user(data.get("user_id"))
    return jsonify(result)


# ================= 图书操作 =================

@app.route("/library/api/books", methods=["POST"])
def api_add_book():
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
    data = request.get_json(silent=True) or {}
    result = get_service().delete_book(data.get("title"))
    return jsonify(result)


# ================= 借还 =================

@app.route("/library/api/borrow", methods=["POST"])
def api_borrow():
    data = request.get_json(silent=True) or {}
    result = get_service().borrow(
        user_id=data.get("user_id"),
        title=data.get("title"),
        join_waitlist=bool(data.get("join_waitlist")),
    )
    return jsonify(result)


@app.route("/library/api/return", methods=["POST"])
def api_return():
    data = request.get_json(silent=True) or {}
    result = get_service().return_book(data.get("user_id"), data.get("title"))
    return jsonify(result)


# ================= 撤销 =================

@app.route("/library/api/undo", methods=["POST"])
def api_undo():
    return jsonify(get_service().undo())


# ================= 启动 =================

if __name__ == "__main__":
    # 默认 5001 而非 Flask 惯用的 5000 —— macOS 的「AirPlay 接收器」会占用 5000，
    # 导致服务起不来（表现为所有请求返回 403）。Linux 上两个端口都空闲。
    port = int(os.environ.get("LIBRARY_PORT", 5001))
    print(f"图书管理系统已启动: http://localhost:{port}/library/", file=sys.stderr)
    app.run(host="0.0.0.0", port=port, debug=False)
