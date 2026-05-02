import { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Mic, Volume2, CheckCircle2, Loader2, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import Layout from '@/components/Layout';
import { useParams } from 'react-router-dom';
import { useThemeContext } from '@/contexts/ThemeContext';
import { fetchJson, wsUrl } from '@/lib/backend';
import { getAuthToken, getCurrentUser } from '@/lib/auth';

type MessageEnvelope = {
  type: string;
  session_id?: string;
  payload?: Record<string, any>;
};

type TurnState = 'examiner_speaking' | 'candidate_speaking' | 'processing_candidate' | 'finished' | 'preparation';

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

const CollapsibleMessage = ({ text }: { text: string }) => {
  const [expanded, setExpanded] = useState(false);
  const isPart2Eval = text.startsWith('[Part 2 evaluated]');
  const displayText = isPart2Eval ? text.replace('[Part 2 evaluated]', '').trim() : text;
  
  if (!isPart2Eval) {
    return <p className="whitespace-pre-wrap leading-relaxed font-medium">{text}</p>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2 border-b border-primary-foreground/20 pb-1 mb-1">
        <span className="text-xs opacity-90 font-semibold italic">Long Speech Transcript</span>
        <button 
          onClick={() => setExpanded(!expanded)} 
          className="text-[10px] uppercase tracking-wider bg-primary-foreground/10 hover:bg-primary-foreground/20 px-2 py-0.5 rounded transition-colors"
        >
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>
      <p className={`whitespace-pre-wrap leading-relaxed font-medium ${expanded ? '' : 'line-clamp-3 opacity-90'}`}>
        {displayText}
      </p>
    </div>
  );
};

const SpeakingTest = () => {
  const { part } = useParams();
  const { setStudyMode } = useThemeContext();
  const initialIsPart2 = String(part || '').trim() === '2';

  const [isPart2Active, setIsPart2Active] = useState(initialIsPart2);
  const [testState, setTestState] = useState<'idle' | 'recording' | 'processing' | 'finished'>('idle');
  const [sessionStarted, setSessionStarted] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [prepSecondsLeft, setPrepSecondsLeft] = useState(0);
  const [speakingSecondsLeft, setSpeakingSecondsLeft] = useState(0);
  const [messages, setMessages] = useState<{ id: string; role: 'examiner' | 'candidate'; text: string; isCueCard?: boolean }[]>([]);
  const [report, setReport] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [turnState, setTurnState] = useState<TurnState>('processing_candidate');
  const [startingSession, setStartingSession] = useState(false);
  const [evaluationStatus, setEvaluationStatus] = useState<'idle' | 'processing' | 'ready'>('idle');
  const [firstExaminerAudioReceived, setFirstExaminerAudioReceived] = useState(false);
  const [timerPhase, setTimerPhase] = useState<'idle' | 'prep' | 'speaking'>('idle');
  const [cueCardText, setCueCardText] = useState<string>('');

  const socketRef = useRef<WebSocket | null>(null);
  const playbackQueueRef = useRef<Promise<void>>(Promise.resolve());
  const turnStateRef = useRef<TurnState>('processing_candidate');
  const stopRequestedRef = useRef(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const nextPlaybackTimeRef = useRef<number>(0);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const mutedGainRef = useRef<GainNode | null>(null);
  const sampleRateRef = useRef<number>(16000);
  const utteranceActiveRef = useRef(false);
  const utteranceSilenceMsRef = useRef(0);
  const utteranceSpeechMsRef = useRef(0);
  const turnEndSilenceMsRef = useRef(700);
  const turnMinSpeechMsRef = useRef(450);
  const activeAudioChunkIdRef = useRef<string | null>(null);
  const expectedAudioSeqRef = useRef(0);
  const audioChunkBufferRef = useRef<Map<number, { audioBase64: string; isLast: boolean }>>(new Map());
  const messagesTopRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { setStudyMode('speaking'); }, [setStudyMode]);

  useEffect(() => {
    if (testState !== 'recording') return;
    const interval = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [testState]);

  useEffect(() => {
    if (messagesTopRef.current && messagesTopRef.current.parentElement) {
      messagesTopRef.current.parentElement.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [messages, turnState]);

  useEffect(() => {
    return () => {
      if (socketRef.current) socketRef.current.close();
      stopMicCapture();
    };
  }, []);

  useEffect(() => {
    if (!sessionId || evaluationStatus !== 'processing') return;
    let cancelled = false;

    const poll = async () => {
      try {
        const data = await fetchJson<{ status: string; final_report?: Record<string, any>; scores?: Record<string, any> }>(
          `/api/speaking/sessions/${sessionId}`
        );
        if (cancelled) return;
        if (data.status === 'finished' && data.final_report && Object.keys(data.final_report).length > 0) {
          setReport(data.final_report);
          setEvaluationStatus('ready');
        } else if (!report && data.scores) {
          setReport({ scores: data.scores });
        }
      } catch {
        if (cancelled) return;
      }
    };

    const timer = window.setInterval(poll, 2500);
    poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [sessionId, evaluationStatus, report]);

  const overallBand = useMemo(() => Number(report?.scores?.overall_band || 0).toFixed(1), [report]);
  const turnStatusText = useMemo(() => {
    if (!sessionStarted) return 'Waiting to start';
    if (turnState === 'examiner_speaking') return 'Examiner speaking...';
    if (turnState === 'candidate_speaking') return 'Your turn';
    if (turnState === 'processing_candidate') return 'Processing your answer...';
    return 'Session finished';
  }, [sessionStarted, turnState]);

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const resetUtteranceTracking = () => {
    utteranceActiveRef.current = false;
    utteranceSilenceMsRef.current = 0;
    utteranceSpeechMsRef.current = 0;
  };

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

      socket.onclose = (event) => {
        if (!event.wasClean && testState !== 'finished' && testState !== 'idle') {
          setError('Connection lost. Please refresh the page or try again.');
          stopMicCapture();
          setStartingSession(false);
          setTestState('idle');
        }
      };

      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data) as MessageEnvelope;

        if (msg.type === 'session.started') {
          setSessionStarted(true);
          setMessages([]);
          setFirstExaminerAudioReceived(false);
          setSessionId(msg.session_id || null);
          if (isPart2Active) {
            const timers = msg.payload?.timers || {};
            setPrepSecondsLeft(Number(timers.prep_seconds || 0));
            setSpeakingSecondsLeft(Number(timers.speaking_seconds || 0));
            setTimerPhase('idle');
          }
          const turnConfig = msg.payload?.turn || {};
          turnEndSilenceMsRef.current = Number(turnConfig.end_silence_ms || 700);
          turnMinSpeechMsRef.current = Number(turnConfig.min_speech_ms || 450);
        }

        if (msg.type === 'turn.state') {
          const next = String(msg.payload?.state || '') as TurnState;
          if (next) {
            turnStateRef.current = next;
            setTurnState(next);
            if (next !== 'candidate_speaking') resetUtteranceTracking();
            if (next !== 'candidate_speaking' && next !== 'preparation') {
              setTimerPhase('idle');
            }
          }
        }

        if (msg.type === 'examiner.text.start') {
          // Add an empty message for the new turn
          setMessages((prev) => [...prev, { id: Date.now().toString() + Math.random(), role: 'examiner', text: '' }]);
        }

        if (msg.type === 'examiner.text.chunk' && msg.payload?.text) {
          const textChunk = String(msg.payload.text);
          setMessages((prev) => {
            if (prev.length === 0) return prev;
            const lastMsg = prev[prev.length - 1];
            if (lastMsg.role === 'examiner') {
              let updatedText = lastMsg.text + textChunk;
              let isCueCard = lastMsg.isCueCard;
              if (updatedText.includes('[PART2]')) {
                  isCueCard = true;
                  updatedText = updatedText.replace(/\[PART2\]\s*/g, '');
              }
              const updated = [...prev];
              updated[updated.length - 1] = { ...lastMsg, text: updatedText, isCueCard };
              return updated;
            }
            return [...prev, { id: Date.now().toString() + Math.random(), role: 'examiner', text: textChunk }];
          });
        }
        
        // Keep examiner.text for backward compatibility if greeting isn't streamed
        if (msg.type === 'examiner.text' && msg.payload?.text) {
          let text = String(msg.payload.text);
          let isCueCard = false;
          if (text.includes('[PART2]')) {
             isCueCard = true;
             text = text.replace(/\[PART2\]\s*/g, '');
          }
          if (text) {
            setMessages((prev) => [...prev, { id: Date.now().toString() + Math.random(), role: 'examiner', text, isCueCard }]);
          }
        }

        if (msg.type === 'examiner.audio.chunk' && msg.payload?.audio_base64 !== undefined) {
          setStartingSession(false);
          setFirstExaminerAudioReceived(true);
          const chunkId = String(msg.payload.chunk_id || '').trim();
          const seq = Number(msg.payload.seq || 0);
          const isLast = Boolean(msg.payload.is_last);
          if (chunkId) queueAudioPlaybackChunk(chunkId, seq, isLast, String(msg.payload.audio_base64));
        }

        if (msg.type === 'playback.stop') {
           stopAllPlayback();
        }

        if (msg.type === 'turn.interrupted') {
          setMessages((prev) => {
            if (prev.length === 0) return prev;
            const lastMsg = prev[prev.length - 1];
            if (lastMsg.role === 'examiner') {
              const updated = [...prev];
              updated[updated.length - 1] = { ...lastMsg, text: lastMsg.text + ' [Interrupted]' };
              return updated;
            }
            return prev;
          });
        }

        if (msg.type === 'transcript.final' && msg.payload?.text) {
          const text = String(msg.payload.text);
          if (text) {
            setMessages((prev) => {
              if (text.startsWith('[Part 2 evaluated]')) {
                const pIdx = prev.findIndex(m => m.role === 'candidate' && m.text.includes('[Candidate completed Part 2'));
                if (pIdx !== -1) {
                  const newM = [...prev];
                  newM[pIdx] = { ...newM[pIdx], text };
                  return newM;
                }
              }
              return [...prev, { id: Date.now().toString() + Math.random(), role: 'candidate', text }];
            });
          }
        }

        if (msg.type === 'timer.update') {
          if (msg.payload?.phase === 'prep') {
            setPrepSecondsLeft(Number(msg.payload.seconds_left || 0));
          } else if (msg.payload?.phase === 'speaking') {
            const left = Number(msg.payload.seconds_left || 0);
            setSpeakingSecondsLeft(left);
            if (left <= 0) setTimerPhase('idle');
          }
        }

        if (msg.type === 'timer.start_prep') {
          setTimerPhase('prep');
          setIsPart2Active(true);
          setPrepSecondsLeft(Number(msg.payload?.seconds || 60));
        }

        if (msg.type === 'timer.start_speaking') {
          setTimerPhase('speaking');
          setIsPart2Active(true);
          setSpeakingSecondsLeft(Number(msg.payload?.seconds || 120));
        }

        if (msg.type === 'session.report.partial') {
          setReport({ scores: msg.payload?.scores || {} });
          setEvaluationStatus('processing');
          stopMicCapture();
          setTestState('finished');
          setTimerPhase('idle');
          setTurnState('finished');
        }

        if (msg.type === 'session.report.final') {
          setReport(msg.payload || null);
          setEvaluationStatus('ready');
          stopMicCapture();
          setTestState('finished');
          setTimerPhase('idle');
          setTurnState('finished');
        }

        if (msg.type === 'session.report') {
          setReport(msg.payload || null);
          setEvaluationStatus('ready');
          stopMicCapture();
          setTestState('finished');
          setTimerPhase('idle');
          setTurnState('finished');
        }

        if (msg.type === 'error') {
          setError(String(msg.payload?.message || 'Unknown socket error'));
          setStartingSession(false);
          stopMicCapture();
          setTestState('idle');
        }
      };
    });
  };

  const queueAudioPlayback = (audioBase64: string, isLast: boolean, chunkId: string) => {
    playbackQueueRef.current = playbackQueueRef.current.then(async () => {
      if (stopRequestedRef.current) return;
      
      try {
        if (!audioContextRef.current) {
          audioContextRef.current = new AudioContext({ sampleRate: 16000 });
        }
        const ctx = audioContextRef.current;
        if (ctx.state === 'suspended') {
          await ctx.resume();
        }

        const bytes = base64ToUint8Array(audioBase64);
        const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
        const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
        
        if (stopRequestedRef.current) return;

        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);
        activeSourcesRef.current.push(source);

        const currentTime = ctx.currentTime;
        // If nextPlaybackTime is in the past, start immediately
        let startTime = Math.max(currentTime, nextPlaybackTimeRef.current);
        // Add a tiny buffer if we're starting immediately to avoid glitches
        if (startTime === currentTime) startTime += 0.05;
        
        source.start(startTime);
        
        // Slightly overlap chunks to eliminate natural silence padding introduced by TTS at the end of sentences
        const overlap = 0.08; 
        nextPlaybackTimeRef.current = startTime + Math.max(0, audioBuffer.duration - overlap);

        return new Promise<void>((resolve) => {
          source.onended = () => {
            activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
            if (isLast && !stopRequestedRef.current) {
              console.log(`Sending playback done for chunk: ${chunkId}`);
              sendPlaybackDone(chunkId);
            }
            resolve();
          };
        });
      } catch (err) {
        console.error("Audio playback error", err);
      }
    });
  };

  const sendPlaybackDone = (chunkId: string) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
    socketRef.current.send(
      JSON.stringify({
        type: 'examiner.audio.playback_done',
        session_id: sessionId || undefined,
        payload: { chunk_id: chunkId },
      })
    );
  };

  const cancelTest = () => {
    stopAllPlayback();
    stopMicCapture();
    setStartingSession(false);
    setTestState('idle');
    setSessionStarted(false);
    setTimerPhase('idle');
    if (socketRef.current) {
      if (socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ type: 'session.stop', session_id: sessionId || undefined, payload: {} }));
      }
      socketRef.current.close();
    }
  };

  useEffect(() => {
    if (!sessionStarted || testState === 'finished') return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        const confirmCancel = window.confirm("Are you sure? Your test will be canceled if you switch tabs or minimize.");
        if (confirmCancel) {
          cancelTest();
        }
      }
    };

    const handleBlur = () => {
      const confirmCancel = window.confirm("Are you sure? Your test will be canceled if you leave the window.");
      if (confirmCancel) {
        cancelTest();
      }
    };
    
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
      return '';
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("blur", handleBlur);
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("blur", handleBlur);
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [sessionStarted, testState, sessionId]);

  const queueAudioPlaybackChunk = (chunkId: string, seq: number, isLast: boolean, audioBase64: string) => {
    console.log(`Received audio chunk: id=${chunkId}, seq=${seq}, isLast=${isLast}, base64Len=${audioBase64.length}`);
    if (activeAudioChunkIdRef.current !== chunkId) {
      activeAudioChunkIdRef.current = chunkId;
      expectedAudioSeqRef.current = 0;
      audioChunkBufferRef.current.clear();
    }

    audioChunkBufferRef.current.set(seq, { audioBase64, isLast });
    while (audioChunkBufferRef.current.has(expectedAudioSeqRef.current)) {
      const expectedSeq = expectedAudioSeqRef.current;
      const item = audioChunkBufferRef.current.get(expectedSeq);
      if (!item) break;
      console.log(`Processing expected sequence: ${expectedSeq}`);
      audioChunkBufferRef.current.delete(expectedSeq);
      
      if (item.audioBase64) {
          queueAudioPlayback(item.audioBase64, item.isLast, chunkId);
      } else if (item.isLast) {
        // If there's no audio but it's the last chunk (e.g., empty buffer), just schedule the done signal
        playbackQueueRef.current = playbackQueueRef.current.then(async () => {
          if (!stopRequestedRef.current) {
            console.log(`Sending playback done for chunk: ${chunkId}`);
            sendPlaybackDone(chunkId);
          }
        });
      }
      
      expectedAudioSeqRef.current += 1;
    }
  };

  const sendAudioChunk = (pcmBuffer: ArrayBuffer, forceTranscribe = false) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
    // We send audio continuously. The backend determines state.
    if (isPart2Active && prepSecondsLeft > 0 && !forceTranscribe) return;
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
    resetUtteranceTracking();
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
    activeAudioChunkIdRef.current = null;
    expectedAudioSeqRef.current = 0;
    audioChunkBufferRef.current.clear();
    
    activeSourcesRef.current.forEach((source) => {
      try {
        source.stop();
        source.disconnect();
      } catch {
        // noop
      }
    });
    activeSourcesRef.current = [];
    nextPlaybackTimeRef.current = 0;

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
    setStartingSession(true);
    try {
      stopRequestedRef.current = false;
      setFirstExaminerAudioReceived(false);
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
        // Stream always, even when examiner speaking, to allow barge-in.
        if (turnStateRef.current === 'finished') {
          return;
        }

        const channel = event.inputBuffer.getChannelData(0);
        const pcm = float32ToPcm16(channel);
        const rms = Math.sqrt(channel.reduce((acc, v) => acc + v * v, 0) / Math.max(1, channel.length));
        const durationMs = (channel.length / Math.max(1, sampleRateRef.current)) * 1000;
        // Always stream audio chunks to backend for real-time endpointing and barge-in.
        sendAudioChunk(pcm, false);
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
      setStartingSession(false);
    }
  };

  const requestFinalReport = () => {
    stopAllPlayback();
    sendAudioChunk(new Uint8Array(640).buffer, true);
    stopMicCapture();
    setStartingSession(false);
    setEvaluationStatus('processing');
    setTestState('processing');
    socketRef.current?.send(JSON.stringify({ type: 'session.stop', session_id: sessionId || undefined, payload: {} }));
  };

  const waitingForExaminer = sessionStarted && testState !== 'finished' && messages.filter(m => m.role === 'examiner').length === 0;
  const waitingForFirstExaminerAudio = sessionStarted && !firstExaminerAudioReceived && turnState === 'examiner_speaking';

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 max-w-4xl relative">
        <div className="absolute w-64 h-64 bg-primary/8 rounded-full blur-3xl top-10 left-1/2 -translate-x-1/2 pointer-events-none animate-float" />

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="text-center relative z-10">
          <h1 className="text-2xl font-bold text-foreground mb-2">Speaking Test - Part {part}</h1>

          {error && <p className="text-destructive mb-4">{error}</p>}

          {testState !== 'finished' && (
            <div className="space-y-4 mt-10">
              {isPart2Active && timerPhase === 'prep' && (
                <div className="my-6">
                  <CountdownRing
                    label="Prep Time"
                    sublabel="Prepare your speech — it will start automatically"
                    total={60}
                    left={prepSecondsLeft}
                    colorClass="text-primary"
                    ringClass="stroke-primary"
                  />
                  <div className="mt-6 flex justify-center">
                    <Button onClick={() => {
                      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN || socketRef.current?.readyState === 1) {
                        socketRef.current.send(JSON.stringify({ type: 'timer.skip_prep', session_id: sessionId || undefined }));
                      }
                    }} className="gap-2 h-11 glow-sm">
                      <Mic className="h-4 w-4" /> Skip Prep & Start Speaking
                    </Button>
                  </div>
                </div>
              )}

              {isPart2Active && timerPhase === 'speaking' && (
                <div className="my-6">
                  <CountdownRing
                    label="Speech Time"
                    sublabel="Speak until time runs out"
                    total={120}
                    left={speakingSecondsLeft}
                    colorClass="text-destructive"
                    ringClass="stroke-destructive"
                  />
                  <div className="mt-6 flex justify-center">
                    <Button variant="destructive" onClick={() => {
                      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN || socketRef.current?.readyState === 1) {
                        socketRef.current.send(JSON.stringify({ type: 'timer.stop_speaking', session_id: sessionId || undefined }));
                      }
                    }} className="gap-2 h-11 glow-sm">
                      <Square className="h-4 w-4" /> Stop Speaking
                    </Button>
                  </div>
                </div>
              )}

              <Card className="glass-card flex flex-col h-[70vh] min-h-[600px]">
                <div className="p-4 border-b border-border/50 bg-background/50 flex flex-col sm:flex-row justify-between items-center gap-4 rounded-t-lg">
                  <div className="flex items-center gap-4">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Turn: {turnStatusText}</p>
                    <div className="font-mono text-sm font-bold text-foreground">{formatTime(seconds)}</div>
                  </div>
                  <div className="flex items-center justify-center gap-3">
                    {!sessionStarted && (
                      <Button onClick={startRecording} className="gap-2 h-9 glow-sm" disabled={startingSession}>
                        {startingSession ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
                        {startingSession ? 'Preparing...' : 'Start Test'}
                      </Button>
                    )}
                    {sessionStarted && (
                      <Button variant="destructive" onClick={() => {
                          if (window.confirm("Are you sure? Your test will be canceled.")) {
                              cancelTest();
                          }
                      }} className="h-9">
                        Cancel Test
                      </Button>
                    )}
                    <Button variant="outline" onClick={requestFinalReport} disabled={!sessionStarted} className="h-9">
                      Finish
                    </Button>
                  </div>
                </div>
                <CardContent className="flex-1 overflow-y-auto p-6 flex flex-col gap-4 relative scroll-smooth">
                  <div ref={messagesTopRef} className="h-1 shrink-0" />
                  
                  {turnState === 'candidate_speaking' && (
                    <div className="flex w-full justify-end">
                      <div className="max-w-[80%] rounded-2xl px-4 py-3 text-sm bg-primary/20 text-foreground rounded-tr-sm animate-pulse">
                        <p className="text-xs opacity-70 mb-1 font-semibold uppercase">You</p>
                        <p className="flex gap-1 items-center">
                          <span className="h-1.5 w-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                          <span className="h-1.5 w-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                          <span className="h-1.5 w-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                        </p>
                      </div>
                    </div>
                  )}

                  {[...messages].reverse().map((msg) => (
                    <div key={msg.id} className={`flex w-full ${msg.role === 'candidate' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${msg.role === 'candidate' ? 'bg-primary text-primary-foreground rounded-tr-sm' : msg.isCueCard ? 'bg-primary/20 border border-primary/30 text-foreground rounded-tl-sm' : 'bg-muted text-foreground rounded-tl-sm'}`}>
                        <p className="text-xs opacity-70 mb-1 font-semibold uppercase">
                          {msg.role === 'candidate' ? 'You' : msg.isCueCard ? 'Examiner (Task Card)' : 'Examiner'}
                        </p>
                        <CollapsibleMessage text={msg.text} />
                      </div>
                    </div>
                  ))}

                  {(waitingForExaminer || waitingForFirstExaminerAudio) && (
                    <div className="flex items-center justify-center gap-2 text-sm text-primary py-4">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Examiner is preparing the first question and audio...
                    </div>
                  )}
                  {startingSession && (
                    <div className="flex items-center justify-center gap-2 text-sm text-primary py-4">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Connecting and preparing examiner voice...
                    </div>
                  )}
                  {!sessionStarted && !startingSession && (
                    <div className="text-center text-muted-foreground py-10 flex items-center justify-center">
                      <p>Start recording to begin the speaking interaction.</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {testState === 'processing' && (
                <p className="text-sm text-primary flex items-center justify-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Preparing your speaking evaluation...
                </p>
              )}
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

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="bg-card">
                  <CardContent className="py-4 flex flex-col items-center justify-center space-y-2">
                    <p className="text-sm font-medium text-muted-foreground">Fluency & Coherence</p>
                    <p className="text-3xl font-bold text-primary">{Number(report?.scores?.fc || 0).toFixed(1)}</p>
                  </CardContent>
                </Card>
                <Card className="bg-card">
                  <CardContent className="py-4 flex flex-col items-center justify-center space-y-2">
                    <p className="text-sm font-medium text-muted-foreground">Lexical Resource</p>
                    <p className="text-3xl font-bold text-primary">{Number(report?.scores?.lr || 0).toFixed(1)}</p>
                  </CardContent>
                </Card>
                <Card className="bg-card">
                  <CardContent className="py-4 flex flex-col items-center justify-center space-y-2">
                    <p className="text-sm font-medium text-muted-foreground">Grammatical Range & Accuracy</p>
                    <p className="text-3xl font-bold text-primary">{Number(report?.scores?.gra || 0).toFixed(1)}</p>
                  </CardContent>
                </Card>
              </div>

              {evaluationStatus === 'processing' && (
                <p className="text-sm text-primary flex items-center justify-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Detailed feedback is being generated in the background...
                </p>
              )}

              {report?.examiner_comments && (
                <Card>
                  <CardContent className="py-5 space-y-3">
                    <h3 className="font-semibold text-lg flex items-center gap-2">
                       <CheckCircle2 className="h-5 w-5 text-primary" />
                       Examiner Feedback
                    </h3>
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
                      {report.examiner_comments}
                    </p>
                  </CardContent>
                </Card>
              )}

              {report?.transcript && (
                <Card>
                  <CardContent className="py-5 space-y-4">
                     <h3 className="font-semibold text-lg">Test Transcript</h3>
                     <div className="space-y-4 mt-4">
                       {String(report.transcript).split('\n').filter(line => line.trim()).map((line, idx) => {
                         const isUser = line.toLowerCase().startsWith('user:');
                         const content = line.replace(/^(user|assistant):\s*/i, '');
                         return (
                           <div key={idx} className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
                             <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${isUser ? 'bg-primary text-primary-foreground rounded-tr-sm' : 'bg-muted text-foreground rounded-tl-sm'}`}>
                               <p className="text-xs opacity-70 mb-1 font-semibold uppercase">{isUser ? 'You' : 'Examiner'}</p>
                               <p className="whitespace-pre-wrap leading-relaxed">{content}</p>
                             </div>
                           </div>
                         );
                       })}
                     </div>
                  </CardContent>
                </Card>
              )}

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

const CountdownRing = ({
  label,
  sublabel,
  total,
  left,
  colorClass,
  ringClass,
}: {
  label: string;
  sublabel: string;
  total: number;
  left: number;
  colorClass: string;
  ringClass: string;
}) => {
  const radius = 78;
  const circumference = 2 * Math.PI * radius;
  const progress = left / total;
  const dashOffset = circumference * (1 - progress);
  const mins = Math.floor(left / 60);
  const secs = (left % 60).toString().padStart(2, '0');
  const urgent = left <= 10 && left > 0;

  return (
    <div className="flex flex-col items-center">
      <p className={`text-xs font-bold uppercase tracking-[0.2em] ${colorClass} mb-3`}>{label}</p>
      <div className="relative inline-flex items-center justify-center">
        <motion.div
          animate={urgent ? { scale: [1, 1.05, 1] } : { scale: 1 }}
          transition={{ repeat: Infinity, duration: 0.8 }}
          className="relative"
        >
          <svg width="200" height="200" className="-rotate-90">
            <circle
              cx="100"
              cy="100"
              r={radius}
              strokeWidth="8"
              fill="none"
              className="stroke-muted"
            />
            <motion.circle
              cx="100"
              cy="100"
              r={radius}
              strokeWidth="8"
              fill="none"
              strokeLinecap="round"
              className={ringClass}
              strokeDasharray={circumference}
              animate={{ strokeDashoffset: dashOffset }}
              transition={{ duration: 1, ease: 'linear' }}
              style={{ filter: urgent ? 'drop-shadow(0 0 8px currentColor)' : undefined }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <motion.span
              key={left}
              initial={{ scale: 1.15, opacity: 0.6 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.3 }}
              className={`font-mono text-5xl font-bold ${urgent ? 'text-destructive' : 'text-foreground'}`}
            >
              {mins}:{secs}
            </motion.span>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
              {urgent ? 'Hurry up!' : 'remaining'}
            </span>
          </div>
        </motion.div>
        {/* Pulse rings */}
        <span className={`absolute w-[200px] h-[200px] rounded-full ${urgent ? 'bg-destructive/10' : 'bg-primary/5'} animate-pulse-ring pointer-events-none`} />
      </div>
      <p className="text-sm text-muted-foreground mt-3">{sublabel}</p>
    </div>
  );
};

export default SpeakingTest;
