# OpenSpec: SNOMED CT Radiology Procedure Deconstructor

## Overview

A Flask/HTML/JS demonstration app that shows the relationship between precoordinated SNOMED CT radiology procedure codes and their semantic components (Procedure/Modality, Body Site, Laterality, Contrast). Two linked panels read **left → right, decomposed → precoordinated**: the left panel selects the four component axes; the right panel shows the single precoordinated SNOMED code they resolve to. Colour carries the teaching message — each axis owns a fixed hue, and the precoordinated code is rendered as a composite bar of those hues.

---

## Decisions Log

| # | Decision | Choice |
|---|----------|--------|
| 1 | Interaction direction | **C2 — Two-panel, bidirectionally linked** |
| 2 | Cross-panel trigger | **On `change` — no button required** |
| 3 | Concept map structure | **In-memory dict, cached to disk as JSON** |
| 4 | Valueset source | **Full expansion from config URL** |
| 5 | Compose dropdown population | **Preloaded valuesets** (`get_body_structures`, `read_focus_procedures`, etc.) |
| 6 | Invalid tuple handling | **Cascading client-side JS filtering from concept map** |
| 7 | Startup strategy | **Disk cache; rebuild if absent** |
| 8 | Config format | **YAML (`config.yaml`)** |
| 9 | Dropdown display | **Preferred Term in list; code + PT revealed in detail card on selection** |
| 10 | Laterality/Contrast controls | **Bootstrap 5 toggle button groups** |
| 11 | CSS framework | **Bootstrap 5 CDN** |
| 12 | File structure | **`app.py` + `map_builder.py` + `config.py`; existing files untouched** |
| 13 | Display term storage | **Stored in cache JSON alongside codes** |
| 14 | Partial concepts (missing axes) | ~~Excluded — only fully-specified concepts~~ → **Relaxed: partial concepts admitted (see R4)** |

---

## Revised Decisions — 2026-07-15

Supersedes the rows above where noted. Prompted by "revisit some decisions."

| # | Decision | Revised choice | Supersedes |
|---|----------|----------------|------------|
| R1 | Body-site scope | **Body Site is gated on modality** — dropdown disabled until a modality is chosen, then populated only with sites that co-occur with that modality in the concept map | Q5 |
| R2 | Modality display names | **Common names, not SNOMED PTs** — X-ray / CT / MRI / Ultrasound / Fluoroscopy / PET / Bone scan (see mapping) | Q9 (procedure axis) |
| R3 | Panel direction | **Left = Compose (components), Right = precoordinated result** — reversed to read decomposed → precoordinated | Q1, Q13 |
| R4 | Default valueset | **All SNOMED imaging procedures** — `ecl/<363679005` (constraints `405813007=*,424361007=*` dropped) | Q4 valueset |

**R2 — modality common-name mapping** (applied to the procedure axis display term):

| Focus code | SNOMED PT | Common name |
|---|---|---|
| 168537006 | Plain radiography | X-ray |
| 77477000 | Computerized axial tomography | CT |
| 71651007 | Magnetic resonance imaging | MRI |
| 16310003 | Diagnostic ultrasonography | Ultrasound |
| 44491008 | Fluoroscopy | Fluoroscopy |
| 35385009 | Positron emission tomography scan | PET |
| 258113007 | Bone scan | Bone scan |

**R4 — Q14 relaxed (resolved 2026-07-15).** Broadening to all imaging procedures means many concepts lack a site and/or contrast qualifier. **Q14 is relaxed:** partial concepts are now *admitted*, not dropped. A missing axis renders as the C8 *absent* (hatched-grey) stripe in the composite bar. A concept is still excluded only if it fails to map to a focus modality at all (no modality axis = nothing to teach).

---

## Colour Scheme — 2026-07-15 (grilled)

Colour encodes the **four semantic axes**, not panel identity. Panels are neutral; the message is *Modality + Site + Laterality + Contrast = precoordinated code*, told in colour.

