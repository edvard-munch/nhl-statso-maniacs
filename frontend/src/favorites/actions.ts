import type { InjectionKey } from 'vue';
import { readonly, shallowRef, watch } from 'vue';
import {
  ApiError,
  ApiProtocolError,
  meFavoritePut,
  meFavoriteDelete,
  meFavoritesList,
  type FavoriteQuota,
  type PlayerRetrievePath,
} from '../api/index.js';
import type { Session } from '../auth/session.js';
import type { PrivateActionContext } from '../private/actionTypes.js';
import { parsePlayerIdentity } from '../players/profile.js';

const HTTP_OK = 200;
const HTTP_CREATED = 201;
const HTTP_NO_CONTENT = 204;
const MEMBERSHIP_PAGE_SIZE = 100;
const REJECTED_STATUSES = new Set([400, 404, 405, 406]);
const HTTP_CONFLICT = 409;
const HTTP_FORBIDDEN = 403;
export type FavoriteIntent = {
  action: 'add' | 'remove';
  path: PlayerRetrievePath;
  name: string;
  source: string;
};
export type FavoriteOutcome = {
  outcome: 'confirmed' | 'observed' | 'uncertain' | 'rejected';
  message: string;
  reference: string | null;
  desiredObserved: boolean;
  quota: FavoriteQuota | null;
};
export type FavoriteNotice = FavoriteIntent & FavoriteOutcome & { owner: number; revision: number };
function validQuota(value: FavoriteQuota): boolean {
  return (
    !!value &&
    typeof value.over_limit === 'boolean' &&
    ['limit', 'skaters_count', 'goalies_count', 'total_count', 'remaining'].every(
      (key) =>
        Number.isSafeInteger(value[key as keyof FavoriteQuota]) &&
        Number(value[key as keyof FavoriteQuota]) >= 0,
    )
  );
}
async function observe(
  ctx: PrivateActionContext,
  path: PlayerRetrievePath,
): Promise<'present' | 'absent' | 'unknown'> {
  const { data } = await ctx.request((signal) =>
    meFavoritesList({
      client: ctx.client,
      query: { player_type: path.player_type, page: 1, page_size: MEMBERSHIP_PAGE_SIZE },
      signal,
    }),
  );
  if (
    !ctx.sameOwner() ||
    data.meta.player_type !== path.player_type ||
    !Array.isArray(data.results)
  )
    return 'unknown';
  if (
    !data.results.every(
      (row) =>
        typeof row.nhl_id === 'number' &&
        !!parsePlayerIdentity(row.player_type, String(row.nhl_id)) &&
        row.player_type === path.player_type,
    )
  )
    return 'unknown';
  if (data.results.some((row) => row.nhl_id === path.nhl_id)) return 'present';
  // One owner-locked complete snapshot can prove absence. Never scan moving pages.
  const ids = new Set(data.results.map((row) => row.nhl_id));
  return data.next === null &&
    data.previous === null &&
    data.count === data.results.length &&
    ids.size === data.count
    ? 'absent'
    : 'unknown';
}
export async function applyFavoriteIntent(
  ctx: PrivateActionContext,
  intent: FavoriteIntent,
): Promise<FavoriteOutcome> {
  const result = (
    outcome: FavoriteOutcome['outcome'],
    message: string,
    reference: string | null = null,
    desiredObserved = false,
    quota: FavoriteQuota | null = null,
  ): FavoriteOutcome => ({ outcome, message, reference, desiredObserved, quota });
  try {
    if (intent.action === 'add') {
      const response = await ctx.request((signal) =>
        meFavoritePut({ client: ctx.client, path: intent.path, signal }),
      );
      const body = response.data;
      if (
        ![HTTP_OK, HTTP_CREATED].includes(response.response.status) ||
        body.is_favorite !== true ||
        body.nhl_id !== intent.path.nhl_id ||
        body.player_type !== intent.path.player_type ||
        !validQuota(body.quota)
      )
        throw new Error('Unconfirmed favorite response');
      return result(
        'confirmed',
        response.response.status === HTTP_CREATED
          ? `${intent.name} was added to Favorites.`
          : `${intent.name} is already saved in Favorites.`,
        null,
        true,
        body.quota,
      );
    }
    const response = await ctx.request((signal) =>
      meFavoriteDelete({ client: ctx.client, path: intent.path, signal }),
    );
    if (response.response.status !== HTTP_NO_CONTENT)
      throw new Error('Unconfirmed removal response');
    return result('confirmed', `${intent.name} was removed from Favorites.`, null, true);
  } catch (failure) {
    if (!ctx.sameOwner()) return result('uncertain', 'The action could not be confirmed.');
    const code = failure instanceof ApiError ? failure.body.error.code : null;
    const reference =
      failure instanceof ApiError || failure instanceof ApiProtocolError ? failure.requestId : null;
    if (
      failure instanceof ApiError &&
      failure.response.status === HTTP_CONFLICT &&
      code === 'favorites_quota_exceeded'
    )
      return result(
        'rejected',
        'The Favorites limit was reached. Remove a saved player before adding another.',
        reference,
      );
    if (
      failure instanceof ApiError &&
      failure.response.status === HTTP_FORBIDDEN &&
      (code === 'csrf_failed' || code === 'authentication_required')
    ) {
      await ctx.recheck();
      return result(
        'rejected',
        'Your session changed. Review sign-in status, then submit again if needed.',
        reference,
      );
    }
    if (failure instanceof ApiError && REJECTED_STATUSES.has(failure.response.status))
      return result(
        'rejected',
        'This saved-player action was rejected. Refresh the page before trying again.',
        reference,
      );
    // A lost/timed-out result may have committed. Reverify owner, then read once.
    try {
      if (!(await ctx.recheck()) || !ctx.sameOwner())
        return result('uncertain', 'The action could not be confirmed.', reference);
      const observed = await observe(ctx, intent.path);
      if (!ctx.sameOwner())
        return result('uncertain', 'The action could not be confirmed.', reference);
      const desired = intent.action === 'add' ? observed === 'present' : observed === 'absent';
      if (desired)
        return result(
          'observed',
          intent.action === 'add'
            ? `${intent.name} is currently saved in Favorites. The original save response was uncertain.`
            : `${intent.name} is currently absent from Favorites. The original removal response was uncertain.`,
          reference,
          true,
        );
      return result(
        'uncertain',
        observed === 'unknown'
          ? 'The action could not be confirmed from saved data. Check Favorites before choosing to submit again.'
          : 'A current saved-data read does not show the requested state. Submit again only if you still want that change.',
        reference,
      );
    } catch {
      return result(
        'uncertain',
        'The action could not be confirmed. Check Favorites before choosing to submit again.',
        reference,
      );
    }
  }
}

