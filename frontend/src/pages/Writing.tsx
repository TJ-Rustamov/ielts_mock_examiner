import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Timer, TimerOff, Send, PenTool, FileText, AlertTriangle, Shuffle, Edit3, Upload, X, Image as ImageIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import Layout from '@/components/Layout';
import { useNavigate } from 'react-router-dom';
import { useThemeContext } from '@/contexts/ThemeContext';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { fetchJson, resolveAssetUrl } from '@/lib/backend';

type TopicMode = 'randomize' | 'manual' | 'upload';
type RandomTopicResponse = {
  id: number;
  task_type: 'task1' | 'task2';
  title: string;
  prompt: string;
  topic_image_url: string | null;
};

const Writing = () => {
  const [selectedPart, setSelectedPart] = useState<'task1' | 'task2'>('task1');
  const [topicMode, setTopicMode] = useState<TopicMode | null>(null);
  const [timerEnabled, setTimerEnabled] = useState(false);
  const [timeLeft, setTimeLeft] = useState(20 * 60);
  const [essay, setEssay] = useState('');
  const [currentTopic, setCurrentTopic] = useState('');
  const [currentImage, setCurrentImage] = useState<string | null>(null);
  const [currentImageFile, setCurrentImageFile] = useState<File | null>(null);
  const [manualTopic, setManualTopic] = useState('');
  const [manualImage, setManualImage] = useState<string | null>(null);
  const [manualImageFile, setManualImageFile] = useState<File | null>(null);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadPreview, setUploadPreview] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [imagePreviewOpen, setImagePreviewOpen] = useState(false);
  const [imagePreviewSrc, setImagePreviewSrc] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [topicError, setTopicError] = useState<string | null>(null);
  const [randomizing, setRandomizing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const manualImageInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { setStudyMode } = useThemeContext();

  useEffect(() => { setStudyMode('writing'); }, [setStudyMode]);

  useEffect(() => {
    if (!timerEnabled || timeLeft <= 0) return;
    const interval = setInterval(() => setTimeLeft(t => t - 1), 1000);
    return () => clearInterval(interval);
  }, [timerEnabled, timeLeft]);

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const parts = [
    { id: 'task1' as const, label: 'Task 1', time: 20, desc: 'Describe visual data', icon: FileText },
    { id: 'task2' as const, label: 'Task 2', time: 40, desc: 'Essay response', icon: PenTool },
  ];

  const topicModes = [
    { id: 'randomize' as TopicMode, label: 'Randomize', icon: Shuffle, desc: 'Get a random topic' },
    { id: 'manual' as TopicMode, label: 'Manual Entry', icon: Edit3, desc: 'Type your own topic' },
    { id: 'upload' as TopicMode, label: 'Upload Image', icon: Upload, desc: 'Upload a topic image' },
  ];

  const handleRandomize = async () => {
    setTopicMode('randomize');
    setCurrentImageFile(null);
    setTopicError(null);
    setRandomizing(true);
    try {
      const random = await fetchJson<RandomTopicResponse>(`/api/writing/topics/random?task_type=${selectedPart}`);
      setCurrentTopic(random.prompt);
      setCurrentImage(random.task_type === 'task1' ? resolveAssetUrl(random.topic_image_url) : null);
    } catch (error) {
      setTopicError(error instanceof Error ? error.message : 'Failed to load random topic');
      setCurrentTopic('');
      setCurrentImage(null);
    } finally {
      setRandomizing(false);
    }
  };

  const handleManualSelect = () => {
    setTopicMode('manual');
    setCurrentTopic('');
    setCurrentImage(null);
    setCurrentImageFile(null);
    setManualTopic('');
    setManualImage(null);
    setManualImageFile(null);
  };

  const handleManualConfirm = () => {
    setCurrentTopic(manualTopic);
    setCurrentImage(manualImage);
    setCurrentImageFile(manualImageFile);
  };

  const handleManualImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!['image/jpeg', 'image/png'].includes(file.type)) return;
    const url = URL.createObjectURL(file);
    setManualImage(url);
    setManualImageFile(file);
  };

  const handleUploadSelect = () => {
    setTopicMode('upload');
    setUploadModalOpen(true);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!['image/jpeg', 'image/png'].includes(file.type)) return;
    setUploadFile(file);
    setUploadPreview(URL.createObjectURL(file));
  };

  const handleUploadConfirm = () => {
    if (!uploadFile) return;
    setCurrentImage(uploadPreview);
    setCurrentImageFile(uploadFile);
    setCurrentTopic('Uploaded topic image');
    setUploadModalOpen(false);
    setUploadPreview(null);
    setUploadFile(null);
  };

  const openImagePreview = (src: string) => {
    setImagePreviewSrc(src);
    setImagePreviewOpen(true);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const topicImageUrl = currentImage && /^https?:\/\//.test(currentImage) ? currentImage : null;
      let response: { id: number };

      if (currentImageFile) {
        const formData = new FormData();
        formData.append('task_type', selectedPart);
        formData.append('prompt', currentTopic);
        formData.append('essay', essay);
        formData.append('topic_image', currentImageFile);
        if (topicImageUrl) formData.append('topic_image_url', topicImageUrl);

        response = await fetchJson<{ id: number }>('/api/writing/evaluate', {
          method: 'POST',
          body: formData,
        });
      } else {
        response = await fetchJson<{ id: number }>('/api/writing/evaluate', {
          method: 'POST',
          body: JSON.stringify({
            task_type: selectedPart,
            prompt: currentTopic,
            essay,
            topic_image_url: topicImageUrl || undefined,
          }),
        });
      }

      navigate(`/writing/evaluation/${response.id}`);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Failed to submit essay');
    } finally {
      setSubmitting(false);
    }
  };

  const resetTopic = () => {
    setTopicMode(null);
    setCurrentTopic('');
    setCurrentImage(null);
    setCurrentImageFile(null);
    setManualTopic('');
    setManualImage(null);
    setManualImageFile(null);
    setTopicError(null);
  };

  const handlePartSwitch = (id: 'task1' | 'task2', time: number) => {
    setSelectedPart(id);
    setTimeLeft(time * 60);
    resetTopic();
    setEssay('');
  };

  const wordCount = essay.split(/\s+/).filter(Boolean).length;
  const isLow = (selectedPart === 'task1' && wordCount > 0 && wordCount < 150) || (selectedPart === 'task2' && wordCount > 0 && wordCount < 250);
  const hasTopicSet = !!currentTopic;

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 max-w-4xl relative">
        <div className="absolute w-80 h-80 bg-primary/5 rounded-full blur-3xl -top-20 -right-20 pointer-events-none" />

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="relative z-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-xl bg-primary/10">
              <PenTool className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-foreground">Writing Practice</h1>
              <p className="text-muted-foreground">Write your essay and get AI-powered feedback</p>
            </div>
          </div>

          {/* Part selector + timer */}
          <div className="flex items-center gap-3 my-8 flex-wrap">
            {parts.map((part, i) => (
              <motion.div key={part.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}>
                <Button
                  variant={selectedPart === part.id ? 'default' : 'outline'}
                  onClick={() => handlePartSwitch(part.id, part.time)}
                  className={`gap-2 h-11 ${selectedPart === part.id ? 'glow-sm' : ''}`}
                >
                  <part.icon className="h-4 w-4" />
                  {part.label}
                </Button>
              </motion.div>
            ))}
            <div className="ml-auto flex items-center gap-3">
              <Button variant="ghost" size="icon" onClick={() => setTimerEnabled(!timerEnabled)} className={timerEnabled ? 'text-primary bg-primary/10' : ''}>
                {timerEnabled ? <Timer className="h-4 w-4" /> : <TimerOff className="h-4 w-4" />}
              </Button>
              {timerEnabled && (
                <motion.span initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}
                  className={`font-mono text-lg font-bold px-3 py-1 rounded-lg ${timeLeft < 60 ? 'text-destructive bg-destructive/10 animate-pulse' : 'text-foreground bg-muted'}`}
                >
                  {formatTime(timeLeft)}
                </motion.span>
              )}
            </div>
          </div>

          {/* Topic selection area */}
          <AnimatePresence mode="wait">
            {!hasTopicSet ? (
              <motion.div key="topic-selector" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="mb-6">
                <p className="text-sm font-medium text-muted-foreground mb-3">Choose how to get your topic:</p>
                <div className="grid grid-cols-3 gap-3">
                  {topicModes.map((mode, i) => (
                    <motion.div key={mode.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
                      <Card
                        className={`cursor-pointer transition-all hover:border-primary/50 hover:shadow-md ${topicMode === mode.id && !hasTopicSet ? 'border-primary bg-primary/5' : ''}`}
                        onClick={() => {
                          if (mode.id === 'randomize') handleRandomize();
                          else if (mode.id === 'manual') handleManualSelect();
                          else handleUploadSelect();
                        }}
                      >
                        <CardContent className="flex flex-col items-center gap-2 py-5 px-3 text-center">
                          <div className="p-2.5 rounded-xl bg-primary/10">
                            <mode.icon className="h-5 w-5 text-primary" />
                          </div>
                          <span className="font-medium text-sm text-foreground">{mode.label}</span>
                          <span className="text-xs text-muted-foreground">{mode.desc}</span>
                        </CardContent>
                      </Card>
                    </motion.div>
                  ))}
                </div>
                {topicError && <p className="text-sm text-destructive mt-3">{topicError}</p>}
                {randomizing && <p className="text-sm text-muted-foreground mt-3">Loading random topic...</p>}

                {/* Manual entry form */}
                <AnimatePresence>
                  {topicMode === 'manual' && !hasTopicSet && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
                      <div className="mt-4 p-4 rounded-xl border bg-card space-y-3">
                        <Input
                          placeholder="Enter your topic..."
                          value={manualTopic}
                          onChange={e => setManualTopic(e.target.value)}
                          className="text-sm"
                        />
                        {selectedPart === 'task1' && (
                          <div>
                            <input ref={manualImageInputRef} type="file" accept=".jpg,.jpeg,.png" className="hidden" onChange={handleManualImageUpload} />
                            <Button variant="outline" size="sm" className="gap-2" onClick={() => manualImageInputRef.current?.click()}>
                              <ImageIcon className="h-4 w-4" />
                              {manualImage ? 'Change Image' : 'Attach Task Image (required)'}
                            </Button>
                            {manualImage && (
                              <img src={manualImage} alt="Task" className="mt-2 rounded-lg max-h-32 object-contain border" />
                            )}
                          </div>
                        )}
                        <Button
                          size="sm"
                          disabled={!manualTopic.trim() || (selectedPart === 'task1' && !manualImage)}
                          onClick={handleManualConfirm}
                          className="gap-2"
                        >
                          Confirm Topic
                        </Button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ) : (
              /* Topic display */
              <motion.div key="topic-display" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="mb-6">
                <Card className="border-primary/20 bg-primary/5">
                  <CardContent className="py-4 px-5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 space-y-3">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold uppercase tracking-wider text-primary bg-primary/10 px-2 py-0.5 rounded-full">
                            {selectedPart === 'task1' ? 'Task 1' : 'Task 2'} Topic
                          </span>
                        </div>
                        <p className="text-sm text-foreground leading-relaxed">{currentTopic}</p>
                        {currentImage && (
                          <div className="space-y-2">
                            <img
                              src={currentImage}
                              alt="Task visual"
                              className="rounded-lg max-h-48 object-contain border border-border cursor-zoom-in"
                              onClick={() => openImagePreview(currentImage)}
                            />
                            <Button variant="outline" size="sm" onClick={() => openImagePreview(currentImage)}>
                              View Larger
                            </Button>
                          </div>
                        )}
                      </div>
                      <Button variant="ghost" size="icon" onClick={resetTopic} className="shrink-0 h-8 w-8">
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Essay writing area */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <Card className="overflow-hidden relative group">
              <div className="absolute inset-0 bg-gradient-to-br from-primary/3 via-transparent to-transparent pointer-events-none" />
              <CardContent className="pt-6 relative z-10">
                <Textarea
                  placeholder={
                    !hasTopicSet
                      ? "Select a topic above to start writing..."
                      : selectedPart === 'task1'
                        ? "Summarise the information by selecting and reporting the main features, and make comparisons where relevant..."
                        : "Write about the following topic. Give reasons for your answer and include any relevant examples from your own knowledge or experience..."
                  }
                  value={essay}
                  onChange={e => setEssay(e.target.value)}
                  disabled={!hasTopicSet}
                  className="min-h-[400px] resize-none text-base leading-relaxed border-none focus-visible:ring-0 bg-transparent disabled:opacity-50"
                />
                <div className="flex items-center justify-between mt-4 pt-4 border-t">
                  <div className="flex items-center gap-3">
                    <motion.p key={wordCount} initial={{ scale: 1.1 }} animate={{ scale: 1 }} className="text-sm font-medium text-muted-foreground">
                      <span className="text-foreground font-bold text-lg">{wordCount}</span> words
                    </motion.p>
                    {isLow && (
                      <motion.span initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                        className="flex items-center gap-1 text-xs text-destructive bg-destructive/10 px-2 py-1 rounded-full"
                      >
                        <AlertTriangle className="h-3 w-3" />
                        Min {selectedPart === 'task1' ? 150 : 250}
                      </motion.span>
                    )}
                  </div>
                  <Button onClick={handleSubmit} disabled={wordCount < 10 || !hasTopicSet || submitting} className="gap-2 glow-sm h-11 px-6">
                    <Send className="h-4 w-4" /> Submit Essay
                  </Button>
                </div>
                {submitError && <p className="text-sm text-destructive mt-3">{submitError}</p>}
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      </div>

      {/* Upload Image Modal */}
      <Dialog open={uploadModalOpen} onOpenChange={(open) => { if (!open) { setUploadModalOpen(false); setUploadPreview(null); setUploadFile(null); if (!currentTopic) setTopicMode(null); } }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-primary" />
              Upload Topic Image
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <input ref={fileInputRef} type="file" accept=".jpg,.jpeg,.png" className="hidden" onChange={handleFileChange} />
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-border rounded-xl p-8 flex flex-col items-center gap-3 cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-all"
            >
              {uploadPreview ? (
                <img src={uploadPreview} alt="Preview" className="max-h-48 rounded-lg object-contain" />
              ) : (
                <>
                  <ImageIcon className="h-10 w-10 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground font-medium">JPG or PNG only</p>
                  <p className="text-xs text-muted-foreground">Click to browse</p>
                </>
              )}
            </div>
            <Button onClick={handleUploadConfirm} disabled={!uploadFile} className="w-full gap-2">
              <Upload className="h-4 w-4" />
              Upload
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Fullscreen-style Image Preview */}
      <Dialog open={imagePreviewOpen} onOpenChange={setImagePreviewOpen}>
        <DialogContent className="w-[96vw] max-w-6xl h-[92vh] p-2">
          <DialogHeader>
            <DialogTitle>Task Image</DialogTitle>
          </DialogHeader>
          <div className="w-full h-full flex items-center justify-center bg-muted/20 rounded-md overflow-hidden">
            {imagePreviewSrc && (
              <img src={imagePreviewSrc} alt="Task visual large" className="w-full h-full object-contain" />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </Layout>
  );
};

export default Writing;
