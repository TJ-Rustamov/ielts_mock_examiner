/**
 * Listening audio player with two modes.
 *
 * Exam mode: the recording runs start to finish. No pause, no seeking, no
 * speed change - only volume, because headphones vary. Part files are chained
 * so the parts sound like one continuous recording.
 *
 * Practice mode: pause, a draggable seek bar, and 5-second skips.
 *
 * The lock is client-side deterrence, not DRM; anyone determined can pull the
 * file from devtools. What actually protects a score is the server clock,
 * which ends the attempt regardless of what the player did.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Headphones, Loader2, Pause, Play, Rewind, FastForward, SkipBack, SkipForward, Volume2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Slider } from '@/components/ui/slider';
import { fetchAudioObjectUrl, type AttemptMode, type ExamSection } from '@/lib/exams';
import { formatClock } from '@/hooks/use-exam-attempt';

interface LockedAudioPlayerProps {
  attemptId: number;
  sections: ExamSection[];
  mode: AttemptMode;
  startIndex?: number;
  onPartChange?: (index: number) => void;
  onFinished?: () => void;
}

const LockedAudioPlayer = ({
  attemptId, sections, mode, startIndex = 0, onPartChange, onFinished,
}: LockedAudioPlayerProps) => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const urls = useRef<Map<number, string>>(new Map());
  const pending = useRef<Map<number, Promise<string>>>(new Map());
  const lastTime = useRef(0);

  const [index, setIndex] = useState(startIndex);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [needsGesture, setNeedsGesture] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.9);
  const [finished, setFinished] = useState(false);

  const locked = mode === 'exam';

  const load = useCallback((i: number): Promise<string> => {
    const section = sections[i];
    if (!section) return Promise.reject(new Error('no such part'));
    const cached = urls.current.get(section.id);
    if (cached) return Promise.resolve(cached);
    const inflight = pending.current.get(section.id);
    if (inflight) return inflight;
    const request = fetchAudioObjectUrl(attemptId, section.id).then((url) => {
      urls.current.set(section.id, url);
      pending.current.delete(section.id);
      return url;
    });
    pending.current.set(section.id, request);
    return request;
  }, [attemptId, sections]);

  useEffect(() => {
    const owned = urls.current;
    return () => { owned.forEach((url) => URL.revokeObjectURL(url)); };
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    load(index)
      .then((url) => {
        if (cancelled) return;
        lastTime.current = 0;
        audio.src = url;
        audio.volume = volume;
        setLoading(false);
        audio.play().then(() => setNeedsGesture(false)).catch(() => setNeedsGesture(true));
        onPartChange?.(index);
        // Fetch the next part now so the handover at the end of this one is silent.
        load(index + 1).catch(() => undefined);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setLoading(false);
        setError(err.message || 'The audio could not be loaded.');
      });
    return () => { cancelled = true; };
    // Re-run only when the part changes; volume is applied by its own effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume;
  }, [volume]);

  const handleTimeUpdate = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (!audio.seeking) lastTime.current = audio.currentTime;
    setTime(audio.currentTime);
  };

  const handleSeeking = () => {
    const audio = audioRef.current;
    if (!audio || !locked) return;
    if (Math.abs(audio.currentTime - lastTime.current) > 0.75) audio.currentTime = lastTime.current;
  };

  const handlePause = () => {
    const audio = audioRef.current;
    setPlaying(false);
    if (!audio || !locked || audio.ended || audio.currentTime === 0) return;
    audio.play().catch(() => setNeedsGesture(true));
  };

  const handleRateChange = () => {
    const audio = audioRef.current;
    if (audio && locked && audio.playbackRate !== 1) audio.playbackRate = 1;
  };

  const handleEnded = () => {
    if (index < sections.length - 1) {
      setIndex((current) => current + 1);
      return;
    }
    setPlaying(false);
    setFinished(true);
    onFinished?.();
  };

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) audio.play().catch(() => setNeedsGesture(true));
    else audio.pause();
  };

  const seekTo = (seconds: number) => {
    const audio = audioRef.current;
    if (!audio || locked) return;
    const target = Math.max(0, Math.min(seconds, audio.duration || seconds));
    lastTime.current = target;
    audio.currentTime = target;
  };

  const partLabel = sections[index]?.label || `Part ${index + 1}`;

  return (
    <div className="space-y-2">
      <audio
        ref={audioRef}
        preload="auto"
        controls={false}
        onContextMenu={(event) => event.preventDefault()}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
        onPlay={() => setPlaying(true)}
        onPause={handlePause}
        onSeeking={handleSeeking}
        onRateChange={handleRateChange}
        onEnded={handleEnded}
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 shrink-0">
          <Headphones className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">{partLabel}</span>
          <span className="text-xs text-muted-foreground">
            {index + 1} / {sections.length}
          </span>
        </div>

        {!locked && (
          <div className="flex items-center gap-1">
            <Button size="icon" variant="ghost" className="h-8 w-8" aria-label="Previous part"
              disabled={index === 0} onClick={() => setIndex((i) => Math.max(0, i - 1))}>
              <SkipBack className="h-4 w-4" />
            </Button>
            <Button size="icon" variant="ghost" className="h-8 w-8" aria-label="Back 5 seconds"
              onClick={() => seekTo(time - 5)}>
              <Rewind className="h-4 w-4" />
            </Button>
            <Button size="icon" variant="outline" className="h-8 w-8" aria-label={playing ? 'Pause' : 'Play'}
              onClick={togglePlay}>
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>
            <Button size="icon" variant="ghost" className="h-8 w-8" aria-label="Forward 5 seconds"
              onClick={() => seekTo(time + 5)}>
              <FastForward className="h-4 w-4" />
            </Button>
            <Button size="icon" variant="ghost" className="h-8 w-8" aria-label="Next part"
              disabled={index >= sections.length - 1}
              onClick={() => setIndex((i) => Math.min(sections.length - 1, i + 1))}>
              <SkipForward className="h-4 w-4" />
            </Button>
          </div>
        )}

        <div className="flex flex-1 min-w-[180px] items-center gap-2">
          {locked ? (
            <Progress value={duration ? (time / duration) * 100 : 0} className="h-2" />
          ) : (
            <Slider
              value={[time]}
              max={duration || 1}
              step={1}
              onValueChange={([value]) => seekTo(value)}
              aria-label="Seek"
            />
          )}
          <span className="w-24 text-right text-xs tabular-nums text-muted-foreground">
            {formatClock(Math.floor(time))} / {formatClock(Math.floor(duration))}
          </span>
        </div>

        <div className="flex w-32 items-center gap-2">
          <Volume2 className="h-4 w-4 text-muted-foreground" />
          <Slider value={[volume]} max={1} step={0.05} onValueChange={([value]) => setVolume(value)}
            aria-label="Volume" />
        </div>
      </div>

      {loading && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" /> Loading audio...
        </p>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
      {needsGesture && !loading && (
        <Button size="sm" onClick={() => {
          audioRef.current?.play().then(() => setNeedsGesture(false)).catch(() => undefined);
        }}>
          <Play className="mr-1 h-4 w-4" /> Start the audio
        </Button>
      )}
      {locked && !finished && (
        <p className="text-xs text-muted-foreground">
          Exam mode: the recording plays once and cannot be paused or replayed.
        </p>
      )}
      {finished && (
        <p className="text-xs font-medium text-primary">
          The recording has finished. Use the remaining time to check your answers.
        </p>
      )}
    </div>
  );
};

export default LockedAudioPlayer;
