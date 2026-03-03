import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import boto3
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.database import SessionLocal

router = APIRouter(prefix="/api/ws", tags=["WebSocket Bridge"])

AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-south-1"))
WS_CONNECTIONS_TABLE = os.getenv("WS_CONNECTIONS_TABLE", "ws_connections")
if not WS_CONNECTIONS_TABLE.replace("_", "").isalnum():
    raise RuntimeError("WS_CONNECTIONS_TABLE must contain only letters, numbers, and underscores.")

_translate_client = boto3.client("translate", region_name=AWS_REGION)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


async def _read_payload(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        raw = (await request.body()).decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw)
        except Exception:
            data = {}

    # 🔥 Handle HTTP proxy wrapped body
    body = data.get("body")

    if isinstance(body, str):
        try:
            parsed = json.loads(body)
            data["body"] = parsed
        except Exception:
            # body is plain text (not JSON)
            data["body"] = body

    return data

def _extract_context(payload: Dict[str, Any], request: Request) -> Tuple[str, str, str, str, Any]:
    request_context = payload.get("requestContext") or {}

    route_key = request_context.get("routeKey")
    connection_id = request_context.get("connectionId")
    domain_name = request_context.get("domainName")
    stage = request_context.get("stage")

    # 🔥 If proxy mode did not send requestContext, read from headers
    if not connection_id:
        connection_id = request.headers.get("x-amzn-connection-id")
        route_key = request.headers.get("x-amzn-route-key")
        domain_name = request.headers.get("x-forwarded-host")
        stage = request.headers.get("x-amzn-stage")

    body = payload.get("body") or {}

    return route_key or "", connection_id or "", domain_name or "", stage or "", body

def _save_connection(connection_id: str) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                f"""
                INSERT INTO {WS_CONNECTIONS_TABLE} (connection_id, connected_at)
                VALUES (:connection_id, :connected_at)
                ON CONFLICT (connection_id)
                DO UPDATE SET connected_at = EXCLUDED.connected_at
                """
            ),
            {"connection_id": connection_id, "connected_at": _utc_now_iso()},
        )
        db.commit()
    finally:
        db.close()


def _delete_connection(connection_id: str) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(f"DELETE FROM {WS_CONNECTIONS_TABLE} WHERE connection_id = :connection_id"),
            {"connection_id": connection_id},
        )
        db.commit()
    finally:
        db.close()


def _translate_to_english(text: str) -> str:
    if not text:
        return ""
    response = _translate_client.translate_text(
        Text=text,
        SourceLanguageCode="auto",
        TargetLanguageCode="en",
    )
    return response["TranslatedText"]


def _post_to_connection(
    connection_id: str,
    data: Dict[str, Any],
    domain_name: str,
    stage: str,
) -> None:
    if not domain_name or not stage:
        raise HTTPException(status_code=400, detail="Missing domainName/stage in requestContext.")

    endpoint_url = f"https://{domain_name}/{stage}"
    api_client = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint_url)
    api_client.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps(data).encode("utf-8"),
    )


@router.post("/connect")
async def on_connect(request: Request):
    payload = await _read_payload(request)
    route_key, connection_id, domain_name, stage, body = _extract_context(payload)
    if not connection_id:
        raise HTTPException(status_code=400, detail="Missing connectionId in requestContext.")

    try:
        _save_connection(connection_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save connection in Postgres table '{WS_CONNECTIONS_TABLE}': {exc}",
        )
    return {"statusCode": 200, "body": "Connected"}


@router.post("/disconnect")
async def on_disconnect(request: Request):
    payload = await _read_payload(request)
    _, connection_id, _, _, _ = _extract_context(payload)
    if not connection_id:
        raise HTTPException(status_code=400, detail="Missing connectionId in requestContext.")

    try:
        _delete_connection(connection_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete connection in Postgres table '{WS_CONNECTIONS_TABLE}': {exc}",
        )
    return {"statusCode": 200, "body": "Disconnected"}


@router.post("/message")
async def on_message(request: Request):
    payload = await _read_payload(request)
    route_key, connection_id, domain_name, stage, body = _extract_context(payload)

    if not connection_id:
        raise HTTPException(status_code=400, detail="Missing connectionId in requestContext.")

    # Accept several common message shapes from API Gateway mapping templates.
    text = ""
    if isinstance(body, dict):
        text = str(body.get("text") or body.get("message") or "")
    elif isinstance(body, str):
        text = body

    english_text = _translate_to_english(text) if text else ""

    response = {
        "type": "message",
        "route": route_key or "$default",
        "transcript_hindi": text,
        "transcript_english": english_text,
        "timestamp": _utc_now_iso(),
    }

    try:
        _post_to_connection(
            connection_id=connection_id,
            data=response,
            domain_name=domain_name,
            stage=stage,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"postToConnection failed: {exc}")

    return {"statusCode": 200, "body": "Message processed"}
