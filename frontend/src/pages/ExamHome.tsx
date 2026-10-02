import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { BookOpen, Clock, Headphones, ListChecks, ArrowRight, History, Trophy } from 'lucide-react';
import Layout from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { useThemeContext } from '@/contexts/ThemeContext';
import {
  errorMessage, listAttempts, listTests,
  type AttemptMode, type AttemptState, type ModuleSummary, type Skill,
} from '@/lib/exams';

const COPY: Record<Skill, { title: string; subtitle: string; icon: typeof BookOpen }> = {
  reading: {
    title: 'Reading Practice',
    subtitle: 'Three passages, forty questions, sixty minutes',
    icon: BookOpen,
  },
  listening: {
    title: 'Listening Practice',
    subtitle: 'Four recorded parts, forty questions',
    icon: Headphones,
  },
};

const MODES: { id: AttemptMode; title: string; description: string }[] = [
  {
    id: 'exam',
    title: 'Exam mode',
    description: 'Like the real test: the recording plays once, straight through. Volume only.',
  },
  {
    id: 'practice',
    title: 'Practice mode',
    description: 'Pause, seek and skip 5 seconds. Your result is marked as practice.',
  },
];

const ExamHome = ({ skill }: { skill: Skill }) => {
  const navigate = useNavigate();
  const { setStudyMode } = useThemeContext();
  const [tests, setTests] = useState<ModuleSummary[] | null>(null);
  const [attempts, setAttempts] = useState<AttemptState[]>([]);
  const [error, setError] = useState('');
  const [choosing, setChoosing] = useState<ModuleSummary | null>(null);

  const { title, subtitle, icon: Icon } = COPY[skill];

  useEffect(() => { setStudyMode(skill); }, [skill, setStudyMode]);

  useEffect(() => {
    let cancelled = false;
    setTests(null);
    setError('');
    Promise.all([listTests(skill), listAttempts()])
      .then(([testResponse, attemptResponse]) => {
        if (cancelled) return;
        setTests(testResponse.tests);
        setAttempts(attemptResponse.attempts.filter((a) => a.module.skill === skill));
      })
      .catch((err) => { if (!cancelled) setError(errorMessage(err, 'Could not load tests.')); });
    return () => { cancelled = true; };
  }, [skill]);

  const byBook = useMemo(() => {
    const groups = new Map<string, ModuleSummary[]>();
    (tests ?? []).forEach((test) => {
      const list = groups.get(test.book) ?? [];
      list.push(test);
      groups.set(test.book, list);
    });
    groups.forEach((list) => list.sort((a, b) => a.test_number - b.test_number));
    return [...groups.entries()];
  }, [tests]);

  const inProgress = useMemo(
    () => new Set(attempts.filter((a) => a.status === 'in_progress').map((a) => a.module.id)),
    [attempts],
  );

  const open = (test: ModuleSummary) => {
    if (skill === 'listening') setChoosing(test);
    else navigate(`/exam/${test.id}`);
  };

  const recent = attempts.filter((a) => a.status !== 'in_progress').slice(0, 8);

  return (
    <Layout>
      <div className="container mx-auto max-w-4xl px-4 py-8">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <div className="mb-8 flex items-center gap-3">
            <div className="rounded-xl bg-primary/10 p-2">
              <Icon className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-foreground">{title}</h1>
              <p className="text-muted-foreground">{subtitle}</p>
            </div>
          </div>

          {error && (
            <Card className="border-destructive/40">
              <CardContent className="py-6 text-sm text-destructive">{error}</CardContent>
            </Card>
          )}

          {!error && tests === null && (
            <div className="grid gap-3 sm:grid-cols-2">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
            </div>
          )}

          {tests !== null && tests.length === 0 && (
            <Card>
              <CardContent className="py-10 text-center text-muted-foreground">
                No {skill} tests are available yet. They appear here once an administrator
                has imported a book and verified its answer key.
              </CardContent>
            </Card>
          )}

          {byBook.map(([book, list]) => (
            <section key={book} className="mb-8">
              <h2 className="mb-3 text-lg font-semibold">{book}</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {list.map((test, i) => (
                  <motion.div
                    key={test.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                  >
                    <Card
                      role="button"
                      tabIndex={0}
                      onClick={() => open(test)}
                      onKeyDown={(event) => { if (event.key === 'Enter') open(test); }}
                      className="group cursor-pointer border-border/50 transition-all hover:border-primary/40 hover:glow-sm"
                    >
                      <CardContent className="flex items-center gap-4 py-5">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-lg font-semibold group-hover:text-primary">
                              Test {test.test_number}
                            </span>
                            {inProgress.has(test.id) && <Badge variant="secondary">In progress</Badge>}
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <span className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5">
                              <ListChecks className="h-3 w-3" /> {test.total_questions} questions
                            </span>
                            <span className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5">
                              <Clock className="h-3 w-3" /> {Math.round(test.duration_seconds / 60)} min
                            </span>
                            {test.best_band && (
                              <span className="flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-primary">
                                <Trophy className="h-3 w-3" /> Best {test.best_band}
                              </span>
                            )}
                          </div>
                        </div>
                        <ArrowRight className="h-5 w-5 text-muted-foreground transition-all group-hover:translate-x-1 group-hover:text-primary" />
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </section>
          ))}

          {recent.length > 0 && (
            <section className="mt-10">
              <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
                <History className="h-4 w-4" /> Recent attempts
              </h2>
              <Card>
                <CardContent className="divide-y p-0">
                  {recent.map((attempt) => (
                    <button
                      key={attempt.id}
                      type="button"
                      onClick={() => navigate(`/exam/result/${attempt.id}`)}
                      className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-muted/50"
                    >
                      <span>
                        {attempt.module.book} · Test {attempt.module.test_number}
                        {attempt.mode === 'practice' && (
                          <Badge variant="outline" className="ml-2">Practice</Badge>
                        )}
                      </span>
                      <span className="flex items-center gap-3 text-muted-foreground">
                        {attempt.submitted_at && new Date(attempt.submitted_at).toLocaleDateString()}
                        <span className="font-semibold text-foreground">
                          {attempt.band ? `Band ${attempt.band}` : `${attempt.raw_score ?? 0}/40`}
                        </span>
                      </span>
                    </button>
                  ))}
                </CardContent>
              </Card>
            </section>
          )}
        </motion.div>
      </div>

      <Dialog open={choosing !== null} onOpenChange={(open_) => { if (!open_) setChoosing(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {choosing ? `${choosing.book} · Test ${choosing.test_number}` : 'Choose a mode'}
            </DialogTitle>
            <DialogDescription>
              How should the recording play? The timer starts as soon as you begin.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            {MODES.map((mode) => (
              <Card
                key={mode.id}
                role="button"
                tabIndex={0}
                className="cursor-pointer transition-colors hover:border-primary/50"
                onClick={() => choosing && navigate(`/exam/${choosing.id}?mode=${mode.id}`)}
              >
                <CardContent className="py-4">
                  <div className="font-semibold">{mode.title}</div>
                  <p className="text-sm text-muted-foreground">{mode.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </Layout>
  );
};

export default ExamHome;
