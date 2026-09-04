from __future__ import annotations

import json
import os
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from flask import Flask, Response, jsonify, request

from extractors import EXTRACTORS
from storage import UsageStore


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
API_FILE = Path(os.getenv("API_FILE", str(BASE_DIR / "apis9.json")))
KEY_FILE = Path(os.getenv("KEY_FILE", str(BASE_DIR / "keys.json")))
PORT = int(os.getenv("PORT", "8080"))
MAX_QUERY_LENGTH = max(1, int(os.getenv("MAX_QUERY_LENGTH", "256")))
UPSTREAM_CONNECT_TIMEOUT = max(
    0.1, float(os.getenv("UPSTREAM_CONNECT_TIMEOUT", "4"))
)
UPSTREAM_READ_TIMEOUT = max(
    0.1, float(os.getenv("UPSTREAM_READ_TIMEOUT", "10"))
)
MAX_UPSTREAM_WORKERS = max(
    1, int(os.getenv("MAX_UPSTREAM_WORKERS", "16"))
)
IST = ZoneInfo("Asia/Kolkata")

# link2qr returns an image, so it does not need an extractor.
SPECIAL_TYPES = {"link2qr"}


# -----------------------------------------------------------------------------
# App / shared state
# -----------------------------------------------------------------------------

app = Flask(__name__)
app.json.sort_keys = False

_config_lock = threading.RLock()
_usage_store = UsageStore()

_search_executor = ThreadPoolExecutor(
    max_workers=MAX_UPSTREAM_WORKERS,
    thread_name_prefix="upstream",
)

_local = threading.local()


# -----------------------------------------------------------------------------
# Time helpers
# -----------------------------------------------------------------------------

def now_ist() -> datetime:
    return datetime.now(IST)


# -----------------------------------------------------------------------------
# JSON / configuration helpers
# -----------------------------------------------------------------------------

def load_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError, TypeError) as exc:
        app.logger.warning("Failed to read %s: %s", path, exc)
        return default


def load_apis(api_type: str | None = None):
    """Load upstream URLs for one type from apis9.json."""
    with _config_lock:
        payload = load_json(API_FILE, {"apis": {}})

    if not isinstance(payload, dict):
        return []

    data = payload.get("apis", {})

    if isinstance(data, list):
        # Backward compatibility for an old flat list config.
        return [
            item
            for item in data
            if isinstance(item, str) and item.strip()
        ]

    if not isinstance(data, dict) or not api_type:
        return []

    urls = data.get(api_type.lower(), [])

    if not isinstance(urls, list):
        return []

    return [
        item.strip()
        for item in urls
        if isinstance(item, str) and item.strip()
    ]


def load_key_config(key: str):
    with _config_lock:
        payload = load_json(KEY_FILE, {"keys": {}})

    if not isinstance(payload, dict):
        return None

    keys = payload.get("keys", {})

    if not isinstance(keys, dict):
        return None

    config = keys.get(key)

    return config if isinstance(config, dict) else None


def key_is_valid(key: str):
    config = load_key_config(key)

    if config is None:
        return False, "Invalid Key", None

    expiry = config.get("expiry")

    if expiry not in (None, ""):
        try:
            if datetime.now(timezone.utc).timestamp() > float(expiry):
                return False, "Key Expired", None

        except (TypeError, ValueError):
            return False, "Invalid Key Expiry", None

    return True, "OK", config


# -----------------------------------------------------------------------------
# HTTP session helper
# -----------------------------------------------------------------------------

def get_session() -> requests.Session:
    """Create one keep-alive session per worker thread."""
    session = getattr(_local, "session", None)

    if session is None:
        session = requests.Session()

        session.headers.update(
            {
                "User-Agent": "AbyssAPI/2.1",
                "Accept": (
                    "application/json, text/json, text/plain, "
                    "image/*;q=0.8, */*;q=0.5"
                ),
                "Connection": "keep-alive",
            }
        )

        _local.session = session

    return session


# -----------------------------------------------------------------------------
# Extractor helpers
# -----------------------------------------------------------------------------

def extract_data(data, api_type: str):
    """Run the extractor registered for the requested API type."""
    extractor = EXTRACTORS.get(api_type.lower())

    if extractor is None:
        return None

    return extractor(data)


