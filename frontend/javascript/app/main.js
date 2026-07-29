(function () {
  'use strict';

  const TOKEN_KEY   = 'eduportal_token';
  const REFRESH_KEY = 'eduportal_refresh_token';
  const USER_KEY    = 'eduportal_user';

  function getToken() { return localStorage.getItem(TOKEN_KEY); }
  function getRefreshToken() { return localStorage.getItem(REFRESH_KEY); }
  function getUser()  { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } }
  // Parent accounts can search and view listings but not save them — every
  // "Save"/bookmark affordance in the UI must check this, not just getToken().
  function canBookmark() { const u = getUser(); return !!getToken() && (!u || u.role !== 'parent'); }
  // Parent accounts can view/stream materials but not download a copy.
  function canDownloadMaterial() { const u = getUser(); return !!getToken() && (!u || u.role !== 'parent'); }

  // Shared by every "Save"/bookmark button across directory, materials, and
  // scholarship listings — POSTs the bookmark then updates the button to
  // reflect success/failure. `opts.onSuccess` lets scholarship buttons apply
  // their distinct styling; the default matches the school/material buttons.
  // `opts.alreadyText` lets callers customize the "already bookmarked" message.
  async function saveBookmark(btn, itemType, itemId, opts) {
    opts = opts || {};
    btn.disabled = true;
    try {
      await api('/api/bookmarks', { method: 'POST', body: JSON.stringify({ item_type: itemType, item_id: itemId }) });
      if (opts.onSuccess) opts.onSuccess(btn); else btn.textContent = 'Saved ✓';
    } catch (err) {
      btn.textContent = (opts.alreadyText && err.message.includes('already')) ? opts.alreadyText : err.message;
      btn.disabled = false;
    }
  }

  // Shared by the scholarship detail panel and list-view "Apply" buttons.
  async function applyToScholarship(btn, scholarshipId) {
    btn.disabled = true;
    btn.textContent = 'Submitting…';
    try {
      await api('/api/applications', { method: 'POST', body: JSON.stringify({ scholarship_id: scholarshipId }) });
      btn.textContent = 'Application submitted';
      btn.style.background = '#1a7a3c';
    } catch (err) {
      btn.textContent = err.message.includes('already') ? 'Already applied' : err.message;
      btn.disabled = false;
    }
  }

  // Shared by the scholarship posting forms on /opportunities and /ngo-dashboard.
  async function uploadScholarshipMedia(scholarshipId, fieldName, file) {
    if (!file || !file.size) return;
    try {
      await EP.uploadFile(`/api/scholarships/${scholarshipId}/${fieldName}`, fieldName, file);
    } catch (err) {
      throw new Error(err.message || `${fieldName === 'poster' ? 'Poster image' : 'Video'} upload failed`);
    }
  }

  function saveSession(token, user, refreshToken) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken);
  }
  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }

  // Fetch wrapper — retries once with a refreshed access token on a 401
  async function api(path, opts = {}, _retried = false) {
    const headers = { ...(opts.headers || {}) };
    if (opts.body) headers['Content-Type'] = 'application/json';
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(path, { ...opts, headers });
    if (res.status === 401 && !_retried && path !== '/api/refresh' && getRefreshToken()) {
      const refreshed = await EP.refreshSession();
      if (refreshed) return api(path, opts, true);
      clearSession();
    }
    const ct   = res.headers.get('content-type') || '';
    const body = ct.includes('application/json') ? await res.json() : await res.text();
    if (!res.ok) throw new Error((body && body.error) || `HTTP ${res.status}`);
    return body;
  }

  const esc = EP.esc;

  // Scholarship deadlines are plain YYYY-MM-DD strings, so a lexicographic
  // comparison against today's date is a valid (and cheap) "still open" check.
  function isOpenDeadline(deadline) {
    return !!deadline && deadline >= new Date().toISOString().slice(0, 10);
  }

  // School "Hours" is a single free-text DB column (no schema change here),
  // but typing "7:30 AM - 3:30 PM" by hand is error-prone — these compose a
  // real <input type="time"> pair plus a day-of-week checkbox row into that
  // same text format on save, and best-effort parse it back on load.
  const HOURS_DAYS = [
    ['mon', 'Mon'], ['tue', 'Tue'], ['wed', 'Wed'], ['thu', 'Thu'],
    ['fri', 'Fri'], ['sat', 'Sat'], ['sun', 'Sun'],
  ];

  function hoursTo12h(hhmm) {
    if (!hhmm) return '';
    const [h, m] = hhmm.split(':').map(Number);
    const period = h >= 12 ? 'PM' : 'AM';
    const h12 = ((h + 11) % 12) + 1;
    return `${h12}:${String(m).padStart(2, '0')} ${period}`;
  }

  function hoursTo24h(h12) {
    const m = /^(\d{1,2}):(\d{2})\s*(AM|PM)$/i.exec((h12 || '').trim());
    if (!m) return '';
    let h = parseInt(m[1], 10);
    const period = m[3].toUpperCase();
    if (period === 'PM' && h !== 12) h += 12;
    if (period === 'AM' && h === 12) h = 0;
    return `${String(h).padStart(2, '0')}:${m[2]}`;
  }

  function composeHours(form) {
    const days = HOURS_DAYS
      .filter(([key]) => form.querySelector(`[name="hours_day_${key}"]`)?.checked)
      .map(([, label]) => label);
    const open  = form.querySelector('[name="hours_open"]')?.value;
    const close = form.querySelector('[name="hours_close"]')?.value;
    const dayPart  = days.join(', ');
    const timePart = (open && close) ? `${hoursTo12h(open)} – ${hoursTo12h(close)}` : '';
    if (dayPart && timePart) return `${dayPart} · ${timePart}`;
    return dayPart || timePart || '';
  }

  function fillHoursPickers(form, hoursStr) {
    if (!hoursStr) return;
    const [dayPart, timePart] = hoursStr.split('·').map(s => s && s.trim());
    const selected = (dayPart || '').split(',').map(s => s.trim().toLowerCase().slice(0, 3));
    HOURS_DAYS.forEach(([key]) => {
      const el = form.querySelector(`[name="hours_day_${key}"]`);
      if (el) el.checked = selected.includes(key);
    });
    const range = /^(.+?)\s*[–-]\s*(.+)$/.exec(timePart || '');
    if (range) {
      const openEl  = form.querySelector('[name="hours_open"]');
      const closeEl = form.querySelector('[name="hours_close"]');
      if (openEl)  openEl.value  = hoursTo24h(range[1]);
      if (closeEl) closeEl.value = hoursTo24h(range[2]);
    }
  }

  // Shared by the school-logo and NGO-logo uploaders: same optimistic-preview
  // pattern as the profile avatar, including reverting the preview if the
  // upload fails so a rejected file never looks saved when it wasn't.
  function wireLogoUpload({ inputEl, imgEl, fallbackEl, msgEl, uploadUrl, currentUrl }) {
    if (imgEl && fallbackEl) {
      if (currentUrl) {
        imgEl.src = currentUrl;
        imgEl.classList.remove('hidden');
        fallbackEl.classList.add('hidden');
      } else {
        imgEl.classList.add('hidden');
        fallbackEl.classList.remove('hidden');
      }
    }
    inputEl?.addEventListener('change', async () => {
      const file = inputEl.files?.[0];
      if (!file) return;
      if (file.size > 2 * 1024 * 1024) { setMsg(msgEl, 'Image must be under 2 MB.', true); return; }
      const previousSrc = imgEl ? imgEl.src : '';
      const previousImgHidden = imgEl ? imgEl.classList.contains('hidden') : true;
      const previousFallbackHidden = fallbackEl ? fallbackEl.classList.contains('hidden') : true;
      const reader = new FileReader();
      reader.onload = (ev) => {
        if (imgEl) { imgEl.src = ev.target.result; imgEl.classList.remove('hidden'); }
        if (fallbackEl) fallbackEl.classList.add('hidden');
      };
      reader.readAsDataURL(file);
      try {
        const data = await EP.uploadFile(uploadUrl, 'logo', file);
        setMsg(msgEl, 'Logo saved.');
        if (imgEl) imgEl.src = data.logo_url + '?t=' + Date.now();
      } catch (err) {
        if (imgEl) { imgEl.src = previousSrc; imgEl.classList.toggle('hidden', previousImgHidden); }
        if (fallbackEl) fallbackEl.classList.toggle('hidden', previousFallbackHidden);
        setMsg(msgEl, 'Upload failed, logo was not saved: ' + err.message, true);
      }
    });
  }

  // A dropdown filter that silently does nothing until a separate "Search"
  // button is clicked reads as broken to most users — apply it the moment
  // it changes. Free-text search stays on manual submit (Enter/button) so
  // it doesn't re-query on every keystroke.
  function autoApplyFilterSelects(form, onChange) {
    form?.querySelectorAll('select').forEach(sel => sel.addEventListener('change', onChange));
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

  // VAPID public keys are base64url — the Push API wants a raw Uint8Array
  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const output = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) output[i] = rawData.charCodeAt(i);
    return output;
  }

  // PDF checklist download (no external lib)
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

  function materialKindFromPath(filePath) {
    if (!filePath || typeof filePath !== 'string') return 'file';
    const ext = filePath.includes('.') ? filePath.split('.').pop().toLowerCase() : '';
    return ['mp4', 'webm', 'ogg', 'm4v'].includes(ext) ? 'video' : 'file';
  }

  // The material's own `type` field ("tutorial video" vs. past paper/study
  // guide/teacher note) is the authoritative signal — it's chosen from a
  // fixed dropdown at upload time. Falling back to sniffing the file
  // extension only matters for old rows saved before `type` existed.
  function materialIsVideo(m) {
    return m.type === 'tutorial video' || materialKindFromPath(m.file_path) === 'video';
  }

  // Shows a small preview the moment a file is chosen — a video plays its
  // first frame as a thumbnail, an image shows the picture itself — so
  // the person can confirm what they picked before submitting, instead of
  // trusting a bare filename next to the native "Choose File" button.
  function wireFilePreview(inputEl, previewEl) {
    if (!inputEl || !previewEl) return;
    let lastUrl = null;
    inputEl.addEventListener('change', () => {
      if (lastUrl) { URL.revokeObjectURL(lastUrl); lastUrl = null; }
      const file = inputEl.files && inputEl.files[0];
      if (!file) {
        previewEl.innerHTML = '';
        previewEl.classList.add('hidden');
        return;
      }
      const kind = materialKindFromPath(file.name);
      if (kind === 'video') {
        lastUrl = URL.createObjectURL(file);
        previewEl.innerHTML = `
          <video muted preload="metadata" class="file-preview-video"></video>
          <span class="file-preview-label">🎬 Video selected — ${esc(file.name)}</span>`;
        const videoEl = previewEl.querySelector('video');
        videoEl.src = lastUrl;
        videoEl.addEventListener('loadedmetadata', () => { try { videoEl.currentTime = 0.1; } catch (e) { /* ignore */ } });
      } else if (file.type.startsWith('image/')) {
        lastUrl = URL.createObjectURL(file);
        previewEl.innerHTML = `
          <img class="file-preview-image" alt="">
          <span class="file-preview-label">🖼️ Image selected — ${esc(file.name)}</span>`;
        previewEl.querySelector('img').src = lastUrl;
      } else {
        previewEl.innerHTML = `<span class="file-preview-label">📄 File selected — ${esc(file.name)}</span>`;
      }
      previewEl.classList.remove('hidden');
    });
  }

  // Pagination helper
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

  // Where a signed-in user lands: the platform admin's workspace is the
  // Admin Panel, not the student/parent-oriented browse-and-apply dashboard.
  function postAuthRedirectPath(user) {
    return user && user.role === 'admin' ? '/admin' : '/dashboard';
  }

  // Google Sign-In button — rendered manually rather than via the library's
  // declarative data-width scan, since that attribute only accepts a fixed
  // pixel value: a width sized for desktop overflowed narrow mobile screens
  // instead of shrinking to fit. Sized here to whatever room the slot
  // actually has, capped to Google's supported 200-400px range.
  window.initGoogleSignIn = function () {
    if (!window.google || !window.google.accounts || !window.GOOGLE_CLIENT_ID) return;
    const slot = document.getElementById('google-signin-btn');
    if (!slot) return;
    google.accounts.id.initialize({
      client_id: window.GOOGLE_CLIENT_ID,
      callback: window.handleGoogleCredential,
    });
    const available = slot.clientWidth || (slot.parentElement && slot.parentElement.clientWidth) || 400;
    const width = Math.max(200, Math.min(400, Math.floor(available)));
    google.accounts.id.renderButton(slot, {
      type: 'standard', shape: 'pill', size: 'large', text: 'continue_with', logo_alignment: 'left', width,
    });
  };

  // Google Sign-In — called by Google's Identity Services button once the user completes the flow
  window.handleGoogleCredential = async function (response) {
    const msg = document.getElementById('login-message') || document.getElementById('register-message');
    try {
      const data = await api('/api/auth/google', { method: 'POST', body: JSON.stringify({ credential: response.credential }) });
      if (data.needs_role) {
        showGoogleRolePicker(response.credential, data.name, data.email);
        return;
      }
      saveSession(data.token, data.user, data.refresh_token);
      window.location.href = postAuthRedirectPath(data.user);
    } catch (err) {
      setMsg(msg, err.message || 'Google sign-in failed.', true);
    }
  };

  // Shown once, the first time a brand-new Google account signs in — the
  // backend deliberately does not default new accounts to any role
  // (in particular never to "admin", which is assigned by an existing
  // admin, not chosen at signup) until the person picks one here.
  function showGoogleRolePicker(credential, name, email) {
    const existing = document.getElementById('google-role-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'google-role-modal';
    modal.className = 'role-picker-overlay';
    modal.innerHTML = `
      <div class="role-picker-card">
        <p class="role-picker-eyebrow">One last step</p>
        <h2 class="role-picker-title">Welcome, ${esc((name || email || '').split(' ')[0] || 'there')}</h2>
        <p class="role-picker-copy">Tell us who you are so EduPortal shows you the right tools.</p>
        <div class="role-picker-grid">
          <button type="button" class="role-picker-option" data-role="student"><i data-lucide="graduation-cap" width="20" height="20"></i>Student</button>
          <button type="button" class="role-picker-option" data-role="parent"><i data-lucide="users" width="20" height="20"></i>Parent</button>
          <button type="button" class="role-picker-option" data-role="teacher"><i data-lucide="presentation" width="20" height="20"></i>Teacher</button>
          <button type="button" class="role-picker-option" data-role="school_admin"><i data-lucide="school" width="20" height="20"></i>School Admin</button>
          <button type="button" class="role-picker-option" data-role="ngo_officer"><i data-lucide="heart-handshake" width="20" height="20"></i>Organisation Officer</button>
        </div>
        <p id="google-role-msg" class="status-message"></p>
      </div>`;
    document.body.appendChild(modal);
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();

    const msgEl = document.getElementById('google-role-msg');
    modal.querySelectorAll('.role-picker-option').forEach((btn) => {
      btn.addEventListener('click', async () => {
        modal.querySelectorAll('.role-picker-option').forEach((b) => b.disabled = true);
        setMsg(msgEl, 'Setting up your account…');
        try {
          const data = await api('/api/auth/google', {
            method: 'POST',
            body: JSON.stringify({ credential, role: btn.dataset.role }),
          });
          saveSession(data.token, data.user, data.refresh_token);
          window.location.href = postAuthRedirectPath(data.user);
        } catch (err) {
          setMsg(msgEl, err.message, true);
          modal.querySelectorAll('.role-picker-option').forEach((b) => b.disabled = false);
        }
      });
    });
  }

  // Login
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
        saveSession(data.token, data.user, data.refresh_token);
        window.location.href = postAuthRedirectPath(data.user);
      } catch (err) {
        setMsg(msg, err.message, true);
        btn.disabled = false;
      }
    });
  }

  // Register
  function initRegister() {
    const form = document.getElementById('register-form');
    const msg  = document.getElementById('register-message');
    if (!form) return;

    // Password strength meter
    const pwInput = document.getElementById('reg-password');
    const pwBar   = document.getElementById('pw-strength-bar');
    const pwLabel = document.getElementById('pw-strength-label');
    const pwWrap  = document.getElementById('pw-strength-wrap');
    if (pwInput) {
      pwInput.addEventListener('input', () => {
        const v = pwInput.value;
        let score = 0;
        if (v.length >= 8)  score++;
        if (/[A-Z]/.test(v)) score++;
        if (/[0-9]/.test(v)) score++;
        if (/[^A-Za-z0-9]/.test(v)) score++;
        const levels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
        const colors = ['', '#9c3b2e', '#fe7f2d', '#b86000', '#000000'];
        pwWrap.style.display = v.length ? 'block' : 'none';
        pwBar.style.width  = v.length ? (score / 4 * 100) + '%' : '0';
        pwBar.style.background = colors[score] || '#ccc';
        pwLabel.textContent = v.length ? levels[score] || '' : '';
        pwLabel.style.color = colors[score] || '#ccc';
      });
    }

    // Password visibility toggle (register page's own password field)
    document.querySelector('[data-toggle-password]')?.addEventListener('click', function () {
      const input = document.getElementById('reg-password');
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      this.querySelector('.eye-open')?.classList.toggle('hidden', show);
      this.querySelector('.eye-closed')?.classList.toggle('hidden', !show);
    });

    // Two-step registration wizard
    const step1 = document.getElementById('register-step-1');
    const step2 = document.getElementById('register-step-2');
    const nextBtn = document.getElementById('register-next-btn');
    const backBtn = document.getElementById('register-back-btn');
    const step1Msg = document.getElementById('register-step1-message');
    const progressBar = document.querySelector('.register-progress-bar');
    const CHECK_SVG = '<svg viewBox="0 0 16 16" fill="none" width="14" height="14" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8l3.5 3.5L13 4"/></svg>';

    function setStep(step) {
      step1.classList.toggle('hidden', step !== 1);
      step2.classList.toggle('hidden', step !== 2);
      if (progressBar) progressBar.style.width = step === 1 ? '50%' : '100%';

      // Only the first left-panel step ("Create your account") reflects real
      // progress — it flips to done once the user has passed its validation.
      const firstStep = document.getElementById('lp-step-1');
      const firstCircle = firstStep?.querySelector('.lp-step-circle');
      if (firstCircle) {
        const done = step > 1;
        firstStep.classList.toggle('lp-step--done', done);
        firstCircle.classList.toggle('lp-step-circle--outline', !done);
        firstCircle.innerHTML = done ? CHECK_SVG : '1';
      }

      if (step === 2) step2.querySelector('select[name="role"]')?.focus();
      else step1.querySelector('input[name="name"]')?.focus();
    }

    nextBtn?.addEventListener('click', function () {
      const nameInput = step1.querySelector('input[name="name"]');
      const pwInput2  = step1.querySelector('input[name="password"]');
      if (!nameInput.value.trim()) {
        setMsg(step1Msg, 'Please enter your full name.', true);
        nameInput.focus();
        return;
      }
      if (pwInput2.value.length < 8) {
        setMsg(step1Msg, 'Password must be at least 8 characters.', true);
        pwInput2.focus();
        return;
      }
      setMsg(step1Msg, '');
      setStep(2);
    });

    backBtn?.addEventListener('click', function () { setStep(1); });

    if (progressBar) progressBar.style.width = '50%'; // init only — skip the focus() from setStep(1) on load

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(msg, 'Creating account\u2026');
      const fd = Object.fromEntries(new FormData(form));
      try {
        const data = await api('/api/register', { method: 'POST', body: JSON.stringify(fd) });
        if (data.email_verification_required) {
          // Registering with an email leaves the account unverified until
          // the link in that email is clicked \u2014 there's no token yet, so
          // don't touch session storage or redirect like the phone-only
          // path below does.
          form.reset();
          if (msg) {
            msg.classList.remove('is-error');
            msg.classList.add('is-success');
            msg.innerHTML = esc(data.message || 'Registration successful. Please check your email to verify your account.');
            if (data.dev_verify_url) {
              msg.innerHTML += '<br><small>Email delivery isn\u2019t set up in this environment, so nothing was actually sent. '
                + 'Use this link to verify your account instead: '
                + '<a href="' + esc(data.dev_verify_url) + '">' + esc(data.dev_verify_url) + '</a></small>';
            }
          }
          btn.disabled = false;
          return;
        }
        saveSession(data.token, data.user, data.refresh_token);
        window.location.href = postAuthRedirectPath(data.user);
      } catch (err) {
        setMsg(msg, err.message, true);
        btn.disabled = false;
      }
    });
  }

  // Dashboard
  async function initDashboard() {
    const isAuthed = !!getToken();
    const user = getUser();

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

    const appsEl = document.getElementById('dashboard-applications');
    const alertsEl = document.getElementById('dashboard-notifications');
    const appsCountEl = document.getElementById('stat-applications');

    if (!isAuthed) {
      if (appsCountEl) appsCountEl.textContent = '0';
      if (appsEl) appsEl.innerHTML = '<p class="empty-text">Sign in to view your applications.</p>';
      if (alertsEl) alertsEl.innerHTML = '<p class="empty-text">Sign in to view your notifications.</p>';
    } else {
      try {
        const [{ items: applications }, { items: notifications }] = await Promise.all([
          api('/api/applications'),
          api('/api/notifications'),
        ]);

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
        if (appsCountEl) appsCountEl.textContent = '0';
        if (appsEl) appsEl.innerHTML = '<p class="empty-text">Your application history is unavailable right now.</p>';
        if (alertsEl) alertsEl.innerHTML = '<p class="empty-text">Alerts are unavailable right now.</p>';
      }
    }

    try {
      const { items } = await api('/api/scholarships');
      const container = document.getElementById('dashboard-scholarships');
      if (container) {
        const open = items.filter(s => isOpenDeadline(s.deadline));
        container.innerHTML = open.slice(0, 3).map(s => `
          <a class="opportunity-card" href="/opportunities">
            <span class="tag">Scholarship</span>
            <h3>${esc(s.title)}</h3>
            <p class="org">${esc(s.provider || 'Verified NGO')}</p>
            <div class="result-card-footer">
              <span class="deadline-badge">Deadline: <strong>${esc(s.deadline)}</strong></span>
              <span class="card-link">Details</span>
            </div>
          </a>`).join('') || '<p class="empty-text">No scholarships available.</p>';
      }
    } catch (err) {
      const container = document.getElementById('dashboard-scholarships');
      if (container) {
        container.innerHTML = '<p class="empty-text">Scholarships are unavailable right now. Open the scholarships page for the latest programs.</p>';
      }
    }

    const savedEl = document.getElementById('stat-saved');
    if (!isAuthed) {
      if (savedEl) savedEl.textContent = '0';
    } else {
      try {
        const { items } = await api('/api/bookmarks');
        if (savedEl) savedEl.textContent = items.filter(b => b.item_type === 'school').length;
      } catch (_) {
        if (savedEl) savedEl.textContent = '0';
      }
    }
  }

  // Directory
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
            ${school.logo_url ? `<img class="school-detail-logo school-detail-logo-sm" src="${esc(school.logo_url)}" alt="${esc(school.name)} logo">` : ''}
            <div class="u-flex-wrap u-mb-sm">
              <span class="tag">${esc(school.state)}</span>
              ${statusBadge(school.status)}
            </div>
            <h2 class="u-card-title-md">${esc(school.name)}</h2>
            <p class="u-card-copy">${esc(school.county)} &middot; ${esc(school.level)} &middot; ${esc(school.boarding || 'Day')} &middot; ${esc(school.type || 'Mixed')}</p>
            <div class="u-card-copy-sm">${EP.paragraphs(school.description)}</div>
            <p class="u-card-copy-xs">Hours: ${esc(school.hours || 'N/A')} &middot; Capacity: ${esc(school.capacity)} &middot; Enrolled: ${esc(school.enrollment)}</p>
            <p class="u-card-copy-xs">Contact: ${esc(school.contact_name)} &middot; ${esc(school.phone)}</p>
            <div class="u-card-inline-actions">
              <a class="card-button u-card-button-link" href="/schools/${school.id}">Full profile</a>
              ${canBookmark() ? `<button class="card-button bookmark-btn u-card-button-outline-link" data-type="school" data-id="${school.id}">Save school</button>` : ''}
            </div>
          </div>`;
        if (inlineReqs) {
          const reqParts = [];
          if (school.requirements_text) {
            reqParts.push(`<p class="u-list-copy">${esc(school.requirements_text).replace(/\n/g, '<br>')}</p>`);
          }
          if (items.length) {
            reqParts.push(items.map(r => `
                <label class="checklist-item">
                  <input type="checkbox" ${r.is_required ? 'checked' : ''} disabled>
                  <span>
                    <strong>${esc(r.item_label)}</strong>
                    ${!r.is_required ? '<span class="tag tag-muted checklist-optional-tag">Optional</span>' : ''}
                    ${r.notes ? `<span class="u-list-copy-xs checklist-note">${esc(r.notes)}</span>` : ''}
                  </span>
                </label>`).join(''));
          }
          if (school.requirements_doc_url) {
            reqParts.push(`<a class="card-link u-mt-sm" href="${esc(school.requirements_doc_url)}" download>Download requirements document</a>`);
          }
          inlineReqs.innerHTML = `<p class="section-label u-card-section-label">ADMISSION CHECKLIST</p>` +
            (reqParts.length ? reqParts.join('') : '<p class="u-list-copy">No requirements listed yet.</p>');
        }
        inlineDetail.querySelector('.bookmark-btn')?.addEventListener('click', (e) => saveBookmark(e.currentTarget, 'school', id));
      } catch (err) {
        inlineDetail.innerHTML = `<p class="u-text-danger">${esc(err.message)}</p>`;
      }
    }

    async function load(page = 1) {
      currentPage = page;
      results.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      const params = EP.filterParamsFromForm(form);
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
                ${s.logo_url ? `<img class="school-card-logo" src="${esc(s.logo_url)}" alt="">` : ''}
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
    autoApplyFilterSelects(form, () => load(1));

    const preset = new URLSearchParams(location.search).get('search');
    if (preset && form) form.querySelector('[name="search"]').value = preset;

    load(1);
  }

  // School profile
  async function initSchoolProfile() {
    const shell = document.getElementById('school-shell');
    if (!shell) return;
    // Read ID from URL path since we removed the Jinja2 variable
    const id = schoolIdFromPath();
    if (!id) { shell.innerHTML = '<p class="u-text-danger">School not found.</p>'; return; }

    try {
      const [{ school }, { items }, { items: examResults }] = await Promise.all([
        api(`/api/schools/${id}`),
        api(`/api/schools/${id}/requirements`),
        api(`/api/schools/${id}/exam-results`),
      ]);

      // Update page title
      document.title = `${school.name} | EduPortal South Sudan`;
      const bannerH1 = document.querySelector('.top-banner h1');
      if (bannerH1) bannerH1.textContent = school.name;

      const detail = document.getElementById('school-detail');
      if (detail) {
        const facilityLabels = {
          has_library: 'Library', has_laboratory: 'Laboratory', has_sports_facilities: 'Sports facilities',
          has_water_sanitation: 'Water & sanitation', has_electricity: 'Electricity',
        };
        const activityLabels = {
          has_sports_clubs: 'Sports clubs', has_arts_culture: 'Arts & culture',
          has_academic_clubs: 'Academic clubs', has_student_government: 'Student government',
        };
        const activeFacilities = Object.keys(facilityLabels).filter(k => Number(school[k]));
        const activeActivities = Object.keys(activityLabels).filter(k => Number(school[k]));

        detail.innerHTML = `
          <div class="school-detail-header u-mb-md">
            ${school.logo_url ? `<img class="school-detail-logo" src="${esc(school.logo_url)}" alt="${esc(school.name)} logo">` : ''}
            <div class="school-detail-header-text">
              <h1 class="school-detail-title">${esc(school.name)}</h1>
              <div class="u-card-link-flex-end">
                <span class="tag">${esc(school.state)}</span>
                ${statusBadge(school.status)}
                <span class="tag tag-muted">${esc(school.type || 'Mixed')}</span>
                <span class="tag tag-muted">${esc(school.ownership === 'private' ? 'Private' : school.ownership === 'mission' ? 'Mission' : 'Public')}</span>
                ${school.registration_verified ? '<span class="tag tag-muted">Registration verified</span>' : ''}
              </div>
              <p class="u-card-copy">${esc(school.county)}, ${esc(school.state)} &middot; ${esc(school.level)} &middot; ${esc(school.boarding || 'Day')}</p>
            </div>
          </div>
          <div class="u-list-copy">${EP.paragraphs(school.description)}</div>
          <div class="detail-grid u-mb-md">
            <div class="detail-item detail-item-wide"><span class="detail-key">Hours</span><span>${esc(school.hours || 'N/A')}</span></div>
            <div class="detail-item"><span class="detail-key">Capacity</span><span>${esc(school.capacity)}</span></div>
            <div class="detail-item"><span class="detail-key">Enrolled</span><span>${esc(school.enrollment)}</span></div>
            <div class="detail-item"><span class="detail-key">Curriculum</span><span>${esc(school.curriculum)}</span></div>
            <div class="detail-item"><span class="detail-key">Language</span><span>${esc(school.language || 'English')}</span></div>
            <div class="detail-item"><span class="detail-key">Contact</span><span>${esc(school.contact_name)}</span></div>
            <div class="detail-item"><span class="detail-key">Phone</span><span>${esc(school.phone)}</span></div>
            ${school.email ? `<div class="detail-item detail-item-wide"><span class="detail-key">Email</span><span>${esc(school.email)}</span></div>` : ''}
            ${school.address ? `<div class="detail-item"><span class="detail-key">Address</span><span>${esc(school.address)}</span></div>` : ''}
            ${school.registration_number ? `<div class="detail-item"><span class="detail-key">Registration No.</span><span>${esc(school.registration_number)}</span></div>` : ''}
            ${school.year_established ? `<div class="detail-item"><span class="detail-key">Established</span><span>${esc(school.year_established)}</span></div>` : ''}
            ${school.headteacher_name ? `<div class="detail-item"><span class="detail-key">Headteacher</span><span>${esc(school.headteacher_name)}</span></div>` : ''}
            ${school.teaching_staff_count ? `<div class="detail-item"><span class="detail-key">Teaching Staff</span><span>${esc(school.teaching_staff_count)}</span></div>` : ''}
            ${school.classroom_count ? `<div class="detail-item"><span class="detail-key">Classrooms</span><span>${esc(school.classroom_count)}</span></div>` : ''}
          </div>
          ${school.mission || school.vision || school.core_values ? `
            <div class="u-mb-md">
              ${school.mission ? `<p class="detail-key">Mission</p><div class="u-list-copy">${EP.paragraphs(school.mission)}</div>` : ''}
              ${school.vision ? `<p class="detail-key">Vision</p><div class="u-list-copy">${EP.paragraphs(school.vision)}</div>` : ''}
              ${school.core_values ? `<p class="detail-key">Core Values</p><div class="u-list-copy">${EP.paragraphs(school.core_values)}</div>` : ''}
            </div>` : ''}
          ${school.subjects_offered ? `<p class="detail-key">Subjects Offered</p><div class="subjects-grid u-mb-md">${
            school.subjects_offered.split(/[,\n]/).map(s => s.trim()).filter(Boolean)
              .map(s => `<span class="subject-chip">${esc(s)}</span>`).join('')
          }</div>` : ''}
          ${activeFacilities.length ? `
            <p class="detail-key">Facilities</p>
            <div class="u-card-link-flex-end u-mb-md">${activeFacilities.map(k => `<span class="tag tag-muted">${esc(facilityLabels[k])}</span>`).join('')}</div>` : ''}
          ${activeActivities.length || school.extracurricular_other ? `
            <p class="detail-key">Extracurricular Activities</p>
            <div class="u-card-link-flex-end u-mb-md">${activeActivities.map(k => `<span class="tag tag-muted">${esc(activityLabels[k])}</span>`).join('')}${
              (school.extracurricular_other || '').split(',').map(s => s.trim()).filter(Boolean)
                .map(t => `<span class="tag tag-muted">${esc(t)}</span>`).join('')
            }</div>` : ''}
          ${examResults.length ? `
            <p class="detail-key">National Exam Pass Rates</p>
            <div class="detail-grid u-mb-md">${examResults.map(r => `<div class="detail-item"><span class="detail-key">${esc(r.subject)} (${esc(r.year)})</span><span>${esc(r.pass_rate)}%</span></div>`).join('')}</div>` : ''}
          ${school.age_requirements || school.entry_grades || school.fees_structure || school.how_to_apply ? `
            <p class="detail-key">Admission Information</p>
            <div class="detail-grid u-mb-md">
              ${school.age_requirements ? `<div class="detail-item"><span class="detail-key">Age Requirements</span><span>${esc(school.age_requirements)}</span></div>` : ''}
              ${school.entry_grades ? `<div class="detail-item"><span class="detail-key">Entry Grades</span><span>${esc(school.entry_grades)}</span></div>` : ''}
            </div>
            ${school.fees_structure ? `<p class="detail-key">Fees</p><div class="u-list-copy">${EP.paragraphs(school.fees_structure)}</div>` : ''}
            ${school.how_to_apply ? `<p class="detail-key">How to Apply</p><div class="u-list-copy u-mb-md">${EP.paragraphs(school.how_to_apply)}</div>` : ''}` : ''}
          ${canBookmark() ? `<button class="card-button bookmark-btn u-card-button-compact-sm" data-type="school" data-id="${school.id}">Save school</button>` : ''}`;
      }

      const checklist = document.getElementById('school-checklist');
      if (checklist) {
        const parts = [];
        if (school.requirements_text) {
          parts.push(`<p class="u-list-copy">${esc(school.requirements_text).replace(/\n/g, '<br>')}</p>`);
        }
        if (items.length) {
          parts.push(items.map(r => `
              <label class="checklist-item">
                <input type="checkbox" class="checklist-tick" ${r.is_required ? 'checked' : ''}>
                <span>
                  <strong>${esc(r.item_label)}</strong>
                  ${!r.is_required ? '<span class="tag tag-muted checklist-optional-tag">Optional</span>' : ''}
                  ${r.notes ? `<span class="u-list-copy-xs checklist-note">${esc(r.notes)}</span>` : ''}
                </span>
              </label>`).join(''));
        }
        checklist.innerHTML = parts.length ? parts.join('') : '<p class="u-text-muted">No requirements listed yet.</p>';

        // Prefer a real uploaded document; fall back to generating a PDF
        // from the itemised list (legacy schools that used the old editor).
        if (school.requirements_doc_url) {
          const dlLink = document.createElement('a');
          dlLink.className = 'card-button u-card-button-compact-sm u-inline-flex-center u-mt-md';
          dlLink.href = school.requirements_doc_url;
          dlLink.setAttribute('download', '');
          dlLink.innerHTML = `<svg viewBox="0 0 16 16" fill="none" width="15" height="15"><path d="M8 2v8M5 7l3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg> Download Requirements Document`;
          checklist.after(dlLink);
        } else if (items.length) {
          const dlBtn = document.createElement('button');
          dlBtn.className = 'card-button u-card-button-compact-sm u-inline-flex-center u-mt-md';
          dlBtn.innerHTML = `<svg viewBox="0 0 16 16" fill="none" width="15" height="15"><path d="M8 2v8M5 7l3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg> Download checklist PDF`;
          checklist.after(dlBtn);
          dlBtn.addEventListener('click', () => downloadChecklistPDF(school, items));
        }
      }

      shell.addEventListener('click', (e) => {
        const btn = e.target.closest('.bookmark-btn');
        if (!btn) return;
        saveBookmark(btn, btn.dataset.type, btn.dataset.id);
      });

      // School admin edit panel
      try {
        const { user: me } = await api('/api/me');
        if (me.role === 'school_admin' && me.school_id === Number(id) || me.role === 'admin') {
          _renderSchoolEditPanel(shell, school, id);
        }
      } catch (_) {}

    } catch (err) {
      const detail = document.getElementById('school-detail');
      if (detail) detail.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
    }
  }

  function _renderSchoolEditPanel(shell, school, id) {
    const panel = document.createElement('section');
    panel.className = 'card content-panel u-panel-top-md';
    panel.innerHTML = `
      <p class="section-label">MANAGE SCHOOL PROFILE</p>
      <p class="school-note u-school-note">You are the assigned admin for this school. Changes are saved immediately.</p>

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
              <option value="both" ${school.level==='both'?'selected':''}>Both</option>
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
              <option value="Both" ${school.boarding==='Both'?'selected':''}>Both</option>
            </select>
          </label>
          <label class="field-label">Ownership
            <select class="field-input" name="ownership">
              <option value="public" ${school.ownership==='public'?'selected':''}>Public</option>
              <option value="private" ${school.ownership==='private'?'selected':''}>Private</option>
              <option value="mission" ${school.ownership==='mission'?'selected':''}>Mission</option>
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
          <label class="field-label">Curriculum
            <input class="field-input" name="curriculum" value="${esc(school.curriculum||'')}">
          </label>
          <label class="field-label">Language
            <input class="field-input" name="language" value="${esc(school.language||'')}">
          </label>
          <label class="field-label">Registration Number
            <input class="field-input" name="registration_number" value="${esc(school.registration_number||'')}">
          </label>
          <label class="field-label">Year Established
            <input class="field-input" name="year_established" type="number" min="1900" max="2099" value="${esc(school.year_established||'')}">
          </label>
          <label class="field-label">Physical Address
            <input class="field-input" name="address" value="${esc(school.address||'')}">
          </label>
          <label class="field-label">Headteacher / Principal
            <input class="field-input" name="headteacher_name" value="${esc(school.headteacher_name||'')}">
          </label>
          <label class="field-label">Teaching Staff Count
            <input class="field-input" name="teaching_staff_count" type="number" min="0" value="${esc(school.teaching_staff_count||'')}">
          </label>
          <label class="field-label">Classroom Count
            <input class="field-input" name="classroom_count" type="number" min="0" value="${esc(school.classroom_count||'')}">
          </label>
          <label class="field-label">Age Requirements
            <input class="field-input" name="age_requirements" value="${esc(school.age_requirements||'')}">
          </label>
          <label class="field-label">Entry Grade Levels
            <input class="field-input" name="entry_grades" value="${esc(school.entry_grades||'')}">
          </label>
        </div>
        <label class="field-label u-field-label-block-md">Hours &amp; Days Open</label>
        <div class="form-grid u-grid-auto-220 u-mb-md">
          <label class="field-label">Opens
            <input class="field-input" name="hours_open" type="time">
          </label>
          <label class="field-label">Closes
            <input class="field-input" name="hours_close" type="time">
          </label>
        </div>
        <div class="days-checkbox-row u-mb-md">
          <label><input type="checkbox" name="hours_day_mon"> Mon</label>
          <label><input type="checkbox" name="hours_day_tue"> Tue</label>
          <label><input type="checkbox" name="hours_day_wed"> Wed</label>
          <label><input type="checkbox" name="hours_day_thu"> Thu</label>
          <label><input type="checkbox" name="hours_day_fri"> Fri</label>
          <label><input type="checkbox" name="hours_day_sat"> Sat</label>
          <label><input type="checkbox" name="hours_day_sun"> Sun</label>
        </div>
        <label class="field-label u-field-label-block-md">School Logo / Photo
          <div class="school-logo-uploader">
            <img id="edit-logo-img" class="school-logo-preview hidden" src="" alt="School logo">
            <div id="edit-logo-fallback" class="school-logo-fallback">No logo uploaded</div>
            <input type="file" id="edit-logo-input" accept="image/*" class="hidden">
            <button type="button" id="edit-logo-upload-btn" class="card-button school-outline-btn u-inline-btn-sm">Upload Logo</button>
          </div>
          <p id="edit-logo-msg" class="status-message u-space-bottom-xs"></p>
        </label>
        <label class="field-label u-field-label-block-md">Description
          <textarea class="field-input u-textarea-vertical" name="description" rows="3">${esc(school.description||'')}</textarea>
        </label>
        <label class="field-label u-field-label-block-md">Mission Statement
          <textarea class="field-input u-textarea-vertical" name="mission" rows="2">${esc(school.mission||'')}</textarea>
        </label>
        <label class="field-label u-field-label-block-md">Vision Statement
          <textarea class="field-input u-textarea-vertical" name="vision" rows="2">${esc(school.vision||'')}</textarea>
        </label>
        <label class="field-label u-field-label-block-md">Core Values
          <textarea class="field-input u-textarea-vertical" name="core_values" rows="2">${esc(school.core_values||'')}</textarea>
        </label>
        <label class="field-label u-field-label-block-md">Subjects / Courses Offered
          <textarea class="field-input u-textarea-vertical" name="subjects_offered" rows="2">${esc(school.subjects_offered||'')}</textarea>
        </label>
        <label class="field-label u-field-label-block-md">Fees Structure
          <textarea class="field-input u-textarea-vertical" name="fees_structure" rows="2">${esc(school.fees_structure||'')}</textarea>
        </label>
        <label class="field-label u-field-label-block-md">How to Apply
          <textarea class="field-input u-textarea-vertical" name="how_to_apply" rows="2">${esc(school.how_to_apply||'')}</textarea>
        </label>
        <label class="field-label u-field-label-block-md">Admission Requirements
          <textarea class="field-input u-textarea-vertical" name="requirements_text" rows="4" placeholder="Paste your admission requirements here — birth certificate, previous report card, etc.">${esc(school.requirements_text||'')}</textarea>
        </label>
        <p class="school-form-divider">Facilities &amp; Extracurricular</p>
        <div class="school-checkbox-grid">
          <label class="school-checkbox"><input type="checkbox" name="has_library" ${Number(school.has_library)?'checked':''}> Library</label>
          <label class="school-checkbox"><input type="checkbox" name="has_laboratory" ${Number(school.has_laboratory)?'checked':''}> Laboratory</label>
          <label class="school-checkbox"><input type="checkbox" name="has_sports_facilities" ${Number(school.has_sports_facilities)?'checked':''}> Sports facilities</label>
          <label class="school-checkbox"><input type="checkbox" name="has_water_sanitation" ${Number(school.has_water_sanitation)?'checked':''}> Water &amp; sanitation</label>
          <label class="school-checkbox"><input type="checkbox" name="has_electricity" ${Number(school.has_electricity)?'checked':''}> Electricity</label>
          <label class="school-checkbox"><input type="checkbox" name="has_sports_clubs" ${Number(school.has_sports_clubs)?'checked':''}> Sports clubs</label>
          <label class="school-checkbox"><input type="checkbox" name="has_arts_culture" ${Number(school.has_arts_culture)?'checked':''}> Arts &amp; culture</label>
          <label class="school-checkbox"><input type="checkbox" name="has_academic_clubs" ${Number(school.has_academic_clubs)?'checked':''}> Academic clubs</label>
          <label class="school-checkbox"><input type="checkbox" name="has_student_government" ${Number(school.has_student_government)?'checked':''}> Student government</label>
        </div>
        <label class="field-label u-field-label-block-md">Other Activities
          <div id="edit-activity-tags" class="school-tag-list"></div>
          <div class="school-tag-add-row">
            <input type="text" id="edit-activity-input" class="field-input" placeholder="e.g. Debate club, Chess club, Environmental club">
            <button type="button" id="edit-activity-add-btn" class="card-button school-outline-btn u-inline-btn-sm">+ Add</button>
          </div>
        </label>
        <button class="card-button u-card-button-compact-sm" type="submit">Save School Info</button>
        <span id="edit-school-msg" class="u-inline-note"></span>
      </form>

      <hr class="u-hr-soft">

      <p class="section-label u-card-head-sm">ADMISSION REQUIREMENTS DOCUMENT</p>
      <p class="u-text-muted-xs">Have a printed admission form or checklist? Upload it as a PDF — students will be able to download it, alongside the text pasted above.</p>
      <p id="edit-reqdoc-msg" class="status-message u-space-bottom-xs"></p>
      <a id="edit-reqdoc-link" class="text-link hidden" href="" target="_blank" rel="noopener" download>Download current document</a>
      <div class="u-card-inline-actions">
        <input type="file" id="edit-reqdoc-input" accept=".pdf,image/*" class="hidden">
        <button type="button" id="edit-reqdoc-upload-btn" class="card-button u-btn-outline-maroon">Upload Document</button>
      </div>`;

    shell.appendChild(panel);

    // School info form
    const editForm = panel.querySelector('#edit-school-form');
    const editMsg  = panel.querySelector('#edit-school-msg');
    fillHoursPickers(editForm, school.hours);

    const editLogoInput = panel.querySelector('#edit-logo-input');
    panel.querySelector('#edit-logo-upload-btn')?.addEventListener('click', () => editLogoInput?.click());
    wireLogoUpload({
      inputEl: editLogoInput,
      imgEl: panel.querySelector('#edit-logo-img'),
      fallbackEl: panel.querySelector('#edit-logo-fallback'),
      msgEl: panel.querySelector('#edit-logo-msg'),
      uploadUrl: `/api/schools/${id}/logo`,
      currentUrl: school.logo_url,
    });

    const editTagList  = panel.querySelector('#edit-activity-tags');
    const editTagInput = panel.querySelector('#edit-activity-input');
    let editActivityTags = (school.extracurricular_other || '')
      .split(',').map(s => s.trim()).filter(Boolean);
    function renderEditActivityTags() {
      if (!editTagList) return;
      editTagList.innerHTML = editActivityTags.map((t, i) => `
        <span class="school-tag">${esc(t)}<button type="button" class="school-tag-remove" data-idx="${i}" aria-label="Remove ${esc(t)}">&times;</button></span>
      `).join('');
      editTagList.querySelectorAll('.school-tag-remove').forEach(btn => {
        btn.addEventListener('click', () => {
          editActivityTags.splice(Number(btn.dataset.idx), 1);
          renderEditActivityTags();
        });
      });
    }
    renderEditActivityTags();
    function addEditActivityTag() {
      const val = editTagInput.value.trim();
      if (val && !editActivityTags.includes(val)) { editActivityTags.push(val); renderEditActivityTags(); }
      editTagInput.value = '';
    }
    panel.querySelector('#edit-activity-add-btn')?.addEventListener('click', addEditActivityTag);
    editTagInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); addEditActivityTag(); }
    });

    editForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = editForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(editMsg, 'Saving\u2026');
      const fd = Object.fromEntries(new FormData(editForm));
      // FormData silently omits unchecked checkboxes and empty number
      // inputs \u2014 leaving either out of the payload means "don't touch this
      // field" server-side, not "clear it", so both need an explicit value.
      ['capacity','enrollment','year_established','teaching_staff_count','classroom_count'].forEach(k => {
        fd[k] = fd[k] ? Number(fd[k]) : null;
      });
      ['has_library','has_laboratory','has_sports_facilities','has_water_sanitation','has_electricity',
       'has_sports_clubs','has_arts_culture','has_academic_clubs','has_student_government'].forEach(f => {
        fd[f] = editForm.querySelector(`[name="${f}"]`)?.checked ? 1 : 0;
      });
      fd.extracurricular_other = editActivityTags.join(', ');
      fd.hours = composeHours(editForm);
      try {
        await api(`/api/schools/${id}`, { method: 'PUT', body: JSON.stringify(fd) });
        setMsg(editMsg, 'Saved \u2713');
      } catch (err) {
        setMsg(editMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    // Requirements document \u2014 a PDF/scanned-image attachment, alongside
    // the pasted "Admission Requirements" text in the main info form.
    const editReqDocInput = panel.querySelector('#edit-reqdoc-input');
    const editReqDocBtn   = panel.querySelector('#edit-reqdoc-upload-btn');
    const editReqDocLink  = panel.querySelector('#edit-reqdoc-link');
    const editReqDocMsg   = panel.querySelector('#edit-reqdoc-msg');
    if (editReqDocLink && school.requirements_doc_url) {
      editReqDocLink.href = school.requirements_doc_url;
      editReqDocLink.classList.remove('hidden');
    }
    editReqDocBtn?.addEventListener('click', () => editReqDocInput?.click());
    editReqDocInput?.addEventListener('change', async () => {
      const file = editReqDocInput.files?.[0];
      if (!file) return;
      if (file.size > 20 * 1024 * 1024) { setMsg(editReqDocMsg, 'File must be under 20 MB.', true); return; }
      setMsg(editReqDocMsg, 'Uploading\u2026');
      try {
        const data = await EP.uploadFile(`/api/schools/${id}/requirements-doc`, 'doc', file);
        setMsg(editReqDocMsg, 'Document saved.');
        if (editReqDocLink) {
          editReqDocLink.href = data.requirements_doc_url + '?t=' + Date.now();
          editReqDocLink.classList.remove('hidden');
        }
      } catch (err) {
        setMsg(editReqDocMsg, 'Upload failed, document was not saved: ' + err.message, true);
      }
    });
  }

  // Materials
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
    wireFilePreview(document.getElementById('material-file-input'), document.getElementById('material-file-preview'));
    if (uploadForm) {
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
            await EP.uploadFile(`/api/materials/${newId}/upload`, 'file', file);
          }
          setMsg(uploadMsg, 'Submitted for admin review. It will appear once approved.');
          uploadForm.reset();
        } catch (err) {
          setMsg(uploadMsg, err.message, true);
        } finally { btn.disabled = false; }
      });
    }

    const MAT_VIEW_KEY = 'eduportal_materials_view';
    let viewMode = localStorage.getItem(MAT_VIEW_KEY) || 'list';
    function setMaterialView(mode) {
      viewMode = mode;
      localStorage.setItem(MAT_VIEW_KEY, mode);
      document.getElementById('mat-btn-grid') && document.getElementById('mat-btn-grid').classList.toggle('active', mode === 'grid');
      document.getElementById('mat-btn-list') && document.getElementById('mat-btn-list').classList.toggle('active', mode === 'list');
      results.className = mode === 'list' ? 'material-list' : 'material-grid';
    }
    document.getElementById('mat-btn-list')?.addEventListener('click', () => setMaterialView('list'));
    document.getElementById('mat-btn-grid')?.addEventListener('click', () => setMaterialView('grid'));
    results.className = viewMode === 'list' ? 'material-list' : 'material-grid';
    document.getElementById('mat-btn-grid')?.classList.toggle('active', viewMode === 'grid');
    document.getElementById('mat-btn-list')?.classList.toggle('active', viewMode === 'list');

    async function load(page) {
      page = page || 1;
      results.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      const params = EP.filterParamsFromForm(form);
      params.set('page', page);
      try {
        const data = await api(`/api/materials?${params}`);
        results.className = viewMode === 'list' ? 'material-list' : 'material-grid';
        const inlineDetail = document.getElementById('material-detail');
        results.innerHTML = data.items.length
          ? data.items.map(m => {
              const isVideo = materialIsVideo(m);
              // Real preview (first PDF page / a video frame) when the server
              // managed to generate one at upload time; otherwise fall back
              // to a generic icon so older materials (or ones ffmpeg/PyMuPDF
              // failed on) still show something meaningful.
              const hasThumb = !!m.thumbnail_path;
              const thumbStyle = hasThumb ? ` style="background-image:url('${esc(m.thumbnail_path)}')"` : '';
              const cardThumb = isVideo
                ? `<div class="material-card-thumb material-card-thumb-video${hasThumb ? ' has-image' : ''}"${thumbStyle}>
                    <svg class="material-card-thumb-play" viewBox="0 0 48 48" width="34" height="34" fill="none">
                      <circle cx="24" cy="24" r="22" fill="rgba(255,255,255,0.2)"/>
                      <path d="M19 15.5v17l15-8.5-15-8.5z" fill="#fff"/>
                    </svg>
                  </div>`
                : `<div class="material-card-thumb material-card-thumb-pdf${hasThumb ? ' has-image' : ''}"${thumbStyle}>
                    ${!hasThumb ? `<svg viewBox="0 0 40 48" width="28" height="34" fill="none">
                      <path d="M6 2h20l8 8v36H6V2z" fill="#fff" stroke="rgba(35,61,77,0.35)" stroke-width="1.5"/>
                      <path d="M26 2v8h8" fill="none" stroke="rgba(35,61,77,0.35)" stroke-width="1.5"/>
                      <rect x="11" y="20" width="18" height="2.4" rx="1.2" fill="rgba(35,61,77,0.22)"/>
                      <rect x="11" y="26" width="18" height="2.4" rx="1.2" fill="rgba(35,61,77,0.22)"/>
                      <rect x="11" y="32" width="11" height="2.4" rx="1.2" fill="rgba(35,61,77,0.22)"/>
                    </svg>` : ''}
                    <span class="material-card-thumb-tag">PDF</span>
                  </div>`;
              return `
              <article class="result-card material-card" data-id="${m.id}" tabindex="0" role="button">
                ${cardThumb}
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
                  ${canBookmark()
                    ? `<button class="card-link bookmark-btn" data-type="material" data-id="${m.id}" type="button">Save</button>`
                    : getToken() ? '' : '<span class="card-link material-card-save-hint">Login to save</span>'}
                </div>
              </article>`;
            }).join('')
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
                  ${m.file_path && materialIsVideo(m) ? `
                    <div class="u-mt-sm">
                      <video controls preload="metadata" class="material-video-player">
                        <source src="/api/materials/${m.id}/stream?token=${encodeURIComponent(getToken() || '')}">
                        Your browser does not support video playback.
                      </video>
                    </div>` : ''}
                  <div class="u-card-inline-actions-wrap material-detail-actions">
                    ${getToken() ? (materialIsVideo(m)
                      ? `<a class="card-button u-card-button-link" href="/api/materials/${m.id}/stream?token=${encodeURIComponent(getToken())}" target="_blank" rel="noopener">
                          <svg viewBox="0 0 16 16" fill="none" width="13" height="13" class="u-mini-svg-gap"><path d="M6 4l6 4-6 4V4z" fill="currentColor"/></svg>
                          Watch Tutorial
                        </a>`
                      : `<a class="card-button u-card-button-outline-link u-card-button-link" href="/api/materials/${m.id}/stream?token=${encodeURIComponent(getToken())}" target="_blank" rel="noopener">
                          <svg viewBox="0 0 16 16" fill="none" width="13" height="13" class="u-mini-svg-gap"><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.4"/></svg>
                          View
                        </a>
                        ${canDownloadMaterial() ? `<a class="card-button u-card-button-link" href="/api/materials/${m.id}/download" download>
                          <svg viewBox="0 0 16 16" fill="none" width="13" height="13" class="u-mini-svg-gap"><path d="M8 2v8M5 7l3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
                          Download File
                        </a>` : ''}`) : `<a class="card-button u-card-button-link" href="/login">Login to watch or download</a>`}
                    ${canBookmark() ? `<button class="card-button detail-bookmark-btn u-card-button-outline-link u-card-button-link" data-id="${m.id}">Save material</button>` : ''}
                  </div>
                </div>`;
              inlineDetail.querySelector('.detail-bookmark-btn')?.addEventListener('click', (ev) => saveBookmark(ev.currentTarget, 'material', m.id));
              // The token embedded in the <source> URL goes stale if the
              // 2-hour access token expires while this tab stays open —
              // unlike api()'s JSON calls, a <video> element has no way to
              // retry on its own, so it would otherwise just show a broken
              // player until the page is reloaded. Refresh and reload once.
              const videoEl = inlineDetail.querySelector('.material-video-player');
              if (videoEl) {
                videoEl.addEventListener('error', async () => {
                  const ok = await EP.refreshSession();
                  const source = videoEl.querySelector('source');
                  if (ok && source) {
                    source.src = `/api/materials/${m.id}/stream?token=${encodeURIComponent(getToken() || '')}`;
                    videoEl.load();
                  }
                }, { once: true });
              }
            }
          });
          card.addEventListener('keydown', e => { if (e.key === 'Enter') card.click(); });
        });

        results.querySelectorAll('.bookmark-btn').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            saveBookmark(btn, btn.dataset.type, btn.dataset.id);
          });
        });

        // Show the most recent result in the detail panel by default,
        // instead of leaving it on the empty "Select a resource" placeholder.
        const firstCard = results.querySelector('.material-card');
        if (firstCard && inlineDetail) firstCard.click();
      } catch (err) {
        results.innerHTML = `<p class="u-text-danger">${esc(err.message)}</p>`;
      }
    }

    form && form.addEventListener('submit', (e) => { e.preventDefault(); load(1); });
    autoApplyFilterSelects(form, () => load(1));
    load(1);
  }


  // Opportunities (Scholarships)
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
        ${s.poster_image_url ? `<img class="opp-poster-img" src="${esc(s.poster_image_url)}" alt="">` : ''}
        <div class="detail-header">
          <div>
            <span class="tag">${esc(s.provider || 'Verified NGO')}</span>
            <h2 class="detail-title">${esc(s.title)}</h2>
            <p class="deadline-badge">Deadline: <strong>${esc(s.deadline)}</strong></p>
          </div>
          <div class="u-card-inline-actions-end">
            ${getToken() ? `<button class="card-button apply-btn u-card-button-compact-sm" data-id="${s.id}">Apply Now</button>
            ${canBookmark() ? `<button class="card-button sch-bookmark-btn u-card-button-outline-link u-card-button-compact-sm" data-id="${s.id}">&#9825; Save</button>` : ''}` : '<a class="card-button u-card-button-compact-sm" href="/login">Login to Apply</a>'}
          </div>
        </div>
        <div class="detail-body">
          ${s.video_path ? `<div class="detail-section">
            <video controls preload="metadata" class="opp-video-player">
              <source src="${esc(s.video_path)}">
              Your browser does not support video playback.
            </video>
          </div>` : ''}
          <div class="detail-section">
            <p class="detail-key">About this opportunity</p>
            ${EP.paragraphs(s.description)}
          </div>
          <div class="detail-section">
            <p class="detail-key">Who Can Apply</p>
            ${EP.paragraphs(s.eligibility)}
          </div>
          <div class="detail-grid">
            <div class="detail-item"><span class="detail-key">Provider</span><span>${esc(s.provider || 'N/A')}</span></div>
            ${s.slots_available ? `<div class="detail-item"><span class="detail-key">Slots Available</span><span>${esc(s.slots_available)}</span></div>` : ''}
            ${s.contact_person ? `<div class="detail-item"><span class="detail-key">Contact Person</span><span>${esc(s.contact_person)}</span></div>` : ''}
            ${s.org_contact ? `<div class="detail-item"><span class="detail-key">Contact</span><span>${esc(s.org_contact)}</span></div>` : ''}
            ${s.org_email ? `<div class="detail-item"><span class="detail-key">Email</span><span>${esc(s.org_email)}</span></div>` : ''}
          </div>
          ${s.whats_covered ? `<div class="detail-section"><p class="detail-key">What's Covered</p>${EP.paragraphs(s.whats_covered)}</div>` : ''}
          ${s.required_docs ? `<div class="detail-section"><p class="detail-key">Required Documents</p>${EP.paragraphs(s.required_docs)}</div>` : ''}
          <div class="detail-section"><p class="detail-key">How to Apply</p>${EP.paragraphs(s.how_to_apply)}</div>
          ${s.external_link ? `<div class="detail-section"><a href="${esc(s.external_link)}" target="_blank" rel="noopener" class="card-button u-card-button-link-inline">Visit Application Page</a></div>` : ''}
          ${s.org_description ? `<div class="detail-section"><p class="detail-key">About ${esc(s.provider || 'the Organisation')}</p>${EP.paragraphs(s.org_description)}</div>` : ''}
        </div>`;

      // Apply button handler
      detailContent.querySelector('.apply-btn')?.addEventListener('click', (btn_e) => applyToScholarship(btn_e.currentTarget, s.id));

      // Bookmark button handler
      detailContent.querySelector('.sch-bookmark-btn')?.addEventListener('click', (btn_e) => {
        saveBookmark(btn_e.currentTarget, 'scholarship', s.id, {
          onSuccess: (btn) => { btn.textContent = 'Saved'; btn.style.color = 'var(--maroon)'; },
          alreadyText: 'Already saved',
        });
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
    wireFilePreview(document.getElementById('opp-poster-input'), document.getElementById('opp-poster-preview'));
    wireFilePreview(document.getElementById('opp-video-input'), document.getElementById('opp-video-preview'));

    postSchForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = postSchForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(postSchMsg, 'Submitting\u2026');
      const rawFd = new FormData(postSchForm);
      const posterFile = rawFd.get('poster');
      const videoFile = rawFd.get('video');
      rawFd.delete('poster');
      rawFd.delete('video');
      const fd = Object.fromEntries(rawFd);
      try {
        const { id: newId } = await api('/api/scholarships', { method: 'POST', body: JSON.stringify(fd) });
        await uploadScholarshipMedia(newId, 'poster', posterFile);
        await uploadScholarshipMedia(newId, 'video', videoFile);
        setMsg(postSchMsg, 'Submitted for admin review. It will appear once approved.');
        postSchForm.reset();
      } catch (err) {
        setMsg(postSchMsg, err.message, true);
      } finally { btn.disabled = false; }
    });

    // Card view is a compact grid you click into for details; list view
    // inlines the full write-up (description, what's covered, required
    // docs, how to apply) so you can read every listing without navigating
    // away one at a time. The choice is remembered across visits (and
    // survives logout/login — a separate key from the session, never
    // touched by clearSession()) instead of always resetting to card view.
    const OPP_VIEW_KEY = 'eduportal_opportunities_view';
    let viewMode = localStorage.getItem(OPP_VIEW_KEY) || 'card';
    let currentItems = [];

    function renderCard(s) {
      return `
        <article class="result-card opportunity-card u-cursor-pointer" data-id="${s.id}" tabindex="0" role="button">
          ${s.poster_image_url ? `<img class="opp-card-thumb" src="${esc(s.poster_image_url)}" alt="">` : ''}
          <div class="result-card-top"><span class="tag">Scholarship</span></div>
          <h3 class="result-card-title">${esc(s.title)}</h3>
          <p class="org">${esc(s.provider || 'Verified NGO')}</p>
          <p class="result-card-preview">${esc(s.eligibility)}</p>
          <div class="result-card-footer">
            <span class="deadline-badge">Deadline: ${esc(s.deadline)}</span>
            <span class="card-link">Details</span>
          </div>
        </article>`;
    }

    function renderListItem(s) {
      return `
        <article class="result-card opportunity-list-item" data-id="${s.id}">
          ${s.poster_image_url ? `<img class="opp-list-thumb" src="${esc(s.poster_image_url)}" alt="">` : ''}
          <div class="opp-list-content">
            <div class="opp-list-header">
              <div>
                <span class="tag">Scholarship</span>
                <h3 class="result-card-title">${esc(s.title)}</h3>
                <p class="org">${esc(s.provider || 'Verified NGO')}</p>
              </div>
              <span class="deadline-badge">Deadline: ${esc(s.deadline)}</span>
            </div>
            <div class="detail-section"><p class="detail-key">About this opportunity</p>${EP.paragraphs(s.description)}</div>
            <div class="detail-section"><p class="detail-key">Who Can Apply</p>${EP.paragraphs(s.eligibility)}</div>
            ${s.slots_available ? `<div class="detail-grid">
              <div class="detail-item"><span class="detail-key">Slots Available</span><span>${esc(s.slots_available)}</span></div>
            </div>` : ''}
            ${s.whats_covered ? `<div class="detail-section"><p class="detail-key">What's Covered</p>${EP.paragraphs(s.whats_covered)}</div>` : ''}
            ${s.required_docs ? `<div class="detail-section"><p class="detail-key">Required Documents</p>${EP.paragraphs(s.required_docs)}</div>` : ''}
            <div class="detail-section"><p class="detail-key">How to Apply</p>${EP.paragraphs(s.how_to_apply)}</div>
            <div class="opp-list-actions">
              ${getToken()
                ? `<button class="card-button apply-btn-list u-card-button-compact-sm" data-id="${s.id}">Apply Now</button>
                   ${canBookmark() ? `<button class="card-button sch-bookmark-btn-list u-card-button-outline-link u-card-button-compact-sm" data-id="${s.id}">&#9825; Save</button>` : ''}`
                : `<a class="card-button u-card-button-compact-sm" href="/login">Login to Apply</a>`}
              ${s.video_path ? `<button class="card-button u-card-button-outline-link u-card-button-compact-sm opp-list-more" data-id="${s.id}">Watch video &amp; more</button>` : ''}
            </div>
          </div>
        </article>`;
    }

    function render() {
      results.className = viewMode === 'list' ? 'opportunities-list-view' : 'cards-grid results-grid';
      if (!currentItems.length) {
        results.innerHTML = '<p class="empty-text">No scholarships matched those filters.</p>';
        return;
      }
      results.innerHTML = currentItems.map(viewMode === 'list' ? renderListItem : renderCard).join('');

      if (viewMode === 'card') {
        results.querySelectorAll('.opportunity-card').forEach(card => {
          const handler = () => {
            const s = currentItems.find(i => String(i.id) === card.dataset.id);
            if (s) showDetail(s);
          };
          card.addEventListener('click', handler);
          card.addEventListener('keydown', e => { if (e.key === 'Enter') handler(); });
        });
        return;
      }

      results.querySelectorAll('.apply-btn-list').forEach(btn => {
        btn.addEventListener('click', () => applyToScholarship(btn, Number(btn.dataset.id)));
      });
      results.querySelectorAll('.sch-bookmark-btn-list').forEach(btn => {
        btn.addEventListener('click', () => {
          saveBookmark(btn, 'scholarship', Number(btn.dataset.id), {
            onSuccess: (b) => { b.textContent = 'Saved'; b.style.color = 'var(--maroon)'; },
            alreadyText: 'Already saved',
          });
        });
      });
      results.querySelectorAll('.opp-list-more').forEach(btn => {
        btn.addEventListener('click', () => {
          const s = currentItems.find(i => String(i.id) === btn.dataset.id);
          if (s) showDetail(s);
        });
      });
    }

    function syncViewToggleButtons() {
      document.getElementById('opp-btn-card')?.classList.toggle('active', viewMode === 'card');
      document.getElementById('opp-btn-list')?.classList.toggle('active', viewMode === 'list');
    }
    function setOpportunityView(mode) {
      viewMode = mode;
      localStorage.setItem(OPP_VIEW_KEY, mode);
      syncViewToggleButtons();
      render();
    }
    document.getElementById('opp-btn-card')?.addEventListener('click', () => setOpportunityView('card'));
    document.getElementById('opp-btn-list')?.addEventListener('click', () => setOpportunityView('list'));
    syncViewToggleButtons();

    async function load() {
      results.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      const params = EP.filterParamsFromForm(form);
      try {
        const { items: allItems } = await api(`/api/scholarships?${params}`);
        // Hide scholarships whose deadline has already passed.
        currentItems = allItems.filter(s => isOpenDeadline(s.deadline));
        render();
      } catch (err) {
        results.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }

    form?.addEventListener('submit', (e) => { e.preventDefault(); load(); });
    autoApplyFilterSelects(form, load);
    load();
  }

  // Announcements
  // My Applications
  async function initMyApplications() {
    if (!getToken()) { window.location.href = '/login'; return; }

    const listEl   = document.getElementById('applications-list');
    const summaryEl = document.getElementById('apps-summary');
    if (!listEl) return;

    // View toggle
    const APPS_VIEW_KEY = 'eduportal_applications_view';
    let viewMode = localStorage.getItem(APPS_VIEW_KEY) || 'grid';
    function setAppView(mode) {
      viewMode = mode;
      localStorage.setItem(APPS_VIEW_KEY, mode);
      document.getElementById('btn-grid')?.classList.toggle('active', mode === 'grid');
      document.getElementById('btn-list')?.classList.toggle('active', mode === 'list');
      listEl.className = mode === 'list' ? 'apps-list-view' : 'apps-grid-view';
    }
    document.getElementById('btn-grid')?.addEventListener('click', () => setAppView('grid'));
    document.getElementById('btn-list')?.addEventListener('click', () => setAppView('list'));
    document.getElementById('btn-grid')?.classList.toggle('active', viewMode === 'grid');
    document.getElementById('btn-list')?.classList.toggle('active', viewMode === 'list');
    listEl.className = viewMode === 'list' ? 'apps-list-view' : 'apps-grid-view';

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

  // Profile
  async function initProfile() {
    if (!getToken()) { window.location.href = '/login'; return; }

    const form    = document.getElementById('profile-form');
    const msg     = document.getElementById('profile-message');
    const nameEl  = document.getElementById('profile-name-display');
    const roleEl  = document.getElementById('profile-role-display');
    const avatarInput    = document.getElementById('avatar-input');
    const avatarImg      = document.getElementById('profile-avatar-img');
    const avatarFallback = document.getElementById('avatar-fallback');
    const uploadBtn      = document.getElementById('avatar-upload-btn');
    if (!form) return;

    // Matches the initials the sidebar shows for the same "no avatar yet"
    // state (sidebar-main.js) — without this, a user with no photo saw two
    // different placeholders at once: initials up top, a generic silhouette
    // icon here.
    function showInitialsFallback(name) {
      if (!avatarFallback) return;
      const initials = (name || '').split(' ').map(w => w[0] || '').join('').slice(0, 2).toUpperCase();
      avatarFallback.innerHTML = initials
        ? `<span class="avatar-fallback-initials">${esc(initials)}</span>`
        : avatarFallback.innerHTML;
    }

    // A broken/expired avatar URL falls back to the initials placeholder
    // instead of a broken-image glyph, however avatarImg.src ends up set.
    avatarImg?.addEventListener('error', () => {
      avatarImg.style.display = 'none';
      if (avatarFallback) avatarFallback.style.display = 'flex';
    });

    // Load current profile data
    try {
      const { user } = await api('/api/me');
      if (nameEl) nameEl.textContent = user.name;
      if (roleEl) roleEl.textContent = user.role.replace('_', ' ');
      showInitialsFallback(user.name);

      // Show saved avatar if present
      if (user.avatar && avatarImg) {
        avatarImg.src = user.avatar;
        avatarImg.style.display = '';
        if (avatarFallback) avatarFallback.style.display = 'none';
        // Also update sidebar/top-bar immediately on page load
        _refreshSidebarAvatar(user.avatar);
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
      // Remember what was showing before the optimistic preview, so a failed
      // upload can be reverted instead of leaving a preview on screen that
      // was never actually saved — that preview would otherwise look fine
      // on this page, then "disappear" the moment the user left it, since
      // nothing was ever persisted to the server.
      const previousSrc = avatarImg ? avatarImg.src : '';
      const previousImgDisplay = avatarImg ? avatarImg.style.display : '';
      const previousFallbackDisplay = avatarFallback ? avatarFallback.style.display : '';
      // Optimistic preview
      const reader = new FileReader();
      reader.onload = (ev) => {
        if (avatarImg) { avatarImg.src = ev.target.result; avatarImg.style.display = ''; }
        if (avatarFallback) avatarFallback.style.display = 'none';
      };
      reader.readAsDataURL(file);
      // Upload to server
      try {
        const data = await EP.uploadFile('/api/me/avatar', 'avatar', file);
        setMsg(msg, 'Profile photo saved.');
        // Bust cache so the new image shows immediately
        const freshSrc = data.avatar + '?t=' + Date.now();
        if (avatarImg) avatarImg.src = freshSrc;
        // Persist avatar URL in stored session so sidebar/banner reflect it
        const stored = getUser();
        if (stored) { stored.avatar = data.avatar; localStorage.setItem(USER_KEY, JSON.stringify(stored)); }
        // Live-update sidebar avatar and account trigger without reload
        _refreshSidebarAvatar(freshSrc);
      } catch (err) {
        // Revert the optimistic preview — it was never actually saved.
        if (avatarImg) { avatarImg.src = previousSrc; avatarImg.style.display = previousImgDisplay; }
        if (avatarFallback) avatarFallback.style.display = previousFallbackDisplay;
        setMsg(msg, 'Upload failed, photo was not saved: ' + err.message, true);
      }
    });
  }

  // Settings
  async function initSettings() {
    if (!getToken()) { window.location.href = '/login'; return; }

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
        const data = await api('/api/change-password', { method: 'POST', body: JSON.stringify(fd) });
        if (data.token && data.refresh_token) saveSession(data.token, getUser(), data.refresh_token);
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

    // Push notifications (this device)
    const pushBtn = document.getElementById('push-toggle-btn');
    const pushMsg = document.getElementById('push-message');

    async function refreshPushButtonState() {
      if (!pushBtn) return;
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        pushBtn.disabled = true;
        setMsg(pushMsg, 'Push notifications are not supported in this browser.', true);
        return;
      }
      const reg = await navigator.serviceWorker.ready.catch(() => null);
      const sub = reg ? await reg.pushManager.getSubscription() : null;
      pushBtn.textContent = sub ? 'Disable push notifications' : 'Enable push notifications';
    }

    pushBtn?.addEventListener('click', async () => {
      pushBtn.disabled = true;
      try {
        const reg = await navigator.serviceWorker.register('/sw.js');
        const existing = await reg.pushManager.getSubscription();
        if (existing) {
          await api('/api/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint: existing.endpoint }) });
          await existing.unsubscribe();
          setMsg(pushMsg, 'Push notifications disabled on this device.');
        } else {
          const { key, enabled } = await api('/api/push/vapid-public-key');
          if (!enabled) { setMsg(pushMsg, 'Push notifications are not configured on this server yet.', true); return; }
          const sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(key),
          });
          await api('/api/push/subscribe', { method: 'POST', body: JSON.stringify(sub.toJSON()) });
          setMsg(pushMsg, 'Push notifications enabled on this device.');
        }
      } catch (err) {
        setMsg(pushMsg, err.message || 'Could not update push notification settings.', true);
      } finally {
        pushBtn.disabled = false;
        refreshPushButtonState();
      }
    });

    if (pushBtn) refreshPushButtonState();
  }

  // Admin
  // Admin panel — shared helpers and per-tab loaders used by initAdmin
  // below. Pulled out of that function (previously ~700 lines in one
  // closure) into module scope so each tab's concern reads as its own
  // unit; initAdmin itself is now just the page bootstrap: guard clause,
  // wiring, and the initial loadAll() kick-off.

  // Fields worth showing an admin reviewing a pending submission, per type
  // — enough to judge the content without leaving the queue.
  const QUEUE_DETAIL_FIELDS = {
    material: [['subject','Subject'],['grade','Grade'],['year','Year'],['type','Type'],['preview_text','Preview']],
    announcement: [['org_name','Organisation'],['org_type','Org type'],['audience','Audience'],['priority','Priority'],['state','State'],['expires_at','Expires'],['body','Body']],
    scholarship: [['provider','Provider'],['deadline','Deadline'],['eligibility','Eligibility'],['slots_available','Slots'],['whats_covered','What’s covered'],['contact_person','Contact'],['how_to_apply','How to apply'],['required_docs','Required documents'],['external_link','External link'],['description','Description']],
    school: [['state','State'],['county','County'],['level','Level'],['type','Type'],['ownership','Ownership'],['boarding','Boarding'],['contact_name','Contact'],['phone','Phone'],['email','Email'],['address','Address'],['registration_number','Registration No.'],['headteacher_name','Headteacher'],['mission','Mission'],['description','Description']],
    ngo: [['org_type','Org type'],['state','State'],['county','County'],['contact','Contact'],['email','Email'],['phone','Phone'],['website','Website'],['registration_number','Registration No.'],['areas_of_focus','Areas of focus'],['mission','Mission'],['description','Description']],
    organization: [['org_type','Org type'],['state','State'],['email','Email'],['phone','Phone'],['website','Website'],['description','Description']],
  };

  function ensureQueueModal() {
    return EP.createModal({
      id: 'queue-modal-overlay',
      bodyHtml: `
        <div class="ann-modal" role="dialog" aria-modal="true">
          <button type="button" class="ann-modal-close" aria-label="Close">
            <svg viewBox="0 0 16 16" fill="none" width="16" height="16"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          </button>
          <p class="eyebrow u-mb-xs u-text-maroon" id="queue-modal-type"></p>
          <h2 class="ann-modal-title" id="queue-modal-title"></h2>
          <div class="ann-modal-body" id="queue-modal-body"></div>
        </div>`,
    });
  }

  function openQueueModal(item, type) {
    const modal = ensureQueueModal();
    modal.querySelector('#queue-modal-type').textContent = type;
    modal.querySelector('#queue-modal-title').textContent = item.title;
    const fields = QUEUE_DETAIL_FIELDS[type] || [];
    modal.querySelector('#queue-modal-body').innerHTML = fields
      .filter(([key]) => item[key] != null && String(item[key]).trim() !== '')
      .map(([key, label]) => `<p><strong>${esc(label)}:</strong> ${esc(String(item[key]))}</p>`)
      .join('') || '<p class="u-text-muted-xs">No further details available.</p>';
    modal.classList.remove('hidden');
  }

  // Re-queries the tab/sub-tab button+panel sets on every call rather than
  // closing over them — cheap (click-driven, not hot-path) and keeps these
  // usable from module scope without initAdmin having to pass them in.
  function activateTab(id) {
    document.querySelectorAll('.admin-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === id));
    document.querySelectorAll('.admin-tab-panel').forEach(p => p.classList.toggle('active', p.id === id));
  }
  function activateSub(id) {
    document.querySelectorAll('.admin-sub-btn').forEach(b => b.classList.toggle('active', b.dataset.sub === id));
    document.querySelectorAll('.admin-sub-panel').forEach(p => p.classList.toggle('active', p.id === id));
  }

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
                <button class="card-button u-card-button-outline-link" data-action="view" data-type="${esc(type)}" data-id="${item.id}">View</button>
                <button class="card-button" data-action="approve" data-type="${esc(type)}" data-id="${item.id}">Approve</button>
                <button class="card-button btn-reject" data-action="reject" data-type="${esc(type)}" data-id="${item.id}">Reject</button>
              </div>
            </div>`).join('')
        : '<p class="empty-text">No items pending.</p>';

      el.querySelectorAll('[data-action="view"]').forEach(btn => {
        btn.addEventListener('click', () => {
          const item = items.find(i => String(i.id) === btn.dataset.id);
          if (item) openQueueModal(item, btn.dataset.type);
        });
      });

      el.querySelectorAll('[data-action="approve"], [data-action="reject"]').forEach(btn => {
        btn.addEventListener('click', async () => {
          let note = '';
          if (btn.dataset.action === 'reject') {
            const entered = prompt('Reason for rejection (shown to the submitter):');
            if (entered === null) return; // cancelled
            note = entered;
          }
          btn.disabled = true;
          try {
            await api('/api/admin/approve', { method: 'POST', body: JSON.stringify({
              target_type: btn.dataset.type, target_id: Number(btn.dataset.id), action: btn.dataset.action, note,
            })});
            loadAll();
          } catch (err) { btn.disabled = false; btn.textContent = err.message; }
        });
      });
    }

    async function loadPendingAssignments() {
      const el = document.getElementById('admin-pending-assignments');
      if (!el) return;
      try {
        const { school_admins, ngo_officers } = await api('/api/admin/pending-assignments');
        const rows = [
          ...school_admins.map(a => ({ ...a, kind: 'school_admin' })),
          ...ngo_officers.map(a => ({ ...a, kind: 'ngo_officer' })),
        ];
        el.innerHTML = rows.length
          ? rows.map(a => `
            <div class="admin-user-row">
              <div>
                <strong>${esc(a.name)}</strong>
                <span>${esc(a.kind === 'school_admin' ? 'School admin' : 'NGO officer')} &middot; ${esc(a.email || a.phone || 'no contact')}</span>
              </div>
              <span class="u-copy-danger u-strong-inline">Not yet assigned</span>
            </div>`).join('')
          : '<p class="empty-text">Every school admin and NGO officer account is assigned.</p>';
      } catch (_) { el.innerHTML = '<p class="empty-text">Could not load.</p>'; }
    }

    // Shared by every admin user-management button below (assign school/NGO,
    // change role, suspend/unsuspend, delete) — all follow the same
    // confirm → disable → request → reload shape; only the confirmation
    // text, endpoint, and payload differ per action.
    async function runUserAction(btn, confirmMsg, request) {
      if (confirmMsg != null && !confirm(confirmMsg)) return;
      btn.disabled = true;
      try {
        await request();
        loadUsers();
      } catch (err) { btn.disabled = false; btn.textContent = err.message; }
    }

    async function loadUsers() {
      const role = document.getElementById('admin-role-select')?.value || '';
      try {
        const { items } = await api(`/api/admin/users${role ? `?role=${role}` : ''}`);
        const schoolList = await api('/api/schools?per_page=100').catch(() => ({ items: [] }));
        const allSchools = schoolList.items || [];
        const ngoList = await api('/api/admin/ngos').catch(() => ({ items: [] }));
        const allNgos = ngoList.items || [];
        const el = document.getElementById('admin-users-list');
        const total = document.getElementById('stat-users');
        if (total) total.textContent = items.length;
        const selfId = getUser()?.id;
        if (el) {
          el.innerHTML = items.length
            ? items.map(u => {
                const isSelf = u.id === selfId;
                const schoolOptions = allSchools.map(s =>
                  `<option value="${s.id}" ${u.school_id === s.id ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
                const ngoOptions = allNgos.map(n =>
                  `<option value="${n.id}" ${u.ngo_id === n.id ? 'selected' : ''}>${esc(n.org_name)}</option>`).join('');
                const assignControl = u.role === 'school_admin' ? `
                  <select class="school-assign-select u-compact-select u-admin-select" data-id="${u.id}">
                    <option value="">No school assigned</option>
                    ${schoolOptions}
                  </select>
                  <button class="btn-assign-school u-admin-action-btn" data-id="${u.id}">Assign</button>`
                  : u.role === 'ngo_officer' ? `
                  <select class="ngo-assign-select u-compact-select u-admin-select" data-id="${u.id}">
                    <option value="">No organisation assigned</option>
                    ${ngoOptions}
                  </select>
                  <button class="btn-assign-ngo u-admin-action-btn" data-id="${u.id}">Assign</button>` : '';
                return `
                <div class="admin-user-row" data-user-row="${u.id}">
                  <div class="admin-user-view">
                    <strong>${esc(u.name)}${isSelf ? ' (you)' : ''}</strong>
                    <span>${esc(u.role)} &middot; ${esc(u.state)} &middot; ${esc(u.email || u.phone || 'no contact')}</span>
                    ${u.role === 'school_admin' && u.school_id ? `<span class="u-assigned-school-note">🏫 Assigned to school #${u.school_id}</span>` : ''}
                    ${u.role === 'ngo_officer' && u.ngo_id ? `<span class="u-assigned-school-note">🏫 Assigned to organisation #${u.ngo_id}</span>` : ''}
                  </div>
                  <div class="admin-user-edit hidden">
                    <input class="field-input u-compact-select" data-edit="name" value="${esc(u.name)}" placeholder="Name">
                    <input class="field-input u-compact-select" data-edit="email" value="${esc(u.email || '')}" placeholder="Email">
                    <input class="field-input u-compact-select" data-edit="phone" value="${esc(u.phone || '')}" placeholder="Phone">
                    <input class="field-input u-compact-select" data-edit="state" value="${esc(u.state || '')}" placeholder="State">
                    <input class="field-input u-compact-select" data-edit="county" value="${esc(u.county || '')}" placeholder="County">
                    <button class="btn-save-user u-admin-action-btn" data-id="${u.id}">Save</button>
                    <button class="btn-cancel-edit-user u-admin-action-btn">Cancel</button>
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
                    <button class="btn-change-role u-admin-action-btn" data-id="${u.id}" ${isSelf ? 'disabled title="You cannot change your own role"' : ''}>Set Role</button>
                    ${assignControl}
                    <button class="btn-edit-user u-admin-action-btn" data-id="${u.id}">Edit</button>
                    <button class="btn-reset-password u-admin-action-btn" data-id="${u.id}">Reset Password</button>
                    ${isSelf ? '' : `
                    <button class="btn-suspend" data-id="${u.id}" ${u.verified === -1 ? 'disabled' : ''}>${u.verified === -1 ? 'Suspended' : 'Suspend'}</button>
                    <button class="btn-unsuspend u-admin-action-btn" data-id="${u.id}" ${u.verified === -1 ? '' : 'disabled'}>Reactivate</button>
                    <button class="btn-delete-user u-admin-delete-btn" data-id="${u.id}">Delete</button>`}
                  </div>
                </div>`;
              }).join('')
            : '<p class="empty-text">No users found.</p>';

          el.querySelectorAll('.btn-assign-school').forEach(btn => {
            btn.addEventListener('click', () => {
              const row = btn.closest('.admin-user-row');
              const sel = row.querySelector('.school-assign-select');
              const schoolId = sel?.value ? Number(sel.value) : null;
              runUserAction(btn, schoolId ? `Assign this user to school #${schoolId}?` : 'Remove school assignment?',
                () => api(`/api/admin/users/${btn.dataset.id}/assign-school`, { method: 'POST', body: JSON.stringify({ school_id: schoolId }) }));
            });
          });

          el.querySelectorAll('.btn-assign-ngo').forEach(btn => {
            btn.addEventListener('click', () => {
              const row = btn.closest('.admin-user-row');
              const sel = row.querySelector('.ngo-assign-select');
              const ngoId = sel?.value ? Number(sel.value) : null;
              runUserAction(btn, ngoId ? `Assign this user to organisation #${ngoId}?` : 'Remove organisation assignment?',
                () => api(`/api/admin/users/${btn.dataset.id}/assign-ngo`, { method: 'POST', body: JSON.stringify({ ngo_id: ngoId }) }));
            });
          });

          el.querySelectorAll('.btn-reset-password').forEach(btn => {
            btn.addEventListener('click', async () => {
              if (!confirm('Send this user a password reset code?')) return;
              btn.disabled = true;
              try {
                const res = await api(`/api/admin/users/${btn.dataset.id}/reset-password`, { method: 'POST' });
                alert(res.dev_token ? `${res.message}\n\nDev reset code: ${res.dev_token}` : res.message);
              } catch (err) { alert(err.message); }
              finally { btn.disabled = false; }
            });
          });

          el.querySelectorAll('.btn-change-role').forEach(btn => {
            btn.addEventListener('click', () => {
              const row = btn.closest('.admin-user-row');
              const newRole = row.querySelector('.role-select')?.value;
              if (!newRole) return;
              runUserAction(btn, `Change this user's role to "${newRole}"?`,
                () => api(`/api/admin/users/${btn.dataset.id}/role`, { method: 'POST', body: JSON.stringify({ role: newRole }) }));
            });
          });

          el.querySelectorAll('.btn-suspend:not([disabled])').forEach(btn => {
            btn.addEventListener('click', () => {
              runUserAction(btn, 'Suspend this user?', () => api(`/api/admin/users/${btn.dataset.id}/suspend`, { method: 'POST' }));
            });
          });

          el.querySelectorAll('.btn-unsuspend:not([disabled])').forEach(btn => {
            btn.addEventListener('click', () => {
              runUserAction(btn, 'Reactivate this user’s account?', () => api(`/api/admin/users/${btn.dataset.id}/unsuspend`, { method: 'POST' }));
            });
          });

          el.querySelectorAll('.btn-edit-user').forEach(btn => {
            btn.addEventListener('click', () => {
              const row = btn.closest('[data-user-row]');
              row.querySelector('.admin-user-view').classList.add('hidden');
              row.querySelector('.admin-user-edit').classList.remove('hidden');
            });
          });

          el.querySelectorAll('.btn-cancel-edit-user').forEach(btn => {
            btn.addEventListener('click', () => {
              const row = btn.closest('[data-user-row]');
              row.querySelector('.admin-user-edit').classList.add('hidden');
              row.querySelector('.admin-user-view').classList.remove('hidden');
            });
          });

          el.querySelectorAll('.btn-save-user').forEach(btn => {
            btn.addEventListener('click', async () => {
              const row = btn.closest('[data-user-row]');
              const payload = {};
              row.querySelectorAll('[data-edit]').forEach(input => { payload[input.dataset.edit] = input.value.trim(); });
              btn.disabled = true;
              try {
                await api(`/api/admin/users/${btn.dataset.id}`, { method: 'PUT', body: JSON.stringify(payload) });
                loadUsers();
              } catch (err) { btn.disabled = false; alert(err.message); }
            });
          });

          el.querySelectorAll('.btn-delete-user').forEach(btn => {
            btn.addEventListener('click', () => {
              runUserAction(btn, 'Permanently delete this user? This cannot be undone.',
                () => api(`/api/admin/users/${btn.dataset.id}`, { method: 'DELETE' }));
            });
          });
        }
      } catch (_) {
        const el = document.getElementById('admin-users-list');
        if (el) el.innerHTML = '<p class="empty-text">Could not load users.</p>';
      }
    }

    async function loadAnalytics() {
      try {
        const data = await api('/api/admin/analytics');
        const statesEl = document.getElementById('analytics-states');
        const rolesEl = document.getElementById('analytics-roles');
        const bookmarksEl = document.getElementById('analytics-bookmarks');
        const schBookmarksEl = document.getElementById('analytics-scholarship-bookmarks');
        const contentEl = document.getElementById('analytics-content');
        const appsEl = document.getElementById('analytics-applications');
        const materialsEl = document.getElementById('analytics-materials');
        const annEl = document.getElementById('analytics-announcements');
        if (statesEl) statesEl.innerHTML = data.users_by_state.map(r =>
          `<div><strong>${esc(r.state)}</strong><span>${esc(r.count)} users</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
        if (rolesEl) rolesEl.innerHTML = (data.users_by_role || []).map(r =>
          `<div><strong>${esc(r.role)}</strong><span>${esc(r.count)} users</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
        if (bookmarksEl) bookmarksEl.innerHTML = data.bookmarked_schools.map(r =>
          `<div><strong>${esc(r.name)}</strong><span>${esc(r.count)} saves</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
        if (schBookmarksEl) schBookmarksEl.innerHTML = (data.bookmarked_scholarships || []).map(r =>
          `<div><strong>${esc(r.name)}</strong><span>${esc(r.count)} saves</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
        if (contentEl) contentEl.innerHTML = `
          <div><strong>${esc(data.approved.materials)}</strong><span>approved materials</span></div>
          <div><strong>${esc(data.approved.announcements)}</strong><span>approved announcements</span></div>
          <div><strong>${esc(data.approved.scholarships)}</strong><span>approved scholarships</span></div>
          <div><strong>${esc(data.approved.schools)}</strong><span>approved schools</span></div>
          <div><strong>${esc(data.total_users)}</strong><span>registered users</span></div>
          <div><strong>${esc(data.total_applications)}</strong><span>total applications</span></div>
          <div><strong>${esc(data.total_downloads)}</strong><span>total material downloads</span></div>`;
        if (appsEl) appsEl.innerHTML = data.scholarship_applications.map(r =>
          `<div><strong>${esc(r.title)}</strong><span>${esc(r.applications)} applications</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
        if (materialsEl) materialsEl.innerHTML = data.top_materials.map(r =>
          `<div><strong>${esc(r.title)}</strong><span>${esc(r.downloads)} downloads &middot; ${esc(r.saves)} saves</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
        if (annEl) annEl.innerHTML = (data.most_viewed_announcements || []).map(r =>
          `<div><strong>${esc(r.title)}</strong><span>${esc(r.view_count)} views</span></div>`).join('') || '<div><strong>No data</strong><span>—</span></div>';
      } catch (_) {
        ['analytics-states', 'analytics-roles', 'analytics-bookmarks', 'analytics-scholarship-bookmarks',
         'analytics-content', 'analytics-applications', 'analytics-materials', 'analytics-announcements']
          .forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<p class="empty-text">Could not load.</p>';
          });
      }
    }

    async function loadAll() {
      try {
        const queue = await api('/api/admin/queue');
        const counts = { 'stat-mat': queue.materials, 'stat-ann': queue.announcements, 'stat-sch': queue.scholarships };
        Object.entries(counts).forEach(([id, v]) => { const el = document.getElementById(id); if (el) el.textContent = v; });
        renderQueue('pending-materials',     queue.material_items,     'material');
        renderQueue('pending-announcements', queue.announcement_items, 'announcement');
        renderQueue('pending-scholarships',  queue.scholarship_items,  'scholarship');
        renderQueue('pending-schools',       queue.school_items,       'school');
        renderQueue('pending-ngos',          queue.ngo_items,          'ngo');
        renderQueue('pending-partners',      queue.organization_items, 'organization');
      } catch (_) {
        ['pending-materials', 'pending-announcements', 'pending-scholarships',
         'pending-schools', 'pending-ngos', 'pending-partners']
          .forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<p class="empty-text">Could not load the approval queue.</p>';
          });
      }

      await loadUsers();
      await loadAnalytics();
      await loadPendingAssignments();
      await loadAuditLog();
    }

    async function loadAuditLog() {
      const el = document.getElementById('admin-audit-log');
      if (!el) return;
      const fd = new FormData(document.getElementById('audit-filter-form') || undefined);
      const qs = new URLSearchParams();
      for (const [k, v] of fd.entries()) if (v) qs.set(k, v);
      try {
        const { items } = await api(`/api/admin/audit-log${qs.toString() ? '?' + qs.toString() : ''}`);
        el.innerHTML = items.length
          ? items.map(l => `
              <div class="admin-audit-row">
                <p><strong>${esc(l.action)}</strong> on ${esc(l.target_type)}${l.target_id != null ? ' #' + esc(l.target_id) : ''} &middot; ${esc(l.admin_name || 'Admin #' + l.admin_id)}${l.note ? ` &mdash; ${esc(l.note)}` : ''}</p>
                <p class="audit-time">${esc(l.timestamp)}</p>
              </div>`).join('')
          : '<p class="empty-text">No audit entries yet.</p>';
      } catch (_) {
        el.innerHTML = '<p class="empty-text">Could not load the audit log.</p>';
      }
    }
    // Applications tab
    async function loadAdminApps() {
      const listEl = document.getElementById('admin-applications-list');
      if (!listEl) return;
      const status = document.getElementById('admin-apps-status')?.value || '';
      listEl.innerHTML = '<p class="loading-text">Loading\u2026</p>';
      try {
        const { items } = await api('/api/admin/applications' + (status ? '?status=' + encodeURIComponent(status) : ''));
        if (!items.length) { listEl.innerHTML = '<p class="empty-text">No applications found.</p>'; return; }
        listEl.innerHTML = items.map(a => `
          <div class="admin-approve-card u-flex-center">
            <div class="u-flex-grow-1">
              <p class="eyebrow u-school-title-sm">${esc(a.scholarship_title || 'Scholarship')}</p>
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
              sel.closest('.admin-approve-card').querySelector('.app-status-badge').outerHTML = appStatusBadge(newStatus);
            } catch (err) {
              alert(err.message);
            } finally { sel.disabled = false; sel.value = ''; }
          });
        });
      } catch (err) {
        listEl.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }

    // Schools tab
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
                  ${s.registration_number ? `<span class="u-school-copy-inline">Reg. ${esc(s.registration_number)} ${Number(s.registration_verified) ? '&mdash; verified' : '&mdash; unverified'}</span>` : ''}
                </div>
                <div class="u-inline-flex-wrap-sm">
                  <a class="card-button u-card-button-compact-tight" href="/schools/${s.id}" target="_blank">View</a>
                  ${s.registration_number ? `<button class="btn-toggle-verify u-admin-action-btn" data-type="school" data-id="${s.id}" data-verified="${Number(s.registration_verified) ? 1 : 0}">${Number(s.registration_verified) ? 'Unverify' : 'Verify Registration'}</button>` : ''}
                  <button class="btn-delete-school u-btn-pill-danger" data-id="${s.id}">Delete</button>
                </div>
              </div>`).join('')
          : '<p class="empty-text">No schools found.</p>';

        listEl.querySelectorAll('.btn-delete-school').forEach(btn => {
          btn.addEventListener('click', () => {
            runDeleteWithConfirm(btn, 'Permanently delete this school and all its requirements? This cannot be undone.',
              `/api/schools/${btn.dataset.id}`, loadAdminSchools);
          });
        });
        wireVerifyButtons(listEl, loadAdminSchools);
      } catch (err) {
        listEl.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }

    // Shared by the schools/NGOs/partner-organisations "Delete" buttons —
    // confirm, disable, DELETE, reload; on failure, re-enable and show the
    // error on the button.
    async function runDeleteWithConfirm(btn, confirmMsg, endpoint, reload) {
      if (!confirm(confirmMsg)) return;
      btn.disabled = true;
      try {
        await api(endpoint, { method: 'DELETE' });
        reload();
      } catch (err) { btn.disabled = false; btn.textContent = err.message; }
    }

    function wireVerifyButtons(container, reload) {
      container.querySelectorAll('.btn-toggle-verify').forEach(btn => {
        btn.addEventListener('click', async () => {
          const nowVerified = btn.dataset.verified === '1';
          btn.disabled = true;
          try {
            await api('/api/admin/registration-verify', { method: 'POST', body: JSON.stringify({
              target_type: btn.dataset.type, target_id: Number(btn.dataset.id), verified: !nowVerified,
            })});
            reload();
          } catch (err) { btn.disabled = false; alert(err.message); }
        });
      });
    }

    // Shared by the school/NGO/partner-organisation onboarding forms below —
    // each POSTs the form, shows an invite link on success, and reloads its
    // own list. Only the endpoint, success text, invite-link element IDs,
    // reload callback, and (for schools) a payload transform differ.
    async function handleOnboardSubmit(form, msgEl, endpoint, successMsg, inviteIds, reload, transform) {
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(msgEl, 'Onboarding…');
      const fd = Object.fromEntries(new FormData(form));
      if (transform) transform(fd, form);
      try {
        const res = await api(endpoint, { method: 'POST', body: JSON.stringify(fd) });
        setMsg(msgEl, successMsg);
        form.reset();
        const wrap = document.getElementById(inviteIds.wrap);
        const linkEl = document.getElementById(inviteIds.link);
        const noteEl = document.getElementById(inviteIds.note);
        if (wrap && linkEl) {
          linkEl.textContent = res.invite_link;
          if (noteEl) noteEl.textContent = res.email_sent
            ? `Invitation email sent to ${esc(fd.email)}.`
            : `SMTP not configured — share this link manually with ${esc(fd.email)}.`;
          wrap.style.display = 'block';
        }
        reload();
      } catch (err) {
        setMsg(msgEl, err.message, true);
      } finally { btn.disabled = false; }
    }

    // Organisations tab
    async function loadAdminNgos() {
      const listEl  = document.getElementById('admin-ngos-list');
      const countEl = document.getElementById('admin-ngos-count');
      if (!listEl) return;
      listEl.innerHTML = '<p class="loading-text">Loading…</p>';
      try {
        const { items } = await api('/api/admin/ngos');
        if (countEl) countEl.textContent = `${items.length} organisation${items.length !== 1 ? 's' : ''}`;
        listEl.innerHTML = items.length
          ? items.map(n => `
              <div class="admin-user-row">
                <div>
                  <strong>${esc(n.org_name)}</strong>
                  <span>${esc(n.org_type || 'NGO')} &middot; ${esc(n.county || '')}${n.county && n.state ? ', ' : ''}${esc(n.state || '')} &middot; ${esc(n.email || n.phone || 'no contact')}</span>
                  <span class="u-school-copy-inline">${Number(n.verified) ? 'Listed' : 'Awaiting approval'} &middot; Registration ${Number(n.registration_verified) ? 'verified' : 'unverified'}</span>
                </div>
                <div class="u-inline-flex-wrap-sm">
                  <button class="btn-toggle-verify u-admin-action-btn" data-type="ngo" data-id="${n.id}" data-verified="${Number(n.registration_verified) ? 1 : 0}">${Number(n.registration_verified) ? 'Unverify' : 'Verify Registration'}</button>
                  <button class="btn-delete-ngo u-btn-pill-danger" data-id="${n.id}">Delete</button>
                </div>
              </div>`).join('')
          : '<p class="empty-text">No organisations found.</p>';

        listEl.querySelectorAll('.btn-delete-ngo').forEach(btn => {
          btn.addEventListener('click', () => {
            runDeleteWithConfirm(btn, 'Permanently delete this organisation, its scholarships and programmes? This cannot be undone.',
              `/api/admin/ngos/${btn.dataset.id}`, loadAdminNgos);
          });
        });
        wireVerifyButtons(listEl, loadAdminNgos);
      } catch (err) {
        listEl.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }

    // Partner Organisations tab
    async function loadAdminOrganizations() {
      const listEl  = document.getElementById('admin-partners-list');
      const countEl = document.getElementById('admin-partners-count');
      if (!listEl) return;
      listEl.innerHTML = '<p class="loading-text">Loading…</p>';
      try {
        const [verified, pending] = await Promise.all([
          api('/api/organizations?verified=1'),
          api('/api/organizations?verified=0'),
        ]);
        const items = [...pending.items, ...verified.items];
        if (countEl) countEl.textContent = `${items.length} organisation${items.length !== 1 ? 's' : ''}`;
        listEl.innerHTML = items.length
          ? items.map(o => `
              <div class="admin-user-row">
                <div>
                  <strong>${esc(o.name)}</strong>
                  <span>${esc(o.org_type || 'Organisation')} &middot; ${esc(o.state || 'National')} &middot; ${esc(o.email || o.phone || 'no contact')}</span>
                  <span class="u-school-copy-inline">${Number(o.verified) ? 'Listed' : 'Awaiting approval'}</span>
                </div>
                <div class="u-inline-flex-wrap-sm">
                  <button class="btn-delete-partner u-btn-pill-danger" data-id="${o.id}">Delete</button>
                </div>
              </div>`).join('')
          : '<p class="empty-text">No partner organisations found.</p>';

        listEl.querySelectorAll('.btn-delete-partner').forEach(btn => {
          btn.addEventListener('click', () => {
            runDeleteWithConfirm(btn, 'Permanently delete this organisation? This cannot be undone.',
              `/api/admin/organizations/${btn.dataset.id}`, loadAdminOrganizations);
          });
        });
      } catch (err) {
        listEl.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }

    // Tools tab: backup status, CSV export
    async function loadBackupStatus() {
      const el = document.getElementById('admin-backup-status');
      if (!el) return;
      el.innerHTML = '<p class="loading-text">Loading…</p>';
      try {
        const { items } = await api('/api/admin/backup-status');
        el.innerHTML = items.length
          ? items.map(b => `
              <div class="admin-audit-row">
                <p><strong>${b.success ? 'Success' : 'Failed'}</strong>${b.file_size ? ' &middot; ' + esc(Math.round(b.file_size / 1024)) + ' KB' : ''}${b.message ? ' &mdash; ' + esc(b.message) : ''}</p>
                <p class="audit-time">${esc(b.ran_at)}</p>
              </div>`).join('')
          : '<p class="empty-text">No backup runs recorded yet.</p>';
      } catch (err) {
        el.innerHTML = `<p class="u-copy-danger">${esc(err.message)}</p>`;
      }
    }
  // Admin dashboard bootstrap: auth/role guard, wires every tab's static
  // elements (tab/sub-tab buttons, filter forms, onboarding forms) to the
  // loaders and helpers defined above, then kicks off the initial load.
  async function initAdmin() {
    if (!getToken()) { window.location.href = '/login'; return; }
    const user = getUser();
    const notice = document.getElementById('admin-notice');
    if (user?.role !== 'admin') {
      if (notice) notice.classList.remove('hidden');
      return;
    }

    // Tab navigation
    const tabBtns = [...document.querySelectorAll('.admin-tab-btn')];
    const subBtns = [...document.querySelectorAll('.admin-sub-btn')];
    tabBtns.forEach(b => b.addEventListener('click', () => activateTab(b.dataset.tab)));
    subBtns.forEach(b => b.addEventListener('click', () => activateSub(b.dataset.sub)));
    activateTab('tab-approvals');
    activateSub('sub-materials');

    document.getElementById('audit-filter-form')?.addEventListener('submit', (e) => { e.preventDefault(); loadAuditLog(); });
    document.getElementById('audit-filter-clear')?.addEventListener('click', () => setTimeout(loadAuditLog, 0));

    document.getElementById('user-filter-form')?.addEventListener('submit', (e) => { e.preventDefault(); loadUsers(); });
    autoApplyFilterSelects(document.getElementById('user-filter-form'), loadUsers);

    document.getElementById('admin-apps-filter-form')?.addEventListener('submit', (e) => { e.preventDefault(); loadAdminApps(); });
    document.querySelector('[data-tab="tab-applications"]')?.addEventListener('click', () => loadAdminApps());

    const addSchoolForm = document.getElementById('admin-add-school-form');
    const addSchoolMsg  = document.getElementById('admin-add-school-msg');
    addSchoolForm?.addEventListener('submit', (e) => {
      e.preventDefault();
      handleOnboardSubmit(addSchoolForm, addSchoolMsg, '/api/admin/onboard-school', 'School onboarded ✓',
        { wrap: 'admin-invite-link-wrap', link: 'admin-invite-link-text', note: 'admin-invite-email-note' },
        loadAdminSchools,
        (fd, form) => {
          ['capacity', 'enrollment'].forEach(k => { if (fd[k]) fd[k] = Number(fd[k]); });
          fd.hours = composeHours(form);
        });
    });

    const addNgoForm = document.getElementById('admin-add-ngo-form');
    const addNgoMsg  = document.getElementById('admin-add-ngo-msg');
    addNgoForm?.addEventListener('submit', (e) => {
      e.preventDefault();
      handleOnboardSubmit(addNgoForm, addNgoMsg, '/api/admin/onboard-ngo', 'Organisation onboarded ✓',
        { wrap: 'admin-ngo-invite-link-wrap', link: 'admin-ngo-invite-link-text', note: 'admin-ngo-invite-email-note' },
        loadAdminNgos);
    });

    const addPartnerForm = document.getElementById('admin-add-partner-form');
    const addPartnerMsg  = document.getElementById('admin-add-partner-msg');
    addPartnerForm?.addEventListener('submit', (e) => {
      e.preventDefault();
      handleOnboardSubmit(addPartnerForm, addPartnerMsg, '/api/admin/organizations', 'Organisation onboarded ✓',
        { wrap: 'admin-partner-invite-link-wrap', link: 'admin-partner-invite-link-text', note: 'admin-partner-invite-email-note' },
        loadAdminOrganizations);
    });

    document.querySelector('[data-tab="tab-schools"]')?.addEventListener('click', () => loadAdminSchools());
    document.querySelector('[data-tab="tab-ngos"]')?.addEventListener('click', () => loadAdminNgos());
    document.querySelector('[data-tab="tab-partners"]')?.addEventListener('click', () => loadAdminOrganizations());

    document.getElementById('backup-status-refresh')?.addEventListener('click', () => loadBackupStatus());
    document.querySelector('[data-tab="tab-tools"]')?.addEventListener('click', () => loadBackupStatus());

    document.getElementById('analytics-export-link')?.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        const res = await fetch('/api/admin/analytics/export.csv', { headers: { Authorization: `Bearer ${getToken()}` } });
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href = url; a.download = 'eduportal_analytics.csv';
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } catch (err) { alert(err.message); }
    });

    loadAll();
  }


  // Bookmarks
  async function initBookmarks() {
    if (!getToken()) { window.location.href = '/login'; return; }

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
              ? (materialIsVideo(m)
                ? `<a class="card-link u-link-maroon" href="/api/materials/${m.id}/stream?token=${encodeURIComponent(getToken())}" target="_blank" rel="noopener">
                    <svg viewBox="0 0 14 14" fill="none" width="12" height="12" class="u-mr-sm"><path d="M5 3l6 4-6 4V3z" fill="currentColor"/></svg>
                    Watch Tutorial
                  </a>`
                : `<a class="card-link u-link-maroon" href="/api/materials/${m.id}/stream?token=${encodeURIComponent(getToken())}" target="_blank" rel="noopener">
                  <svg viewBox="0 0 14 14" fill="none" width="12" height="12" class="u-mr-sm"><path d="M1 7s2.2-4.4 6-4.4S13 7 13 7s-2.2 4.4-6 4.4S1 7 1 7z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><circle cx="7" cy="7" r="1.7" stroke="currentColor" stroke-width="1.4"/></svg>
                  View
                </a>
                ${canDownloadMaterial() ? `<a class="card-link u-link-maroon" href="/api/materials/${m.id}/download" download>
                  <svg viewBox="0 0 14 14" fill="none" width="12" height="12" class="u-mr-sm"><path d="M7 1v7M4 6l3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M1 11h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
                  Download File
                </a>` : ''}`)
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
          <p class="result-card-preview">${esc(s.eligibility || '')}</p>
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

  // Forgot / Reset Password
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
        setTimeout(() => { window.location.href = '/login'; }, 1800);
      } catch (err) {
        setMsg(resetMsg, err.message, true);
        btn.disabled = false;
      }
    });
  }

  // School Dashboard
  async function initSchoolDashboard() {
    if (!getToken()) { window.location.href = '/login'; return; }
    const user = getUser();
    const notice = document.getElementById('school-dash-notice');
    if (user?.role !== 'school_admin' && user?.role !== 'admin') {
      if (notice) notice.classList.remove('hidden');
      return;
    }

    // A school_admin with no school linked yet gets a "list your school"
    // form instead of a dead-end error message.
    if (user.role === 'school_admin' && !user.school_id) {
      const claimSection = document.getElementById('school-dash-claim');
      const claimForm = document.getElementById('school-claim-form');
      const claimMsg  = document.getElementById('school-claim-msg');
      if (claimSection) claimSection.classList.remove('hidden');
      claimForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = claimForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        setMsg(claimMsg, 'Submitting…');
        const fd = Object.fromEntries(new FormData(claimForm));
        if (fd.year_established) fd.year_established = Number(fd.year_established);
        try {
          const data = await api('/api/schools', { method: 'POST', body: JSON.stringify(fd) });
          setMsg(claimMsg, data.message || 'Submitted for admin review.');
          const updatedUser = { ...user, school_id: data.id };
          saveSession(getToken(), updatedUser, getRefreshToken());
          setTimeout(() => window.location.reload(), 1200);
        } catch (err) {
          setMsg(claimMsg, err.message, true);
          btn.disabled = false;
        }
      });
      return;
    }

    // Load school data via /api/my-school
    let school, materials, bookmarkCount, examResults;
    try {
      const data = await api('/api/my-school');
      school        = data.school;
      materials     = data.materials;
      bookmarkCount = data.bookmark_count;
      examResults   = data.exam_results;
    } catch (err) {
      // The cached user.school_id above can go stale the moment an admin
      // deletes this school — the browser has no way to know that happened,
      // so it still skips straight past the claim form to this fetch, which
      // now 404s ("no school assigned" / "school not found" depending on
      // when it was deleted). Self-heal instead of leaving a school_admin
      // stuck on a dead-end error with no way back to the claim form: clear
      // the stale id and reload once, which re-runs this function down the
      // "list your school" branch above.
      const msg = (err.message || '').toLowerCase();
      if (user.role === 'school_admin' && (msg.includes('no school assigned') || msg.includes('school not found'))) {
        saveSession(getToken(), { ...user, school_id: null }, getRefreshToken());
        window.location.reload();
        return;
      }
      if (notice) { notice.textContent = err.message; notice.classList.remove('hidden'); }
      return;
    }

    if (!school.approved) {
      const infoMsgEl = document.getElementById('sd-info-msg');
      setMsg(infoMsgEl, 'This school is awaiting admin approval — it will appear in the public directory once approved. You can keep completing the profile below in the meantime.');
      infoMsgEl?.classList.remove('is-success', 'is-error');
      infoMsgEl?.classList.add('is-notice');
    }

    // Fill header
    const title = document.getElementById('school-dash-title');
    if (title) title.textContent = school.name;
    const profileLink = document.getElementById('sd-public-profile-link');
    if (profileLink) { profileLink.href = `/schools/${school.id}`; profileLink.classList.remove('hidden'); }

    // Fill stat cards
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('sd-enrollment', school.enrollment ?? '—');
    set('sd-capacity',   school.capacity   ?? '—');
    set('sd-bookmarks',  bookmarkCount      ?? 0);
    set('sd-status',     school.status      ?? '—');

    // Pre-fill info form
    const SCHOOL_TEXT_FIELDS = [
      'name','status','capacity','enrollment','contact_name','phone','email','description',
      'state','county','address','registration_number','year_established',
      'curriculum','language','subjects_offered','mission','vision','core_values',
      'age_requirements','entry_grades','fees_structure','how_to_apply','requirements_text',
      'headteacher_name','teaching_staff_count','classroom_count',
    ];
    const SCHOOL_FLAG_FIELDS = [
      'has_library','has_laboratory','has_sports_facilities','has_water_sanitation','has_electricity',
      'has_sports_clubs','has_arts_culture','has_academic_clubs','has_student_government',
    ];
    const infoForm = document.getElementById('sd-info-form');
    if (infoForm) {
      const fill = (name, val) => { const el = infoForm.querySelector(`[name="${name}"]`); if (el && val != null) el.value = val; };
      SCHOOL_TEXT_FIELDS.forEach(f => fill(f, school[f]));
      SCHOOL_FLAG_FIELDS.forEach(f => {
        const el = infoForm.querySelector(`[name="${f}"]`);
        if (el) el.checked = !!Number(school[f]);
      });
      fillHoursPickers(infoForm, school.hours);
      const logoInput    = document.getElementById('sd-logo-input');
      const logoUploadBtn = document.getElementById('sd-logo-upload-btn');
      logoUploadBtn?.addEventListener('click', () => logoInput?.click());
      wireLogoUpload({
        inputEl: logoInput,
        imgEl: document.getElementById('sd-logo-img'),
        fallbackEl: document.getElementById('sd-logo-fallback'),
        msgEl: document.getElementById('sd-logo-msg'),
        uploadUrl: `/api/schools/${school.id}/logo`,
        currentUrl: school.logo_url,
      });

      // Extracurricular activities beyond the four fixed checkboxes — a
      // free-form, addable/removable tag list backed by one text column.
      const tagList  = document.getElementById('sd-activity-tags');
      const tagInput = document.getElementById('sd-activity-input');
      let activityTags = (school.extracurricular_other || '')
        .split(',').map(s => s.trim()).filter(Boolean);
      function renderActivityTags() {
        if (!tagList) return;
        tagList.innerHTML = activityTags.map((t, i) => `
          <span class="school-tag">${esc(t)}<button type="button" class="school-tag-remove" data-idx="${i}" aria-label="Remove ${esc(t)}">&times;</button></span>
        `).join('');
        tagList.querySelectorAll('.school-tag-remove').forEach(btn => {
          btn.addEventListener('click', () => {
            activityTags.splice(Number(btn.dataset.idx), 1);
            renderActivityTags();
          });
        });
      }
      renderActivityTags();
      function addActivityTag() {
        const val = tagInput.value.trim();
        if (val && !activityTags.includes(val)) { activityTags.push(val); renderActivityTags(); }
        tagInput.value = '';
      }
      document.getElementById('sd-activity-add-btn')?.addEventListener('click', addActivityTag);
      tagInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); addActivityTag(); }
      });

      const infoMsg = document.getElementById('sd-info-msg');
      infoForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = infoForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        setMsg(infoMsg, 'Saving\u2026');
        const fd = Object.fromEntries(new FormData(infoForm));
        // An empty numeric field arrives as '' from FormData, which the
        // database rejects for an integer column \u2014 send null instead so
        // "leave this blank" actually clears the field rather than 500ing.
        ['capacity','enrollment','year_established','teaching_staff_count','classroom_count'].forEach(k => {
          fd[k] = fd[k] ? Number(fd[k]) : null;
        });
        SCHOOL_FLAG_FIELDS.forEach(f => { fd[f] = infoForm.querySelector(`[name="${f}"]`)?.checked ? 1 : 0; });
        fd.hours = composeHours(infoForm);
        fd.extracurricular_other = activityTags.join(', ');
        try {
          await api(`/api/schools/${school.id}`, { method: 'PUT', body: JSON.stringify(fd) });
          setMsg(infoMsg, 'Saved \u2713');
          const title = document.getElementById('school-dash-title');
          if (title && fd.name) title.textContent = fd.name;
        } catch (err) { setMsg(infoMsg, err.message, true); }
        finally { btn.disabled = false; }
      });
    }

    // Requirements document — a PDF/scanned-image attachment, alongside
    // the pasted "Admission Requirements" text in the main info form.
    const reqDocInput = document.getElementById('sd-reqdoc-input');
    const reqDocBtn   = document.getElementById('sd-reqdoc-upload-btn');
    const reqDocLink  = document.getElementById('sd-reqdoc-link');
    const reqDocMsg   = document.getElementById('sd-reqdoc-msg');
    if (reqDocLink && school.requirements_doc_url) {
      reqDocLink.href = school.requirements_doc_url;
      reqDocLink.classList.remove('hidden');
    }
    reqDocBtn?.addEventListener('click', () => reqDocInput?.click());
    reqDocInput?.addEventListener('change', async () => {
      const file = reqDocInput.files?.[0];
      if (!file) return;
      if (file.size > 20 * 1024 * 1024) { setMsg(reqDocMsg, 'File must be under 20 MB.', true); return; }
      setMsg(reqDocMsg, 'Uploading…');
      try {
        const data = await EP.uploadFile(`/api/schools/${school.id}/requirements-doc`, 'doc', file);
        setMsg(reqDocMsg, 'Document saved.');
        if (reqDocLink) {
          reqDocLink.href = data.requirements_doc_url + '?t=' + Date.now();
          reqDocLink.classList.remove('hidden');
        }
      } catch (err) {
        setMsg(reqDocMsg, 'Upload failed, document was not saved: ' + err.message, true);
      }
    });

    // Exam results editor
    const examEditor = document.getElementById('sd-exam-editor');
    const examMsg     = document.getElementById('sd-exam-msg');
    let examItems = (examResults || []).map(r => ({ year: r.year, subject: r.subject, pass_rate: r.pass_rate }));

    function renderExamEditor() {
      if (!examEditor) return;
      examEditor.innerHTML = examItems.map((r, i) => `
        <div class="req-row exam-row">
          <input class="field-input exam-year" type="number" placeholder="Year" value="${esc(r.year)}">
          <input class="field-input exam-subject" placeholder="Subject" value="${esc(r.subject)}">
          <input class="field-input exam-rate" type="number" step="0.1" min="0" max="100" placeholder="Pass rate %" value="${esc(r.pass_rate)}">
          <button class="req-remove u-btn-outline-danger" data-idx="${i}" type="button">&times;</button>
        </div>`).join('');
      examEditor.querySelectorAll('.req-remove').forEach(btn => {
        btn.addEventListener('click', () => { examItems.splice(Number(btn.dataset.idx), 1); renderExamEditor(); });
      });
    }
    renderExamEditor();

    document.getElementById('sd-add-exam')?.addEventListener('click', () => {
      examItems.push({ year: new Date().getFullYear(), subject: '', pass_rate: '' });
      renderExamEditor();
    });
    document.getElementById('sd-save-exam')?.addEventListener('click', async () => {
      const btn = document.getElementById('sd-save-exam');
      btn.disabled = true;
      setMsg(examMsg, 'Saving\u2026');
      const rows = examEditor.querySelectorAll('.exam-row');
      const saved = [...rows].map(row => ({
        year: Number(row.querySelector('.exam-year').value),
        subject: row.querySelector('.exam-subject').value.trim(),
        pass_rate: Number(row.querySelector('.exam-rate').value),
      })).filter(r => r.subject && r.year);
      try {
        await api(`/api/schools/${school.id}/exam-results`, { method: 'PUT', body: JSON.stringify({ items: saved }) });
        setMsg(examMsg, 'Saved \u2713');
        examItems = saved;
      } catch (err) { setMsg(examMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // Announcement form (doubles as the "save edits" form once
    // dataset.editingId is set \u2014 same pattern as the NGO dashboard)
    const annForm = document.getElementById('sd-ann-form');
    const annMsg  = document.getElementById('sd-ann-msg');
    annForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = annForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      const rawFd = new FormData(annForm);
      const attachFile = rawFd.get('attachment_file');
      const fd = { ...Object.fromEntries(rawFd), source_type: 'School' };
      delete fd.attachment_file;
      try {
        await EP.submitEditablePost({
          form: annForm,
          editingId: annForm.dataset.editingId,
          payload: fd,
          createUrl: '/api/announcements',
          idUrl: (id) => `/api/announcements/${id}`,
          fileUploads: [{ file: attachFile, uploadUrl: (id) => `/api/announcements/${id}/upload` }],
          request: api,
          setMsg: (text, isError) => setMsg(annMsg, text, isError),
        });
        loadRecentAnnouncements();
      } catch (err) { setMsg(annMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // Material upload form (doubles as the "save edits" form once
    // dataset.editingId is set)
    const matForm = document.getElementById('sd-mat-form');
    const matMsg  = document.getElementById('sd-mat-msg');
    matForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = matForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      const rawFd = new FormData(matForm);
      const file = rawFd.get('file');
      const meta = { title: rawFd.get('title'), subject: rawFd.get('subject'), grade: rawFd.get('grade'), year: Number(rawFd.get('year')), type: rawFd.get('type') };
      try {
        await EP.submitEditablePost({
          form: matForm,
          editingId: matForm.dataset.editingId,
          payload: meta,
          createUrl: '/api/materials',
          idUrl: (id) => `/api/materials/${id}`,
          fileUploads: [{ file, uploadUrl: (id) => `/api/materials/${id}/upload` }],
          request: api,
          setMsg: (text, isError) => setMsg(matMsg, text, isError),
        });
        loadRecentMaterials();
      } catch (err) { setMsg(matMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // Load recent announcements & materials \u2014 via /api/my-school so this
    // only ever shows (and edits/deletes) this school's own submissions,
    // not every school/NGO/org's pending items site-wide.
    async function loadRecentAnnouncements() {
      const el = document.getElementById('sd-ann-list');
      if (!el) return;
      let anns;
      try {
        anns = (await api('/api/my-school')).announcements || [];
      } catch (_) { el.innerHTML = '<p class="empty-text">Could not load announcements.</p>'; return; }
      el.innerHTML = anns.length
        ? anns.map(a => {
          const badge = a.approved
            ? '<span class="status-badge status-open">Live</span>'
            : '<span class="status-badge status-limited">Pending</span>';
          const rejectNote = (!a.approved && a.rejection_reason)
            ? `<p class="u-text-danger u-list-copy-xs">Feedback: ${esc(a.rejection_reason)}</p>` : '';
          return `
          <div class="admin-audit-row">
            <div>
              <p><strong>${esc(a.title)}</strong> ${badge}</p>
              <p class="audit-time">${esc(a.created_at ? a.created_at.slice(0,10) : '')}</p>
              ${rejectNote}
            </div>
            <div class="admin-approve-actions">
              <button type="button" class="card-button u-inline-btn-sm" data-ann-edit="${a.id}">Edit</button>
              <button type="button" class="card-button btn-reject u-inline-btn-sm" data-ann-del="${a.id}">Delete</button>
            </div>
          </div>`;
        }).join('')
        : '<p class="empty-text">No announcements yet.</p>';

      el.querySelectorAll('[data-ann-del]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          if (!confirm('Delete this announcement?')) return;
          try {
            await api(`/api/announcements/${btn.dataset.annDel}`, { method: 'DELETE' });
            loadRecentAnnouncements();
          } catch (err) { setMsg(annMsg, err.message, true); }
        });
      });
      el.querySelectorAll('[data-ann-edit]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const a = anns.find(x => String(x.id) === btn.dataset.annEdit);
          if (!a || !annForm) return;
          EP.populateFormFields(annForm, a, ['title', 'body', 'audience', 'priority', 'expires_at', 'attachment_url']);
          annForm.dataset.editingId = a.id;
          setMsg(annMsg, `Editing "${a.title}" \u2014 resubmit to save changes.`);
          annForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
      });
    }

    async function loadRecentMaterials() {
      const el = document.getElementById('sd-mat-list');
      if (!el) return;
      let items;
      try {
        items = (await api('/api/my-school')).materials || [];
      } catch (_) { el.innerHTML = '<p class="empty-text">Could not load materials.</p>'; return; }
      el.innerHTML = items.length
        ? items.map(m => {
          const badge = m.approved
            ? '<span class="status-badge status-open">Live</span>'
            : '<span class="status-badge status-limited">Pending</span>';
          const rejectNote = (!m.approved && m.rejection_reason)
            ? `<p class="u-text-danger u-list-copy-xs">Feedback: ${esc(m.rejection_reason)}</p>` : '';
          return `
          <div class="admin-audit-row">
            <div>
              <p><strong>${esc(m.title)}</strong> ${badge}</p>
              <p class="audit-time">${esc(m.subject)} &middot; ${esc(m.grade)} &middot; ${esc(m.year)}</p>
              ${rejectNote}
            </div>
            <div class="admin-approve-actions">
              <button type="button" class="card-button u-inline-btn-sm" data-mat-edit="${m.id}">Edit</button>
              <button type="button" class="card-button btn-reject u-inline-btn-sm" data-mat-del="${m.id}">Delete</button>
            </div>
          </div>`;
        }).join('')
        : '<p class="empty-text">No materials yet.</p>';

      el.querySelectorAll('[data-mat-del]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          if (!confirm('Delete this material?')) return;
          try {
            await api(`/api/materials/${btn.dataset.matDel}`, { method: 'DELETE' });
            loadRecentMaterials();
          } catch (err) { setMsg(matMsg, err.message, true); }
        });
      });
      el.querySelectorAll('[data-mat-edit]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const m = items.find(x => String(x.id) === btn.dataset.matEdit);
          if (!m || !matForm) return;
          EP.populateFormFields(matForm, m, ['title', 'subject', 'grade', 'year', 'type']);
          matForm.dataset.editingId = m.id;
          setMsg(matMsg, `Editing "${m.title}" \u2014 resubmit to save changes.`);
          matForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
      });
    }

    loadRecentAnnouncements();
    loadRecentMaterials();
  }

  // NGO Dashboard
  async function initNGODashboard() {
    if (!getToken()) { window.location.href = '/login'; return; }
    const user = getUser();
    const notice = document.getElementById('ngo-dash-notice');
    if (user?.role !== 'ngo_officer' && user?.role !== 'admin') {
      if (notice) notice.classList.remove('hidden');
      return;
    }

    // Load NGO data
    let ngoData;
    try {
      ngoData = await api('/api/my-ngo');
    } catch (err) {
      if (notice) { notice.textContent = err.message; notice.classList.remove('hidden'); }
      return;
    }

    const { ngo, scholarships: ngoScholarships, announcements: ngoAnns, programs: ngoPrograms, applications: ngoApps } = ngoData;
    const title = document.getElementById('ngo-dash-title');
    if (title) title.textContent = ngo ? ngo.org_name : 'Your organisation';

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('nd-sch-count', ngoScholarships?.length ?? 0);
    set('nd-app-count', ngoApps?.length ?? 0);
    set('nd-ann-count', ngoAnns?.length ?? 0);

    // Pre-fill org profile
    const orgForm = document.getElementById('nd-org-form');
    const orgMsg  = document.getElementById('nd-org-msg');
    const NGO_TEXT_FIELDS = [
      'org_name', 'contact', 'phone', 'email', 'description',
      'registration_number', 'year_founded', 'org_type', 'areas_of_focus',
      'state', 'county', 'website', 'mission', 'vision', 'core_values',
    ];
    if (orgForm && ngo) {
      NGO_TEXT_FIELDS.forEach((f) => {
        const el = orgForm.querySelector(`[name="${f}"]`);
        if (el && ngo[f] != null) el.value = ngo[f];
      });
      if (!ngo.registration_verified) {
        // Distinct from the org being approved/listed — a separate, optional
        // attestation an admin sets on the registration number specifically.
        // Not styled as success (green) or error (red): it's neither.
        setMsg(orgMsg, "Registration number not yet verified by an admin — a separate check from your organisation being approved and listed, so this doesn't block anything.");
        orgMsg.classList.remove('is-success', 'is-error');
        orgMsg.classList.add('is-notice');
      }
    }
    const ngoLogoInput = document.getElementById('ngo-logo-input');
    const ngoLogoUploadBtn = document.getElementById('ngo-logo-upload-btn');
    const ngoLogoMsg = document.getElementById('ngo-logo-msg');
    ngoLogoUploadBtn?.addEventListener('click', () => ngoLogoInput?.click());
    // No NGO row exists yet on a brand-new account \u2014 disable the uploader
    // instead of letting the user hit the server-side error blind.
    function setLogoUploaderEnabled(enabled) {
      if (ngoLogoUploadBtn) ngoLogoUploadBtn.disabled = !enabled;
      if (ngoLogoInput) ngoLogoInput.disabled = !enabled;
      if (!enabled) setMsg(ngoLogoMsg, 'Save your organisation profile below first, then add a logo.');
      else if (ngoLogoMsg && ngoLogoMsg.textContent.includes('Save your organisation profile')) setMsg(ngoLogoMsg, '');
    }
    setLogoUploaderEnabled(!!ngo);
    wireLogoUpload({
      inputEl: ngoLogoInput,
      imgEl: document.getElementById('ngo-logo-img'),
      fallbackEl: document.getElementById('ngo-logo-fallback'),
      msgEl: ngoLogoMsg,
      uploadUrl: '/api/my-ngo/logo',
      currentUrl: ngo?.logo_url,
    });
    orgForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = orgForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(orgMsg, 'Saving\u2026');
      const fd = Object.fromEntries(new FormData(orgForm));
      fd.year_founded = fd.year_founded ? Number(fd.year_founded) : null;
      try {
        await api('/api/my-ngo', { method: 'PUT', body: JSON.stringify(fd) });
        setMsg(orgMsg, 'Saved \u2713');
        setLogoUploaderEnabled(true);
        // First save creates the NGO row \u2014 reflect that immediately instead
        // of leaving the title/stats stuck at their pre-save placeholders.
        if (title && fd.org_name) title.textContent = fd.org_name;
      } catch (err) { setMsg(orgMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // Programmes: list, add, delete
    const progList = document.getElementById('nd-prog-list');
    const progForm = document.getElementById('nd-prog-form');
    const progMsg  = document.getElementById('nd-prog-msg');
    function renderPrograms(programs) {
      if (!progList) return;
      progList.innerHTML = programs.length
        ? programs.map(p => `
          <div class="admin-approve-card">
            <div class="u-card-flex-main">
              <h3>${esc(p.name)}</h3>
              <p>${esc(p.target_beneficiaries || 'Beneficiaries not specified')}${p.geographic_coverage ? ' \u00b7 ' + esc(p.geographic_coverage) : ''}${p.beneficiaries_per_year ? ' \u00b7 ~' + esc(p.beneficiaries_per_year) + '/yr' : ''}</p>
            </div>
            <div class="admin-approve-actions">
              <button type="button" class="card-button btn-reject u-inline-btn-sm" data-prog-id="${p.id}">Remove</button>
            </div>
          </div>`).join('')
        : '<p class="empty-text">No programmes added yet.</p>';
      progList.querySelectorAll('[data-prog-id]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          if (!confirm('Remove this programme?')) return;
          try {
            await api(`/api/my-ngo/programs/${btn.dataset.progId}`, { method: 'DELETE' });
            loadPrograms();
          } catch (err) { setMsg(progMsg, err.message, true); }
        });
      });
    }
    renderPrograms(ngoPrograms || []);
    async function loadPrograms() {
      try {
        const { items } = await api('/api/my-ngo/programs');
        renderPrograms(items);
      } catch (_) { /* keep last render */ }
    }
    progForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = progForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      setMsg(progMsg, 'Adding\u2026');
      const fd = Object.fromEntries(new FormData(progForm));
      fd.beneficiaries_per_year = fd.beneficiaries_per_year ? Number(fd.beneficiaries_per_year) : null;
      try {
        await api('/api/my-ngo/programs', { method: 'POST', body: JSON.stringify(fd) });
        setMsg(progMsg, 'Programme added \u2713');
        progForm.reset();
        loadPrograms();
      } catch (err) { setMsg(progMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // Post scholarship form (doubles as the "save edits" form once dataset.editingId is set)
    const schForm = document.getElementById('nd-sch-form');
    const schMsg  = document.getElementById('nd-sch-msg');
    wireFilePreview(document.getElementById('nd-poster-input'), document.getElementById('nd-poster-preview'));
    wireFilePreview(document.getElementById('nd-video-input'), document.getElementById('nd-video-preview'));
    schForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = schForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      const rawFd = new FormData(schForm);
      const posterFile = rawFd.get('poster');
      const videoFile = rawFd.get('video');
      rawFd.delete('poster');
      rawFd.delete('video');
      const fd = Object.fromEntries(rawFd);
      fd.slots_available = fd.slots_available ? Number(fd.slots_available) : null;
      try {
        await EP.submitEditablePost({
          form: schForm,
          editingId: schForm.dataset.editingId,
          payload: fd,
          createUrl: '/api/scholarships',
          idUrl: (id) => `/api/scholarships/${id}`,
          fileUploads: [
            { file: posterFile, fieldName: 'poster', uploadUrl: (id) => `/api/scholarships/${id}/poster` },
            { file: videoFile, fieldName: 'video', uploadUrl: (id) => `/api/scholarships/${id}/video` },
          ],
          request: api,
          setMsg: (text, isError) => setMsg(schMsg, text, isError),
        });
        loadMyScholarships();
      } catch (err) { setMsg(schMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    // My scholarships list \u2014 editable in place, with delete
    async function loadMyScholarships() {
      const el = document.getElementById('nd-sch-list');
      if (!el) return;
      let all;
      try {
        all = (await api('/api/my-ngo')).scholarships || [];
      } catch (_) { el.innerHTML = '<p class="empty-text">Could not load scholarships.</p>'; return; }
      el.innerHTML = all.length
        ? all.map(s => {
          const badge = s.approved
            ? '<span class="status-badge status-open">Live</span>'
            : '<span class="status-badge status-limited">Pending review</span>';
          const rejectNote = (!s.approved && s.rejection_reason)
            ? `<p class="u-text-danger u-list-copy-xs">Feedback: ${esc(s.rejection_reason)}</p>` : '';
          return `
          <div class="admin-approve-card">
            <div class="u-card-flex-main">
              <div class="u-flex-wrap">${badge}</div>
              <h3>${esc(s.title)}</h3>
              <p>Deadline: ${esc(s.deadline)}${s.slots_available ? ' \u00b7 ' + esc(s.slots_available) + ' slots' : ''}</p>
              <div class="u-flex-wrap">
                ${s.poster_image_url ? '<span class="tag tag-muted">Poster image</span>' : ''}
                ${s.video_path ? '<span class="tag tag-muted">Promo video</span>' : ''}
              </div>
              ${rejectNote}
            </div>
            <div class="admin-approve-actions">
              <button type="button" class="card-button u-inline-btn-sm" data-sch-edit="${s.id}">Edit</button>
              <button type="button" class="card-button btn-reject u-inline-btn-sm" data-sch-del="${s.id}">Delete</button>
            </div>
          </div>`;
        }).join('')
        : '<p class="empty-text">No scholarships posted yet.</p>';

      el.querySelectorAll('[data-sch-del]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          if (!confirm('Delete this scholarship? This also removes any applications submitted to it.')) return;
          try {
            await api(`/api/scholarships/${btn.dataset.schDel}`, { method: 'DELETE' });
            loadMyScholarships();
          } catch (err) { setMsg(schMsg, err.message, true); }
        });
      });
      el.querySelectorAll('[data-sch-edit]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const sch = all.find(s => String(s.id) === btn.dataset.schEdit);
          if (!sch || !schForm) return;
          EP.populateFormFields(schForm, sch, ['title', 'description', 'eligibility', 'deadline',
            'how_to_apply', 'required_docs', 'external_link', 'slots_available', 'whats_covered', 'contact_person']);
          schForm.dataset.editingId = sch.id;
          setMsg(schMsg, `Editing "${sch.title}" \u2014 resubmit to save changes.`);
          schForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
      });
    }

    // Post announcement form (doubles as the "save edits" form once
    // dataset.editingId is set \u2014 same pattern as the scholarship form above)
    const annForm = document.getElementById('nd-ann-form');
    const annMsg  = document.getElementById('nd-ann-msg');
    annForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = annForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      const rawFd = new FormData(annForm);
      const attachFile = rawFd.get('attachment_file');
      const fd = { ...Object.fromEntries(rawFd), source_type: 'NGO' };
      delete fd.attachment_file;
      try {
        await EP.submitEditablePost({
          form: annForm,
          editingId: annForm.dataset.editingId,
          payload: fd,
          createUrl: '/api/announcements',
          idUrl: (id) => `/api/announcements/${id}`,
          fileUploads: [{ file: attachFile, uploadUrl: (id) => `/api/announcements/${id}/upload` }],
          request: api,
          setMsg: (text, isError) => setMsg(annMsg, text, isError),
        });
        loadMyAnnouncements();
      } catch (err) { setMsg(annMsg, err.message, true); }
      finally { btn.disabled = false; }
    });

    async function loadMyAnnouncements() {
      const el = document.getElementById('nd-ann-list');
      if (!el) return;
      let anns;
      try {
        anns = (await api('/api/my-ngo')).announcements || [];
      } catch (_) { el.innerHTML = '<p class="empty-text">Could not load announcements.</p>'; return; }
      el.innerHTML = anns.length
        ? anns.map(a => {
          const badge = a.approved
            ? '<span class="status-badge status-open">Live</span>'
            : '<span class="status-badge status-limited">Pending</span>';
          const rejectNote = (!a.approved && a.rejection_reason)
            ? `<p class="u-text-danger u-list-copy-xs">Feedback: ${esc(a.rejection_reason)}</p>` : '';
          return `
          <div class="admin-audit-row">
            <div>
              <p><strong>${esc(a.title)}</strong> ${badge}</p>
              <p class="audit-time">${esc(a.audience || 'all')} &middot; ${esc(a.created_at ? a.created_at.slice(0,10) : '')}</p>
              ${rejectNote}
            </div>
            <div class="admin-approve-actions">
              <button type="button" class="card-button u-inline-btn-sm" data-ann-edit="${a.id}">Edit</button>
              <button type="button" class="card-button btn-reject u-inline-btn-sm" data-ann-del="${a.id}">Delete</button>
            </div>
          </div>`;
        }).join('')
        : '<p class="empty-text">No announcements yet.</p>';

      el.querySelectorAll('[data-ann-del]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          if (!confirm('Delete this announcement?')) return;
          try {
            await api(`/api/announcements/${btn.dataset.annDel}`, { method: 'DELETE' });
            loadMyAnnouncements();
          } catch (err) { setMsg(annMsg, err.message, true); }
        });
      });
      el.querySelectorAll('[data-ann-edit]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const a = anns.find(x => String(x.id) === btn.dataset.annEdit);
          if (!a || !annForm) return;
          EP.populateFormFields(annForm, a, ['title', 'body', 'audience', 'priority', 'expires_at', 'attachment_url']);
          annForm.dataset.editingId = a.id;
          setMsg(annMsg, `Editing "${a.title}" \u2014 resubmit to save changes.`);
          annForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
      });
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
    loadMyAnnouncements();
  }

  // Accept Invite
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
        saveSession(data.token, data.user, data.refresh_token);
        window.location.href = data.user.role === 'school_admin' ? '/school-dashboard' : '/ngo-dashboard';
      } catch (err) {
        setMsg(msg, err.message, true);
        btn.disabled = false;
      }
    });
  }

  // Live sidebar avatar refresh (called after upload without reload)
  function _refreshSidebarAvatar(src) {
    const imgTag = `<img src="${src}" alt="" class="avatar-photo">`;
    function apply() {
      document.querySelectorAll('.sidebar-avatar-sm').forEach(el => { el.innerHTML = imgTag; });
      const trigger = document.querySelector('.account-trigger');
      if (trigger) trigger.innerHTML = imgTag;
    }
    apply();
    // Retry once after sidebar finishes rendering (sidebar-main.js is deferred)
    setTimeout(apply, 300);
  }

  // Boot
  function bootApp() {
    const page = document.body.dataset.page || '';

    // Restore avatar on every page from localStorage immediately
    const storedUser = getUser();
    if (storedUser && storedUser.avatar) {
      _refreshSidebarAvatar(storedUser.avatar);
    }
    if (document.getElementById('login-form'))    initLogin();
    if (document.getElementById('register-form')) initRegister();
    if (document.getElementById('forgot-form'))   initForgotPassword();
    if (page === 'accept-invite')  initAcceptInvite();
    if (page === 'dashboard' || document.getElementById('stat-schools')) initDashboard();
    if (page === 'directory')        initDirectory();
    if (document.getElementById('school-shell'))  initSchoolProfile();
    if (page === 'materials')        initMaterials();
    if (page === 'opportunities')    initOpportunities();
    if (page === 'my-applications')  initMyApplications();
    if (page === 'bookmarks')        initBookmarks();
    if (page === 'profile')          initProfile();
    if (page === 'settings')         initSettings();
    if (page === 'admin')            initAdmin();
    if (page === 'school-dashboard') initSchoolDashboard();
    if (page === 'ngo-dashboard')    initNGODashboard();
  }

  // Pages load this with `defer`, but guard against it running after
  // DOMContentLoaded already fired (e.g. late injection during testing).
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootApp);
  } else {
    bootApp();
  }

  // The Google Identity Services script (async, third-party) is expected to
  // call initGoogleSignIn via its onload handler once this file has already
  // defined it. On the off chance it finishes loading first, render the
  // button now instead of leaving it permanently blank.
  if (window.google && window.google.accounts && window.google.accounts.id) {
    initGoogleSignIn();
  }

})();


