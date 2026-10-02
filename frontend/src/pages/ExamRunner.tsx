/**
 * Sits one Reading or Listening module.
 *
 * Reading: passage and questions side by side in a resizable split.
 * Listening: the locked audio player above the questions for the current part.
 *
 * Nothing here decides a score. Answers autosave to the server, the countdown
 * runs against the server's clock, and marking happens server-side on submit.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import {
  AlertTriangle, BookOpen, Check, Clock, CloudOff, Flag, Headphones, Loader2, Play, Send,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  ResizableHandle, ResizablePanel, ResizablePanelGroup,
} from '@/components/ui/resizable';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import GroupRenderer from '@/components/exam/GroupRenderer';
import LockedAudioPlayer from '@/components/exam/LockedAudioPlayer';
import PassagePages from '@/components/exam/PassagePages';
import { useThemeContext } from '@/contexts/ThemeContext';
import { useIsMobile } from '@/hooks/use-mobile';
import {
  formatClock, isAnswered, useAnswerAutosave, useServerClock, type SaveState,
} from '@/hooks/use-exam-attempt';
import {
  advanceSection, errorMessage, listTests, startAttempt, submitAttempt,
  type AttemptMode, type AttemptState, type ExamSection, type ModuleContent, type ModuleSummary,
} from '@/lib/exams';
import { cn } from '@/lib/utils';

const WARNINGS_AT = [600, 300, 60];

function Passage({ section }: { section: ExamSection }) {
  const hasPages = (section.passage_pages?.length ?? 0) > 0;
  const [view, setView] = useState<'page' | 'text'>('page');
  const paragraphs = section.passage_paragraphs?.length
    ? section.passage_paragraphs.map((p) => ({ label: p.label, text: p.html }))
    : section.passage_html.split(/\n+/).map((text) => text.trim()).filter(Boolean)
      .map((text) => ({ label: '', text }));

  return (
    <article className="space-y-4 leading-7">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{section.label}</p>
          {section.title && !(hasPages && view === 'page') && (
            <h2 className="text-xl font-semibold">{section.title}</h2>
          )}
        </div>
        {hasPages && paragraphs.length > 0 && (
          <div className="flex shrink-0 rounded-md border p-0.5 text-xs">
            {(['page', 'text'] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setView(option)}
                className={cn(
                  'rounded px-2 py-1 capitalize',
                  view === option ? 'bg-primary text-primary-foreground' : 'text-muted-foreground',
                )}
              >
                {option === 'page' ? 'Book page' : 'Text'}
              </button>
            ))}
          </div>
        )}
      </header>
      {hasPages && view === 'page' ? (
        <PassagePages section={section} />
      ) : paragraphs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          The passage text for this section was not imported.
        </p>
      ) : (
        // Passage text is rendered as text, never as HTML: it comes from PDF
        // extraction and has not been sanitised.
        paragraphs.map((paragraph, index) => (
          <p key={index}>
            {paragraph.label && <b className="mr-2 text-primary">{paragraph.label}</b>}
            {paragraph.text}
          </p>
        ))
      )}
    </article>
  );
}

function SaveIndicator({ state, savedAt }: { state: SaveState; savedAt: Date | null }) {
  if (state === 'saving') {
    return (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> Saving
      </span>
    );
  }
  if (state === 'offline') {
    return (
      <span className="flex items-center gap-1 text-xs text-amber-600" title="Answers are kept on this device and will be sent when the connection returns">
        <CloudOff className="h-3 w-3" /> Offline - kept locally
      </span>
    );
  }
  if (state === 'closed') {
    return <span className="text-xs text-destructive">Attempt closed</span>;
  }
  if (state === 'saved' && savedAt) {
    return (
      <span className="hidden items-center gap-1 text-xs text-muted-foreground sm:flex">
        <Check className="h-3 w-3" /> Saved {savedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </span>
    );
  }
  return null;
}

const ExamRunner = () => {
  const { moduleId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setStudyMode } = useThemeContext();
  const isMobile = useIsMobile();

  const [mode, setMode] = useState<AttemptMode>(
    searchParams.get('mode') === 'practice' ? 'practice' : 'exam',
  );
  const [summary, setSummary] = useState<ModuleSummary | null>(null);
  const [attempt, setAttempt] = useState<AttemptState | null>(null);
  const [content, setContent] = useState<ModuleContent | null>(null);
  const [starting, setStarting] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [sectionIndex, setSectionIndex] = useState(0);
  const [currentQuestion, setCurrentQuestion] = useState<number | null>(null);
  const [flagged, setFlagged] = useState<Set<number>>(new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [audioFinished, setAudioFinished] = useState(false);
  const [focusLosses, setFocusLosses] = useState(0);

  const warned = useRef<Set<number>>(new Set());
  const submittedRef = useRef(false);

  const clock = useServerClock(attempt?.expires_at ?? null);
  const autosave = useAnswerAutosave(attempt?.id ?? null, attempt?.answers ?? {}, clock.sync);

  // Module details for the start screen. The attempt is not created until the
  // candidate presses Start, so time spent reading instructions is not lost.
  useEffect(() => {
    listTests()
      .then(({ tests }) => {
        const found = tests.find((t) => t.id === Number(moduleId)) ?? null;
        setSummary(found);
        if (found) setStudyMode(found.skill);
      })
      .catch(() => undefined);
  }, [moduleId, setStudyMode]);

  const begin = async () => {
    setStarting(true);
    setLoadError('');
    try {
      const response = await startAttempt(Number(moduleId), mode);
      clock.sync(response.attempt.server_now);
      setStudyMode(response.content.skill);
      setContent(response.content);
      setAttempt(response.attempt);
      const lastSection = response.content.sections.length - 1;
      setSectionIndex(Math.max(0, Math.min((response.attempt.current_section || 1) - 1, lastSection)));
      try {
        const stored = localStorage.getItem(`exam_flags_${response.attempt.id}`);
        if (stored) setFlagged(new Set(JSON.parse(stored) as number[]));
      } catch { /* ignore */ }
    } catch (error) {
      setLoadError(errorMessage(error, 'Could not start this test.'));
    } finally {
      setStarting(false);
    }
  };

  const submit = useCallback(async (automatic = false) => {
    if (!attempt || submittedRef.current) return;
    submittedRef.current = true;
    setSubmitting(true);
    try {
      await autosave.flushNow();
      await submitAttempt(attempt.id);
    } catch (error) {
      const message = errorMessage(error, '');
      if (!/already submitted/i.test(message)) {
        submittedRef.current = false;
        setSubmitting(false);
        toast.error(message || 'Could not submit. Your answers are saved - please try again.');
        return;
      }
    }
    autosave.clearLocal();
    try { localStorage.removeItem(`exam_flags_${attempt.id}`); } catch { /* ignore */ }
    if (automatic) toast.info('Time is up. Your answers have been submitted.');
    navigate(`/exam/result/${attempt.id}`, { replace: true });
  }, [attempt, autosave, navigate]);

  // Time warnings, and submission when the clock reaches zero.
  useEffect(() => {
    const remaining = clock.remaining;
    if (remaining === null || !attempt) return;
    WARNINGS_AT.forEach((mark) => {
      if (remaining <= mark && remaining > mark - 10 && !warned.current.has(mark)) {
        warned.current.add(mark);
        toast.warning(mark >= 120 ? `${mark / 60} minutes left` : '1 minute left');
      }
    });
    if (remaining === 0) void submit(true);
  }, [clock.remaining, attempt, submit]);

  // Record, don't punish: leaving the tab is counted and shown, never used to
  // cancel the attempt - a notification or a second monitor can trigger it.
  useEffect(() => {
    if (!attempt) return;
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') setFocusLosses((n) => n + 1);
    };
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (submittedRef.current) return;
      event.preventDefault();
      event.returnValue = '';
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('beforeunload', onBeforeUnload);
    };
  }, [attempt]);

  const locations = useMemo(() => {
    const map = new Map<number, { section: number; group: number }>();
    content?.sections.forEach((section, sectionIdx) => {
      section.groups.forEach((group) => {
        group.questions.forEach((question) => {
          map.set(question.number, { section: sectionIdx, group: group.id });
        });
      });
    });
    return map;
  }, [content]);

  const numbersBySection = useMemo(
    () => (content?.sections ?? []).map((section) =>
      section.groups.flatMap((group) => group.questions.map((q) => q.number)).sort((a, b) => a - b)),
    [content],
  );

  const allNumbers = useMemo(() => numbersBySection.flat(), [numbersBySection]);
  const unanswered = allNumbers.filter((n) => !isAnswered(autosave.answers[n])).length;

  const jumpTo = (number: number) => {
    const location = locations.get(number);
    if (!location) return;
    setSectionIndex(location.section);
    setCurrentQuestion(number);
    window.requestAnimationFrame(() => {
      document.querySelector(`[data-group="${location.group}"]`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  const toggleFlag = () => {
    if (currentQuestion === null || !attempt) return;
    setFlagged((previous) => {
      const next = new Set(previous);
      if (next.has(currentQuestion)) next.delete(currentQuestion);
      else next.add(currentQuestion);
      try { localStorage.setItem(`exam_flags_${attempt.id}`, JSON.stringify([...next])); } catch { /* ignore */ }
      return next;
    });
  };

  const handlePartChange = useCallback((index: number) => {
    setSectionIndex(index);
    if (attempt) advanceSection(attempt.id, index + 1).catch(() => undefined);
  }, [attempt]);

  // ------------------------------------------------------------------ start

  if (!attempt || !content) {
    const skill = summary?.skill;
    const SkillIcon = skill === 'listening' ? Headphones : BookOpen;
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <Card className="w-full max-w-lg">
          <CardContent className="space-y-5 py-8">
            <div className="flex items-center gap-3">
              <div className="rounded-xl bg-primary/10 p-2">
                <SkillIcon className="h-6 w-6 text-primary" />
              </div>
              <div>
                <h1 className="text-xl font-semibold">
                  {summary ? `${summary.book} · Test ${summary.test_number}` : 'IELTS test'}
                </h1>
                <p className="text-sm capitalize text-muted-foreground">{skill ?? ''}</p>
              </div>
            </div>

            {summary && (
              <ul className="space-y-1 text-sm text-muted-foreground">
                <li>{summary.total_questions} questions</li>
                <li>{Math.round(summary.duration_seconds / 60)} minutes, timed from when you start</li>
                <li>Answers save automatically as you go</li>
              </ul>
            )}

            {skill === 'listening' && (
              <div className="grid grid-cols-2 gap-2">
                {(['exam', 'practice'] as AttemptMode[]).map((option) => (
                  <Button
                    key={option}
                    type="button"
                    variant={mode === option ? 'default' : 'outline'}
                    onClick={() => setMode(option)}
                  >
                    {option === 'exam' ? 'Exam mode' : 'Practice mode'}
                  </Button>
                ))}
                <p className="col-span-2 text-xs text-muted-foreground">
                  {mode === 'exam'
                    ? 'The recording plays once, straight through. Only volume can be changed.'
                    : 'You can pause, seek and skip. The result is labelled as practice.'}
                </p>
              </div>
            )}

            {loadError && (
              <p className="flex items-start gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {loadError}
              </p>
            )}

            <div className="flex gap-2">
              <Button variant="outline" onClick={() => navigate(skill ? `/${skill}` : '/')}>
                Back
              </Button>
              <Button className="flex-1" onClick={begin} disabled={starting}>
                {starting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                Start or resume
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ----------------------------------------------------------------- running

  const isListening = content.skill === 'listening';
  const section = content.sections[sectionIndex];
  const remaining = clock.remaining;

  const questions = (
    <div className="space-y-10">
      {section?.groups.map((group) => (
        <GroupRenderer
          key={group.id}
          group={group}
          answers={autosave.answers}
          onChange={autosave.setAnswer}
          onFocusQuestion={setCurrentQuestion}
        />
      ))}
    </div>
  );

  const preventCopy = (event: React.ClipboardEvent) => {
    if (attempt.mode === 'exam') event.preventDefault();
  };

  return (
    <div className="flex h-screen flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b bg-card px-4">
        <div className="flex min-w-0 items-center gap-2">
          {isListening
            ? <Headphones className="h-4 w-4 shrink-0 text-primary" />
            : <BookOpen className="h-4 w-4 shrink-0 text-primary" />}
          <span className="truncate font-heading font-semibold">
            {content.book} · Test {content.test_number}
          </span>
          {attempt.mode === 'practice' && <Badge variant="secondary">Practice</Badge>}
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          <SaveIndicator state={autosave.state} savedAt={autosave.savedAt} />
          <span
            className={cn(
              'flex items-center gap-1 rounded px-2 py-1 font-mono text-sm tabular-nums',
              remaining !== null && remaining <= 300
                ? 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300'
                : remaining !== null && remaining <= 600
                  ? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'
                  : 'bg-muted',
            )}
            aria-label="Time remaining"
          >
            <Clock className="h-4 w-4" /> {formatClock(remaining)}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={currentQuestion === null}
            onClick={toggleFlag}
            title="Flag the question you are on for review"
          >
            <Flag className={cn('h-4 w-4 sm:mr-1', currentQuestion !== null && flagged.has(currentQuestion) && 'fill-amber-400 text-amber-500')} />
            <span className="hidden sm:inline">Flag</span>
          </Button>
          <Button size="sm" onClick={() => setConfirmOpen(true)} disabled={submitting}>
            {submitting ? <Loader2 className="h-4 w-4 animate-spin sm:mr-1" /> : <Send className="h-4 w-4 sm:mr-1" />}
            <span className="hidden sm:inline">Submit</span>
          </Button>
        </div>
      </header>

      {focusLosses > 0 && attempt.mode === 'exam' && (
        <div className="shrink-0 bg-amber-50 px-4 py-1 text-center text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200">
          You have left the test window {focusLosses} time{focusLosses === 1 ? '' : 's'}.
        </div>
      )}

      {isListening && (
        <div className="shrink-0 border-b bg-card/60 px-4 py-3">
          <LockedAudioPlayer
            attemptId={attempt.id}
            sections={content.sections}
            mode={attempt.mode}
            startIndex={sectionIndex}
            onPartChange={handlePartChange}
            onFinished={() => setAudioFinished(true)}
          />
        </div>
      )}

      <nav className="flex shrink-0 gap-1 overflow-x-auto border-b px-4 py-2">
        {content.sections.map((item, index) => (
          <Button
            key={item.id}
            size="sm"
            variant={index === sectionIndex ? 'default' : 'ghost'}
            onClick={() => setSectionIndex(index)}
          >
            {item.label || `${isListening ? 'Part' : 'Passage'} ${item.order}`}
          </Button>
        ))}
        {audioFinished && (
          <span className="ml-auto self-center text-xs font-medium text-primary">
            Transfer time - check your answers
          </span>
        )}
      </nav>

      <div className="min-h-0 flex-1">
        {isListening ? (
          <div className="h-full overflow-y-auto">
            <div className="mx-auto max-w-3xl p-6">{questions}</div>
          </div>
        ) : isMobile ? (
          <div className="h-full space-y-8 overflow-y-auto p-4">
            <details open className="rounded-lg border p-3" onCopy={preventCopy}>
              <summary className="cursor-pointer text-sm font-medium">Passage</summary>
              <div className="mt-3">{section && <Passage section={section} />}</div>
            </details>
            {questions}
          </div>
        ) : (
          <ResizablePanelGroup direction="horizontal" className="h-full">
            <ResizablePanel defaultSize={50} minSize={25}>
              <div className="h-full overflow-y-auto p-6" onCopy={preventCopy}>
                {section && <Passage section={section} />}
              </div>
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={50} minSize={30}>
              <div className="h-full overflow-y-auto p-6">{questions}</div>
            </ResizablePanel>
          </ResizablePanelGroup>
        )}
      </div>

      <footer className="shrink-0 overflow-x-auto border-t bg-card px-3 py-2">
        <div className="flex min-w-max gap-5">
          {content.sections.map((item, index) => (
            <div key={item.id} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setSectionIndex(index)}
                className={cn(
                  'mr-1 text-xs font-medium',
                  index === sectionIndex ? 'text-primary' : 'text-muted-foreground',
                )}
              >
                {item.label || `Section ${item.order}`}
              </button>
              {numbersBySection[index].map((number) => (
                <button
                  key={number}
                  type="button"
                  onClick={() => jumpTo(number)}
                  title={`Question ${number}${flagged.has(number) ? ' (flagged)' : ''}`}
                  className={cn(
                    'h-7 w-7 rounded border text-xs tabular-nums transition-colors',
                    isAnswered(autosave.answers[number])
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'bg-background hover:bg-muted',
                    flagged.has(number) && 'ring-2 ring-amber-400',
                    currentQuestion === number && 'outline outline-2 outline-offset-1 outline-foreground',
                  )}
                >
                  {number}
                </button>
              ))}
            </div>
          ))}
        </div>
      </footer>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Submit your answers?</AlertDialogTitle>
            <AlertDialogDescription>
              {unanswered > 0
                ? `${unanswered} question${unanswered === 1 ? ' is' : 's are'} still unanswered. `
                : 'Every question has an answer. '}
              {flagged.size > 0 && `${flagged.size} flagged for review. `}
              You cannot change anything after submitting.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep working</AlertDialogCancel>
            <AlertDialogAction onClick={() => void submit(false)}>Submit</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default ExamRunner;
