/**
 * API client and types for Reading & Listening.
 *
 * Wraps the shared `fetchJson` from lib/backend.ts, which already attaches the
 * auth token and force-logs-out on 401/403.
 */
import { fetchJson, apiUrl } from '@/lib/backend';

export type Skill = 'reading' | 'listening';
export type AttemptMode = 'exam' | 'practice';

/** Mirrors exams.importer.boilerplate. */
export type GroupType =
  | 'mcq_single' | 'mcq_multi' | 'tfng' | 'ynng'
  | 'list_of_headings' | 'matching_paragraph' | 'matching_features'
  | 'matching_bank' | 'sentence_endings' | 'classification' | 'short_answer'
  | 'note_completion' | 'table_completion' | 'form_completion'
  | 'flowchart_completion' | 'summary_completion' | 'summary_completion_bank'
  | 'sentence_completion' | 'diagram_labelling' | 'map_labelling'
  | 'plan_labelling' | 'unknown';

export interface Option { letter: string; text: string }

/** A renderable block. `text` may contain {{Qn}} placeholders. */
export type LayoutBlock =
  | { kind: 'heading'; text: string }
  | { kind: 'line'; text: string }
  | { kind: 'bullets'; items: string[] }
  | { kind: 'table'; head?: { text: string }[]; rows: { text: string }[][] }
  | { kind: 'flow'; steps: { text: string; arrow?: boolean }[] };

export interface ExamQuestion {
  number: number;
  prompt_text: string;
  options: Option[];
}

export interface ExamGroup {
  id: number;
  order: number;
  type: GroupType;
  instruction_text: string;
  first_question: number;
  last_question: number;
  word_limit: string;
  select_count: number | null;
  options: Option[];
  options_reusable: boolean;
  layout: LayoutBlock[];
  image_url: string | null;
  questions: ExamQuestion[];
}

export interface ExamSection {
  id: number;
  order: number;
  label: string;
  title: string;
  first_question: number;
  last_question: number;
  passage_html: string;
  passage_paragraphs: { label: string; html: string }[];
  has_audio: boolean;
  audio_seconds: number | null;
  groups: ExamGroup[];
}

export interface ModuleSummary {
  id: number;
  skill: Skill;
  book: string;
  book_slug: string;
  test_number: number;
  total_questions: number;
  duration_seconds: number;
  is_published: boolean;
  best_band: string | null;
}

export interface ModuleContent extends ModuleSummary {
  transfer_seconds: number;
  sections: ExamSection[];
}

/** What the student has entered for one question. */
export type AnswerValue =
  | { text: string }
  | { letter: string }
  | { letters: string[] };

export interface AttemptState {
  id: number;
  status: 'in_progress' | 'submitted' | 'expired' | 'abandoned';
  mode: AttemptMode;
  module: ModuleSummary;
  started_at: string;
  expires_at: string;
  submitted_at: string | null;
  current_section: number;
  raw_score: number | null;
  band: string | null;
  answers: Record<string, AnswerValue>;
  server_now: string;
}

export interface ResultRow {
  number: number;
  response: string;
  is_correct: boolean;
  reason: 'correct' | 'wrong' | 'blank' | 'over_word_limit' | 'over_selected' | 'partial';
  accepted: string[];
}

export interface ExamResult {
  attempt_id: number;
  status: string;
  mode: AttemptMode;
  raw_score: number | null;
  band: string | null;
  total_questions: number;
  correct: number;
  blank: number;
  wrong: number;
  /** Cambridge does not publish exact conversions; always surface this. */
  indicative: boolean;
  rows: ResultRow[];
}

// --- student ---------------------------------------------------------------

export function listTests(skill?: Skill) {
  const query = skill ? `?skill=${skill}` : '';
  return fetchJson<{ tests: ModuleSummary[] }>(`/api/exams/tests${query}`);
}

export function startAttempt(moduleId: number, mode: AttemptMode = 'exam') {
  return fetchJson<{ attempt: AttemptState; content: ModuleContent }>(
    `/api/exams/modules/${moduleId}/attempts`,
    { method: 'POST', body: JSON.stringify({ mode }) },
  );
}

export function getAttempt(attemptId: number) {
  return fetchJson<{ attempt: AttemptState; content?: ModuleContent }>(
    `/api/exams/attempts/${attemptId}`,
  );
}

export function saveAnswers(
  attemptId: number,
  answers: { question_number: number; value: AnswerValue }[],
) {
  return fetchJson<{ saved: number; server_now: string; expires_at: string }>(
    `/api/exams/attempts/${attemptId}/answers`,
    { method: 'PATCH', body: JSON.stringify({ answers }) },
  );
}

