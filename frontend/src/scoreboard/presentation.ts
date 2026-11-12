import type { SavedGameState } from '../api/index.js';

const SCHEDULE_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const POSITIVE_PAGE_PATTERN = /^[1-9]\d*$/;
export const SCOREBOARD_PAGE_SIZE = 50;
export const FIRST_PAGE = 1;
const dateFormatter = new Intl.DateTimeFormat('en', { dateStyle: 'full', timeZone: 'UTC' });
const shortDateFormatter = new Intl.DateTimeFormat('en', {
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
});
const savedTimeFormatter = new Intl.DateTimeFormat('en', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'UTC',
});

export function isScheduleDate(value: unknown): value is string {
  if (typeof value !== 'string' || !SCHEDULE_DATE_PATTERN.test(value) || value.startsWith('0000'))
    return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function parsePage(value: unknown): number | null {
  if (value === undefined) return FIRST_PAGE;
  if (typeof value !== 'string' || !POSITIVE_PAGE_PATTERN.test(value)) return null;
  const page = Number(value);
  return Number.isSafeInteger(page) ? page : null;
}

// UTC here preserves a calendar label, rather than converting an NHL schedule date
// into the viewer's local date. The API supplies the Pacific date selection.
export function scheduleDateLabel(value: string, short = false): string {
  if (!isScheduleDate(value)) return value;
  return (short ? shortDateFormatter : dateFormatter).format(new Date(`${value}T00:00:00Z`));
}

export function savedTimeLabel(value: string | null): string {
  if (!value) return 'Save time unavailable';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? 'Save time unavailable'
    : `${savedTimeFormatter.format(parsed)} UTC`;
}

export function stateLabel(state: SavedGameState): string {
  if (state.conflict) return 'Conflicting saved state';
  if (state.value === 'final') return 'Final (saved)';
  if (state.value === 'live') return 'Saved as live';
  return 'State unknown';
}
