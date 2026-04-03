import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import Layout from '@/components/Layout';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchJson } from '@/lib/backend';

type WritingResponse = {
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

const labelMap: Record<string, string> = {
  ta: 'Task Achievement',
  tr: 'Task Response',
  cc: 'Coherence & Cohesion',
  lr: 'Lexical Resource',
  gra: 'Grammatical Range & Accuracy',
};

const WritingEvaluation = () => {
  const { id } = useParams();
  const [data, setData] = useState<WritingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const run = async () => {
      if (!id) {
        setError('Missing evaluation id');
        setLoading(false);
        return;
      }

      try {
        const response = await fetchJson<WritingResponse>(`/api/writing/evaluate/${id}`);
        setData(response);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load evaluation');
      } finally {
        setLoading(false);
      }
    };

    run();
  }, [id]);

  const scoreRows = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.scores)
      .filter(([key]) => key !== 'overall_band')
      .map(([key, score]) => ({ key, label: labelMap[key] || key.toUpperCase(), score }));
  }, [data]);

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 relative">
        <div className="absolute w-72 h-72 bg-primary/5 rounded-full blur-3xl -top-20 right-0 pointer-events-none" />

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="relative z-10">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-primary/10">
                <Sparkles className="h-6 w-6 text-primary" />
              </div>
              <h1 className="text-3xl font-bold text-foreground">Essay Evaluation</h1>
            </div>
            <Button variant="outline" onClick={() => navigate('/writing')}>Back to Writing</Button>
          </div>

          {loading && <p className="text-muted-foreground">Loading evaluation...</p>}
          {error && <p className="text-destructive">{error}</p>}

          {data && (
            <div className="grid lg:grid-cols-2 gap-6">
              <Card className="h-full">
                <CardHeader>
                  <CardTitle>Your Essay</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-2">Prompt</p>
                  <p className="text-sm mb-4">{data.prompt}</p>
                  <p className="text-foreground leading-relaxed whitespace-pre-wrap text-sm">{data.essay_text}</p>
                  <p className="text-xs text-muted-foreground mt-4 bg-muted px-3 py-1.5 rounded-full inline-block">{data.word_count} words</p>
                </CardContent>
              </Card>

              <div className="space-y-6">
                <Card className="overflow-hidden relative">
                  <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent pointer-events-none" />
                  <CardContent className="py-6 text-center relative z-10">
                    <p className="text-5xl font-bold text-primary glow-sm inline-block">{Number(data.scores.overall_band || 0).toFixed(1)}</p>
                    <p className="text-sm text-muted-foreground mt-1 font-medium">Overall Band Score</p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader><CardTitle>Score Breakdown</CardTitle></CardHeader>
                  <CardContent className="space-y-4">
                    {scoreRows.map((row) => (
                      <div key={row.key} className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-foreground font-medium">{row.label}</span>
                          <span className="font-bold text-primary">{Number(row.score).toFixed(1)}</span>
                        </div>
                        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-primary rounded-full" style={{ width: `${(Number(row.score) / 9) * 100}%` }} />
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <CheckCircle2 className="h-5 w-5 text-primary" /> Examiner Comments
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-foreground leading-relaxed text-sm whitespace-pre-wrap">{data.examiner_comments}</p>
                    {!!data.corrections?.length && (
                      <div className="mt-4 space-y-2">
                        <p className="text-xs font-semibold text-muted-foreground">Corrections</p>
                        {data.corrections.map((c, i) => (
                          <p key={i} className="text-xs text-muted-foreground">{c.error} ({c.correction})</p>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          )}
        </motion.div>
      </div>
    </Layout>
  );
};

export default WritingEvaluation;