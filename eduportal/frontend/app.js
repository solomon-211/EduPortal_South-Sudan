(function () {
  'use strict';

  const TOKEN_KEY = 'eduportal_token';
  const USER_KEY  = 'eduportal_user';

  // ── Session helpers ─────────────────────────────────────────────────────────
  function getToken() { return localStorage.getItem(TOKEN_KEY); }
  function getUser()  { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } }
  function saveSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  // ── Fetch wrapper ───────────────────────────────────────────────────────────
  async function api(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(path, { ...opts, headers });
    const ct = res.headers.get('content-type') || '';
    const body = ct.includes('application/json') ? await res.json() : await res.text();
    if (!res.ok) throw new Error((body && body.error) || `Request failed (${res.status})`);
    return body;
  }

  // ── HTML escape ─────────────────────────────────────────────────────────────
  function esc(v) {
    return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Status message helper ───────────────────────────────────────────────────
  function setMsg(el, text, isError = false) {
    if (!el) return;
    el.textContent = text;
    el.style.color = isError ? '#c0392b' : '#2e7d32';
  }

  // ── Page: Login ─────────────────────────────────────────────────────────────
  function initLogin() {
    const form = document.getElementById('login-form');
    const msg  = document.getElementById('login-message');
    if (!form) return;

    // Password toggle
    const pwInput  = document.getElementById('password-input');
    const pwToggle = document.querySelector('[data-toggle-password]');
    if (pwToggle && pwInput) {
      pwToggle.addEventListener('click', () => {
        const show = pwInput.type === 'password';
        pwInput.type = show ? 'text' : 'password';
        pwToggle.querySelector('.eye-open')?.classList.toggle('hidden', show);
        pwToggle.querySelector('.eye-closed')?.classList.toggle('hidden', !show);
      });
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      setMsg(msg, 'Signing in…');
      const fd = Object.fromEntries(new FormData(form));
      try {
        const data = await api('/api/login', { method: 'POST', body: JSON.stringify({ identifier: fd.identifier, password: fd.password }) });
        saveSession(data.token, data.user);
        window.location.href = '/dashboard';
      } catch (err) {
        setMsg(msg, err.message, true);
      }
    });
  }

  // ── Page: Register ──────────────────────────────────────────────────────────
  function initRegister() {
    const form = document.getElementById('register-form');
    const msg  = document.getElementById('register-message');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      setMsg(msg, 'Creating account…');
      const fd = Object.fromEntries(new FormData(form));
      try {
        const data = await api('/api/register', { method: 'POST', body: JSON.stringify(fd) });
        saveSession(data.token, data.user);
        window.location.href = '/dashboard';
      } catch (err) {
        setMsg(msg, err.message, true);
      }
    });
  }

  // ── Page: Dashboard ─────────────────────────────────────────────────────────
  async function initDashboard() {
    const user = getUser();

    // Redirect to login if not authenticated
    if (!getToken()) { window.location.href = '/'; return; }

    // Greet user
    const greetEl = document.getElementById('dashboard-greeting');
    if (greetEl && user) greetEl.textContent = `Welcome back, ${user.name.split(' ')[0]}.`;

    // Logout button
    document.getElementById('logout-btn')?.addEventListener('click', () => {
      clearSession();
      window.location.href = '/';
    });

    // Live stats
    try {
      const stats = await api('/api/stats');
      const map = { 'stat-schools': stats.schools, 'stat-materials': stats.materials, 'stat-scholarships': stats.scholarships, 'stat-announcements': stats.announcements };
      Object.entries(map).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      });
    } catch (_) {}

    // Recent scholarships
    try {
      const { items } = await api('/api/scholarships');
      const container = document.getElementById('dashboard-scholarships');
      if (container) {
        container.innerHTML = items.slice(0, 3).map(s => `
          <div class="opportunity-card">
            <span class="tag">Scholarship</span>
            <h3>${esc(s.title)}</h3>
            <p class="org">${esc(s.provider || 'Verified NGO')}</p>
            <p>📅 ${esc(s.deadline)}</p>
            <p>${esc(s.eligibility)}</p>
          </div>`).join('') || '<p>No scholarships available.</p>';
      }
    } catch (_) {}

    // Saved schools count
    try {
      const { items } = await api('/api/bookmarks');
      const el = document.getElementById('stat-saved');
      if (el) el.textContent = items.filter(b => b.item_type === 'school').length;
    } catch (_) {}
  }

  // ── Page: Directory ─────────────────────────────────────────────────────────
  async function initDirectory() {
    const form    = document.getElementById('school-search-form');
    const results = document.getElementById('directory-results');
    if (!form || !results) return;

    async function load() {
      results.innerHTML = '<p style="padding:1rem;color:#888">Loading…</p>';
      const params = new URLSearchParams(new FormData(form));
      [...params.entries()].forEach(([k, v]) => { if (!v) params.delete(k); });
      const { items } = await api(`/api/schools?${params}`);
      results.innerHTML = items.length
        ? items.map(s => `
            <a class="card school-result-card" href="/schools/${s.id}">
              <span class="tag">${esc(s.state)}</span>
              <h3>${esc(s.name)}</h3>
              <p>${esc(s.county)} · ${esc(s.level)} · ${esc(s.boarding || 'Day')}</p>
              <p style="color:#888;font-size:0.9rem">${esc(s.description || '')}</p>
              <span class="status-pill ${s.status}">${esc(s.status)}</span>
            </a>`).join('')
        : '<p style="padding:1rem;color:#888">No schools matched those filters.</p>';
    }

    form.addEventListener('submit', (e) => { e.preventDefault(); load().catch(err => { results.innerHTML = `<p style="color:#c0392b;padding:1rem">${esc(err.message)}</p>`; }); });

    // Pre-fill search from URL
    const preset = new URLSearchParams(location.search).get('search');
    if (preset) form.querySelector('[name="search"]').value = preset;

    load().catch(console.error);
  }

  // ── Page: School profile ────────────────────────────────────────────────────
  async function initSchoolProfile() {
    const shell = document.getElementById('school-shell');
    if (!shell) return;
    const id = shell.dataset.schoolId;

    try {
      const [{ school }, { items }] = await Promise.all([
        api(`/api/schools/${id}`),
        api(`/api/schools/${id}/requirements`),
      ]);

      const detail = document.getElementById('school-detail');
      if (detail) {
        detail.innerHTML = `
          <span class="tag">${esc(school.state)}</span>
          <h1 style="margin:0.5rem 0">${esc(school.name)}</h1>
          <p>${esc(school.description || '')}</p>
          <p>${esc(school.county)} · ${esc(school.level)} · ${esc(school.boarding || 'Day')} · ${esc(school.hours || '')}</p>
          <p>Capacity: ${esc(school.capacity)} · Enrolled: ${esc(school.enrollment)}</p>
          <p>Contact: ${esc(school.contact_name)} · ${esc(school.phone)}${school.email ? ' · ' + esc(school.email) : ''}</p>
          <span class="status-pill ${school.status}">${esc(school.status)}</span>
          ${getToken() ? `<button class="card-button bookmark-btn" data-type="school" data-id="${school.id}" style="margin-top:1rem;width:auto;padding:0.6rem 1.2rem">Save school</button>` : ''}`;
      }

      const checklist = document.getElementById('school-checklist');
      if (checklist) {
        checklist.innerHTML = items.length
          ? items.map(r => `
              <label class="checklist-item">
                <input type="checkbox" ${r.is_required ? 'checked' : ''} disabled>
                <span>
                  <strong>${esc(r.item_label)}</strong>
                  ${!r.is_required ? '<span class="tag" style="font-size:0.72rem;margin-left:0.4rem">Optional</span>' : ''}
                  ${r.notes ? `<span style="display:block;color:#888;font-size:0.88rem">${esc(r.notes)}</span>` : ''}
                </span>
              </label>`).join('')
          : '<p style="color:#888">No requirements listed yet.</p>';
      }

      // Bookmark button
      shell.addEventListener('click', async (e) => {
        const btn = e.target.closest('.bookmark-btn');
        if (!btn) return;
        btn.disabled = true;
        try {
          await api('/api/bookmarks', { method: 'POST', body: JSON.stringify({ item_type: btn.dataset.type, item_id: btn.dataset.id }) });
          btn.textContent = 'Saved ✓';
        } catch (err) {
          btn.textContent = err.message;
          btn.disabled = false;
        }
      });
    } catch (err) {
      const detail = document.getElementById('school-detail');
      if (detail) detail.innerHTML = `<p style="color:#c0392b">${esc(err.message)}</p>`;
    }
  }

  // ── Page: Materials ─────────────────────────────────────────────────────────
  async function initMaterials() {
    const form    = document.getElementById('materials-search-form');
    const results = document.getElementById('materials-results');
    if (!form || !results) return;

    async function load() {
      results.innerHTML = '<p style="padding:1rem;color:#888">Loading…</p>';
      const params = new URLSearchParams(new FormData(form));
      [...params.entries()].forEach(([k, v]) => { if (!v) params.delete(k); });
      const { items } = await api(`/api/materials?${params}`);
      results.innerHTML = items.length
        ? items.map(m => `
            <article class="card material-card">
              <span class="tag">${esc(m.subject)} · ${esc(m.grade)}</span>
              <h3>${esc(m.title)}</h3>
              <p>${esc(m.year)} · ${esc(m.type)}</p>
              <p style="color:#888;font-size:0.9rem">${esc(m.preview_text || '')}</p>
              <p style="font-weight:700;color:#8b1a1a">${esc(m.file_size || '')}</p>
              ${getToken() ? `<button class="card-button bookmark-btn" data-type="material" data-id="${m.id}" style="margin-top:0.5rem;padding:0.5rem 1rem;font-size:0.85rem">Save</button>` : ''}
            </article>`).join('')
        : '<p style="padding:1rem;color:#888">No materials matched those filters.</p>';
    }

    form.addEventListener('submit', (e) => { e.preventDefault(); load().catch(console.error); });

    results.addEventListener('click', async (e) => {
      const btn = e.target.closest('.bookmark-btn');
      if (!btn) return;
      btn.disabled = true;
      try {
        await api('/api/bookmarks', { method: 'POST', body: JSON.stringify({ item_type: btn.dataset.type, item_id: btn.dataset.id }) });
        btn.textContent = 'Saved ✓';
      } catch (err) { btn.textContent = err.message; btn.disabled = false; }
    });

    load().catch(console.error);
  }

  // ── Page: Opportunities ─────────────────────────────────────────────────────
  async function initOpportunities() {
    const form    = document.getElementById('scholarships-search-form');
    const results = document.getElementById('opportunities-results');
    if (!form || !results) return;

    async function load() {
      results.innerHTML = '<p style="padding:1rem;color:#888">Loading…</p>';
      const params = new URLSearchParams(new FormData(form));
      [...params.entries()].forEach(([k, v]) => { if (!v) params.delete(k); });
      const { items } = await api(`/api/scholarships?${params}`);
      results.innerHTML = items.length
        ? items.map(s => `
            <article class="card opportunity-card">
              <span class="tag">Scholarship</span>
              <h3>${esc(s.title)}</h3>
              <p class="org">${esc(s.provider || 'Verified NGO')}</p>
              <p>${esc(s.eligibility)}</p>
              <p>📅 Deadline: <strong>${esc(s.deadline)}</strong></p>
              <p style="color:#888;font-size:0.9rem">${esc(s.how_to_apply)}</p>
              ${getToken() ? `<button class="card-button bookmark-btn" data-type="scholarship" data-id="${s.id}" style="margin-top:0.5rem;padding:0.5rem 1rem;font-size:0.85rem">Save</button>` : ''}
            </article>`).join('')
        : '<p style="padding:1rem;color:#888">No scholarships matched those filters.</p>';
    }

    form.addEventListener('submit', (e) => { e.preventDefault(); load().catch(console.error); });

    results.addEventListener('click', async (e) => {
      const btn = e.target.closest('.bookmark-btn');
      if (!btn) return;
      btn.disabled = true;
      try {
        await api('/api/bookmarks', { method: 'POST', body: JSON.stringify({ item_type: btn.dataset.type, item_id: btn.dataset.id }) });
        btn.textContent = 'Saved ✓';
      } catch (err) { btn.textContent = err.message; btn.disabled = false; }
    });

    load().catch(console.error);
  }

  // ── Page: Announcements ─────────────────────────────────────────────────────
  async function initAnnouncements() {
    const form    = document.getElementById('announcements-filter-form');
    const results = document.getElementById('announcements-results');
    if (!results) return;

    async function load() {
      results.innerHTML = '<p style="padding:1rem;color:#888">Loading…</p>';
      const params = form ? new URLSearchParams(new FormData(form)) : new URLSearchParams();
      [...params.entries()].forEach(([k, v]) => { if (!v) params.delete(k); });
      const { items } = await api(`/api/announcements?${params}`);
      results.innerHTML = items.length
        ? items.map(a => `
            <article class="card announcement-card">
              <span class="tag">${esc(a.source_type)} · ${esc(a.audience)}</span>
              <h3>${esc(a.title)}</h3>
              <p>${esc(a.body)}</p>
              <p style="color:#888;font-size:0.88rem">Expires: ${esc(a.expires_at || 'N/A')}</p>
            </article>`).join('')
        : '<p style="padding:1rem;color:#888">No announcements found.</p>';
    }

    form?.addEventListener('submit', (e) => { e.preventDefault(); load().catch(console.error); });
    load().catch(console.error);
  }

  // ── Page: Admin ─────────────────────────────────────────────────────────────
  async function initAdmin() {
    if (!getToken()) { window.location.href = '/'; return; }
    const user = getUser();
    if (user?.role !== 'admin') {
      document.getElementById('admin-notice')?.setAttribute('style', 'display:block');
      return;
    }

    // Queue counts
    try {
      const queue = await api('/api/admin/queue');
      ['materials', 'announcements', 'scholarships'].forEach(k => {
        const el = document.getElementById(`queue-${k}`);
        if (el) el.textContent = queue[k];
      });
    } catch (_) {}

    // Users list
    try {
      const { items } = await api('/api/admin/users');
      const list = document.getElementById('admin-users-list');
      if (list) {
        list.innerHTML = items.map(u => `
          <div class="card" style="padding:1rem;display:flex;justify-content:space-between;align-items:center;gap:1rem">
            <div>
              <strong>${esc(u.name)}</strong>
              <p style="margin:0.2rem 0 0;color:#888;font-size:0.88rem">${esc(u.role)} · ${esc(u.state)} · ${esc(u.email || u.phone || 'no contact')}</p>
            </div>
            <span class="tag">${esc(u.role)}</span>
          </div>`).join('') || '<p style="color:#888">No users found.</p>';
      }
    } catch (_) {}

    // Audit log
    try {
      const { items } = await api('/api/admin/audit-log');
      const log = document.getElementById('admin-audit-log');
      if (log) {
        log.innerHTML = items.length
          ? items.map(l => `<div class="card" style="padding:0.8rem"><strong>${esc(l.action)}</strong> on ${esc(l.target_type)} #${esc(l.target_id)} <span style="color:#888;font-size:0.85rem">${esc(l.timestamp)}</span></div>`).join('')
          : '<p style="color:#888">No audit entries yet.</p>';
      }
    } catch (_) {}
  }

  // ── Boot ────────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.page || document.body.className;

    if (page === 'auth-page' || document.getElementById('login-form'))    initLogin();
    if (document.getElementById('register-form'))                          initRegister();
    if (page === 'dashboard-page' || document.getElementById('stat-schools')) initDashboard();
    if (document.body.dataset.page === 'directory')                        initDirectory();
    if (document.getElementById('school-shell'))                           initSchoolProfile();
    if (document.body.dataset.page === 'materials')                        initMaterials();
    if (document.body.dataset.page === 'opportunities')                    initOpportunities();
    if (document.body.dataset.page === 'announcements')                    initAnnouncements();
    if (document.body.dataset.page === 'admin')                            initAdmin();
  });
})();
