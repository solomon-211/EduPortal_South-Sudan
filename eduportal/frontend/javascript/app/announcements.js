/* announcements.js — EduPortal South Sudan */
(function () {
  'use strict';

  const PUBLISHER_ROLES = new Set(['admin', 'school_admin', 'ngo_officer', 'org_publisher']);

  const PRIORITY_META = {
    urgent: { label: 'Urgent',  cls: 'ann-priority-urgent' },
    high:   { label: 'High',    cls: 'ann-priority-high'   },
    normal: { label: '',        cls: ''                     },
  };

  const ORG_TYPE_ICON = {
    'Ministry of General Education': '🏛️',
    'State Ministry of Education':   '🏢',
    'Examination Body':              '📋',
    'University':                    '🎓',
    'College':                       '🏫',
    'School':                        '🏫',
    'NGO':                           '🤝',
    'Scholarship Provider':          '💰',
  };

  // ── Helpers ────────────────────────────────────────────────────────────────

  function token() {
    return localStorage.getItem('token') || '';
  }

  function authHeaders() {
    return { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` };
  }

  function fmtDate(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function escHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  function renderCard(ann) {
    const pm      = PRIORITY_META[ann.priority] || PRIORITY_META.normal;
    const icon    = ORG_TYPE_ICON[ann.org_type] || ORG_TYPE_ICON[ann.source_type] || '📢';
    const orgName = escHtml(ann.org_name || ann.source_type || 'EduPortal');
    const orgType = escHtml(ann.org_type || ann.source_type || '');
    const stateTag = ann.state
      ? `<span class="tag tag-muted">${escHtml(ann.state)}</span>`
      : `<span class="tag tag-muted">National</span>`;
    const priorityTag = pm.label
      ? `<span class="tag ${pm.cls}">${pm.label}</span>`
      : '';
    const audienceTag = ann.audience
      ? `<span class="tag">${escHtml(ann.audience)}</span>`
      : '';
    const expiryNote = ann.expires_at
      ? `<span class="deadline-badge">Expires ${fmtDate(ann.expires_at)}</span>`
      : '';
    const attachBtn = ann.attachment_path
      ? `<a href="${escHtml(ann.attachment_path)}" target="_blank" rel="noopener" class="card-link">📎 Download attachment</a>`
      : ann.attachment_url
      ? `<a href="${escHtml(ann.attachment_url)}" target="_blank" rel="noopener" class="card-link">View attachment ↗</a>`
      : '';

    return `
      <article class="ann-list-item">
        <div class="ann-list-meta">
          <span class="ann-org-icon" title="${orgType}" style="font-size:1.6rem;line-height:1">${icon}</span>
          ${stateTag}
          ${priorityTag}
        </div>
        <div class="ann-list-body">
          <h3 class="ann-list-title">${escHtml(ann.title)}</h3>
          <p class="ann-list-preview">${escHtml(ann.body)}</p>
          <div class="ann-list-footer">
            <div style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:center">
              <span class="org" style="font-size:.82rem">${orgName}</span>
              ${audienceTag}
            </div>
            <div style="display:flex;gap:.75rem;align-items:center;flex-wrap:wrap">
              ${expiryNote}
              ${attachBtn}
              <span class="u-text-muted-xs">${fmtDate(ann.created_at)}</span>
            </div>
          </div>
        </div>
      </article>`;
  }

  // ── Fetch & display ────────────────────────────────────────────────────────

  function buildQuery(formData) {
    const p = new URLSearchParams();
    for (const [k, v] of formData.entries()) {
      if (v) p.set(k === 'source' ? 'source' : k, v);
    }
    return p.toString();
  }

  function renderUrgentBanner(items) {
    const strip = document.getElementById('urgent-banner-strip');
    if (!strip) return;
    const urgent = items.filter(a => a.priority === 'urgent');
    if (!urgent.length) { strip.classList.add('hidden'); return; }
    strip.classList.remove('hidden');
    strip.innerHTML = urgent.map(a => `
      <div style="display:flex;align-items:flex-start;gap:.85rem;padding:1rem 1.3rem;
        background:linear-gradient(135deg,rgba(192,57,43,0.1),rgba(192,57,43,0.05));
        border:1.5px solid rgba(192,57,43,0.25);border-radius:14px;margin-bottom:.6rem">
        <span style="font-size:1.4rem;flex-shrink:0">🚨</span>
        <div style="flex:1;min-width:0">
          <p style="margin:0 0 .2rem;font-weight:800;color:#c0392b;font-size:.95rem">${escHtml(a.title)}</p>
          <p style="margin:0;font-size:.84rem;color:#888">${escHtml(a.body).slice(0,200)}${a.body.length>200?'…':''}</p>
          <p style="margin:.3rem 0 0;font-size:.76rem;color:#aaa">
            ${escHtml(a.org_name || a.source_type || 'EduPortal')}
            ${a.expires_at ? ' · Expires ' + fmtDate(a.expires_at) : ''}
          </p>
        </div>
      </div>`).join('');
  }

  async function loadAnnouncements(qs) {
    const el = document.getElementById('announcements-results');
    if (!el) return;
    el.innerHTML = '<p class="loading-text">Loading…</p>';
    try {
      const res  = await fetch(`/api/announcements?${qs || ''}`);
      const data = await res.json();
      const items = data.items || [];
      renderUrgentBanner(items);
      if (!items.length) {
        el.innerHTML = '<p class="empty-text">No announcements found.</p>';
        return;
      }
      el.innerHTML = items.map(renderCard).join('');
    } catch {
      el.innerHTML = '<p class="empty-text">Failed to load announcements.</p>';
    }
  }

  // ── Post form ──────────────────────────────────────────────────────────────

  async function handlePost(e) {
    e.preventDefault();
    const form = e.target;
    const msg  = document.getElementById('post-ann-message');
    const btn  = form.querySelector('button[type="submit"]');
    const fd   = new FormData(form);

    const payload = {
      title:          fd.get('title'),
      body:           fd.get('body'),
      audience:       fd.get('audience'),
      org_type:       fd.get('org_type'),
      org_name:       fd.get('org_name') || undefined,
      priority:       fd.get('priority'),
      state:          fd.get('state') || undefined,
      expires_at:     fd.get('expires_at') || undefined,
      attachment_url: fd.get('attachment_url') || undefined,
    };
    const attachFile = fd.get('attachment_file');

    btn.disabled = true;
    msg.textContent = '';
    msg.className = 'status-message';

    try {
      const res  = await fetch('/api/announcements', {
        method:  'POST',
        headers: authHeaders(),
        body:    JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        msg.textContent = data.error || 'Submission failed.';
        msg.classList.add('is-error');
      } else {
        // Upload PDF attachment if one was selected
        if (attachFile && attachFile.size > 0) {
          const fileFd = new FormData();
          fileFd.append('file', attachFile);
          try {
            const uploadRes = await fetch(`/api/announcements/${data.id}/upload`, {
              method: 'POST',
              headers: { Authorization: `Bearer ${token()}` },
              body: fileFd,
            });
            if (!uploadRes.ok) {
              const uploadErr = await uploadRes.json().catch(() => ({}));
              msg.textContent = `Submitted, but file upload failed: ${uploadErr.error || 'unknown error'}`;
              msg.classList.add('is-error');
              return;
            }
          } catch {
            msg.textContent = 'Submitted, but file upload failed (network error).';
            msg.classList.add('is-error');
            return;
          }
        }
        msg.textContent = 'Submitted for review. It will appear once approved.';
        msg.classList.add('is-success');
        form.reset();
        loadAnnouncements('');
      }
    } catch {
      msg.textContent = 'Network error. Please try again.';
      msg.classList.add('is-error');
    } finally {
      btn.disabled = false;
    }
  }

  // ── Init ───────────────────────────────────────────────────────────────────

  function init() {
    // Show post form for authorised roles
    const stored = localStorage.getItem('user');
    if (stored) {
      try {
        const user = JSON.parse(stored);
        if (PUBLISHER_ROLES.has(user.role)) {
          const sec = document.getElementById('post-announcement-section');
          if (sec) sec.classList.remove('hidden');

          // Pre-select org_type for school_admin / ngo_officer
          const orgTypeSelect = document.getElementById('post-org-type');
          if (orgTypeSelect) {
            if (user.role === 'school_admin') orgTypeSelect.value = 'School';
            if (user.role === 'ngo_officer')  orgTypeSelect.value = 'NGO';
          }
        }
      } catch { /* ignore */ }
    }

    // Filter form
    const filterForm = document.getElementById('announcements-filter-form');
    if (filterForm) {
      filterForm.addEventListener('submit', (e) => {
        e.preventDefault();
        loadAnnouncements(buildQuery(new FormData(filterForm)));
      });
    }

    // Post form
    const postForm = document.getElementById('post-announcement-form');
    if (postForm) postForm.addEventListener('submit', handlePost);

    // Initial load
    loadAnnouncements('');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