def parse_upstream_json(response: requests.Response):
    """
    Parse JSON robustly.

    Some upstreams send valid JSON while declaring a non-JSON content type.
    response.json() can reject those; json.loads(response.text) handles them.
    """
    try:
        return response.json()

    except (
        ValueError,
        requests.exceptions.JSONDecodeError,
    ):
        pass

    text = response.text.lstrip("\ufeff").strip()

    if not text:
        return None

    try:
        return json.loads(text)

    except (TypeError, ValueError):
        return None


# -----------------------------------------------------------------------------
# Secret placeholder helper
# -----------------------------------------------------------------------------
def resolve_api_url(api_url, query):
    encoded_query = quote(str(query), safe="")
    url = api_url.replace("{query}", encoded_query)

    # Family API secret
    if "{FAMILY_API_KEY}" in url:
        family_key = os.getenv("FAMILY_API_KEY", "").strip()

        if not family_key:
            return None, "FAMILY_API_KEY is not configured"

        url = url.replace("{FAMILY_API_KEY}", family_key)

    # VNUM API secret
    if "{VNUM_API_KEY}" in url:
        vnum_key = os.getenv("VNUM_API_KEY", "").strip()

        if not vnum_key:
            return None, "VNUM_API_KEY is not configured"

        url = url.replace("{VNUM_API_KEY}", vnum_key)

    return url, None


# -----------------------------------------------------------------------------
# Upstream request
# -----------------------------------------------------------------------------

def call_api(api_url: str, query: str, api_type: str):
    """
    Call one upstream and normalize the outcome.

    This function is intentionally type-generic. Every normal data type is
    passed through its registered extractor; link2qr is the only image special
    case.
    """
    api_type = api_type.lower()

    # Resolve query + environment-based secrets here.
    url, config_error = resolve_api_url(api_url, query)

    if config_error:
        app.logger.error(
            "API CONFIG ERROR type=%s error=%s",
            api_type,
            config_error,
        )

        return {
            "found": False,
            "config_error": True,
            "message": config_error,
        }

    if not url:
        return {
            "found": False,
            "config_error": True,
            "message": "Could not build upstream URL",
        }

    try:
        response = get_session().get(
            url,
            timeout=(
                UPSTREAM_CONNECT_TIMEOUT,
                UPSTREAM_READ_TIMEOUT,
            ),
            allow_redirects=True,
        )

        status = response.status_code
        content_type = response.headers.get("Content-Type", "")

        app.logger.info(
            "UPSTREAM type=%s status=%s content_type=%s url=%s",
            api_type,
            status,
            content_type,
            url,
        )

        if not 200 <= status < 300:
            app.logger.warning(
                "UPSTREAM FAILED type=%s status=%s url=%s",
                api_type,
                status,
                url,
            )

            return {
                "found": False,
                "upstream_error": True,
                "status_code": status,
                "message": f"Upstream returned HTTP {status}",
            }

        # ------------------------------------------------------------------
        # Image response type
        # ------------------------------------------------------------------

        if api_type in SPECIAL_TYPES:
            content = response.content

            if not content:
                return {
                    "found": False,
                    "upstream_error": True,
                    "status_code": status,
                    "message": "Upstream returned an empty image",
                }

            return {
                "found": True,
                "image": content,
                "content_type": content_type or "image/png",
            }

        # ------------------------------------------------------------------
        # Normal JSON response types
        # ------------------------------------------------------------------

        payload = parse_upstream_json(response)

        if payload is None:
            body_preview = (
                response.text[:300]
                .replace("\n", " ")
                .replace("\r", " ")
            )

            app.logger.warning(
                "UPSTREAM NON-JSON type=%s content_type=%s body=%r",
                api_type,
                content_type,
                body_preview,
            )

            return {
                "found": False,
                "upstream_error": True,
                "status_code": status,
                "message": "Upstream returned a non-JSON response",
            }

        try:
            parsed = extract_data(payload, api_type)

        except Exception:
            app.logger.exception(
                "EXTRACTOR ERROR type=%s url=%s",
                api_type,
                url,
            )

            return {
                "found": False,
                "extract_error": True,
                "message": f"Extractor error for type: {api_type}",
            }

        if parsed:
            return {
                "found": True,
                "data": parsed,
            }

        app.logger.warning(
            "EXTRACTOR EMPTY type=%s payload_type=%s",
            api_type,
            type(payload).__name__,
        )

        return {
            "found": False,
            "extract_error": True,
            "message": f"Could not parse {api_type} response",
        }

    except requests.Timeout as exc:
        app.logger.warning(
            "UPSTREAM TIMEOUT type=%s url=%s error=%s",
            api_type,
            url,
            exc,
        )

        return {
            "found": False,
            "upstream_error": True,
            "message": "Upstream request timed out",
        }

    except requests.RequestException as exc:
        app.logger.warning(
            "UPSTREAM REQUEST ERROR type=%s url=%s error=%s",
            api_type,
            url,
            exc,
        )

        return {
            "found": False,
            "upstream_error": True,
            "message": "Upstream request failed",
        }

    except Exception:
        app.logger.exception(
            "UNEXPECTED UPSTREAM ERROR type=%s url=%s",
            api_type,
            url,
        )

        return {
            "found": False,
            "upstream_error": True,
            "message": "Unexpected upstream error",
        }


