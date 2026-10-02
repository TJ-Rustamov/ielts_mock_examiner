/**
 * Import a book PDF, publish its content as draft tests, and attach audio.
 *
 * Publishing here creates the questions and a proposed answer key; it does not
 * make anything visible to students. That happens per test, after the key is
 * verified on the Reading & Listening page.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { FileUp, Headphones, Loader2, Music, Rocket, Save } from 'lucide-react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  assignAudio, createImportJob, errorMessage, listAdminModules, listAudio, listImportJobs,
  publishImportJob, uploadAudio, type AudioAsset, type ImportJob,
} from '@/lib/exams';

const STATUS_STYLES: Record<ImportJob['status'], string> = {
  queued: 'bg-muted text-muted-foreground',
  running: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
  needs_review: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  failed: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
};

const STATUS_LABELS: Record<ImportJob['status'], string> = {
  queued: 'Queued',
  running: 'Reading the PDF',
  needs_review: 'Ready to publish',
  published: 'Published',
  failed: 'Failed',
};

function slugify(value: string) {
  return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

const ExamImport = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [file, setFile] = useState<File | null>(null);
  const [slug, setSlug] = useState('');
  const [uploading, setUploading] = useState(false);
  const [publishing, setPublishing] = useState<number | null>(null);

  const jobsQuery = useQuery({
    queryKey: ['exam-import-jobs'],
    queryFn: listImportJobs,
    // Poll only while something is still being parsed.
    refetchInterval: (query) => {
      const jobs = query.state.data?.jobs ?? [];
      return jobs.some((job) => job.status === 'queued' || job.status === 'running') ? 2000 : false;
    },
  });

  const modulesQuery = useQuery({ queryKey: ['exam-admin-modules'], queryFn: () => listAdminModules() });

  const books = useMemo(() => {
    const seen = new Map<string, string>();
    (modulesQuery.data?.modules ?? []).forEach((m) => seen.set(m.book_slug, m.book));
    return [...seen.entries()];
  }, [modulesQuery.data]);

  const [audioBook, setAudioBook] = useState('');
  const [audioFiles, setAudioFiles] = useState<File[]>([]);
  const [audioUploading, setAudioUploading] = useState(false);
  const [assets, setAssets] = useState<AudioAsset[]>([]);
  const [slots, setSlots] = useState<Record<number, { test: string; part: string }>>({});

  useEffect(() => {
    if (!audioBook && books.length) setAudioBook(books[0][0]);
  }, [books, audioBook]);

  const loadAssets = async (bookSlug: string) => {
    if (!bookSlug) return;
    try {
      const response = await listAudio(bookSlug);
      setAssets(response.assets);
      const next: Record<number, { test: string; part: string }> = {};
      response.assets.forEach((asset) => {
        next[asset.id] = {
          test: asset.test_number ? String(asset.test_number) : '',
          part: asset.part_number ? String(asset.part_number) : '',
        };
      });
      setSlots(next);
    } catch (error) {
      toast.error(errorMessage(error, 'Could not load audio.'));
    }
  };

  useEffect(() => { void loadAssets(audioBook); }, [audioBook]);

  const startImport = async () => {
    if (!file || !slug) return;
    setUploading(true);
    try {
      await createImportJob(file, slug);
      toast.success('Upload complete. The PDF is being read - this can take a few minutes.');
      setFile(null);
      await queryClient.invalidateQueries({ queryKey: ['exam-import-jobs'] });
    } catch (error) {
      toast.error(errorMessage(error, 'Could not start the import.'));
    } finally {
      setUploading(false);
    }
  };

  const publish = async (job: ImportJob) => {
    setPublishing(job.id);
    try {
      const response = await publishImportJob(job.id);
      toast.success(`Created ${response.modules.length} tests with ${response.questions} questions. ${response.note}`);
      await queryClient.invalidateQueries({ queryKey: ['exam-import-jobs'] });
      await queryClient.invalidateQueries({ queryKey: ['exam-admin-modules'] });
    } catch (error) {
      toast.error(errorMessage(error, 'Could not publish.'));
    } finally {
      setPublishing(null);
    }
  };

  const sendAudio = async () => {
    if (!audioBook || audioFiles.length === 0) return;
    setAudioUploading(true);
    try {
      const response = await uploadAudio(audioBook, audioFiles);
      toast.success(`Uploaded ${response.created.length} file(s). Check the test and part numbers below.`);
      setAudioFiles([]);
      await loadAssets(audioBook);
    } catch (error) {
      toast.error(errorMessage(error, 'Could not upload audio.'));
    } finally {
      setAudioUploading(false);
    }
  };

  const saveSlot = async (asset: AudioAsset) => {
    const slot = slots[asset.id];
    const test = slot?.test ? Number(slot.test) : null;
    const part = slot?.part ? Number(slot.part) : null;
    try {
      const response = await assignAudio(asset.id, test, part);
      toast.success(response.attached_to_section
        ? `Attached to Test ${test}, Part ${part}.`
        : 'Saved. No matching listening part exists yet - publish the book first.');
      await queryClient.invalidateQueries({ queryKey: ['exam-admin-modules'] });
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save this slot.'));
    }
  };

  const jobs = jobsQuery.data?.jobs ?? [];

  return (
    <AdminLayout>
      <div className="max-w-5xl space-y-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <FileUp className="h-6 w-6 text-primary" /> Import books
          </h1>
          <p className="text-sm text-muted-foreground">
            Imported tests start as drafts. Verify each answer key before it goes live.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">1. Upload the book PDF</CardTitle>
            <CardDescription>
              Questions and answer keys are read from the PDF. Re-uploading the same file reuses the
              earlier result.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <div className="space-y-1">
              <Label htmlFor="book-file">PDF</Label>
              <Input
                id="book-file"
                type="file"
                accept="application/pdf"
                onChange={(event) => {
                  const chosen = event.target.files?.[0] ?? null;
                  setFile(chosen);
                  if (chosen && !slug) setSlug(slugify(chosen.name.replace(/\.pdf$/i, '')));
                }}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="book-slug">Book identifier</Label>
              <Input
                id="book-slug"
                placeholder="cambridge-21"
                value={slug}
                onChange={(event) => setSlug(slugify(event.target.value))}
              />
            </div>
            <Button onClick={startImport} disabled={!file || !slug || uploading}>
              {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileUp className="mr-2 h-4 w-4" />}
              Import
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">2. Publish as draft tests</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Book</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Notes</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-6 text-center text-muted-foreground">
                      No imports yet.
                    </TableCell>
                  </TableRow>
                )}
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="font-medium">{job.book_slug}</TableCell>
                    <TableCell>
                      <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLES[job.status]}`}>
                        {job.status === 'running' && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />}
                        {STATUS_LABELS[job.status]}
                      </span>
                      {job.status === 'running' && job.stage && (
                        <div className="mt-1 text-xs text-muted-foreground">{job.stage}</div>
                      )}
                    </TableCell>
                    <TableCell className="max-w-md text-xs text-muted-foreground">
                      {job.status === 'failed' ? (
                        <details>
                          <summary className="cursor-pointer text-destructive">Show error</summary>
                          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap">{job.error}</pre>
                        </details>
                      ) : job.warnings.length ? (
                        <details>
                          <summary className="cursor-pointer">{job.warnings.length} note(s)</summary>
                          <ul className="mt-2 list-disc space-y-1 pl-4">
                            {job.warnings.slice(0, 30).map((warning, index) => <li key={index}>{warning}</li>)}
                          </ul>
                        </details>
                      ) : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      {job.status === 'needs_review' && (
                        <Button size="sm" onClick={() => void publish(job)} disabled={publishing === job.id}>
                          {publishing === job.id ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Rocket className="mr-1 h-4 w-4" />}
                          Publish drafts
                        </Button>
                      )}
                      {job.status === 'published' && (
                        <Button size="sm" variant="outline" onClick={() => navigate('/admin/exams')}>
                          Review keys
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Headphones className="h-5 w-5" /> 3. Listening audio
            </CardTitle>
            <CardDescription>
              Upload one file per part. The test and part are guessed from file names such as
              <code className="mx-1">T1S2.m4a</code> or <code className="mx-1">test-1-2.mp3</code>;
              correct them before saving. A listening test cannot go live until all four parts have audio.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {books.length === 0 ? (
              <p className="text-sm text-muted-foreground">Publish a book first.</p>
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-[220px_1fr_auto] sm:items-end">
                  <div className="space-y-1">
                    <Label>Book</Label>
                    <Select value={audioBook} onValueChange={setAudioBook}>
                      <SelectTrigger><SelectValue placeholder="Choose a book" /></SelectTrigger>
                      <SelectContent>
                        {books.map(([bookSlug, title]) => (
                          <SelectItem key={bookSlug} value={bookSlug}>{title}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="audio-files">Audio files</Label>
                    <Input
                      id="audio-files"
                      type="file"
                      multiple
                      accept="audio/*"
                      onChange={(event) => setAudioFiles(Array.from(event.target.files ?? []))}
                    />
                  </div>
                  <Button onClick={sendAudio} disabled={!audioBook || audioFiles.length === 0 || audioUploading}>
                    {audioUploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Music className="mr-2 h-4 w-4" />}
                    Upload {audioFiles.length > 0 ? `(${audioFiles.length})` : ''}
                  </Button>
                </div>

                {assets.length > 0 && (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>File</TableHead>
                        <TableHead>Length</TableHead>
                        <TableHead className="w-24">Test</TableHead>
                        <TableHead className="w-24">Part</TableHead>
                        <TableHead className="text-right">Save</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {assets.map((asset) => (
                        <TableRow key={asset.id}>
                          <TableCell className="max-w-xs truncate text-sm">{asset.original_filename}</TableCell>
                          <TableCell className="text-sm tabular-nums">
                            {asset.duration_seconds
                              ? `${Math.floor(asset.duration_seconds / 60)}:${String(asset.duration_seconds % 60).padStart(2, '0')}`
                              : <Badge variant="destructive">unreadable</Badge>}
                          </TableCell>
                          <TableCell>
                            <Input
                              className="h-8"
                              inputMode="numeric"
                              value={slots[asset.id]?.test ?? ''}
                              onChange={(event) => setSlots((s) => ({
                                ...s, [asset.id]: { ...s[asset.id], test: event.target.value.replace(/\D/g, '') },
                              }))}
                            />
                          </TableCell>
                          <TableCell>
                            <Input
                              className="h-8"
                              inputMode="numeric"
                              value={slots[asset.id]?.part ?? ''}
                              onChange={(event) => setSlots((s) => ({
                                ...s, [asset.id]: { ...s[asset.id], part: event.target.value.replace(/\D/g, '') },
                              }))}
                            />
                          </TableCell>
                          <TableCell className="text-right">
                            <Button size="sm" variant="outline" onClick={() => void saveSlot(asset)}>
                              <Save className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </AdminLayout>
  );
};

export default ExamImport;
