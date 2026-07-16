from __future__ import annotations

import yaml
import os

_DEFAULTS = {
    "terminology_servers": [
        {
            "id": "r4-csiro",
            "label": "r4.ontoserver.csiro.au",
            "url": "https://r4.ontoserver.csiro.au/fhir",
        },
    ],
    "valuesets": [
        {
            "id": "ranzcr",
            "label": "RANZCR Radiology Referral",
            "url": "https://ranzcr.com/fhir/ValueSet/radiology-referral-1",
        },
    ],
    "default_valueset": "ranzcr",
    "default_terminology_server": "r4-csiro",
    "cache_dir": "cache",
    "cache_enabled": True,
    "flask_debug": False,
    "flask_port": 5000,
}


def load_config(path: str = "config.yaml") -> dict:
    """Load YAML config, falling back to defaults for any missing keys."""
    config = dict(_DEFAULTS)
    if os.path.exists(path):
        with open(path, "r") as fh:
            loaded = yaml.safe_load(fh) or {}
        config.update(loaded)
    else:
        print(f"Warning: config file '{path}' not found — using defaults.")
    return config


def find_valueset(config: dict, valueset_id: str) -> dict | None:
    """Return the {id, label, url} dict for valueset_id, or None if unknown."""
    for entry in config.get("valuesets", []):
        if entry.get("id") == valueset_id:
            return entry
    return None


def find_terminology_server(config: dict, server_id: str) -> dict | None:
    """Return the {id, label, url} dict for server_id, or None if unknown."""
    for entry in config.get("terminology_servers", []):
        if entry.get("id") == server_id:
            return entry
    return None
