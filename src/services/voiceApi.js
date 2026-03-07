const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * Upload audio for transcription.
 *
 * @param {Blob}        audioBlob
 * @param {Object}      options
 * @param {string|null} options.languageCode            - e.g. "hi-IN", null to auto-detect
 * @param {boolean}     options.detectMultipleLanguages - default true
 * @param {boolean}     options.waitForResult           - default true
 *
 * @returns {{ queryId: string, transcript: string }}
 */
export async function uploadAudio(audioBlob, options = {}) {
  const {
    languageCode = null,
    detectMultipleLanguages = true,
    waitForResult = true,
  } = options;

  const formData = new FormData();
  formData.append("file", audioBlob, "recording.webm");

  // Only append language_code if explicitly provided — backend expects null/absent for auto-detect
  if (languageCode !== null) {
    formData.append("language_code", languageCode);
  }

  formData.append("detect_multiple_languages", String(detectMultipleLanguages));
  formData.append("wait_for_result", String(waitForResult));

  const res = await fetch(`${BASE_URL}/api/voice/transcribe`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Transcription upload failed [${res.status}]: ${err}`);
  }

  return res.json(); // { queryId, transcript }
}

/**
 * Send transcribed English text to the agent for a response.
 *
 * @param {string}      userText            - transcript_english from transcribe step
 * @param {string|null} sessionId           - pass existing session ID to maintain conversation context
 * @param {string|null} detectedLanguageCode
 *
 * @returns {AgentTurnResponse}
 */
export async function sendVoiceTurn(userText, sessionId = null, detectedLanguageCode = null) {
  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: userText,
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Agent call failed [${res.status}]: ${err}`);
  }

  return res.json();
  // { session_id, status, reply_text, should_ask_followup,
  //   followup_question, missing_fields, collected_slots, referenced_schemes }
}


export async function fetchTTSAudio(text, languageCode = null) {
  const res = await fetch(`${BASE_URL}/api/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      language_code: languageCode,
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`TTS failed [${res.status}]: ${err}`);
  }

  const audioBlob = await res.blob();                     // audio/mpeg blob
  return URL.createObjectURL(audioBlob);                  // blob:// URL
}