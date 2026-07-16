"""
app.py
Flask application for the SNOMED CT Radiology Procedure Deconstructor.

Routes:
  GET  /                       — main UI
  GET  /api/valuesets          — configured valuesets/terminology servers + defaults
  GET  /api/concept-map        — concept map for a (valueset, server) combo
  GET  /api/preloaded-options  — compose-panel dropdown options for a combo
  POST /api/refresh            — kick off a background rebuild of a combo
  GET  /api/refresh-status     — poll a combo's background rebuild status
  GET  /api/status             — readiness check
"""

from __future__ import annotations

import argparse
import logging
import os
import threading

from flask import Flask, jsonify, render_template, request

import fetcher
import map_builder
from config import load_config, find_valueset, find_terminology_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global state — populated in main() before Flask starts serving requests
_config: dict = {}
_concept_maps: dict[str, dict] = {}   # combo_key -> {"entries": [...], "built_at": ...}

# Background refresh bookkeeping — only one refresh runs at a time app-wide
_refresh_lock = threading.Lock()
_refreshing_combo: str | None = None
_last_attempted_combo: str | None = None
_refresh_error: str | None = None


# ── Combo helpers ────────────────────────────────────────────────────────────

def _combo_key(valueset_id: str, server_id: str) -> str:
    return f"{valueset_id}__{server_id}"


def _resolve_combo():
    """Read ?vs=&server= from the query string, falling back to configured defaults."""
    vs_id = request.args.get("vs") or _config.get("default_valueset")
    server_id = request.args.get("server") or _config.get("default_terminology_server")
    if find_valueset(_config, vs_id) is None:
        vs_id = _config.get("default_valueset")
    if find_terminology_server(_config, server_id) is None:
        server_id = _config.get("default_terminology_server")
    return vs_id, server_id


def _run_refresh(valueset_id: str, server_id: str, server_url: str) -> None:
    global _refreshing_combo, _refresh_error
    key = _combo_key(valueset_id, server_id)
    try:
        fetcher.baseurl = server_url
        logger.info("Refreshing concept map for %s against %s", key, server_url)
        payload = map_builder.refresh_map(_config, valueset_id, server_id)
        with _refresh_lock:
            _concept_maps[key] = payload
        logger.info("Refresh complete for %s: %d entries", key, len(payload["entries"]))
    except Exception as exc:
        logger.exception("Refresh failed for %s", key)
        with _refresh_lock:
            _refresh_error = str(exc)
    finally:
        with _refresh_lock:
            _refreshing_combo = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/valuesets")
def api_valuesets():
    return jsonify({
        "valuesets": _config.get("valuesets", []),
        "terminology_servers": _config.get("terminology_servers", []),
        "default_valueset": _config.get("default_valueset"),
        "default_terminology_server": _config.get("default_terminology_server"),
    })


@app.route("/api/concept-map")
def api_concept_map():
    vs_id, server_id = _resolve_combo()
    cached = _concept_maps.get(_combo_key(vs_id, server_id))
    if cached is None:
        return jsonify({"entries": [], "built_at": None, "cached": False})
    return jsonify({"entries": cached["entries"], "built_at": cached["built_at"], "cached": True})


@app.route("/api/preloaded-options")
def api_preloaded_options():
    vs_id, server_id = _resolve_combo()
    cached = _concept_maps.get(_combo_key(vs_id, server_id))
    entries = cached["entries"] if cached else []

    # Procedures from the focus-procedure file (may include options not in the valueset)
    raw_procs = fetcher.read_focus_procedures() or []
    procedures = [{"code": c, "term": d} for c, d in raw_procs]

    # Body sites: unique de-lateralised sites that appear in the concept map
    bodysite_map: dict[str, str] = {}
    for entry in entries:
        code = entry["bodysite_code"]
        if code not in bodysite_map:
            bodysite_map[code] = entry["bodysite_term"]
    bodysites = sorted(
        [{"code": k, "term": v} for k, v in bodysite_map.items()],
        key=lambda x: x["term"],
    )

    return jsonify({
        "procedures": procedures,
        "bodysites": bodysites,
        "laterality": [
            {"code": "7771000",  "term": "Left"},
            {"code": "24028007", "term": "Right"},
            {"code": "51440002", "term": "Bilateral"},
        ],
        "contrast": [
            {"code": "373066001", "term": "With contrast"},
            {"code": "373067005", "term": "Without contrast"},
        ],
    })


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    global _refreshing_combo, _last_attempted_combo, _refresh_error

    vs_id, server_id = _resolve_combo()
    valueset = find_valueset(_config, vs_id)
    server = find_terminology_server(_config, server_id)
    if valueset is None or server is None:
        return jsonify({"status": "error", "message": "unknown valueset or terminology server"}), 400

    key = _combo_key(vs_id, server_id)
    with _refresh_lock:
        if _refreshing_combo is not None:
            return jsonify({"status": "already_running", "combo": _refreshing_combo}), 409
        _refreshing_combo = key
        _last_attempted_combo = key
        _refresh_error = None

    thread = threading.Thread(target=_run_refresh, args=(vs_id, server_id, server["url"]), daemon=True)
    thread.start()
    return jsonify({"status": "started"}), 202


