import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { PenTool, Mic, TrendingUp, BookOpen, Target, Award, ArrowUpRight, Flame } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import Layout from '@/components/Layout';
import { useThemeContext } from '@/contexts/ThemeContext';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { fetchJson } from '@/lib/backend';

type WritingSession = {
  id: number;
  task_type: 'task1' | 'task2';
  prompt: string;
  scores: Record<string, number>;
  word_count: number;
  created_at: string;
};

type SpeakingSession = {
  id: number;
  part: string;
  status: string;
  transcript: string;
  scores: Record<string, number>;
  created_at: string;
};

type SessionCard = {
  id: string;
  date: string;
  type: string;
  score: number;
  topic: string;
};

const formatBandScore = (score: number): number => {
  const floor = Math.floor(score);
  const fraction = score - floor;
  if (fraction < 0.5) return floor;
  if (fraction >= 0.7) return floor + 1;
  return floor + 0.5;
};

const toScore = (scores: Record<string, number> | undefined): number => {
  const value = Number(scores?.overall_band ?? 0);
  return Number.isFinite(value) ? formatBandScore(value) : 0;
};

const truncate = (value: string, maxLength = 80): string => {
  const text = (value || '').trim();
  if (!text) return 'No topic captured';
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}...` : text;
};

const formatDate = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
};

const buildChartData = (rows: SessionCard[], key: 'writing' | 'speaking') => {
  return rows
    .slice()
    .reverse()
    .slice(-6)
    .map((item, index) => ({
      date: `S${index + 1}`,
      [key]: item.score,
    }));
};

const Dashboard = () => {
  const { studyMode: activeView, setStudyMode: setActiveView } = useThemeContext();
  // The study mode is shared app-wide and can now be reading or listening, but this
  // page only has Writing and Speaking views. Anything else shows Writing rather
  // than silently falling through to the Speaking data.
  const dashboardView: 'writing' | 'speaking' = activeView === 'speaking' ? 'speaking' : 'writing';
  const navigate = useNavigate();

  const [writingSessions, setWritingSessions] = useState<SessionCard[]>([]);
  const [speakingSessions, setSpeakingSessions] = useState<SessionCard[]>([]);
  const [speakingFilter, setSpeakingFilter] = useState<'all' | '1' | '2' | '3'>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const [writing, speaking] = await Promise.all([
          fetchJson<{ results: WritingSession[] }>('/api/writing/sessions'),
          fetchJson<{ results: SpeakingSession[] }>('/api/speaking/sessions'),
        ]);

        if (!mounted) return;

        setWritingSessions(
          (writing.results || []).map((item) => ({
            id: `w-${item.id}`,
            date: formatDate(item.created_at),
            type: item.task_type === 'task1' ? 'Task 1' : 'Task 2',
            score: toScore(item.scores),
            topic: truncate(item.prompt),
          }))
        );

        setSpeakingSessions(
          (speaking.results || []).map((item) => ({
            id: `s-${item.id}`,
            date: formatDate(item.created_at),
            type: item.part === 'all' ? 'All Parts' : `Part ${item.part}`,
            score: toScore(item.scores),
            topic: truncate(item.transcript || 'Speaking test session'),
            rawPart: item.part,
          })) as (SessionCard & { rawPart: string })[]
        );
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : 'Failed to load sessions');
      } finally {
        if (mounted) setLoading(false);
      }
    };

    run();
    return () => {
      mounted = false;
    };
  }, []);

  const filteredSpeakingSessions = useMemo(() => {
    if (speakingFilter === 'all') return speakingSessions;
    return speakingSessions.filter(s => (s as any).rawPart === speakingFilter || (s as any).rawPart === 'all');
  }, [speakingSessions, speakingFilter]);

  const sessions = dashboardView === 'writing' ? writingSessions : filteredSpeakingSessions;
  const safeScores = sessions.map((s) => s.score).filter((s) => Number.isFinite(s) && s > 0);
  const rawAvg = safeScores.length ? (safeScores.reduce((a, s) => a + s, 0) / safeScores.length) : 0;
  const avgScore = safeScores.length ? formatBandScore(rawAvg).toFixed(1) : '0.0';
  const bestScore = safeScores.length ? Math.max(...safeScores).toFixed(1) : '0.0';
  const improvement = safeScores.length >= 2 ? `+${(safeScores[0] - safeScores[safeScores.length - 1]).toFixed(1)}` : '+0.0';

  const chartData = useMemo(() => buildChartData(sessions, dashboardView), [sessions, dashboardView]);

  const stats = [
    { label: 'Total Sessions', value: sessions.length, icon: BookOpen, color: 'from-primary/20 to-primary/5' },
    { label: 'Average Score', value: avgScore, icon: Target, color: 'from-primary/15 to-accent/10' },
    { label: 'Best Score', value: bestScore, icon: Award, color: 'from-accent/20 to-secondary/10' },
    { label: 'Improvement', value: improvement, icon: TrendingUp, color: 'from-primary/10 to-primary/5' },
  ];

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 relative">
        <div className="absolute w-96 h-96 bg-primary/5 rounded-full blur-3xl -top-40 -right-40 pointer-events-none" />

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-8 gap-4 relative z-10">
          <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-3xl font-bold text-foreground">Dashboard</h1>
              <motion.div animate={{ scale: [1, 1.2, 1] }} transition={{ repeat: Infinity, duration: 2 }}>
                <Flame className="h-6 w-6 text-primary" />
              </motion.div>
            </div>
            <p className="text-muted-foreground">Track your IELTS progress</p>
          </motion.div>
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="flex items-center gap-1 bg-muted/80 backdrop-blur-sm rounded-xl p-1.5 border border-border/50">
            {(['writing', 'speaking'] as const).map((view) => (
              <button
                key={view}
                onClick={() => setActiveView(view)}
                className={`relative px-5 py-2.5 rounded-lg text-sm font-medium transition-colors capitalize ${
                  dashboardView === view ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {dashboardView === view && (
                  <motion.div layoutId="dashboardTab" className="absolute inset-0 bg-primary rounded-lg glow-sm" transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }} />
                )}
                <span className="relative z-10 flex items-center gap-2">
                  {view === 'writing' ? <PenTool className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                  {view}
                </span>
              </button>
            ))}
          </motion.div>
        </div>

        {error && <p className="text-destructive mb-4">{error}</p>}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {stats.map((stat, i) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ delay: i * 0.08, type: 'spring' }}
              whileHover={{ y: -4, transition: { duration: 0.2 } }}
            >
              <Card className="overflow-hidden relative group hover:glow-sm transition-shadow">
                <div className={`absolute inset-0 bg-gradient-to-br ${stat.color} opacity-60`} />
                <CardContent className="pt-6 relative z-10">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-primary/10 group-hover:bg-primary/20 transition-colors">
                      <stat.icon className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <motion.p
                        key={`${stat.value}-${dashboardView}`}
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="text-2xl font-bold text-foreground"
                      >
                        {stat.value}
                      </motion.p>
                      <p className="text-xs text-muted-foreground">{stat.label}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <Card className="mb-8 overflow-hidden relative">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent pointer-events-none" />
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Progress Over Time
                <TrendingUp className="h-4 w-4 text-primary" />
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                  <YAxis domain={[4, 9]} stroke="hsl(var(--muted-foreground))" fontSize={12} />
                  <Tooltip
                    contentStyle={{
                      background: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '12px',
                      color: 'hsl(var(--foreground))',
                      boxShadow: '0 10px 30px -10px hsl(var(--primary) / 0.1)',
                    }}
                  />
                  <Area type="monotone" dataKey={dashboardView} stroke="hsl(var(--primary))" strokeWidth={2.5} fill="url(#colorGrad)" dot={{ fill: 'hsl(var(--primary))', strokeWidth: 2, r: 5 }} activeDot={{ r: 7, strokeWidth: 0 }} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="flex items-center justify-between mb-4"
        >
          <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
            Recent Sessions
            <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full font-normal">{sessions.length} total</span>
          </h2>
          
          {dashboardView === 'speaking' && (
            <div className="flex items-center gap-2 text-sm bg-muted/50 p-1 rounded-lg">
              {(['all', '1', '2', '3'] as const).map(filter => (
                <button
                  key={filter}
                  onClick={() => setSpeakingFilter(filter)}
                  className={`px-3 py-1 rounded-md transition-colors ${
                    speakingFilter === filter 
                      ? 'bg-primary text-primary-foreground shadow-sm' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                  }`}
                >
                  {filter === 'all' ? 'All' : `Part ${filter}`}
                </button>
              ))}
            </div>
          )}
        </motion.div>

        {loading && <p className="text-muted-foreground">Loading sessions...</p>}
        {!loading && sessions.length === 0 && <p className="text-muted-foreground">No sessions yet. Start a test to see results here.</p>}

        <AnimatePresence mode="wait">
          <motion.div key={dashboardView} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="grid gap-3">
            {sessions.map((session, i) => (
              <motion.div
                key={session.id}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06 }}
                whileHover={{ x: 4, transition: { duration: 0.15 } }}
              >
                <Card
                  className="cursor-pointer hover:glow-sm transition-all group border-border/50 hover:border-primary/30"
                  onClick={() => navigate(`/session/${session.id}`)}
                >
                  <CardContent className="flex items-center justify-between py-4">
                    <div className="flex items-center gap-4">
                      <div className="p-2.5 rounded-xl bg-primary/10 group-hover:bg-primary/20 transition-colors">
                        {dashboardView === 'writing' ? <PenTool className="h-5 w-5 text-primary" /> : <Mic className="h-5 w-5 text-primary" />}
                      </div>
                      <div>
                        <p className="font-medium text-foreground group-hover:text-primary transition-colors">{session.topic}</p>
                        <p className="text-sm text-muted-foreground">{session.type} - {session.date}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <p className="text-2xl font-bold text-primary">{session.score.toFixed(1)}</p>
                        <p className="text-xs text-muted-foreground">Band Score</p>
                      </div>
                      <ArrowUpRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </motion.div>
        </AnimatePresence>
      </div>
    </Layout>
  );
};

export default Dashboard;
