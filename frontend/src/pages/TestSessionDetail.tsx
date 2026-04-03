import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import Layout from '@/components/Layout';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchJson } from '@/lib/backend';

type WritingDetail = {
  id: number;
  task_type: 'task1' | 'task2';
  prompt: string;
  essay_text: string;
  scores: Record<string, number>;
  examiner_comments: string;
  corrections: Array<{ error: string; correction: string }>;
  word_count: number;
  created_at: string;
};

type SpeakingDetail = {
  id: number;
  part: string;
  status: string;
  scores: Record<string, number>;
  final_report: {
    examiner_comments?: string;
  };
  transcript: string;
  created_at: string;
};

const writingLabels: Record<string, string> = {
  ta: 'Task Achievement',
  tr: 'Task Response',
  cc: 'Coherence & Cohesion',
  lr: 'Lexical Resource',
  gra: 'Grammatical Range & Accuracy',
};

const speakingLabels: Record<string, string> = {
  fc: 'Fluency & Coherence',
  lr: 'Lexical Resource',
  gra: 'Grammatical Range & Accuracy',
};

const formatDate = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const TestSessionDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isWriting, setIsWriting] = useState(true);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [summary, setSummary] = useState('');
  const [meta, setMeta] = useState('');
  const [bodyText, setBodyText] = useState('');

  useEffect(() => {
    let mounted = true;

    const run = async () => {
      if (!id) {
        setError('Missing session id');
        setLoading(false);
        return;
      }

      const [kind, rawId] = id.split('-');
      if (!kind || !rawId || Number.isNaN(Number(rawId))) {
        setError('Invalid session id format');
        setLoading(false);
        return;
      }

      try {
        if (kind === 'w') {
          const data = await fetchJson<WritingDetail>(`/api/writing/evaluate/${rawId}`);
          if (!mounted) return;

          setIsWriting(true);
          setScores(data.scores || {});
          setSummary(data.examiner_comments || 'No examiner comments.');
          setMeta(`Writing ${data.task_type === 'task1' ? 'Task 1' : 'Task 2'} - ${formatDate(data.created_at)}`);
          setBodyText(data.essay_text || 'No essay text available.');
        } else if (kind === 's') {
          const data = await fetchJson<SpeakingDetail>(`/api/speaking/sessions/${rawId}`);
          if (!mounted) return;

          setIsWriting(false);
          setScores(data.scores || {});
          setSummary(data.final_report?.examiner_comments || 'No examiner comments.');
          setMeta(`Speaking Part ${data.part} - ${formatDate(data.created_at)}`);
          setBodyText(data.transcript || 'No transcript available.');
        } else {
          throw new Error('Unknown session type');
        }
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : 'Failed to load session');
      } finally {
        if (mounted) setLoading(false);
      }
    };

    run();
    return () => {
      mounted = false;
    };
  }, [id]);

  const criteria = useMemo(() => {
    const labels = isWriting ? writingLabels : speakingLabels;
    return Object.entries(scores)
      .filter(([key]) => key !== 'overall_band')
      .map(([key, score]) => ({
        name: labels[key] || key.toUpperCase(),
        score: Number(score || 0),
      }));
  }, [isWriting, scores]);

  const overall = Number(scores?.overall_band || 0).toFixed(1);

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 max-w-3xl relative">
        <div className="absolute w-72 h-72 bg-primary/5 rounded-full blur-3xl -top-20 right-0 pointer-events-none" />

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="relative z-10">
          <Button variant="ghost" onClick={() => navigate('/')} className="gap-2 mb-6">
            <ArrowLeft className="h-4 w-4" /> Back to Dashboard
          </Button>

          {loading && <p className="text-muted-foreground">Loading session...</p>}
          {error && <p className="text-destructive">{error}</p>}

          {!loading && !error && (
            <>
              <div className="flex items-center justify-between mb-8">
                <div>
                  <h1 className="text-3xl font-bold text-foreground">Session Details</h1>
                  <p className="text-muted-foreground mt-1">{meta}</p>
                </div>
                <motion.div
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: 'spring', delay: 0.3 }}
                  className="text-center p-4 rounded-2xl bg-primary/10 glow"
                >
                  <p className="text-4xl font-bold text-primary">{overall}</p>
                  <p className="text-xs text-muted-foreground font-medium">Overall Band</p>
                </motion.div>
              </div>

              <div className="grid md:grid-cols-2 gap-4 mb-8">
                {criteria.map((c, i) => (
                  <motion.div key={c.name} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.08 }}>
                    <Card className="overflow-hidden relative group hover:glow-sm transition-shadow">
                      <div className="absolute bottom-0 left-0 h-1 bg-primary rounded-full transition-all" style={{ width: `${(c.score / 9) * 100}%` }} />
                      <CardContent className="flex items-center justify-between py-5">
                        <span className="text-sm font-medium text-foreground">{c.name}</span>
                        <span className="text-xl font-bold text-primary">{c.score.toFixed(1)}</span>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>

              <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
                <Card className="overflow-hidden relative mb-4">
                  <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent pointer-events-none" />
                  <CardHeader className="relative z-10">
                    <CardTitle className="flex items-center gap-2">
                      <TrendingUp className="h-5 w-5 text-primary" />
                      Examiner Feedback
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="relative z-10">
                    <p className="text-sm text-foreground whitespace-pre-wrap">{summary}</p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>{isWriting ? 'Submitted Essay' : 'Test Transcript'}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-foreground whitespace-pre-wrap">{bodyText}</p>
                  </CardContent>
                </Card>
              </motion.div>
            </>
          )}
        </motion.div>
      </div>
    </Layout>
  );
};

export default TestSessionDetail;
