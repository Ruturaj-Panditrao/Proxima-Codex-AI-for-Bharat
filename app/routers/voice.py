import os
import json
from datetime import datetime, timezone
from uuid import uuid4

import boto3
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

router = APIRouter(prefix="/api/voice", tags=["Voice"])

REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-south-1"))
VOICE_INPUT_S3_BUCKET = os.getenv("VOICE_INPUT_S3_BUCKET", "")
VOICE_TRANSCRIBE_LAMBDA_FUNCTION = os.getenv("VOICE_TRANSCRIBE_LAMBDA_FUNCTION", "")

s3_client = boto3.client("s3", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
translate_client = boto3.client("translate", region_name=REGION)

SUPPORTED_LANGUAGE_CODES = {
    "hi-IN",
    "en-US",
    "ta-IN",
    "te-IN",
    "ml-IN",
    "kn-IN",
    "mr-IN",
    "bn-IN",
    "gu-IN",
    "pa-IN",
}


def _validate_voice_config() -> None:
    if not VOICE_INPUT_S3_BUCKET:
        raise HTTPException(
            status_code=500,
            detail="Missing VOICE_INPUT_S3_BUCKET environment variable.",
        )
    if not VOICE_TRANSCRIBE_LAMBDA_FUNCTION:
        raise HTTPException(
            status_code=500,
            detail="Missing VOICE_TRANSCRIBE_LAMBDA_FUNCTION environment variable.",
        )


def _upload_file_to_s3(file: UploadFile) -> tuple[str, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    safe_name = (file.filename or "audio.wav").replace(" ", "_")
    object_key = f"voice-inputs/{timestamp}/{uuid4().hex}_{safe_name}"

    file.file.seek(0)
    extra_args = {}
    if file.content_type:
        extra_args["ContentType"] = file.content_type

    s3_client.upload_fileobj(file.file, VOICE_INPUT_S3_BUCKET, object_key, ExtraArgs=extra_args)
    return f"s3://{VOICE_INPUT_S3_BUCKET}/{object_key}", object_key


def _parse_lambda_payload(response_payload: bytes) -> dict:
    if not response_payload:
        return {}

    decoded = response_payload.decode("utf-8")
    if not decoded:
        return {}

    body = json.loads(decoded)
    if isinstance(body, dict) and isinstance(body.get("body"), str):
        try:
            nested = json.loads(body["body"])
            if isinstance(nested, dict):
                body = nested
        except json.JSONDecodeError:
            pass

    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="Lambda returned a non-object payload.")
    return body


def translate_to_english(text: str) -> str:
    if not text:
        return ""
    try:
        response = translate_client.translate_text(
            Text=text,
            SourceLanguageCode="auto",
            TargetLanguageCode="en",
        )
        return response["TranslatedText"]
    except Exception as exc:
        print("Translate error:", exc)
        return text


@router.post("/transcribe")
async def transcribe_audio_file(
    file: UploadFile = File(...),
    language_code: str | None = Form(None),
    detect_multiple_languages: bool = Form(True),
    wait_for_result: bool = Form(True),
):
    if language_code and language_code not in SUPPORTED_LANGUAGE_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language_code '{language_code}'. Use one of: {sorted(SUPPORTED_LANGUAGE_CODES)}",
        )

    _validate_voice_config()

    try:
        s3_uri, s3_key = _upload_file_to_s3(file)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to upload audio to S3: {exc}") from exc

    lambda_payload = {
        "bucket": VOICE_INPUT_S3_BUCKET,
        "key": s3_key,
        "s3_uri": s3_uri,
        "detect_multiple_languages": detect_multiple_languages,
        "language_options": sorted(SUPPORTED_LANGUAGE_CODES),
        "language_code": language_code,
    }

    invocation_type = "RequestResponse" if wait_for_result else "Event"
    try:
        lambda_response = lambda_client.invoke(
            FunctionName=VOICE_TRANSCRIBE_LAMBDA_FUNCTION,
            InvocationType=invocation_type,
            Payload=json.dumps(lambda_payload).encode("utf-8"),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to invoke Lambda: {exc}") from exc

    if invocation_type == "Event":
        return {
            "status": "accepted",
            "message": "Audio uploaded to S3 and sent to Lambda for async transcription.",
            "s3_uri": s3_uri,
            "lambda_status_code": lambda_response.get("StatusCode"),
        }

    if lambda_response.get("FunctionError"):
        error_payload = lambda_response.get("Payload").read().decode("utf-8")
        raise HTTPException(status_code=502, detail=f"Lambda error: {error_payload}")

    response_payload = lambda_response.get("Payload").read()
    lambda_data = _parse_lambda_payload(response_payload)

    transcript_text = (
        lambda_data.get("transcript_text")
        or lambda_data.get("transcript")
        or lambda_data.get("text")
        or ""
    ).strip()
    detected_language = (
        lambda_data.get("detected_language_code")
        or lambda_data.get("detected_language")
        or lambda_data.get("language_code")
        or (language_code or "auto")
    )
    english_text = translate_to_english(transcript_text) if transcript_text else ""

    return {
        "status": "completed",
        "s3_uri": s3_uri,
        "detected_language_code": detected_language,
        "transcript_text": transcript_text,
        "transcript_hindi": transcript_text,
        "transcript_english": english_text,
        "lambda_result": lambda_data,
    }
