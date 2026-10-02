/**
 * Check and confirm one module's answer key.
 *
 * The grid arrives pre-filled - from the book's text layer where it has one,
 * otherwise from OCR of the uploaded image. Either way it is a proposal: the
 * test stays hidden from students until someone presses Verify here, and any
 * edit clears a previous verification.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, CheckCircle2, ImageUp, Loader2, Save, ShieldCheck } from 'lucide-react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  errorMessage, getAnswerSheet, saveAnswerSheet, uploadAnswerSheet, verifyAnswerSheet,
  type AdminModule, type AnswerSheet, type SheetAnswer,
} from '@/lib/exams';
import { cn } from '@/lib/utils';

const SOURCE_LABELS: Record<string, string> = {
  pdf: 'From the book PDF',
  ocr: 'Read from the image',
  manual: 'Typed in',
};

const joinAccepted = (answer: SheetAnswer | undefined) => (answer?.accepted ?? []).join(' / ');

const AnswerSheetEditor = () => {
  const { moduleId } = useParams();
  const id = Number(moduleId);
  const navigate = useNavigate();

  const [sheet, setSheet] = useState<AnswerSheet | null>(null);
  const [module, setModule] = useState<AdminModule | null>(null);
  const [grid, setGrid] = useState<Record<number, string>>({});
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const applySheet = useCallback((next: AnswerSheet | null) => {
    setSheet(next);
    const values: Record<number, string> = {};
    Object.entries(next?.answers ?? {}).forEach(([number, answer]) => {
      values[Number(number)] = joinAccepted(answer);
    });
    setGrid(values);
    setDirty(false);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getAnswerSheet(id);
      applySheet(response.sheet);
      setModule(response.module);
    } catch (error) {
      toast.error(errorMessage(error, 'Could not load this answer key.'));
    } finally {
      setLoading(false);
    }
  }, [id, applySheet]);

  useEffect(() => { void load(); }, [load]);

  const total = module?.total_questions || 40;
  const numbers = useMemo(() => Array.from({ length: total }, (_, i) => i + 1), [total]);
  const missing = numbers.filter((number) => !(grid[number] ?? '').trim());

  const changedFromProposal = (number: number) =>
    (grid[number] ?? '') !== joinAccepted(sheet?.proposed_answers?.[String(number)]);

  const setCell = (number: number, value: string) => {
    setGrid((previous) => {
      const next = { ...previous, [number]: value };
      // "21 & 22 IN EITHER ORDER" share one set of letters; keep partners in step.
      const partners = sheet?.answers?.[String(number)]?.set_numbers ?? [];
      partners.forEach((partner) => { next[partner] = value; });
      return next;
    });
    setDirty(true);
  };

  const save = async () => {
    if (!sheet) return;
    setSaving(true);
    try {
      const payload: Record<string, string | SheetAnswer> = {};
      numbers.forEach((number) => {
        const value = (grid[number] ?? '').trim();
        if (!value) return;
        const original = sheet.answers[String(number)];
        // Keep the kind and set details of an existing answer so that, for
        // example, a TRUE/FALSE key still accepts "T" after an edit.
        payload[String(number)] = original
          ? { ...original, accepted: value.split('/').map((part) => part.trim()).filter(Boolean) }
          : value;
      });
      const updated = await saveAnswerSheet(id, payload);
      applySheet(updated);
      toast.success('Saved. Verify again once every answer has been checked.');
      await load();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save.'));
    } finally {
      setSaving(false);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    try {
      const response = await uploadAnswerSheet(id, file);
      applySheet(response.sheet);
      toast.success(
        `The grid has ${response.read} of ${response.total} answers`
        + (response.filled_by_ocr ? `, ${response.filled_by_ocr} read from the image.` : '.'),
      );
      await load();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not upload the image.'));
    } finally {
      setUploading(false);
    }
  };

  const verify = async () => {
    setVerifying(true);
    try {
      const response = await verifyAnswerSheet(id);
      toast.success(
        response.remarked_attempts
          ? `Verified. ${response.remarked_attempts} submitted attempt(s) were re-marked.`
          : 'Verified.',
      );
      setModule(response.module);
      await load();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not verify.'));
    } finally {
      setVerifying(false);
      setConfirmOpen(false);
    }
  };

  return (
    <AdminLayout>
      <div className="space-y-6">
        <Button variant="ghost" size="sm" onClick={() => navigate('/admin/exams')}>
          <ArrowLeft className="mr-1 h-4 w-4" /> All tests
        </Button>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">
              {module ? `${module.book} · Test ${module.test_number} · ` : ''}
              <span className="capitalize">{module?.skill ?? ''}</span> answer key
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {sheet?.is_verified
                ? <Badge className="bg-emerald-600 hover:bg-emerald-600"><CheckCircle2 className="mr-1 h-3 w-3" /> Verified</Badge>
                : <Badge className="bg-amber-500 hover:bg-amber-500">Not verified</Badge>}
              {sheet?.proposal_source && (
                <Badge variant="outline">{SOURCE_LABELS[sheet.proposal_source] ?? sheet.proposal_source}</Badge>
              )}
              <Badge variant="secondary">{total - missing.length} / {total} filled</Badge>
            </div>
            {module && module.blocking_problems.length > 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                Blocking publication: {module.blocking_problems.join('; ')}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={save} disabled={!sheet || !dirty || saving}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              Save
            </Button>
            <Button
              onClick={() => setConfirmOpen(true)}
              disabled={!sheet || dirty || missing.length > 0 || verifying || sheet.is_verified}
              title={dirty ? 'Save your changes first' : missing.length ? 'Fill every answer first' : ''}
            >
              <ShieldCheck className="mr-2 h-4 w-4" /> Verify
            </Button>
          </div>
        </div>

        {loading ? (
          <Skeleton className="h-[600px] rounded-xl" />
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="h-fit lg:sticky lg:top-6">
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-base">Answer sheet image</CardTitle>
                <Button asChild size="sm" variant="outline" disabled={uploading}>
                  <label className="cursor-pointer">
                    {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ImageUp className="mr-2 h-4 w-4" />}
                    {sheet?.image_url ? 'Replace' : 'Upload'}
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ''; }}
                    />
                  </label>
                </Button>
              </CardHeader>
              <CardContent>
                {sheet?.image_url ? (
                  <a href={sheet.image_url} target="_blank" rel="noreferrer" title="Open full size">
                    <img src={sheet.image_url} alt="Uploaded answer key" className="w-full rounded border" />
                  </a>
                ) : (
                  <p className="py-10 text-center text-sm text-muted-foreground">
                    Upload a photo or scan of this test's answer key page. It is what you check the
                    grid against, and any answers still missing are read from it.
                  </p>
                )}
                {!!sheet?.warnings?.length && (
                  <details className="mt-4 text-xs text-muted-foreground">
                    <summary className="cursor-pointer">{sheet.warnings.length} import note(s)</summary>
                    <ul className="mt-2 list-disc space-y-1 pl-4">
                      {sheet.warnings.map((warning, index) => <li key={index}>{warning}</li>)}
                    </ul>
                  </details>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Accepted answers</CardTitle>
                <p className="text-xs text-muted-foreground">
                  Separate alternatives with a slash, e.g. <code>10 / ten</code>. Amber marks an
                  answer that differs from what was imported.
                </p>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {!sheet && (
                  <p className="pb-4 text-sm text-muted-foreground">
                    Upload the answer sheet image to create the grid.
                  </p>
                )}
                {numbers.map((number) => {
                  const answer = sheet?.answers?.[String(number)];
                  const empty = !(grid[number] ?? '').trim();
                  const edited = !!sheet && changedFromProposal(number);
                  return (
                    <div key={number} className="flex items-center gap-2">
                      <span className="w-7 text-right text-sm font-medium tabular-nums">{number}</span>
                      <Input
                        value={grid[number] ?? ''}
                        disabled={!sheet}
                        onChange={(event) => setCell(number, event.target.value)}
                        spellCheck={false}
                        className={cn(
                          'h-8',
                          empty && 'border-destructive/60',
                          edited && !empty && 'border-amber-400 ring-1 ring-amber-300',
                        )}
                        aria-label={`Answer ${number}`}
                      />
                      <span className="w-20 shrink-0 text-[11px] text-muted-foreground">
                        {answer?.kind === 'letter_set' && answer.set_numbers?.length
                          ? `set ${answer.set_numbers.join('&')}`
                          : answer?.kind ?? ''}
                      </span>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm this answer key?</AlertDialogTitle>
            <AlertDialogDescription>
              Every student who sits this test is marked against these answers. Confirm only after
              checking all {total} of them against the sheet. Attempts already submitted will be
              re-marked.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Not yet</AlertDialogCancel>
            <AlertDialogAction onClick={() => void verify()}>I have checked every answer</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AdminLayout>
  );
};

export default AnswerSheetEditor;
