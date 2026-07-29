/* announcements.js — EduPortal South Sudan */
(function () {
  'use strict';

  const PRIORITY_META = {
    urgent: { label: 'Urgent',  cls: 'ann-priority-urgent' },
    high:   { label: 'High',    cls: 'ann-priority-high'   },
    normal: { label: '',        cls: ''                     },
  };

  const ORG_TYPE_ICON = EP.ORG_TYPE_ICON;

  // Helpers

  const authHeaders = EP.authHeaders;
  const fmtDate = EP.fmtDate;
  const escHtml = EP.esc;

  let currentItems = [];

  // Render

  function renderCard(ann) {
    const pm      = PRIORITY_META[ann.priority] || PRIORITY_META.normal;
    const icon    = ORG_TYPE_ICON[ann.org_type] || ORG_TYPE_ICON[ann.source_type] || 'megaphone';
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
      ? `<a href="${escHtml(ann.attachment_path)}" target="_blank" rel="noopener" class="card-link"><i data-lucide="paperclip" width="14" height="14"></i> Download attachment</a>`
      : ann.attachment_url
      ? `<a href="${escHtml(ann.attachment_url)}" target="_blank" rel="noopener" class="card-link"><i data-lucide="external-link" width="14" height="14"></i> View attachment</a>`
      : '';

    return `
      <article class="ann-list-item">
        <div class="ann-list-meta">
          <i class="ann-org-icon" data-lucide="${icon}" title="${orgType}" width="26" height="26"></i>
          ${stateTag}
          ${priorityTag}
        </div>
        <div class="ann-list-body">
          <h3 class="ann-list-title">${escHtml(ann.title)}</h3>
          <p class="ann-list-preview">${escHtml(ann.body)}</p>
          <div class="ann-list-footer">
            <div class="ann-list-footer-left">
              <span class="org">${orgName}</span>
              ${audienceTag}
            </div>
            <div class="ann-list-footer-right">
              ${expiryNote}
              <button type="button" class="card-link ann-view-btn" data-id="${ann.id}">
                <i data-lucide="eye" width="14" height="14"></i> View full details
              </button>
              ${attachBtn}
              <span class="u-text-muted-xs">${fmtDate(ann.created_at)}</span>
            </div>
          </div>
        </div>
      </article>`;
  }

  // Full-detail modal — built once, populated per announcement.

  function ensureModal() {
    return EP.createModal({
      id: 'ann-modal-overlay',
      onClose: closeModal,
      bodyHtml: `
        <div class="ann-modal" role="dialog" aria-modal="true" aria-labelledby="ann-modal-title">
          <button type="button" class="ann-modal-close" aria-label="Close">
            <svg viewBox="0 0 16 16" fill="none" width="16" height="16"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          </button>
          <div class="ann-modal-meta" id="ann-modal-meta"></div>
          <h2 class="ann-modal-title" id="ann-modal-title"></h2>
          <div class="ann-modal-body" id="ann-modal-body"></div>
          <div class="ann-modal-footer" id="ann-modal-footer"></div>
        </div>`,
    });
  }

  function closeModal() {
    const modal = document.getElementById('ann-modal-overlay');
    if (modal) modal.classList.add('hidden');
  }

  function openModal(ann) {
    const modal = ensureModal();
    const pm = PRIORITY_META[ann.priority] || PRIORITY_META.normal;
    const orgName = escHtml(ann.org_name || ann.source_type || 'EduPortal');
    const orgType = escHtml(ann.org_type || ann.source_type || '');
    modal.querySelector('#ann-modal-meta').innerHTML = `
      <span class="tag">${orgType || 'EduPortal'}</span>
      <span class="tag tag-muted">${escHtml(ann.state || 'National')}</span>
      ${pm.label ? `<span class="tag ${pm.cls}">${pm.label}</span>` : ''}
      ${ann.audience ? `<span class="tag">${escHtml(ann.audience)}</span>` : ''}`;
    modal.querySelector('#ann-modal-title').textContent = ann.title;
    modal.querySelector('#ann-modal-body').innerHTML = EP.paragraphs(ann.body);
    const attach = ann.attachment_path
      ? `<a href="${escHtml(ann.attachment_path)}" target="_blank" rel="noopener" class="card-button u-card-button-link"><i data-lucide="paperclip" width="14" height="14"></i> Download attachment</a>`
      : ann.attachment_url
      ? `<a href="${escHtml(ann.attachment_url)}" target="_blank" rel="noopener" class="card-button u-card-button-link"><i data-lucide="external-link" width="14" height="14"></i> View attachment</a>`
      : '';
    modal.querySelector('#ann-modal-footer').innerHTML = `
      <div>
        <strong>${orgName}</strong>
        <span class="u-text-muted-xs">Posted ${fmtDate(ann.created_at)}${ann.expires_at ? ' · Expires ' + fmtDate(ann.expires_at) : ''}</span>
      </div>
      ${attach}`;
    modal.classList.remove('hidden');
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
  }

  // Fetch & display

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
      <div class="urgent-banner-item">
        <i data-lucide="triangle-alert" width="22" height="22" class="urgent-banner-item__icon"></i>
        <div class="urgent-banner-item__body">
          <p class="urgent-banner-item__title">${escHtml(a.title)}</p>
          <p class="urgent-banner-item__desc">${escHtml(a.body).slice(0,200)}${a.body.length>200?'…':''}</p>
          <p class="urgent-banner-item__meta">
            ${escHtml(a.org_name || a.source_type || 'EduPortal')}
            ${a.expires_at ? ' · Expires ' + fmtDate(a.expires_at) : ''}
          </p>
        </div>
      </div>`).join('');
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
  }

  async function loadAnnouncements(qs) {
    const el = document.getElementById('announcements-results');
    if (!el) return;
    el.innerHTML = '<p class="loading-text">Loading…</p>';
    try {
      const res  = await fetch(`/api/announcements?${qs || ''}`);
      const data = await res.json();
      const items = data.items || [];
      currentItems = items;
      renderUrgentBanner(items);
      if (!items.length) {
        el.innerHTML = '<p class="empty-text">No announcements found.</p>';
        return;
      }
      el.innerHTML = items.map(renderCard).join('');
      el.querySelectorAll('.ann-view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const ann = currentItems.find(a => String(a.id) === btn.dataset.id);
          if (ann) openModal(ann);
        });
      });
      if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
      items.forEach(a => fetch(`/api/announcements/${a.id}/view`, { method: 'POST' }).catch(() => {}));
    } catch {
      el.innerHTML = '<p class="empty-text">Failed to load announcements.</p>';
    }
  }

  // Post form

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
          try {
            await EP.uploadFile(`/api/announcements/${data.id}/upload`, 'file', attachFile);
          } catch (uploadErr) {
            msg.textContent = `Submitted, but file upload failed: ${uploadErr.message || 'unknown error'}`;
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

  // Init

  function init() {
    // Only the platform admin posts from this page — school_admin,
    // ngo_officer, and org_publisher each already have a "Post an
    // announcement" form on their own dashboard, so showing a second one
    // here would just be a duplicate, disconnected place to do the same
    // thing.
    const stored = localStorage.getItem('eduportal_user');
    if (stored) {
      try {
        const user = JSON.parse(stored);
        if (user.role === 'admin') {
          const sec = document.getElementById('post-announcement-section');
          if (sec) sec.classList.remove('hidden');
        }
      } catch { /* ignore */ }
    }

    // Filter form
    const filterForm = document.getElementById('announcements-filter-form');
    if (filterForm) {
      const applyFilters = () => loadAnnouncements(buildQuery(new FormData(filterForm)));
      filterForm.addEventListener('submit', (e) => {
        e.preventDefault();
        applyFilters();
      });
      // A dropdown that does nothing until "Search" is clicked reads as
      // broken — apply it the moment it changes.
      filterForm.querySelectorAll('select').forEach(sel => sel.addEventListener('change', applyFilters));
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
