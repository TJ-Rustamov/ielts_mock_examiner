/**
 * Confirm an answer key without reading it - for an admin who will sit the test.
 *
 * The grid shows only what the self-checks made of each answer. Answers they
 * vouch for stay hidden; the ones they flag are opened one at a time, next to
 * the book's own printed key row, so the check is against the page rather
 * than memory. Every reveal is recorded server-side and counted here.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import {
  AlertTriangle, CheckCircle2, CircleDashed, Eye, ImageUp, Loader2, ShieldCheck, UserCheck,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import KeyCrop from '@/components/admin/KeyCrop';
import {
  confirmAnswers, errorMessage, revealAnswer, saveBlindCell, uploadBlindAnswerSheet,
  verifyAnswerSheet,
  type AdminModule, type BlindSheet, type CellStatus, type RevealedCell, type SheetAnswer,
} from '@/lib/exams';
import { cn } from '@/lib/utils';

const STATUS_STYLE: Record<CellStatus, string> = {
  trusted: 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  confirmed: 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-300',
  check: 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-300',
  missing: 'border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300',
};

const STATUS_LABEL: Record<CellStatus, string> = {
  trusted: 'Self-checks passed',
  confirmed: 'You checked it',
  check: 'Needs a look',
  missing: 'No answer yet',
};

const CHECK_LABEL: Record<string, string> = {
  present: 'Answer present',
  kind: 'Right kind of answer',
  option_range: 'One of the options',
  set_size: 'Right number of letters',
  word_limit: 'Within the word limit',
  in_source: 'Printed in the passage / audioscript',
  agreement: 'Two readings agree',
  confidence: 'OCR confidence',
  second_reading: 'Came from a second reading',
};

const StatusIcon = ({ status, className }: { status: CellStatus; className?: string }) => {
  if (status === 'trusted') return <CheckCircle2 className={className} />;
  if (status === 'confirmed') return <UserCheck className={className} />;
  if (status === 'missing') return <CircleDashed className={className} />;
  return <AlertTriangle className={className} />;
};

const joinAccepted = (answer: SheetAnswer | null | undefined) => (answer?.accepted ?? []).join(' / ');

interface BlindKeyReviewProps {
  moduleId: number;
  total: number;
  sheet: BlindSheet | null;
  module: AdminModule | null;
  onSheet: (sheet: BlindSheet) => void;
  onVerified: (module: AdminModule) => void;
}

const BlindKeyReview = ({ moduleId, total, sheet, module, onSheet, onVerified }: BlindKeyReviewProps) => {
  const [open, setOpen] = useState<number | null>(null);
  const [cell, setCell] = useState<RevealedCell | null>(null);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [confirmVerify, setConfirmVerify] = useState(false);
  const [peek, setPeek] = useState<number | null>(null);

  const numbers = Array.from({ length: total }, (_, index) => index + 1);
  const counts = sheet?.status_counts ?? { trusted: 0, confirmed: 0, check: 0, missing: total };
  const outstanding = numbers.filter((number) => {
    const status = sheet?.cells[String(number)]?.status ?? 'missing';
    return status === 'check' || status === 'missing';
  });

  const openCell = async (number: number) => {
    setOpen(number);
    setCell(null);
    setValue('');
    try {
      const revealed = await revealAnswer(moduleId, number);
      setCell(revealed);
      setValue(joinAccepted(revealed.answer));
    } catch (error) {
      toast.error(errorMessage(error, 'Could not open this answer.'));
      setOpen(null);
    }
  };

  const requestOpen = (number: number) => {
    const status = sheet?.cells[String(number)]?.status;
    // Opening a trusted answer is allowed but deliberate: it spoils that one.
    if (status === 'trusted' || status === 'confirmed') setPeek(number);
    else void openCell(number);
  };

  const closeCell = () => { setOpen(null); setCell(null); };

  const accept = async () => {
    if (open === null) return;
    setBusy(true);
    try {
      onSheet(await confirmAnswers(moduleId, [open]));
      toast.success(`Question ${open} confirmed.`);
      closeCell();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not confirm.'));
    } finally {
      setBusy(false);
    }
  };

  const save = async (text: string) => {
    if (open === null) return;
    const trimmed = text.trim();
    if (!trimmed) { toast.error('Type the answer first.'); return; }
    setBusy(true);
    try {
      const original = cell?.answer;
      // Keep kind and set details so, for example, a TRUE/FALSE key still
      // accepts "T" after the edit.
      const payload: string | SheetAnswer = original
        ? { ...original, accepted: trimmed.split('/').map((part) => part.trim()).filter(Boolean) }
        : trimmed;
      onSheet(await saveBlindCell(moduleId, open, payload));
      toast.success(`Question ${open} saved.`);
      closeCell();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save.'));
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    try {
      const response = await uploadBlindAnswerSheet(moduleId, file);
      onSheet(response.sheet);
      toast.success(
        response.filled_by_ocr
          ? `Read ${response.filled_by_ocr} more answer(s) from the image, and cross-checked the rest.`
          : 'Cross-checked the key against the image.',
      );
    } catch (error) {
      toast.error(errorMessage(error, 'Could not read the image.'));
    } finally {
      setUploading(false);
    }
  };

  const verify = async () => {
    setVerifying(true);
    try {
      const response = await verifyAnswerSheet(moduleId, 'blind');
      toast.success(
        response.remarked_attempts
          ? `Verified. ${response.remarked_attempts} submitted attempt(s) were re-marked.`
          : 'Verified - without showing you the answers the checks vouched for.',
      );
      onVerified(response.module);
    } catch (error) {
      toast.error(errorMessage(error, 'Could not verify.'));
    } finally {
      setVerifying(false);
      setConfirmVerify(false);
    }
  };

  const correction = cell?.check?.correction;
  const notes = (cell?.check?.checks ?? []).filter((check) => check.result !== 'pass' || check.note);

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-3 py-4">
          {(['trusted', 'confirmed', 'check', 'missing'] as CellStatus[]).map((status) => (
            <span key={status} className={cn('flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm', STATUS_STYLE[status])}>
              <StatusIcon status={status} className="h-4 w-4" />
              {counts[status] ?? 0} {STATUS_LABEL[status].toLowerCase()}
            </span>
          ))}
          <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
            <Eye className="h-3.5 w-3.5" />
            You have seen {sheet?.revealed.length ?? 0} of {total} answers
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="text-base">Answers, hidden</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {outstanding.length
                ? `Open the ${outstanding.length} amber or red question(s) one at a time and compare each with the book's key row.`
                : 'Nothing is left to look at. You can verify without seeing the rest.'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline" disabled={uploading}>
              <label className="cursor-pointer" title="A photo or scan of the key page adds a second reading to cross-check against. It is not shown here.">
                {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ImageUp className="mr-2 h-4 w-4" />}
                Cross-check with a photo
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ''; }}
                />
              </label>
            </Button>
            {outstanding.length > 0 && (
              <Button size="sm" variant="secondary" onClick={() => void openCell(outstanding[0])}>
                Next to check ({outstanding[0]})
              </Button>
            )}
            <Button
              size="sm"
              onClick={() => setConfirmVerify(true)}
              disabled={!sheet || outstanding.length > 0 || verifying || sheet.is_verified}
              title={outstanding.length ? 'Look at every amber and red question first' : ''}
            >
              <ShieldCheck className="mr-2 h-4 w-4" />
              {sheet?.is_verified ? 'Verified' : 'Verify without revealing'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {!sheet ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              This module has no answer key yet. Publish its import, or cross-check with a photo of the key page.
            </p>
          ) : (
            <div className="grid grid-cols-5 gap-2 sm:grid-cols-8 lg:grid-cols-10">
              {numbers.map((number) => {
                const info = sheet.cells[String(number)];
                const status: CellStatus = info?.status ?? 'missing';
                const failing = (info?.checks ?? []).filter((check) => check.result !== 'pass');
                return (
                  <button
                    key={number}
                    type="button"
                    onClick={() => requestOpen(number)}
                    className={cn(
                      'flex h-14 flex-col items-center justify-center rounded-md border text-sm font-medium tabular-nums transition hover:brightness-95',
                      STATUS_STYLE[status],
                    )}
                    title={[
                      STATUS_LABEL[status],
                      ...failing.map((check) => `${CHECK_LABEL[check.name] ?? check.name}: ${check.result}`),
                      info?.revealed ? '(you have seen this one)' : '',
                    ].filter(Boolean).join('\n')}
                    aria-label={`Question ${number}: ${STATUS_LABEL[status]}`}
                  >
                    <span>{number}</span>
                    <StatusIcon status={status} className="mt-0.5 h-3.5 w-3.5 opacity-80" />
                  </button>
                );
              })}
            </div>
          )}
          {!!sheet?.notes_count && (
            <p className="mt-4 text-xs text-muted-foreground">
              {sheet.notes_count} import note(s) are hidden here because they quote answers.
              Switch off blind mode to read them.
            </p>
          )}
          {module && module.blocking_problems.length > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              Blocking publication: {module.blocking_problems.join('; ')}
            </p>
          )}
        </CardContent>
      </Card>

      <Dialog open={open !== null} onOpenChange={(next) => { if (!next) closeCell(); }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Question {open}</DialogTitle>
            <DialogDescription>
              Compare with the printed key row. Confirm it if it matches; correct it if it does not.
            </DialogDescription>
          </DialogHeader>
          {open !== null && (
            <div className="space-y-4">
              <KeyCrop moduleId={moduleId} number={open} available={cell ? cell.has_crop : true} />
              {!cell ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> Loading…
                </div>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium" htmlFor="blind-answer">
                      Accepted answer{cell.answer?.kind ? ` (${cell.answer.kind.replace('_', ' ')})` : ''}
                    </label>
                    <Input
                      id="blind-answer"
                      value={value}
                      onChange={(event) => setValue(event.target.value)}
                      spellCheck={false}
                      placeholder="Separate alternatives with a slash, e.g. 10 / ten"
                    />
                    {cell.answer?.set_numbers && cell.answer.set_numbers.length > 1 && (
                      <p className="text-xs text-muted-foreground">
                        Shared by questions {cell.answer.set_numbers.join(' & ')} (in either order).
                      </p>
                    )}
                  </div>
                  {correction && (
                    <div className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm dark:border-sky-900 dark:bg-sky-950">
                      {correction.explained
                        ? <>Corrected from OCR <code>{correction.from.join(' / ')}</code> to the passage spelling.</>
                        : <>The passage has <code>{correction.to.join(' / ')}</code>.</>}
                      {!correction.explained && (
                        <Button size="sm" variant="link" className="h-auto px-1" onClick={() => setValue(correction.to.join(' / '))}>
                          Use this
                        </Button>
                      )}
                    </div>
                  )}
                  {notes.length > 0 && (
                    <ul className="space-y-1 text-xs">
                      {notes.map((check, index) => (
                        <li key={index} className="flex gap-2">
                          <Badge variant={check.result === 'fail' ? 'destructive' : check.result === 'warn' ? 'secondary' : 'outline'} className="shrink-0">
                            {check.result}
                          </Badge>
                          <span>
                            <span className="font-medium">{CHECK_LABEL[check.name] ?? check.name}</span>
                            {check.note ? ` - ${check.note}` : ''}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {cell.raw_text && (
                    <p className="text-xs text-muted-foreground">As read from the page: <code>{cell.raw_text}</code></p>
                  )}
                </>
              )}
            </div>
          )}
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="ghost" onClick={closeCell}>Close</Button>
            {cell?.answer && value.trim() === joinAccepted(cell.answer) ? (
              <Button onClick={() => void accept()} disabled={busy}>
                {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <UserCheck className="mr-2 h-4 w-4" />}
                Matches the book
              </Button>
            ) : (
              <Button onClick={() => void save(value)} disabled={busy || !cell}>
                {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save this answer
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={peek !== null} onOpenChange={(next) => { if (!next) setPeek(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Show answer {peek}?</AlertDialogTitle>
            <AlertDialogDescription>
              The self-checks already vouch for this one. Opening it shows you the answer, which
              you will then know when you sit the test.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it hidden</AlertDialogCancel>
            <AlertDialogAction onClick={() => { const number = peek; setPeek(null); if (number !== null) void openCell(number); }}>
              Show it
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmVerify} onOpenChange={setConfirmVerify}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Verify without revealing?</AlertDialogTitle>
            <AlertDialogDescription>
              {counts.trusted} answer(s) passed every self-check and stay hidden; {counts.confirmed} you
              checked yourself. Every student who sits this test is marked against this key. If a
              hidden answer turns out wrong, fix it from your results page after you sit the test -
              attempts are re-marked automatically.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Not yet</AlertDialogCancel>
            <AlertDialogAction onClick={() => void verify()}>Verify</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default BlindKeyReview;
