import type { ApiClient } from '../api/http.js';
export type PrivateActionContext = {
  client: ApiClient;
  request: <T>(operation: (signal: AbortSignal) => Promise<T>) => Promise<T>;
  sameOwner: () => boolean;
  recheck: () => Promise<boolean>;
};
export type PrivateActionResult<T> = { owner: number; revision: number; value: T | null };
