import yaml
import os

_DEFAULTS = {
    "terminology_server": "https://r4.ontoserver.csiro.au/fhir",
    "valueset_url": "http://snomed.info/sct?fhir_vs=ecl/<363679005:405813007=*,424361007=*",
    "cache_file": "concept_map_cache.json",
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
