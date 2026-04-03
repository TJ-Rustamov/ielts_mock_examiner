import { useEffect, useMemo, useState } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Plus, Power, Trash2, Upload } from 'lucide-react';
import { fetchJson, resolveAssetUrl } from '@/lib/backend';

type TaskType = 'task1' | 'task2';

type Topic = {
  id: number;
  task_type: TaskType;
  title: string;
  prompt: string;
  topic_image_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type TopicFormState = {
  taskType: TaskType;
  title: string;
  imageFile: File | null;
};

const initialForm: TopicFormState = {
  taskType: 'task1',
  title: '',
  imageFile: null,
};

const WritingTopics = () => {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [activeTab, setActiveTab] = useState<TaskType>('task1');
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [form, setForm] = useState<TopicFormState>(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTopics = async () => {
    setLoading(true);
    setError(null);
    try {
      const [task1, task2] = await Promise.all([
        fetchJson<{ results: Topic[] }>('/api/writing/admin/topics?task_type=task1'),
        fetchJson<{ results: Topic[] }>('/api/writing/admin/topics?task_type=task2'),
      ]);
      setTopics([...task1.results, ...task2.results]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load topics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTopics();
  }, []);

  const topicsByTask = useMemo(
    () => ({
      task1: topics.filter((t) => t.task_type === 'task1'),
      task2: topics.filter((t) => t.task_type === 'task2'),
    }),
    [topics]
  );

  const uploadImage = async (file: File): Promise<string> => {
    const formData = new FormData();
    formData.append('image', file);
    const data = await fetchJson<{ image_url: string }>('/api/writing/upload-topic-image', {
      method: 'POST',
      body: formData,
    });
    return data.image_url;
  };

  const handleAddTopic = async () => {
    if (!form.title.trim()) {
      setError('Topic is required.');
      return;
    }
    if (form.taskType === 'task1' && !form.imageFile) {
      setError('Task 1 topic image is required.');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      let imageUrl: string | undefined;
      if (form.taskType === 'task1' && form.imageFile) {
        imageUrl = await uploadImage(form.imageFile);
      }

      const newTopic = await fetchJson<Topic>('/api/writing/admin/topics', {
        method: 'POST',
        body: JSON.stringify({
          task_type: form.taskType,
          title: form.title,
          topic_image_url: imageUrl,
          is_active: true,
        }),
      });

      setTopics((prev) => [newTopic, ...prev]);
      setForm(initialForm);
      setIsAddOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add topic');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (topic: Topic) => {
    setError(null);
    try {
      const updated = await fetchJson<Topic>(`/api/writing/admin/topics/${topic.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !topic.is_active }),
      });
      setTopics((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update topic');
    }
  };

  const handleDelete = async (topicId: number) => {
    setError(null);
    try {
      await fetchJson<{}>(`/api/writing/admin/topics/${topicId}`, { method: 'DELETE' });
      setTopics((prev) => prev.filter((topic) => topic.id !== topicId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete topic');
    }
  };

  const renderTopicList = (taskType: TaskType) => {
    const list = topicsByTask[taskType];

    if (loading) {
      return <div className="text-sm text-muted-foreground py-8">Loading topics...</div>;
    }

    if (list.length === 0) {
      return <div className="text-sm text-muted-foreground py-8 text-center">No topics yet.</div>;
    }

    return (
      <div className="space-y-3">
        {list.map((topic) => (
          <Card key={topic.id} className={!topic.is_active ? 'opacity-50' : ''}>
            <CardContent className="flex items-start gap-4 p-4">
              {topic.topic_image_url && (
                <div className="w-20 h-20 rounded-lg bg-muted flex items-center justify-center flex-shrink-0 overflow-hidden">
                  <img src={resolveAssetUrl(topic.topic_image_url) || ''} alt="Topic" className="w-full h-full object-cover" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-foreground text-sm">{topic.title}</span>
                  <Badge variant={topic.is_active ? 'default' : 'secondary'} className="text-xs">
                    {topic.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2">{topic.prompt}</p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleToggleActive(topic)}>
                  <Power className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => handleDelete(topic.id)}>
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
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-heading font-bold text-foreground">Writing Topics</h1>
            <p className="text-muted-foreground text-sm mt-1">Manage Task 1 and Task 2 prompts separately</p>
          </div>

          <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Add Topic
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add Writing Topic</DialogTitle>
              </DialogHeader>

              <div className="space-y-4 mt-2">
                <div className="flex gap-2">
                  <Button
                    variant={form.taskType === 'task1' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setForm((prev) => ({ ...prev, taskType: 'task1', imageFile: null }))}
                  >
                    Task 1
                  </Button>
                  <Button
                    variant={form.taskType === 'task2' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setForm((prev) => ({ ...prev, taskType: 'task2', imageFile: null }))}
                  >
                    Task 2
                  </Button>
                </div>

                <Input
                  placeholder="Topic"
                  value={form.title}
                  onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))}
                />

                {form.taskType === 'task1' && (
                  <div className="border-2 border-dashed border-border rounded-lg p-4 text-center">
                    <Upload className="h-6 w-6 mx-auto text-muted-foreground mb-2" />
                    <p className="text-sm text-muted-foreground mb-2">Upload chart/graph image (JPG or PNG)</p>
                    <input
                      type="file"
                      accept=".jpg,.jpeg,.png"
                      className="text-sm"
                      onChange={(e) => {
                        const file = e.target.files?.[0] || null;
                        setForm((prev) => ({ ...prev, imageFile: file }));
                      }}
                    />
                  </div>
                )}

                <Button className="w-full" onClick={handleAddTopic} disabled={saving}>
                  {saving ? 'Saving...' : 'Add Topic'}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TaskType)}>
          <TabsList>
            <TabsTrigger value="task1">Task 1 ({topicsByTask.task1.length})</TabsTrigger>
            <TabsTrigger value="task2">Task 2 ({topicsByTask.task2.length})</TabsTrigger>
          </TabsList>
          <TabsContent value="task1" className="mt-4">
            {renderTopicList('task1')}
          </TabsContent>
          <TabsContent value="task2" className="mt-4">
            {renderTopicList('task2')}
          </TabsContent>
        </Tabs>
      </div>
    </AdminLayout>
  );
};

export default WritingTopics;
