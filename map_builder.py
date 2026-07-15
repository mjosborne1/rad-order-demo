"""
map_builder.py
Builds and caches the SNOMED CT concept map used by the Flask app.

Each entry maps a precoordinated radiology procedure code to its four
semantic axes: Procedure/Modality, Body Site, Laterality, and Contrast.
Only concepts where all four axes resolve are included.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import pandas as pd
from fhirpathpy import evaluate

import fetcher

logger = logging.getLogger(__name__)

# ── In-process caches to avoid redundant terminology server calls ─────────────
_term_cache: dict[str, str] = {}
_split_site_cache: dict[str, list] = {}


# ── Preferred-term helpers ────────────────────────────────────────────────────

def _extract_display(data: dict, fallback: str) -> str:
    """Pull the 'display' parameter out of a CodeSystem/$lookup Parameters response."""
    for param in data.get("parameter", []):
        if param.get("name") == "display":
            return param.get("valueString", fallback)
    return fallback


def get_preferred_term(code: str) -> str:
    """Return the SNOMED CT preferred term for *code*, using a local cache."""
    if code in _term_cache:
        return _term_cache[code]
    try:
        data = fetcher.get_concept_all_props(code)
        term = _extract_display(data, code)
    except Exception as exc:
        logger.warning("Could not fetch preferred term for %s: %s", code, exc)
        term = code
    _term_cache[code] = term
    return term


# ── Single-call properties + term extraction ─────────────────────────────────

def _get_props_and_term(code: str) -> tuple[str, pd.DataFrame]:
    """
    One CodeSystem/$lookup call per concept.
    Returns (preferred_term, DataFrame[Concept, TypeId, Qualifier, TargetValue]).
    """
    data = fetcher.get_concept_all_props(code)

    # Preferred term
    pt = _extract_display(data, code)
    _term_cache[code] = pt

    # Properties — same FHIRPath logic as fetcher.get_snomed_props
    expr = "Parameters.parameter.where(name='property').part.where(name='subproperty').part"
    parts = evaluate(data, expr)

    rows = []
    type_id = -1
    qualifier = ""
    for elem in parts:
        if elem.get("name") == "code":
            qualifier = elem.get("valueCode", "")
            type_id = fetcher.match_property_name(qualifier)
        if elem.get("name") == "value":
            target_value = elem.get("valueCode", "")
            rows.append([code, type_id, qualifier, target_value])

    df = pd.DataFrame(rows, columns=["Concept", "TypeId", "Qualifier", "TargetValue"])
    return pt, df


# ── De-lateralisation helper (cached) ────────────────────────────────────────

def _cached_split_site(code: str) -> list:
    if code not in _split_site_cache:
        _split_site_cache[code] = fetcher.split_site(code)
    return _split_site_cache[code]


# ── Core decomposition ────────────────────────────────────────────────────────

def decompose_concept(
    pre_co: str,
    df: pd.DataFrame,
    left_list: list,
    right_list: list,
    focus_procedures,
    bilateral_procs: list,
    procs_without_contrast: list,
) -> dict | None:
    """
    Decompose a precoordinated SNOMED CT procedure into its four axes.
    Returns a dict of raw codes, or None if any axis cannot be resolved
    (concept is excluded from the concept map).
    """
    lat = ""
    contrast = ""
    site = ""

    sorted_props = df.sort_values(by=["TypeId"])

    for _, row in sorted_props.iterrows():
        # Body Site (TypeId 1) — laterality inferred from body-site membership
        if row["TypeId"] == 1:
            concept = row["TargetValue"]
            if concept in left_list:
                lat = "7771000"
            elif concept in right_list:
                lat = "24028007"
            site = concept
            if lat:
                parts = _cached_split_site(concept)
                if parts:
                    site = parts[0]

        # Contrast (TypeId 3) — presence of qualifier means "with contrast"
        if row["TypeId"] == 3:
            contrast = "373066001"

    # Bilateral procedure override
    if pre_co in bilateral_procs:
        lat = "51440002"

    # Without-contrast override (explicit "without" wins over absence of qualifier)
    if pre_co in procs_without_contrast:
        contrast = "373067005"

    # Map to focus/modality procedure
    procedure = fetcher.procedure_mapper(pre_co, focus_procedures)

    # Exclude if we couldn't map to a focus procedure
    if procedure == pre_co:
        logger.debug("Skipping %s — no focus procedure ancestor found", pre_co)
        return None

    # Exclude if any axis is still unresolved
    if not site or not lat or not contrast:
        logger.debug(
            "Skipping %s — unresolved axis (site=%s lat=%s contrast=%s)",
            pre_co, site, lat, contrast,
        )
        return None

    return {
        "pre_co": pre_co,
        "procedure": procedure,
        "bodysite": site,
        "laterality": lat,
        "contrast": contrast,
    }


# ── Concept map builder ───────────────────────────────────────────────────────

def build_concept_map(config: dict) -> list[dict]:
    """
    Expand the configured valueset, decompose every concept, and return
    a list of fully-resolved entry dicts (all four axes + preferred terms).
    """
    logger.info("Expanding valueset: %s", config["valueset_url"])
    vs_data = fetcher.get_valueset(config["valueset_url"])

    codes: list[str] = evaluate(vs_data, "expansion.contains.code")
    displays: list[str] = evaluate(vs_data, "expansion.contains.display")

    # Seed term cache from expansion (avoids a lookup call for the precoordinated terms)
    for code, display in zip(codes, displays):
        _term_cache[code] = display

    logger.info("Valueset contains %d concepts — fetching support lists…", len(codes))

    left_list = fetcher.get_body_structures("left")
    logger.info("  left body structures: %d", len(left_list))
    right_list = fetcher.get_body_structures("right")
    logger.info("  right body structures: %d", len(right_list))
    focus_procedures = fetcher.read_focus_procedures()
    bilateral_procs = fetcher.get_bilateral_procedures()
    logger.info("  bilateral procedures: %d", len(bilateral_procs))
    procs_without_contrast = fetcher.get_procedures_without_contrast()
    logger.info("  without-contrast procedures: %d", len(procs_without_contrast))

    entries: list[dict] = []

    for i, code in enumerate(codes, 1):
        logger.info("[%d/%d] Processing %s", i, len(codes), code)
        try:
            pt, df = _get_props_and_term(code)
        except Exception as exc:
            logger.warning("Skipping %s — lookup failed: %s", code, exc)
            continue

        if df.empty:
            logger.debug("Skipping %s — no properties returned", code)
            continue

        axes = decompose_concept(
            code, df, left_list, right_list,
            focus_procedures, bilateral_procs, procs_without_contrast,
        )
        if axes is None:
            continue

        entries.append({
            "precoordinated_code": code,
            "precoordinated_term": pt,
            "procedure_code":  axes["procedure"],
            "procedure_term":  get_preferred_term(axes["procedure"]),
            "bodysite_code":   axes["bodysite"],
            "bodysite_term":   get_preferred_term(axes["bodysite"]),
            "laterality_code": axes["laterality"],
            "laterality_term": get_preferred_term(axes["laterality"]),
            "contrast_code":   axes["contrast"],
            "contrast_term":   get_preferred_term(axes["contrast"]),
        })

    logger.info("Concept map built: %d entries (of %d concepts)", len(entries), len(codes))
    return entries


# ── Cache load / save ─────────────────────────────────────────────────────────

def _save_cache(entries: list[dict], config: dict) -> None:
    cache_file = config.get("cache_file", "concept_map_cache.json")
    payload = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "valueset_url": config.get("valueset_url", ""),
        "entries": entries,
    }
    with open(cache_file, "w") as fh:
        json.dump(payload, fh, indent=2)
    logger.info("Concept map cache written to %s", cache_file)


def _load_cache(config: dict) -> list[dict] | None:
    cache_file = config.get("cache_file", "concept_map_cache.json")
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, "r") as fh:
            payload = json.load(fh)
        entries = payload.get("entries", [])
        built_at = payload.get("built_at", "unknown")
        logger.info(
            "Loaded concept map from cache (%s): %d entries (built %s)",
            cache_file, len(entries), built_at,
        )
        return entries
    except Exception as exc:
        logger.warning("Cache load failed (%s) — will rebuild: %s", cache_file, exc)
        return None


def load_or_build_map(config: dict) -> list[dict]:
    """
    Return the concept map entries, loading from disk cache if available,
    otherwise building from the terminology server and saving to cache.
    """
    if config.get("cache_enabled", True):
        cached = _load_cache(config)
        if cached is not None:
            return cached

    entries = build_concept_map(config)

    if config.get("cache_enabled", True):
        _save_cache(entries, config)

    return entries
