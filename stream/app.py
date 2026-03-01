import asyncio
import json
import boto3

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent


app = FastAPI()

REGION = "us-east-1"

translate_client = boto3.client("translate", region_name=REGION)


def translate_to_english(text):

    try:

        response = translate_client.translate_text(
            Text=text,
            SourceLanguageCode="auto",
            TargetLanguageCode="en"
        )

        return response["TranslatedText"]

    except Exception as e:

        print("Translate error:", e)
        return text


class MyEventHandler(TranscriptResultStreamHandler):

    def __init__(self, output_stream, websocket: WebSocket):

        super().__init__(output_stream)
        self.websocket = websocket

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):

        results = transcript_event.transcript.results

        for result in results:

            if result.is_partial:
                continue

            for alt in result.alternatives:

                hindi_text = alt.transcript

                english_text = translate_to_english(hindi_text)

                response = {
                    "transcript_hindi": hindi_text,
                    "transcript_english": english_text
                }

                await self.websocket.send_text(json.dumps(response))


@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    client = TranscribeStreamingClient(region=REGION)

    stream = await client.start_stream_transcription(
        language_code="hi-IN",
        media_sample_rate_hz=16000,
        media_encoding="pcm"
    )

    handler = MyEventHandler(stream.output_stream, websocket)

    async def receive_audio():

        try:

            while True:

                audio_chunk = await websocket.receive_bytes()

                await stream.input_stream.send_audio_event(
                    audio_chunk=audio_chunk
                )

        except WebSocketDisconnect:

            await stream.input_stream.end_stream()

    await asyncio.gather(
        receive_audio(),
        handler.handle_events()
    )


@app.get("/")
def health():

    return {"status": "Voice streaming backend running"}