import { createRouter, createWebHistory, type RouterHistory } from 'vue-router';
import HomeView from './views/HomeView.vue';
import PlayersView from './views/PlayersView.vue';
import ScoreboardView from './views/ScoreboardView.vue';
import GameDetailView from './views/GameDetailView.vue';
import NotFoundView from './views/NotFoundView.vue';
import LoginView from './views/LoginView.vue';
import RegisterView from './views/RegisterView.vue';
import PasswordResetRequestView from './views/PasswordResetRequestView.vue';
import PasswordResetConfirmView from './views/PasswordResetConfirmView.vue';
import { RECOVERY_PATH, captureResetLink, type ResetLinkSlot } from './auth/resetLink.js';

export const SITE_TITLE = 'NHL Statso Maniacs';

export function createAppRouter(
  history: RouterHistory = createWebHistory(),
  resetLink?: ResetLinkSlot,
) {
  const router = createRouter({
    history,
    routes: [
      {
        path: '/password-reset',
        name: 'password-reset',
        component: PasswordResetRequestView,
        meta: { title: 'Reset password' },
      },
      {
        path: RECOVERY_PATH,
        name: 'recover-password',
        component: PasswordResetConfirmView,
        meta: { title: 'Choose a new password' },
      },
      { path: '/', name: 'home', component: HomeView, meta: { title: 'Home' } },
      { path: '/login', name: 'login', component: LoginView, meta: { title: 'Sign in' } },
      {
        path: '/register',
        name: 'register',
        component: RegisterView,
        meta: { title: 'Create account' },
      },
      { path: '/players', name: 'players', component: PlayersView, meta: { title: 'Players' } },
      { path: '/games', name: 'games', component: ScoreboardView, meta: { title: 'Games' } },
      {
        path: '/games/:nhlId',
        name: 'game-detail',
        component: GameDetailView,
        meta: { title: 'Game details' },
      },
      {
        path: '/:pathMatch(.*)*',
        name: 'not-found',
        component: NotFoundView,
        meta: { title: 'Page not found' },
      },
    ],
    scrollBehavior: () => ({ top: 0 }),
  });
  if (resetLink)
    router.beforeEach((to) => {
      if (!to.hash && !Object.keys(to.query).length) return;
      let clean: string | null = null;
      const captured = captureResetLink(
        new URL(to.fullPath, window.location.origin).href,
        (path) => {
          clean = path;
          history.replace(path, { back: null, current: path, forward: null });
        },
      );
      if (clean !== null) {
        resetLink.replace(captured);
        return { path: clean, replace: true };
      }
    });
  router.afterEach((to) => {
    document.title = `${to.meta.title} | ${SITE_TITLE}`;
  });
  return router;
}
