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
from storage import UsageStore, ist_now

BASE_DIR = Path(__file__).resolve().parent
API_FILE = Path(os.getenv("API_FILE", str(BASE_DIR / "apis9.json")))
KEY_FILE = Path(os.getenv("KEY_FILE", str(BASE_DIR / "keys.json")))
PORT = int(os.getenv("PORT", "8888"))
MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "256"))
UPSTREAM_CONNECT_TIMEOUT = float(os.getenv("UPSTREAM_CONNECT_TIMEOUT", "4"))
UPSTREAM_READ_TIMEOUT = float(os.getenv("UPSTREAM_READ_TIMEOUT", "10"))
MAX_UPSTREAM_WORKERS = int(os.getenv("MAX_UPSTREAM_WORKERS", "16"))
IST = ZoneInfo("Asia/Kolkata")

app = Flask(__name__)
app.json.sort_keys = False

_config_lock = threading.RLock()
_usage_store = UsageStore()
_search_executor = ThreadPoolExecutor(max_workers=MAX_UPSTREAM_WORKERS, thread_name_prefix="upstream")
_local = threading.local()


def now_ist() -> datetime:
    return datetime.now(IST)


def load_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError) as exc:
        app.logger.warning("Failed to read %s: %s", path, exc)
        return default


def load_apis(api_type: str | None = None):
    data = load_json(API_FILE, {"apis": {}}).get("apis", {})
    if isinstance(data, list):
        return data
    if api_type:
        urls = data.get(api_type.lower(), [])
        return urls if isinstance(urls, list) else []
    return []


def load_key_config(key: str):
    keys = load_json(KEY_FILE, {"keys": {}}).get("keys", {})
    return keys.get(key)


def key_is_valid(key: str):
    config = load_key_config(key)
    if not isinstance(config, dict):
        return False, "Invalid Key", None

    expiry = config.get("expiry")
    if expiry not in (None, ""):
        try:
            if datetime.now(timezone.utc).timestamp() > float(expiry):
                return False, "Key Expired", None
        except (TypeError, ValueError):
            return False, "Invalid Key Expiry", None

    return True, "OK", config


def get_session():
    session = getattr(_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "AbyssAPI/2.0",
            "Accept": "application/json,image/*;q=0.8,*/*;q=0.5",
            "Connection": "keep-alive",
        })
        _local.session = session
    return session


def extract_data(data, api_type: str):
    extractor = EXTRACTORS.get(api_type.lower())
    if extractor is None:
        return None
    return extractor(data)


def call_api(api_url: str, query: str, api_type: str):
    try:
        encoded_query = quote(str(query), safe="")
        url = api_url.replace("{query}", encoded_query)
        response = get_session().get(
            url,
            timeout=(UPSTREAM_CONNECT_TIMEOUT, UPSTREAM_READ_TIMEOUT),
        )
        if response.status_code < 200 or response.status_code >= 300:
            return None

        if api_type == "link2qr":
            content = response.content
            if content:
                return {
                    "found": True,
                    "image": content,
                    "content_type": response.headers.get("Content-Type", "image/png"),
                }
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        parsed = extract_data(payload, api_type)
        if parsed:
            return {"found": True, "data": parsed}
    except requests.RequestException as exc:
        app.logger.debug("Upstream request failed: %s", exc)
    except Exception:
        app.logger.exception("Unexpected upstream/parser error")
    return None


def search(query: str, api_type: str):
    api_type = api_type.lower()
    apis = load_apis(api_type)
    if not apis:
        return {"found": False, "error": f"No APIs found for type: {api_type}"}

    # Avoid a thread hop when there is only one upstream.
    if len(apis) == 1:
        return call_api(apis[0], query, api_type) or {"found": False}

    futures = {_search_executor.submit(call_api, url, query, api_type) for url in apis}
    pending = set(futures)
    try:
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                try:
                    result = future.result()
                except Exception:
                    app.logger.exception("Upstream future failed")
                    continue
                if result and result.get("found"):
                    for other in pending:
                        other.cancel()
                    return result
    finally:
        # Queued work is cancelled; already-running network calls finish under their own timeout.
        for future in pending:
            future.cancel()
    return {"found": False}


@app.get("/")
def home():
    return jsonify({
        "success": True,
        "message": "API is alive",
        "server_time_ist": now_ist().isoformat(),
        "timezone": "Asia/Kolkata",
    })


@app.get("/health")
def health():
    return jsonify({
        "success": True,
        "status": "healthy",
        "server_time_ist": now_ist().isoformat(),
    })


@app.get("/api")
def api():
    api_type = (request.args.get("types") or "").strip().lower()
    key = (request.args.get("key") or "").strip()
    spell = (request.args.get("spell") or "").strip()

    if not api_type or not key or not spell:
        return jsonify({"success": False, "error": "Missing types, key or spell"}), 400
    if len(spell) > MAX_QUERY_LENGTH:
        return jsonify({"success": False, "error": "Query too long"}), 413

    ok, msg, key_config = key_is_valid(key)
    if not ok:
        return jsonify({"success": False, "error": msg}), 403

    admitted, msg, current_used = _usage_store.reserve(
        key,
        key_config.get("limit_per_hour"),
        key_config.get("limit_per_day"),
    )
    if not admitted:
        return jsonify({"success": False, "error": msg, "Used_count": current_used}), 429

    try:
        data = search(spell, api_type)

        if api_type == "link2qr":
            if data.get("found") and data.get("image"):
                _usage_store.finish(key, True)
                return Response(data["image"], mimetype=data.get("content_type", "image/png"))
            _usage_store.finish(key, False)
            return jsonify({"success": False, "error": "QR Generation Failed"}), 502

        if data.get("error"):
            _usage_store.finish(key, False)
            return jsonify({"success": False, "error": data["error"]}), 502

        if data.get("found"):
            used = _usage_store.finish(key, True)
            return jsonify({
                "success": True,
                "type": api_type,
                "result": {
                    "Spell": spell,
                    **data["data"],
                    "Used_count": used,
                    "Server_Time_IST": now_ist().isoformat(),
                    "DM FOR BUY": "@llx_oIl",
                    "Developer": "@BotFatherPrime",
                },
            })

        _usage_store.finish(key, False)
        return jsonify({
            "success": True,
            "type": api_type,
            "result": {
                "Spell": spell,
                "Msg": f"No Data Found Of {spell}",
                "Used_count": _usage_store.get_total(key),
                "Server_Time_IST": now_ist().isoformat(),
                "DM FOR BUY": "@llx_oIl",
                "Developer": "@BotFatherPrime",
            },
        })
    except Exception:
        # Make sure an admitted request never leaves an inflight slot stuck.
        _usage_store.finish(key, False)
        app.logger.exception("Request handling failed")
        return jsonify({"success": False, "error": "Internal server error"}), 500


if __name__ == "__main__":
    print(f"API STARTED ON PORT {PORT} | IST={now_ist().isoformat()}")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