@app.route("/api/refresh-status")
def api_refresh_status():
    vs_id, server_id = _resolve_combo()
    key = _combo_key(vs_id, server_id)
    with _refresh_lock:
        refreshing = _refreshing_combo == key
        error = _refresh_error if (not refreshing and _last_attempted_combo == key) else None
    cached = _concept_maps.get(key)
    built_at = cached["built_at"] if cached else None
    return jsonify({"refreshing": refreshing, "built_at": built_at, "error": error})


@app.route("/api/status")
def api_status():
    vs_id, server_id = _resolve_combo()
    cached = _concept_maps.get(_combo_key(vs_id, server_id))
    count = len(cached["entries"]) if cached else 0
    return jsonify({"ready": True, "count": count})


# ── Bootstrap ─────────────────────────────────────────────────────────────────
#
# Runs unconditionally at module import time — not just under `if __name__ ==
# "__main__"` — because a production WSGI server (gunicorn, etc.) imports this
# module and uses the `app` object directly; it never calls main(). Configured
# via env vars (CONFIG_FILE, REFRESH_ON_START) since that's the only lever a
# WSGI server invocation gives us; `python app.py --refresh` re-bootstraps with
# the CLI-provided values afterwards.

def _bootstrap(config_path: str, do_refresh: bool) -> None:
    global _config
    _config = load_config(config_path)

    default_vs = _config.get("default_valueset")
    default_server_id = _config.get("default_terminology_server")
    default_key = _combo_key(default_vs, default_server_id)

    if do_refresh:
        server = find_terminology_server(_config, default_server_id)
        fetcher.baseurl = server["url"]
        logger.info("Terminology server: %s", fetcher.baseurl)
        logger.info("Refreshing default combo: %s", default_key)
        payload = map_builder.refresh_map(_config, default_vs, default_server_id)
        _concept_maps[default_key] = payload
        logger.info("Rebuilt %s — %d entries", default_key, len(payload["entries"]))

    # Load every (valueset, server) combo that already has a cache file.
    # Cheap — JSON reads only, no network calls, so startup stays instant.
    for vs in _config.get("valuesets", []):
        for server in _config.get("terminology_servers", []):
            key = _combo_key(vs["id"], server["id"])
            if key in _concept_maps:
                continue  # already loaded via a refresh above
            payload = map_builder.load_cached_map(_config, vs["id"], server["id"])
            if payload is not None:
                _concept_maps[key] = payload

    logger.info("Ready — %d combo(s) loaded: %s", len(_concept_maps), ", ".join(_concept_maps.keys()))


_bootstrap(
    os.environ.get("CONFIG_FILE", "config.yaml"),
    os.environ.get("REFRESH_ON_START", "").lower() in ("1", "true", "yes"),
)


# ── Entry point (local dev only — `python app.py`) ─────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SNOMED CT Radiology Procedure Deconstructor"
    )
    parser.add_argument(
        "--config", default="config.yaml", metavar="FILE",
        help="Path to YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Rebuild the default valueset/server combo's cache from the terminology server",
    )
    args = parser.parse_args()

    if args.config != "config.yaml" or args.refresh:
        _bootstrap(args.config, args.refresh)

    app.run(
        debug=_config.get("flask_debug", False),
        port=int(os.environ.get("PORT", _config.get("flask_port", 5000))),
        use_reloader=False,  # prevent double-build on debug reload
    )


if __name__ == "__main__":
    main()
