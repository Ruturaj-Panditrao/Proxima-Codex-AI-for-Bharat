import { useState, useRef, useCallback } from "react";

/**
 * Plays audio from a URL/Blob (real) or falls back to speechSynthesis (dummy).
 * Swap `playDummy` → `playFromUrl` once backend sends audio.
 */
export function useAudioPlayer() {
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef(null);
  const utteranceRef = useRef(null);

  // ─── DUMMY: Browser Text-to-Speech ───────────────────────────────────────
  const playDummy = useCallback((text, languageCode = "en-US") => {
    if (window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
      setIsPlaying(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = languageCode;
    utterance.rate = 0.95;
    utterance.onstart = () => setIsPlaying(true);
    utterance.onend = () => setIsPlaying(false);
    utterance.onerror = () => setIsPlaying(false);

    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }, []);

  // ─── REAL: Play audio from URL or Blob (use this once backend is ready) ──
  const playFromUrl = useCallback((audioUrlOrBlob) => {
    if (audioRef.current) {
      if (!audioRef.current.paused) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
        setIsPlaying(false);
        return;
      }
      audioRef.current.src =
        audioUrlOrBlob instanceof Blob
          ? URL.createObjectURL(audioUrlOrBlob)
          : audioUrlOrBlob;
    } else {
      const audio = new Audio(
        audioUrlOrBlob instanceof Blob
          ? URL.createObjectURL(audioUrlOrBlob)
          : audioUrlOrBlob
      );
      audio.onplay = () => setIsPlaying(true);
      audio.onended = () => setIsPlaying(false);
      audio.onerror = () => setIsPlaying(false);
      audioRef.current = audio;
      console.log("Audio initialized:", audio);
    }
    audioRef.current.play();
  }, []);

  const stop = useCallback(() => {
    window.speechSynthesis.cancel();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setIsPlaying(false);
  }, []);

  return { isPlaying, playDummy, playFromUrl, stop };
}
