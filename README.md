# AI FOR BHARAT

Backend platform for:
- Indian government scheme discovery (`/api/schemes`)
- RAG-style agent answers using AWS Bedrock + pgvector (`/api/chat`)
- Voice transcription pipeline using S3 + Lambda + Amazon Transcribe (`/api/voice/transcribe`)
- Text-to-speech using Amazon Polly (`/api/tts`)

The backend lives in `BACKEND/` and is built with FastAPI + PostgreSQL.

## Project Structure

```text
AI FOR BHARAT/
├─ BACKEND/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ database.py
│  │  ├─ models.py
│  │  ├─ schemas.py
│  │  ├─ services.py
│  │  └─ routers/
│  │     ├─ schemes.py
│  │     ├─ chat.py
│  │     ├─ voice.py
│  │     └─ tts_router.py
│  ├─ lambda/
│  │  ├─ transcribe_from_s3.py
│  │  ├─ transcribe_from_s3.zip
│  │  └─ trust-policy.json
│  ├─ ingest_data.py
│  ├─ update_embeddings.py
│  ├─ requirements.txt
│  ├─ Dockerfile
│  └─ test.html
├─ master_schemes_list.json
├─ first_scheme_deep_data.json
├─ ultimate_schemes_database.json
└─ scrape.py
```

## Features

- Scheme listing and filtering by search/state.
- Top-k vector retrieval from PostgreSQL `pgvector`.
- Answer generation via Amazon Bedrock (`apac.amazon.nova-lite-v1:0`).
- Voice upload to S3 and transcription through Lambda + Amazon Transcribe.
- Runtime language detection fallback for voice response normalization.
- MP3 speech synthesis via Amazon Polly.

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- SQLAlchemy + PostgreSQL + pgvector
- AWS services:
  - S3
  - Lambda
  - Transcribe
  - Translate
  - Polly
  - Bedrock Runtime

## Supported Voice Language Codes

Current configured set:
- `hi-IN`
- `en-US`
- `ta-IN`
- `te-IN`
- `ml-IN`
- `kn-IN`
- `mr-IN`
- `bn-IN`
- `gu-IN`
- `pa-IN`

Note: Support depends on Amazon Transcribe/Translate availability and audio quality.

## Prerequisites

- Python 3.11 or newer
- PostgreSQL with `pgvector` extension
- AWS credentials with access to required services
- A configured S3 bucket for voice uploads
- Lambda function deployed from `BACKEND/lambda/transcribe_from_s3.py`

## Environment Variables

Create `BACKEND/.env` (or copy from `.env.example`) with:

- `DATABASE_URL`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION` (or `AWS_REGION`)
- `VOICE_INPUT_S3_BUCKET`
- `VOICE_TRANSCRIBE_LAMBDA_FUNCTION`
- `AGENT_ENABLE_FOLLOW_UP` (optional)

## Local Setup

1. Create and activate a virtual environment.
2. Install dependencies.
3. Start FastAPI.

```powershell
cd BACKEND
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
GET http://127.0.0.1:8000/
```

## API Overview

### 1) Schemes API

Base: `/api/schemes`

- `GET /api/schemes/`
  - Query params: `skip`, `limit`, `state`, `search`
- `GET /api/schemes/{slug}`

Example:

```bash
curl "http://127.0.0.1:8000/api/schemes/?search=scholarship&state=Assam&limit=10"
```

### 2) Chat Agent API

Base: `/api/chat`

- `POST /api/chat/`

Body:

```json
{
  "query": "I am a farmer from Maharashtra, what schemes can help?"
}
```

Pipeline:
- Generate embedding (Titan V2)
- Retrieve top 3 nearest schemes from pgvector
- Generate response with Bedrock Nova Lite

### 3) Voice Transcription API

Base: `/api/voice`

- `POST /api/voice/transcribe` (multipart form-data)
  - `file` (required)
  - `language_code` (optional)
  - `detect_multiple_languages` (optional, default backend currently `false`)
  - `wait_for_result` (optional, default `true`)

Flow:
1. Upload audio to S3
2. Invoke Lambda transcription job
3. Return transcript + detected language + English translation

Example:

```bash
curl -X POST "http://127.0.0.1:8000/api/voice/transcribe" \
  -F "file=@voice_note.wav" \
  -F "wait_for_result=true"
