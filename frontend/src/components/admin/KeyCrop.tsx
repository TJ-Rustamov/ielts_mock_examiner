/**
 * The printed answer-key row for one question, cut from the book's own page.
 *
 * Behind an authenticated endpoint, so it is fetched into a blob URL rather
 * than pointed at with <img src>. Revoked on unmount or when the cell changes.
 */
import { useEffect, useState } from 'react';
import { ImageOff, Loader2 } from 'lucide-react';
import { fetchKeyCropUrl } from '@/lib/exams';

interface KeyCropProps {
  moduleId: number;
  number: number;
  /** Skip the request when the server already said there is no crop. */
  available?: boolean;
}

const KeyCrop = ({ moduleId, number, available = true }: KeyCropProps) => {
  const [url, setUrl] = useState<string | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'none'>(available ? 'loading' : 'none');

  useEffect(() => {
    if (!available) {
      setState('none');
      return undefined;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setState('loading');
    setUrl(null);
    fetchKeyCropUrl(moduleId, number)
      .then((result) => {
        objectUrl = result;
        if (cancelled) {
          if (result) URL.revokeObjectURL(result);
          return;
        }
        setUrl(result);
        setState(result ? 'ready' : 'none');
      })
      .catch(() => { if (!cancelled) setState('none'); });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [moduleId, number, available]);

  if (state === 'loading') {
    return (
      <div className="flex h-20 items-center justify-center rounded border bg-muted/40 text-xs text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading the book's key row…
      </div>
    );
  }
  if (state === 'none' || !url) {
    return (
      <div className="flex h-16 items-center justify-center gap-2 rounded border border-dashed text-xs text-muted-foreground">
        <ImageOff className="h-4 w-4" /> No picture of this row - check it in the book.
      </div>
    );
  }
  return (
    <img
      src={url}
      alt={`Answer key row for question ${number}`}
      className="w-full rounded border bg-white"
    />
  );
};

export default KeyCrop;
