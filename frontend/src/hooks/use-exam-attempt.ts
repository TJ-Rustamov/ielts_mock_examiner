/**
 * Autosave and the server-authoritative clock for an exam attempt.
 *
 * Autosave has three layers, because the writing test's approach - keep the
 * essay in component state and nothing else - loses everything on a refresh:
 *
 * 1. every change is mirrored to localStorage synchronously, so a reload
 *    restores answers before any network round-trip;
 * 2. dirty answers are flushed to the server on a short debounce, a heartbeat,
 *    tab hide and page unload, and stay queued while offline;
 * 3. on load, locally dirty answers are replayed over the server's copy.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ExamRequestError, saveAnswers, type AnswerValue } from '@/lib/exams';

export type SaveState = 'idle' | 'saving' | 'saved' | 'offline' | 'closed';

const DEBOUNCE_MS = 800;
const HEARTBEAT_MS = 15000;
const RETRY_MS = 5000;

const storageKey = (attemptId: number) => `exam_attempt_${attemptId}`;

interface StoredAnswers {
  answers: Record<string, AnswerValue>;
  dirty: number[];
}

export function useAnswerAutosave(
  attemptId: number | null,
  initial: Record<string, AnswerValue>,
  onServerTime?: (serverNow: string) => void,
) {
  const [answers, setAnswers] = useState<Record<number, AnswerValue>>({});
  const [state, setState] = useState<SaveState>('idle');
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  const answersRef = useRef<Record<number, AnswerValue>>({});
  const dirty = useRef<Set<number>>(new Set());
  const inFlight = useRef<Promise<void> | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const closed = useRef(false);

  const persistLocal = useCallback(() => {
    if (attemptId == null) return;
    try {
      const payload: StoredAnswers = {
        answers: answersRef.current as Record<string, AnswerValue>,
        dirty: [...dirty.current],
      };
      localStorage.setItem(storageKey(attemptId), JSON.stringify(payload));
    } catch {
      // Storage full or disabled: the server copy is still the source of truth.
    }
  }, [attemptId]);

  const flush = useCallback(async (keepalive = false): Promise<void> => {
    if (attemptId == null || closed.current) return;
    if (inFlight.current) {
      await inFlight.current;
      if (dirty.current.size === 0) return;
    }
    if (dirty.current.size === 0) return;

    const sent = [...dirty.current].map((number) => ({
      question_number: number,
      value: answersRef.current[number],
    }));

    const run = (async () => {
      setState('saving');
      try {
        const response = await saveAnswers(attemptId, sent, keepalive);
        // Only clear what is unchanged since it was sent; anything typed while
        // the request was in flight stays dirty for the next flush.
        sent.forEach(({ question_number, value }) => {
          if (answersRef.current[question_number] === value) dirty.current.delete(question_number);
        });
        persistLocal();
        setSavedAt(new Date());
        setState(dirty.current.size ? 'saving' : 'saved');
        onServerTime?.(response.server_now);
      } catch (error) {
        if (error instanceof ExamRequestError && error.code === 'attempt_closed') {
          closed.current = true;
          setState('closed');
          return;
        }
        setState('offline');
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => { void flush(); }, RETRY_MS);
      }
    })();

    inFlight.current = run;
    try {
      await run;
    } finally {
      inFlight.current = null;
    }
  }, [attemptId, persistLocal, onServerTime]);

  const schedule = useCallback((delay: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { void flush(); }, delay);
  }, [flush]);

  // Hydrate once per attempt: server answers first, then replay anything the
  // server never received (for example, answers typed just before a crash).
  useEffect(() => {
    if (attemptId == null) return;
    closed.current = false;
    dirty.current = new Set();
    const merged: Record<number, AnswerValue> = {};
    Object.entries(initial || {}).forEach(([number, value]) => { merged[Number(number)] = value; });
    try {
      const raw = localStorage.getItem(storageKey(attemptId));
      if (raw) {
        const local = JSON.parse(raw) as StoredAnswers;
        (local.dirty || []).forEach((number) => {
          const value = local.answers?.[number];
          if (value !== undefined) {
            merged[number] = value;
            dirty.current.add(number);
          }
        });
      }
    } catch {
      // Corrupt local copy: ignore it rather than block the test.
    }
    answersRef.current = merged;
    setAnswers(merged);
    if (dirty.current.size) schedule(0);
    // `initial` is only meaningful for the first render of this attempt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attemptId]);

  useEffect(() => {
    if (attemptId == null) return;
    const heartbeat = window.setInterval(() => { void flush(); }, HEARTBEAT_MS);
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') void flush(true);
    };
    const onPageHide = () => { void flush(true); };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', onPageHide);
    return () => {
      window.clearInterval(heartbeat);
      window.clearTimeout(timer.current);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', onPageHide);
    };
  }, [attemptId, flush]);

  const setAnswer = useCallback((number: number, value: AnswerValue) => {
    if (closed.current) return;
    answersRef.current = { ...answersRef.current, [number]: value };
    setAnswers(answersRef.current);
    dirty.current.add(number);
    persistLocal();
    schedule(DEBOUNCE_MS);
  }, [persistLocal, schedule]);

  const clearLocal = useCallback(() => {
    if (attemptId == null) return;
    try { localStorage.removeItem(storageKey(attemptId)); } catch { /* ignore */ }
  }, [attemptId]);

  return {
    answers,
    setAnswer,
    state,
    savedAt,
    pending: dirty.current.size,
    flushNow: flush,
    clearLocal,
  };
}

/**
 * Countdown against the server's clock, not the browser's.
 *
 * Each response carries `server_now`; the offset between that and `Date.now()`
 * is applied to every tick, so a wrong system clock neither steals time nor
 * grants extra. The server also rejects late submissions independently.
 */
export function useServerClock(expiresAt: string | null) {
  const offset = useRef(0);
  const [now, setNow] = useState(() => Date.now());

  const sync = useCallback((serverNow: string) => {
    const server = Date.parse(serverNow);
    if (!Number.isNaN(server)) offset.current = server - Date.now();
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const remaining = expiresAt
    ? Math.max(0, Math.floor((Date.parse(expiresAt) - (now + offset.current)) / 1000))
    : null;

  return { remaining, sync };
}

export function isAnswered(value: AnswerValue | undefined): boolean {
  if (!value) return false;
  if ('text' in value) return Boolean(value.text && value.text.trim());
  if ('letter' in value) return Boolean(value.letter && value.letter.trim());
  if ('letters' in value) return Boolean(value.letters && value.letters.length);
  return false;
}

export function formatClock(totalSeconds: number | null): string {
  if (totalSeconds === null) return '--:--';
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return hours ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`;
}