export function createFavoriteActions(session: Session) {
  const notice = shallowRef<FavoriteNotice | null>(null);
  const running = shallowRef(false);
  let disposed = false;
  const stop = watch(
    [() => session.user.value?.id, () => session.status.value, () => session.revision.value],
    () => {
      notice.value = null;
    },
    { flush: 'sync' },
  );
  async function run(
    action: FavoriteIntent['action'],
    type: string,
    id: number,
    name: string,
    source: string,
  ) {
    const path = parsePlayerIdentity(type, String(id));
    if (
      disposed ||
      running.value ||
      session.busy.value ||
      !path ||
      !session.user.value ||
      session.status.value !== 'ready'
    )
      return false;
    running.value = true;
    notice.value = null;
    const intent = { action, path, name, source };
    try {
      const response = await session.withPrivateAction((ctx) => applyFavoriteIntent(ctx, intent));
      if (
        disposed ||
        !response ||
        response.owner !== session.user.value?.id ||
        response.revision !== session.revision.value ||
        session.status.value !== 'ready' ||
        session.busy.value
      )
        return false;
      notice.value = {
        ...intent,
        ...(response.value ?? {
          outcome: 'uncertain',
          message:
            'The action could not be confirmed. Check Favorites before choosing to submit again.',
          reference: null,
          desiredObserved: false,
          quota: null,
        }),
        owner: response.owner,
        revision: response.revision,
      };
      return notice.value.desiredObserved;
    } finally {
      running.value = false;
    }
  }
  return {
    notice: readonly(notice),
    running: readonly(running),
    run,
    dispose() {
      disposed = true;
      stop();
      notice.value = null;
    },
  };
}

export type FavoriteActions = ReturnType<typeof createFavoriteActions>;
export const favoriteActionsKey: InjectionKey<FavoriteActions> = Symbol('favorite-actions');
