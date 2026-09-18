"""
Service 层：图书管理的业务逻辑

从 src/main.py 的 LibSys 类中提取而来，但做了三处关键改动：

  1. **不含 input() / print()** —— 参数从方法签名传入，结果用返回值或异常表达。
     原 LibSys 把「读输入 → 改数据 → 打印结果」揉在一个方法里，
     Web 层无法复用，所以必须拆开。

  2. **不再 sys.exit()** —— 原 exit_system() 会杀死进程，
     Web 服务下等于自杀。

  3. **持久化改为写时保存** —— 原版只在退出时保存一次，
     Web 服务长期驻留，进程崩溃会丢掉全部数据，所以每次变更后立即落盘。

原有的数据结构（HashTable / BST / Stack）和模型（User / Book / Magazine）
**原封不动复用**，见 src/ 目录。
"""

import os
import sys

# ---- 让 src/ 下的模块可以被导入 ----
# src/ 内部用的是 `from utils.storage import ...` 这种相对项目根的写法，
# 所以必须把 src/ 本身加进 sys.path
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from utils.storage import Storage                        # noqa: E402
from utils.exceptions import (                           # noqa: E402
    LibraryBaseException,
    ItemNotFoundError,
    DuplicateItemError,
    OutOfStockError,
)
from structures.stack import Stack                       # noqa: E402
from models.user import User                             # noqa: E402
from models.resource import Book, Magazine               # noqa: E402


class ServiceError(LibraryBaseException):
    """Service 层对外抛出的业务异常，携带可直接展示给用户的中文消息"""