export function advanceSection(attemptId: number, section: number) {
  return fetchJson<{ current_section: number; server_now: string }>(
    `/api/exams/attempts/${attemptId}/advance`,
    { method: 'POST', body: JSON.stringify({ section }) },
  );
}

export function submitAttempt(attemptId: number) {
  return fetchJson<ExamResult>(`/api/exams/attempts/${attemptId}/submit`, {
    method: 'POST',
  });
}

export function getResult(attemptId: number) {
  return fetchJson<ExamResult>(`/api/exams/attempts/${attemptId}/result`);
}

export function listAttempts() {
  return fetchJson<{ attempts: AttemptState[] }>('/api/exams/attempts');
}

export function overallBand() {
  return fetchJson<{
    reading: number | null; listening: number | null;
    writing: number | null; speaking: number | null; overall: string | null;
  }>('/api/exams/overall-band');
}

/** Audio is served through an authenticated view, not MEDIA_URL. */
export function attemptAudioUrl(attemptId: number, sectionId: number) {
  return apiUrl(`/api/exams/attempts/${attemptId}/audio/${sectionId}`);
}

// --- admin -----------------------------------------------------------------

export interface AdminModule extends ModuleSummary {
  blocking_problems: string[];
  has_answer_sheet: boolean;
  answer_sheet_verified: boolean;
}

export interface AnswerSheet {
  id: number;
  module: number;
  image_url: string | null;
  answers: Record<string, { kind: string; accepted: string[] }>;
  ocr_answers: Record<string, { kind: string; accepted: string[] }>;
  raw_text: Record<string, string>;
  ocr_confidence: number | null;
  warnings: string[];
  is_verified: boolean;
  verified_at: string | null;
  answered_count: number;
  missing_numbers: number[];
  edited_numbers: number[];
}

export function listAdminModules(bookSlug?: string) {
  const query = bookSlug ? `?book=${encodeURIComponent(bookSlug)}` : '';
  return fetchJson<{ modules: AdminModule[] }>(`/api/exams/admin/modules${query}`);
}

export function setModulePublished(moduleId: number, isPublished: boolean) {
  return fetchJson<AdminModule>(`/api/exams/admin/modules/${moduleId}`, {
    method: 'PATCH',
    body: JSON.stringify({ is_published: isPublished }),
  });
}

export function getAnswerSheet(moduleId: number) {
  return fetchJson<{ sheet: AnswerSheet | null; module: AdminModule }>(
    `/api/exams/admin/modules/${moduleId}/answer-sheet`,
  );
}

export function uploadAnswerSheet(moduleId: number, file: File) {
  const form = new FormData();
  form.append('image', file);
  return fetchJson<{
    sheet: AnswerSheet; read: number; total: number; missing: number[];
  }>(`/api/exams/admin/modules/${moduleId}/answer-sheet`, {
    method: 'POST',
    body: form,
  });
}

/** Send the corrected grid. Any edit clears the verified flag server-side. */
export function saveAnswerSheet(
  moduleId: number,
  answers: Record<string, string>,
) {
  return fetchJson<AnswerSheet>(
    `/api/exams/admin/modules/${moduleId}/answer-sheet`,
    { method: 'PATCH', body: JSON.stringify({ answers }) },
  );
}

export function verifyAnswerSheet(moduleId: number) {
  return fetchJson<{ verified: boolean; remarked_attempts: number; module: AdminModule }>(
    `/api/exams/admin/modules/${moduleId}/answer-sheet/verify`,
    { method: 'POST' },
  );
}

export interface ImportJob {
  id: number;
  book_slug: string;
  status: 'queued' | 'running' | 'needs_review' | 'published' | 'failed';
  stage: string;
  progress: number;
  warnings: string[];
  error: string;
  payload_version: number;
  created_at: string;
  updated_at: string;
}

export function listImportJobs() {
  return fetchJson<{ jobs: ImportJob[] }>('/api/exams/admin/import-jobs');
}

export function createImportJob(file: File, bookSlug: string) {
  const form = new FormData();
  form.append('file', file);
  form.append('book_slug', bookSlug);
  return fetchJson<ImportJob>('/api/exams/admin/import-jobs', {
    method: 'POST',
    body: form,
  });
}

export function getImportJob(jobId: number, withPayload = false) {
  return fetchJson<ImportJob & { payload?: unknown }>(
    `/api/exams/admin/import-jobs/${jobId}${withPayload ? '?payload=1' : ''}`,
  );
}

export function publishImportJob(jobId: number) {
  return fetchJson<{
    book: string | null; modules: number[]; questions: number;
    warnings: string[]; note: string;
  }>(`/api/exams/admin/import-jobs/${jobId}/publish`, { method: 'POST' });
}
