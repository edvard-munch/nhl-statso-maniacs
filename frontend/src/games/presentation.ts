import type { GamePlayerAvailabilityEnum } from '../api/index.js';

const POSITIVE_ID = /^[1-9]\d*$/;
const SECONDS_PER_MINUTE = 60;
const TIME_COMPONENT_WIDTH = 2;
const PERCENT_SCALE = 100;
const PERCENT_DECIMALS = 1;
export const UNAVAILABLE = '—';

export function parseGameId(value: unknown): number | null {
  if (typeof value !== 'string' || !POSITIVE_ID.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}
export function numberLabel(value: number | null): string {
  return value === null ? UNAVAILABLE : String(value);
}
export function toiLabel(seconds: number | null): string {
  if (seconds === null || !Number.isInteger(seconds) || seconds < 0) return UNAVAILABLE;
  const minutes = Math.floor(seconds / SECONDS_PER_MINUTE);
  const remainder = seconds % SECONDS_PER_MINUTE;
  return `${String(minutes).padStart(TIME_COMPONENT_WIDTH, '0')}:${String(remainder).padStart(TIME_COMPONENT_WIDTH, '0')}`;
}
export function savePercentageLabel(value: number | null): string {
  if (value === null || !Number.isFinite(value) || value < 0 || value > 1) return UNAVAILABLE;
  return `${(value * PERCENT_SCALE).toFixed(PERCENT_DECIMALS)}%`;
}
export const AVAILABILITY_LABELS: Record<GamePlayerAvailabilityEnum, string> = {
  complete: 'Complete',
  partial: 'Partial',
  missing: 'Missing',
  unverified: 'Unverified',
};