| # | Decision | Choice |
|---|----------|--------|
| C1 | What colour encodes | The four semantic axes (not panel identity) |
| C2 | Precoordinated code | Composite bar — four axis-hue stripes; hatched-grey stripe when an axis is absent |
| C3 | Palette | Modality `#3b5bdb` · Body Site `#0c8599` · Laterality `#e8590c` · Contrast `#7048e8`; **red `#e03131` reserved for no-match**; greys `#adb5bd`/charcoal for neutral |
| C4 | Mark | Left-border accent (3–4px) + coloured label, on **both inputs and output** |
| C5 | Foundation & flow | Soft-grey scaffold (`#f8f9fa` page, white panels, `#e9ecef` headers); centred **"="** connector between panels (rotates to "↓" on narrow screens) |
| C6 | Active state | Engaged control fills with its axis hue; text colour chosen per-swatch for ≥4.5:1 |
| C7 | Theme | Light-only; seven colours defined as `:root` CSS variables (`--axis-modality`, etc.) for a future dark swap |
| C8 | Negative states | **Gated** (disabled + "Select a modality first") ≠ **Absent** (hatched hollow stripe) ≠ **No-match** (red alert) — three marks, never overload grey |
| C9 | Hue discipline | Strict exclusivity — axis hues appear only on axis controls/rows/stripes; all incidental chrome (status badge, spinner, focus rings, buttons, "=" connector) neutralised |

---

## File Structure

```
rad-order-demo/
├── app.py                   # Flask routes only (thin)
├── map_builder.py           # build_concept_map(), cache load/save
├── config.py                # YAML config loader
├── config.yaml              # Runtime config (terminology server, valueset URL, cache path)
├── concept_map_cache.json   # Generated at first run; source of truth for UI
├── fetcher.py               # Existing — unchanged (get_valueset, get_snomed_props, etc.)
├── helpers.py               # Existing — unchanged
├── procedures.txt           # Existing — focus procedure codes
├── body_site_vs_id.txt      # Existing — body site valueset IDs
└── templates/
    └── index.html           # Single-page Bootstrap 5 UI
```

---

## Config Schema (`config.yaml`)

```yaml
terminology_server: "https://r4.ontoserver.csiro.au/fhir"
valueset_url: "http://snomed.info/sct?fhir_vs=ecl/..."  # precoordinated radiology procedures
cache_file: "concept_map_cache.json"
cache_enabled: true
flask_debug: true
```

Loaded by `config.py` using `PyYAML`. Keys exposed as a simple dict; `map_builder.py` and `app.py` import `load_config()`.

---

## Data Model

### Concept Map Cache (`concept_map_cache.json`)

```json
{
  "entries": [
    {
      "precoordinated_code": "399208008",
      "precoordinated_term": "Plain chest X-ray (procedure)",
      "procedure_code": "399208008",
      "procedure_term": "Plain chest X-ray",
      "bodysite_code": "51185008",
      "bodysite_term": "Thoracic structure",
      "laterality_code": null,
      "laterality_term": null,
      "contrast_code": "373067005",
      "contrast_term": "No"
    }
  ],
  "built_at": "2026-07-14T10:00:00Z",
  "valueset_url": "http://snomed.info/sct?fhir_vs=ecl/..."
}
```

**Rules:**
- Only concepts where **all four axes are non-null** are included (Q14).
- Display terms are **Preferred Terms** captured from `CodeSystem/$lookup` `display` field (Q13, Q9).
- `laterality_code` uses SNOMED qualifier codes: `7771000` (left), `24028007` (right), `51440002` (bilateral).
- `contrast_code` uses: `373066001` (with contrast), `373067005` (without contrast).

---

## `map_builder.py`

### `build_concept_map(config) -> list[dict]`

1. Call `get_valueset(config["valueset_url"])` to expand the valueset.
2. For each concept code in `expansion.contains`:
   a. Call `get_snomed_props(code)` — retrieves defining relationships via `CodeSystem/$lookup?property=*`.
   b. Call `get_concept_all_props(code)` to capture preferred term from `display`.
   c. Use `expand_body_site()` logic from `fetcher.py` to resolve laterality and de-lateralise body site.
   d. Use `procedure_mapper()` to map to focus procedure code.
   e. If any of the four axes is null → **skip this concept** (Q14).
   f. Append a full entry dict (codes + preferred terms for all axes).
3. Return list of entry dicts.

### `load_or_build_map(config) -> list[dict]`

```
if cache_enabled and cache_file exists:
    load and return JSON
else:
    entries = build_concept_map(config)
    if cache_enabled:
        write JSON to cache_file
    return entries
```

### Helper: `get_preferred_term(code) -> str`

Extract `display` from `CodeSystem/$lookup` response. Falls back to code string if not found.

---

## `app.py`

