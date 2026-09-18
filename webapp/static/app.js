// 图书管理前端逻辑（原生 JS，无构建步骤）

const API = '/library/api';

// 当前操作身份，存 localStorage 免得刷新就丢
let currentUserId = localStorage.getItem('library_user') || '';
let state = { books: [], users: [], history: [] };

// ---------- 工具 ----------

function $(id) { return document.getElementById(id); }

/** 转义 HTML，防止书名/用户名里写 <script> 被执行 */
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

/** 统一的请求封装：非 2xx 时把后端的 error 消息抛出来 */
async function api(path, body) {
  const opts = body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : {};
  const res = await fetch(API + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `请求失败（HTTP ${res.status}）`);
  return data;
}

// ---------- 数据加载 ----------

async function load() {
  try {
    state = await api('/state');
    render();
  } catch (e) {
    toast('加载失败：' + e.message, false);
  }
}

// ---------- 渲染 ----------

function render() {
  renderBooks();
  renderUsers();
  renderHistory();
  renderUserSelect();
}

function renderUserSelect() {
  const sel = $('current-user');
  const opts = ['<option value="">（请选择身份）</option>']
    .concat(state.users.map(u =>
      `<option value="${esc(u.user_id)}"${u.user_id === currentUserId ? ' selected' : ''}>` +
      `${esc(u.name)}（${esc(u.user_id)}）</option>`));

  sel.innerHTML = opts.join('');

  // 之前选的身份如果被删了，清掉
  if (currentUserId && !state.users.some(u => u.user_id === currentUserId)) {
    currentUserId = '';
    localStorage.removeItem('library_user');
    sel.value = '';
  }
}

function renderBooks() {
  $('books-count').textContent = `共 ${state.books.length} 种`;

  if (!state.books.length) {
    $('books').innerHTML = '<div class="empty">还没有图书</div>';
    return;
  }

  const rows = state.books.map(b => {
    const isMag = b.type === 'Magazine';
    const out = b.available_copies === 0;
    const tag = isMag
      ? '<span class="tag mag">杂志</span>'
      : '<span class="tag">图书</span>';

    return `<tr>
      <td class="title-cell">${esc(b.title)}</td>
      <td>${tag}</td>
      <td class="stock${out ? ' out' : ''}">${b.available_copies}/${b.total_copies}</td>
      <td>
        <button class="sm" data-borrow="${esc(b.title)}"${out ? ' disabled' : ''}>借</button>
        <button class="sm" data-return="${esc(b.title)}">还</button>
      </td>
    </tr>`;
  }).join('');

  $('books').innerHTML = `
    <table class="table">
      <thead><tr><th>书名</th><th>类型</th><th>可借/总数</th><th>操作</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderUsers() {
  $('users-count').textContent = `共 ${state.users.length} 人`;

  if (!state.users.length) {
    $('users').innerHTML = '<div class="empty">还没有用户</div>';
    return;
  }

  $('users').innerHTML = state.users.map(u => {
    const n = u.borrowed_items.length;
    return `<div class="user-item">
      <span>
        <span class="name">${esc(u.name)}</span>
        <span class="id">${esc(u.user_id)}</span>
      </span>
      <span class="books">${n ? `借了 ${n} 本` : ''}
        <button class="sm danger" data-deluser="${esc(u.user_id)}" style="margin-left:6px">删</button>
      </span>
    </div>`;
  }).join('');
}

const ACTION_LABEL = {
  add_user: '新增用户', add_book: '新增图书',
  delete_user: '删除用户', delete_book: '删除图书',
  borrow: '借阅', return: '归还', join_waitlist: '排队',
};

function renderHistory() {
  $('history-count').textContent = `共 ${state.history.length} 条`;

  if (!state.history.length) {
    $('history').innerHTML = '<div class="empty">还没有操作</div>';
    return;
  }

  // 最新的排前面，最多显示 30 条
  const items = state.history.slice(-30).reverse().map((a, i) => {
    const parts = [];
    if (a.user_id) parts.push(esc(a.user_id));
    if (a.item_title) parts.push('《' + esc(a.item_title) + '》');
    const label = ACTION_LABEL[a.action_type] || a.action_type;
    return `<div class="history-item">
      <span class="idx">${state.history.length - i}</span>
      <span class="type">${esc(label)}</span>${parts.join(' ')}
    </div>`;
  }).join('');

  $('history').innerHTML = items;
}

// ---------- 动作 ----------

function requireUser() {
  if (!currentUserId) {
    toast('请先在左上角选择"当前身份"', false);
    return false;
  }
  return true;
}

async function doBorrow(title) {
  if (!requireUser()) return;
  try {
    const r = await api('/borrow', { user_id: currentUserId, title });
    toast(r.message);
    await load();
  } catch (e) {
    // 无库存时后端会提示"是否加入等待队列"
    if (e.message.includes('等待队列')) {
      if (confirm(e.message)) {
        try {
          const r = await api('/borrow', { user_id: currentUserId, title, join_waitlist: true });
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
  if (!requireUser()) return;
  try {
    const r = await api('/return', { user_id: currentUserId, title });
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

async function doAddUser() {
  const id = $('new-user-id').value.trim();
  const name = $('new-user-name').value.trim();
  if (!id || !name) return toast('用户 ID 和姓名都要填', false);
  try {
    const r = await api('/users', { user_id: id, name });
    toast(r.message);
    $('new-user-id').value = '';
    $('new-user-name').value = '';
    await load();
  } catch (e) {
    toast(e.message, false);
  }
}

async function doDeleteUser(userId) {
  if (!confirm(`确定删除用户 ${userId}？`)) return;
  try {
    const r = await api('/users/delete', { user_id: userId });
    toast(r.message);
    await load();
  } catch (e) {
    toast(e.message, false);
  }
}

async function doAddBook() {
  const kind = $('add-kind').value;
  const payload = {
    kind,
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

// ---------- 事件绑定（用委托，列表重绘后依然有效）----------

document.addEventListener('click', e => {
  const t = e.target;
  if (t.dataset.borrow) return doBorrow(t.dataset.borrow);
  if (t.dataset.return) return doReturn(t.dataset.return);
  if (t.dataset.deluser) return doDeleteUser(t.dataset.deluser);
  if (t.id === 'btn-undo') return doUndo();
  if (t.id === 'btn-refresh') return load();
  if (t.id === 'btn-add-user') return doAddUser();
  if (t.id === 'btn-add-submit') return doAddBook();
  if (t.id === 'btn-add-cancel') { $('add-panel').style.display = 'none'; return; }
  if (t.id === 'btn-toggle-add') {
    const p = $('add-panel');
    p.style.display = p.style.display === 'none' ? 'block' : 'none';
  }
});

$('current-user').addEventListener('change', e => {
  currentUserId = e.target.value;
  if (currentUserId) localStorage.setItem('library_user', currentUserId);
  else localStorage.removeItem('library_user');
});

// ---------- 启动 ----------
load();