# -----------------------------------------------------------------------------
# Search / fan-out
# -----------------------------------------------------------------------------

def search(query: str, api_type: str):
    """
    Search all configured upstreams for a type.

    - One upstream: no unnecessary thread hop.
    - Multiple upstreams: race them concurrently and return the first success.
    - If every upstream fails, preserve a useful diagnostic instead of turning
      every problem into a misleading 'No Data Found'.
    """
    api_type = api_type.lower()
    apis = load_apis(api_type)

    if not apis:
        return {
            "found": False,
            "config_error": True,
            "error": f"No APIs found for type: {api_type}",
        }

    if len(apis) == 1:
        return call_api(apis[0], query, api_type)

    futures = {
        _search_executor.submit(
            call_api,
            url,
            query,
            api_type,
        )
        for url in apis
    }

    pending = set(futures)
    failures = []

    try:
        while pending:
            done, pending = wait(
                pending,
                return_when=FIRST_COMPLETED,
            )

            for future in done:
                try:
                    result = future.result()

                except Exception as exc:
                    app.logger.exception(
                        "Upstream future failed"
                    )

                    failures.append(
                        {
                            "found": False,
                            "upstream_error": True,
                            "message": str(exc),
                        }
                    )

                    continue

                if result and result.get("found"):
                    for other in pending:
                        other.cancel()

                    return result

                if result:
                    failures.append(result)

    finally:
        # Queued tasks are cancelled; requests already running will finish
        # within their own configured timeout.
        for future in pending:
            future.cancel()

    # Prefer a meaningful configuration error.
    for item in failures:
        if item.get("config_error"):
            return item

    # Then an upstream error.
    for item in failures:
        if item.get("upstream_error"):
            return item

    # Then an extractor error.
    for item in failures:
        if item.get("extract_error"):
            return item

    return {"found": False}


# -----------------------------------------------------------------------------
# Common response helpers
# -----------------------------------------------------------------------------

def base_result(spell: str, used_count: int):
    return {
        "Spell": spell,
        "Used_count": used_count,
        "Server_Time_IST": now_ist().isoformat(),
        "DM FOR BUY": "@llx_oIl",
        "Developer": "@BotFatherPrime",
    }


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.get("/")
def home():
    return jsonify(
        {
            "success": True,
            "message": "API is alive",
            "server_time_ist": now_ist().isoformat(),
            "timezone": "Asia/Kolkata",
        }
    )


@app.get("/health")
def health():
    return jsonify(
        {
            "success": True,
            "status": "healthy",
            "server_time_ist": now_ist().isoformat(),
        }
    )


