# Newspaper reconstruction

A workbench for reading scanned historical newspapers. Drop in a scan, watch the page being
recognised region by region, then read, correct and export the result.

upload → queued GPU recognition → streamed stages → reconstruction → persisted corrections → export

Built for dense vertical Traditional Chinese broadsheets, though it will take any scan you give
it. The reference page is a 1946 edition at 5079×7029, 1-bit, 300 dpi (35.7 MP).

No scans are distributed with this repository. Uploads are content-addressed: an image is
hashed after normalisation, so dropping the same page in again reuses its stored recognition
and corrections instead of spending another GPU run. That cache (SQLite metadata plus image
blobs) lives under `.runtime/` and is gitignored, so nobody's newspaper reaches version
control.

## Quickstart

```bash
uv sync                      # API and tests; no GPU, no Paddle
uv sync --extra gpu          # adds paddleocr + paddlepaddle-gpu (cu118)

cd frontend && bun install && bun run build && cd ..
uv run --extra gpu uvicorn newsrec.api.app:app --port 8000
# http://127.0.0.1:8000/   — serves the built frontend from the same origin
```

For frontend work, `bun run dev` proxies the API to `127.0.0.1:8000`.

| variable | default | meaning |
|---|---|---|
| `NEWSREC_DATA` | `.runtime` | SQLite file and blob storage root |
| `NEWSREC_ENGINE` | `structure` | engine preloaded at startup: `structure`, `cht`, or `none` (runs without a GPU) |

You can choose any interactive engine from the UI. Only one is resident at a time, since two
server recognisers do not fit an 8 GB card. Picking another swaps the models, which the job
reports as a `loading` stage before recognition starts. `NEWSREC_ENGINE` only decides which one
is warm from the first request; `none` disables recognition entirely and still serves saved
pages.

## How it works

`PPStructureV3.predict()` is a single atomic call that yields nothing until it finishes, so
`services/recognition.py` drives the PaddleX sub-models directly and emits stages as they
complete:

```
queued → [loading] → preprocessed → layout → lines → done
```

Layout boxes reach the browser in about three seconds and are drawn over the scan the browser
already holds, so the page is legible long before recognition finishes. Job state lives in the
repository and the SSE stream is a view over it: a refresh mid-run reconnects with
`Last-Event-ID` rather than orphaning the job.

Corrections are stored as records against `(page, engine, block_id, line_index)` rather than as
a rewritten page document. Recognition output stays immutable and the diff stays inspectable.

## Architecture

Dependencies run one way only: `api → services → repository → domain`. `domain` imports
nothing but the standard library, and Paddle is imported *only* inside
`services/recognition.py`, so the API, the tests and CI all run on a machine with no GPU and no
Paddle installed.

```
src/newsrec/
├─ domain/       page.py (Page/Block/Line/BBox, SCHEMA_VERSION) · document.py · engines.py
├─ services/     ingestion · recognition · normalization · corrections · evaluation · export · workspace
├─ repository/   db.py — SQLite metadata, content-hashed, UUID-named filesystem blobs
├─ workers/      queue.py (single GPU consumer) · bus.py (per-job SSE fan-out)
└─ api/          app.py · schemas.py · limits.py
frontend/        Svelte 5 + Vite + Bun
├─ src/lib/api.ts              the only module that knows backend URLs
├─ src/lib/render/layout.ts    fitRuns + drawText, pure and unit-tested
└─ src/lib/render/blur-gl.ts   WebGL blur pipeline
```

`engines.py` is the single source of engine truth, and `schemas/page.schema.json` is the
generated JSON Schema for the page contract.

Two constraints shape the rest:

- **One GPU, many uploads.** Paddle inference is blocking and VRAM-bound, so running it in the
  default threadpool would exhaust an 8 GB card on two concurrent uploads. A single consumer
  task drains an `asyncio.Queue`; pipelines are constructed once in the FastAPI `lifespan` hook
  and held in VRAM. Concurrent users queue and see their position.
- **Uploads are untrusted.** A 50 MiB cap is enforced by ASGI middleware *before* multipart
  spooling, followed by PIL `verify()`, a bounded `MAX_IMAGE_PIXELS`, storage names never
  derived from the uploaded filename, and normalisation to RGB PNG on ingest.

## HTTP API

```
POST   /api/documents                  multipart → {document_id, page_id, cached}
GET    /api/documents                  list
GET    /api/documents/{id}
DELETE /api/documents/{id}
POST   /api/pages/{id}/recognize       {engine} → {job_id}
GET    /api/jobs/{id}                  status snapshot, for reconnect
GET    /api/jobs/{id}/events           SSE stream
GET    /api/pages/{id}?engine=         page JSON, corrections merged in
GET    /api/pages/{id}/image           full PNG
GET    /api/pages/{id}/thumbnail
GET    /api/pages/{id}/corrections     saved edits for this page and engine
PUT    /api/pages/{id}/corrections     persisted
DELETE /api/pages/{id}/corrections     restore recognised text
GET    /api/pages/{id}/export?format=html|alto|page-xml
GET    /api/engines
```

