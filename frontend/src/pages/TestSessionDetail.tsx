import { type ReactNode, useEffect, useMemo, useState, Fragment } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, CheckCircle2, Loader2, Wand2, PlayCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import Layout from '@/components/Layout';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchJson } from '@/lib/backend';

type CriterionKey = 'fc' | 'lr' | 'gra';

type CriterionIssue = {
  issue: string;
  suggestion: string;
  excerpt: string;
};

type CriterionIssueEntry = CriterionIssue & {
  targetDomId?: string;
};

type InlineSuggestion = {
  span_text: string;
  issue: string;
  suggestion: string;
  criterion: string;
};

type TranscriptHighlightRange = {
  start: number;
  end: number;
  item: InlineSuggestion;
  domId: string;
};

type TurnImprovement = {
  original_text: string;
  enhanced_text: string;
  why_better: string;
  criterion: string;
};

type TurnRewriteEntry = {
  rewritten_response: string;
  coach_summary: string;
  improvements: TurnImprovement[];
};

type SpeakingDetail = {
  id: number;
  part: string;
  status: string;
  scores: Record<string, number>;
  final_report: {
    examiner_comments?: string;
    corrections?: Array<{ error: string; correction: string }>;
    criteria_feedback?: Partial<Record<CriterionKey, CriterionIssue[]>>;
    inline_suggestions?: InlineSuggestion[];
  };
  transcript: string;
  created_at: string;
};

const labelMap: Record<string, string> = {
  fc: 'Fluency & Coherence',
  lr: 'Lexical Resource',
  gra: 'Grammatical Range & Accuracy',
};

const criterionTagColor: Record<string, string> = {
  fc: 'bg-blue-500/15 text-blue-700 dark:text-blue-300',
  lr: 'bg-purple-500/15 text-purple-700 dark:text-purple-300',
  gra: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
};

const isCriterionKey = (value: string): value is CriterionKey => ['fc', 'lr', 'gra'].includes(value);

const toConciseCommentPoints = (raw: string): string[] => {
  const cleaned = (raw || '').replace(/\s+/g, ' ').trim();
  if (!cleaned) return [];
  return cleaned
    .split(/(?<=[.!?])\s+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 4)
    .map((line) => (line.length > 140 ? `${line.slice(0, 137)}...` : line));
};

