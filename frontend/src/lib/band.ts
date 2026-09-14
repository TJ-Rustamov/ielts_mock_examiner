/**
 * IELTS band rounding.
 *
 * Mirrors `round_ielts_half` in backend/exams/bands.py — keep the two in sync.
 *
 * The official rule rounds to the nearest half band: a fractional part of .25
 * or more rounds up to .5, and .75 or more rounds up to the next whole band.
 * The previous per-page `formatBandScore` helpers used .5/.7 thresholds and so
 * reported 6.25 as 6.0 where IELTS gives 6.5.
 */
export function roundIeltsHalf(score: number): number {
  if (!Number.isFinite(score)) return 0;
  const whole = Math.floor(score);
  const frac = score - whole;
  if (frac < 0.25) return whole;
  if (frac < 0.75) return whole + 0.5;
  return whole + 1;
}

/** Band as a display string, always to one decimal place (e.g. "6.5", "7.0"). */
export function formatBand(score: number | null | undefined): string {
  if (score === null || score === undefined || !Number.isFinite(score)) return '—';
  return roundIeltsHalf(score).toFixed(1);
}

/** Mean of the four skill bands, rounded to the nearest half band. */
export function overallBand(bands: Array<number | null | undefined>): number | null {
  const present = bands.filter((b): b is number => typeof b === 'number' && Number.isFinite(b));
  if (present.length === 0) return null;
  return roundIeltsHalf(present.reduce((a, b) => a + b, 0) / present.length);
}
