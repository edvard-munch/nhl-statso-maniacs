import type { Router } from 'vue-router';
import { safeReturnLocation } from '../auth/returnLocation.js';
import { parseCatalogueQuery } from '../players/catalogue.js';
export function favoritesReturn(value: unknown, router: Router): string | null {
  const target = router.resolve(safeReturnLocation(value, router));
  if (target.name !== 'favorites') return null;
  try {
    parseCatalogueQuery(target.query);
    return target.fullPath;
  } catch {
    return null;
  }
}