const formatDate = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const TestSessionDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [data, setData] = useState<SpeakingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedCriterion, setExpandedCriterion] = useState<CriterionKey | null>(null);
  const [hoveredExcerpt, setHoveredExcerpt] = useState<string>('');
  const [focusedExcerpt, setFocusedExcerpt] = useState<string>('');
  const [selectedHighlightId, setSelectedHighlightId] = useState<string | null>(null);
  const [showAllByCriterion, setShowAllByCriterion] = useState<Partial<Record<CriterionKey, boolean>>>({});

  // Turn Rewrite Modal State
  const [rewriteModalOpen, setRewriteModalOpen] = useState(false);
  const [currentTurnIndex, setCurrentTurnIndex] = useState<number | null>(null);
  const [currentExaminerQuestion, setCurrentExaminerQuestion] = useState('');
  const [currentCandidateResponse, setCurrentCandidateResponse] = useState('');
  
  const [selectedBand, setSelectedBand] = useState('7');
  const [generatingBand, setGeneratingBand] = useState<string | null>(null);
  const [rewriteError, setRewriteError] = useState('');
  const [playingTts, setPlayingTts] = useState(false);
  
  // Cache for rewrites: turnIndex -> band -> TurnRewriteEntry
  const [rewriteCache, setRewriteCache] = useState<Record<number, Record<string, TurnRewriteEntry>>>({});
  const [selectedImprovementKey, setSelectedImprovementKey] = useState<string | null>(null);

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
          navigate(`/writing/evaluation/${rawId}`, { replace: true });
          return;
        } else if (kind === 's') {
          const res = await fetchJson<SpeakingDetail>(`/api/speaking/sessions/${rawId}`);
          if (!mounted) return;
          setData(res);
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
  }, [id, navigate]);

  const scores = data?.scores || {};
  const report = data?.final_report || {};

  const scoreRows = useMemo(() => {
    if (!data) return [];
    return Object.entries(scores)
      .filter(([key]) => key !== 'overall_band')
      .map(([key, score]) => ({ key, label: labelMap[key] || key.toUpperCase(), score: Number(score || 0) }));
  }, [data, scores]);

  useEffect(() => {
    if (!expandedCriterion && scoreRows.length > 0 && isCriterionKey(scoreRows[0].key)) {
      setExpandedCriterion(scoreRows[0].key as CriterionKey);
    }
  }, [scoreRows, expandedCriterion]);

  const conciseCommentPoints = useMemo(() => toConciseCommentPoints(report.examiner_comments || ''), [report]);

  const transcriptHighlights = useMemo(() => {
    if (!data) return [] as TranscriptHighlightRange[];
    const transcript = data.transcript || '';
    
    const inlineSuggestions = (report.inline_suggestions || []).map((item, idx) => ({ ...item, _idx: idx }));
    const criteriaSuggestions: Array<InlineSuggestion & { _idx: number }> = Object.entries(report.criteria_feedback || {}).flatMap(([criterion, issues]) =>
      (issues || [])
        .filter((issue) => (issue.excerpt || '').trim())
        .map((issue, idx) => ({
          span_text: issue.excerpt,
          issue: issue.issue,
          suggestion: issue.suggestion,
          criterion,
          _idx: idx,
        }))
    );
    const suggestions = [...inlineSuggestions, ...criteriaSuggestions];
    const ranges: TranscriptHighlightRange[] = [];
    
    for (const item of suggestions) {
      const needle = (item.span_text || '').trim();
      if (!needle) continue;
      
      let from = 0;
      let found = -1;
      while (from < transcript.length) {
        const next = transcript.indexOf(needle, from);
        if (next === -1) break;
        
        const substringBefore = transcript.substring(0, next).toLowerCase();
        const lastUser = Math.max(substringBefore.lastIndexOf('user:'), substringBefore.lastIndexOf('candidate:'));
        const lastExaminer = Math.max(substringBefore.lastIndexOf('assistant:'), substringBefore.lastIndexOf('examiner:'));
        
        const end = next + needle.length;
        const overlap = ranges.some((r) => next < r.end && end > r.start);
        
        if (!overlap && lastUser > lastExaminer) {
          found = next;
          break;
        }
        from = next + 1;
      }
      
      if (found >= 0) {
        ranges.push({
          start: found,
          end: found + needle.length,
          item,
          domId: `transcript-highlight-${ranges.length}`,
        });
      }
    }
    ranges.sort((a, b) => a.start - b.start);
    return ranges;
  }, [data, report]);

  const criterionIssueMap = useMemo(() => {
    const out: Partial<Record<CriterionKey, CriterionIssueEntry[]>> = {
      fc: [],
      lr: [],
      gra: [],
    };
    if (!data) return out;

    const pushUnique = (key: CriterionKey, issue: CriterionIssueEntry) => {
      const list = out[key] || [];
      const dedupeKey = `${(issue.excerpt || '').toLowerCase()}|${(issue.suggestion || '').toLowerCase()}`;
      const exists = list.some(
        (x) => `${(x.excerpt || '').toLowerCase()}|${(x.suggestion || '').toLowerCase()}` === dedupeKey
      );
      if (!exists) {
        list.push(issue);
        out[key] = list;
      }
    };

    for (const key of ['fc', 'lr', 'gra'] as CriterionKey[]) {
      const base = report.criteria_feedback?.[key] || [];
      for (const item of base) {
        pushUnique(key, {
          issue: item.issue || '',
          suggestion: item.suggestion || '',
          excerpt: item.excerpt || '',
        });
      }
    }

    for (const item of report.inline_suggestions || []) {
      const key = String(item.criterion || '').toLowerCase();
      if (!isCriterionKey(key)) continue;
      pushUnique(key, {
        issue: item.issue || 'Issue detected',
        suggestion: item.suggestion || '',
        excerpt: item.span_text || '',
      });
    }

    const assigned: Record<CriterionKey, Set<string>> = {
      fc: new Set<string>(),
      lr: new Set<string>(),
      gra: new Set<string>(),
    };

    const withTargets: Partial<Record<CriterionKey, CriterionIssueEntry[]>> = {
      fc: [],
      lr: [],
      gra: [],
    };

    for (const key of ['fc', 'lr', 'gra'] as CriterionKey[]) {
      const issues = out[key] || [];
      const mapped = issues.map((issue) => {
        const excerpt = (issue.excerpt || '').trim().toLowerCase();
        const issueText = (issue.issue || '').trim().toLowerCase();
        const suggestionText = (issue.suggestion || '').trim().toLowerCase();

        const candidates = transcriptHighlights.filter((highlight) => {
          const highlightCriterion = String(highlight.item.criterion || '').toLowerCase();
          if (highlightCriterion !== key) return false;
          const span = (highlight.item.span_text || '').trim().toLowerCase();
          if (excerpt && span !== excerpt) return false;
          return true;
        });

        const relaxedCandidates = candidates.length
          ? candidates
          : transcriptHighlights.filter((highlight) => {
              const highlightCriterion = String(highlight.item.criterion || '').toLowerCase();
              if (highlightCriterion !== key) return false;
              const span = (highlight.item.span_text || '').trim().toLowerCase();
              return excerpt ? span.includes(excerpt) || excerpt.includes(span) : true;
            });

        const ranked = relaxedCandidates.sort((a, b) => {
          const aScore = ((a.item.issue || '').toLowerCase() === issueText ? 2 : 0) + ((a.item.suggestion || '').toLowerCase() === suggestionText ? 1 : 0);
          const bScore = ((b.item.issue || '').toLowerCase() === issueText ? 2 : 0) + ((b.item.suggestion || '').toLowerCase() === suggestionText ? 1 : 0);
          return bScore - aScore;
        });

        const selected = ranked.find((r) => !assigned[key].has(r.domId)) || ranked[0];

        if (selected) assigned[key].add(selected.domId);
        return { ...issue, targetDomId: selected?.domId };
      });
      withTargets[key] = mapped;
    }

    return withTargets;
  }, [data, report, transcriptHighlights]);

  const focusIssueInTranscript = (issue: CriterionIssueEntry, criterion: CriterionKey) => {
    const excerpt = issue.excerpt || '';
    const needle = excerpt.trim().toLowerCase();
    setExpandedCriterion(criterion);
    setHoveredExcerpt(excerpt);
    setFocusedExcerpt(excerpt);

    const byDomId = issue.targetDomId ? transcriptHighlights.find((range) => range.domId === issue.targetDomId) : undefined;
    const target = byDomId
      || transcriptHighlights.find((range) => {
           const span = (range.item.span_text || '').trim().toLowerCase();
           return !!needle && (span.includes(needle) || needle.includes(span));
         })
      || transcriptHighlights.find((range) => isCriterionKey(range.item.criterion) && range.item.criterion === criterion);
      
    setSelectedHighlightId(target?.domId || null);

    const fallbackId = 'transcript-section-card';
    requestAnimationFrame(() => {
      if (target) {
        document.getElementById(target.domId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
      document.getElementById(fallbackId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  };

  const selectedHighlight = useMemo(
    () => transcriptHighlights.find((item) => item.domId === selectedHighlightId) || null,
    [transcriptHighlights, selectedHighlightId]
  );

  const openRewriteModal = (index: number, question: string, response: string) => {
    setCurrentTurnIndex(index);
    setCurrentExaminerQuestion(question);
    setCurrentCandidateResponse(response);
    setRewriteModalOpen(true);
    setRewriteError('');
    setSelectedImprovementKey(null);
  };

  const generateTurnRewrite = async () => {
    if (!data || currentTurnIndex === null) return;
    const rawId = data.id;
    setGeneratingBand(selectedBand);
    setRewriteError('');

    try {
      const response = await fetchJson<TurnRewriteEntry>(`/api/speaking/sessions/${rawId}/turn-rewrite`, {
        method: 'POST',
        body: JSON.stringify({ 
          band: selectedBand, 
          examiner_question: currentExaminerQuestion,
          candidate_response: currentCandidateResponse
        }),
      });
      
      setRewriteCache(prev => ({
        ...prev,
        [currentTurnIndex]: {
          ...(prev[currentTurnIndex] || {}),
          [selectedBand]: response
        }
      }));
    } catch (err) {
      setRewriteError(err instanceof Error ? err.message : 'Failed to generate improved response');
    } finally {
      setGeneratingBand(null);
    }
  };

  const playTts = async (text: string) => {
    if (!text || playingTts) return;
    setPlayingTts(true);
    try {
      const response = await fetchJson<{audio_base64: string}>(`/api/speaking/tts/synthesize`, {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
      if (response.audio_base64) {
        const audio = new Audio(`data:audio/wav;base64,${response.audio_base64}`);
        audio.onended = () => setPlayingTts(false);
        audio.onerror = () => setPlayingTts(false);
        await audio.play();
      } else {
        setPlayingTts(false);
      }
    } catch (err) {
      console.error('TTS error:', err);
      setPlayingTts(false);
    }
  };

  const parseTranscriptWithHighlights = () => {
    if (!data) return null;
    const transcript = data.transcript || '';
    
    const lines = transcript.split('\n').filter(line => line.trim());
    let currentGlobalIndex = 0;
    
    // Track last examiner question to pass to the modal
    let lastExaminerLine = '';
    
    return (
      <div className="space-y-4">
        {lines.map((line, idx) => {
          const isUser = line.toLowerCase().startsWith('user:') || line.toLowerCase().startsWith('candidate:');
          const prefixMatch = line.match(/^(user|assistant|candidate|examiner):\s*/i);
          const prefixLength = prefixMatch ? prefixMatch[0].length : 0;
          
          const rawContent = line.slice(prefixLength);
          if (!isUser) {
            lastExaminerLine = rawContent;
          }
          
          const lineStartIndex = transcript.indexOf(line, currentGlobalIndex);
          const lineContentStart = lineStartIndex + prefixLength;
          const lineContentEnd = lineStartIndex + line.length;
          
          currentGlobalIndex = lineContentEnd;
          
          const lineHighlights = transcriptHighlights.filter(h => h.start >= lineContentStart && h.end <= lineContentEnd);
          
          let lineNodes: ReactNode[] = [];
          if (lineHighlights.length === 0) {
            lineNodes.push(<span key="content">{rawContent}</span>);
          } else {
            let cursor = lineContentStart;
            for (let i = 0; i < lineHighlights.length; i++) {
              const h = lineHighlights[i];
              if (cursor < h.start) {
                lineNodes.push(<span key={`plain-${i}`}>{transcript.slice(cursor, h.start)}</span>);
              }
              
              const crit = isCriterionKey(h.item.criterion) ? h.item.criterion : null;
              const isActiveCriterion = crit && expandedCriterion ? crit === expandedCriterion : false;
              const normalizedSpan = h.item.span_text.toLowerCase();
              const normalizedHover = hoveredExcerpt.toLowerCase();
              const normalizedFocus = focusedExcerpt.toLowerCase();
              const isHoverLinked = !!normalizedHover && (normalizedSpan.includes(normalizedHover) || normalizedHover.includes(normalizedSpan));
              const isFocused = !!normalizedFocus && (normalizedSpan.includes(normalizedFocus) || normalizedFocus.includes(normalizedSpan));
              const isSelected = selectedHighlightId === h.domId;
              
              lineNodes.push(
                <button
                  key={`highlight-${i}`}
                  type="button"
                  onClick={() => setSelectedHighlightId(h.domId)}
                  className="p-0 m-0 align-baseline"
                >
                  <mark
                    id={h.domId}
                    className={`px-0.5 rounded cursor-pointer transition-colors ${
                      isSelected
                        ? 'bg-rose-300/90 text-foreground ring-1 ring-rose-500/80'
                        : isFocused
                          ? 'bg-rose-300/90 text-foreground ring-1 ring-rose-500/80'
                          : isHoverLinked
                            ? 'bg-rose-300/85 text-foreground ring-1 ring-rose-400/70'
                            : isActiveCriterion
                              ? 'bg-amber-300/80 text-foreground'
                              : 'bg-amber-200/45 text-foreground'
                    }`}
                  >
                    {transcript.slice(h.start, h.end)}
                  </mark>
                </button>
              );
              cursor = h.end;
            }
            if (cursor < lineContentEnd) {
              lineNodes.push(<span key={`tail`}>{transcript.slice(cursor, lineContentEnd)}</span>);
            }
          }
          
          return (
            <div key={idx} className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} group relative`}>
              <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${isUser ? 'bg-primary text-primary-foreground rounded-tr-sm' : 'bg-muted text-foreground rounded-tl-sm'}`}>
                <p className="text-xs opacity-70 mb-1 font-semibold uppercase">{isUser ? 'You' : 'Examiner'}</p>
                <p className="whitespace-pre-wrap leading-relaxed">{lineNodes}</p>
              </div>
              
              {isUser && (
                <div className="absolute top-1/2 -translate-y-1/2 right-[calc(100%-1.5rem)] md:right-auto md:left-2 opacity-0 group-hover:opacity-100 transition-opacity flex items-center pr-2 md:pr-0 md:pl-2">
                  <Button 
                    variant="secondary" 
                    size="sm" 
                    className="h-8 rounded-full shadow-sm text-xs gap-1.5"
                    onClick={() => openRewriteModal(idx, lastExaminerLine, rawContent)}
                  >
                    <Wand2 className="h-3.5 w-3.5" /> Improve
                  </Button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const selectedBandRewrite = currentTurnIndex !== null ? rewriteCache[currentTurnIndex]?.[selectedBand] : undefined;

  const highlightedBandRewrite = useMemo(() => {
    if (!selectedBandRewrite) return <span className="text-muted-foreground">Generate this band version to view it.</span>;
    const text = selectedBandRewrite.rewritten_response || '';
    const improvements = selectedBandRewrite.improvements || [];
    
    if (!improvements.length) return <span>{text}</span>;

    const ranges: Array<{ start: number; end: number; item: TurnImprovement; key: string }> = [];
    for (let i = 0; i < improvements.length; i += 1) {
      const item = improvements[i];
      const needle = (item.enhanced_text || '').trim();
      if (!needle) continue;
      let from = 0;
      let found = -1;
      while (from < text.length) {
        const next = text.indexOf(needle, from);
        if (next === -1) break;
        const end = next + needle.length;
        const overlap = ranges.some((r) => next < r.end && end > r.start);
        if (!overlap) {
          found = next;
          break;
        }
        from = next + 1;
      }
      if (found >= 0) {
        ranges.push({ start: found, end: found + needle.length, item, key: `${selectedBand}-${i}` });
      }
    }

    ranges.sort((a, b) => a.start - b.start);
    const nodes: ReactNode[] = [];
    let cursor = 0;

    for (let i = 0; i < ranges.length; i += 1) {
      const range = ranges[i];
      if (cursor < range.start) {
        nodes.push(<span key={`band-plain-${i}-${cursor}`}>{text.slice(cursor, range.start)}</span>);
      }
      const isSelected = selectedImprovementKey === range.key;
      nodes.push(
        <button
          key={`band-highlight-${i}-${range.start}`}
          type="button"
          onClick={() => setSelectedImprovementKey(range.key)}
          className={`px-0.5 rounded border transition-colors cursor-pointer ${
            isSelected
              ? 'bg-emerald-300/80 border-emerald-500/70 text-foreground'
              : 'bg-emerald-200/45 border-emerald-500/30 hover:bg-emerald-300/60 text-foreground'
          }`}
        >
          {text.slice(range.start, range.end)}
        </button>
      );
      cursor = range.end;
    }

    if (cursor < text.length) {
      nodes.push(<span key={`band-tail-${cursor}`}>{text.slice(cursor)}</span>);
    }

    return <>{nodes}</>;
  }, [selectedBandRewrite, selectedImprovementKey, selectedBand]);

  const selectedImprovement = useMemo(() => {
    if (!selectedImprovementKey || !selectedBandRewrite) return null;
    const idx = Number(selectedImprovementKey.split('-')[1]);
    if (Number.isNaN(idx)) return null;
    return selectedBandRewrite.improvements[idx] || null;
  }, [selectedImprovementKey, selectedBandRewrite]);

  useEffect(() => {
    setSelectedImprovementKey(null);
  }, [selectedBand]);

  const overall = Number(scores?.overall_band || 0).toFixed(1);

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 relative">
        <div className="absolute w-72 h-72 bg-primary/5 rounded-full blur-3xl -top-20 right-0 pointer-events-none" />

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="relative z-10">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-3">
              <Button variant="ghost" onClick={() => navigate('/')} className="gap-2 px-0 hover:bg-transparent">
                <ArrowLeft className="h-5 w-5 text-primary" />
              </Button>
              <h1 className="text-3xl font-bold text-foreground">Speaking Evaluation</h1>
            </div>
            {data && <p className="text-sm text-muted-foreground font-medium bg-muted px-4 py-1.5 rounded-full">Part {data.part} • {formatDate(data.created_at)}</p>}
          </div>

          {loading && <p className="text-muted-foreground">Loading evaluation...</p>}
          {error && <p className="text-destructive">{error}</p>}

          {data && (
            <>
              <div className="text-center mb-8">
                <div className="inline-flex flex-col items-center p-6 rounded-2xl bg-primary/10 glow">
                  <p className="text-5xl font-bold text-primary">{overall}</p>
                  <p className="text-sm text-muted-foreground mt-1 font-medium">Overall Band Score</p>
                </div>
              </div>

              <div className="grid xl:grid-cols-[1.5fr_1fr] gap-6">
                <div className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {scoreRows.map((row) => (
                    <Card key={row.key} className="bg-card">
                      <CardContent className="py-4 flex flex-col items-center justify-center space-y-2 text-center h-full">
                        <p className="text-sm font-medium text-muted-foreground">{row.label}</p>
                        <p className="text-3xl font-bold text-primary">{row.score.toFixed(1)}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                <Card>
                  <CardHeader><CardTitle>Detailed Feedback (Expand To See Exact Problems)</CardTitle></CardHeader>
                  <CardContent>
                    <Accordion
                      type="single"
                      collapsible
                      value={expandedCriterion || undefined}
                      onValueChange={(value) => setExpandedCriterion(isCriterionKey(value) ? value : null)}
                    >
                      {scoreRows.map((row) => {
                        const criterionKey = row.key;
                        const isCriterion = isCriterionKey(criterionKey);
                        const issues = isCriterion ? (criterionIssueMap[criterionKey] || []) : [];
                        return (
                          <AccordionItem key={row.key} value={row.key} className="border rounded-lg px-3 mb-2">
                            <AccordionTrigger className="hover:no-underline py-3">
                              <div className="flex items-center justify-between w-full pr-2">
                                <span className="text-sm font-medium text-foreground">{row.label}</span>
                                <span className="font-bold text-primary">{Number(row.score).toFixed(1)}</span>
                              </div>
                            </AccordionTrigger>
                            <AccordionContent className="pt-1 pb-3">
                              {!issues.length && <p className="text-sm text-muted-foreground">No detailed mistakes were returned for this criterion.</p>}
                              {!!issues.length && (
                                <div className="space-y-2">
                                  <ul className="space-y-2">
                                    {(isCriterion && !showAllByCriterion[criterionKey] ? issues.slice(0, 8) : issues).map((issue, i) => (
                                      <button
                                        type="button"
                                        key={`${issue.issue}-${i}`}
                                        onClick={() => isCriterionKey(criterionKey) && focusIssueInTranscript(issue, criterionKey)}
                                        onMouseEnter={() => setHoveredExcerpt(issue.excerpt || '')}
                                        onMouseLeave={() => setHoveredExcerpt('')}
                                        className="w-full text-left text-sm rounded-md border p-2 bg-muted/20 hover:border-primary/40 transition-colors"
                                      >
                                        <p className="font-medium text-foreground">{issue.issue}</p>
                                        {!!issue.excerpt && <p className="text-xs text-muted-foreground mt-1">From transcript: "{issue.excerpt}"</p>}
                                        {!!issue.suggestion && <p className="text-xs text-primary mt-1">Fix: {issue.suggestion}</p>}
                                      </button>
                                    ))}
                                  </ul>
                                  {isCriterion && issues.length > 8 && (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        setShowAllByCriterion((prev) => ({
                                          ...prev,
                                          [criterionKey]: !prev[criterionKey],
                                        }))
                                      }
                                      className="text-xs font-medium text-primary hover:underline"
                                    >
                                      {showAllByCriterion[criterionKey] ? `Show top 8` : `Show all (${issues.length})`}
                                    </button>
                                  )}
                                </div>
                              )}
                            </AccordionContent>
                          </AccordionItem>
                        );
                      })}
                    </Accordion>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <CheckCircle2 className="h-5 w-5 text-primary" /> Examiner Comments (Short And Actionable)
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {!!conciseCommentPoints.length && (
                      <ul className="space-y-2">
                        {conciseCommentPoints.map((point, idx) => (
                          <li key={`comment-${idx}`} className="text-sm rounded-md bg-primary/5 border border-primary/15 px-3 py-2">
                            {point}
                          </li>
                        ))}
                      </ul>
                    )}
                    {!conciseCommentPoints.length && <p className="text-sm text-muted-foreground">No examiner comments were returned.</p>}

                    {!!report.corrections?.length && (
                      <div className="mt-4 space-y-2">
                        <p className="text-xs font-semibold text-muted-foreground">Fast fixes</p>
                        {report.corrections.map((c, i) => (
                          <p key={i} className="text-xs text-muted-foreground">{c.error} ({c.correction})</p>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-6">
                <Card id="transcript-section-card" className="h-full max-h-[800px] flex flex-col">
                  <CardHeader className="shrink-0">
                    <CardTitle>Test Transcript (Click Highlights To See Suggestion)</CardTitle>
                  </CardHeader>
                  <CardContent className="flex-1 overflow-y-auto pr-2 space-y-4 custom-scrollbar">
                    {parseTranscriptWithHighlights()}
                    
                    <div className="sticky bottom-0 bg-card pt-4 border-t mt-6">
                      {!selectedHighlight && (
                        <p className="text-xs text-muted-foreground">Tip: click any highlighted phrase to view its exact suggestion.</p>
                      )}
                      {selectedHighlight && (
                        <div className="rounded-md border bg-muted/20 p-3 shadow-sm">
                          <p className="text-xs font-semibold text-foreground mb-1">
                            {labelMap[selectedHighlight.item.criterion] || 'Suggestion'}
                          </p>
                          <p className="text-xs text-muted-foreground">{selectedHighlight.item.issue || 'Issue detected.'}</p>
                          {!!selectedHighlight.item.suggestion && (
                            <p className="text-xs text-primary mt-1 font-medium">
                              Fix: {selectedHighlight.item.suggestion}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
            </>
          )}
        </motion.div>
      </div>

      <Dialog open={rewriteModalOpen} onOpenChange={setRewriteModalOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Improve Your Response</DialogTitle>
            <DialogDescription>
              See how a Band 7, 8, or 9 candidate might answer this question.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 mt-4">
            <div className="bg-muted/40 p-3 rounded-lg text-sm space-y-2 border">
              <div>
                <span className="font-semibold text-xs uppercase opacity-70">Examiner Question:</span>
                <p>{currentExaminerQuestion || '(No previous question)'}</p>
              </div>
              <div className="pt-2 border-t border-border/50">
                <span className="font-semibold text-xs uppercase opacity-70">Your Response:</span>
                <p className="text-muted-foreground">{currentCandidateResponse}</p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-t pt-4">
              <ToggleGroup type="single" value={selectedBand} onValueChange={(v) => v && setSelectedBand(v)} className="justify-start">
                <ToggleGroupItem value="7" aria-label="Band 7">Band 7</ToggleGroupItem>
                <ToggleGroupItem value="8" aria-label="Band 8">Band 8</ToggleGroupItem>
                <ToggleGroupItem value="9" aria-label="Band 9">Band 9</ToggleGroupItem>
              </ToggleGroup>

              <div className="flex items-center gap-2">
                <Button onClick={generateTurnRewrite} disabled={generatingBand !== null}>
                  {generatingBand === selectedBand ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating Band {selectedBand}
                    </>
                  ) : (
                    <>
                      <Wand2 className="h-4 w-4 mr-2" />
                      {selectedBandRewrite ? `Generate Again (Band ${selectedBand})` : `Generate Band ${selectedBand}`}
                    </>
                  )}
                </Button>
                
                {!!selectedBandRewrite?.rewritten_response && (
                  <Button 
                    variant="secondary" 
                    onClick={() => playTts(selectedBandRewrite.rewritten_response)} 
                    disabled={playingTts}
                  >
                    {playingTts ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <PlayCircle className="h-4 w-4 mr-2" />
                    )}
                    {playingTts ? 'Playing...' : 'Play Audio'}
                  </Button>
                )}
              </div>
            </div>

            {rewriteError && (
              <p className="text-sm text-destructive mt-2">{rewriteError}</p>
            )}

            <div className="rounded-lg border bg-muted/30 p-4 min-h-[200px] space-y-3 mt-4">
              {!!selectedBandRewrite?.coach_summary && (
                <p className="text-xs rounded-md px-2.5 py-1.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                  {selectedBandRewrite.coach_summary}
                </p>
              )}

              <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                {generatingBand === selectedBand ? 'Generating improved response...' : highlightedBandRewrite}
              </p>
            </div>

            {selectedImprovement && (
              <div className="rounded-lg border border-emerald-500/35 bg-emerald-500/5 p-3 space-y-2 mt-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">Why this is better</p>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${criterionTagColor[selectedImprovement.criterion] || 'bg-muted text-muted-foreground'}`}>
                    {labelMap[selectedImprovement.criterion] || (selectedImprovement.criterion || 'improvement')}
                  </span>
                </div>
                <ScrollArea className="max-h-24 pr-1">
                  {!!selectedImprovement.original_text && (
                    <p className="text-xs text-muted-foreground mb-2">
                      Original: <span className="italic">{selectedImprovement.original_text}</span>
                    </p>
                  )}
                  <p className="text-sm text-foreground">{selectedImprovement.why_better}</p>
                </ScrollArea>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </Layout>
  );
};

export default TestSessionDetail;
