(function () {
  'use strict';

  var nav = document.querySelector('nav.sidebar');
  if (!nav || nav.children.length) return;

  var page = document.body.dataset.page || '';

  var user = null;
  try { user = JSON.parse(localStorage.getItem('eduportal_user') || 'null'); } catch (e) { user = null; }
  var role = user ? (user.role || '') : '';

  // ── Icons (Lucide via data-lucide attributes) ────────────────────────────
  var ICON_NAMES = {
    dashboard:     'layout-dashboard',
    directory:     'building-2',
    materials:     'book-open',
    scholarships:  'graduation-cap',
    announcements: 'megaphone',
    applications:  'clipboard-check',
    bookmarks:     'bookmark',
    profile:       'user-circle',
    settings:      'settings',
    admin:            'shield-check',
    'school-dashboard': 'building-2',
    'ngo-dashboard':    'heart-handshake',
    logout:           'log-out',
    signin:           'log-in',
  };

  // ── Nav structure with role permissions ───────────────────────────────────
  var ALL  = ['student','parent','teacher','school_admin','ngo_officer','admin'];
  var MOST = ['student','parent','teacher','school_admin','ngo_officer','admin'];

  var groups = [
    { label: 'START HERE', items: [
      { href: '/dashboard',   label: 'Dashboard',            key: 'dashboard',     roles: ALL },
      { href: '/directory',   label: 'Explore Institutions', key: 'directory',     roles: MOST },
    ]},
    { label: 'LEARN', items: [
      { href: '/materials',   label: 'Learning Resources',   key: 'materials',     roles: ['student','parent','teacher','school_admin','admin'] },
    ]},
    { label: 'APPLY', items: [
      { href: '/opportunities',   label: 'Scholarships',     key: 'scholarships',  roles: MOST },
      { href: '/announcements',   label: 'Announcements',    key: 'announcements', roles: MOST },
    ]},
    { label: 'MANAGE', items: [
      { href: '/school-dashboard', label: 'School Dashboard', key: 'school-dashboard', roles: ['school_admin'] },
      { href: '/ngo-dashboard',    label: 'NGO Dashboard',    key: 'ngo-dashboard',    roles: ['ngo_officer'] },
    ]},
    { label: 'ACCOUNT', items: [
      { href: '/my-applications', label: 'My Applications',  key: 'applications',  roles: ['student','parent'] },
      { href: '/bookmarks',       label: 'My Bookmarks',     key: 'bookmarks',     roles: ['student','parent','teacher','school_admin','ngo_officer'] },
      { href: '/profile',         label: 'My Profile',       key: 'profile',       roles: ALL },
      { href: '/settings',        label: 'Settings',         key: 'settings',      roles: ALL },
    ]},
  ];

  if (role === 'admin') {
    groups.push({ label: 'ADMIN', items: [
      { href: '/admin', label: 'Admin Panel', key: 'admin', roles: ['admin'] },
    ]});
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function icon(key) {
    var name = ICON_NAMES[key] || 'circle';
    return '<span class="nav-icon" aria-hidden="true"><i data-lucide="' + name + '" width="15" height="15"></i></span>';
  }

  var initials = user ? user.name.split(' ').map(function(w) { return w[0] || ''; }).join('').slice(0,2).toUpperCase() : '';
  var roleLabel = user ? user.role.replace(/_/g, ' ') : '';

  // Avatar HTML helper — shows photo if stored, otherwise initials
  function avatarHtml(sizeClass, initialsStr) {
    var av = user && user.avatar;
    if (av) {
      return '<img src="' + esc(av) + '" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block" onerror="this.style.display=\'none\';this.nextSibling.style.display=\'flex\'">' +
             '<span style="display:none;width:100%;height:100%;align-items:center;justify-content:center;font-size:inherit;font-weight:800">' + esc(initialsStr) + '</span>';
    }
    return esc(initialsStr);
  }

  // Brand logo
  var LOGO_SVG = '<svg viewBox="0 0 24 24" fill="none" width="18" height="18" aria-hidden="true"><path d="M3 11l9-6 9 6-9 6-9-6Z" stroke="white" stroke-width="1.8" stroke-linejoin="round"/><path d="M7 13v5l5 3 5-3v-5" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  // ── Build HTML ────────────────────────────────────────────────────────────
  var html = '';

  // Brand + account combined into one compact static header block
  html += '<div class="sidebar-static-header">';
  html += '<a class="sidebar-brand sidebar-brand-combined" href="/dashboard">';
  html += '<div class="sidebar-brand-top">';
  html += '<div class="sidebar-brand-icon">' + LOGO_SVG + '</div>';
  html += '<div><strong>EduPortal South Sudan</strong></div>';
  html += '</div>';
  if (user) {
    html += '<div class="sidebar-account sidebar-account-compact">';
    var sidebarAvatarContent = user && user.avatar
      ? '<img src="' + esc(user.avatar) + '" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block" onerror="this.style.display=\'none\';this.insertAdjacentHTML(\'afterend\',\'<span style=\\\'display:flex;align-items:center;justify-content:center;width:100%;height:100%;font-size:inherit;font-weight:800\\\'>' + esc(initials) + '</span>\');">'
      : esc(initials);
    html += '<div class="sidebar-avatar sidebar-avatar-sm">' + sidebarAvatarContent + '</div>';
    html += '<div class="sidebar-account-content">';
    html += '<strong class="sidebar-account-name">' + esc(user.name) + '</strong>';
    html += '<span>' + esc(roleLabel) + '</span>';
    html += '</div></div>';
  }
  html += '</a>';
  html += '</div>';

  html += '<div class="sidebar-scroll">';

  // Nav groups
  groups.forEach(function(group) {
    var visibleItems = group.items.filter(function(item) {
      return !item.roles || item.roles.indexOf(role) !== -1 || role === 'admin';
    });
    if (!visibleItems.length) return;

    html += '<div class="nav-group">';
    html += '<p class="nav-label">' + esc(group.label) + '</p>';

    visibleItems.forEach(function(item) {
      var isActive = item.href === ('/' + page) || item.key === page;
      var activeClass = isActive ? ' active' : '';
      var ariaCurrent = isActive ? ' aria-current="page"' : '';
      html += '<a class="' + activeClass.trim() + '" href="' + esc(item.href) + '"' + ariaCurrent + '>';
      html += icon(item.key);
      html += esc(item.label);
      html += '</a>';
    });

    html += '</div>';
  });

  // Bottom: logout / sign in
  html += '<div class="sidebar-bottom">';
  if (user) {
    html += '<a class="logout-link" href="#" id="sidebar-logout-btn"><span class="nav-icon" aria-hidden="true"><i data-lucide="log-out" width="15" height="15"></i></span>Log Out</a>';
  } else {
    html += '<a href="/"><span class="nav-icon" aria-hidden="true"><i data-lucide="log-in" width="15" height="15"></i></span>Sign In</a>';
  }
  html += '</div>';
  html += '</div>';

  nav.innerHTML = html;

  // Render Lucide icons inside sidebar — wait for library if needed
  function renderIcons() {
    if (window.lucide && window.lucide.createIcons) {
      window.lucide.createIcons();
    }
  }
  if (window.lucide) {
    renderIcons();
  } else {
    document.addEventListener('lucide:ready', renderIcons);
    // fallback: poll briefly
    var _t = setInterval(function() {
      if (window.lucide) { clearInterval(_t); renderIcons(); }
    }, 50);
    setTimeout(function() { clearInterval(_t); }, 3000);
  }

  // Logout handler
  var logoutBtn = document.getElementById('sidebar-logout-btn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', function(e) {
      e.preventDefault();
      localStorage.removeItem('eduportal_token');
      localStorage.removeItem('eduportal_user');
      window.location.href = '/';
    });
  }

  // ── Mobile hamburger ──────────────────────────────────────────────────────
  nav.id = 'sidebar-nav';

  var overlay = document.createElement('div');
  overlay.className = 'sidebar-overlay';
  document.body.appendChild(overlay);

  var hamburger = document.createElement('button');
  hamburger.className = 'sidebar-hamburger';
  hamburger.setAttribute('aria-label', 'Open navigation menu');
  hamburger.setAttribute('aria-expanded', 'false');
  hamburger.setAttribute('aria-controls', 'sidebar-nav');
  hamburger.innerHTML = '<span class="ham-bar"></span><span class="ham-bar"></span><span class="ham-bar"></span>';
  document.body.appendChild(hamburger);

  function isMobile() { return window.innerWidth <= 980; }

  function syncHamburger() {
    if (isMobile()) {
      hamburger.style.display = 'flex';
      if (!nav.classList.contains('sidebar-open')) {
        nav.style.transform = 'translateX(-100%)';
      }
    } else {
      hamburger.style.display = 'none';
      nav.style.transform = '';
      overlay.classList.remove('sidebar-overlay-visible');
      document.body.classList.remove('sidebar-body-lock');
    }
  }
  syncHamburger();
  window.addEventListener('resize', syncHamburger);

  function openSidebar() {
    nav.style.transform = 'translateX(0)';
    nav.classList.add('sidebar-open');
    overlay.classList.add('sidebar-overlay-visible');
    hamburger.classList.add('is-open');
    hamburger.setAttribute('aria-expanded', 'true');
    document.body.classList.add('sidebar-body-lock');
  }

  function closeSidebar() {
    nav.style.transform = isMobile() ? 'translateX(-100%)' : '';
    nav.classList.remove('sidebar-open');
    overlay.classList.remove('sidebar-overlay-visible');
    hamburger.classList.remove('is-open');
    hamburger.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('sidebar-body-lock');
  }

  hamburger.addEventListener('click', function() {
    if (nav.classList.contains('sidebar-open')) { closeSidebar(); } else { openSidebar(); }
  });
  overlay.addEventListener('click', closeSidebar);
  document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeSidebar(); });

  nav.querySelectorAll('a').forEach(function(link) {
    link.addEventListener('click', function() { if (isMobile()) closeSidebar(); });
  });

  // ── Top-bar: notification bell + account menu ─────────────────────────────
  var topActions = document.querySelector('.top-banner-actions, .top-actions');
  if (!topActions || !user || topActions.querySelector('[data-account-menu]')) return;

  // Notification bell
  var bellWrap = document.createElement('div');
  bellWrap.className = 'top-notification-wrapper';
  bellWrap.innerHTML = [
    '<button class="top-notification-trigger" type="button" aria-label="Notifications" aria-haspopup="menu" aria-expanded="false">',
    '<i data-lucide="bell" width="18" height="18" aria-hidden="true"></i>',
    '<span class="top-notification-badge hidden" aria-hidden="true"></span>',
    '</button>',
    '<div class="dropdown-menu top-notification-menu" role="menu">',
    '<p class="bell-heading">Notifications</p>',
    '<div class="top-notification-list"><p class="top-notification-empty">Loading\u2026</p></div>',
    '</div>',
  ].join('');

  // Replace placeholder with actual bell SVG
  var bellBtn = bellWrap.querySelector('.top-notification-trigger');
  bellBtn.innerHTML = [
    '<i data-lucide="bell" width="18" height="18" aria-hidden="true"></i>',
    '<span class="top-notification-badge hidden" aria-hidden="true"></span>',
  ].join('');
  topActions.appendChild(bellWrap);

  // Account menu
  var menuWrap = document.createElement('div');
  menuWrap.className = 'user-menu-wrapper';
  menuWrap.dataset.accountMenu = 'true';

  var avatarTriggerContent = user && user.avatar
    ? '<img src="' + esc(user.avatar) + '" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block" onerror="this.style.display=\'none\';this.insertAdjacentHTML(\'afterend\',\'<span style=\\\'display:flex;align-items:center;justify-content:center;width:100%;height:100%;font-size:inherit;font-weight:800\\\'>' + esc(initials) + '</span>\');">'
    : '<span class="account-trigger-initials" aria-hidden="true">' + esc(initials) + '</span>';

  var dropdownHTML = [
    '<button class="account-trigger" type="button" aria-label="Account menu" aria-haspopup="menu" aria-expanded="false">',
    avatarTriggerContent,
    '</button>',
    '<div class="dropdown-menu" role="menu">',
    '<div class="dropdown-user-info">',
    '<p class="dropdown-name">' + esc(user.name) + '</p>',
    '<p class="dropdown-email">' + esc(roleLabel) + '</p>',
    '</div>',
    '<div class="dropdown-section-label">Account</div>',
    '<a class="dropdown-item" href="/profile" role="menuitem"><i data-lucide="user" width="14" height="14"></i> My Profile</a>',
    '<a class="dropdown-item" href="/settings" role="menuitem"><i data-lucide="settings" width="14" height="14"></i> Settings</a>',
    '<div class="dropdown-divider"></div>',
    '<button class="dropdown-item logout" type="button" data-action="logout"><i data-lucide="log-out" width="14" height="14"></i> Log Out</button>',
    '</div>',
  ].join('');
  menuWrap.innerHTML = dropdownHTML;
  topActions.appendChild(menuWrap);
  // Re-render icons for dynamically added top-bar elements
  if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();

  // Bell toggle
  var bellMenu   = bellWrap.querySelector('.top-notification-menu');
  var bellBadge  = bellBtn.querySelector('.top-notification-badge');
  var bellList   = bellWrap.querySelector('.top-notification-list');

  bellBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    var open = bellMenu.classList.toggle('open');
    bellBtn.setAttribute('aria-expanded', String(open));
  });

  // Account menu toggle
  var acctBtn  = menuWrap.querySelector('.account-trigger');
  var acctMenu = menuWrap.querySelector('.dropdown-menu');

  acctBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    var open = acctMenu.classList.toggle('open');
    acctBtn.setAttribute('aria-expanded', String(open));
  });

  menuWrap.querySelector('[data-action="logout"]').addEventListener('click', function() {
    localStorage.removeItem('eduportal_token');
    localStorage.removeItem('eduportal_user');
    window.location.href = '/';
  });

  document.addEventListener('click', function(e) {
    if (!menuWrap.contains(e.target)) { acctMenu.classList.remove('open'); acctBtn.setAttribute('aria-expanded','false'); }
    if (!bellWrap.contains(e.target)) { bellMenu.classList.remove('open'); bellBtn.setAttribute('aria-expanded','false'); }
  });

  // Load notifications
  var token = localStorage.getItem('eduportal_token');
  if (token) {
    fetch('/api/notifications', { headers: { 'Authorization': 'Bearer ' + token } })
      .then(function(r) { return r.ok ? r.json() : { items: [], count: 0 }; })
      .then(function(data) {
        var cnt = (data && data.count) || 0;
        var items = (data && Array.isArray(data.items)) ? data.items : [];
        if (cnt > 0) {
          bellBadge.textContent = String(cnt);
          bellBadge.classList.remove('hidden');
          bellBtn.setAttribute('aria-label', 'Notifications (' + cnt + ' unread)');
        }
        bellList.innerHTML = items.length
          ? items.map(function(n) {
              return '<div class="bell-item"><strong>' + esc(n.title || '') + '</strong><span>' + esc(n.body || '') + '</span></div>';
            }).join('')
          : '<p class="top-notification-empty">No new notifications.</p>';
      })
      .catch(function() {
        bellList.innerHTML = '<p class="top-notification-empty">No notifications available.</p>';
      });
  } else {
    bellList.innerHTML = '<p class="top-notification-empty">Sign in to see notifications.</p>';
  }

})();
