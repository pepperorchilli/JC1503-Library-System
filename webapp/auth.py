"""
全站账号鉴权（与 Node 端共用一套账号）

会话存在 MySQL 的 sessions 表里（由 robot-arm 的 server 写入），
本模块直接查同一张表校验 token —— **不需要服务间调用**，
两个服务天然共享登录状态。

sessions / accounts 两张表的定义见 robot-arm 仓库的 server/schema.sql。
"""

import os
import urllib.parse

import pymysql
from flask import redirect, request

# ---------- 数据库配置（与 Node 端一致，走环境变量）----------

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ.get("DB_USER", "arm_app"),
    "password": os.environ.get("DB_PASSWORD", "arm_dev_password"),
    "database": os.environ.get("DB_NAME", "robot_arm"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": True,
}

COOKIE_NAME = "arm_token"


def _connect():
    """
    每次请求新建连接。

    对个人站点这种低并发场景足够，也避免了连接池的复杂度。
    将来访问量上来了再换 DBUtils.PooledDB 即可。
    """
    return pymysql.connect(**DB_CONFIG)


def current_account():
    """
    从 cookie 里的 token 查出当前账号。

    返回 {'username','nickname','role'} 或 None（未登录/会话过期）。
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    try:
        conn = _connect()
    except pymysql.MySQLError:
        # 数据库连不上时按未登录处理，避免整个服务 500
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.username, a.nickname, a.role
                  FROM sessions s
                  JOIN accounts a ON a.id = s.account_id
                 WHERE s.token = %s AND s.expire_at > NOW()
                """,
                (token,),
            )
            row = cur.fetchone()
            return row or None
    except pymysql.MySQLError:
        return None
    finally:
        conn.close()


def login_redirect():
    """跳转到统一登录页，并带上返回地址"""
    nxt = urllib.parse.quote(request.full_path if request.query_string else request.path)
    return redirect(f"/login?next={nxt}")
