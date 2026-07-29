(function () {
  'use strict';

  var nav = document.querySelector('nav.sidebar');
  if (!nav || nav.children.length) return;

  var page = document.body.dataset.page || '';

  var user = null;
  try { user = JSON.parse(localStorage.getItem('eduportal_user') || 'null'); } catch (e) { user = null; }
  var role = user ? (user.role || '') : '';

  // Same greeting on every page — set once here instead of per-page init().
  var greetEl = document.getElementById('page-greeting');
  if (greetEl && user && user.name) {
    greetEl.textContent = 'Welcome back, ' + user.name.split(' ')[0] + '.';
  }

  // Icons (Lucide via data-lucide attributes)
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
    'org-dashboard':    'landmark',
    logout:           'log-out',
    signin:           'log-in',
  };

  // Every account role that browses/applies/bookmarks as a platform user.
  // The platform admin is deliberately NOT in this list: admin's job is
  // running the platform (onboarding schools/organisations, moderating
  // content, managing accounts — all inside the Admin Panel) rather than
  // using it as a student/parent/school/NGO would. An item's `roles` array
  // is the complete, exhaustive list of who sees it — there is no
  // "admin sees everything" bypass in the filter below.
  var EVERYONE = ['student','parent','teacher','school_admin','ngo_officer','org_publisher'];

  var groups = [
    { label: 'START HERE', items: [
      { href: '/dashboard',   label: 'Dashboard',            key: 'dashboard',     roles: EVERYONE },
      { href: '/directory',   label: 'Explore Institutions', key: 'directory',     roles: EVERYONE },
    ]},
    { label: 'LEARN', items: [
      { href: '/materials',   label: 'Learning Resources',   key: 'materials',     roles: ['student','parent','teacher','school_admin'] },
    ]},
    { label: 'APPLY', items: [
      // Scholarship search isn't a core need for teachers, and school_admin
      // sees NGO-posted scholarships as out of scope for their role.
      { href: '/opportunities',   label: 'Scholarships',     key: 'scholarships',  roles: ['student','parent','ngo_officer','org_publisher'] },
      { href: '/announcements',   label: 'Announcements',    key: 'announcements', roles: EVERYONE },
    ]},
    { label: 'MANAGE', items: [
      { href: '/school-dashboard', label: 'School Dashboard',        key: 'school-dashboard', roles: ['school_admin'] },
      { href: '/ngo-dashboard',    label: 'NGO Dashboard',           key: 'ngo-dashboard',    roles: ['ngo_officer'] },
      { href: '/org-dashboard',    label: 'Organization Dashboard',  key: 'org-dashboard',    roles: ['org_publisher'] },
    ]},
    { label: 'ACCOUNT', items: [
      { href: '/my-applications', label: 'My Applications',  key: 'applications',  roles: ['student','parent'] },
      // Parent accounts can search and view listings but not save bookmarks,
      // so a saved-items page has nothing to show them.
      { href: '/bookmarks',       label: 'My Bookmarks',     key: 'bookmarks',     roles: ['student','teacher','school_admin','ngo_officer','org_publisher'] },
      { href: '/profile',         label: 'My Profile',       key: 'profile',       roles: EVERYONE.concat(['admin']) },
      { href: '/settings',        label: 'Settings',         key: 'settings',      roles: EVERYONE.concat(['admin']) },
    ]},
  ];

  if (role === 'admin') {
    groups.push({ label: 'ADMINISTRATION', items: [
      { href: '/admin', label: 'Admin Panel', key: 'admin', roles: ['admin'] },
    ]});
  }

  // Helpers
  var esc = EP.esc;

  function icon(key) {
    var name = ICON_NAMES[key] || 'circle';
    return '<span class="nav-icon" aria-hidden="true"><i data-lucide="' + name + '" width="15" height="15"></i></span>';
  }

  var initials = user ? (user.name || '').split(' ').map(function(w) { return w[0] || ''; }).join('').slice(0,2).toUpperCase() : '';
  var roleLabel = user ? (user.role || '').replace(/_/g, ' ') : '';

  // Shared by the sidebar identity block and the account-menu trigger — an
  // <img> with an inline onerror fallback to text initials if the avatar
  // URL 404s (e.g. after the underlying file was deleted).
  function avatarImgHTML() {
    return '<img src="' + esc(user.avatar) + '" alt="" class="avatar-photo" onerror="this.style.display=\'none\';this.insertAdjacentHTML(\'afterend\',\'<span class=\\\'avatar-initials-fallback\\\'>' + esc(initials) + '</span>\');">';
  }

  // Brand logo
  var LOGO_SVG = '<svg viewBox="0 0 24 24" fill="none" width="18" height="18" aria-hidden="true"><path d="M3 11l9-6 9 6-9 6-9-6Z" stroke="white" stroke-width="1.8" stroke-linejoin="round"/><path d="M7 13v5l5 3 5-3v-5" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  // Build HTML
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
    var sidebarAvatarContent = user && user.avatar ? avatarImgHTML() : esc(initials);
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
      return !item.roles || item.roles.indexOf(role) !== -1;
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

  html += '</div>'; // close .sidebar-scroll — .sidebar-bottom below is a sibling, not nested inside it

  // Bottom: logout / sign in
  html += '<div class="sidebar-bottom">';
  if (user) {
    html += '<a class="logout-link" href="#" id="sidebar-logout-btn"><span class="nav-icon" aria-hidden="true"><i data-lucide="log-out" width="15" height="15"></i></span>Log Out</a>';
  } else {
    html += '<a href="/"><span class="nav-icon" aria-hidden="true"><i data-lucide="log-in" width="15" height="15"></i></span>Sign In</a>';
  }
  html += '</div>'; // close .sidebar-bottom

  // Shared by the sidebar logout link and the account-menu logout button.
  function doLogout() {
    var refreshToken = localStorage.getItem('eduportal_refresh_token');
    if (refreshToken) {
      fetch('/api/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refreshToken }) }).catch(function() {});
    }
    localStorage.removeItem('eduportal_token');
    localStorage.removeItem('eduportal_refresh_token');
    localStorage.removeItem('eduportal_user');
    window.location.href = '/login';
  }

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
      doLogout();
    });
  }

  // Mobile hamburger
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

  // On mobile, the page title (the first child of .top-banner — an eyebrow +
  // h1 block, consistent across every dashboard/app page) moves out of the
  // fixed top bar and into the top of the scrollable content, so the top bar
  // stays a single constant-height row (hamburger / identity / bell / avatar)
  // regardless of how long a page's title is. Desktop is untouched — the
  // title stays put in .top-banner as it always has.
  var topBanner = document.querySelector('.top-banner');
  var mainContent = document.querySelector('.main-content');
  var titleBlock = topBanner ? topBanner.firstElementChild : null;
  if (titleBlock && titleBlock.classList.contains('top-banner-actions')) {
    titleBlock = null; // page has no title block, just actions — nothing to move
  }

  function syncTitlePlacement() {
    if (!titleBlock || !mainContent) return;
    if (isMobile()) {
      if (titleBlock.parentElement !== mainContent) {
        titleBlock.classList.add('mobile-relocated-title');
        mainContent.insertBefore(titleBlock, mainContent.firstChild);
      }
    } else if (titleBlock.parentElement === mainContent) {
      titleBlock.classList.remove('mobile-relocated-title');
      topBanner.insertBefore(titleBlock, topBanner.firstChild);
    }
  }

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
    syncTitlePlacement();
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

  // Top-bar: notification bell + account menu
  var topActions = document.querySelector('.top-banner-actions, .top-actions');
  if (!topActions || !user || topActions.querySelector('[data-account-menu]')) return;

  // Mobile-only brand + name block, left-aligned in the top bar next to the
  // hamburger. .top-banner is flex with justify-content:space-between, so
  // putting this as .top-banner-actions' sibling (not inside it) pushes the
  // bell/avatar cluster to the right automatically, balancing the bar —
  // on desktop this same identity already lives in the sidebar, so it's
  // hidden there via CSS.
  if (topBanner) {
    var mobileBrand = document.createElement('div');
    mobileBrand.className = 'mobile-brand-block';
    mobileBrand.innerHTML =
      '<strong>EduPortal South Sudan</strong><span>' + esc(user.name) + '</span>';
    topBanner.insertBefore(mobileBrand, topBanner.firstChild);
  }

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
    ? avatarImgHTML()
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

  menuWrap.querySelector('[data-action="logout"]').addEventListener('click', doLogout);

  document.addEventListener('click', function(e) {
    if (!menuWrap.contains(e.target)) { acctMenu.classList.remove('open'); acctBtn.setAttribute('aria-expanded','false'); }
    if (!bellWrap.contains(e.target)) { bellMenu.classList.remove('open'); bellBtn.setAttribute('aria-expanded','false'); }
  });

  // Load notifications
  var token = localStorage.getItem('eduportal_token');

  function setBadge(count) {
    if (count > 0) {
      bellBadge.textContent = String(count);
      bellBadge.classList.remove('hidden');
      bellBtn.setAttribute('aria-label', 'Notifications (' + count + ' unread)');
    } else {
      bellBadge.classList.add('hidden');
      bellBtn.setAttribute('aria-label', 'Notifications');
    }
  }

  // Where clicking a notification should take you — ref_type is set
  // server-side (notifications.ref_type, or synthesized for deadline/
  // announcement items); types with no mapping here just mark as read.
  var NOTIF_LINKS = {
    application: '/my-applications',
    scholarship: '/opportunities',
    announcement: '/announcements',
  };

  function renderNotifications(items) {
    // A persisted notification that's already read has nothing left to tell
    // you — drop it from the tray entirely instead of leaving it listed in
    // a de-emphasized state forever. Ephemeral reminders (deadlines, recent
    // announcements) aren't real notification records and always show.
    var visible = items.filter(function(n) { return !n.persisted || !n.read; });
    bellList.innerHTML = visible.length
      ? visible.map(function(n) {
          var attrs = n.persisted ? ' data-notif-id="' + n.id + '"' : '';
          var href = NOTIF_LINKS[n.ref_type];
          if (href) attrs += ' data-notif-href="' + href + '"';
          var pressable = href ? ' bell-item-pressable' : '';
          return '<div class="bell-item' + (n.persisted ? ' bell-item-unread' : '') + pressable + '"' + attrs + '>' +
            '<strong>' + esc(n.title || '') + '</strong><span>' + esc(n.body || '') + '</span></div>';
        }).join('')
      : '<p class="top-notification-empty">No new notifications.</p>';
  }

  bellList.addEventListener('click', function(e) {
    var item = e.target.closest('.bell-item');
    if (!item) return;
    var href = item.dataset.notifHref;
    var id = item.dataset.notifId;
    if (id) {
      // Optimistic: drop it immediately rather than waiting on the network
      // round-trip, then resync the unread badge once the call lands.
      item.remove();
      if (!bellList.children.length) {
        bellList.innerHTML = '<p class="top-notification-empty">No new notifications.</p>';
      }
      fetch('/api/notifications/' + id + '/read', {
        method: 'POST', headers: { 'Authorization': 'Bearer ' + token },
      }).then(loadNotifications).catch(function() {});
    }
    if (href) window.location.href = href;
  });

  function loadNotifications() {
    fetch('/api/notifications', { headers: { 'Authorization': 'Bearer ' + token } })
      .then(function(r) {
        // A 2-hour access token expiring mid-session breaks this otherwise —
        // this raw fetch (unlike main.js's api() wrapper) has no built-in
        // retry, so the bell would just silently stop updating until the
        // page is reloaded.
        if (r.status === 401) {
          return EP.refreshSession().then(function(ok) {
            if (!ok) return { items: [], count: 0 };
            token = EP.token();
            return fetch('/api/notifications', { headers: { 'Authorization': 'Bearer ' + token } })
              .then(function(r2) { return r2.ok ? r2.json() : { items: [], count: 0 }; });
          });
        }
        return r.ok ? r.json() : { items: [], count: 0 };
      })
      .then(function(data) {
        setBadge((data && data.count) || 0);
        renderNotifications((data && Array.isArray(data.items)) ? data.items : []);
      })
      .catch(function() {
        bellList.innerHTML = '<p class="top-notification-empty">No notifications available.</p>';
      });
  }

  if (token) {
    loadNotifications();
    // Live updates: refresh the bell the moment a new notification arrives
    if (window.EventSource) {
      var stream = null;
      var reconnectingStream = false;
      function openNotificationStream() {
        stream = new EventSource('/api/notifications/stream?token=' + encodeURIComponent(token));
        stream.onmessage = function() { loadNotifications(); };
        stream.onerror = function() {
          // The browser's own auto-reconnect just keeps retrying with the
          // same (now expired) token forever once the 2-hour access token
          // lapses mid-session — refresh it and open a fresh connection
          // instead of leaving live updates silently dead for the rest of
          // the tab's life.
          if (reconnectingStream) return;
          reconnectingStream = true;
          stream.close();
          EP.refreshSession().then(function(ok) {
            reconnectingStream = false;
            if (ok) {
              token = EP.token();
              openNotificationStream();
            }
          });
        };
      }
      openNotificationStream();
      window.addEventListener('beforeunload', function() { if (stream) stream.close(); });
    }
  } else {
    bellList.innerHTML = '<p class="top-notification-empty">Sign in to see notifications.</p>';
  }

})();
