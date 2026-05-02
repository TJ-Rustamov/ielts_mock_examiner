import { useEffect, useMemo, useState } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Save, Volume2 } from 'lucide-react';
import { fetchJson } from '@/lib/backend';

type SpeakingVoiceConfig = {
  tts_provider: string;
  voice: string;
  speed: number;
};

type SpeakingConfigResponse = {
  voice: SpeakingVoiceConfig;
  providers: string[];
  voices: string[];
};

type TTSPreviewResponse = {
  mime_type: string;
  audio_base64: string;
};

const SpeakingConfig = () => {
  const [voiceConfig, setVoiceConfig] = useState<SpeakingVoiceConfig>({ tts_provider: 'kokoro', voice: 'af_heart', speed: 1 });
  const [providers, setProviders] = useState<string[]>(['kokoro']);
  const [voices, setVoices] = useState<string[]>([]);
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

  return (
    <AdminLayout>
      <div className="space-y-6 max-w-3xl">
        <div>
          <h1 className="text-2xl font-heading font-bold text-foreground">Speaking Config</h1>
          <p className="text-muted-foreground text-sm mt-1">Manage voice settings and preview TTS</p>
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
      </div>
    </AdminLayout>
  );
};

export default SpeakingConfig;