### Flask Routes

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Serve `index.html` |
| `GET` | `/api/concept-map` | Return full cache JSON to browser |
| `GET` | `/api/preloaded-options` | Return preloaded valueset options for compose dropdowns |
| `GET` | `/api/status` | `{ "ready": true/false, "count": N }` — startup health check |

### Startup Sequence

```python
config = load_config("config.yaml")
entries = load_or_build_map(config)        # blocking; uses disk cache
focus_procedures = read_focus_procedures() # from fetcher.py
left_bodies = get_body_structures("left")  # from fetcher.py
right_bodies = get_body_structures("right")
```

### `/api/preloaded-options` response shape

```json
{
  "procedures": [{"code": "...", "term": "..."}],
  "bodysites": [{"code": "...", "term": "..."}],
  "laterality": [
    {"code": "7771000",  "term": "Left"},
    {"code": "24028007", "term": "Right"},
    {"code": "51440002", "term": "Bilateral"}
  ],
  "contrast": [
    {"code": "373066001", "term": "With contrast"},
    {"code": "373067005", "term": "Without contrast"}
  ]
}
```

---

## Frontend (`templates/index.html`)

### Layout

Two Bootstrap 5 columns (`col-md-6` each):

```
┌─────────────────────────────────────────────────────────────────┐
│          SNOMED CT Radiology Procedure Deconstructor             │
├──────────────────────────────┬──────────────────────────────────┤
│  DECOMPOSE                   │  COMPOSE                         │
│                              │                                  │
│  Precoordinated code:        │  Procedure/Modality:             │
│  [dropdown ▼]                │  [dropdown ▼]                    │
│                              │                                  │
│  ┌──────────────────────┐    │  Body Site:                      │
│  │ Detail card:         │    │  [dropdown ▼]                    │
│  │ Code: 399208008      │    │                                  │
│  │ Term: Plain chest... │    │  Laterality:                     │
│  │                      │    │  [Left] [Right] [Bilateral]      │
│  │ Procedure:  ██████   │    │                                  │
│  │ Body Site:  ██████   │    │  Contrast:                       │
│  │ Laterality: ██████   │    │  [With] [Without]                │
│  │ Contrast:   ██████   │    │                                  │
│  └──────────────────────┘    │  ┌──────────────────────────┐   │
│                              │  │ Resolved code:            │   │
│                              │  │ 399208008                 │   │
│                              │  │ Plain chest X-ray         │   │
│                              │  └──────────────────────────┘   │
└──────────────────────────────┴──────────────────────────────────┘
```

### JavaScript Behaviour

**Data loaded once at page load:**
```javascript
const conceptMap = await fetch('/api/concept-map').then(r => r.json());
const options    = await fetch('/api/preloaded-options').then(r => r.json());
```

**Decompose panel (`change` on precoordinated dropdown):**
1. Find matching entry in `conceptMap.entries` by `precoordinated_code`.
2. Populate detail card with code, preferred term, and all four axis values.
3. Set compose panel dropdowns/toggles to matching axis values (cross-panel sync).

**Compose panel (any control `change`):**
1. Read current values of all four compose controls.
2. Filter `conceptMap.entries` for exact match on all non-null selected axes.
3. Null/unset toggles treated as wildcard (match any).
4. Cascading: after each selection, recompute valid options for remaining controls from filtered entries and disable unavailable options.
5. If exactly one match → show resolved code card + sync decompose dropdown.
6. If zero matches → show "No matching SNOMED CT code" alert (should not occur if cascading is correct).
7. If multiple matches → show count badge ("3 possible codes — please narrow selection").

### Detail Card Fields

For each axis, show:
- Axis label (e.g. "Procedure/Modality")
- SNOMED code (badge)
- Preferred term

---

## Build & Run

### First run (no cache):
```bash
pip install flask pyyaml requests fhirpathpy fhirclient pandas numpy
python app.py
# Terminology server called once to build concept_map_cache.json
# Subsequent runs load from cache instantly
```

### Force cache rebuild:
```bash
python app.py --refresh
```

### Config override:
```bash
SNOMED_CONFIG=./my_config.yaml python app.py
```

---

## Axes Reference

| Axis | SNOMED Qualifier | Code |
|------|-----------------|------|
| Procedure/Modality | Method (260686004) | varies |
| Body Site | Procedure site (405813007) | varies |
| Laterality | Laterality (272741003) | 7771000 / 24028007 / 51440002 |
| Contrast | Using substance (424361007) | 373066001 / 373067005 |

These map directly to `match_property_name()` in `fetcher.py` (TypeIds 0–3).
