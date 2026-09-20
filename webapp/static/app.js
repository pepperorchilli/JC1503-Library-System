// 图书管理前端逻辑
//
// 与全站账号系统打通：借阅人就是当前登录的账号，不再需要「选择我是谁」。

const API = '/library/api';

let state = { account: null, books: [], myLoans: [], history: [] };
let isAdmin = false;

// ---------- 工具 ----------

function $(id) { return document.getElementById(id); }

/** 转义 HTML，防止书名/昵称里写 <script> 被执行 */
function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

let toastTimer = null;
function toast(msg, ok = true) {
  const el = $('toast');
  el.textContent = msg;
  el.className = 'show ' + (ok ? 'ok' : 'err');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, 2600);
}

/** 请求封装：非 2xx 时抛出后端返回的错误消息 */
async function api(path, body) {
  const opts = body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : {};
  const res = await fetch(API + path, opts);
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    location.href = '/login?next=' + encodeURIComponent(location.pathname);
    throw new Error('需要登录');
  }
  if (!res.ok) throw new Error(data.error || `请求失败（HTTP ${res.status}）`);
  return data;
}

// ---------- 加载与渲染 ----------

async function load() {
  try {
    state = await api('/state');
    isAdmin = state.account && state.account.role === 'admin';
    render();
  } catch (e) {
    if (e.message !== '需要登录') toast('加载失败：' + e.message, false);
  }
}

function render() {
  renderUserBar();
  renderBooks();
  renderLoans();
  renderHistory();
}

function renderUserBar() {
  const a = state.account;
  if (!a) return;

  const badge = isAdmin ? '<span class="badge">管理员</span>' : '';
  $('userbar').innerHTML =
    '<span class="uname">' + esc(a.nickname) + '</span>' + badge +
    '<button class="sm" onclick="doLogout()">退出</button>';

  // 管理员才显示管理面板与添加按钮
  $('admin-panel').style.display = isAdmin ? '' : 'none';
  $('btn-toggle-add').style.display = isAdmin ? '' : 'none';
}

