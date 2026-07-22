// EduPortal service worker — handles Web Push while no tab is open.
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { /* non-JSON payload */ }
  const title = data.title || 'EduPortal South Sudan';
  const body = data.body || '';
  event.waitUntil(self.registration.showNotification(title, { body, tag: 'eduportal-notification' }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow('/dashboard'));
});
