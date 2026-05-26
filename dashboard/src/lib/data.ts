import identityJson from '../data/identity.json';
import manifestJson from '../data/manifest.json';
import prStatsJson from '../data/prs/stats.json';

export interface Model {
  id: string;
  kanban_name: string;
  display_name: string;
  slug: string;
  category: string;
}

export interface Identity {
  models: Model[];
}

export interface Manifest {
  last_updated: string | null;
  kanban_last_updated: string | null;
  models: string[];
  date_range: { start: string | null; end: string | null };
}

export interface PRStats {
  last_updated: string | null;
  total_prs_indexed_90d: number;
  attribution_coverage: { direct: number; inferred_only: number; platform: number };
  truncated: boolean;
}

export const identity = identityJson as Identity;
export const manifest = manifestJson as Manifest;
export const prStats = prStatsJson as PRStats;

export function modelById(id: string): Model | undefined {
  return identity.models.find((m) => m.id === id);
}

// Milliseconds in one calendar day. Used everywhere we slice the trend window
// from "today" (e.g. last 7 / 30 / 90 days). Pulled out of components so
// future tweaks (e.g. switching to dayjs/luxon) happen in one place.
export const MS_PER_DAY = 86_400_000;

/** Whole days between `iso` and now (negative if `iso` is in the future). */
export function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  return (Date.now() - new Date(iso).getTime()) / MS_PER_DAY;
}

/** ISO-date string (YYYY-MM-DD) for `days` days before today, UTC. */
export function cutoffDateDaysAgo(days: number): string {
  return new Date(Date.now() - days * MS_PER_DAY).toISOString().slice(0, 10);
}
