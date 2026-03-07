// hooks/useAgentTurn.js
import { useCallback } from "react";
import { sendVoiceTurn } from "../services/voiceApi";

/**
 * Single-call hook to hit /voice-turn with the English transcript.
 * No polling — response is synchronous from backend.
 */
export function useAgentTurn({ onResult, onError }) {
  const callAgent = useCallback(
    async (transcriptEnglish, sessionId = null, detectedLanguageCode = null) => {
      try {
        const data = await sendVoiceTurn(transcriptEnglish, sessionId, detectedLanguageCode);
        onResult(data);
      } catch (err) {
        onError(err);
      }
    },
    [onResult, onError]
  );

  return { callAgent };
}
