(function () {
  'use strict';

  const TOKEN_KEY = 'eduportal_token';
  const USER_KEY  = 'eduportal_user';

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

  // ── Fetch wrapper ─────────────────────────────────────────────────────────
  async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (opts.body) headers['Content-Type'] = 'application/json';
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res  = await fetch(path, { ...opts, headers });
    const ct   = res.headers.get('content-type') || '';
    const body = ct.includes('application/json') ? await res.json() : await res.text();
    if (!res.ok) throw new Error((body && body.error) || `HTTP ${res.status}`);
    return body;
  }

  function esc(v) {
    return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function schoolIdFromPath() {
    const m = window.location.pathname.match(/\/schools\/(\d+)/);
    return m ? m[1] : null;
  }

  function setMsg(el, text, isError = false) {
    if (!el) return;
    el.textContent = text;
    el.classList.remove('is-error', 'is-success');
    el.classList.add(isError ? 'is-error' : 'is-success');
  }

  // ── PDF checklist download (no external lib) ────────────────────────────────────────────
  function downloadChecklistPDF(school, items) {
    // Build an HTML document and print it as PDF via the browser print dialog
    const rows = items.map(r => {
      const checked = r.is_required ? '&#9745;' : '&#9744;';
      const optional = !r.is_required ? ' <em>(Optional)</em>' : '';
      const notes = r.notes ? `<br><small class="u-text-muted-xs">${r.notes}</small>` : '';
      return `<tr><td class="checklist-print-mark">${checked}</td><td class="checklist-print-cell"><strong>${r.item_label}</strong>${optional}${notes}</td></tr>`;
    }).join('');

    const html = `<!doctype html><html><head><meta charset="utf-8">
      <title>Admission Checklist — ${school.name}</title>
      <style>
        body{font-family:Arial,Helvetica,sans-serif;color:#1e1716;padding:2rem;max-width:600px;margin:0 auto}
        h1{font-size:1.4rem;color:#551010;margin:0 0 0.3rem}
        p{margin:0 0 1.2rem;color:#6d6058;font-size:0.9rem}
        table{width:100%;border-collapse:collapse}
        tr{border-bottom:1px solid #eee}
        tr:last-child{border-bottom:0}
        @media print{body{padding:1rem}}
      </style></head><body>
      <h1>${school.name} — Admission Checklist</h1>
      <p>${school.county}, ${school.state} &middot; ${school.level} &middot; ${school.boarding || 'Day'}</p>
      <table>${rows}</table>
      <p class="checklist-print-footer">Printed from EduPortal South Sudan &middot; eduportal.ss</p>
    </body></html>`;

    const win = window.open('', '_blank', 'width=700,height=600');
    if (!win) { alert('Please allow pop-ups to download the checklist.'); return; }
    win.document.write(html);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); }, 400);
  }

  function statusBadge(status) {
    const map = { open:'status-open', limited:'status-limited', closed:'status-closed' };
    return `<span class="status-badge ${map[status] || ''}">${esc(status)}</span>`;
  }

  function appStatusBadge(status) {
    const colors = {
      submitted:    '#888',
      under_review: '#b86000',
      shortlisted:  '#1a5fa8',
      successful:   '#1a7a3c',
      unsuccessful: '#c0392b',
      withdrawn:    '#aaa',
    };
    const labels = {
      submitted: 'Submitted', under_review: 'Under Review',
      shortlisted: 'Shortlisted', successful: 'Successful',
      unsuccessful: 'Unsuccessful', withdrawn: 'Withdrawn',
    };
    return `<span class="app-status-badge app-status-${esc(status)}">${labels[status] || esc(status)}</span>`;
  }

  // ── Pagination helper ─────────────────────────────────────────────────────
  function renderPagination(container, total, page, perPage, onPage) {
    const pages = Math.ceil(total / perPage);
    if (pages <= 1) { container.innerHTML = ''; return; }
    const items = [];
    items.push(`<button class="pag-btn" data-page="${page-1}" ${page===1?'disabled':''}>Previous</button>`);
    for (let p = 1; p <= pages; p++) {
      items.push(`<button class="pag-btn ${p===page?'pag-active':''}" data-page="${p}">${p}</button>`);
    }
    items.push(`<button class="pag-btn" data-page="${page+1}" ${page===pages?'disabled':''}>Next</button>`);
    container.innerHTML = `<div class="pagination">${items.join('')}</div>`;
    container.querySelectorAll('.pag-btn:not([disabled])').forEach(btn => {
      btn.addEventListener('click', () => onPage(Number(btn.dataset.page)));
    });
  }

  // ── Login ─────────────────────────────────────────────────────────────────
  function initLogin() {
    const form = document.getElementById('login-form');
    const msg  = document.getElementById('login-message');
    if (!form) return;

    // Password visibility toggle
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
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(msg, 'Signing in\u2026');
      const fd = Object.fromEntries(new FormData(form));
      try {
        const data = await api('/api/login', { method: 'POST', body: JSON.stringify({ identifier: fd.identifier, password: fd.password }) });
        saveSession(data.token, data.user);
        window.location.href = '/dashboard';
      } catch (err) {
        setMsg(msg, err.message, true);
        btn.disabled = false;
      }
    });
  }

  // ── Register ──────────────────────────────────────────────────────────────
  function initRegister() {
    const form = document.getElementById('register-form');
    const msg  = document.getElementById('register-message');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(msg, 'Creating account\u2026');
      const fd = Object.fromEntries(new FormData(form));
      try {
        const data = await api('/api/register', { method: 'POST', body: JSON.stringify(fd) });
        saveSession(data.token, data.user);
        window.location.href = '/dashboard';
      } catch (err) {
        setMsg(msg, err.message, true);
        btn.disabled = false;
      }
    });
  }

  // ── Dashboard ─────────────────────────────────────────────────────────────
  async function initDashboard() {
    if (!getToken()) { window.location.href = '/'; return; }
    const user = getUser();

    const greetEl = document.getElementById('dashboard-greeting');
    if (greetEl && user) greetEl.textContent = `Welcome back, ${user.name.split(' ')[0]}.`;

    document.getElementById('logout-btn')?.addEventListener('click', () => {
      clearSession(); window.location.href = '/';
    });

    try {
      const stats = await api('/api/stats');
      const map = {
        'stat-schools': stats.schools, 'stat-materials': stats.materials,
        'stat-scholarships': stats.scholarships, 'stat-announcements': stats.announcements,
        'stat-schools-snap': stats.schools, 'stat-materials-snap': stats.materials,
      };
      Object.entries(map).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      });
    } catch (_) {}

    try {
      const [{ items: applications }, { items: notifications }] = await Promise.all([
        api('/api/applications'),
        api('/api/notifications'),
      ]);

      const appsEl = document.getElementById('dashboard-applications');
      const alertsEl = document.getElementById('dashboard-notifications');
      const appsCountEl = document.getElementById('stat-applications');
      if (appsCountEl) appsCountEl.textContent = applications.length;

      if (appsEl) {
        appsEl.innerHTML = applications.length
          ? applications.slice(0, 4).map(app => `
              <div class="snapshot-list-item dashboard-activity-item">
                <div>
                  <strong>${esc(app.title)}</strong>
                  <span>${esc(app.provider || 'Scholarship program')} · Deadline ${esc(app.deadline)}</span>
                </div>
                <div>${appStatusBadge(app.status)}</div>
              </div>`).join('')
          : '<p class="empty-text">You have not submitted any applications yet. Browse scholarships to get started.</p>';
      }

      if (alertsEl) {
        alertsEl.innerHTML = notifications.length
          ? notifications.slice(0, 4).map(item => `
              <div class="dashboard-activity-item">
                <div>
                  <strong>${esc(item.title)}</strong>
                  <span>${esc(item.body)}</span>
                </div>
              </div>`).join('')
          : '<p class="empty-text">No urgent alerts right now.</p>';
      }
    } catch (_) {
      const appsEl = document.getElementById('dashboard-applications');
      const alertsEl = document.getElementById('dashboard-notifications');
      if (appsEl) appsEl.innerHTML = '<p class="empty-text">Your application history is unavailable right now.</p>';
      if (alertsEl) alertsEl.innerHTML = '<p class="empty-text">Alerts are unavailable right now.</p>';
    }

    try {
      const { items } = await api('/api/scholarships');
      const container = document.getElementById('dashboard-scholarships');
      if (container) {
        container.innerHTML = items.slice(0, 3).map(s => `
          <div class="opportunity-card">
            <span class="tag">Scholarship</span>
            <h3>${esc(s.title)}</h3>
            <p class="org">${esc(s.provider || 'Verified NGO')}</p>
            <div class="result-card-footer">
              <span class="deadline-badge">Deadline: <strong>${esc(s.deadline)}</strong></span>
              <span class="card-link">Open</span>
            </div>
          </div>`).join('') || '<p class="u-text-muted">No scholarships available.</p>';
      }
    } catch (err) {
      const container = document.getElementById('dashboard-scholarships');
      if (container) {
        container.innerHTML = '<p class="empty-text">Scholarships are unavailable right now. Open the scholarships page for the latest programs.</p>';
      }
    }

    try {
      const { items } = await api('/api/bookmarks');
      const el = document.getElementById('stat-saved');
      if (el) el.textContent = items.filter(b => b.item_type === 'school').length;
    } catch (_) {}
  }

  // ── Directory ─────────────────────────────────────────────────────────────
  async function initDirectory() {
    const form    = document.getElementById('school-search-form');
    const results = document.getElementById('directory-results');
    const pagEl   = document.getElementById('directory-pagination');
    const inlineDetail = document.getElementById('school-detail');
    const inlineReqs   = document.getElementById('school-requirements');
    if (!results) return;

    let currentPage = 1;

    async function loadInlineDetail(id) {
      if (!inlineDetail) return;
      inlineDetail.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      if (inlineReqs) inlineReqs.innerHTML = '';
      try {
        const [{ school }, { items }] = await Promise.all([
          api(`/api/schools/${id}`),
          api(`/api/schools/${id}/requirements`),
        ]);
        inlineDetail.innerHTML = `
          <div class="u-p-xs">
            <div class="u-flex-wrap u-mb-sm">
              <span class="tag">${esc(school.state)}</span>
              ${statusBadge(school.status)}
            </div>
            <h2 class="u-card-title-md">${esc(school.name)}</h2>
            <p class="u-card-copy">${esc(school.county)} &middot; ${esc(school.level)} &middot; ${esc(school.boarding || 'Day')} &middot; ${esc(school.type || 'Mixed')}</p>
            <p class="u-card-copy-sm">${esc(school.description || '')}</p>
            <p class="u-card-copy-xs">Hours: ${esc(school.hours || 'N/A')} &middot; Capacity: ${esc(school.capacity)} &middot; Enrolled: ${esc(school.enrollment)}</p>
            <p class="u-card-copy-xs">Contact: ${esc(school.contact_name)} &middot; ${esc(school.phone)}</p>
            <div class="u-card-inline-actions">
              <a class="card-button u-card-button-link" href="/schools/${school.id}">Full profile</a>
              ${getToken() ? `<button class="card-button bookmark-btn u-card-button-outline-link" data-type="school" data-id="${school.id}">Save school</button>` : ''}
            </div>
          </div>`;
        if (inlineReqs) {
          inlineReqs.innerHTML = `<p class="section-label u-card-section-label">ADMISSION CHECKLIST</p>` + (items.length
            ? items.map(r => `
                <label class="checklist-item">
                  <input type="checkbox" ${r.is_required ? 'checked' : ''} disabled>
                  <span>
                    <strong>${esc(r.item_label)}</strong>
                    ${!r.is_required ? '<span class="tag tag-muted checklist-optional-tag">Optional</span>' : ''}
                    ${r.notes ? `<span class="u-list-copy-xs checklist-note">${esc(r.notes)}</span>` : ''}
                  </span>
                </label>`).join('')
            : '<p class="u-list-copy">No requirements listed yet.</p>');
        }
        inlineDetail.querySelector('.bookmark-btn')?.addEventListener('click', async (e) => {
          const btn = e.currentTarget;
          btn.disabled = true;
          try {
            await api('/api/bookmarks', { method: 'POST', body: JSON.stringify({ item_type: 'school', item_id: id }) });
            btn.textContent = 'Saved \u2713';
          } catch (err) { btn.textContent = err.message; btn.disabled = false; }
        });
      } catch (err) {
        inlineDetail.innerHTML = `<p class="u-text-danger">${esc(err.message)}</p>`;
      }
    }

    async function load(page = 1) {
      currentPage = page;
      results.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      const params = new URLSearchParams(form ? new FormData(form) : {});
      [...params.entries()].forEach(([k, v]) => { if (!v) params.delete(k); });
      params.set('page', page);
      try {
        const data = await api(`/api/schools?${params}`);
        results.innerHTML = data.items.length
          ? data.items.map(s => `
              <article class="result-card school-result-card" data-id="${s.id}" tabindex="0" role="button" aria-label="View ${esc(s.name)}">
                <div class="result-card-top">
                  <span class="tag">${esc(s.state)}</span>
                  ${statusBadge(s.status)}
                </div>
                <h3 class="result-card-title">${esc(s.name)}</h3>
                <p class="result-card-meta">${esc(s.county)} &middot; ${esc(s.level)} &middot; ${esc(s.boarding || 'Day')}</p>
                <p class="result-card-preview">${esc(s.description || '')}</p>
                <div class="result-card-footer">
                  <span class="result-card-enroll">Enrolled: ${esc(s.enrollment)}</span>
                  <span class="card-link">View</span>
                </div>
              </article>`).join('')
          : '<p class="empty-text">No schools matched those filters.</p>';

        if (pagEl) renderPagination(pagEl, data.total, page, data.per_page, load);

        const cards = results.querySelectorAll('.school-result-card');
        if (inlineDetail) {
          cards.forEach(card => {
            card.addEventListener('click', () => {
              cards.forEach(c => c.classList.remove('is-selected'));
              card.classList.add('is-selected');
              loadInlineDetail(card.dataset.id);
            });
            card.addEventListener('keydown', e => { if (e.key === 'Enter') card.click(); });
          });
          if (cards.length) { cards[0].classList.add('is-selected'); loadInlineDetail(cards[0].dataset.id); }
        } else {
          cards.forEach(card => {
            card.addEventListener('click', () => { window.location.href = `/schools/${card.dataset.id}`; });
          });
        }
      } catch (err) {
        results.innerHTML = `<p class="u-text-danger">${esc(err.message)}</p>`;
      }
    }

    form?.addEventListener('submit', (e) => { e.preventDefault(); load(1); });

    const preset = new URLSearchParams(location.search).get('search');
    if (preset && form) form.querySelector('[name="search"]').value = preset;

    load(1);
  }

  // ── School profile ────────────────────────────────────────────────────────
  async function initSchoolProfile() {
    const shell = document.getElementById('school-shell');
    if (!shell) return;
    // Read ID from URL path since we removed the Jinja2 variable
    const id = schoolIdFromPath();
    if (!id) { shell.innerHTML = '<p class="u-text-danger">School not found.</p>'; return; }

    try {
      const [{ school }, { items }] = await Promise.all([
        api(`/api/schools/${id}`),
        api(`/api/schools/${id}/requirements`),
      ]);

      // Update page title
      document.title = `${school.name} | EduPortal South Sudan`;
      const bannerH1 = document.querySelector('.top-banner h1');
      if (bannerH1) bannerH1.textContent = school.name;

      const detail = document.getElementById('school-detail');
      if (detail) {
        detail.innerHTML = `
          <div class="u-card-link-flex-end u-mb-md">
            <span class="tag">${esc(school.state)}</span>
            ${statusBadge(school.status)}
            <span class="tag tag-muted">${esc(school.type || 'Mixed')}</span>
          </div>
          <h1 class="school-detail-title">${esc(school.name)}</h1>
          <p class="u-card-copy">${esc(school.county)}, ${esc(school.state)} &middot; ${esc(school.level)} &middot; ${esc(school.boarding || 'Day')}</p>
          <p class="u-list-copy">${esc(school.description || '')}</p>
          <div class="detail-grid u-mb-md">
            <div class="detail-item"><span class="detail-key">Hours</span><span>${esc(school.hours || 'N/A')}</span></div>
            <div class="detail-item"><span class="detail-key">Capacity</span><span>${esc(school.capacity)}</span></div>
            <div class="detail-item"><span class="detail-key">Enrolled</span><span>${esc(school.enrollment)}</span></div>
            <div class="detail-item"><span class="detail-key">Curriculum</span><span>${esc(school.curriculum)}</span></div>
            <div class="detail-item"><span class="detail-key">Language</span><span>${esc(school.language || 'English')}</span></div>
            <div class="detail-item"><span class="detail-key">Contact</span><span>${esc(school.contact_name)}</span></div>
            <div class="detail-item"><span class="detail-key">Phone</span><span>${esc(school.phone)}</span></div>
            ${school.email ? `<div class="detail-item"><span class="detail-key">Email</span><span>${esc(school.email)}</span></div>` : ''}
          </div>
          ${getToken() ? `<button class="card-button bookmark-btn u-card-button-compact-sm">Save school</button>` : ''}`;
      }

      const checklist = document.getElementById('school-checklist');
      if (checklist) {
        checklist.innerHTML = items.length
          ? items.map(r => `
              <label class="checklist-item">
                <input type="checkbox" class="checklist-tick" ${r.is_required ? 'checked' : ''}>
                <span>
                  <strong>${esc(r.item_label)}</strong>
                  ${!r.is_required ? '<span class="tag tag-muted checklist-optional-tag">Optional</span>' : ''}
                  ${r.notes ? `<span class="u-list-copy-xs checklist-note">${esc(r.notes)}</span>` : ''}
                </span>
              </label>`).join('')
          : '<p class="u-text-muted">No requirements listed yet.</p>';

        // PDF download button
        if (items.length) {
          const dlBtn = document.createElement('button');
          dlBtn.className = 'card-button u-card-button-compact-sm u-inline-flex-center u-mt-md';
          dlBtn.innerHTML = `<svg viewBox="0 0 16 16" fill="none" width="15" height="15"><path d="M8 2v8M5 7l3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg> Download checklist PDF`;
          checklist.after(dlBtn);
          dlBtn.addEventListener('click', () => downloadChecklistPDF(school, items));
        }
      }

      shell.addEventListener('click', async (e) => {
        const btn = e.target.closest('.bookmark-btn');
        if (!btn) return;
        btn.disabled = true;
        try {
          await api('/api/bookmarks', { method: 'POST', body: JSON.stringify({ item_type: btn.dataset.type, item_id: btn.dataset.id }) });
          btn.textContent = 'Saved \u2713';
        } catch (err) { btn.textContent = err.message; btn.disabled = false; }
      });

      // ── School admin edit panel ──────────────────────────────────────────
      try {
        const { user: me } = await api('/api/me');
        if (me.role === 'school_admin' && me.school_id === Number(id) || me.role === 'admin') {
          _renderSchoolEditPanel(shell, school, items, id);
        }
      } catch (_) {}

    } catch (err) {
      const detail = document.getElementById('school-detail');
      if (detail) detail.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
    }
  }

  function _renderSchoolEditPanel(shell, school, reqItems, id) {
    const panel = document.createElement('section');
    panel.className = 'card content-panel';
    panel.style.marginTop = '1.2rem';
    panel.innerHTML = `
      <p class="section-label">MANAGE SCHOOL PROFILE</p>
      <p class="school-note" class="u-school-note">You are the assigned admin for this school. Changes are saved immediately.</p>

      <form id="edit-school-form">
        <div class="form-grid u-grid-auto-220">
          <label class="field-label">School Name
            <input class="field-input" name="name" value="${esc(school.name)}">
          </label>
          <label class="field-label">State
            <input class="field-input" name="state" value="${esc(school.state)}">
          </label>
          <label class="field-label">County
            <input class="field-input" name="county" value="${esc(school.county)}">
          </label>
          <label class="field-label">Level
            <select class="field-input" name="level">
              <option value="primary" ${school.level==='primary'?'selected':''}>Primary</option>
              <option value="secondary" ${school.level==='secondary'?'selected':''}>Secondary</option>
            </select>
          </label>
          <label class="field-label">Type
            <select class="field-input" name="type">
              <option value="mixed" ${school.type==='mixed'?'selected':''}>Mixed</option>
              <option value="boys" ${school.type==='boys'?'selected':''}>Boys</option>
              <option value="girls" ${school.type==='girls'?'selected':''}>Girls</option>
            </select>
          </label>
          <label class="field-label">Boarding
            <select class="field-input" name="boarding">
              <option value="Day" ${school.boarding==='Day'?'selected':''}>Day</option>
              <option value="Boarding" ${school.boarding==='Boarding'?'selected':''}>Boarding</option>
            </select>
          </label>
          <label class="field-label">Status
            <select class="field-input" name="status">
              <option value="open" ${school.status==='open'?'selected':''}>Open</option>
              <option value="limited" ${school.status==='limited'?'selected':''}>Limited</option>
              <option value="closed" ${school.status==='closed'?'selected':''}>Closed</option>
            </select>
          </label>
          <label class="field-label">Capacity
            <input class="field-input" name="capacity" type="number" value="${esc(school.capacity)}">
          </label>
          <label class="field-label">Enrollment
            <input class="field-input" name="enrollment" type="number" value="${esc(school.enrollment)}">
          </label>
          <label class="field-label">Contact Name
            <input class="field-input" name="contact_name" value="${esc(school.contact_name)}">
          </label>
          <label class="field-label">Phone
            <input class="field-input" name="phone" value="${esc(school.phone)}">
          </label>
          <label class="field-label">Email
            <input class="field-input" name="email" type="email" value="${esc(school.email||'')}">
          </label>
          <label class="field-label">Hours
            <input class="field-input" name="hours" value="${esc(school.hours||'')}">
          </label>
          <label class="field-label">Curriculum
            <input class="field-input" name="curriculum" value="${esc(school.curriculum||'')}">
          </label>
          <label class="field-label">Language
            <input class="field-input" name="language" value="${esc(school.language||'')}">
          </label>
        </div>
        <label class="field-label u-field-label-block-md">Description
          <textarea class="field-input u-textarea-vertical" name="description" rows="3">${esc(school.description||'')}</textarea>
        </label>
        <button class="card-button u-card-button-compact-sm" type="submit">Save School Info</button>
        <span id="edit-school-msg" class="u-inline-note"></span>
      </form>

      <hr class="u-hr-soft">

      <p class="section-label u-card-head-sm">ADMISSION REQUIREMENTS</p>
      <div id="req-editor"></div>
      <button id="add-req-btn" class="card-button u-btn-outline-maroon">+ Add requirement</button>
      <button id="save-reqs-btn" class="card-button u-card-button-compact-sm" class="u-ml-sm">Save Requirements</button>
      <span id="edit-reqs-msg" class="u-inline-note"></span>`;

    shell.appendChild(panel);

    // ── School info form ────────────────────────────────────────────────────
    const editForm = panel.querySelector('#edit-school-form');
    const editMsg  = panel.querySelector('#edit-school-msg');
    editForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = editForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(editMsg, 'Saving\u2026');
      const fd = Object.fromEntries(new FormData(editForm));
      ['capacity','enrollment'].forEach(k => { if (fd[k]) fd[k] = Number(fd[k]); });
      try {
        await api(`/api/schools/${id}`, { method: 'PUT', body: JSON.stringify(fd) });
        setMsg(editMsg, 'Saved \u2713');
      } catch (err) {
        setMsg(editMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    // ── Requirements editor ─────────────────────────────────────────────────
    const reqEditor = panel.querySelector('#req-editor');
    const reqsMsg   = panel.querySelector('#edit-reqs-msg');
    let reqs = reqItems.map(r => ({ item_label: r.item_label, is_required: r.is_required, notes: r.notes || '' }));

    function renderReqEditor() {
      reqEditor.innerHTML = reqs.map((r, i) => `
        <div class="req-row u-row-flex-top" data-idx="${i}">
          <input class="field-input req-label u-flex-2" placeholder="Requirement label" value="${esc(r.item_label)}">
          <input class="field-input req-notes u-flex-2" placeholder="Notes (optional)" value="${esc(r.notes)}">
          <label class="u-inline-check-row">
            <input type="checkbox" class="req-required" ${r.is_required ? 'checked' : ''}> Required
          </label>
          <button class="req-remove u-btn-outline-danger" data-idx="${i}">&times;</button>
        </div>`).join('');
      reqEditor.querySelectorAll('.req-remove').forEach(btn => {
        btn.addEventListener('click', () => { reqs.splice(Number(btn.dataset.idx), 1); renderReqEditor(); });
      });
    }
    renderReqEditor();

    panel.querySelector('#add-req-btn').addEventListener('click', () => {
      reqs.push({ item_label: '', is_required: true, notes: '' });
      renderReqEditor();
    });

    panel.querySelector('#save-reqs-btn').addEventListener('click', async () => {
      const btn = panel.querySelector('#save-reqs-btn');
      btn.disabled = true;
      setMsg(reqsMsg, 'Saving\u2026');
      // Collect current values from DOM
      const rows = reqEditor.querySelectorAll('.req-row');
      const items = [...rows].map(row => ({
        item_label: row.querySelector('.req-label').value.trim(),
        is_required: row.querySelector('.req-required').checked,
        notes: row.querySelector('.req-notes').value.trim(),
      })).filter(r => r.item_label);
      try {
        await api(`/api/schools/${id}/requirements`, { method: 'PUT', body: JSON.stringify({ items }) });
        setMsg(reqsMsg, 'Saved \u2713');
        reqs = items;
      } catch (err) {
        setMsg(reqsMsg, err.message, true);
      } finally { btn.disabled = false; }
    });
  }

  // ── Materials ─────────────────────────────────────────────────────────────
  async function initMaterials() {
    const form    = document.getElementById('materials-search-form');
    const results = document.getElementById('materials-results');
    const pagEl   = document.getElementById('materials-pagination');
    if (!results) return;

    const user = getUser();
    if (user && ['teacher','school_admin','admin'].includes(user.role)) {
      const uploadSection = document.getElementById('upload-material-section');
      if (uploadSection) uploadSection.classList.remove('hidden');
    }

    const uploadForm = document.getElementById('upload-material-form');
    const uploadMsg  = document.getElementById('upload-material-message');
    if (uploadForm) {
      // Add a file input dynamically if not already present
      if (!uploadForm.querySelector('[name="file"]')) {
        const fileFieldHTML = `
          <div class="field u-grid-span-full">
            <span>PDF file (max 20 MB)</span>
            <input type="file" name="file" accept=".pdf" class="u-file-input">
          </div>`;
        const submitBtn = uploadForm.querySelector('button[type="submit"]');
        submitBtn.insertAdjacentHTML('beforebegin', fileFieldHTML);
      }

      uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = uploadForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        setMsg(uploadMsg, 'Submitting\u2026');
        const rawFd = new FormData(uploadForm);
        const file = rawFd.get('file');
        const metaPayload = {
          title:   (rawFd.get('title') || '').trim(),
          subject: rawFd.get('subject'),
          grade:   rawFd.get('grade'),
          year:    Number(rawFd.get('year')),
          type:    rawFd.get('type'),
        };
        try {
          // Step 1 — create the metadata record
          const { id: newId } = await api('/api/materials', {
            method: 'POST', body: JSON.stringify(metaPayload),
          });
          // Step 2 — upload file if one was selected
          if (file && file.size > 0) {
            const fileFd = new FormData();
            fileFd.append('file', file);
            const token = getToken();
            const uploadRes = await fetch(`/api/materials/${newId}/upload`, {
              method: 'POST',
              headers: token ? { 'Authorization': `Bearer ${token}` } : {},
              body: fileFd,
            });
            if (!uploadRes.ok) {
              const err = await uploadRes.json().catch(() => ({}));
              throw new Error(err.error || 'File upload failed');
            }
          }
          setMsg(uploadMsg, 'Submitted for admin review. It will appear once approved.');
          uploadForm.reset();
        } catch (err) {
          setMsg(uploadMsg, err.message, true);
        } finally { btn.disabled = false; }
      });
    }

    let viewMode = 'list';
    window.setMaterialView = function(mode) {
      viewMode = mode;
      document.getElementById('mat-btn-grid') && document.getElementById('mat-btn-grid').classList.toggle('active', mode === 'grid');
      document.getElementById('mat-btn-list') && document.getElementById('mat-btn-list').classList.toggle('active', mode === 'list');
      results.className = mode === 'list' ? 'material-list' : 'material-grid';
    };

    async function load(page) {
      page = page || 1;
      results.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      const params = new URLSearchParams(form ? new FormData(form) : {});
      [...params.entries()].forEach(([k, v]) => { if (!v) params.delete(k); });
      params.set('page', page);
      try {
        const data = await api(`/api/materials?${params}`);
        results.className = viewMode === 'list' ? 'material-list' : 'material-grid';
        const inlineDetail = document.getElementById('material-detail');
        const askPanel = document.querySelector('.ask-teacher-panel');
        results.innerHTML = data.items.length
          ? data.items.map(m => `
              <article class="result-card material-card" data-id="${m.id}" tabindex="0" role="button">
                <div class="material-card-header">
                  <div class="material-card-badges">
                    <span class="tag">${esc(m.subject)}</span>
                    <span class="tag tag-muted">${esc(m.grade)}</span>
                  </div>
                  <span class="material-card-size">${esc(m.file_size || '')}</span>
                </div>
                <div class="material-card-body">
                  <h3 class="result-card-title">${esc(m.title)}</h3>
                  <p class="material-card-meta">${esc(m.year)} &middot; ${esc(m.type)}</p>
                  <p class="result-card-preview">${esc(m.preview_text || '')}</p>
                </div>
                <div class="material-card-footer">
                  ${getToken()
                    ? `<button class="card-link bookmark-btn" data-type="material" data-id="${m.id}" type="button">Save</button>`
                    : '<span class="card-link material-card-save-hint">Login to save</span>'}
                </div>
              </article>`).join('')
          : '<p class="empty-text">No materials matched those filters.</p>';

        if (pagEl) renderPagination(pagEl, data.total, page, data.per_page, load);

        results.querySelectorAll('.material-card').forEach(card => {
          card.addEventListener('click', (e) => {
            if (e.target.closest('.bookmark-btn')) return;
            results.querySelectorAll('.material-card').forEach(c => c.classList.remove('is-selected'));
            card.classList.add('is-selected');
            const m = data.items.find(i => String(i.id) === card.dataset.id);
            if (m && inlineDetail) {
              inlineDetail.innerHTML = `
                <div class="u-p-xs">
                  <div class="u-card-inline-actions-wrap u-mb-md">
                    <span class="tag">${esc(m.subject)}</span>
                    <span class="tag tag-muted">${esc(m.grade)}</span>
                    <span class="tag tag-muted">${esc(m.type)}</span>
                  </div>
                  <h2 class="u-card-title-sm">${esc(m.title)}</h2>
                  <p class="u-card-copy-xs">${esc(m.year)} &middot; ${esc(m.file_size || 'N/A')}</p>
                  <p class="u-list-copy">${esc(m.preview_text || '')}</p>
                  <div class="u-card-inline-actions-wrap">
                    ${getToken() ? `<a class="card-button u-card-button-link" href="/api/materials/${m.id}/download" download>
                        <svg viewBox="0 0 16 16" fill="none" width="13" height="13" class="u-mini-svg-gap"><path d="M8 2v8M5 7l3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
                        Download PDF
                      </a>` : `<a class="card-button u-card-button-link" href="/login">Login to download</a>`}
                    ${getToken() ? `<button class="card-button detail-bookmark-btn u-card-button-outline-link u-card-button-link" data-id="${m.id}">Save material</button>` : ''}
                  </div>
                </div>`;
              if (askPanel) askPanel.classList.remove('hidden-panel');
              inlineDetail.querySelector('.detail-bookmark-btn')?.addEventListener('click', async (ev) => {
                const btn = ev.currentTarget;
                btn.disabled = true;
                try {
                  await api('/api/bookmarks', { method: 'POST', body: JSON.stringify({ item_type: 'material', item_id: m.id }) });
                  btn.textContent = 'Saved \u2713';
                } catch (err) { btn.textContent = err.message; btn.disabled = false; }
              });
            }
          });
          card.addEventListener('keydown', e => { if (e.key === 'Enter') card.click(); });
        });

        results.querySelectorAll('.bookmark-btn').forEach(btn => {
          btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            btn.disabled = true;
            try {
              await api('/api/bookmarks', { method: 'POST', body: JSON.stringify({ item_type: btn.dataset.type, item_id: btn.dataset.id }) });
              btn.textContent = 'Saved \u2713';
            } catch (err) { btn.textContent = err.message; btn.disabled = false; }
          });
        });
      } catch (err) {
        results.innerHTML = `<p class="u-text-danger">${esc(err.message)}</p>`;
      }
    }

    form && form.addEventListener('submit', (e) => { e.preventDefault(); load(1); });
    load(1);
  }


  // ── Opportunities (Scholarships) ──────────────────────────────────────────
  async function initOpportunities() {
    const form    = document.getElementById('scholarships-search-form');
    const results = document.getElementById('opportunities-results');
    const viewDash   = document.getElementById('view-dashboard');
    const viewDetail = document.getElementById('view-scholarship-detail');
    const detailContent = document.getElementById('scholarship-detail-content');
    const backBtn = document.getElementById('scholarship-back-btn');
    if (!results) return;

    function showList() {
      viewDash?.classList.add('active');
      viewDetail?.classList.remove('active');
    }
    function showDetail(s) {
      viewDash?.classList.remove('active');
      viewDetail?.classList.add('active');
      if (!detailContent) return;
      detailContent.innerHTML = `
        <div class="detail-header">
          <div>
            <span class="tag">${esc(s.provider || 'Verified NGO')}</span>
            <h2 class="detail-title">${esc(s.title)}</h2>
            <p class="deadline-badge">Deadline: <strong>${esc(s.deadline)}</strong></p>
          </div>
          <div class="u-card-inline-actions-end">
            ${getToken() ? `<button class="card-button apply-btn u-card-button-compact-sm" data-id="${s.id}">Apply Now</button>
            <button class="card-button sch-bookmark-btn u-card-button-outline-link u-card-button-compact-sm" data-id="${s.id}">&#9825; Save</button>` : '<a class="card-button u-card-button-compact-sm" href="/login">Login to Apply</a>'}
          </div>
        </div>
        <div class="detail-body">
          <div class="detail-section">
            <p class="detail-key">About this opportunity</p>
            <p>${esc(s.description)}</p>
          </div>
          <div class="detail-grid">
            <div class="detail-item"><span class="detail-key">Eligibility</span><span>${esc(s.eligibility)}</span></div>
            <div class="detail-item"><span class="detail-key">Provider</span><span>${esc(s.provider || 'N/A')}</span></div>
            ${s.org_contact ? `<div class="detail-item"><span class="detail-key">Contact</span><span>${esc(s.org_contact)}</span></div>` : ''}
            ${s.org_email ? `<div class="detail-item"><span class="detail-key">Email</span><span>${esc(s.org_email)}</span></div>` : ''}
          </div>
          ${s.required_docs ? `<div class="detail-section"><p class="detail-key">Required Documents</p><p>${esc(s.required_docs)}</p></div>` : ''}
          <div class="detail-section"><p class="detail-key">How to Apply</p><p>${esc(s.how_to_apply)}</p></div>
          ${s.external_link ? `<div class="detail-section"><a href="${esc(s.external_link)}" target="_blank" rel="noopener" class="card-button u-card-button-link-inline">Visit Application Page</a></div>` : ''}
          ${s.org_description ? `<div class="detail-section"><p class="detail-key">About ${esc(s.provider || 'the Organisation')}</p><p>${esc(s.org_description)}</p></div>` : ''}
        </div>`;

      // Apply button handler
      detailContent.querySelector('.apply-btn')?.addEventListener('click', async (btn_e) => {
        const btn = btn_e.currentTarget;
        btn.disabled = true;
        btn.textContent = 'Submitting\u2026';
        try {
          await api('/api/applications', { method: 'POST', body: JSON.stringify({ scholarship_id: s.id }) });
          btn.textContent = 'Application submitted';
          btn.style.background = '#1a7a3c';
        } catch (err) {
          btn.textContent = err.message.includes('already') ? 'Already applied' : err.message;
          btn.disabled = false;
        }
      });

      // Bookmark button handler
      detailContent.querySelector('.sch-bookmark-btn')?.addEventListener('click', async (btn_e) => {
        const btn = btn_e.currentTarget;
        btn.disabled = true;
        try {
          await api('/api/bookmarks', { method: 'POST', body: JSON.stringify({ item_type: 'scholarship', item_id: s.id }) });
          btn.textContent = 'Saved';
          btn.style.color = 'var(--maroon)';
        } catch (err) {
          btn.textContent = err.message.includes('already') ? 'Already saved' : err.message;
          btn.disabled = false;
        }
      });
    }

    backBtn?.addEventListener('click', showList);

    // Show post-scholarship form for NGO officers
    const user = getUser();
    if (user && ['ngo_officer','admin'].includes(user.role)) {
      const postSection = document.getElementById('post-scholarship-section');
      if (postSection) postSection.classList.remove('hidden');
    }

    const postSchForm = document.getElementById('post-scholarship-form');
    const postSchMsg  = document.getElementById('post-scholarship-msg');
    postSchForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = postSchForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(postSchMsg, 'Submitting\u2026');
      const fd = Object.fromEntries(new FormData(postSchForm));
      try {
        await api('/api/scholarships', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(postSchMsg, 'Submitted for admin review. It will appear once approved.');
        postSchForm.reset();
      } catch (err) {
        setMsg(postSchMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    async function load() {
      results.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      const params = new URLSearchParams(form ? new FormData(form) : {});
      [...params.entries()].forEach(([k, v]) => { if (!v) params.delete(k); });
      // form field is named "deadline" but API expects "deadline_after"
      const deadlineVal = params.get('deadline');
      if (deadlineVal) { params.delete('deadline'); params.set('deadline_after', deadlineVal); }
      try {
        const { items } = await api(`/api/scholarships?${params}`);
        results.innerHTML = items.length
          ? items.map(s => `
              <article class="result-card opportunity-card u-cursor-pointer" data-id="${s.id}" tabindex="0" role="button">
                <div class="result-card-top"><span class="tag">Scholarship</span></div>
                <h3 class="result-card-title">${esc(s.title)}</h3>
                <p class="org">${esc(s.provider || 'Verified NGO')}</p>
                <p class="result-card-meta">${esc(s.eligibility)}</p>
                <div class="result-card-footer">
                  <span class="deadline-badge">Deadline: ${esc(s.deadline)}</span>
                  <span class="card-link">Details</span>
                </div>
              </article>`).join('')
          : '<p class="empty-text">No scholarships matched those filters.</p>';

        results.querySelectorAll('.opportunity-card').forEach(card => {
          const handler = () => {
            const s = items.find(i => String(i.id) === card.dataset.id);
            if (s) showDetail(s);
          };
          card.addEventListener('click', handler);
          card.addEventListener('keydown', e => { if (e.key === 'Enter') handler(); });
        });
      } catch (err) {
        results.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }

    form?.addEventListener('submit', (e) => { e.preventDefault(); load(); });
    load();
  }

  // ── Announcements ─────────────────────────────────────────────────────────
  async function initAnnouncements() {
    const form    = document.getElementById('announcements-filter-form');
    const results = document.getElementById('announcements-results');
    if (!results) return;

    const user = getUser();
    if (user && ['school_admin','ngo_officer','admin'].includes(user.role)) {
      const postSection = document.getElementById('post-announcement-section');
      if (postSection) postSection.classList.remove('hidden');
    }

    const postForm = document.getElementById('post-announcement-form');
    const postMsg  = document.getElementById('post-ann-message');
    if (postForm) {
      postForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = postForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        setMsg(postMsg, 'Submitting\u2026');
        const fd = Object.fromEntries(new FormData(postForm));
        try {
          await api('/api/announcements', { method: 'POST', body: JSON.stringify(fd) });
          setMsg(postMsg, 'Submitted for admin review.');
          postForm.reset();
        } catch (err) {
          setMsg(postMsg, err.message, true);
        } finally { btn.disabled = false; }
      });
    }

    async function load() {
      results.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      const params = new URLSearchParams(form ? new FormData(form) : {});
      [...params.entries()].forEach(([k, v]) => { if (!v) params.delete(k); });
      try {
        const { items } = await api(`/api/announcements?${params}`);
        results.innerHTML = items.length
          ? items.map(a => `
              <article class="ann-list-item">
                <div class="ann-list-meta">
                  <span class="tag">${esc(a.source_type)}</span>
                  <span class="tag tag-muted">${esc(a.audience)}</span>
                </div>
                <div class="ann-list-body">
                  <h3 class="ann-list-title">${esc(a.title)}</h3>
                  <p class="ann-list-preview">${esc(a.body)}</p>
                  <div class="ann-list-footer">
                    <span class="deadline-badge">Expires: ${esc(a.expires_at || 'N/A')}</span>
                    <span class="u-school-copy-inline">${esc(a.created_at ? a.created_at.slice(0,10) : '')}</span>
                  </div>
                </div>
              </article>`).join('')
          : '<p class="empty-text">No announcements found.</p>';
      } catch (err) {
        results.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }

    form && form.addEventListener('submit', (e) => { e.preventDefault(); load(); });
    load();
  }


  // ── My Applications ───────────────────────────────────────────────────────
  async function initMyApplications() {
    if (!getToken()) { window.location.href = '/'; return; }

    const listEl   = document.getElementById('applications-list');
    const summaryEl = document.getElementById('apps-summary');
    if (!listEl) return;

    // View toggle
    let viewMode = 'grid';
    window.setAppView = function(mode) {
      viewMode = mode;
      document.getElementById('btn-grid')?.classList.toggle('active', mode === 'grid');
      document.getElementById('btn-list')?.classList.toggle('active', mode === 'list');
      listEl.className = mode === 'list' ? 'apps-list-view' : 'apps-grid-view';
    };
    listEl.className = 'apps-grid-view';

    const showInactive = document.getElementById('show-inactive');

    const accentClass = { submitted:'', under_review:'accent-orange', shortlisted:'accent-orange', successful:'accent-green', unsuccessful:'accent-muted', withdrawn:'accent-muted' };

    async function load() {
      listEl.innerHTML = '<p class="apps-empty">Loading\u2026</p>';
      try {
        const { items } = await api('/api/applications');
        const showAll = showInactive?.checked;
        const visible = showAll ? items : items.filter(a => !['unsuccessful','withdrawn'].includes(a.status));

        if (summaryEl) summaryEl.textContent = `${items.length} application${items.length !== 1 ? 's' : ''} total`;

        if (!visible.length) {
          listEl.innerHTML = `<p class="apps-empty">${items.length ? 'No active applications. Check "Show unsuccessful" to see all.' : 'No applications yet. Browse scholarships to apply.'}</p>`;
          return;
        }

        // Group by status
        const order = ['submitted','under_review','shortlisted','successful','unsuccessful','withdrawn'];
        const groups = {};
        order.forEach(s => { groups[s] = []; });
        visible.forEach(a => { (groups[a.status] = groups[a.status] || []).push(a); });

        const groupLabels = {
          submitted: 'Submitted', under_review: 'Under Review',
          shortlisted: 'Shortlisted', successful: 'Successful',
          unsuccessful: 'Unsuccessful', withdrawn: 'Withdrawn',
        };

        let html = '';
        order.forEach(status => {
          const group = groups[status];
          if (!group || !group.length) return;
          html += `<div class="app-group-header">${groupLabels[status]} (${group.length})</div>`;
          group.forEach(a => {
            html += `
              <div class="app-card">
                <div class="app-accent ${accentClass[a.status] || ''}"></div>
                <div class="u-card-flex-main">
                  <p class="app-category">${esc(a.provider || 'Scholarship')}</p>
                  <p class="app-org">${esc(a.title)}</p>
                  <p class="app-role">Deadline: ${esc(a.deadline)}</p>
                  <p class="app-location">Applied: ${esc(a.applied_at ? a.applied_at.slice(0,10) : '')}</p>
                </div>
                <div class="u-card-inline-actions-end">
                  ${appStatusBadge(a.status)}
                  ${a.status === 'submitted' ? `<button class="card-link withdraw-btn u-card-link-danger-sm" data-id="${a.id}">Withdraw</button>` : ''}
                </div>
              </div>`;
          });
        });
        listEl.innerHTML = html;

        listEl.querySelectorAll('.withdraw-btn').forEach(btn => {
          btn.addEventListener('click', async () => {
            if (!confirm('Withdraw this application?')) return;
            btn.disabled = true;
            try {
              await api(`/api/applications/${btn.dataset.id}`, { method: 'DELETE' });
              load();
            } catch (err) { btn.textContent = err.message; btn.disabled = false; }
          });
        });
      } catch (err) {
        listEl.innerHTML = `<p class="apps-empty u-text-danger">${esc(err.message)}</p>`;
      }
    }

    showInactive?.addEventListener('change', load);
    load();
  }

  // ── Profile ───────────────────────────────────────────────────────────────
  async function initProfile() {
    if (!getToken()) { window.location.href = '/'; return; }

    const form    = document.getElementById('profile-form');
    const msg     = document.getElementById('profile-message');
    const nameEl  = document.getElementById('profile-name-display');
    const roleEl  = document.getElementById('profile-role-display');
    const avatarInput    = document.getElementById('avatar-input');
    const avatarImg      = document.getElementById('profile-avatar-img');
    const avatarFallback = document.getElementById('avatar-fallback');
    const uploadBtn      = document.getElementById('avatar-upload-btn');
    if (!form) return;

    // Load current profile data
    try {
      const { user } = await api('/api/me');
      if (nameEl) nameEl.textContent = user.name;
      if (roleEl) roleEl.textContent = user.role.replace('_', ' ');

      // Show saved avatar if present
      if (user.avatar && avatarImg) {
        avatarImg.src = user.avatar;
        avatarImg.style.display = '';
        if (avatarFallback) avatarFallback.style.display = 'none';
      }

      // Fill form fields
      const fill = (name, val) => {
        const el = form.querySelector(`[name="${name}"]`);
        if (el && val != null) el.value = val;
      };
      fill('name', user.name);
      fill('email', user.email);
      fill('phone', user.phone);
      fill('state', user.state);
      fill('county', user.county);
      fill('grade', user.grade);
      fill('school_name', user.school_name);
      fill('child_school', user.child_school);
      fill('child_grade', user.child_grade);
      fill('subjects', user.subjects);
      fill('institution', user.institution);
      fill('experience_years', user.experience_years);
      fill('managed_school', user.managed_school);
      fill('position', user.position);

      // Show role-specific fields, hide others
      const role = user.role;
      form.querySelectorAll('[data-role-field]').forEach(el => {
        const target = el.dataset.roleField;
        el.style.display = (target === 'all' || target === role) ? '' : 'none';
      });
    } catch (err) {
      setMsg(msg, err.message, true);
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(msg, 'Saving\u2026');
      const fd = Object.fromEntries(new FormData(form));
      // Remove empty strings
      Object.keys(fd).forEach(k => { if (!fd[k]) delete fd[k]; });
      try {
        await api('/api/me', { method: 'PUT', body: JSON.stringify(fd) });
        setMsg(msg, 'Profile saved successfully.');
        if (nameEl && fd.name) nameEl.textContent = fd.name;
        // Update stored user name
        const stored = getUser();
        if (stored && fd.name) { stored.name = fd.name; localStorage.setItem(USER_KEY, JSON.stringify(stored)); }
      } catch (err) {
        setMsg(msg, err.message, true);
      } finally {
        btn.disabled = false;
      }
    });

    // Avatar upload — sends file to server and persists it
    uploadBtn?.addEventListener('click', () => avatarInput?.click());
    avatarInput?.addEventListener('change', async () => {
      const file = avatarInput.files?.[0];
      if (!file) return;
      if (file.size > 2 * 1024 * 1024) { setMsg(msg, 'Image must be under 2 MB.', true); return; }
      // Optimistic preview
      const reader = new FileReader();
      reader.onload = (ev) => {
        if (avatarImg) { avatarImg.src = ev.target.result; avatarImg.style.display = ''; }
        if (avatarFallback) avatarFallback.style.display = 'none';
      };
      reader.readAsDataURL(file);
      // Upload to server
      try {
        const fd = new FormData();
        fd.append('avatar', file);
        const token = getToken();
        const res = await fetch('/api/me/avatar', {
          method: 'POST',
          headers: token ? { 'Authorization': `Bearer ${token}` } : {},
          body: fd,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        setMsg(msg, 'Profile photo saved.');
        // Bust cache so the new image shows immediately
        if (avatarImg) avatarImg.src = data.avatar + '?t=' + Date.now();
      } catch (err) {
        setMsg(msg, 'Photo preview saved locally, but upload failed: ' + err.message, true);
      }
    });
  }

  // ── Settings ──────────────────────────────────────────────────────────────
  async function initSettings() {
    if (!getToken()) { window.location.href = '/'; return; }

    const pwForm  = document.getElementById('change-password-form');
    const pwMsg   = document.getElementById('password-message');
    const notifForm = document.getElementById('notifications-form');
    const notifMsg  = document.getElementById('notifications-message');
    const deactivateBtn = document.getElementById('deactivate-account-btn');
    const deactivateMsg = document.getElementById('deactivate-message');

    // Load current notification prefs
    try {
      const { user } = await api('/api/me');
      if (notifForm) {
        const setCheck = (name, val) => {
          const el = notifForm.querySelector(`[name="${name}"]`);
          if (el) el.checked = Boolean(val);
        };
        setCheck('notify_email', user.notify_email);
        setCheck('notify_sms',   user.notify_sms);
        setCheck('notify_inapp', user.notify_inapp);
      }
    } catch (_) {}

    notifForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = notifForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        const fd = new FormData(notifForm);
        await api('/api/me', { method: 'PUT', body: JSON.stringify({
          notify_email: fd.get('notify_email') === 'on' ? 1 : 0,
          notify_sms:   fd.get('notify_sms')   === 'on' ? 1 : 0,
          notify_inapp: fd.get('notify_inapp')  === 'on' ? 1 : 0,
        })});
        setMsg(notifMsg, 'Notification preferences saved.');
      } catch (err) {
        setMsg(notifMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    pwForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = pwForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(pwMsg, 'Updating\u2026');
      const fd = Object.fromEntries(new FormData(pwForm));
      if (fd.new_password !== fd.confirm_password) {
        setMsg(pwMsg, 'New passwords do not match.', true);
        btn.disabled = false; return;
      }
      try {
        await api('/api/change-password', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(pwMsg, 'Password changed successfully.');
        pwForm.reset();
      } catch (err) {
        setMsg(pwMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    deactivateBtn?.addEventListener('click', async () => {
      if (!confirm('Deactivate your account? You will be signed out immediately.')) return;
      deactivateBtn.disabled = true;
      setMsg(deactivateMsg, 'Deactivating\u2026');
      try {
        await api('/api/deactivate-account', { method: 'POST' });
        clearSession();
        window.location.href = '/';
      } catch (err) {
        setMsg(deactivateMsg, err.message, true);
        deactivateBtn.disabled = false;
      }
    });
  }

  // ── Admin ─────────────────────────────────────────────────────────────────
  async function initAdmin() {
    if (!getToken()) { window.location.href = '/'; return; }
    const user = getUser();
    const notice = document.getElementById('admin-notice');
    if (user?.role !== 'admin') {
      if (notice) notice.classList.remove('hidden');
      return;
    }

    // Tab navigation
    const tabBtns   = [...document.querySelectorAll('.admin-tab-btn')];
    const tabPanels = [...document.querySelectorAll('.admin-tab-panel')];
    const subBtns   = [...document.querySelectorAll('.admin-sub-btn')];
    const subPanels = [...document.querySelectorAll('.admin-sub-panel')];

    function activateTab(id) {
      tabBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === id));
      tabPanels.forEach(p => p.classList.toggle('active', p.id === id));
    }
    function activateSub(id) {
      subBtns.forEach(b => b.classList.toggle('active', b.dataset.sub === id));
      subPanels.forEach(p => p.classList.toggle('active', p.id === id));
    }
    tabBtns.forEach(b => b.addEventListener('click', () => activateTab(b.dataset.tab)));
    subBtns.forEach(b => b.addEventListener('click', () => activateSub(b.dataset.sub)));
    activateTab('tab-approvals');
    activateSub('sub-materials');

    function renderQueue(containerId, items, type) {
      const el = document.getElementById(containerId);
      if (!el) return;
      el.innerHTML = items.length
        ? items.map(item => `
            <div class="admin-approve-card">
              <div>
                <p class="eyebrow u-mb-xs u-text-maroon">${esc(type)}</p>
                <h3>${esc(item.title)}</h3>
                <p>${esc(item.meta || '')}</p>
              </div>
              <div class="admin-approve-actions">
                <button class="card-button" data-action="approve" data-type="${esc(type)}" data-id="${item.id}">Approve</button>
                <button class="card-button btn-reject" data-action="reject" data-type="${esc(type)}" data-id="${item.id}">Reject</button>
              </div>
            </div>`).join('')
        : '<p class="u-text-muted">No items pending.</p>';

      el.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', async () => {
          btn.disabled = true;
          try {
            await api('/api/admin/approve', { method: 'POST', body: JSON.stringify({
              target_type: btn.dataset.type, target_id: Number(btn.dataset.id), action: btn.dataset.action,
            })});
            loadAll();
          } catch (err) { btn.disabled = false; btn.textContent = err.message; }
        });
      });
    }

    async function loadUsers() {
      const role = document.getElementById('admin-role-select')?.value || '';
      try {
        const { items } = await api(`/api/admin/users${role ? `?role=${role}` : ''}`);
        const schoolList = await api('/api/schools?per_page=100').catch(() => ({ items: [] }));
        const allSchools = schoolList.items || [];
        const el = document.getElementById('admin-users-list');
        const total = document.getElementById('stat-users');
        if (total) total.textContent = items.length;
        if (el) {
          el.innerHTML = items.length
            ? items.map(u => {
                const schoolOptions = allSchools.map(s =>
                  `<option value="${s.id}" ${u.school_id === s.id ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
                const assignControl = u.role === 'school_admin' ? `
                  <select class="school-assign-select u-compact-select u-admin-select" data-id="${u.id}">
                    <option value="">No school assigned</option>
                    ${schoolOptions}
                  </select>
                  <button class="btn-assign-school u-admin-action-btn" data-id="${u.id}">Assign</button>` : '';
                return `
                <div class="admin-user-row">
                  <div>
                    <strong>${esc(u.name)}</strong>
                    <span>${esc(u.role)} &middot; ${esc(u.state)} &middot; ${esc(u.email || u.phone || 'no contact')}</span>
                    ${u.role === 'school_admin' && u.school_id ? `<span class="u-assigned-school-note">&#127eb; Assigned to school #${u.school_id}</span>` : ''}
                  </div>
                  <div class="u-card-link-wrap-end">
                    <select class="role-select u-compact-select" data-id="${u.id}">
                      <option value="student" ${u.role==='student'?'selected':''}>Student</option>
                      <option value="parent" ${u.role==='parent'?'selected':''}>Parent</option>
                      <option value="teacher" ${u.role==='teacher'?'selected':''}>Teacher</option>
                      <option value="school_admin" ${u.role==='school_admin'?'selected':''}>School Admin</option>
                      <option value="ngo_officer" ${u.role==='ngo_officer'?'selected':''}>NGO Officer</option>
                      <option value="admin" ${u.role==='admin'?'selected':''}>Admin</option>
                    </select>
                    <button class="btn-change-role u-admin-action-btn" data-id="${u.id}">Set Role</button>
                    ${assignControl}
                    <button class="btn-suspend" data-id="${u.id}" ${u.verified === -1 ? 'disabled' : ''}>${u.verified === -1 ? 'Suspended' : 'Suspend'}</button>
                    <button class="btn-delete-user u-admin-delete-btn" data-id="${u.id}">Delete</button>
                  </div>
                </div>`;
              }).join('')
            : '<p class="u-text-muted">No users found.</p>';

          el.querySelectorAll('.btn-assign-school').forEach(btn => {
            btn.addEventListener('click', async () => {
              const row = btn.closest('.admin-user-row');
              const sel = row.querySelector('.school-assign-select');
              const schoolId = sel?.value ? Number(sel.value) : null;
              if (!confirm(schoolId ? `Assign this user to school #${schoolId}?` : 'Remove school assignment?')) return;
              btn.disabled = true;
              try {
                await api(`/api/admin/users/${btn.dataset.id}/assign-school`, { method: 'POST', body: JSON.stringify({ school_id: schoolId }) });
                loadUsers();
              } catch (err) { btn.disabled = false; btn.textContent = err.message; }
            });
          });

          el.querySelectorAll('.btn-change-role').forEach(btn => {
            btn.addEventListener('click', async () => {
              const row = btn.closest('.admin-user-row');
              const newRole = row.querySelector('.role-select')?.value;
              if (!newRole || !confirm(`Change this user's role to "${newRole}"?`)) return;
              btn.disabled = true;
              try {
                await api(`/api/admin/users/${btn.dataset.id}/role`, { method: 'POST', body: JSON.stringify({ role: newRole }) });
                loadUsers();
              } catch (err) { btn.disabled = false; btn.textContent = err.message; }
            });
          });

          el.querySelectorAll('.btn-suspend:not([disabled])').forEach(btn => {
            btn.addEventListener('click', async () => {
              if (!confirm('Suspend this user?')) return;
              btn.disabled = true;
              try {
                await api(`/api/admin/users/${btn.dataset.id}/suspend`, { method: 'POST' });
                btn.textContent = 'Suspended';
              } catch (err) { btn.disabled = false; btn.textContent = err.message; }
            });
          });

          el.querySelectorAll('.btn-delete-user').forEach(btn => {
            btn.addEventListener('click', async () => {
              if (!confirm('Permanently delete this user? This cannot be undone.')) return;
              btn.disabled = true;
              try {
                await api(`/api/admin/users/${btn.dataset.id}`, { method: 'DELETE' });
                loadUsers();
              } catch (err) { btn.disabled = false; btn.textContent = err.message; }
            });
          });
        }
      } catch (_) {}
    }

    async function loadAnalytics() {
      try {
        const data = await api('/api/admin/analytics');
        const statesEl = document.getElementById('analytics-states');
        const bookmarksEl = document.getElementById('analytics-bookmarks');
        const contentEl = document.getElementById('analytics-content');
        const appsEl = document.getElementById('analytics-applications');
        if (statesEl) statesEl.innerHTML = data.users_by_state.map(r =>
          `<div><strong>${esc(r.state)}</strong><span>${esc(r.count)} users</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
        if (bookmarksEl) bookmarksEl.innerHTML = data.bookmarked_schools.map(r =>
          `<div><strong>${esc(r.name)}</strong><span>${esc(r.count)} saves</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
        if (contentEl) contentEl.innerHTML = `
          <div><strong>${esc(data.approved.materials)}</strong><span>approved materials</span></div>
          <div><strong>${esc(data.approved.announcements)}</strong><span>approved announcements</span></div>
          <div><strong>${esc(data.approved.scholarships)}</strong><span>approved scholarships</span></div>
          <div><strong>${esc(data.total_users)}</strong><span>registered users</span></div>
          <div><strong>${esc(data.total_applications)}</strong><span>total applications</span></div>`;
        if (appsEl) appsEl.innerHTML = data.scholarship_applications.map(r =>
          `<div><strong>${esc(r.title)}</strong><span>${esc(r.applications)} applications</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
      } catch (_) {}
    }

    async function loadAll() {
      try {
        const queue = await api('/api/admin/queue');
        const counts = { 'stat-mat': queue.materials, 'stat-ann': queue.announcements, 'stat-sch': queue.scholarships };
        Object.entries(counts).forEach(([id, v]) => { const el = document.getElementById(id); if (el) el.textContent = v; });
        renderQueue('pending-materials',     queue.material_items,     'material');
        renderQueue('pending-announcements', queue.announcement_items, 'announcement');
        renderQueue('pending-scholarships',  queue.scholarship_items,  'scholarship');
      } catch (_) {}

      await loadUsers();
      await loadAnalytics();

      try {
        const { items } = await api('/api/admin/audit-log');
        const el = document.getElementById('admin-audit-log');
        if (el) el.innerHTML = items.length
          ? items.map(l => `
              <div class="admin-audit-row">
                <p><strong>${esc(l.action)}</strong> on ${esc(l.target_type)} #${esc(l.target_id)}${l.note ? ` &mdash; ${esc(l.note)}` : ''}</p>
                <p class="audit-time">${esc(l.timestamp)}</p>
              </div>`).join('')
          : '<p class="u-text-muted">No audit entries yet.</p>';
      } catch (_) {}
    }

    document.getElementById('user-filter-form')?.addEventListener('submit', (e) => { e.preventDefault(); loadUsers(); });

    // ── Applications tab ────────────────────────────────────────────────────
    async function loadAdminApps() {
      const listEl = document.getElementById('admin-applications-list');
      if (!listEl) return;
      const status = document.getElementById('admin-apps-status')?.value || '';
      listEl.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      try {
        const { items } = await api('/api/admin/applications' + (status ? '?status=' + encodeURIComponent(status) : ''));
        if (!items.length) { listEl.innerHTML = '<p class="u-text-muted">No applications found.</p>'; return; }
        listEl.innerHTML = items.map(a => `
          <div class="admin-approve-card" class="u-flex-center">
            <div class="u-flex-grow-1">
              <p class="eyebrow" class="u-school-title-sm">${esc(a.scholarship_title || 'Scholarship')}</p>
              <h3 class="u-strong-sm">${esc(a.applicant_name || 'User #' + a.user_id)}</h3>
              <p class="u-school-copy-sm">${esc(a.applicant_email || '')} &middot; Applied ${esc(a.applied_at ? a.applied_at.slice(0,10) : '')}</p>
            </div>
            <div class="u-inline-flex-gap-sm">
              ${appStatusBadge(a.status)}
              <select class="app-status-select u-status-select" data-app-id="${a.id}">
                <option value="">Change status&hellip;</option>
                <option value="submitted">Submitted</option>
                <option value="under_review">Under Review</option>
                <option value="shortlisted">Shortlisted</option>
                <option value="successful">Successful</option>
                <option value="unsuccessful">Unsuccessful</option>
              </select>
            </div>
          </div>`).join('');

        listEl.querySelectorAll('.app-status-select').forEach(sel => {
          sel.addEventListener('change', async () => {
            if (!sel.value) return;
            const newStatus = sel.value;
            sel.disabled = true;
            try {
              await api(`/api/admin/applications/${sel.dataset.appId}/status`, { method: 'POST', body: JSON.stringify({ status: newStatus }) });
              sel.closest('.admin-approve-card').querySelector('[style*="border-radius:999px"]').outerHTML = appStatusBadge(newStatus);
            } catch (err) {
              alert(err.message);
            } finally { sel.disabled = false; sel.value = ''; }
          });
        });
      } catch (err) {
        listEl.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }

    document.getElementById('admin-apps-filter-form')?.addEventListener('submit', (e) => { e.preventDefault(); loadAdminApps(); });
    document.querySelector('[data-tab="tab-applications"]')?.addEventListener('click', () => loadAdminApps());

    // ── Schools tab ─────────────────────────────────────────────────────────
    async function loadAdminSchools() {
      const listEl  = document.getElementById('admin-schools-list');
      const countEl = document.getElementById('admin-schools-count');
      if (!listEl) return;
      listEl.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      try {
        const data = await api('/api/schools?per_page=200');
        const schools = data.items || [];
        if (countEl) countEl.textContent = `${schools.length} school${schools.length !== 1 ? 's' : ''}`;
        listEl.innerHTML = schools.length
          ? schools.map(s => `
              <div class="admin-user-row">
                <div>
                  <strong>${esc(s.name)}</strong>
                  <span>${esc(s.state)} &middot; ${esc(s.county)} &middot; ${esc(s.level)} &middot; ${esc(s.type || 'mixed')}</span>
                  <span class="u-school-copy-inline">${esc(s.boarding || 'Day')} &middot; Enrolled: ${esc(s.enrollment)}</span>
                </div>
                <div class="u-inline-flex-wrap-sm">
                  <a class="card-button u-card-button-compact-tight" href="/schools/${s.id}" target="_blank">View</a>
                  <button class="btn-delete-school u-btn-pill-danger" data-id="${s.id}">Delete</button>
                </div>
              </div>`).join('')
          : '<p class="u-text-muted">No schools found.</p>';

        listEl.querySelectorAll('.btn-delete-school').forEach(btn => {
          btn.addEventListener('click', async () => {
            if (!confirm('Permanently delete this school and all its requirements? This cannot be undone.')) return;
            btn.disabled = true;
            try {
              await api(`/api/schools/${btn.dataset.id}`, { method: 'DELETE' });
              loadAdminSchools();
            } catch (err) { btn.disabled = false; btn.textContent = err.message; }
          });
        });
      } catch (err) {
        listEl.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }

    const addSchoolForm = document.getElementById('admin-add-school-form');
    const addSchoolMsg  = document.getElementById('admin-add-school-msg');
    addSchoolForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = addSchoolForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(addSchoolMsg, 'Onboarding\u2026');
      const fd = Object.fromEntries(new FormData(addSchoolForm));
      ['capacity', 'enrollment'].forEach(k => { if (fd[k]) fd[k] = Number(fd[k]); });
      try {
        const res = await api('/api/admin/onboard-school', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(addSchoolMsg, 'School onboarded \u2713');
        addSchoolForm.reset();
        // Show invite link
        const wrap = document.getElementById('admin-invite-link-wrap');
        const linkEl = document.getElementById('admin-invite-link-text');
        const noteEl = document.getElementById('admin-invite-email-note');
        if (wrap && linkEl) {
          linkEl.textContent = res.invite_link;
          if (noteEl) noteEl.textContent = res.email_sent
            ? `Invitation email sent to ${esc(fd.email)}.`
            : `SMTP not configured — share this link manually with ${esc(fd.email)}.`;
          wrap.style.display = 'block';
        }
        loadAdminSchools();
      } catch (err) {
        setMsg(addSchoolMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    const addNgoForm = document.getElementById('admin-add-ngo-form');
    const addNgoMsg  = document.getElementById('admin-add-ngo-msg');
    addNgoForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = addNgoForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(addNgoMsg, 'Onboarding\u2026');
      const fd = Object.fromEntries(new FormData(addNgoForm));
      try {
        const res = await api('/api/admin/onboard-ngo', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(addNgoMsg, 'Organisation onboarded \u2713');
        addNgoForm.reset();
        const wrap = document.getElementById('admin-ngo-invite-link-wrap');
        const linkEl = document.getElementById('admin-ngo-invite-link-text');
        const noteEl = document.getElementById('admin-ngo-invite-email-note');
        if (wrap && linkEl) {
          linkEl.textContent = res.invite_link;
          if (noteEl) noteEl.textContent = res.email_sent
            ? `Invitation email sent to ${esc(fd.email)}.`
            : `SMTP not configured — share this link manually with ${esc(fd.email)}.`;
          wrap.style.display = 'block';
        }
      } catch (err) {
        setMsg(addNgoMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    document.querySelector('[data-tab="tab-schools"]')?.addEventListener('click', () => loadAdminSchools());

    loadAll();
  }


  // ── Bookmarks ──────────────────────────────────────────────────────────────────
  async function initBookmarks() {
    if (!getToken()) { window.location.href = '/'; return; }

    // Tab switching with count badges
    const tabBtns   = [...document.querySelectorAll('.admin-tab-btn')];
    const tabPanels = [...document.querySelectorAll('.admin-tab-panel')];
    tabBtns.forEach(b => b.addEventListener('click', () => {
      tabBtns.forEach(x => x.classList.remove('active'));
      tabPanels.forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      document.getElementById(b.dataset.tab)?.classList.add('active');
    }));

    // Fetch all bookmarks with full item details in ONE request
    let items = [];
    try {
      const { items: data } = await api('/api/bookmarks/detailed');
      items = data;
    } catch (err) {
      ['bm-schools-list','bm-materials-list','bm-scholarships-list'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      });
      return;
    }

    const schoolItems      = items.filter(b => b.item_type === 'school');
    const materialItems    = items.filter(b => b.item_type === 'material');
    const scholarshipItems = items.filter(b => b.item_type === 'scholarship');

    // Update tab count badges
    tabBtns.forEach(btn => {
      const map = { 'bm-schools': schoolItems.length, 'bm-materials': materialItems.length, 'bm-scholarships': scholarshipItems.length };
      const cnt = map[btn.dataset.tab];
      if (cnt !== undefined) {
        btn.innerHTML = btn.textContent.trim().split(' ')[0] + (cnt > 0 ? ` <span class="u-counter-badge">${cnt}</span>` : '');
      }
    });

    async function remove(bookmarkId, renderFn) {
      try {
        await api(`/api/bookmarks/${bookmarkId}`, { method: 'DELETE' });
        items = items.filter(b => b.bookmark_id !== bookmarkId);
        renderFn();
      } catch (err) { alert(err.message); }
    }

    function renderSchools() {
      const el = document.getElementById('bm-schools-list');
      if (!el) return;
      const bms = items.filter(b => b.item_type === 'school');
      if (!bms.length) {
        el.innerHTML = '<p class="empty-text">No saved schools yet. <a class="text-link" href="/directory">Browse the directory</a> and save schools you like.</p>';
        return;
      }
      el.innerHTML = bms.map(b => {
        const s = b.detail;
        if (!s) return `<article class="result-card"><p class="muted">School #${b.item_id} not found</p><div class="result-card-footer"><button class="card-link remove-bm u-bare-button-danger" data-bm-id="${b.bookmark_id}">Remove</button></div></article>`;
        return `<article class="result-card">
          <div class="result-card-top"><span class="tag">${esc(s.state)}</span>${statusBadge(s.status)}</div>
          <h3 class="result-card-title">${esc(s.name)}</h3>
          <p class="result-card-meta">${esc(s.county)} &middot; ${esc(s.level)} &middot; ${esc(s.boarding || 'Day')}</p>
          <p class="result-card-preview">${esc(s.description || '')}</p>
          <div class="result-card-footer">
            <a class="card-link" href="/schools/${s.id}">View profile</a>
            <button class="card-link remove-bm u-bare-button-danger-sm" data-bm-id="${b.bookmark_id}">Remove</button>
          </div>
        </article>`;
      }).join('');
      el.querySelectorAll('.remove-bm').forEach(btn => {
        btn.addEventListener('click', () => remove(Number(btn.dataset.bmId), renderSchools));
      });
    }

    function renderMaterials() {
      const el = document.getElementById('bm-materials-list');
      if (!el) return;
      const bms = items.filter(b => b.item_type === 'material');
      if (!bms.length) {
        el.innerHTML = '<p class="empty-text">No saved materials yet. <a class="text-link" href="/materials">Browse study materials</a> to save for later.</p>';
        return;
      }
      el.innerHTML = bms.map(b => {
        const m = b.detail;
        if (!m) return `<article class="result-card"><p class="muted">Material #${b.item_id} not found</p><div class="result-card-footer"><button class="card-link remove-bm u-bare-button-danger" data-bm-id="${b.bookmark_id}">Remove</button></div></article>`;
        return `<article class="result-card">
          <div class="result-card-top">
            <span class="tag">${esc(m.subject)}</span>
            <span class="tag tag-muted">${esc(m.grade)}</span>
            <span class="tag tag-muted">${esc(m.type)}</span>
          </div>
          <h3 class="result-card-title">${esc(m.title)}</h3>
          <p class="result-card-meta">${esc(m.year)} &middot; ${esc(m.file_size || 'Size unknown')}</p>
          <p class="result-card-preview">${esc(m.preview_text || '')}</p>
          <div class="result-card-footer">
            ${getToken() && m.file_path
              ? `<a class="card-link u-link-maroon" href="/api/materials/${m.id}/download" download>
                  <svg viewBox="0 0 14 14" fill="none" width="12" height="12" class="u-mr-sm"><path d="M7 1v7M4 6l3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M1 11h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
                  Download PDF
                </a>`
              : `<span class="card-link u-link-muted">${m.file_path ? 'Login to download' : 'No file yet'}</span>`}
            <button class="card-link remove-bm u-bare-button-danger-sm" data-bm-id="${b.bookmark_id}">Remove</button>
          </div>
        </article>`;
      }).join('');
      el.querySelectorAll('.remove-bm').forEach(btn => {
        btn.addEventListener('click', () => remove(Number(btn.dataset.bmId), renderMaterials));
      });
    }

    function renderScholarships() {
      const el = document.getElementById('bm-scholarships-list');
      if (!el) return;
      const bms = items.filter(b => b.item_type === 'scholarship');
      if (!bms.length) {
        el.innerHTML = '<p class="empty-text">No saved scholarships yet. <a class="text-link" href="/opportunities">Browse scholarships</a> and save ones you want to apply for.</p>';
        return;
      }
      el.innerHTML = bms.map(b => {
        const s = b.detail;
        if (!s) return `<article class="result-card"><p class="muted">Scholarship #${b.item_id} not found</p><div class="result-card-footer"><button class="card-link remove-bm u-bare-button-danger" data-bm-id="${b.bookmark_id}">Remove</button></div></article>`;
        return `<article class="result-card">
          <div class="result-card-top"><span class="tag">Scholarship</span></div>
          <h3 class="result-card-title">${esc(s.title)}</h3>
          <p class="org">${esc(s.provider || 'Verified NGO')}</p>
          <p class="result-card-meta">${esc(s.eligibility || '')}</p>
          <div class="result-card-footer">
            <span class="deadline-badge">Deadline: ${esc(s.deadline)}</span>
            <div class="u-card-link-inline-gap">
              <a class="card-link u-link-sm" href="/opportunities">Apply</a>
              <button class="card-link remove-bm u-bare-button-danger-sm" data-bm-id="${b.bookmark_id}">Remove</button>
            </div>
          </div>
        </article>`;
      }).join('');
      el.querySelectorAll('.remove-bm').forEach(btn => {
        btn.addEventListener('click', () => remove(Number(btn.dataset.bmId), renderScholarships));
      });
    }

    renderSchools();
    renderMaterials();
    renderScholarships();
  }

  // ── Forgot / Reset Password ───────────────────────────────────────────────
  function initForgotPassword() {
    const forgotForm = document.getElementById('forgot-form');
    const resetForm  = document.getElementById('reset-form');
    const forgotMsg  = document.getElementById('forgot-message');
    const resetMsg   = document.getElementById('reset-message');
    const stepRequest = document.getElementById('step-request');
    const stepReset   = document.getElementById('step-reset');
    if (!forgotForm) return;

    forgotForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = forgotForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(forgotMsg, 'Sending reset code\u2026');
      const fd = Object.fromEntries(new FormData(forgotForm));
      try {
        const data = await api('/api/forgot-password', { method: 'POST', body: JSON.stringify({ identifier: fd.identifier }) });
        setMsg(forgotMsg, data.message || 'Reset code sent.');
        // In dev the token is returned directly — pre-fill it
        if (data.dev_token) {
          document.getElementById('reset-token-input').value = data.dev_token;
          document.getElementById('reset-user-id').value = data.user_id;
        }
        stepRequest.classList.add('hidden');
        stepReset.classList.remove('hidden');
      } catch (err) {
        setMsg(forgotMsg, err.message, true);
        btn.disabled = false;
      }
    });

    resetForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = resetForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(resetMsg, 'Resetting password\u2026');
      const fd = Object.fromEntries(new FormData(resetForm));
      if (fd.new_password !== fd.confirm_password) {
        setMsg(resetMsg, 'Passwords do not match.', true);
        btn.disabled = false;
        return;
      }
      try {
        const data = await api('/api/reset-password', { method: 'POST', body: JSON.stringify({
          user_id: fd.user_id, token: fd.token, new_password: fd.new_password,
        })});
        setMsg(resetMsg, data.message || 'Password reset. Redirecting\u2026');
        setTimeout(() => { window.location.href = '/'; }, 1800);
      } catch (err) {
        setMsg(resetMsg, err.message, true);
        btn.disabled = false;
      }
    });
  }

  // ── School Dashboard ──────────────────────────────────────────────────────
  async function initSchoolDashboard() {
    if (!getToken()) { window.location.href = '/'; return; }
    const user = getUser();
    const notice = document.getElementById('school-dash-notice');
    if (!user || !['school_admin', 'admin'].includes(user.role)) {
      if (notice) notice.classList.remove('hidden');
      return;
    }

    let schoolId = null;
    let reqItems = [];
    const reqEditor = document.getElementById('sd-req-editor');
    const reqsMsg   = document.getElementById('sd-reqs-msg');

    function renderReqEditor() {
      if (!reqEditor) return;
      reqEditor.innerHTML = reqItems.map((r, i) => `
        <div class="req-row school-req-row">
          <input class="req-label school-req-label" placeholder="Requirement label" value="${esc(r.item_label)}">
          <input class="req-notes school-req-notes" placeholder="Notes (optional)" value="${esc(r.notes || '')}">
          <label class="school-req-checkwrap">
            <input type="checkbox" class="req-required" ${r.is_required ? 'checked' : ''}> Required
          </label>
          <button class="req-remove school-req-remove" data-idx="${i}" type="button">&times;</button>
        </div>`).join('');
      reqEditor.querySelectorAll('.req-remove').forEach(btn => {
        btn.addEventListener('click', () => { reqItems.splice(Number(btn.dataset.idx), 1); renderReqEditor(); });
      });
    }

    try {
      const data = await api('/api/my-school');
      const s = data.school;
      schoolId = s.id;

      document.getElementById('school-dash-title').textContent = s.name;
      document.getElementById('sd-enrollment').textContent = s.enrollment ?? '—';
      document.getElementById('sd-capacity').textContent   = s.capacity   ?? '—';
      document.getElementById('sd-bookmarks').textContent  = data.bookmark_count ?? '—';
      document.getElementById('sd-status').textContent     = s.status     ?? '—';

      // B — show the school's public profile link so admin knows their school ID
      const profileLink = document.getElementById('sd-public-profile-link');
      if (profileLink) {
        profileLink.href = `/schools/${s.id}`;
        profileLink.classList.remove('hidden');
      }

      const form = document.getElementById('sd-info-form');
      const fill = (name, val) => { const el = form.querySelector(`[name="${name}"]`); if (el && val != null) el.value = val; };
      fill('name', s.name); fill('status', s.status); fill('capacity', s.capacity);
      fill('enrollment', s.enrollment); fill('contact_name', s.contact_name);
      fill('phone', s.phone); fill('email', s.email || ''); fill('hours', s.hours || '');
      fill('description', s.description || '');

      reqItems = data.requirements || [];
      renderReqEditor();

      const annEl = document.getElementById('sd-ann-list');
      if (annEl) {
        annEl.innerHTML = data.announcements.length
          ? data.announcements.map(a => `
              <div class="admin-approve-card school-card-stack-item">
                <div class="school-card-meta-row">
                  <span class="tag tag-muted">${esc(a.audience)}</span>
                  <span class="u-card-copy-xs">${esc(a.created_at ? a.created_at.slice(0,10) : '')}</span>
                  ${a.approved ? '<span class="status-badge status-open">Approved</span>' : '<span class="status-badge status-limited">Pending</span>'}
                </div>
                <strong class="school-card-title">${esc(a.title)}</strong>
                <p class="school-card-copy">${esc(a.body)}</p>
              </div>`).join('')
          : '<p class="empty-text">No announcements posted yet.</p>';
      }

      const matEl = document.getElementById('sd-mat-list');
      if (matEl) {
        matEl.innerHTML = data.materials.length
          ? data.materials.map(m => `
              <div class="admin-approve-card school-card-stack-item">
                <div class="school-card-meta-row">
                  <span class="tag">${esc(m.subject)}</span>
                  <span class="tag tag-muted">${esc(m.grade)}</span>
                  ${m.approved ? '<span class="status-badge status-open">Approved</span>' : '<span class="status-badge status-limited">Pending</span>'}
                </div>
                <strong class="school-card-title">${esc(m.title)}</strong>
                <p class="school-card-copy">${esc(m.year)} · ${esc(m.type)} · ${esc(m.file_size || 'No file')}</p>
              </div>`).join('')
          : '<p class="empty-text">No materials uploaded yet.</p>';
      }

    } catch (err) {
      if (notice) { notice.textContent = err.message; notice.classList.remove('hidden'); }
      return;
    }

    document.getElementById('sd-add-req')?.addEventListener('click', () => {
      reqItems.push({ item_label: '', is_required: true, notes: '' });
      renderReqEditor();
    });

    document.getElementById('sd-save-reqs')?.addEventListener('click', async () => {
      const btn = document.getElementById('sd-save-reqs');
      btn.disabled = true;
      setMsg(reqsMsg, 'Saving…');
      const rows = reqEditor.querySelectorAll('.req-row');
      const items = [...rows].map(row => ({
        item_label: row.querySelector('.req-label').value.trim(),
        is_required: row.querySelector('.req-required').checked,
        notes: row.querySelector('.req-notes').value.trim(),
      })).filter(r => r.item_label);
      try {
        await api(`/api/schools/${schoolId}/requirements`, { method: 'PUT', body: JSON.stringify({ items }) });
        setMsg(reqsMsg, 'Saved successfully');
        reqItems = items;
      } catch (err) {
        setMsg(reqsMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    const infoForm = document.getElementById('sd-info-form');
    const infoMsg  = document.getElementById('sd-info-msg');
    infoForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = infoForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(infoMsg, 'Saving…');
      const fd = Object.fromEntries(new FormData(infoForm));
      ['capacity', 'enrollment'].forEach(k => { if (fd[k]) fd[k] = Number(fd[k]); });
      try {
        await api(`/api/schools/${schoolId}`, { method: 'PUT', body: JSON.stringify(fd) });
        setMsg(infoMsg, 'Saved successfully');
        document.getElementById('school-dash-title').textContent = fd.name || '';
        document.getElementById('sd-enrollment').textContent = fd.enrollment ?? '—';
        document.getElementById('sd-capacity').textContent   = fd.capacity   ?? '—';
        document.getElementById('sd-status').textContent     = fd.status     ?? '—';
      } catch (err) {
        setMsg(infoMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    const annForm = document.getElementById('sd-ann-form');
    const annMsg  = document.getElementById('sd-ann-msg');
    annForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = annForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(annMsg, 'Submitting…');
      const fd = Object.fromEntries(new FormData(annForm));
      fd.source_type = 'School';
      try {
        await api('/api/announcements', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(annMsg, 'Submitted for admin review.');
        annForm.reset();
      } catch (err) {
        setMsg(annMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    const matForm = document.getElementById('sd-mat-form');
    const matMsg  = document.getElementById('sd-mat-msg');
    matForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = matForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(matMsg, 'Submitting…');
      const rawFd = new FormData(matForm);
      const file = rawFd.get('file');
      const meta = {
        title:   (rawFd.get('title') || '').trim(),
        subject: rawFd.get('subject'),
        grade:   rawFd.get('grade'),
        year:    Number(rawFd.get('year')),
        type:    rawFd.get('type'),
      };
      try {
        const { id: newId } = await api('/api/materials', { method: 'POST', body: JSON.stringify(meta) });
        if (file && file.size > 0) {
          const fileFd = new FormData();
          fileFd.append('file', file);
          const token = getToken();
          const res = await fetch(`/api/materials/${newId}/upload`, {
            method: 'POST',
            headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            body: fileFd,
          });
          if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.error || 'File upload failed'); }
        }
        setMsg(matMsg, 'Submitted for admin review.');
        matForm.reset();
      } catch (err) {
        setMsg(matMsg, err.message, true);
      } finally { btn.disabled = false; }
    });
  }

  // ── NGO Dashboard ─────────────────────────────────────────────────────────
  async function initNgoDashboard() {
    if (!getToken()) { window.location.href = '/'; return; }
    const user = getUser();
    const notice = document.getElementById('ngo-dash-notice');
    if (!user || !['ngo_officer', 'admin'].includes(user.role)) {
      if (notice) notice.classList.remove('hidden');
      return;
    }

    try {
      const data = await api('/api/my-ngo');
      const ngo = data.ngo;

      document.getElementById('nd-sch-count').textContent = data.scholarships.length;
      document.getElementById('nd-app-count').textContent = data.application_count ?? '—';
      document.getElementById('nd-ann-count').textContent = data.announcements.length;

      if (ngo) {
        document.getElementById('ngo-dash-title').textContent = ngo.org_name;
        const form = document.getElementById('nd-org-form');
        const fill = (name, val) => { const el = form.querySelector(`[name="${name}"]`); if (el && val != null) el.value = val; };
        fill('org_name', ngo.org_name); fill('contact', ngo.contact);
        fill('phone', ngo.phone || ''); fill('email', ngo.email || '');
        fill('description', ngo.description || '');
      }

      const schEl = document.getElementById('nd-sch-list');
      if (schEl) {
        schEl.innerHTML = data.scholarships.length
          ? data.scholarships.map(s => `
              <div class="admin-approve-card u-card-stack-sm">
                <div class="u-inline-flex-wrap-sm">
                  <span class="deadline-badge">Deadline: ${esc(s.deadline)}</span>
                  ${s.approved ? '<span class="status-badge status-open">Approved</span>' : '<span class="status-badge status-limited">Pending review</span>'}
                </div>
                <strong class="u-strong-sm">${esc(s.title)}</strong>
                <p class="u-card-copy-xs">${esc(s.eligibility)}</p>
              </div>`).join('')
          : '<p class="empty-text">No scholarships posted yet.</p>';
      }

      const annEl = document.getElementById('nd-ann-list');
      if (annEl) {
        annEl.innerHTML = data.announcements.length
          ? data.announcements.map(a => `
              <div class="admin-approve-card u-card-stack-sm">
                <div class="u-inline-flex-wrap-sm">
                  <span class="tag tag-muted">${esc(a.audience)}</span>
                  <span class="u-school-copy-inline">${esc(a.created_at ? a.created_at.slice(0,10) : '')}</span>
                  ${a.approved ? '<span class="status-badge status-open">Approved</span>' : '<span class="status-badge status-limited">Pending</span>'}
                </div>
                <strong class="u-strong-sm">${esc(a.title)}</strong>
                <p class="u-card-copy-xs">${esc(a.body)}</p>
              </div>`).join('')
          : '<p class="empty-text">No announcements posted yet.</p>';
      }

    } catch (err) {
      if (notice) { notice.textContent = err.message; notice.classList.remove('hidden'); }
      return;
    }

    const orgForm = document.getElementById('nd-org-form');
    const orgMsg  = document.getElementById('nd-org-msg');
    orgForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = orgForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(orgMsg, 'Saving…');
      const fd = Object.fromEntries(new FormData(orgForm));
      try {
        await api('/api/my-ngo', { method: 'PUT', body: JSON.stringify(fd) });
        setMsg(orgMsg, 'Saved successfully');
        if (fd.org_name) document.getElementById('ngo-dash-title').textContent = fd.org_name;
      } catch (err) {
        setMsg(orgMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    const schForm = document.getElementById('nd-sch-form');
    const schMsg  = document.getElementById('nd-sch-msg');
    schForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = schForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(schMsg, 'Submitting…');
      const fd = Object.fromEntries(new FormData(schForm));
      try {
        await api('/api/scholarships', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(schMsg, 'Submitted for admin review.');
        schForm.reset();
        const el = document.getElementById('nd-sch-count');
        if (el) el.textContent = String(Number(el.textContent || 0) + 1);
      } catch (err) {
        setMsg(schMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    const annForm = document.getElementById('nd-ann-form');
    const annMsg  = document.getElementById('nd-ann-msg');
    annForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = annForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(annMsg, 'Submitting…');
      const fd = Object.fromEntries(new FormData(annForm));
      fd.source_type = 'NGO';
      try {
        await api('/api/announcements', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(annMsg, 'Submitted for admin review.');
        annForm.reset();
      } catch (err) {
        setMsg(annMsg, err.message, true);
      } finally { btn.disabled = false; }
    });
  }

  // ── School Dashboard ─────────────────────────────────────────────────────
  async function initSchoolDashboard() {
    if (!getToken()) { window.location.href = '/'; return; }
    const user = getUser();
    const notice = document.getElementById('school-dash-notice');
    if (user?.role !== 'school_admin' && user?.role !== 'admin') {
      if (notice) notice.style.display = 'block';
      return;
    }

    // Load school data via /api/my-school
    let school, reqs, materials, bookmarkCount;
    try {
      const data = await api('/api/my-school');
      school        = data.school;
      reqs          = data.requirements;
      materials     = data.materials;
      bookmarkCount = data.bookmark_count;
    } catch (err) {
      if (notice) { notice.textContent = err.message; notice.style.display = 'block'; }
      return;
    }

    // Fill header
    const title = document.getElementById('school-dash-title');
    if (title) title.textContent = school.name;
    const profileLink = document.getElementById('sd-public-profile-link');
    if (profileLink) { profileLink.href = `/schools/${school.id}`; profileLink.style.display = ''; }

    // Fill stat cards
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('sd-enrollment', school.enrollment ?? '—');
    set('sd-capacity',   school.capacity   ?? '—');
    set('sd-bookmarks',  bookmarkCount      ?? 0);
    set('sd-status',     school.status      ?? '—');

    // Pre-fill info form
    const infoForm = document.getElementById('sd-info-form');
    if (infoForm) {
      const fill = (name, val) => { const el = infoForm.querySelector(`[name="${name}"]`); if (el && val != null) el.value = val; };
      ['name','status','capacity','enrollment','contact_name','phone','email','hours','description'].forEach(f => fill(f, school[f]));
      const infoMsg = document.getElementById('sd-info-msg');
      infoForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = infoForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        setMsg(infoMsg, 'Saving\u2026');
        const fd = Object.fromEntries(new FormData(infoForm));
        ['capacity','enrollment'].forEach(k => { if (fd[k]) fd[k] = Number(fd[k]); });
        try {
          await api(`/api/schools/${school.id}`, { method: 'PUT', body: JSON.stringify(fd) });
          setMsg(infoMsg, 'Saved \u2713');
        } catch (err) { setMsg(infoMsg, err.message, true); }
        finally { btn.disabled = false; }
      });
    }

    // Requirements editor
    const reqEditor = document.getElementById('sd-req-editor');
    const regsMsg   = document.getElementById('sd-reqs-msg');
    let reqItems = reqs.map(r => ({ item_label: r.item_label, is_required: r.is_required, notes: r.notes || '' }));

    function renderReqEditor() {
      if (!reqEditor) return;
      reqEditor.innerHTML = reqItems.map((r, i) => `
        <div class="req-row" class="u-row-flex-top">
          <input class="field-input req-label" placeholder="Requirement" value="${esc(r.item_label)}" class="u-flex-2">
          <input class="field-input req-notes" placeholder="Notes" value="${esc(r.notes)}" class="u-flex-2">
          <label class="u-inline-check-row">
            <input type="checkbox" class="req-required" ${r.is_required ? 'checked' : ''}> Required
          </label>
          <button class="req-remove u-btn-outline-danger" data-idx="${i}">&times;</button>
        </div>`).join('');
      reqEditor.querySelectorAll('.req-remove').forEach(btn => {
        btn.addEventListener('click', () => { reqItems.splice(Number(btn.dataset.idx), 1); renderReqEditor(); });
      });
    }
    renderReqEditor();

    document.getElementById('sd-add-req')?.addEventListener('click', () => {
      reqItems.push({ item_label: '', is_required: true, notes: '' });
      renderReqEditor();
    });
    document.getElementById('sd-save-reqs')?.addEventListener('click', async () => {
      const btn = document.getElementById('sd-save-reqs');
      btn.disabled = true;
      setMsg(regsMsg, 'Saving\u2026');
      const rows = reqEditor.querySelectorAll('.req-row');
      const saved = [...rows].map(row => ({
        item_label: row.querySelector('.req-label').value.trim(),
        is_required: row.querySelector('.req-required').checked,
        notes: row.querySelector('.req-notes').value.trim(),
      })).filter(r => r.item_label);
      try {
        await api(`/api/schools/${school.id}/requirements`, { method: 'PUT', body: JSON.stringify({ items: saved }) });
        setMsg(regsMsg, 'Saved \u2713');
        reqItems = saved;
      } catch (err) { setMsg(regsMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // Announcement form
    const annForm = document.getElementById('sd-ann-form');
    const annMsg  = document.getElementById('sd-ann-msg');
    annForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = annForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(annMsg, 'Submitting\u2026');
      const fd = { ...Object.fromEntries(new FormData(annForm)), source_type: 'School' };
      try {
        await api('/api/announcements', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(annMsg, 'Submitted for admin review.');
        annForm.reset();
        loadRecentAnnouncements();
      } catch (err) { setMsg(annMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // Material upload form
    const matForm = document.getElementById('sd-mat-form');
    const matMsg  = document.getElementById('sd-mat-msg');
    matForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = matForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(matMsg, 'Submitting\u2026');
      const rawFd = new FormData(matForm);
      const file = rawFd.get('file');
      const meta = { title: rawFd.get('title'), subject: rawFd.get('subject'), grade: rawFd.get('grade'), year: Number(rawFd.get('year')), type: rawFd.get('type') };
      try {
        const { id: newId } = await api('/api/materials', { method: 'POST', body: JSON.stringify(meta) });
        if (file && file.size > 0) {
          const fileFd = new FormData();
          fileFd.append('file', file);
          const token = getToken();
          const res = await fetch(`/api/materials/${newId}/upload`, { method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fileFd });
          if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.error || 'File upload failed'); }
        }
        setMsg(matMsg, 'Submitted for admin review.');
        matForm.reset();
        loadRecentMaterials();
      } catch (err) { setMsg(matMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // Load recent announcements & materials
    async function loadRecentAnnouncements() {
      const el = document.getElementById('sd-ann-list');
      if (!el) return;
      try {
        const { items } = await api('/api/announcements?approved=0');
        const mine = items.slice(0, 5);
        el.innerHTML = mine.length
          ? mine.map(a => `<div class="admin-audit-row"><p><strong>${esc(a.title)}</strong> <span class="tag tag-muted" class="u-audit-pending-tag">pending</span></p><p class="audit-time">${esc(a.created_at ? a.created_at.slice(0,10) : '')}</p></div>`).join('')
          : '<p class="empty-text">No pending announcements.</p>';
      } catch (_) { el.innerHTML = '<p class="empty-text">Could not load announcements.</p>'; }
    }

    async function loadRecentMaterials() {
      const el = document.getElementById('sd-mat-list');
      if (!el) return;
      try {
        const { items } = await api('/api/materials?approved=0');
        el.innerHTML = items.length
          ? items.map(m => `<div class="admin-audit-row"><p><strong>${esc(m.title)}</strong> <span class="tag tag-muted" class="u-audit-pending-tag">pending</span></p><p class="audit-time">${esc(m.subject)} &middot; ${esc(m.grade)} &middot; ${esc(m.year)}</p></div>`).join('')
          : '<p class="empty-text">No pending materials.</p>';
      } catch (_) { el.innerHTML = '<p class="empty-text">Could not load materials.</p>'; }
    }

    loadRecentAnnouncements();
    loadRecentMaterials();
  }

  // ── NGO Dashboard ─────────────────────────────────────────────────────────
  async function initNGODashboard() {
    if (!getToken()) { window.location.href = '/'; return; }
    const user = getUser();
    const notice = document.getElementById('ngo-dash-notice');
    if (user?.role !== 'ngo_officer' && user?.role !== 'admin') {
      if (notice) notice.style.display = 'block';
      return;
    }

    // Load NGO data
    let ngoData;
    try {
      ngoData = await api('/api/my-ngo');
    } catch (err) {
      if (notice) { notice.textContent = err.message; notice.style.display = 'block'; }
      return;
    }

    const { ngo, scholarships: ngoScholarships, applications: ngoApps } = ngoData;
    const title = document.getElementById('ngo-dash-title');
    if (title) title.textContent = ngo ? ngo.org_name : 'Your organisation';

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('nd-sch-count', ngoScholarships?.length ?? 0);
    set('nd-app-count', ngoApps?.length ?? 0);
    set('nd-ann-count', '—');

    // Pre-fill org profile
    const orgForm = document.getElementById('nd-org-form');
    const orgMsg  = document.getElementById('nd-org-msg');
    if (orgForm && ngo) {
      const fill = (name, val) => { const el = orgForm.querySelector(`[name="${name}"]`); if (el && val != null) el.value = val; };
      fill('org_name', ngo.org_name); fill('contact', ngo.contact);
      fill('phone', ngo.phone); fill('email', ngo.email);
      fill('description', ngo.description);
    }
    orgForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = orgForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(orgMsg, 'Saving\u2026');
      const fd = Object.fromEntries(new FormData(orgForm));
      try {
        await api('/api/my-ngo', { method: 'PUT', body: JSON.stringify(fd) });
        setMsg(orgMsg, 'Saved \u2713');
      } catch (err) { setMsg(orgMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // Post scholarship form
    const schForm = document.getElementById('nd-sch-form');
    const schMsg  = document.getElementById('nd-sch-msg');
    schForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = schForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(schMsg, 'Submitting\u2026');
      const fd = Object.fromEntries(new FormData(schForm));
      fd.ngo_id = ngo?.id;
      try {
        await api('/api/scholarships', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(schMsg, 'Submitted for admin review.');
        schForm.reset();
        loadMyScholarships();
      } catch (err) { setMsg(schMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // My scholarships list
    async function loadMyScholarships() {
      const el = document.getElementById('nd-sch-list');
      if (!el) return;
      try {
        const { items } = await api('/api/scholarships?approved=0');
        const withApproved = await api('/api/scholarships');
        const all = [...items, ...withApproved.items];
        el.innerHTML = all.length
          ? all.map(s => `<div class="admin-audit-row"><p><strong>${esc(s.title)}</strong> <span class="tag tag-muted" class="u-audit-pending-tag">${esc(s.provider || 'Your NGO')}</span></p><p class="audit-time">Deadline: ${esc(s.deadline)}</p></div>`).join('')
          : '<p class="empty-text">No scholarships posted yet.</p>';
      } catch (_) { }
    }

    // Applications list
    const appList = document.getElementById('nd-app-list');
    if (appList && ngoApps?.length) {
      appList.innerHTML = ngoApps.map(a => `
        <div class="admin-user-row">
          <div><strong>${esc(a.applicant_name || 'Applicant')}</strong><span>${esc(a.scholarship_title)} &middot; Applied ${esc(a.applied_at ? a.applied_at.slice(0,10) : '')}</span></div>
          ${appStatusBadge(a.status)}
        </div>`).join('');
    } else if (appList) {
      appList.innerHTML = '<p class="empty-text">No applications yet.</p>';
    }

    loadMyScholarships();
  }

  // ── Accept Invite ─────────────────────────────────────────────────────────
  async function initAcceptInvite() {
    const token = new URLSearchParams(location.search).get('token') || '';
    const loadingEl  = document.getElementById('invite-loading');
    const invalidEl  = document.getElementById('invite-invalid');
    const invalidMsg = document.getElementById('invite-invalid-msg');
    const formWrap   = document.getElementById('invite-form-wrap');
    const tokenInput = document.getElementById('invite-token-input');
    const entityLabel = document.getElementById('invite-entity-label');
    const emailDisplay = document.getElementById('invite-email-display');

    if (!token) {
      if (loadingEl) loadingEl.style.display = 'none';
      if (invalidEl) invalidEl.style.display = 'block';
      return;
    }

    try {
      const inv = await api(`/api/invitations/check?token=${encodeURIComponent(token)}`);
      if (loadingEl) loadingEl.style.display = 'none';
      if (tokenInput) tokenInput.value = token;
      if (entityLabel) entityLabel.textContent = inv.entity_name
        ? `Admin invitation — ${inv.entity_name}`
        : 'Admin invitation';
      if (emailDisplay) emailDisplay.textContent = `Your account will be created for: ${inv.email}`;
      if (formWrap) formWrap.style.display = 'block';
    } catch (err) {
      if (loadingEl) loadingEl.style.display = 'none';
      if (invalidMsg) invalidMsg.textContent = err.message;
      if (invalidEl) invalidEl.style.display = 'block';
      return;
    }

    const form = document.getElementById('accept-invite-form');
    const msg  = document.getElementById('invite-message');
    form?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(msg, 'Creating account\u2026');
      const fd = Object.fromEntries(new FormData(form));
      if (fd.password !== fd.confirm_password) {
        setMsg(msg, 'Passwords do not match.', true);
        btn.disabled = false;
        return;
      }
      try {
        const data = await api('/api/accept-invite', {
          method: 'POST',
          body: JSON.stringify({ token: fd.token, name: fd.name, password: fd.password }),
        });
        saveSession(data.token, data.user);
        window.location.href = data.user.role === 'school_admin' ? '/school-dashboard' : '/ngo-dashboard';
      } catch (err) {
        setMsg(msg, err.message, true);
        btn.disabled = false;
      }
    });
  }

  // ── Boot ──────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.page || '';

    if (document.getElementById('login-form'))    initLogin();
    if (document.getElementById('register-form')) initRegister();
    if (document.getElementById('forgot-form'))   initForgotPassword();
    if (page === 'accept-invite')  initAcceptInvite();
    if (page === 'dashboard' || document.getElementById('stat-schools')) initDashboard();
    if (page === 'directory')        initDirectory();
    if (document.getElementById('school-shell'))  initSchoolProfile();
    if (page === 'materials')        initMaterials();
    if (page === 'opportunities')    initOpportunities();
    if (page === 'announcements')    initAnnouncements();
    if (page === 'my-applications')  initMyApplications();
    if (page === 'bookmarks')        initBookmarks();
    if (page === 'profile')          initProfile();
    if (page === 'settings')         initSettings();
    if (page === 'admin')            initAdmin();
    if (page === 'school-dashboard') initSchoolDashboard();
    if (page === 'ngo-dashboard')    initNGODashboard();
  });

})();


