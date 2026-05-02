import { useEffect, useMemo, useState } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Plus, Trash2, Upload, CheckSquare, XSquare } from 'lucide-react';
import { fetchJson } from '@/lib/backend';
import { Checkbox } from '@/components/ui/checkbox';

type QuestionItem = {
  id: number;
  text: string;
};

type SpeakingQuestion = {
  id: number;
  part: 1 | 2 | 3;
  topic: string;
  questions: QuestionItem[];
  cue_card: string;
  points: QuestionItem[];
  is_active: boolean;
};

const SpeakingQuestions = () => {
  const [questions, setQuestions] = useState<SpeakingQuestion[]>([]);
  const [activeTab, setActiveTab] = useState<'1' | '2' | '3'>('1');
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  // New question form state
  const [newTopic, setNewTopic] = useState('');
  const [newQuestions, setNewQuestions] = useState<string[]>(['']);
  const [newCueCard, setNewCueCard] = useState('');
  const [newPoints, setNewPoints] = useState<string[]>(['']);

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const load = async () => {
    setError(null);
    try {
      const data = await fetchJson<{ results: SpeakingQuestion[] }>('/api/admin/speaking-questions');
      setQuestions(data.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load questions');
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      await fetchJson<{}>('/api/admin/speaking-questions/import', {
        method: 'POST',
        body: formData,
      });

      await load();
      
      // Reset input
      e.target.value = '';
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import JSON');
    } finally {
      setUploading(false);
    }
  };

  const addQuestion = async () => {
    setError(null);
    const part = parseInt(activeTab, 10) as 1 | 2 | 3;

    try {
      const formattedQuestions = newQuestions.filter(q => q.trim()).map((q, i) => ({ id: i + 1, text: q.trim() }));
      const formattedPoints = newPoints.filter(p => p.trim()).map((p, i) => ({ id: i + 1, text: p.trim() }));

      const created = await fetchJson<SpeakingQuestion>('/api/admin/speaking-questions', {
        method: 'POST',
        body: JSON.stringify({
          part,
          topic: newTopic,
          questions: part !== 2 ? formattedQuestions : [],
          cue_card: part === 2 ? newCueCard : '',
          points: part === 2 ? formattedPoints : [],
          is_active: true,
        }),
      });
      setQuestions((prev) => [created, ...prev]);
      setIsAddOpen(false);
      setNewTopic('');
      setNewQuestions(['']);
      setNewCueCard('');
      setNewPoints(['']);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add question');
    }
  };

  const toggleQuestion = async (item: SpeakingQuestion) => {
    setError(null);
    try {
      const updated = await fetchJson<SpeakingQuestion>(`/api/admin/speaking-questions/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !item.is_active }),
      });
      setQuestions((prev) => prev.map((q) => (q.id === item.id ? updated : q)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update question');
    }
  };

  const deleteQuestion = async (id: number) => {
    setError(null);
    try {
      await fetchJson<{}>(`/api/admin/speaking-questions/${id}`, { method: 'DELETE' });
      setQuestions((prev) => prev.filter((q) => q.id !== id));
      setSelectedIds(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete question');
    }
  };

  const deleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`Are you sure you want to delete ${selectedIds.size} selected questions?`)) return;
    
    setError(null);
    try {
      await Promise.all(
        Array.from(selectedIds).map(id => 
          fetchJson<{}>(`/api/admin/speaking-questions/${id}`, { method: 'DELETE' })
        )
      );
      setQuestions(prev => prev.filter(q => !selectedIds.has(q.id)));
      setSelectedIds(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete some questions');
      await load(); // Reload to get actual state if partial failure
    }
  };

  const toggleSelectAll = (partList: SpeakingQuestion[]) => {
    const allSelected = partList.every(q => selectedIds.has(q.id));
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allSelected) {
        partList.forEach(q => next.delete(q.id));
      } else {
        partList.forEach(q => next.add(q.id));
      }
      return next;
    });
  };

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const byPart = useMemo(
    () => ({
      1: questions.filter((q) => q.part === 1),
      2: questions.filter((q) => q.part === 2),
      3: questions.filter((q) => q.part === 3),
    }),
    [questions]
  );

  const renderQuestions = (part: 1 | 2 | 3) => {
    const list = byPart[part];
    if (!list.length) return <p className="text-center py-6 text-sm text-muted-foreground">No questions yet.</p>;

    const allSelected = list.length > 0 && list.every(q => selectedIds.has(q.id));
    const anySelected = list.some(q => selectedIds.has(q.id));

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <Checkbox 
              id={`select-all-${part}`} 
              checked={allSelected} 
              onCheckedChange={() => toggleSelectAll(list)} 
            />
            <Label htmlFor={`select-all-${part}`} className="text-sm font-medium">Select All</Label>
          </div>
          {anySelected && (
            <Button variant="destructive" size="sm" onClick={deleteSelected}>
              <Trash2 className="h-4 w-4 mr-2" /> Delete Selected ({list.filter(q => selectedIds.has(q.id)).length})
            </Button>
          )}
        </div>

        {list.map((q) => (
          <Card key={q.id} className={!q.is_active ? 'opacity-50' : ''}>
            <CardContent className="flex items-start gap-4 p-4">
              <div className="pt-1">
                <Checkbox 
                  checked={selectedIds.has(q.id)} 
                  onCheckedChange={() => toggleSelect(q.id)} 
                />
              </div>
              <div className="flex-1 space-y-2">
                <div>
                  <span className="font-semibold text-sm text-primary uppercase">Topic:</span>
                  <span className="ml-2 text-sm text-foreground font-medium">{q.topic}</span>
                </div>
                
                {part !== 2 ? (
                  <div className="space-y-1">
                    <span className="font-semibold text-xs text-muted-foreground uppercase">Questions:</span>
                    <ul className="list-disc pl-5 text-sm text-foreground space-y-1">
                      {q.questions.map((question, idx) => (
                        <li key={idx}>{typeof question === 'string' ? question : question?.text || ''}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div>
                      <span className="font-semibold text-xs text-muted-foreground uppercase">Cue Card:</span>
                      <p className="text-sm text-foreground mt-1">{q.cue_card}</p>
                    </div>
                    <div>
                      <span className="font-semibold text-xs text-muted-foreground uppercase">Points:</span>
                      <ul className="list-disc pl-5 text-sm text-foreground space-y-1 mt-1">
                        {q.points.map((point, idx) => (
                          <li key={idx}>{typeof point === 'string' ? point : point?.text || ''}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
              
              <div className="flex flex-col items-center gap-2 border-l pl-4 border-border/50">
                <Button variant="outline" size="sm" className="w-full" onClick={() => toggleQuestion(q)}>
                  {q.is_active ? 'Disable' : 'Enable'}
                </Button>
                <Button variant="ghost" size="sm" className="w-full text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => deleteQuestion(q.id)}>
                  <Trash2 className="h-4 w-4 mr-2" /> Delete
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  };

  const isAddDisabled = () => {
    if (!newTopic.trim()) return true;
    if (activeTab === '2') {
      return !newCueCard.trim() || newPoints.every(p => !p.trim());
    }
    return newQuestions.every(q => !q.trim());
  };

  const handleQuestionChange = (index: number, value: string) => {
    const updated = [...newQuestions];
    updated[index] = value;
    setNewQuestions(updated);
  };

  const handlePointChange = (index: number, value: string) => {
    const updated = [...newPoints];
    updated[index] = value;
    setNewPoints(updated);
  };

  return (
    <AdminLayout>
      <div className="space-y-6 max-w-5xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-heading font-bold text-foreground">Speaking Questions</h1>
            <p className="text-muted-foreground text-sm mt-1">Manage topics, questions, and cue cards for speaking parts 1, 2, and 3</p>
          </div>
          
          <div className="flex items-center gap-2">
            <Label htmlFor="json-upload" className="cursor-pointer">
              <div className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground hover:bg-secondary/80 rounded-md text-sm font-medium transition-colors">
                <Upload className="h-4 w-4" />
                {uploading ? 'Uploading...' : 'Import JSON'}
              </div>
            </Label>
            <input
              id="json-upload"
              type="file"
              accept=".json"
              className="hidden"
              onChange={handleFileUpload}
              disabled={uploading}
            />
          </div>
        </div>
        
        {error && <p className="text-sm text-destructive">{error}</p>}

        <Card>
          <CardHeader className="flex flex-row items-center justify-between border-b border-border/50 pb-4">
            <CardTitle className="text-base">Question Bank</CardTitle>
            <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
              <DialogTrigger asChild>
                <Button size="sm"><Plus className="h-4 w-4 mr-1" />Add Question</Button>
              </DialogTrigger>
              <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle>Add Part {activeTab} Question</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                  <div className="space-y-2">
                    <Label>Topic</Label>
                    <Input placeholder="e.g. Accommodation" value={newTopic} onChange={(e) => setNewTopic(e.target.value)} />
                  </div>
                  
                  {activeTab !== '2' ? (
                    <div className="space-y-2">
                      <Label>Questions</Label>
                      {newQuestions.map((q, i) => (
                        <div key={i} className="flex items-center gap-2 mb-2">
                          <Input
                            placeholder={`Question ${i + 1}`}
                            value={q}
                            onChange={(e) => handleQuestionChange(i, e.target.value)}
                          />
                          <Button 
                            variant="ghost" 
                            size="icon" 
                            className="shrink-0"
                            onClick={() => setNewQuestions(prev => prev.filter((_, idx) => idx !== i))}
                            disabled={newQuestions.length === 1}
                          >
                            <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                          </Button>
                        </div>
                      ))}
                      <Button variant="outline" size="sm" className="w-full mt-2" onClick={() => setNewQuestions(prev => [...prev, ''])}>
                        <Plus className="h-4 w-4 mr-2" /> Add Another Question
                      </Button>
                    </div>
                  ) : (
                    <>
                      <div className="space-y-2">
                        <Label>Cue Card Text</Label>
                        <Textarea 
                          rows={3}
                          placeholder="Describe an advertisement that persuaded you..." 
                          value={newCueCard} 
                          onChange={(e) => setNewCueCard(e.target.value)} 
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Points</Label>
                        {newPoints.map((p, i) => (
                          <div key={i} className="flex items-center gap-2 mb-2">
                            <Input
                              placeholder={`Point ${i + 1}`}
                              value={p}
                              onChange={(e) => handlePointChange(i, e.target.value)}
                            />
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="shrink-0"
                              onClick={() => setNewPoints(prev => prev.filter((_, idx) => idx !== i))}
                              disabled={newPoints.length === 1}
                            >
                              <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                            </Button>
                          </div>
                        ))}
                        <Button variant="outline" size="sm" className="w-full mt-2" onClick={() => setNewPoints(prev => [...prev, ''])}>
                          <Plus className="h-4 w-4 mr-2" /> Add Another Point
                        </Button>
                      </div>
                    </>
                  )}
                  <Button className="w-full" onClick={addQuestion} disabled={isAddDisabled()}>Save to Database</Button>
                </div>
              </DialogContent>
            </Dialog>
          </CardHeader>
          <CardContent className="pt-6">
            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as '1' | '2' | '3')}>
              <TabsList className="grid w-full grid-cols-3 max-w-md mb-6">
                <TabsTrigger value="1">Part 1 ({byPart[1].length})</TabsTrigger>
                <TabsTrigger value="2">Part 2 ({byPart[2].length})</TabsTrigger>
                <TabsTrigger value="3">Part 3 ({byPart[3].length})</TabsTrigger>
              </TabsList>
              <TabsContent value="1">{renderQuestions(1)}</TabsContent>
              <TabsContent value="2">{renderQuestions(2)}</TabsContent>
              <TabsContent value="3">{renderQuestions(3)}</TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </AdminLayout>
  );
};

export default SpeakingQuestions;
