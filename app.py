"""
app.py
Flask application for the SNOMED CT Radiology Procedure Deconstructor.

Routes:
  GET /                    — main UI
  GET /api/concept-map     — full concept map as JSON (served to browser once)
  GET /api/preloaded-options — compose-panel dropdown options
  GET /api/status          — readiness check
"""

import argparse
import logging
import os
import sys

from flask import Flask, jsonify, render_template

import fetcher
from config import load_config
from map_builder import load_or_build_map

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global state — populated in main() before Flask starts serving requests
_concept_map_entries: list[dict] = []
_config: dict = {}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/concept-map")
def api_concept_map():
    return jsonify({"entries": _concept_map_entries})


@app.route("/api/preloaded-options")
def api_preloaded_options():
    # Procedures from the focus-procedure file (may include options not in the valueset)
    raw_procs = fetcher.read_focus_procedures() or []
    procedures = [{"code": c, "term": d} for c, d in raw_procs]

    # Body sites: unique de-lateralised sites that appear in the concept map
    bodysite_map: dict[str, str] = {}
    for entry in _concept_map_entries:
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


@app.route("/api/status")
def api_status():
    return jsonify({"ready": True, "count": len(_concept_map_entries)})


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global _concept_map_entries, _config

    parser = argparse.ArgumentParser(
        description="SNOMED CT Radiology Procedure Deconstructor"
    )
    parser.add_argument(
        "--config", default="config.yaml", metavar="FILE",
        help="Path to YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Delete the concept map cache and rebuild from the terminology server",
    )
    args = parser.parse_args()

    _config = load_config(args.config)

    # Point fetcher at the configured terminology server
    fetcher.baseurl = _config["terminology_server"]
    logger.info("Terminology server: %s", fetcher.baseurl)

    # Handle cache refresh
    cache_file = _config.get("cache_file", "concept_map_cache.json")
    if args.refresh and os.path.exists(cache_file):
        os.remove(cache_file)
        logger.info("Cache deleted: %s", cache_file)

    # Build or load concept map (blocking — must complete before serving requests)
    _concept_map_entries = load_or_build_map(_config)
    logger.info("Ready — %d concept map entries loaded", len(_concept_map_entries))

    app.run(
        debug=_config.get("flask_debug", False),
        port=_config.get("flask_port", 5000),
        use_reloader=False,  # prevent double-build on debug reload
    )


if __name__ == "__main__":
    main()
