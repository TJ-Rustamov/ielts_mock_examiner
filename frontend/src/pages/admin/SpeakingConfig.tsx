import { useEffect, useMemo, useState } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Plus, Save, Trash2, Volume2 } from 'lucide-react';
import { fetchJson } from '@/lib/backend';

type SpeakingQuestion = {
  id: number;
  part: 1 | 2 | 3;
  question: string;
  follow_up: string;
  is_active: boolean;
};

type SpeakingVoiceConfig = {
  tts_provider: string;
  voice: string;
  speed: number;
};

type SpeakingConfigResponse = {
  voice: SpeakingVoiceConfig;
  providers: string[];
  voices: string[];
  questions: SpeakingQuestion[];
};

type TTSPreviewResponse = {
  mime_type: string;
  audio_base64: string;
};

const SpeakingConfig = () => {
  const [questions, setQuestions] = useState<SpeakingQuestion[]>([]);
  const [voiceConfig, setVoiceConfig] = useState<SpeakingVoiceConfig>({ tts_provider: 'kokoro', voice: 'af_heart', speed: 1 });
  const [providers, setProviders] = useState<string[]>(['kokoro']);
  const [voices, setVoices] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<'1' | '2' | '3'>('1');
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [newQ, setNewQ] = useState({ question: '', followUp: '', part: 1 as 1 | 2 | 3 });
  const [previewText, setPreviewText] = useState('Hello, this is a voice preview test.');
  const [previewAudioUrl, setPreviewAudioUrl] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      const data = await fetchJson<SpeakingConfigResponse>('/api/admin/speaking-config');
      setVoiceConfig(data.voice);
      setProviders(data.providers?.length ? data.providers : ['kokoro']);
      const fetchedVoices = data.voices || [];
      const voiceList = fetchedVoices.length ? fetchedVoices : [data.voice.voice];
      setVoices(Array.from(new Set(voiceList)));
      setQuestions(data.questions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load speaking config');
    }
  };

  useEffect(() => {
    load();
    return () => {
      if (previewAudioUrl) URL.revokeObjectURL(previewAudioUrl);
    };
  }, []);

  const saveVoice = async () => {
    setError(null);
    try {
      const updated = await fetchJson<SpeakingVoiceConfig>('/api/admin/speaking-config', {
        method: 'PUT',
        body: JSON.stringify(voiceConfig),
      });
      setVoiceConfig(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save voice settings');
    }
  };

  const testVoice = async () => {
    if (!previewText.trim()) {
      setError('Enter text to test voice.');
      return;
    }

    setPreviewing(true);
    setError(null);
    try {
      const res = await fetchJson<TTSPreviewResponse>('/api/admin/tts/preview', {
        method: 'POST',
        body: JSON.stringify({ text: previewText, voice: voiceConfig.voice, speed: voiceConfig.speed }),
      });

      const binary = atob(res.audio_base64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: res.mime_type || 'audio/wav' });
      const url = URL.createObjectURL(blob);

      if (previewAudioUrl) URL.revokeObjectURL(previewAudioUrl);
      setPreviewAudioUrl(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate voice preview');
    } finally {
      setPreviewing(false);
    }
  };

  const addQuestion = async () => {
    setError(null);
    try {
      const created = await fetchJson<SpeakingQuestion>('/api/admin/speaking-questions', {
        method: 'POST',
        body: JSON.stringify({
          part: newQ.part,
          question: newQ.question,
          follow_up: newQ.part === 2 ? newQ.followUp : '',
          is_active: true,
        }),
      });
      setQuestions((prev) => [...prev, created]);
      setIsAddOpen(false);
      setNewQ({ question: '', followUp: '', part: 1 });
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete question');
    }
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

    return (
      <div className="space-y-2">
        {list.map((q) => (
          <Card key={q.id} className={!q.is_active ? 'opacity-50' : ''}>
            <CardContent className="flex items-start gap-3 p-3">
              <div className="flex-1">
                <p className="text-sm text-foreground font-medium">{q.question}</p>
                {q.follow_up && <p className="text-xs text-muted-foreground mt-1">{q.follow_up}</p>}
              </div>
              <div className="flex items-center gap-1">
                <Button variant="outline" size="sm" onClick={() => toggleQuestion(q)}>{q.is_active ? 'Disable' : 'Enable'}</Button>
                <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => deleteQuestion(q.id)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  };

  return (
    <AdminLayout>
      <div className="space-y-6 max-w-3xl">
        <div>
          <h1 className="text-2xl font-heading font-bold text-foreground">Speaking Config</h1>
          <p className="text-muted-foreground text-sm mt-1">Manage voice settings, preview TTS, and speaking questions</p>
          {error && <p className="text-sm text-destructive mt-2">{error}</p>}
        </div>

        <Card>
          <CardHeader><CardTitle className="text-base">Voice Settings</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>TTS Provider</Label>
                <Select value={voiceConfig.tts_provider} onValueChange={(v) => setVoiceConfig((p) => ({ ...p, tts_provider: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {providers.map((provider) => (
                      <SelectItem key={provider} value={provider}>{provider}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Voice</Label>
                <Select value={voiceConfig.voice} onValueChange={(v) => setVoiceConfig((p) => ({ ...p, voice: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {voices.map((voice) => (
                      <SelectItem key={voice} value={voice}>{voice}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Speed</Label>
                <Input
                  type="number"
                  step="0.1"
                  min="0.5"
                  max="2"
                  value={String(voiceConfig.speed)}
                  onChange={(e) => setVoiceConfig((p) => ({ ...p, speed: Number(e.target.value || 1) }))}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Test Text</Label>
              <Textarea rows={3} value={previewText} onChange={(e) => setPreviewText(e.target.value)} />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={saveVoice}><Save className="h-4 w-4 mr-1" />Save Voice Settings</Button>
              <Button size="sm" variant="outline" onClick={testVoice} disabled={previewing}>
                <Volume2 className="h-4 w-4 mr-1" />{previewing ? 'Generating...' : 'Test Voice'}
              </Button>
            </div>

            {previewAudioUrl && (
              <audio controls src={previewAudioUrl} className="w-full" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Speaking Questions</CardTitle>
            <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
              <DialogTrigger asChild>
                <Button size="sm"><Plus className="h-4 w-4 mr-1" />Add Question</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Add Speaking Question</DialogTitle></DialogHeader>
                <div className="space-y-4 mt-2">
                  <div className="space-y-2">
                    <Label>Part</Label>
                    <Select value={String(newQ.part)} onValueChange={(v) => setNewQ((p) => ({ ...p, part: Number(v) as 1 | 2 | 3 }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1">Part 1</SelectItem>
                        <SelectItem value="2">Part 2</SelectItem>
                        <SelectItem value="3">Part 3</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Question</Label>
                    <Textarea value={newQ.question} onChange={(e) => setNewQ((p) => ({ ...p, question: e.target.value }))} />
                  </div>
                  {newQ.part === 2 && (
                    <div className="space-y-2">
                      <Label>Follow-up Cue Card Points</Label>
                      <Textarea value={newQ.followUp} onChange={(e) => setNewQ((p) => ({ ...p, followUp: e.target.value }))} />
                    </div>
                  )}
                  <Button className="w-full" onClick={addQuestion} disabled={!newQ.question.trim()}>Add Question</Button>
                </div>
              </DialogContent>
            </Dialog>
          </CardHeader>
          <CardContent>
            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as '1' | '2' | '3')}>
              <TabsList>
                <TabsTrigger value="1">Part 1 ({byPart[1].length})</TabsTrigger>
                <TabsTrigger value="2">Part 2 ({byPart[2].length})</TabsTrigger>
                <TabsTrigger value="3">Part 3 ({byPart[3].length})</TabsTrigger>
              </TabsList>
              <TabsContent value="1" className="mt-3">{renderQuestions(1)}</TabsContent>
              <TabsContent value="2" className="mt-3">{renderQuestions(2)}</TabsContent>
              <TabsContent value="3" className="mt-3">{renderQuestions(3)}</TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </AdminLayout>
  );
};

export default SpeakingConfig;
