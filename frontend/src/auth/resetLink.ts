import { readonly, ref, type InjectionKey } from 'vue';
import type { ResetLinkRequest } from '../api/index.js';

export const RECOVERY_PATH = '/recover-password/';
const MAX_SECRET_LENGTH = 128; // Matches the existing backend UID/token bounds.
const SECRET_FIELDS = ['uidb64', 'token'] as const;

/** Called before router creation: secrets never enter Vue navigation/history state. */
export function captureResetLink(
  href: string,
  scrub: (path: string) => void,
): ResetLinkRequest | null {
  const url = new URL(href);
  const recovery = url.pathname === RECOVERY_PATH || url.pathname === RECOVERY_PATH.slice(0, -1);
  const fragment = new URLSearchParams(url.hash.slice(1));
  const secretFragment = SECRET_FIELDS.some((field) => fragment.has(field));
  const secretQuery = SECRET_FIELDS.some((field) => url.searchParams.has(field));
  if (recovery || secretFragment || secretQuery) scrub(url.pathname);
  // Only the configured fragment format is accepted. Query/path tokens are never used.
  if (
    !recovery ||
    url.search ||
    [...fragment.keys()].some(
      (field) => !SECRET_FIELDS.includes(field as (typeof SECRET_FIELDS)[number]),
    )
  )
    return null;
  const values: Partial<ResetLinkRequest> = {};
  for (const field of SECRET_FIELDS) {
    const entries = fragment.getAll(field);
    if (entries.length !== 1 || !entries[0] || entries[0].length > MAX_SECRET_LENGTH) return null;
    values[field] = entries[0];
  }
  return { uidb64: values.uidb64!, token: values.token! };
}

export function createResetLinkSlot(initial: ResetLinkRequest | null) {
  let value = initial;
  const version = ref(0);
  return {
    version: readonly(version),
    replace(next: ResetLinkRequest | null) {
      value = next;
      version.value += 1;
    },
    take() {
      const result = value;
      value = null;
      return result;
    },
    clear() {
      value = null;
    },
  };
}
export type ResetLinkSlot = ReturnType<typeof createResetLinkSlot>;
export const resetLinkKey: InjectionKey<ResetLinkSlot> = Symbol('reset-link');
