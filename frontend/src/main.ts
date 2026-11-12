import { createApp } from 'vue';
import App from './App.vue';
import { createAppRouter } from './router.js';
import './style.css';
import { createSession, sessionKey } from './auth/session.js';

const router = createAppRouter();
const session = createSession();
createApp(App).provide(sessionKey, session).use(router).mount('#app');
void session.checkSession();
