import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, CheckCircle2, Flag, Info, Loader2, MinusCircle, RotateCcw, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import KeyCrop from '@/components/admin/KeyCrop';
import GroupRenderer from '@/components/exam/GroupRenderer';
import PassagePages from '@/components/exam/PassagePages';
import { isAdminUser } from '@/lib/auth';
import { useThemeContext } from '@/contexts/ThemeContext';
import {
  correctAnswerAfterAttempt, errorMessage, getAttempt, getResult,
  type AnswerValue, type AttemptState, type ExamResult as ExamResultData,
  type ModuleContent, type ResultRow,
} from '@/lib/exams';
import { cn } from '@/lib/utils';

type Filter = 'all' | 'incorrect' | 'blank';

const REASON_LABELS: Record<ResultRow['reason'], string> = {
  correct: 'Correct',
  wrong: 'Incorrect',
  blank: 'Not answered',
  over_word_limit: 'Exceeded the word limit',
  over_selected: 'Too many options chosen',
  partial: 'Partly correct',
};

function matches(row: ResultRow, filter: Filter): boolean {
  if (filter === 'all') return true;
  if (filter === 'blank') return row.reason === 'blank';
  return !row.is_correct && row.reason !== 'blank';
}

const ExamResult = () => {
  const { attemptId } = useParams();
  const id = Number(attemptId);
  const navigate = useNavigate();
  const { setStudyMode } = useThemeContext();

  const [attempt, setAttempt] = useState<AttemptState | null>(null);
  const [content, setContent] = useState<ModuleContent | null>(null);
  const [result, setResult] = useState<ExamResultData | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  // Staff who sat the test blind can fix a key the importer misread, here,
  // against the book's own key row. Everyone's attempts are re-marked.
  const canFixKey = isAdminUser();
  const [fixing, setFixing] = useState<ResultRow | null>(null);
  const [fixValue, setFixValue] = useState('');
  const [savingFix, setSavingFix] = useState(false);

  const openFix = (row: ResultRow) => {
    setFixing(row);
    setFixValue(row.accepted.join(' / '));
  };

  const saveFix = async () => {
    if (!fixing || !attempt) return;
    if (!fixValue.trim()) { toast.error('Type the correct answer.'); return; }
    setSavingFix(true);
    try {
      const response = await correctAnswerAfterAttempt(attempt.module.id, fixing.number, fixValue.trim());
      toast.success(
        `Key for question ${fixing.number} corrected` +
        (response.remarked_attempts ? `; ${response.remarked_attempts} attempt(s) re-marked.` : '.'),
      );
      setFixing(null);
      setResult(await getResult(id));
    } catch (err) {
      toast.error(errorMessage(err, 'Could not correct the key.'));
    } finally {
      setSavingFix(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const detail = await getAttempt(id);
        if (cancelled) return;
        if (detail.attempt.status === 'in_progress') {
          // Results only exist once the attempt is submitted.
          navigate(`/exam/${detail.attempt.module.id}`, { replace: true });
          return;
        }
        setAttempt(detail.attempt);
        setContent(detail.content ?? null);
        setStudyMode(detail.attempt.module.skill);
        const marked = await getResult(id);
        if (!cancelled) setResult(marked);
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, 'Could not load this result.'));
      }
    })();
    return () => { cancelled = true; };
  }, [id, navigate, setStudyMode]);

  const marks = useMemo(() => {
    const map: Record<number, { is_correct: boolean; accepted: string[]; reason: string }> = {};
    result?.rows.forEach((row) => { map[row.number] = row; });
    return map;
  }, [result]);

  const answers = useMemo(() => {
    const map: Record<number, AnswerValue> = {};
    Object.entries(attempt?.answers ?? {}).forEach(([number, value]) => { map[Number(number)] = value; });
    return map;
  }, [attempt]);

  const visibleNumbers = useMemo(
    () => new Set((result?.rows ?? []).filter((row) => matches(row, filter)).map((row) => row.number)),
    [result, filter],
  );

  if (error) {
    return (
      <Layout>
        <div className="container mx-auto max-w-3xl px-4 py-10">
          <Card><CardContent className="py-8 text-destructive">{error}</CardContent></Card>
        </div>
      </Layout>
    );
  }

  if (!attempt || !result) {
    return (
      <Layout>
        <div className="container mx-auto max-w-4xl space-y-4 px-4 py-10">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-96 rounded-xl" />
        </div>
      </Layout>
    );
  }

  const skill = attempt.module.skill;
  const rows = result.rows.filter((row) => matches(row, filter));

  return (
    <Layout>
      <div className="container mx-auto max-w-4xl space-y-8 px-4 py-8">
        <Button variant="ghost" size="sm" onClick={() => navigate(`/${skill}`)}>
          <ArrowLeft className="mr-1 h-4 w-4" /> Back to {skill}
        </Button>

        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="overflow-hidden">
            <CardContent className="flex flex-col gap-6 py-8 sm:flex-row sm:items-center">
              <div className="text-center sm:w-44">
                <div className="text-sm text-muted-foreground">
                  {result.mode === 'practice' ? 'Practice band' : 'Band'}
                </div>
                <div className="font-heading text-6xl font-bold text-primary">
                  {result.band ?? '—'}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {result.raw_score ?? 0} / {result.total_questions}
                </div>
              </div>
              <div className="flex-1 space-y-4">
                <div>
                  <h1 className="text-2xl font-semibold">
                    {attempt.module.book} · Test {attempt.module.test_number}
                  </h1>
                  <p className="text-sm capitalize text-muted-foreground">
                    {skill}
                    {result.mode === 'practice' && <Badge variant="secondary" className="ml-2">Practice</Badge>}
                    {result.status === 'expired' && <Badge variant="outline" className="ml-2">Submitted when time ran out</Badge>}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 text-sm">
                  <span className="flex items-center gap-1 rounded-full bg-emerald-100 px-3 py-1 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                    <CheckCircle2 className="h-4 w-4" /> {result.correct} correct
                  </span>
                  <span className="flex items-center gap-1 rounded-full bg-red-100 px-3 py-1 text-red-800 dark:bg-red-950 dark:text-red-300">
                    <XCircle className="h-4 w-4" /> {result.wrong} incorrect
                  </span>
                  <span className="flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-muted-foreground">
                    <MinusCircle className="h-4 w-4" /> {result.blank} not answered
                  </span>
                </div>
                {result.indicative && (
                  <p className="flex items-start gap-2 text-xs text-muted-foreground">
                    <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    This band is indicative. Cambridge adjusts the raw-score conversion for each
                    test and does not publish exact tables.
                  </p>
                )}
                <Button size="sm" variant="outline" onClick={() => navigate(`/exam/${attempt.module.id}`)}>
                  <RotateCcw className="mr-1 h-4 w-4" /> Take this test again
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <Tabs value={filter} onValueChange={(value) => setFilter(value as Filter)}>
          <TabsList>
            <TabsTrigger value="all">All ({result.rows.length})</TabsTrigger>
            <TabsTrigger value="incorrect">Incorrect ({result.wrong})</TabsTrigger>
            <TabsTrigger value="blank">Not answered ({result.blank})</TabsTrigger>
          </TabsList>
        </Tabs>

        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>Your answer</TableHead>
                  <TableHead>Accepted answer</TableHead>
                  <TableHead className="hidden sm:table-cell">Result</TableHead>
                  {canFixKey && <TableHead className="w-10"><span className="sr-only">Fix key</span></TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.number}>
                    <TableCell className="font-medium tabular-nums">{row.number}</TableCell>
                    <TableCell>
                      <span className={cn(
                        'rounded px-2 py-0.5 text-sm',
                        row.is_correct
                          ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                          : row.reason === 'blank'
                            ? 'text-muted-foreground'
                            : 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
                      )}>
                        {row.response || '—'}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm">
                      {row.accepted.length ? row.accepted.join(' / ') : '—'}
                    </TableCell>
                    <TableCell className="hidden text-sm text-muted-foreground sm:table-cell">
                      {REASON_LABELS[row.reason] ?? row.reason}
                    </TableCell>
                    {canFixKey && (
                      <TableCell>
                        {!row.is_correct && (
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7"
                            onClick={() => openFix(row)}
                            title="Key looks wrong? Check it against the book"
                            aria-label={`Check the key for question ${row.number}`}
                          >
                            <Flag className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
                {rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={canFixKey ? 5 : 4} className="py-6 text-center text-muted-foreground">
                      Nothing to show for this filter.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {content && (
          <section className="space-y-6">
            <h2 className="text-xl font-semibold">Questions</h2>
            {content.sections.map((section) => {
              const groups = section.groups.filter((group) =>
                group.questions.some((question) => visibleNumbers.has(question.number)));
              if (groups.length === 0) return null;
              return (
                <Card key={section.id}>
                  <CardContent className="space-y-8 py-6">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">{section.label}</p>
                      {section.title && <h3 className="text-lg font-semibold">{section.title}</h3>}
                    </div>
                    {skill === 'reading' && (section.passage_pages?.length > 0 || section.passage_html) && (
                      <details className="rounded-lg border p-3">
                        <summary className="cursor-pointer text-sm font-medium">Show the passage</summary>
                        {section.passage_pages?.length > 0 ? (
                          <div className="mx-auto mt-3 max-w-3xl">
                            <PassagePages section={section} />
                          </div>
                        ) : (
                          <div className="mt-3 space-y-3 text-sm leading-6">
                            {section.passage_html.split(/\n+/).filter(Boolean).map((text, index) => (
                              <p key={index}>{text}</p>
                            ))}
                          </div>
                        )}
                      </details>
                    )}
                    {groups.map((group) => (
                      <GroupRenderer
                        key={group.id}
                        group={group}
                        answers={answers}
                        onChange={() => undefined}
                        readOnly
                        marks={marks}
                      />
                    ))}
                  </CardContent>
                </Card>
              );
            })}
          </section>
        )}
      </div>

      {canFixKey && (
        <Dialog open={fixing !== null} onOpenChange={(open) => { if (!open) setFixing(null); }}>
          <DialogContent className="max-w-xl">
            <DialogHeader>
              <DialogTitle>Key looks wrong? Question {fixing?.number}</DialogTitle>
              <DialogDescription>
                This is the book's printed key row. If the accepted answer was misread, correct it -
                every submitted attempt on this test is re-marked.
              </DialogDescription>
            </DialogHeader>
            {fixing && (
              <div className="space-y-3">
                <KeyCrop moduleId={attempt.module.id} number={fixing.number} />
                <div className="text-sm">
                  You answered <span className="font-medium">{fixing.response || '—'}</span>.
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor="fix-answer">Accepted answer</label>
                  <Input
                    id="fix-answer"
                    value={fixValue}
                    onChange={(event) => setFixValue(event.target.value)}
                    spellCheck={false}
                    placeholder="Separate alternatives with a slash, e.g. 10 / ten"
                  />
                </div>
              </div>
            )}
            <DialogFooter className="gap-2 sm:gap-0">
              <Button variant="ghost" onClick={() => setFixing(null)}>Cancel</Button>
              <Button
                onClick={() => void saveFix()}
                disabled={savingFix || !fixing || fixValue.trim() === fixing.accepted.join(' / ')}
              >
                {savingFix && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Correct the key
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </Layout>
  );
};

export default ExamResult;
