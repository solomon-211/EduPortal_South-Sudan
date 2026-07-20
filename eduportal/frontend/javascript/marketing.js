(function () {
  'use strict';

  // ── Mobile nav toggle ─────────────────────────────────────────────────────
  const hamburger = document.getElementById('mkt-hamburger');
  const navLinks  = document.getElementById('mkt-nav-links');
  const navActions = document.getElementById('mkt-nav-actions');

  if (hamburger) {
    hamburger.addEventListener('click', () => {
      const open = hamburger.classList.toggle('open');
      if (navLinks)  navLinks.classList.toggle('open', open);
      if (navActions) navActions.classList.toggle('open', open);
      hamburger.setAttribute('aria-expanded', String(open));
    });
  }

  // Close menu when a link is clicked
  document.querySelectorAll('.mkt-nav__links a').forEach(link => {
    link.addEventListener('click', () => {
      hamburger?.classList.remove('open');
      navLinks?.classList.remove('open');
      navActions?.classList.remove('open');
    });
  });

  // ── Active nav link ───────────────────────────────────────────────────────
  const path = window.location.pathname;
  document.querySelectorAll('.mkt-nav__links a').forEach(a => {
    const href = a.getAttribute('href');
    if (href === path || (path === '/' && href === '/')) {
      a.classList.add('active');
    }
  });

  // ── Smooth scroll for anchor links ───────────────────────────────────────
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
      const target = document.querySelector(a.getAttribute('href'));
      if (target) { e.preventDefault(); target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    });
  });

  // ── Contact form ──────────────────────────────────────────────────────────
  const contactForm = document.getElementById('mkt-contact-form');
  const contactMsg  = document.getElementById('mkt-contact-msg');
  if (contactForm) {
    contactForm.addEventListener('submit', async e => {
      e.preventDefault();
      const btn = contactForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      btn.textContent = 'Sending…';
      const fd = Object.fromEntries(new FormData(contactForm));
      try {
        const res = await fetch('/api/contact', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(fd),
        });
        const data = await res.json();
        if (contactMsg) {
          contactMsg.textContent = data.message || 'Message sent. We will be in touch soon.';
          contactMsg.style.color = '#1a7a3c';
        }
        contactForm.reset();
      } catch {
        if (contactMsg) { contactMsg.textContent = 'Could not send message. Please email us directly.'; contactMsg.style.color = '#c0392b'; }
      } finally {
        btn.disabled = false;
        btn.textContent = 'Send Message';
      }
    });
  }

  // ── Partner form ──────────────────────────────────────────────────────────
  const partnerForm = document.getElementById('mkt-partner-form');
  const partnerMsg  = document.getElementById('mkt-partner-msg');
  if (partnerForm) {
    partnerForm.addEventListener('submit', async e => {
      e.preventDefault();
      const btn = partnerForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      btn.textContent = 'Submitting…';
      const fd = Object.fromEntries(new FormData(partnerForm));
      try {
        const res = await fetch('/api/partner-inquiry', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(fd),
        });
        const data = await res.json();
        if (partnerMsg) { partnerMsg.textContent = data.message || 'Enquiry received. We will contact you shortly.'; partnerMsg.style.color = '#1a7a3c'; }
        partnerForm.reset();
      } catch {
        if (partnerMsg) { partnerMsg.textContent = 'Could not submit. Please email us directly.'; partnerMsg.style.color = '#c0392b'; }
      } finally {
        btn.disabled = false;
        btn.textContent = 'Submit Enquiry';
      }
    });
  }

  // ── Live stats from API ───────────────────────────────────────────────────
  async function loadStats() {
    try {
      const res = await fetch('/api/stats');
      if (!res.ok) return;
      const { schools, scholarships, states } = await res.json();
      document.querySelectorAll('[data-stat="schools"]').forEach(el => { el.textContent = schools + '+'; });
      document.querySelectorAll('[data-stat="scholarships"]').forEach(el => { el.textContent = scholarships + '+'; });
      document.querySelectorAll('[data-stat="states"]').forEach(el => { el.textContent = states; });
    } catch (_) {}
  }
  loadStats();

})();
