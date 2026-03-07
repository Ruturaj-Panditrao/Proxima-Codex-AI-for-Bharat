import { useState, useEffect, useRef } from "react";
import { useCallback } from "react";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useAgentTurn } from "../hooks/useAgentTurn";
import { uploadAudio } from "../services/voiceApi";
import { useAudioPlayer } from "../hooks/useAudioPlayer";
import { fetchTTSAudio } from "../services/voiceApi";

const steps = [
  { icon: "🎙️", label: "Speak", desc: "Talk in your language" },
  { icon: "🔍", label: "Detect", desc: "Language identified" },
  { icon: "🌐", label: "Translate", desc: "Converted to English" },
  { icon: "📋", label: "Match", desc: "Schemes fetched" },
  { icon: "🔄", label: "Deliver", desc: "Info in your language" },
];

const langs = [
  "हिंदी",
  "தமிழ்",
  "বাংলা",
  "తెలుగు",
  "മലയാളം",
  "ਪੰਜਾਬੀ",
  "English",
  "मराठी",
];

export default function VoiceApp() {
  const [listening, setListening] = useState(false);
  const [currentLang, setCurrentLang] = useState(0);
  const [ripples, setRipples] = useState([]);
  const [dots, setDots] = useState("");
  const rippleId = useRef(0);

  const [sessionId, setSessionId] = useState(null);
  const [agentReply, setAgentReply] = useState("");
  const [followupQuestion, setFollowupQuestion] = useState(null);
  const [referencedSchemes, setReferencedSchemes] = useState([]);

  const [detectedLanguage, setDetectedLanguage] = useState("");
  const [transcriptHindi, setTranscriptHindi] = useState("");
  const [transcriptEnglish, setTranscriptEnglish] = useState("");

  const [phase, setPhase] = useState("idle"); // idle | recording | processing | polling | done | error
  const [transcript, setTranscript] = useState("");
  const [finalResponse, setFinalResponse] = useState("");
  const [queryId, setQueryId] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [audioUrl, setAudioUrl] = useState(null);
  // Inside your component:
  const { isPlaying, playDummy, playFromUrl, stop } = useAudioPlayer();

  const { isRecording, audioBlob, startRecording, stopRecording } =
    useAudioRecorder();

  const { callAgent } = useAgentTurn({
    onResult: async (data) => {
      // persist for next turn
      setAgentReply(data.answer);

      setPhase("done");

      try {
        const url = await fetchTTSAudio(data.answer, (transcriptHindi!=null)?"hi-IN":"en-US");
        console.log("Prefetched TTS audio URL:", url);
        setAudioUrl(url);
      } catch (err) {
        console.warn("TTS prefetch failed:", err.message);
      }
    },
    onError: (err) => {
      setErrorMsg(err.message);
      setPhase("error");
    },
  });

  useEffect(() => {
    console.log(phase);
  }, [phase]);
  // Triggered when recording stops and blob is ready
  const handleUpload = useCallback(async (blob) => {
    setPhase("processing");
    try {
      const data = await uploadAudio(blob, {
        languageCode: null,
        detectMultipleLanguages: true,
        waitForResult: true,
      });

      // Map backend response fields to state
      setTranscript(data.transcript_text);
      setDetectedLanguage(data.detected_language_code); // e.g. "hi-IN"
      setTranscriptHindi(data.transcript_hindi);
      setTranscriptEnglish(data.transcript_english);

      const queryId = data.lambda_result?.query_id; // ← adjust key to match lambda_result shape
      // if (!queryId) throw new Error("No query ID returned from backend.");

      setQueryId(queryId);

      await callAgent(
        data.transcript_hindi != null
          ? data.transcript_hindi
          : data.transcript_english,
        sessionId,
        data.detected_language_code,
      );
    } catch (err) {
      setErrorMsg(err.message);
      setPhase("error");
    }
  }, []);

  // Respond to audioBlob becoming available after stopRecording()
  useEffect(() => {
    if (audioBlob) handleUpload(audioBlob);
  }, [audioBlob, handleUpload]);

  // const handleMic = () => {
  //   if (phase === "processing") return;
  //   if (!listening) {
  //     setListening(true);
  //     setPhase("listening");
  //     setTranscript("");
  //   } else {
  //     setListening(false);
  //     setPhase("processing");
  //     setTranscript("मुझे प्रधानमंत्री आवास योजना के बारे में जानकारी चाहिए...");
  //   }
  // };

  const handleMic = () => {
    if (isRecording) {
      setListening(false);
      setPhase("processing");
      stopRecording(); // triggers audioBlob → handleUpload
    } else {
      setPhase("listening");
      setTranscript("");
      setFinalResponse("");
      setErrorMsg("");
      startRecording();
    }
  };

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentLang((p) => (p + 1) % langs.length);
    }, 1800);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (phase === "processing") {
      let count = 0;
      const t = setInterval(() => {
        count++;
        setDots(".".repeat((count % 3) + 1));
        // if (count > 15) {
        //   clearInterval(t);
        //   // setPhase("done");
        // }
      }, 300);
      return () => clearInterval(t);
    }
  }, [phase]);

  useEffect(() => {
    if (isRecording) {
      const interval = setInterval(() => {
        const id = rippleId.current++;
        setRipples((r) => [...r, id]);
        setTimeout(() => setRipples((r) => r.filter((x) => x !== id)), 1800);
      }, 600);
      return () => clearInterval(interval);
    }
  }, [isRecording]);

  const handlePlayAudio = () => {
    // TODO: replace playDummy with playFromUrl(audioUrl) once backend ready
    if (audioUrl) {
      playFromUrl(audioUrl); // ← real Polly audio
    } else {
      playDummy(agentReply, detectedLanguage || "en-US"); // ← fallback
    }
  };

  const reset = () => {
    stop();
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(null);
    setPhase("idle");
    setListening(false);
    setTranscript("");
    setAgentReply("");
    setTranscriptHindi("");
    setTranscriptEnglish("");
  };

  return (
    <div style={styles.root}>
      {/* Noise texture overlay */}
      <div style={styles.noise} />

      {/* Floating orbs */}
      <div style={{ ...styles.orb, ...styles.orb1 }} />
      <div style={{ ...styles.orb, ...styles.orb2 }} />
      <div style={{ ...styles.orb, ...styles.orb3 }} />

      {/* Header */}
      <header style={styles.header}>
        <div style={styles.badge}>
          <span style={styles.badgeDot} />
          <span style={styles.badgeText}>Beta · Multilingual</span>
        </div>
        <div style={styles.langPill}>
          <span style={styles.langIcon}>🌏</span>
          <span style={styles.langText}>{langs[currentLang]}</span>
        </div>
      </header>

      {/* Hero */}
      <main style={styles.main}>
        <div style={styles.tagline}>
          <span style={styles.taglineAccent}>सरकारी योजनाएं</span>
          <span style={styles.taglineSub}> · Government Schemes</span>
        </div>

        <h1 style={styles.headline}>
          Speak Your
          <br />
          <em style={styles.headlineEm}>Language.</em>
        </h1>

        <p style={styles.subtext}>
          Ask about any government scheme in{" "}
          <strong>your native language</strong>. Our AI detects, translates,
          fetches, and delivers answers — instantly.
        </p>

        {/* Steps */}
        <div style={styles.steps}>
          {steps.map((s, i) => (
            <div key={i} style={styles.step}>
              <div style={styles.stepIcon}>{s.icon}</div>
              <div style={styles.stepLabel}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Mic Section */}
        <div style={styles.micSection}>
          {/* Ripples */}
          <div style={styles.rippleContainer}>
            {ripples.map((id) => (
              <div key={id} style={styles.ripple} />
            ))}
          </div>

          {/* Mic Button */}
          <button
            style={{
              ...styles.micBtn,
              ...(isRecording ? styles.micBtnActive : {}),
              ...(phase === "processing" ? styles.micBtnProcessing : {}),
            }}
            onClick={handleMic}
            aria-label="Start recording"
          >
            <div style={styles.micInner}>
              {phase === "processing" ? (
                <svg
                  width="40"
                  height="40"
                  viewBox="0 0 40 40"
                  style={styles.spinner}
                >
                  <circle
                    cx="20"
                    cy="20"
                    r="16"
                    fill="none"
                    stroke="rgba(255,255,255,0.2)"
                    strokeWidth="3"
                  />
                  <circle
                    cx="20"
                    cy="20"
                    r="16"
                    fill="none"
                    stroke="white"
                    strokeWidth="3"
                    strokeDasharray="30 70"
                    strokeLinecap="round"
                  />
                </svg>
              ) : (
                <svg width="40" height="40" viewBox="0 0 24 24" fill="white">
                  {isRecording ? (
                    /* Stop icon */
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  ) : (
                    /* Mic icon */
                    <>
                      <rect x="9" y="2" width="6" height="11" rx="3" />
                      <path
                        d="M5 10a7 7 0 0 0 14 0"
                        stroke="white"
                        strokeWidth="2"
                        fill="none"
                        strokeLinecap="round"
                      />
                      <line
                        x1="12"
                        y1="17"
                        x2="12"
                        y2="21"
                        stroke="white"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                      <line
                        x1="8"
                        y1="21"
                        x2="16"
                        y2="21"
                        stroke="white"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </>
                  )}
                </svg>
              )}
            </div>
          </button>

          {/* Status */}
          <div style={styles.statusArea}>
            {phase === "idle" && (
              <p style={styles.statusHint}>
                Tap the mic and speak your question
              </p>
            )}
            {phase === "listening" && (
              <div style={styles.statusLive}>
                <span style={styles.liveDot} />
                <span>Listening… speak now</span>
              </div>
            )}
            {phase === "processing" && (
              <p style={styles.statusProcessing}>Processing{dots}</p>
            )}
            {phase === "done" && (
              <div style={styles.resultCard}>
                <div style={styles.resultHeader}>
                  <span style={styles.resultCheck}>✓</span>
                  <span>
                    Detected: <strong>{detectedLanguage || "Unknown"}</strong> ·
                    Response ready
                  </span>
                </div>

                {/* Original transcript in input language */}
                <p style={styles.resultTranscript}>
                  {transcriptHindi !== "" ? transcriptHindi : transcriptEnglish}
                </p>

                {/* Agent reply with audio button */}
                <div style={styles.agentReply}>
                  <div style={styles.agentReplyHeader}>
                    <span style={styles.agentLabel}>🤖 Agent Response</span>
                    <button
                      style={{
                        ...styles.audioBtn,
                        ...(isPlaying ? styles.audioBtnActive : {}),
                      }}
                      onClick={handlePlayAudio}
                      title={isPlaying ? "Stop audio" : "Play response"}
                    >
                      {isPlaying ? "⏹ Stop" : "🔊 Play"}
                    </button>
                  </div>
                  <p>{agentReply}</p>
                </div>

                {/* Follow-up question */}
                {followupQuestion && (
                  <div style={styles.followupBox}>
                    <span style={styles.followupIcon}>💬</span>
                    <p>{followupQuestion}</p>
                  </div>
                )}

                {/* Referenced schemes */}
                {referencedSchemes.length > 0 && (
                  <div style={styles.resultInfo}>
                    {referencedSchemes.map((scheme, index) => (
                      <div key={index} style={styles.schemeTag}>
                        📋 {scheme?.name ?? scheme}
                      </div>
                    ))}
                  </div>
                )}

                <button
                  style={styles.resetBtn}
                  onClick={() => {
                    stop();
                    reset();
                  }}
                >
                  ↺ Ask Another
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Supported languages */}
        <div style={styles.langsRow}>
          <span style={styles.langsLabel}>Supported:</span>
          {langs.slice(0, 6).map((l, i) => (
            <span key={i} style={styles.langChip}>
              {l}
            </span>
          ))}
          <span style={styles.langChip}>+12 more</span>
        </div>
      </main>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&family=Noto+Serif+Devanagari:wght@600&display=swap');

        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes rippleOut {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(3.5); opacity: 0; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        @keyframes float1 {
          0%, 100% { transform: translateY(0px) translateX(0px); }
          33% { transform: translateY(-30px) translateX(15px); }
          66% { transform: translateY(15px) translateX(-10px); }
        }
        @keyframes float2 {
          0%, 100% { transform: translateY(0px) translateX(0px); }
          50% { transform: translateY(25px) translateX(-20px); }
        }
        @keyframes langSlide {
          0%, 100% { opacity: 1; transform: translateY(0); }
          45% { opacity: 0; transform: translateY(-8px); }
          55% { opacity: 0; transform: translateY(8px); }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

const styles = {
  agentReplyHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "8px",
  },
  agentLabel: {
    fontSize: "12px",
    fontWeight: "600",
    color: "#2563eb",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
  },
  audioBtn: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    padding: "5px 12px",
    fontSize: "13px",
    fontWeight: "500",
    border: "1px solid #2563eb",
    borderRadius: "20px",
    backgroundColor: "white",
    color: "#2563eb",
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  audioBtnActive: {
    backgroundColor: "#2563eb",
    color: "white",
  },

  agentReply: {
    backgroundColor: "#f0f7ff",
    borderLeft: "3px solid #2563eb",
    borderRadius: "8px",
    padding: "12px 16px",
    margin: "12px 0",
    fontSize: "15px",
    lineHeight: "1.6",
    color: "#1e293b",
  },
  followupBox: {
    display: "flex",
    alignItems: "flex-start",
    gap: "8px",
    backgroundColor: "#fffbeb",
    borderRadius: "8px",
    padding: "10px 14px",
    margin: "8px 0",
    fontSize: "14px",
    color: "#92400e",
  },
  followupIcon: {
    fontSize: "16px",
    marginTop: "2px",
  },

  root: {
    minHeight: "100vh",
    background: "#0a0e1a",
    fontFamily: "'Sora', sans-serif",
    color: "#e8eaf0",
    position: "relative",
    overflow: "hidden",
    display: "flex",
    width: "100vw",
    flexDirection: "column",
    alignItems: "center",
    boxSizing: "border-box",
  },
  noise: {
    position: "fixed",
    inset: 0,
    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E")`,
    pointerEvents: "none",
    zIndex: 0,
  },
  orb: {
    position: "fixed",
    borderRadius: "50%",
    filter: "blur(80px)",
    pointerEvents: "none",
    zIndex: 0,
  },
  orb1: {
    width: 400,
    height: 400,
    background:
      "radial-gradient(circle, rgba(99,102,241,0.25) 0%, transparent 70%)",
    top: -100,
    left: -100,
    animation: "float1 12s ease-in-out infinite",
  },
  orb2: {
    width: 350,
    height: 350,
    background:
      "radial-gradient(circle, rgba(236,72,153,0.18) 0%, transparent 70%)",
    bottom: -80,
    right: -80,
    animation: "float2 15s ease-in-out infinite",
  },
  orb3: {
    width: 250,
    height: 250,
    background:
      "radial-gradient(circle, rgba(34,211,238,0.12) 0%, transparent 70%)",
    top: "40%",
    right: "15%",
    animation: "float1 10s ease-in-out infinite reverse",
  },
  header: {
    position: "relative",
    zIndex: 2,
    width: "100%",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "24px 32px",
  },
  badge: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 100,
    padding: "6px 14px",
  },
  badgeDot: {
    width: 7,
    height: 7,
    borderRadius: "50%",
    background: "#4ade80",
    animation: "pulse 2s infinite",
    display: "block",
  },
  badgeText: {
    fontSize: 12,
    color: "rgba(255,255,255,0.6)",
    letterSpacing: "0.05em",
    textTransform: "uppercase",
  },
  langPill: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "rgba(99,102,241,0.15)",
    border: "1px solid rgba(99,102,241,0.3)",
    borderRadius: 100,
    padding: "6px 16px",
    minWidth: 120,
    justifyContent: "center",
  },
  langIcon: { fontSize: 16 },
  langText: {
    fontSize: 14,
    fontWeight: 600,
    color: "#a5b4fc",
    animation: "langSlide 1.8s ease-in-out infinite",
    display: "inline-block",
    minWidth: 70,
    textAlign: "center",
  },
  main: {
    position: "relative",
    zIndex: 2,
    width: "100%",
    padding: "20px 32px 60px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    textAlign: "center",
  },
  tagline: {
    fontSize: 13,
    letterSpacing: "0.15em",
    textTransform: "uppercase",
    marginBottom: 16,
    color: "rgba(255,255,255,0.4)",
  },
  taglineAccent: {
    color: "#f97316",
    fontFamily: "'Noto Serif Devanagari', serif",
  },
  taglineSub: { color: "rgba(255,255,255,0.35)" },
  headline: {
    fontSize: "clamp(42px, 8vw, 72px)",
    fontWeight: 700,
    lineHeight: 1.05,
    letterSpacing: "-0.03em",
    margin: "0 0 20px",
    color: "#f1f5f9",
  },
  headlineEm: {
    fontStyle: "italic",
    background: "linear-gradient(135deg, #6366f1, #ec4899, #f97316)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
  },
  subtext: {
    fontSize: 16,
    lineHeight: 1.7,
    color: "rgba(255,255,255,0.5)",
    // maxWidth: 480,
    marginBottom: 40,
  },
  steps: {
    display: "flex",
    gap: 8,
    marginBottom: 52,
    flexWrap: "wrap",
    justifyContent: "center",
  },
  step: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 100,
    padding: "8px 16px",
    fontSize: 13,
    color: "rgba(255,255,255,0.6)",
  },
  stepIcon: { fontSize: 16 },
  stepLabel: { fontWeight: 600 },
  micSection: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 32,
    width: "100%",
    marginBottom: 40,
  },
  rippleContainer: {
    position: "absolute",
    width: 120,
    height: 120,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    pointerEvents: "none",
  },
  ripple: {
    position: "absolute",
    width: 120,
    height: 120,
    borderRadius: "50%",
    border: "2px solid rgba(99,102,241,0.5)",
    animation: "rippleOut 1.8s ease-out forwards",
  },
  micBtn: {
    position: "relative",
    width: 100,
    height: 100,
    borderRadius: "50%",
    border: "none",
    background: "linear-gradient(135deg, #4f46e5, #7c3aed)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 0 40px rgba(99,102,241,0.4), 0 8px 32px rgba(0,0,0,0.4)",
    transition: "all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",
    zIndex: 2,
  },
  micBtnActive: {
    background: "linear-gradient(135deg, #dc2626, #ec4899)",
    boxShadow: "0 0 60px rgba(220,38,38,0.5), 0 8px 32px rgba(0,0,0,0.4)",
    transform: "scale(1.1)",
  },
  micBtnProcessing: {
    background: "linear-gradient(135deg, #0ea5e9, #6366f1)",
    cursor: "not-allowed",
  },
  micInner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  spinner: {
    animation: "spin 1s linear infinite",
  },
  statusArea: {
    minHeight: 80,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
  },
  statusHint: {
    color: "rgba(255,255,255,0.3)",
    fontSize: 15,
    letterSpacing: "0.02em",
  },
  statusLive: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    color: "#f87171",
    fontSize: 16,
    fontWeight: 500,
  },
  liveDot: {
    width: 10,
    height: 10,
    borderRadius: "50%",
    background: "#f87171",
    animation: "pulse 1s infinite",
    display: "block",
  },
  statusProcessing: {
    color: "#7dd3fc",
    fontSize: 16,
    fontWeight: 500,
    letterSpacing: "0.05em",
  },
  resultCard: {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 20,
    padding: "24px 28px",
    width: "100%",
    textAlign: "left",
    animation: "fadeIn 0.5s ease",
  },
  resultHeader: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: 12,
    color: "#4ade80",
    fontSize: 14,
    fontWeight: 600,
  },
  resultCheck: {
    background: "rgba(74,222,128,0.15)",
    borderRadius: "50%",
    width: 24,
    height: 24,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
  },
  resultTranscript: {
    fontSize: 15,
    color: "rgba(255,255,255,0.6)",
    fontStyle: "italic",
    marginBottom: 16,
    lineHeight: 1.6,
  },
  resultInfo: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    marginBottom: 20,
  },
  schemeTag: {
    background: "rgba(99,102,241,0.15)",
    border: "1px solid rgba(99,102,241,0.3)",
    borderRadius: 8,
    padding: "6px 12px",
    fontSize: 13,
    color: "#a5b4fc",
  },
  resetBtn: {
    background: "rgba(255,255,255,0.08)",
    border: "1px solid rgba(255,255,255,0.15)",
    borderRadius: 10,
    padding: "10px 20px",
    color: "white",
    fontSize: 14,
    cursor: "pointer",
    fontFamily: "'Sora', sans-serif",
    fontWeight: 500,
    transition: "background 0.2s",
  },
  langsRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
    justifyContent: "center",
  },
  langsLabel: {
    fontSize: 12,
    color: "rgba(255,255,255,0.3)",
    textTransform: "uppercase",
    letterSpacing: "0.1em",
    marginRight: 4,
  },
  langChip: {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 100,
    padding: "4px 12px",
    fontSize: 12,
    color: "rgba(255,255,255,0.4)",
  },
};
