import { useEffect, useMemo, useState } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Checkbox } from '@/components/ui/checkbox';
import { Save } from 'lucide-react';
import { fetchJson } from '@/lib/backend';

type AIConfig = {
  provider: string;
  enabled_models: string[];
  writing_model: string;
  speaking_model: string;
  writing_prompt: string;
  speaking_prompt: string;
  temperature: number;
  max_tokens: number;
  streaming_enabled: boolean;
  updated_at?: string;
};

type AIConfigPayload = {
  config: AIConfig;
  model_catalog: Record<string, string[]>;
};

const AIConfiguration = () => {
  const [config, setConfig] = useState<AIConfig | null>(null);
  const [modelCatalog, setModelCatalog] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setError(null);
      try {
        const data = await fetchJson<AIConfigPayload>('/api/admin/ai-config');
        setConfig(data.config);
        setModelCatalog(data.model_catalog || {});
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load AI config');
      }
    };
    load();
  }, []);

  const providerModels = useMemo(() => {
    if (!config) return [];
    return modelCatalog[config.provider] || [];
  }, [config, modelCatalog]);

  useEffect(() => {
    if (!config) return;
    if ((config.enabled_models || []).length > 0) return;
    if (!providerModels.length) return;
    const first = providerModels[0];
    const second = providerModels[1] || first;
    setConfig((prev) =>
      prev
        ? {
            ...prev,
            enabled_models: [first, second].filter((v, i, a) => a.indexOf(v) === i),
            writing_model: first,
            speaking_model: second,
          }
        : prev
    );
  }, [config, providerModels]);

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await fetchJson<AIConfig>('/api/admin/ai-config', {
        method: 'PUT',
        body: JSON.stringify(config),
      });
      setConfig(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save AI config');
    } finally {
      setSaving(false);
    }
  };

  const toggleModel = (model: string, checked: boolean) => {
    if (!config) return;
    if (!checked && (config.enabled_models || []).length <= 1) {
      return;
    }
    const next = checked
      ? Array.from(new Set([...(config.enabled_models || []), model]))
      : (config.enabled_models || []).filter((m) => m !== model);

    const fallback = next[0] || model;
    setConfig({
      ...config,
      enabled_models: next,
      writing_model: next.includes(config.writing_model) ? config.writing_model : fallback,
      speaking_model: next.includes(config.speaking_model) ? config.speaking_model : fallback,
    });
  };

  if (!config) {
    return (
      <AdminLayout>
        <p className="text-sm text-muted-foreground">Loading AI configuration...</p>
      </AdminLayout>
    );
  }

  return (
    <AdminLayout>
      <div className="space-y-6 max-w-3xl">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-heading font-bold text-foreground">AI Configuration</h1>
            <p className="text-muted-foreground text-sm mt-1">Choose enabled models and assign separate models for writing/speaking</p>
            {error && <p className="text-sm text-destructive mt-2">{error}</p>}
          </div>
          <Button size="sm" onClick={save} disabled={saving}>
            <Save className="h-4 w-4 mr-1" />{saving ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>

        <Card>
          <CardHeader><CardTitle className="text-base">Provider & Models</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Provider</Label>
                <Select
                  value={config.provider}
                  onValueChange={(provider) => {
                    const available = modelCatalog[provider] || [];
                    const defaults = available.slice(0, Math.min(2, available.length));
                    const enabled = defaults.length ? defaults : available;
                    const first = enabled[0] || '';
                    const second = enabled[1] || first;
                    setConfig((p) =>
                      p
                        ? {
                            ...p,
                            provider,
                            enabled_models: enabled,
                            writing_model: first,
                            speaking_model: second,
                          }
                        : p
                    );
                  }}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.keys(modelCatalog).map((provider) => (
                      <SelectItem key={provider} value={provider}>{provider}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Enabled Models (multi-select)</Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 border rounded-md p-3">
                {providerModels.map((model) => (
                  <label key={model} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={(config.enabled_models || []).includes(model)}
                      onCheckedChange={(checked) => toggleModel(model, Boolean(checked))}
                    />
                    <span>{model}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Writing Model</Label>
                <Select value={config.writing_model} onValueChange={(v) => setConfig((p) => (p ? { ...p, writing_model: v } : p))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(config.enabled_models || []).map((model) => (
                      <SelectItem key={model} value={model}>{model}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Speaking Model</Label>
                <Select value={config.speaking_model} onValueChange={(v) => setConfig((p) => (p ? { ...p, speaking_model: v } : p))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(config.enabled_models || []).map((model) => (
                      <SelectItem key={model} value={model}>{model}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Temperature</Label>
                <Input type="number" step="0.1" min="0" max="2" value={String(config.temperature)} onChange={(e) => setConfig((p) => (p ? { ...p, temperature: Number(e.target.value || 0) } : p))} />
              </div>
              <div className="space-y-2">
                <Label>Max Tokens</Label>
                <Input type="number" value={String(config.max_tokens)} onChange={(e) => setConfig((p) => (p ? { ...p, max_tokens: Number(e.target.value || 0) } : p))} />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Switch checked={config.streaming_enabled} onCheckedChange={(v) => setConfig((p) => (p ? { ...p, streaming_enabled: v } : p))} />
              <Label>Enable Streaming</Label>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">System Prompts</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Writing Evaluation Prompt</Label>
              <Textarea rows={5} value={config.writing_prompt} onChange={(e) => setConfig((p) => (p ? { ...p, writing_prompt: e.target.value } : p))} />
            </div>
            <Separator />
            <div className="space-y-2">
              <Label>Speaking Evaluation Prompt</Label>
              <Textarea rows={5} value={config.speaking_prompt} onChange={(e) => setConfig((p) => (p ? { ...p, speaking_prompt: e.target.value } : p))} />
            </div>
          </CardContent>
        </Card>
      </div>
    </AdminLayout>
  );
};

export default AIConfiguration;