```

### 4) Text-to-Speech API

Base: `/api`

- `POST /api/tts`

Body:

```json
{
  "text": "Namaste, main aapki madad ke liye yahan hoon.",
  "language_code": "hi-IN"
}
```

Returns `audio/mpeg`.

## Data Ingestion and Embeddings

From `BACKEND/`:

1. Ingest schemes JSON into PostgreSQL:

```powershell
python ingest_data.py
```

2. Generate/update vector embeddings:

```powershell
python update_embeddings.py
```

## Lambda: `transcribe_from_s3.py`

Location:
- `BACKEND/lambda/transcribe_from_s3.py`

What it does:
- Starts Transcribe jobs from S3 media URI
- Supports explicit `LanguageCode`, `IdentifyLanguage`, and `IdentifyMultipleLanguages`
- Handles unsupported multi-language codes with retries/fallback
- Parses transcript text and best-effort detected language

Recent robustness in this code:
- Safe boolean parsing for incoming event flags
- Better language extraction from multiple Transcribe payload formats
- Fallback to job-level language metadata when transcript JSON lacks language

## Deployment Notes

### Backend Docker image

From `BACKEND/`:

```powershell
docker build -t ai4bharat/backend .
```

Push to ECR (replace account/registry as needed):

```powershell
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.ap-south-1.amazonaws.com
docker tag ai4bharat/backend:latest <account>.dkr.ecr.ap-south-1.amazonaws.com/ai4bharat/backend:latest
docker push <account>.dkr.ecr.ap-south-1.amazonaws.com/ai4bharat/backend:latest
```

### Lambda package/update

From `BACKEND/`:

```powershell
Compress-Archive -Path .\lambda\transcribe_from_s3.py -DestinationPath .\lambda\transcribe_from_s3.zip -Force
aws lambda update-function-code --function-name ai4bharat-transcribe-from-s3 --zip-file fileb://lambda/transcribe_from_s3.zip --region ap-south-1
```

For full step-by-step CLI sequence, see:
- `BACKEND/aws guide.txt`

## IAM Permissions (Minimum)

Backend execution role/user:
- `s3:PutObject` on `VOICE_INPUT_S3_BUCKET/voice-inputs/*`
- `lambda:InvokeFunction` on `VOICE_TRANSCRIBE_LAMBDA_FUNCTION`
- Bedrock invoke permissions
- Polly + Translate permissions

Lambda role:
- `transcribe:StartTranscriptionJob`
- `transcribe:GetTranscriptionJob`
- CloudWatch Logs permissions
- Optional S3 write permissions if output bucket is used

## Troubleshooting

### `detected_language_code` is `unknown`
- Check Lambda deployed version is latest zip.
- Check audio clarity and single-speaker quality.
- Verify Transcribe region support.
- Backend now falls back to Translate source language for normalization when possible.

### Marathi or another supported language not detected reliably
- Try `detect_multiple_languages=false` for single-language clips.
- Ensure sample rate and encoding are clean (`wav` 16k mono is preferred for testing).
- Confirm language is in supported set and AWS service supports that path in your region.

### Lambda invocation errors
- Verify `VOICE_TRANSCRIBE_LAMBDA_FUNCTION` name/ARN.
- Verify backend IAM has `lambda:InvokeFunction`.

### S3 upload errors
- Verify `VOICE_INPUT_S3_BUCKET` exists in the same region.
- Verify backend IAM has `s3:PutObject` permission.

## Quick Manual Test UI

Use:
- `BACKEND/test.html`

It records browser audio and posts to `/api/voice/transcribe`.

## Security Notes

- Do not commit real AWS keys or DB credentials to git.
- Prefer IAM roles over static access keys in production.
- Restrict CORS in production (currently backend allows `*`).

## License

Add your project license here (for example, MIT).

