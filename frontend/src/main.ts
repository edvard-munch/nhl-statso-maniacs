import { createApp } from 'vue';
import App from './App.vue';
import { createAppRouter } from './router.js';
import './style.css';
import { createSession, sessionKey } from './auth/session.js';

import { captureResetLink, createResetLinkSlot, resetLinkKey } from './auth/resetLink.js';

const resetLink = createResetLinkSlot(
  captureResetLink(window.location.href, (path) => window.history.replaceState(null, '', path)),
);
const router = createAppRouter(undefined, resetLink);
const session = createSession();
createApp(App)
  .provide(sessionKey, session)
  .provide(resetLinkKey, resetLink)
  .use(router)
  .mount('#app');
void session.checkSession();