@app.get("/api")
def api():
    api_type = (
        request.args.get("types") or ""
    ).strip().lower()

    key = (
        request.args.get("key") or ""
    ).strip()

    spell = (
        request.args.get("spell") or ""
    ).strip()

    if not api_type or not key or not spell:
        return jsonify(
            {
                "success": False,
                "error": "Missing types, key or spell",
            }
        ), 400

    if len(spell) > MAX_QUERY_LENGTH:
        return jsonify(
            {
                "success": False,
                "error": "Query too long",
            }
        ), 413

    # Reject unsupported types before consuming usage.
    if (
        api_type not in EXTRACTORS
        and api_type not in SPECIAL_TYPES
    ):
        return jsonify(
            {
                "success": False,
                "type": api_type,
                "error": f"Unsupported API type: {api_type}",
            }
        ), 400

    ok, msg, key_config = key_is_valid(key)

    if not ok:
        return jsonify(
            {
                "success": False,
                "error": msg,
            }
        ), 403

    admitted, msg, current_used = _usage_store.reserve(
        key,
        key_config.get("limit_per_hour"),
        key_config.get("limit_per_day"),
    )

    if not admitted:
        return jsonify(
            {
                "success": False,
                "error": msg,
                "Used_count": current_used,
            }
        ), 429

    finished = False

    try:
        data = search(spell, api_type)

        # ------------------------------------------------------------------
        # QR image response
        # ------------------------------------------------------------------

        if api_type in SPECIAL_TYPES:
            if data.get("found") and data.get("image"):
                used = _usage_store.finish(key, True)
                finished = True

                mimetype = (
                    data.get("content_type") or "image/png"
                ).split(";", 1)[0].strip()

                return Response(
                    data["image"],
                    mimetype=mimetype,
                )

            _usage_store.finish(key, False)
            finished = True

            if data.get("upstream_error"):
                return jsonify(
                    {
                        "success": False,
                        "type": api_type,
                        "error": data.get(
                            "message",
                            "QR upstream failed",
                        ),
                        "upstream_status": data.get(
                            "status_code"
                        ),
                    }
                ), 502

            return jsonify(
                {
                    "success": False,
                    "type": api_type,
                    "error": "QR Generation Failed",
                }
            ), 502

        # ------------------------------------------------------------------
        # Configuration errors
        # ------------------------------------------------------------------

        if data.get("config_error"):
            _usage_store.finish(key, False)
            finished = True

            return jsonify(
                {
                    "success": False,
                    "type": api_type,
                    "error": data.get(
                        "message",
                        data.get(
                            "error",
                            "API configuration error",
                        ),
                    ),
                }
            ), 502

        # ------------------------------------------------------------------
        # Upstream errors
        # ------------------------------------------------------------------

        if data.get("upstream_error"):
            _usage_store.finish(key, False)
            finished = True

            return jsonify(
                {
                    "success": False,
                    "type": api_type,
                    "error": data.get(
                        "message",
                        "Upstream request failed",
                    ),
                    "upstream_status": data.get(
                        "status_code"
                    ),
                }
            ), 502

        # ------------------------------------------------------------------
        # Extractor errors
        # ------------------------------------------------------------------

        if data.get("extract_error"):
            _usage_store.finish(key, False)
            finished = True

            return jsonify(
                {
                    "success": False,
                    "type": api_type,
                    "error": data.get(
                        "message",
                        "Response parsing failed",
                    ),
                }
            ), 502

        # ------------------------------------------------------------------
        # Successful extracted data
        # ------------------------------------------------------------------

        if (
            data.get("found")
            and isinstance(data.get("data"), dict)
        ):
            used = _usage_store.finish(key, True)
            finished = True

            result = base_result(spell, used)
            result.update(data["data"])

            return jsonify(
                {
                    "success": True,
                    "type": api_type,
                    "result": result,
                }
            )

        # ------------------------------------------------------------------
        # Valid API call, no matching data found
        # ------------------------------------------------------------------

        used = _usage_store.finish(key, False)
        finished = True

        result = base_result(spell, used)
        result["Msg"] = f"No Data Found Of {spell}"

        return jsonify(
            {
                "success": True,
                "type": api_type,
                "result": result,
            }
        )

    except Exception:
        if not finished:
            _usage_store.finish(key, False)

        app.logger.exception(
            "Request handling failed"
        )

        return jsonify(
            {
                "success": False,
                "type": api_type,
                "error": "Internal server error",
            }
        ), 500


# -----------------------------------------------------------------------------
# Local development entry point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print(
        f"API STARTED ON PORT {PORT} | "
        f"IST={now_ist().isoformat()}"
    )

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        threaded=True,
    )