function renderBooks() {
  $('books-count').textContent = `共 ${state.books.length} 种`;

  if (!state.books.length) {
    $('books').innerHTML = '<div class="empty">还没有图书</div>';
    return;
  }

  const loaned = new Set(state.myLoans);

  const rows = state.books.map(b => {
    const isMag = b.type === 'Magazine';
    const out = b.available_copies === 0;
    const tag = isMag ? '<span class="tag mag">杂志</span>' : '<span class="tag">图书</span>';
    const iBorrowed = loaned.has(b.title);

    // 「还」只对自己借过的书可用 —— 否则点了会报「你没有借阅这本书」
    const delBtn = isAdmin
      ? `<button class="sm danger" data-delbook="${esc(b.title)}">删</button>`
      : '';

    return `<tr>
      <td class="title-cell">${esc(b.title)}${iBorrowed ? ' <span class="tag mine">已借</span>' : ''}</td>
      <td>${tag}</td>
      <td class="stock${out ? ' out' : ''}">${b.available_copies}/${b.total_copies}</td>
      <td>
        <button class="sm" data-borrow="${esc(b.title)}"${out || iBorrowed ? ' disabled' : ''}>借</button>
        <button class="sm" data-return="${esc(b.title)}"${iBorrowed ? '' : ' disabled'}>还</button>
        ${delBtn}
      </td>
    </tr>`;
  }).join('');

  $('books').innerHTML = `
    <table class="table">
      <thead><tr><th>书名</th><th>类型</th><th>可借/总数</th><th>操作</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderLoans() {
  $('loans-count').textContent = state.myLoans.length ? `${state.myLoans.length} 本` : '';

  if (!state.myLoans.length) {
    $('loans').innerHTML = '<div class="empty">还没借书</div>';
    return;
  }

  $('loans').innerHTML = state.myLoans.map(t =>
    `<div class="loan-item">
      <span class="loan-title">${esc(t)}</span>
      <button class="sm" data-return="${esc(t)}">归还</button>
    </div>`
  ).join('');
}

const ACTION_LABEL = {
  add_book: '新增图书', delete_book: '删除图书',
  borrow: '借阅', return: '归还', join_waitlist: '排队',
  add_user: '新增用户', delete_user: '删除用户',
};

function renderHistory() {
  if (!isAdmin) return;
  const h = state.history || [];
  $('history-count').textContent = h.length ? `共 ${h.length} 条` : '';

  if (!h.length) {
    $('history').innerHTML = '<div class="empty">还没有操作</div>';
    return;
  }

  $('history').innerHTML = h.slice(-20).reverse().map((a, i) => {
    const parts = [];
    if (a.user_id) parts.push(esc(a.user_id));
    if (a.item_title) parts.push('《' + esc(a.item_title) + '》');
    const label = ACTION_LABEL[a.action_type] || a.action_type;
    return `<div class="history-item">
      <span class="idx">${h.length - i}</span>
      <span class="type">${esc(label)}</span>${parts.join(' ')}
    </div>`;
  }).join('');
}

// ---------- 动作 ----------

async function doBorrow(title) {
  try {
    const r = await api('/borrow', { title });
    toast(r.message);
    await load();
  } catch (e) {
    // 无库存时后端提示可加入等待队列
    if (e.message.includes('等待队列')) {
      if (confirm(e.message)) {
        try {
          const r = await api('/borrow', { title, join_waitlist: true });
          toast(r.message);
          await load();
        } catch (e2) { toast(e2.message, false); }
      }
    } else {
      toast(e.message, false);
    }
  }
}

async function doReturn(title) {
  try {
    const r = await api('/return', { title });
    toast(r.message);
    await load();
  } catch (e) {
    toast(e.message, false);
  }
}

async function doUndo() {
  try {
    const r = await api('/undo', {});
    toast(r.message);
    await load();
  } catch (e) {
    toast(e.message, false);
  }
}

async function doDeleteBook(title) {
  if (!confirm(`确定删除《${title}》？`)) return;
  try {
    const r = await api('/books/delete', { title });
    toast(r.message);
    await load();
  } catch (e) {
    toast(e.message, false);
  }
}

async function doAddBook() {
  const payload = {
    kind: $('add-kind').value,
    resource_id: $('add-id').value.trim(),
    title: $('add-title').value.trim(),
    total_copies: $('add-total').value,
    author: $('add-author').value.trim(),
    isbn: $('add-isbn').value.trim(),
  };
  try {
    const r = await api('/books', payload);
    toast(r.message);
    $('add-panel').style.display = 'none';
    ['add-id', 'add-title', 'add-author', 'add-isbn'].forEach(k => { $(k).value = ''; });
    await load();
  } catch (e) {
    toast(e.message, false);
  }
}

/** 退出登录调的是 Node 端的接口（账号系统在那边） */
async function doLogout() {
  try { await fetch('/api/logout', { method: 'POST' }); } catch (e) { /* 忽略 */ }
  location.href = '/';
}

// ---------- 事件（用委托，列表重绘后依然有效）----------

document.addEventListener('click', e => {
  const t = e.target;
  if (t.dataset.borrow) return doBorrow(t.dataset.borrow);
  if (t.dataset.return) return doReturn(t.dataset.return);
  if (t.dataset.delbook) return doDeleteBook(t.dataset.delbook);
  if (t.id === 'btn-undo') return doUndo();
  if (t.id === 'btn-add-submit') return doAddBook();
  if (t.id === 'btn-add-cancel') { $('add-panel').style.display = 'none'; return; }
  if (t.id === 'btn-toggle-add') {
    const p = $('add-panel');
    p.style.display = p.style.display === 'none' ? 'block' : 'none';
  }
});

load();
