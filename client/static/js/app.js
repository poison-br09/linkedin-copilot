// ── Auth helpers ──────────────────────────────────────────────────────────
const API = '/api/v1';

function getToken() { return localStorage.getItem('token'); }
function getUser()  { return JSON.parse(localStorage.getItem('user') || '{}'); }

function setAuth(token, user) {
  localStorage.setItem('token', token);
  localStorage.setItem('user', JSON.stringify(user));
}
function clearAuth() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
}

async function apiFetch(path, opts = {}) {
  const token = getToken();
  const res = await fetch(API + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) { clearAuth(); window.location.href = '/'; }
  return res;
}

function showAlert(containerId, message, type = 'error') {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.className = `alert alert-${type}`;
  el.textContent = message;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 5000);
}

function statusBadge(status) {
  const s = (status || '').toLowerCase();
  return `<span class="badge badge-${s}">${status}</span>`;
}

// ── Login ─────────────────────────────────────────────────────────────────
async function handleLogin(e) {
  e.preventDefault();
  const btn = document.getElementById('login-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Signing in…';

  try {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: document.getElementById('email').value,
        password: document.getElementById('password').value,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Login failed');
    setAuth(data.access_token, { id: data.user_id, email: data.email });

    // Determine role by attempting admin endpoint
    const adminCheck = await apiFetch('/admin/users');
    window.location.href = adminCheck.ok ? '/admin' : '/dashboard';
  } catch (err) {
    showAlert('login-alert', err.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Sign in';
  }
}

function logout() { clearAuth(); window.location.href = '/'; }

// ── Admin dashboard ───────────────────────────────────────────────────────
async function loadAdminDashboard() {
  if (!getToken()) { window.location.href = '/'; return; }
  const res  = await apiFetch('/admin/users');
  if (!res.ok) { window.location.href = '/'; return; }
  const data = await res.json();

  document.getElementById('user-count').textContent = data.count;
  const tbody = document.getElementById('users-tbody');
  tbody.innerHTML = data.users.map(u => `
    <tr>
      <td class="text-primary-col">${u.display_name || '—'}</td>
      <td class="truncate text-xs">${u.id}</td>
      <td>${u.session_ready
        ? '<span class="badge badge-active">● Connected</span>'
        : '<span class="badge badge-inactive">● Disconnected</span>'}</td>
      <td>${u.is_active
        ? '<span class="badge badge-active">Active</span>'
        : '<span class="badge badge-inactive">Inactive</span>'}</td>
      <td class="flex gap-8">
        <button class="btn btn-sm btn-ghost" onclick="resetSession('${u.id}')">Reset</button>
        <button class="btn btn-sm btn-danger" onclick="deactivateUser('${u.id}')">Deactivate</button>
      </td>
    </tr>
  `).join('');
}

async function createUser(e) {
  e.preventDefault();
  const btn = document.getElementById('create-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  try {
    const res  = await apiFetch('/admin/users', {
      method: 'POST',
      body: {
        email: document.getElementById('new-email').value,
        password: document.getElementById('new-password').value,
        display_name: document.getElementById('new-name').value,
      },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed');
    showAlert('admin-alert', `User ${data.email} created!`, 'success');
    closeModal('create-modal');
    await loadAdminDashboard();
  } catch (err) {
    showAlert('admin-alert', err.message, 'error');
  } finally { btn.disabled = false; btn.textContent = 'Create User'; }
}

async function resetSession(userId) {
  if (!confirm('Reset LinkedIn session for this user?')) return;
  const res  = await apiFetch(`/admin/users/${userId}/reset-session`, { method: 'POST' });
  const data = await res.json();
  showAlert('admin-alert', data.detail || 'Done', res.ok ? 'success' : 'error');
}

async function deactivateUser(userId) {
  if (!confirm('Deactivate this user?')) return;
  const res  = await apiFetch(`/admin/users/${userId}`, { method: 'DELETE' });
  const data = await res.json();
  showAlert('admin-alert', data.detail || 'Done', res.ok ? 'success' : 'error');
  await loadAdminDashboard();
}

// ── User dashboard ─────────────────────────────────────────────────────────
let pendingSessionId = null;

async function loadUserDashboard() {
  if (!getToken()) { window.location.href = '/'; return; }
  const [configRes, statusRes, queueRes] = await Promise.all([
    apiFetch('/config'),
    apiFetch('/status'),
    apiFetch('/status/queue?limit=20'),
  ]);
  const config = await configRes.json();
  const status = await statusRes.json();
  const queue  = await queueRes.json();

  const liEl = document.getElementById('li-status');
  if (liEl) liEl.innerHTML = config.session_ready
    ? '<span class="badge badge-active">● Connected</span>'
    : '<span class="badge badge-inactive">● Not Connected</span>';

  const stats = status.queue_stats || {};
  ['pending','processing','done','failed','dead'].forEach(s => {
    const el = document.getElementById(`stat-${s}`);
    if (el) el.textContent = stats[s.toUpperCase()] ?? 0;
  });

  const tbody = document.getElementById('queue-tbody');
  if (tbody) {
    tbody.innerHTML = queue.rows.map(r => `
      <tr>
        <td class="text-primary-col truncate">${r.event_urn}</td>
        <td>${statusBadge(r.status)}</td>
        <td>${r.retry_count}</td>
        <td class="text-xs">${r.created_at ? new Date(r.created_at).toLocaleString() : '—'}</td>
        <td class="text-xs">${r.processed_at ? new Date(r.processed_at).toLocaleString() : '—'}</td>
      </tr>
    `).join('');
  }

  if (document.getElementById('conv-url'))
    document.getElementById('conv-url').value = config.conversation_url || '';
}

async function connectLinkedIn(e) {
  e.preventDefault();
  const btn = document.getElementById('connect-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Connecting…';
  try {
    const res  = await apiFetch('/linkedin/connect', {
      method: 'POST',
      body: {
        linkedin_email: document.getElementById('li-email').value,
        linkedin_password: document.getElementById('li-password').value,
      },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed');
    if (data.requires_otp) {
      pendingSessionId = data.pending_session_id;
      closeModal('connect-modal');
      openModal('otp-modal');
    } else {
      showAlert('user-alert', 'LinkedIn connected!', 'success');
      closeModal('connect-modal');
      await loadUserDashboard();
    }
  } catch (err) {
    showAlert('user-alert', err.message, 'error');
  } finally { btn.disabled = false; btn.textContent = 'Connect'; }
}

async function submitOtp(e) {
  e.preventDefault();
  const btn = document.getElementById('otp-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  try {
    const res  = await apiFetch('/linkedin/verify-otp', {
      method: 'POST',
      body: { pending_session_id: pendingSessionId, otp: document.getElementById('otp-input').value },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'OTP failed');
    showAlert('user-alert', 'LinkedIn connected!', 'success');
    closeModal('otp-modal');
    await loadUserDashboard();
  } catch (err) {
    showAlert('user-alert', err.message, 'error');
  } finally { btn.disabled = false; btn.textContent = 'Verify'; }
}

async function saveConfig(e) {
  e.preventDefault();
  const body = {};
  const url = document.getElementById('conv-url')?.value;
  const key = document.getElementById('nvidia-key')?.value;
  if (url) body.conversation_url = url;
  if (key) body.nvidia_api_key = key;
  const res  = await apiFetch('/config', { method: 'PUT', body });
  const data = await res.json();
  showAlert('user-alert', res.ok ? 'Config saved!' : (data.detail || 'Error'), res.ok ? 'success' : 'error');
}

// ── Modals ─────────────────────────────────────────────────────────────────
function openModal(id)  { document.getElementById(id)?.classList.add('open'); }
function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }
