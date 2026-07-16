# SNOMED CT Radiology Procedure Deconstructor

A small Flask web app that shows the two-way relationship between a
**precoordinated** SNOMED CT radiology procedure and the **semantic components**
it is built from. It talks to a FHIR terminology server (Ontoserver by default)
to expand valuesets, look up concept properties, and evaluate ECL expressions.

Every precoordinated procedure is broken down into four axes:

| Axis | SNOMED qualifier | Example |
| --- | --- | --- |
| **Procedure / Modality** | Method (`260686004`) | Computerized axial tomography |
| **Body Site** | Procedure site (`405813007`) | Chest |
| **Laterality** | Laterality (`272741003`) | Left / Right / Bilateral |
| **Use of Contrast** | Using substance (`424361007`) | With / Without contrast |

## What it does

The UI has two panels backed by the same in-memory *concept map*:

- **← Decompose** — pick a precoordinated code and see its four axes.
- **Compose →** — choose components (procedure, body site, laterality, contrast)
  and find the precoordinated code that matches. When several codes match, you
  pick the intended concept from a list.

Selecting on either side keeps the other in sync.

## How it works

`map_builder.build_concept_map()` drives the terminology work for a given
`(valueset, terminology server)` combo:

1. **Expand** the configured valueset (`ValueSet/$expand`) to get every
   precoordinated procedure code.
2. For each concept, **look up** its defining relationships
   (`CodeSystem/$lookup?property=*`) and sort them into the four axes.
3. **De-lateralise** body sites (find the proximal primitive parent via ECL) and
   infer laterality from left/right body-structure membership.
4. **Map** each concept up its ancestor hierarchy to a *focus procedure*
   (the base modality) listed in [`procedures.txt`](procedures.txt).
5. Concepts where all four axes resolve are kept; the rest are skipped.

The resulting concept map is cached to disk as one JSON file per combo
(`cache/<valueset>__<server>.json`) so subsequent starts are instant and don't
hit the terminology server.

## Project layout

| File | Purpose |
| --- | --- |
| [`app.py`](app.py) | Flask app, routes, background-refresh bookkeeping, bootstrap |
| [`map_builder.py`](map_builder.py) | Builds, caches, and loads the concept map |
| [`fetcher.py`](fetcher.py) | Low-level FHIR terminology calls ($expand, $lookup, ECL) |
| [`config.py`](config.py) | Loads `config.yaml` over built-in defaults |
| [`config.yaml`](config.yaml) | Terminology servers, valuesets, defaults, cache/Flask settings |
| [`helpers.py`](helpers.py) | File and resource-validation helpers |
| [`procedures.txt`](procedures.txt) | Focus procedures used to identify the base modality |
| [`templates/index.html`](templates/index.html) | Single-page UI (Bootstrap + vanilla JS) |
| [`render.yaml`](render.yaml) | Render.com deployment config |
| `cache/` | Generated concept-map JSON files (one per combo) |

## Getting started

Requires Python 3.9+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
# Serve using whatever cached concept maps already exist under cache/
python app.py

# Build the default valueset/server combo's cache first, then serve
python app.py --refresh

# Use a different config file
python app.py --config my-config.yaml
```

Then open http://localhost:5000.

The first time you run it there is no cache, so a combo shows *"Not built yet"*.
Tick **Refresh cache** in the UI (or start with `--refresh`) to build it from the
terminology server — this can take a while as it looks up every concept in the
valueset.

## Configuration

[`config.yaml`](config.yaml) defines the terminology servers and valuesets that
appear in the UI dropdowns, plus defaults and cache/Flask settings. Any missing
key falls back to the defaults in [`config.py`](config.py). Highlights:

- `terminology_servers` / `valuesets` — the selectable combos.
- `default_valueset` / `default_terminology_server` — selected on startup and
  used by `--refresh`.
- `cache_dir`, `cache_enabled` — where concept-map JSON is written, and whether
  cached maps are loaded at all.
- `flask_debug`, `flask_port` — local dev server settings.

The set of focus procedures used to identify the base modality lives in
[`procedures.txt`](procedures.txt) — edit it to match the procedures in your
valueset.

## API

The UI is driven by a small JSON API:

| Route | Description |
| --- | --- |
| `GET /` | Main UI |
| `GET /api/valuesets` | Configured valuesets / terminology servers + defaults |
| `GET /api/concept-map` | Concept map for a `(vs, server)` combo |
| `GET /api/preloaded-options` | Compose-panel dropdown options for a combo |
| `POST /api/refresh` | Kick off a background rebuild of a combo |
| `GET /api/refresh-status` | Poll a combo's background rebuild status |
| `GET /api/status` | Readiness check |

Combo selection is via `?vs=<valueset_id>&server=<server_id>` query params,
falling back to the configured defaults.

## Deployment

The app is a standard WSGI application (`app:app`). [`render.yaml`](render.yaml)
deploys it on Render.com with gunicorn:

```bash
gunicorn -w 1 --bind 0.0.0.0:$PORT app:app
```

Because `app.py` bootstraps at import time, a WSGI server picks up the `app`
object directly (it never calls `main()`). Two environment variables control
startup:

- `CONFIG_FILE` — path to the YAML config (default `config.yaml`).
- `REFRESH_ON_START` — set to `1`/`true`/`yes` to rebuild the default combo's
  cache on boot.

A single worker (`-w 1`) is used so the in-memory concept map and refresh lock
are shared across requests.
