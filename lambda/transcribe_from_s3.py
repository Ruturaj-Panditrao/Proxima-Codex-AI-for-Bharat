import json
import os
import time
import urllib.request
import re
from datetime import datetime, timezone

import boto3
import botocore.session


REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-south-1"))
MAX_WAIT_SECONDS = int(os.getenv("MAX_WAIT_SECONDS", "240"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "3"))
TRANSCRIBE_OUTPUT_BUCKET = os.getenv("TRANSCRIBE_OUTPUT_BUCKET", "")
TRANSCRIBE_OUTPUT_PREFIX = os.getenv("TRANSCRIBE_OUTPUT_PREFIX", "transcribe-output/")

transcribe_client = boto3.client("transcribe", region_name=REGION)


def _get_allowed_language_codes() -> set[str]:
    service_model = botocore.session.get_session().get_service_model("transcribe")
    operation_model = service_model.operation_model("StartTranscriptionJob")
    language_options_shape = operation_model.input_shape.members["LanguageOptions"]
    return set(language_options_shape.member.enum or [])


ALLOWED_LANGUAGE_CODES = _get_allowed_language_codes()


def _guess_media_format(object_key: str) -> str:
    extension = object_key.rsplit(".", 1)[-1].lower() if "." in object_key else "wav"
    supported = {"mp3", "mp4", "wav", "flac", "ogg", "amr", "webm", "m4a"}
    return extension if extension in supported else "wav"


def _fetch_transcript_json(transcript_uri: str) -> dict:
    with urllib.request.urlopen(transcript_uri, timeout=30) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def _extract_transcript_and_language(transcript_json: dict) -> tuple[str, str]:
    results = transcript_json.get("results", {}) if isinstance(transcript_json, dict) else {}
    transcript_text = ""
    detected_language_code = ""

    transcripts = results.get("transcripts", [])
    if transcripts and isinstance(transcripts, list):
        transcript_text = (transcripts[0].get("transcript") or "").strip()

    detected_language_code = (results.get("language_code") or "").strip()
    if not detected_language_code:
        language_identification = results.get("language_identification", [])
        if language_identification and isinstance(language_identification, list):
            detected_language_code = (language_identification[0].get("code") or "").strip()

    return transcript_text, detected_language_code


def _start_transcription_job(
    bucket: str,
    key: str,
    language_code: str | None,
    detect_multiple_languages: bool,
    language_options: list[str] | None,
) -> tuple[str, dict]:
    job_name = f"voice-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{int(time.time() * 1000) % 1000000}"
    media_uri = f"s3://{bucket}/{key}"
    media_format = _guess_media_format(key)

    request = {
        "TranscriptionJobName": job_name,
        "Media": {"MediaFileUri": media_uri},
        "MediaFormat": media_format,
    }

    if TRANSCRIBE_OUTPUT_BUCKET:
        request["OutputBucketName"] = TRANSCRIBE_OUTPUT_BUCKET
        request["OutputKey"] = TRANSCRIBE_OUTPUT_PREFIX

    normalized_options = [code for code in (language_options or []) if code in ALLOWED_LANGUAGE_CODES]

    if detect_multiple_languages:
        request["IdentifyMultipleLanguages"] = True
        if normalized_options:
            request["LanguageOptions"] = normalized_options
    elif language_code and language_code in ALLOWED_LANGUAGE_CODES:
        request["LanguageCode"] = language_code
    else:
        # Fallback: detect dominant language if explicit mode was not requested.
        request["IdentifyLanguage"] = True
        if normalized_options:
            request["LanguageOptions"] = normalized_options

    # Retry strategy for IdentifyMultipleLanguages validation failures:
    # AWS can reject specific codes (for this feature) even when they are valid general language codes.
    while True:
        try:
            response = transcribe_client.start_transcription_job(**request)
            return job_name, response
        except transcribe_client.exceptions.BadRequestException as exc:
            message = str(exc)
            if not request.get("IdentifyMultipleLanguages"):
                raise

            # Pattern seen from AWS:
            # "Language code ml-IN is not currently supported for multiple language identification."
            match = re.search(r"Language code ([A-Za-z]{2,3}-[A-Za-z]{2}) is not currently supported", message)
            if match and request.get("LanguageOptions"):
                bad_code = match.group(1)
                filtered = [c for c in request["LanguageOptions"] if c != bad_code]
                if filtered and len(filtered) != len(request["LanguageOptions"]):
                    request["LanguageOptions"] = filtered
                    continue
                if not filtered:
                    del request["LanguageOptions"]
                    request["IdentifyMultipleLanguages"] = False
                    request["IdentifyLanguage"] = True
                    continue
            raise


def _wait_for_completion(job_name: str) -> dict:
    deadline = time.time() + MAX_WAIT_SECONDS

    while True:
        response = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
        job = response["TranscriptionJob"]
        status = job["TranscriptionJobStatus"]

        if status in {"COMPLETED", "FAILED"}:
            return job

        if time.time() > deadline:
            raise TimeoutError(
                f"Transcription job '{job_name}' did not complete within {MAX_WAIT_SECONDS} seconds."
            )
        time.sleep(POLL_SECONDS)


def lambda_handler(event, _context):
    bucket = event.get("bucket")
    key = event.get("key")
    language_code = event.get("language_code")
    detect_multiple_languages = bool(event.get("detect_multiple_languages", True))
    language_options = event.get("language_options") or []
    wait_for_result = bool(event.get("wait_for_result", True))

    ignored_language_options = [code for code in language_options if code not in ALLOWED_LANGUAGE_CODES]
    if language_code and language_code not in ALLOWED_LANGUAGE_CODES:
        language_code = None

    if not bucket or not key:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required 'bucket' or 'key' in event."}),
        }

    try:
        job_name, _ = _start_transcription_job(
            bucket=bucket,
            key=key,
            language_code=language_code,
            detect_multiple_languages=detect_multiple_languages,
            language_options=language_options,
        )
    except Exception as exc:
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to start job: {exc}"})}

    if not wait_for_result:
        return {
            "statusCode": 202,
            "body": json.dumps(
                {
                    "status": "accepted",
                    "message": "Transcription job started.",
                    "transcription_job_name": job_name,
                    "ignored_language_options": ignored_language_options,
                }
            ),
        }

    try:
        job = _wait_for_completion(job_name)
    except TimeoutError as exc:
        return {
            "statusCode": 202,
            "body": json.dumps(
                {
                    "status": "in_progress",
                    "message": str(exc),
                    "transcription_job_name": job_name,
                }
            ),
        }
    except Exception as exc:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Failed waiting for job completion: {exc}"}),
        }

    if job["TranscriptionJobStatus"] == "FAILED":
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "failed",
                    "transcription_job_name": job_name,
                    "failure_reason": job.get("FailureReason", "Unknown"),
                }
            ),
        }

    transcript_uri = job["Transcript"]["TranscriptFileUri"]
    try:
        transcript_json = _fetch_transcript_json(transcript_uri)
        transcript_text, detected_language_code = _extract_transcript_and_language(transcript_json)
    except Exception as exc:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Failed reading transcript JSON: {exc}"}),
        }

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "status": "completed",
                "transcription_job_name": job_name,
                "transcript_text": transcript_text,
                "detected_language_code": detected_language_code or "unknown",
                "transcript_uri": transcript_uri,
                "ignored_language_options": ignored_language_options,
            }
        ),
    }
