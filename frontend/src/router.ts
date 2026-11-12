import { createRouter, createWebHistory, type RouterHistory } from 'vue-router';
import HomeView from './views/HomeView.vue';
import ScoreboardView from './views/ScoreboardView.vue';
import GameDetailView from './views/GameDetailView.vue';
import NotFoundView from './views/NotFoundView.vue';

export const SITE_TITLE = 'NHL Statso Maniacs';

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({
    history,
    routes: [
      { path: '/', name: 'home', component: HomeView, meta: { title: 'Home' } },
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
  router.afterEach((to) => {
    document.title = `${to.meta.title} | ${SITE_TITLE}`;
  });
  return router;
}
