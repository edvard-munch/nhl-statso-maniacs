import type { Router } from 'vue-router';

const MAX_RETURN_LENGTH = 2048;
// eslint-disable-next-line no-control-regex -- Reject control characters in return navigation.
const FORBIDDEN_CHARACTERS = /[\u0000-\u001f\u007f\\]/;
const RETURN_ROUTES = new Set([
  'home',
  'games',
  'game-detail',
  'players',
  'player-profile',
  'player-gamelog',
]);
export function safeReturnLocation(value: unknown, router: Router): string {
  if (
    typeof value !== 'string' ||
    value.length > MAX_RETURN_LENGTH ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    FORBIDDEN_CHARACTERS.test(value)
  )
    return '/';
  try {
    const target = router.resolve(value);
    return typeof target.name === 'string' && RETURN_ROUTES.has(target.name)
      ? target.fullPath
      : '/';
  } catch {
    return '/';
  }
}
