import { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Mic, Volume2, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import Layout from '@/components/Layout';
import { useParams } from 'react-router-dom';
import { useThemeContext } from '@/contexts/ThemeContext';
import { wsUrl } from '@/lib/backend';
import { getAuthToken, getCurrentUser } from '@/lib/auth';

type MessageEnvelope = {
  type: string;
  session_id?: string;
  payload?: Record<string, any>;
};

const arrayBufferToBase64 = (buffer: ArrayBuffer): string => {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
};

const base64ToUint8Array = (base64: string): Uint8Array => {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
};

const float32ToPcm16 = (input: Float32Array): ArrayBuffer => {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const s = Math.max(-1, Math.min(1, input[i]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return output.buffer;
};

const SpeakingTest = () => {
  const { part } = useParams();
  const { setStudyMode } = useThemeContext();
  const isPart2 = String(part || '').trim() === '2';

  const [testState, setTestState] = useState<'idle' | 'recording' | 'processing' | 'finished'>('idle');
  const [sessionStarted, setSessionStarted] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [prepSecondsLeft, setPrepSecondsLeft] = useState(0);
  const [speakingSecondsLeft, setSpeakingSecondsLeft] = useState(0);
  const [examinerTurns, setExaminerTurns] = useState<string[]>([]);
  const [transcript, setTranscript] = useState('');
  const [report, setReport] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const playbackQueueRef = useRef<Promise<void>>(Promise.resolve());
  const examinerSpeakingRef = useRef(false);
  const stopRequestedRef = useRef(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const mutedGainRef = useRef<GainNode | null>(null);
  const sampleRateRef = useRef<number>(16000);
  const utteranceActiveRef = useRef(false);
  const utteranceSilenceMsRef = useRef(0);
  const utteranceSpeechMsRef = useRef(0);

  useEffect(() => { setStudyMode('speaking'); }, [setStudyMode]);

  useEffect(() => {
    if (testState !== 'recording') return;
    const interval = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [testState]);

  useEffect(() => {
    if (!isPart2 || !sessionStarted || testState === 'finished') return;
    const interval = setInterval(() => {
      setPrepSecondsLeft((prev) => (prev > 0 ? prev - 1 : 0));
      setSpeakingSecondsLeft((prev) => {
        if (prepSecondsLeft > 0) return prev;
        if (testState !== 'recording') return prev;
        return prev > 0 ? prev - 1 : 0;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [isPart2, sessionStarted, prepSecondsLeft, testState]);

  useEffect(() => {
    if (!isPart2 || !sessionStarted) return;
    if (prepSecondsLeft <= 0 && speakingSecondsLeft === 0 && testState === 'recording') {
      requestFinalReport();
    }
  }, [isPart2, sessionStarted, prepSecondsLeft, speakingSecondsLeft, testState]);

  useEffect(() => {
    return () => {
      if (socketRef.current) socketRef.current.close();
      stopMicCapture();
    };
  }, []);

  const overallBand = useMemo(() => Number(report?.scores?.overall_band || 0).toFixed(1), [report]);

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const connectSocket = (): Promise<void> => {
    return new Promise((resolve, reject) => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      const socket = new WebSocket(wsUrl('/ws/speaking/test'));
      socketRef.current = socket;

      socket.onopen = () => resolve();
      socket.onerror = () => reject(new Error('WebSocket connection failed'));

      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data) as MessageEnvelope;

        if (msg.type === 'session.started') {
          setSessionStarted(true);
          setSessionId(msg.session_id || null);
          if (isPart2) {
            const timers = msg.payload?.timers || {};
            setPrepSecondsLeft(Number(timers.prep_seconds || 0));
            setSpeakingSecondsLeft(Number(timers.speaking_seconds || 0));
          }
        }

        if (msg.type === 'examiner.text' && msg.payload?.text) {
          setExaminerTurns((prev) => [...prev, String(msg.payload?.text)]);
        }

        if (msg.type === 'examiner.audio' && msg.payload?.audio_base64) {
          queueAudioPlayback(String(msg.payload.audio_base64));
        }

        if (msg.type === 'transcript.final' && msg.payload?.text) {
          setTranscript(String(msg.payload?.text));
        }

        if (msg.type === 'timer.update' && msg.payload?.phase === 'prep') {
          setPrepSecondsLeft(Number(msg.payload.seconds_left || 0));
        }

        if (msg.type === 'session.report') {
          setReport(msg.payload || null);
          stopMicCapture();
          setTestState('finished');
        }

        if (msg.type === 'error') {
          setError(String(msg.payload?.message || 'Unknown socket error'));
          stopMicCapture();
          setTestState('idle');
        }
      };
    });
  };

  const queueAudioPlayback = (audioBase64: string) => {
    playbackQueueRef.current = playbackQueueRef.current.then(async () => {
      if (stopRequestedRef.current) return;
      examinerSpeakingRef.current = true;
      const bytes = base64ToUint8Array(audioBase64);
      const blob = new Blob([bytes], { type: 'audio/wav' });
      const url = URL.createObjectURL(blob);
      try {
        if (stopRequestedRef.current) return;
        const audio = new Audio(url);
        currentAudioRef.current = audio;
        await audio.play();
        await new Promise<void>((resolve) => {
          audio.onended = () => resolve();
          audio.onerror = () => resolve();
        });
      } catch {
        // Ignore autoplay errors and continue queue.
      } finally {
        examinerSpeakingRef.current = false;
        currentAudioRef.current = null;
        URL.revokeObjectURL(url);
      }
    });
  };

  const sendAudioChunk = (pcmBuffer: ArrayBuffer, forceTranscribe = false) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
    if (examinerSpeakingRef.current && !forceTranscribe) return;
    if (isPart2 && prepSecondsLeft > 0 && !forceTranscribe) return;
    const msg: MessageEnvelope = {
      type: 'audio.chunk',
      session_id: sessionId || undefined,
      payload: {
        audio_base64: arrayBufferToBase64(pcmBuffer),
        mime_type: 'audio/pcm',
        sample_rate: sampleRateRef.current,
        force_transcribe: forceTranscribe,
      },
    };
    socketRef.current.send(JSON.stringify(msg));
  };

  const stopMicCapture = () => {
    utteranceActiveRef.current = false;
    utteranceSilenceMsRef.current = 0;
    utteranceSpeechMsRef.current = 0;
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current.onaudioprocess = null;
      processorRef.current = null;
    }
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }
    if (mutedGainRef.current) {
      mutedGainRef.current.disconnect();
      mutedGainRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => undefined);
      audioContextRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  };

  const stopAllPlayback = () => {
    stopRequestedRef.current = true;
    examinerSpeakingRef.current = false;
    if (currentAudioRef.current) {
      try {
        currentAudioRef.current.pause();
        currentAudioRef.current.currentTime = 0;
      } catch {
        // noop
      }
      currentAudioRef.current = null;
    }
    // Reset queue so pending examiner audios are discarded.
    playbackQueueRef.current = Promise.resolve();
  };

  const startSessionIfNeeded = () => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN || sessionStarted) return;

    const startMsg: MessageEnvelope = {
      type: 'session.start',
      payload: {
        part: part || 'all',
        token: getAuthToken() || undefined,
        candidate: { name: getCurrentUser()?.username || 'Candidate' },
      },
    };
    socketRef.current.send(JSON.stringify(startMsg));
  };

  const startRecording = async () => {
    setError(null);
    try {
      stopRequestedRef.current = false;
      await connectSocket();
      startSessionIfNeeded();

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = stream;

      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;
      sampleRateRef.current = audioContext.sampleRate || 16000;

      const source = audioContext.createMediaStreamSource(stream);
      sourceNodeRef.current = source;

      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;
      processor.onaudioprocess = (event) => {
        const channel = event.inputBuffer.getChannelData(0);
        const pcm = float32ToPcm16(channel);
        const rms = Math.sqrt(channel.reduce((acc, v) => acc + v * v, 0) / Math.max(1, channel.length));
        const durationMs = (channel.length / Math.max(1, sampleRateRef.current)) * 1000;
        const speechThreshold = 0.012;
        const silenceToEndMs = 700;
        const minUtteranceMs = 450;

        if (examinerSpeakingRef.current) return;

        if (rms >= speechThreshold) {
          utteranceActiveRef.current = true;
          utteranceSilenceMsRef.current = 0;
          utteranceSpeechMsRef.current += durationMs;
          sendAudioChunk(pcm, false);
          return;
        }

        if (!utteranceActiveRef.current) return;

        utteranceSilenceMsRef.current += durationMs;
        sendAudioChunk(pcm, false);

        if (utteranceSilenceMsRef.current >= silenceToEndMs && utteranceSpeechMsRef.current >= minUtteranceMs) {
          sendAudioChunk(new Uint8Array(640).buffer, true);
          utteranceActiveRef.current = false;
          utteranceSilenceMsRef.current = 0;
          utteranceSpeechMsRef.current = 0;
        }
      };

      const mutedGain = audioContext.createGain();
      mutedGain.gain.value = 0;
      mutedGainRef.current = mutedGain;

      source.connect(processor);
      processor.connect(mutedGain);
      mutedGain.connect(audioContext.destination);

      setSeconds(0);
      setTestState('recording');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Microphone or connection error');
    }
  };

  const requestFinalReport = () => {
    stopAllPlayback();
    sendAudioChunk(new Uint8Array(640).buffer, true);
    stopMicCapture();
    setTestState('processing');
    socketRef.current?.send(JSON.stringify({ type: 'session.stop', session_id: sessionId || undefined, payload: {} }));
  };

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 max-w-2xl relative">
        <div className="absolute w-64 h-64 bg-primary/8 rounded-full blur-3xl top-10 left-1/2 -translate-x-1/2 pointer-events-none animate-float" />

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="text-center relative z-10">
          <h1 className="text-2xl font-bold text-foreground mb-2">Speaking Test - Part {part}</h1>

          {error && <p className="text-destructive mb-4">{error}</p>}

          {testState !== 'finished' && (
            <div className="space-y-4 mt-10">
              <Card className="glass-card">
                <CardContent className="py-6 text-left space-y-3">
                  {examinerTurns.length === 0 && <p className="text-muted-foreground">Start recording to begin the speaking interaction.</p>}
                  {examinerTurns.map((turn, i) => (
                    <p key={i} className="text-sm">Examiner: {turn}</p>
                  ))}
                  {transcript && <p className="text-sm text-primary">You: {transcript}</p>}
                </CardContent>
              </Card>

              <div className="font-mono text-3xl font-bold text-foreground">{formatTime(seconds)}</div>
              {isPart2 && (
                <div className="flex items-center justify-center gap-3 text-sm">
                  <span className="px-3 py-1 rounded bg-muted text-foreground">
                    Prep: {formatTime(prepSecondsLeft)}
                  </span>
                  <span className="px-3 py-1 rounded bg-muted text-foreground">
                    Speak: {formatTime(speakingSecondsLeft)}
                  </span>
                </div>
              )}

              <div className="flex items-center justify-center gap-3">
                  {!sessionStarted && (
                    <Button onClick={startRecording} className="gap-2 h-11 glow-sm">
                      <Mic className="h-4 w-4" /> Start Test
                    </Button>
                  )}
                  <Button variant="outline" onClick={requestFinalReport} disabled={!sessionStarted} className="h-11">
                    Finish & Get Report
                  </Button>
              </div>
            </div>
          )}

          {testState === 'finished' && report && (
            <div className="text-left mt-8 space-y-6">
              <div className="text-center">
                <div className="inline-flex flex-col items-center p-6 rounded-2xl bg-primary/10 glow">
                  <p className="text-5xl font-bold text-primary">{overallBand}</p>
                  <p className="text-sm text-muted-foreground mt-1 font-medium">Overall Band Score</p>
                </div>
              </div>

              <Card>
                <CardContent className="py-5 space-y-3">
                  <p className="text-sm"><CheckCircle2 className="h-4 w-4 inline mr-2 text-primary" />FC: {report?.scores?.fc}</p>
                  <p className="text-sm"><CheckCircle2 className="h-4 w-4 inline mr-2 text-primary" />LR: {report?.scores?.lr}</p>
                  <p className="text-sm"><CheckCircle2 className="h-4 w-4 inline mr-2 text-primary" />GRA: {report?.scores?.gra}</p>
                  <p className="text-sm mt-3 text-muted-foreground whitespace-pre-wrap">{report?.examiner_comments}</p>
                </CardContent>
              </Card>

              <Button variant="outline" onClick={() => window.location.reload()} className="h-11 gap-2">
                <Volume2 className="h-4 w-4" /> Start New Session
              </Button>
            </div>
          )}
        </motion.div>
      </div>
    </Layout>
  );
};

export default SpeakingTest;
