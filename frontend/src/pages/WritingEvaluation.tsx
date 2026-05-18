import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, Loader2, Sparkles, Wand2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import Layout from '@/components/Layout';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchJson } from '@/lib/backend';
import { useThemeContext } from '@/contexts/ThemeContext';

type CriterionKey = 'ta' | 'tr' | 'cc' | 'lr' | 'gra';

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

type EssayHighlightRange = {
  start: number;
  end: number;
  item: InlineSuggestion;
  domId: string;
};

type BandImprovement = {
  original_text: string;
  enhanced_text: string;
  why_better: string;
  criterion: string;
};

type BandEssayEntry = {
  rewritten_essay: string;
  coach_summary: string;
  improvements: BandImprovement[];
};

type WritingResponse = {
  id: number;
  task_type: 'task1' | 'task2';
  prompt: string;
  essay_text: string;
  scores: Record<string, number>;
  examiner_comments: string;
  corrections: Array<{ error: string; correction: string }>;
  criteria_feedback?: Partial<Record<CriterionKey, CriterionIssue[]>>;
  inline_suggestions?: InlineSuggestion[];
  word_count: number;
  band_essays_status?: 'pending' | 'processing' | 'done' | 'failed';
  created_at: string;
};

type BandEssaysResponse = {
  status: 'pending' | 'processing' | 'done' | 'failed';
  essays: Record<string, BandEssayEntry | string>;
  generated_bands?: string[];
  error: string;
};

const labelMap: Record<string, string> = {
  ta: 'Task Achievement',
  tr: 'Task Response',
  cc: 'Coherence & Cohesion',
  lr: 'Lexical Resource',
  gra: 'Grammatical Range & Accuracy',
};

const criterionTagColor: Record<string, string> = {
  ta: 'bg-blue-500/15 text-blue-700 dark:text-blue-300',
  tr: 'bg-blue-500/15 text-blue-700 dark:text-blue-300',
  cc: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  lr: 'bg-purple-500/15 text-purple-700 dark:text-purple-300',
  gra: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
};

const isCriterionKey = (value: string): value is CriterionKey => ['ta', 'tr', 'cc', 'lr', 'gra'].includes(value);

const normalizeBandEntry = (entry: BandEssayEntry | string | undefined): BandEssayEntry => {
  if (typeof entry === 'string') {
    return { rewritten_essay: entry, coach_summary: '', improvements: [] };
  }
  if (!entry || typeof entry !== 'object') {
    return { rewritten_essay: '', coach_summary: '', improvements: [] };
  }
  return {
    rewritten_essay: entry.rewritten_essay || '',
    coach_summary: entry.coach_summary || '',
    improvements: Array.isArray(entry.improvements) ? entry.improvements : [],
  };
};

const toConciseCommentPoints = (raw: string): string[] => {
  const cleaned = (raw || '').replace(/\s+/g, ' ').trim();
  if (!cleaned) return [];
  return cleaned
    .split(/(?<=[.!?])\s+/)
    .map((line) => line.trim())
    .filter(Boolean);
};

const formatBandScore = (score: number): string => {
  const floor = Math.floor(score);
  const fraction = score - floor;
  if (fraction < 0.5) return floor.toFixed(1);
  if (fraction >= 0.7) return (floor + 1).toFixed(1);
  return (floor + 0.5).toFixed(1);
};