## Offline CLI

PaddleOCR-VL needs 21-35 min/page on Windows (no vLLM, so decoding is eager and
autoregressive), which is why it is not offered interactively:

```bash
uv run --extra gpu parse.py structure path/to/scan.tif   # normalises to data/page.png, then runs
uv run --extra gpu parse.py vl                           # reuses data/page.png
uv run --extra gpu normalize.py vl                       # -> out/vl/page.json
```

`parse.py` is the only tool that takes a source image; it normalises the scan once into
`data/page.png` (gitignored), and `normalize.py`, `bench_ocr.py` and `scripts/` read that.

## Tests

```bash
uv run pytest                              # 12 tests, no GPU required
cd frontend && bun test && bun run check   # pure layout tests, no DOM stubs
```

The suite runs with Paddle absent, verified in a CPU-only environment where
`importlib.util.find_spec('paddle')` is `None`. `scripts/verify_api_gpu.py` exercises the full
HTTP, worker and persistence path against a real GPU and writes `bench/api-verification.json`.

## Performance

RTX 3070, Windows 11, CUDA 12.2 driver, cu118 build. Measured, not estimated.

| stage | cold | warm |
|---|---:|---:|
| pipeline construction | 10.7 s | n/a (held in VRAM) |
| layout boxes on screen | 3.2 s | 0.9 s |
| `done`, page saved | 37.6 s | 40.6-43.3 s |

PP-StructureV3 loads 13 models for a newspaper page by default, including six table models,
`PP-FormulaNet_plus-L`, and `UVDoc` page-dewarping on a flatbed scan. The `lean` configuration
switches off the seven this workload never uses. That cuts a page from about 8 min to about
40 s, with identical output: 77 blocks and 577 lines either way. Evidence in
`bench/results.json` and `bench/api-verification.json`.

End-to-end browser verification (`bench/screenshots/`): a scan uploaded, 87 layout regions drawn
at 3.7 s, `done` at 40.6 s with 77 blocks and 577 lines, a headline corrected to 哈利曼爲商部長,
and the correction still present after a browser reload and in all three exports. Re-dropping
the same scan returned its stored 77-region result immediately, leaving one document, one page
and one pair of blobs in the database.

## Accuracy

`bench/EVALUATION.md` reports pilot CER over a 262-character hand-transcribed sample across four
spatially separated strata, with per-region scores and committed per-line predictions.

**The sample does not settle the default recognizer.** `lean` scores best overall (67.9% CER),
but every configuration scores 100% CER on dense body text because the detector merges columns
across printed separators, a *layout* failure charged to recognition. `structure` is therefore
the provisional default. Character count is not accuracy: `cht_srvdet` produces the most
characters and no simplified leakage, yet scores worse than `lean`, because some of those
characters are hallucinated on non-text regions.

The ground truth was transcribed by an AI assistant from source crops and is *not*
independently human-reviewed; `bench/ground-truth.json` records that provenance.

## Design notes

- **The page is rotated before recognition.** StructureV3 turns the page 90° CCW
  (`doc_preprocessor_res.angle`) so its horizontal-text models can read vertical columns;
  `normalization.unrotate` maps the coordinates back. Only 0° and 90° are verified against a
  scan; any other angle raises rather than silently misplacing every block on the page.
- **The detector drives line recall; the recognizer drives script fidelity.** Swapping only the
  recognizer holds detections at 577-579; swapping the detector to mobile drops them to 485.
- **Uncovered text stays visible.** 53 of 577 recognised lines (9%) fall outside every detected
  block. They are kept under a distinct `unassigned` label instead of being dropped, so the
  layout gap can be inspected.
- **The streamed `lines` stage reports fewer lines (~448) than the finished page (577).** Layout
  parsing re-recognises regions the page-level pass missed. The lower count is an accurate
  snapshot of that moment, not lines that went missing.
- **`block_order` is not `block_id`.** Only some blocks get a reading order; the rest carry
  `None` and must not fall back to `block_id`, which is a different numbering space and would
  scramble the order.
- **Glyph sizing is bisected.** 99% of the page is full-width CJK, so one character advances
  exactly one em and the fit is pure arithmetic with no text measurement. A multiplicative
  decay search undershoots by up to one step (median 4.2%, max 8.0%, 37% of lines off by more
  than 5%); bisection lands on the boundary exactly, with a worst-case fill ratio of 1.0000 and
  zero overflow across 473 lines.
- **WebGL2 is optional.** Without it, the scan and the recognised text still render.

## Limitations

- One page per document; no auth, no multi-user.
- A queued recognition cannot be cancelled: there is one GPU consumer and the job is short.
- Dense-body column merging is unsolved and is the largest accuracy lever available.
- PaddleOCR-VL is offline-only on Windows until vLLM is available to it.