class LibraryService:
    def __init__(self):
        self.users, self.books = Storage.load_data()
        self.history_stack = Stack()

    # ================= 内部工具 =================

    def _save(self):
        """每次变更后立即落盘（原版只在退出时保存）"""
        Storage.save_data(self.users, self.books)

    def _push_history(self, action_type, **fields):
        self.history_stack.push({"action_type": action_type, **fields})

    # ================= 查询 =================

    def list_books(self):
        """图书列表（BST 中序遍历，按标题字母序）"""
        return [item.to_dict() for item in self.books.to_list()]

    def list_users(self):
        """用户列表"""
        return [user.to_dict() for user in self.users.to_list()]

    def history(self):
        """
        操作历史，最新的在最前面。

        实现沿用了原版的「双栈倒腾」——既完成遍历，又不破坏原栈状态。
        """
        result = []
        temp_stack = Stack()

        while self.history_stack.item_count > 0:
            action = self.history_stack.pop()
            result.append(self._public_action(action))
            temp_stack.push(action)

        while temp_stack.item_count > 0:
            self.history_stack.push(temp_stack.pop())

        result.reverse()   # 最新的排前面
        return result

    @staticmethod
    def _public_action(action):
        """
        历史记录里可能存着 Python 对象（删除操作为了支持撤销会暂存原对象），
        这些不能直接序列化成 JSON，对外只暴露可读的字段。
        """
        public = {}
        for key, value in action.items():
            if key.endswith("_obj"):        # user_obj / item_obj 不对外
                continue
            public[key] = value
        return public

    # ================= 用户 =================

    def add_user(self, user_id, name):
        user_id = (user_id or "").strip()
        name = (name or "").strip()

        if not user_id or not name:
            raise ServiceError("用户 ID 和姓名都不能为空")

        try:
            self.users.insert(user_id, User(user_id, name))
        except DuplicateItemError:
            raise ServiceError(f"用户 ID「{user_id}」已存在")

        self._push_history("add_user", user_id=user_id)
        self._save()
        return {"ok": True, "message": f"已添加用户 {name}（{user_id}）"}

    def delete_user(self, user_id):
        user_id = (user_id or "").strip()
        if not user_id:
            raise ServiceError("请提供用户 ID")

        try:
            user_obj = self.users.get(user_id)
        except ItemNotFoundError:
            raise ServiceError(f"找不到用户「{user_id}」")

        # 有未归还的书不允许删除
        if len(user_obj.borrowed_items) > 0:
            raise ServiceError(f"用户 {user_obj.name} 还有 {len(user_obj.borrowed_items)} 本未归还，无法删除")

        self.users.remove(user_id)
        # 暂存原对象，供撤销时恢复
        self._push_history("delete_user", user_id=user_id, user_obj=user_obj)
        self._save()
        return {"ok": True, "message": f"已删除用户 {user_obj.name}"}

    # ================= 图书 =================

    def add_book(self, kind, resource_id, title, total_copies,
                 author=None, isbn=None, issue_number=None):
        """
        kind: "Book" 或 "Magazine"
        """
        resource_id = (resource_id or "").strip()
        title = (title or "").strip()

        if not resource_id or not title:
            raise ServiceError("图书编号和标题都不能为空")

        try:
            total = int(total_copies)
        except (TypeError, ValueError):
            raise ServiceError("总册数必须是整数")

        if total <= 0:
            raise ServiceError("总册数必须大于 0")

        if kind == "Magazine":
            item = Magazine(resource_id, title, total, issue_number or "-")
        else:
            item = Book(resource_id, title, total, author or "-", isbn or "-")

        # BST 的 insert 遇到相同标题会静默覆盖，这里先查一次，避免用户以为新增成功
        try:
            self.books.search(title)
            raise ServiceError(f"标题「{title}」已存在")
        except ItemNotFoundError:
            pass   # 不存在才是正常的

        self.books.insert(title, item)
        self._push_history("add_book", item_title=title)
        self._save()
        return {"ok": True, "message": f"已添加《{title}》，共 {total} 册"}

    def delete_book(self, title):
        title = (title or "").strip()
        if not title:
            raise ServiceError("请提供书名")

        try:
            item = self.books.search(title)
        except ItemNotFoundError:
            raise ServiceError(f"找不到《{title}》")

        if item.available_copies != item.total_copies:
            raise ServiceError(f"《{title}》还有 {item.total_copies - item.available_copies} 册未归还，无法删除")

        if not item.waitlist.is_empty():
            raise ServiceError(f"《{title}》还有人在排队等待，无法删除")

        self.books.remove(title)
        self._push_history("delete_book", item_title=title, item_obj=item)
        self._save()
        return {"ok": True, "message": f"已删除《{title}》"}

    # ================= 借还 =================

    def borrow(self, user_id, title, join_waitlist=False):
        """
        借书。

        无库存时：
          - join_waitlist=True  → 加入等待队列，返回成功
          - join_waitlist=False → 抛 OutOfStockError，由前端提示是否排队
        """
        user_id = (user_id or "").strip()
        title = (title or "").strip()

        if not user_id or not title:
            raise ServiceError("用户 ID 和书名都不能为空")

        try:
            user = self.users.get(user_id)
        except ItemNotFoundError:
            raise ServiceError(f"找不到用户「{user_id}」")

        try:
            book = self.books.search(title)
        except ItemNotFoundError:
            raise ServiceError(f"找不到《{title}》")

        try:
            book.borrow_item()
        except OutOfStockError:
            if join_waitlist:
                book.waitlist.enqueue(user_id)
                self._push_history("join_waitlist", user_id=user_id, item_title=title)
                self._save()
                return {"ok": True, "message": f"《{title}》已借完，你已加入等待队列"}
            raise ServiceError(f"《{title}》已全部借出，是否加入等待队列？")

        user.borrow_book(title)
        self._push_history("borrow", user_id=user_id, item_title=title)
        self._save()
        return {"ok": True, "message": f"{user.name} 借阅《{title}》成功"}

    def return_book(self, user_id, title):
        """
        还书。若有等待队列，自动把书分配给队首用户。

        这一整套是原 LibSys.return_item() 的逻辑，只是不再 print。
        """
        user_id = (user_id or "").strip()
        title = (title or "").strip()

        if not user_id or not title:
            raise ServiceError("用户 ID 和书名都不能为空")

        try:
            user = self.users.get(user_id)
        except ItemNotFoundError:
            raise ServiceError(f"找不到用户「{user_id}」")

        try:
            book = self.books.search(title)
        except ItemNotFoundError:
            raise ServiceError(f"找不到《{title}》")

        if not user.return_book(title):
            raise ServiceError(f"{user.name} 没有借阅《{title}》")

        next_borrower = book.return_item()
        message = f"{user.name} 归还《{title}》成功"

        # 有等待队列 → 自动分配给队首用户
        if next_borrower is not None:
            try:
                next_user = self.users.get(next_borrower)
                next_user.borrow_book(title)
                message += f"；已自动分配给等待中的 {next_user.name}"
            except LibraryBaseException:
                message += "；但分配给等待用户时出错"

        self._push_history("return", user_id=user_id, item_title=title)
        self._save()
        return {"ok": True, "message": message}

    # ================= 撤销 =================

    def undo(self):
        """
        撤销最近一次操作。

        对应原 LibSys.undo_last_action()，逐个 action_type 走反向逻辑。
        """
        action = self.history_stack.pop()
        if action is None:
            raise ServiceError("没有可撤销的操作")

        action_type = action.get("action_type")

        try:
            if action_type == "add_user":
                self.users.remove(action["user_id"])
                message = f"已撤销：删除用户 {action['user_id']}"

            elif action_type == "add_book":
                self.books.remove(action["item_title"])
                message = f"已撤销：删除《{action['item_title']}》"

            elif action_type == "delete_user":
                obj = action["user_obj"]
                self.users.insert(obj.user_id, obj)
                message = f"已撤销：恢复用户 {obj.name}"

            elif action_type == "delete_book":
                obj = action["item_obj"]
                self.books.insert(obj.title, obj)
                message = f"已撤销：恢复《{obj.title}》"

            elif action_type == "borrow":
                user = self.users.get(action["user_id"])
                book = self.books.search(action["item_title"])
                if not user.return_book(action["item_title"]):
                    raise ServiceError("撤销失败：用户并没有借阅这本书")
                next_borrower = book.return_item()
                message = f"已撤销：{user.name} 的借阅"
                if next_borrower:
                    try:
                        self.users.get(next_borrower).borrow_book(action["item_title"])
                        message += "；已转给等待用户"
                    except LibraryBaseException:
                        message += "；转给等待用户时出错"

            elif action_type == "return":
                user = self.users.get(action["user_id"])
                book = self.books.search(action["item_title"])
                book.borrow_item()
                user.borrow_book(action["item_title"])
                message = f"已撤销：{user.name} 的归还（重新借出）"

            elif action_type == "join_waitlist":
                book = self.books.search(action["item_title"])
                # 从等待队列里移除（队列没有 remove，重建一个）
                remaining = [x for x in book.waitlist.to_list() if x != action["user_id"]]
                from structures.queue import Queue
                book.waitlist = Queue()
                for uid in remaining:
                    book.waitlist.enqueue(uid)
                message = f"已撤销：把 {action['user_id']} 移出《{action['item_title']}》的等待队列"

            else:
                raise ServiceError(f"未知的操作类型：{action_type}")

        except ItemNotFoundError as e:
            raise ServiceError(f"撤销失败：{e}")

        self._save()
        return {"ok": True, "message": message}


# 单例：Flask 应用共用一份内存数据
_service = None


def get_service():
    global _service
    if _service is None:
        _service = LibraryService()
    return _service