const WritingEvaluation = () => {
  const { id } = useParams();
  const [data, setData] = useState<WritingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedBand, setSelectedBand] = useState('7');
  const [bandStatus, setBandStatus] = useState<'pending' | 'processing' | 'done' | 'failed'>('pending');
  const [bandEssays, setBandEssays] = useState<Record<string, BandEssayEntry>>({
    '7': { rewritten_essay: '', coach_summary: '', improvements: [] },
    '8': { rewritten_essay: '', coach_summary: '', improvements: [] },
    '9': { rewritten_essay: '', coach_summary: '', improvements: [] },
  });
  const [generatingBand, setGeneratingBand] = useState<string | null>(null);
  const [bandError, setBandError] = useState<string>('');
  const [expandedCriterion, setExpandedCriterion] = useState<CriterionKey | null>(null);
  const [hoveredExcerpt, setHoveredExcerpt] = useState<string>('');
  const [focusedExcerpt, setFocusedExcerpt] = useState<string>('');
  const [selectedEssayHighlightId, setSelectedEssayHighlightId] = useState<string | null>(null);
  const [showAllByCriterion, setShowAllByCriterion] = useState<Partial<Record<CriterionKey, boolean>>>({});
  const [selectedImprovementKey, setSelectedImprovementKey] = useState<string | null>(null);
  const navigate = useNavigate();
  const { setStudyMode } = useThemeContext();

  useEffect(() => {
    setStudyMode('writing');
  }, [setStudyMode]);

  useEffect(() => {
    let pollingInterval: number | null = null;
    let isMounted = true;

    const run = async () => {
      if (!id) {
        setError('Missing evaluation id');
        setLoading(false);
        return;
      }

      try {
        const [evaluationResponse, bandsResponse] = await Promise.all([
          fetchJson<WritingResponse>(`/api/writing/evaluate/${id}`),
          fetchJson<BandEssaysResponse>(`/api/writing/evaluate/${id}/band-essays`),
        ]);
        
        if (!isMounted) return;

        setData(evaluationResponse);
        setBandStatus(bandsResponse.status || evaluationResponse.band_essays_status || 'pending');
        setBandEssays({
          '7': normalizeBandEntry(bandsResponse.essays?.['7']),
          '8': normalizeBandEntry(bandsResponse.essays?.['8']),
          '9': normalizeBandEntry(bandsResponse.essays?.['9']),
        });
        setBandError(bandsResponse.error || '');

        // If examiner_comments is empty, it means the detailed evaluation is still processing
        if (!evaluationResponse.examiner_comments) {
          pollingInterval = window.setInterval(async () => {
            try {
              const updatedData = await fetchJson<WritingResponse>(`/api/writing/evaluate/${id}`, { cache: 'no-store' });
              if (!isMounted) return;
              
              if (updatedData.examiner_comments) {
                setData(updatedData);
                if (pollingInterval) clearInterval(pollingInterval);
              }
            } catch (e) {
              // Ignore polling errors
            }
          }, 3000);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load evaluation');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    run();

    return () => {
      isMounted = false;
      if (pollingInterval) clearInterval(pollingInterval);
    };
  }, [id]);

  const scoreRows = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.scores)
      .filter(([key]) => key !== 'overall_band')
      .map(([key, score]) => ({ key, label: labelMap[key] || key.toUpperCase(), score }));
  }, [data]);

  useEffect(() => {
    if (!expandedCriterion && scoreRows.length > 0 && isCriterionKey(scoreRows[0].key)) {
      setExpandedCriterion(scoreRows[0].key);
    }
  }, [scoreRows, expandedCriterion]);

  const conciseCommentPoints = useMemo(() => toConciseCommentPoints(data?.examiner_comments || ''), [data]);

  const selectedBandEntry = useMemo(() => bandEssays[selectedBand] || { rewritten_essay: '', coach_summary: '', improvements: [] }, [bandEssays, selectedBand]);

  const essayHighlights = useMemo(() => {
    if (!data) return [] as EssayHighlightRange[];
    const essay = data.essay_text || '';
    const inlineSuggestions = (data.inline_suggestions || []).map((item, idx) => ({ ...item, _idx: idx }));
    const criteriaSuggestions: Array<InlineSuggestion & { _idx: number }> = Object.entries(data.criteria_feedback || {}).flatMap(([criterion, issues]) =>
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
    const ranges: EssayHighlightRange[] = [];
    for (const item of suggestions) {
      const needle = (item.span_text || '').trim();
      if (!needle) continue;
      let from = 0;
      let found = -1;
      while (from < essay.length) {
        const next = essay.indexOf(needle, from);
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
        ranges.push({
          start: found,
          end: found + needle.length,
          item,
          domId: `essay-highlight-${ranges.length}`,
        });
      }
    }
    ranges.sort((a, b) => a.start - b.start);
    return ranges;
  }, [data]);

  const criterionIssueMap = useMemo(() => {
    const out: Partial<Record<CriterionKey, CriterionIssueEntry[]>> = {
      ta: [],
      tr: [],
      cc: [],
      lr: [],
      gra: [],
    };
    if (!data) return out;

    const pushUnique = (key: CriterionKey, issue: CriterionIssueEntry) => {
      const list = out[key] || [];
      // Collapse near-duplicates that point to the same text and same fix, even if issue labels differ.
      const dedupeKey = `${(issue.excerpt || '').toLowerCase()}|${(issue.suggestion || '').toLowerCase()}`;
      const exists = list.some(
        (x) =>
          `${(x.excerpt || '').toLowerCase()}|${(x.suggestion || '').toLowerCase()}` === dedupeKey
      );
      if (!exists) {
        list.push(issue);
        out[key] = list;
      }
    };

    for (const key of ['ta', 'tr', 'cc', 'lr', 'gra'] as CriterionKey[]) {
      const base = data.criteria_feedback?.[key] || [];
      for (const item of base) {
        pushUnique(key, {
          issue: item.issue || '',
          suggestion: item.suggestion || '',
          excerpt: item.excerpt || '',
        });
      }
    }

    for (const item of data.inline_suggestions || []) {
      const key = String(item.criterion || '').toLowerCase();
      if (!isCriterionKey(key)) continue;
      pushUnique(key, {
        issue: item.issue || 'Issue detected',
        suggestion: item.suggestion || '',
        excerpt: item.span_text || '',
      });
    }

    const assigned: Record<CriterionKey, Set<string>> = {
      ta: new Set<string>(),
      tr: new Set<string>(),
      cc: new Set<string>(),
      lr: new Set<string>(),
      gra: new Set<string>(),
    };

    const withTargets: Partial<Record<CriterionKey, CriterionIssueEntry[]>> = {
      ta: [],
      tr: [],
      cc: [],
      lr: [],
      gra: [],
    };

    for (const key of ['ta', 'tr', 'cc', 'lr', 'gra'] as CriterionKey[]) {
      const issues = out[key] || [];
      const mapped = issues.map((issue) => {
        const excerpt = (issue.excerpt || '').trim().toLowerCase();
        const issueText = (issue.issue || '').trim().toLowerCase();
        const suggestionText = (issue.suggestion || '').trim().toLowerCase();

        const candidates = essayHighlights.filter((highlight) => {
          const highlightCriterion = String(highlight.item.criterion || '').toLowerCase();
          if (!(highlightCriterion === key || (key === 'ta' && highlightCriterion === 'tr') || (key === 'tr' && highlightCriterion === 'ta'))) {
            return false;
          }
          const span = (highlight.item.span_text || '').trim().toLowerCase();
          if (excerpt && span !== excerpt) return false;
          return true;
        });

        const relaxedCandidates = candidates.length
          ? candidates
          : essayHighlights.filter((highlight) => {
              const highlightCriterion = String(highlight.item.criterion || '').toLowerCase();
              if (!(highlightCriterion === key || (key === 'ta' && highlightCriterion === 'tr') || (key === 'tr' && highlightCriterion === 'ta'))) {
                return false;
              }
              const span = (highlight.item.span_text || '').trim().toLowerCase();
              return excerpt ? span.includes(excerpt) || excerpt.includes(span) : true;
            });

        const ranked = relaxedCandidates.sort((a, b) => {
          const aScore =
            ((a.item.issue || '').toLowerCase() === issueText ? 2 : 0) +
            ((a.item.suggestion || '').toLowerCase() === suggestionText ? 1 : 0);
          const bScore =
            ((b.item.issue || '').toLowerCase() === issueText ? 2 : 0) +
            ((b.item.suggestion || '').toLowerCase() === suggestionText ? 1 : 0);
          return bScore - aScore;
        });

        const selected =
          ranked.find((r) => !assigned[key].has(r.domId)) ||
          ranked[0];

        if (selected) assigned[key].add(selected.domId);
        return { ...issue, targetDomId: selected?.domId };
      });
      withTargets[key] = mapped;
    }

    return withTargets;
  }, [data, essayHighlights]);

  const focusIssueInEssay = (issue: CriterionIssueEntry, criterion: CriterionKey) => {
    const excerpt = issue.excerpt || '';
    const needle = excerpt.trim().toLowerCase();
    setExpandedCriterion(criterion);
    setHoveredExcerpt(excerpt);
    setFocusedExcerpt(excerpt);

    const byDomId = issue.targetDomId ? essayHighlights.find((range) => range.domId === issue.targetDomId) : undefined;
    const target = byDomId
      || essayHighlights.find((range) => {
           const span = (range.item.span_text || '').trim().toLowerCase();
           return !!needle && (span.includes(needle) || needle.includes(span));
         })
      || essayHighlights.find((range) => isCriterionKey(range.item.criterion) && range.item.criterion === criterion);
    setSelectedEssayHighlightId(target?.domId || null);

    const fallbackId = 'essay-section-card';
    requestAnimationFrame(() => {
      if (target) {
        document.getElementById(target.domId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
      document.getElementById(fallbackId)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  };

  const selectedEssayHighlight = useMemo(
    () => essayHighlights.find((item) => item.domId === selectedEssayHighlightId) || null,
    [essayHighlights, selectedEssayHighlightId]
  );

  const highlightedEssay = useMemo(() => {
    if (!data) return null;
    const essay = data.essay_text || '';
    if (!essayHighlights.length) {
      return <span>{essay}</span>;
    }

    const nodes: ReactNode[] = [];
    let cursor = 0;

    for (let i = 0; i < essayHighlights.length; i += 1) {
      const range = essayHighlights[i];
      if (cursor < range.start) {
        nodes.push(<span key={`plain-${i}-${cursor}`}>{essay.slice(cursor, range.start)}</span>);
      }
      const crit = isCriterionKey(range.item.criterion) ? range.item.criterion : null;
      const isActiveCriterion = crit && expandedCriterion ? crit === expandedCriterion : false;
      const normalizedSpan = range.item.span_text.toLowerCase();
      const normalizedHover = hoveredExcerpt.toLowerCase();
      const normalizedFocus = focusedExcerpt.toLowerCase();
      const isHoverLinked = !!normalizedHover && (normalizedSpan.includes(normalizedHover) || normalizedHover.includes(normalizedSpan));
      const isFocused = !!normalizedFocus && (normalizedSpan.includes(normalizedFocus) || normalizedFocus.includes(normalizedSpan));
      const isSelected = selectedEssayHighlightId === range.domId;
      nodes.push(
        <button
          key={`highlight-${i}-${range.start}`}
          type="button"
          onClick={() => setSelectedEssayHighlightId(range.domId)}
          className="p-0 m-0 align-baseline"
        >
          <mark
            id={range.domId}
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
            {essay.slice(range.start, range.end)}
          </mark>
        </button>
      );
      cursor = range.end;
    }

    if (cursor < essay.length) {
      nodes.push(<span key={`tail-${cursor}`}>{essay.slice(cursor)}</span>);
    }

    return <>{nodes}</>;
  }, [data, essayHighlights, expandedCriterion, hoveredExcerpt, focusedExcerpt]);

  const highlightedBandEssay = useMemo(() => {
    const text = selectedBandEntry.rewritten_essay || '';
    const improvements = selectedBandEntry.improvements || [];
    if (!text) return <span className="text-muted-foreground">Generate this band version to view it.</span>;
    if (!improvements.length) return <span>{text}</span>;

    const ranges: Array<{ start: number; end: number; item: BandImprovement; key: string }> = [];
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
  }, [selectedBandEntry, selectedImprovementKey, selectedBand]);

  const selectedImprovement = useMemo(() => {
    if (!selectedImprovementKey) return null;
    const idx = Number(selectedImprovementKey.split('-')[1]);
    if (Number.isNaN(idx)) return null;
    return selectedBandEntry.improvements[idx] || null;
  }, [selectedImprovementKey, selectedBandEntry]);

  useEffect(() => {
    setSelectedImprovementKey(null);
  }, [selectedBand]);

  const generateBandEssay = async (force = false) => {
    if (!id) return;
    setGeneratingBand(selectedBand);
    setBandError('');

    try {
      const response = await fetchJson<BandEssaysResponse>(`/api/writing/evaluate/${id}/band-essays`, {
        method: 'POST',
        body: JSON.stringify({ band: selectedBand, force }),
      });
      setBandStatus(response.status);
      setBandEssays({
        '7': normalizeBandEntry(response.essays?.['7']),
        '8': normalizeBandEntry(response.essays?.['8']),
        '9': normalizeBandEntry(response.essays?.['9']),
      });
      setBandError(response.error || '');
    } catch (err) {
      setBandStatus('failed');
      setBandError(err instanceof Error ? err.message : 'Failed to generate improved essay');
    } finally {
      setGeneratingBand(null);
    }
  };

  const isProcessingEvaluation = data && !data.examiner_comments;

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

          {isProcessingEvaluation && (
            <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-8 bg-primary/10 border border-primary/20 p-4 rounded-xl flex items-center gap-4">
              <Loader2 className="h-6 w-6 text-primary animate-spin shrink-0" />
              <div>
                <h3 className="font-semibold text-foreground">Detailed Evaluation in Progress</h3>
                <p className="text-sm text-muted-foreground">Your score is ready! We are generating detailed feedback and corrections in the background.</p>
              </div>
            </motion.div>
          )}

          {loading && <p className="text-muted-foreground">Loading evaluation...</p>}
          {error && <p className="text-destructive">{error}</p>}

          {data && (
            <>
              <div className="text-center mb-8">
                <div className="inline-flex flex-col items-center p-6 rounded-2xl bg-primary/10 glow">
                  <p className="text-5xl font-bold text-primary">{formatBandScore(Number(data.scores.overall_band || 0))}</p>
                  <p className="text-sm text-muted-foreground mt-1 font-medium">Overall Band Score</p>
                </div>
              </div>

              <div className="grid xl:grid-cols-[1.5fr_1fr] gap-6">
                <div className="space-y-6">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {!isProcessingEvaluation && scoreRows.map((row) => (
                    <Card key={row.key} className="bg-card">
                      <CardContent className="py-4 flex flex-col items-center justify-center space-y-2 text-center h-full">
                        <p className="text-sm font-medium text-muted-foreground">{row.label}</p>
                        <p className="text-3xl font-bold text-primary">{Number(row.score).toFixed(1)}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                <Card>
                  <CardHeader><CardTitle>Detailed Feedback (Expand To See Exact Problems)</CardTitle></CardHeader>
                  <CardContent>
                    {isProcessingEvaluation ? (
                      <div className="flex flex-col items-center justify-center py-12 text-center border-2 border-dashed border-border rounded-xl">
                        <Loader2 className="h-8 w-8 text-primary animate-spin mb-3" />
                        <p className="text-foreground font-medium">Analyzing your essay...</p>
                        <p className="text-sm text-muted-foreground mt-1">Feedback will appear here shortly.</p>
                      </div>
                    ) : (
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
                                        onClick={() => isCriterionKey(criterionKey) && focusIssueInEssay(issue, criterionKey)}
                                        onMouseEnter={() => setHoveredExcerpt(issue.excerpt || '')}
                                        onMouseLeave={() => setHoveredExcerpt('')}
                                        className="w-full text-left text-sm rounded-md border p-2 bg-muted/20 hover:border-primary/40 transition-colors"
                                      >
                                        <p className="font-medium text-foreground">{issue.issue}</p>
                                        {!!issue.excerpt && <p className="text-xs text-muted-foreground mt-1">From essay: "{issue.excerpt}"</p>}
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
                    )}
                  </CardContent>
                </Card>

                <Card id="essay-section-card">
                  <CardHeader>
                    <CardTitle>Your Essay (Click Highlighted Text To See Suggestion)</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-muted-foreground mb-2">Prompt</p>
                    <p className="text-sm mb-4">{data.prompt}</p>
                    <p className="text-foreground leading-relaxed whitespace-pre-wrap text-sm">{highlightedEssay}</p>
                    <div className="mt-4">
                      {!selectedEssayHighlight && (
                        <p className="text-xs text-muted-foreground">Tip: click any highlighted phrase to view its exact suggestion.</p>
                      )}
                      {selectedEssayHighlight && (
                        <div className="rounded-md border bg-muted/20 p-3">
                          <p className="text-xs font-semibold text-foreground mb-1">
                            {labelMap[selectedEssayHighlight.item.criterion] || 'Suggestion'}
                          </p>
                          <p className="text-xs text-muted-foreground">{selectedEssayHighlight.item.issue || 'Issue detected.'}</p>
                          {!!selectedEssayHighlight.item.suggestion && (
                            <p className="text-xs text-primary mt-1">
                              Fix: {selectedEssayHighlight.item.suggestion}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-4 bg-muted px-3 py-1.5 rounded-full inline-block">{data.word_count} words</p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <CheckCircle2 className="h-5 w-5 text-primary" /> Examiner Comments (Short And Actionable)
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {isProcessingEvaluation ? (
                      <div className="flex flex-col items-center justify-center py-6 text-center">
                        <Loader2 className="h-6 w-6 text-primary animate-spin mb-2" />
                        <p className="text-sm text-muted-foreground">Generating comments...</p>
                      </div>
                    ) : (
                      <>
                        {!!conciseCommentPoints.length && (
                          <ul className="space-y-2">
                            {conciseCommentPoints.map((point, idx) => (
                              <li key={`comment-${idx}`} className="text-sm rounded-md bg-primary/5 border border-primary/15 px-3 py-2 text-foreground">
                                {point}
                              </li>
                            ))}
                          </ul>
                        )}
                        {!conciseCommentPoints.length && <p className="text-sm text-muted-foreground">No examiner comments were returned.</p>}
                      </>
                    )}

                    {!!data.corrections?.length && (
                      <div className="mt-4 space-y-2">
                        <p className="text-xs font-semibold text-muted-foreground">Fast fixes</p>
                        {data.corrections.map((c, i) => (
                          <p key={i} className="text-xs text-muted-foreground">{c.error} ({c.correction})</p>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Band 7 / 8 / 9 Enhanced Versions</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <ToggleGroup type="single" value={selectedBand} onValueChange={(v) => v && setSelectedBand(v)} className="justify-start">
                      <ToggleGroupItem value="7" aria-label="Band 7">Band 7</ToggleGroupItem>
                      <ToggleGroupItem value="8" aria-label="Band 8">Band 8</ToggleGroupItem>
                      <ToggleGroupItem value="9" aria-label="Band 9">Band 9</ToggleGroupItem>
                    </ToggleGroup>

                    <div className="flex items-center gap-2">
                      <Button onClick={() => generateBandEssay(false)} disabled={generatingBand !== null}>
                        {generatingBand === selectedBand ? (
                          <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating Band {selectedBand}
                          </>
                        ) : (
                          <>
                            <Wand2 className="h-4 w-4 mr-2" />
                            {selectedBandEntry.rewritten_essay ? `Generate Again (Band ${selectedBand})` : `Generate Band ${selectedBand}`}
                          </>
                        )}
                      </Button>
                      {!!selectedBandEntry.rewritten_essay && (
                        <Button variant="outline" onClick={() => generateBandEssay(true)} disabled={generatingBand !== null}>
                          Regenerate
                        </Button>
                      )}
                    </div>

                    {bandStatus === 'failed' && (
                      <p className="text-sm text-destructive">{bandError || 'Failed to generate improved essay.'}</p>
                    )}

                    <div className="rounded-lg border bg-muted/30 p-4 min-h-[380px] space-y-3 overflow-hidden">
                      {!!selectedBandEntry.coach_summary && (
                        <p className="text-xs rounded-md px-2.5 py-1.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                          {selectedBandEntry.coach_summary}
                        </p>
                      )}

                      <ScrollArea className="h-[290px] w-full pr-1">
                        <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                          {generatingBand === selectedBand ? 'Generating enhanced essay...' : highlightedBandEssay}
                        </p>
                      </ScrollArea>
                    </div>

                    {selectedImprovement && (
                      <div className="rounded-lg border border-emerald-500/35 bg-emerald-500/5 p-3 space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">Why this is better</p>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full ${criterionTagColor[selectedImprovement.criterion] || 'bg-muted text-muted-foreground'}`}>
                            {labelMap[selectedImprovement.criterion] || (selectedImprovement.criterion || 'rewrite')}
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
                  </CardContent>
                </Card>
              </div>
            </div>
            </>
          )}
        </motion.div>
      </div>
    </Layout>
  );
};

export default WritingEvaluation;
