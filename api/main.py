from __future__ import annotations

import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from autonlp import ConditionExtractorPipeline


SUPPORTED_LANGS = ["ko", "en", "ja", "zh", "fr", "de", "ar"]
API_TOKEN = os.getenv("AUTONLP_API_TOKEN", "").strip()
API_KEYS_ENV = os.getenv("AUTONLP_API_KEYS", "").strip()
AUTH_ISSUER_TOKEN = os.getenv("AUTONLP_AUTH_ISSUER_TOKEN", "").strip()
ISSUED_KEY_TTL_SECONDS = int(os.getenv("AUTONLP_ISSUED_KEY_TTL_SECONDS", "86400"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("AUTONLP_RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("AUTONLP_RATE_LIMIT_MAX_REQUESTS", "120"))
BATCH_MAX_ITEMS = int(os.getenv("AUTONLP_BATCH_MAX_ITEMS", "32"))

_RATE_LIMIT_STORE: dict[str, deque[float]] = defaultdict(deque)
_RATE_LIMIT_LOCK = threading.Lock()
_ISSUED_AUTH_KEYS: dict[str, float] = {}
_ISSUED_AUTH_KEYS_LOCK = threading.Lock()


class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)
    lang: str = Field(default="ko")
    ref_datetime: str | None = Field(default=None, description="ISO datetime (e.g. 2026-03-04T12:00:00+09:00)")
    recipient_lexicon: list[str] | None = None
    normalize_object_items: bool = True
    object_join_token: str | None = None
    config: dict[str, Any] | None = None


class ExtractResponse(BaseModel):
    result: dict[str, Any]


class BatchExtractRequest(BaseModel):
    items: list[ExtractRequest] = Field(..., min_length=1)
    continue_on_error: bool = True


class BatchExtractItem(BaseModel):
    index: int
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class BatchExtractResponse(BaseModel):
    results: list[BatchExtractItem]


class AuthKeyIssueRequest(BaseModel):
    ttl_seconds: int | None = Field(default=None, ge=60, le=7 * 24 * 3600)


class AuthKeyIssueResponse(BaseModel):
    auth_key: str
    expires_at_unix: int


def _normalize_lexicon(lexicon: list[str] | None) -> tuple[str, ...]:
    if not lexicon:
        return tuple()
    return tuple(sorted({item.strip() for item in lexicon if item and item.strip()}))


def _parse_reference_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ref_datetime: {value}") from exc


def _normalize_lang(lang: str) -> str:
    value = (lang or "ko").lower().strip()
    if value in {"kr", "ko-kr"}:
        return "ko"
    if value in {"en-us", "en-gb"}:
        return "en"
    if value in {"jp", "ja-jp"}:
        return "ja"
    if value in {"zh-cn", "zh-tw"}:
        return "zh"
    if value in {"fr-fr"}:
        return "fr"
    if value in {"de-de"}:
        return "de"
    if value in {"ar-sa"}:
        return "ar"
    return value


def _auth_key(request: Request) -> str:
    token = _extract_incoming_auth_key(request)
    if token:
        return f"token:{token}"
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def _configured_api_keys() -> set[str]:
    keys: set[str] = set()
    if API_TOKEN:
        keys.add(API_TOKEN)
    if API_KEYS_ENV:
        keys.update({item.strip() for item in API_KEYS_ENV.split(",") if item.strip()})
    return keys


def _extract_incoming_auth_key(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        token = header.removeprefix("Bearer ").strip()
        if token:
            return token
    x_auth_key = request.headers.get("x-auth-key", "").strip()
    if x_auth_key:
        return x_auth_key
    return ""


def _purge_expired_issued_keys(now: float) -> None:
    expired = [key for key, exp in _ISSUED_AUTH_KEYS.items() if exp <= now]
    for key in expired:
        _ISSUED_AUTH_KEYS.pop(key, None)


def _generate_auth_key() -> str:
    return f"ak_{secrets.token_urlsafe(32)}"


def _issue_auth_key(ttl_seconds: int) -> tuple[str, int]:
    key = _generate_auth_key()
    expires_at = int(time.time()) + ttl_seconds
    with _ISSUED_AUTH_KEYS_LOCK:
        _purge_expired_issued_keys(time.time())
        _ISSUED_AUTH_KEYS[key] = float(expires_at)
    return key, expires_at


def _validate_auth(request: Request) -> None:
    configured_keys = _configured_api_keys()
    has_dynamic_issuer = bool(AUTH_ISSUER_TOKEN)
    if not configured_keys and not has_dynamic_issuer:
        return
    token = _extract_incoming_auth_key(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth key")

    if token in configured_keys:
        return

    with _ISSUED_AUTH_KEYS_LOCK:
        now = time.time()
        _purge_expired_issued_keys(now)
        expires_at = _ISSUED_AUTH_KEYS.get(token)
        if expires_at and expires_at > now:
            return

    raise HTTPException(status_code=401, detail="Invalid auth key")


def _validate_issuer_auth(request: Request) -> None:
    if not AUTH_ISSUER_TOKEN:
        raise HTTPException(status_code=403, detail="Issuer token is not configured")
    issuer_token = request.headers.get("x-issuer-token", "").strip()
    if issuer_token != AUTH_ISSUER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid issuer token")


def _check_rate_limit(request: Request) -> None:
    if RATE_LIMIT_MAX_REQUESTS <= 0:
        return
    key = _auth_key(request)
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    with _RATE_LIMIT_LOCK:
        queue = _RATE_LIMIT_STORE[key]
        while queue and queue[0] < window_start:
            queue.popleft()
        if len(queue) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        queue.append(now)


def _extract_one(request: ExtractRequest) -> dict[str, Any]:
    lang = _normalize_lang(request.lang)
    if lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail=f"Unsupported lang: {request.lang}")

    config = request.config or {}
    config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)
    lexicon = _normalize_lexicon(request.recipient_lexicon)

    pipeline = _get_pipeline(
        lang=lang,
        ref_datetime=request.ref_datetime,
        recipient_lexicon=lexicon,
        normalize_object_items=request.normalize_object_items,
        object_join_token=request.object_join_token,
        config_json=config_json,
    )
    return pipeline.extract(request.text).to_dict()


@lru_cache(maxsize=64)
def _get_pipeline(
    lang: str,
    ref_datetime: str | None,
    recipient_lexicon: tuple[str, ...],
    normalize_object_items: bool,
    object_join_token: str | None,
    config_json: str,
) -> ConditionExtractorPipeline:
    config: dict[str, Any] = json.loads(config_json)
    parsed_dt = _parse_reference_datetime(ref_datetime)
    return ConditionExtractorPipeline(
        lang=lang,
        reference_datetime=parsed_dt,
        recipient_lexicon=list(recipient_lexicon) if recipient_lexicon else None,
        normalize_object_items=normalize_object_items,
        object_join_token=object_join_token,
        config=config,
    )


app = FastAPI(title="autonlp API", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/supported-langs")
def supported_langs() -> dict[str, list[str]]:
    return {"langs": SUPPORTED_LANGS}


@app.post("/auth/issue-key", response_model=AuthKeyIssueResponse)
def issue_auth_key(request: AuthKeyIssueRequest, raw_request: Request) -> AuthKeyIssueResponse:
    _validate_issuer_auth(raw_request)
    ttl_seconds = request.ttl_seconds if request.ttl_seconds is not None else ISSUED_KEY_TTL_SECONDS
    auth_key, expires_at = _issue_auth_key(ttl_seconds)
    return AuthKeyIssueResponse(auth_key=auth_key, expires_at_unix=expires_at)


@app.post("/extract", response_model=ExtractResponse)
def extract(request: ExtractRequest, raw_request: Request) -> ExtractResponse:
    _validate_auth(raw_request)
    _check_rate_limit(raw_request)

    try:
        result = _extract_one(request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ExtractResponse(result=result)


@app.post("/extract/batch", response_model=BatchExtractResponse)
def extract_batch(request: BatchExtractRequest, raw_request: Request) -> BatchExtractResponse:
    _validate_auth(raw_request)
    _check_rate_limit(raw_request)

    if len(request.items) > BATCH_MAX_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size exceeds limit: {len(request.items)} > {BATCH_MAX_ITEMS}",
        )

    results: list[BatchExtractItem] = []
    for index, item in enumerate(request.items):
        try:
            result = _extract_one(item)
            results.append(BatchExtractItem(index=index, ok=True, result=result))
        except Exception as exc:
            if not request.continue_on_error:
                if isinstance(exc, HTTPException):
                    raise exc
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            message = exc.detail if isinstance(exc, HTTPException) else str(exc)
            results.append(BatchExtractItem(index=index, ok=False, error=message))

    return BatchExtractResponse(results=results)
