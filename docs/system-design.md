# Newspaper Reconstruction: System Requirements and Design

## 1. Architecture diagram

![System architecture](architecture.png)

## 2. System overview and component interactions

The system reads scanned historical newspapers. An archivist drops in a page image, watches recognition arrive region by region, corrects what the recogniser got wrong, and exports the result. It targets dense vertical Traditional Chinese broadsheets (the reference page is a 1946 edition, 35.7 megapixels) and accepts any scan.

Two constraints shaped nearly every decision: there is one GPU and many uploads, and every upload arrives from outside the trust boundary.

Four tiers interact. In the browser, `api.ts` is the only module aware of backend URLs. The FastAPI tier terminates HTTP and runs the upload guards. The recognition tier owns the GPU: an `asyncio.Queue` feeds one consumer task calling a single-threaded executor that holds one resident Paddle pipeline. The persistence tier keeps SQLite metadata beside UUID-named blobs.

`PPStructureV3.predict()` is one atomic call yielding nothing until it finishes, so `services/recognition.py` drives the PaddleX sub-models directly and emits a stage as each completes. Layout boxes arrive in about three seconds and are drawn over the scan the browser already holds, so the page is legible long before recognition ends. Stages are appended to the repository and published on a per-job bus the SSE endpoint reads, so a mid-run refresh reconnects with `Last-Event-ID` rather than orphaning the job. Corrections are records against `(page, engine, block_id, line_index)`, not a rewritten page, so recognition output stays immutable.

## 3. Module breakdown

| Module | Input | Output | Methodology |
|---|---|---|---|
| `domain/page.py` | Page dict | `Page`/`Block`/`Line`/`BBox` | Frozen dataclasses; rejects duplicate ids or order, scores outside [0,1], boxes outside the page, unverified rotations |
| `domain/engines.py` | — | `EngineSpec` registry | Single source of engine truth; `lean` kwargs disable five unused model families |
| `domain/document.py` | — | `Document`, `PageRef`, `JobStatus` | Plain value objects, standard library only |
| `services/ingestion.py` | Uploaded bytes | Full PNG + 800 px thumbnail | Size cap, PIL `verify()`, pixel bound, single-frame check, EXIF transpose, RGB conversion |
| `services/recognition.py` | Normalised image path | Generator of stage events | Drives PaddleX sub-models one at a time; sole Paddle import boundary |
| `services/normalization.py` | Raw PaddleX result | Validated `Page` | Unrotates coordinates, assigns lines by centre containment, parks unordered blocks last, keeps uncovered lines as `unassigned` |
| `services/corrections.py` | `Page` + edit list | Corrected `Page` | Applies edits by index, rebuilds `block.text`, rejects duplicates and unknown blocks |
| `services/export.py` | Corrected `Page` | HTML / ALTO v4 / PAGE-XML | ElementTree serialisation with per-line coordinates and reading order |
| `services/evaluation.py` | `Page` + ground truth | CER, line recall, per-line detail | NFC normalisation, Levenshtein distance, greedy one-to-one IoU matching |
| `services/workspace.py` | Route calls | Façade results | Thin orchestration over repository and services; computes the content address |
| `repository/db.py` | Domain objects | Rows and blobs | SQLite with foreign keys; content-hash unique index; UUID blob names; monotonic event sequence |
| `workers/queue.py` | Job requests | Persisted stage events | One consumer task, `max_workers=1` executor, engine swapping, queue-position broadcast |
| `workers/bus.py` | Job id | `asyncio.Event` signals | Per-job subscriber sets woken on publish |
| `api/app.py` | HTTP requests | JSON, SSE, files | FastAPI routes, Pydantic validation, lifespan-scoped worker, static frontend mount |
| `api/limits.py` | ASGI scope | 413 or pass-through | Bounds `content-length` and streamed body before multipart parsing |
| `lib/api.ts` | UI calls | Typed responses | Sole URL boundary; `fetch` plus `EventSource` |
| `lib/render/layout.ts` | Text + box | Glyph commands | Bisection on glyph size; pure and unit-tested, no DOM |
| `App.svelte` + components | User actions | Rendered workbench | Svelte 5 runes, `localStorage` session, stage-driven progressive rendering |

## 4. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Accept a scanned image, validate it, normalise it to RGB PNG and store it with a thumbnail |
| FR-2 | Address content by digest so a re-uploaded scan reuses its stored recognition |
| FR-3 | List engines with enabled and loaded state; let the user select any interactive one |
| FR-4 | Queue a recognition job per page and reject a second concurrent job for that page |
| FR-5 | Stream stage events over SSE with monotonic ids and resume after disconnection |
| FR-6 | Reconstruct the page as ordered blocks and lines mapped back onto the original scan |
| FR-7 | Draw recognised regions over the scan and render the reconstruction beside it |
| FR-8 | Persist per-line corrections and restore recognised text on undo |
| FR-9 | Export the corrected page as HTML, ALTO v4 or PAGE-XML |
| FR-10 | List, fetch and delete documents, refusing deletion while a job is active |
| FR-11 | Score recognition against hand-transcribed ground truth and report CER per line |

## 5. Non-functional requirements

| ID | Category | Requirement and design consequence |
|---|---|---|
| NFR-1 | Performance | Layout on screen in ~3.2 s cold, 0.9 s warm; full page ~37.6 s. `lean` drops seven unused models, cutting eight minutes to forty with identical output |
| NFR-2 | Scalability | Inference is blocking and VRAM-bound, so one consumer drains the queue and pipelines are built once at startup. Users queue and see their position |
| NFR-3 | Reliability | Job state is persisted, not held in the stream. A restart marks in-flight jobs errored; a refresh reconnects rather than orphaning work |
| NFR-4 | Security | A 50 MiB cap applies before multipart spooling, then `verify()`, a pixel bound, single-frame rejection, and UUID storage names |
| NFR-5 | Portability | Paddle is imported only inside `services/recognition.py`, so the API, the tests and CI run with no GPU installed |
| NFR-6 | Usability | The page is legible before recognition finishes; WebGL2 is optional; session state survives a reload |
| NFR-7 | Maintainability | Dependencies run one way, `api → services → repository → domain`; `domain` imports only the standard library |
| NFR-8 | Privacy | SQLite and blobs live under a gitignored `.runtime/`, so no scan reaches version control |
| NFR-9 | Integrity | Recognition output is immutable; a new run clears that engine's corrections, because line indices belong to one run |

## 6. Design notes

**The page is rotated before recognition.** StructureV3 turns it 90° counter-clockwise so horizontal-text models can read vertical columns, and `unrotate` maps coordinates back. Only 0° and 90° are verified; any other angle raises rather than silently misplacing every block.

**Uncovered text stays visible.** Fifty-three of 577 recognised lines fall outside every detected block. They are kept under an `unassigned` label instead of being dropped.

**Character count is not accuracy.** One configuration emits the most characters yet scores worse on CER, because some of those characters are hallucinated on non-text regions.

### Known limitations

One page per document, no authentication, no multi-user support, and no cancelling a queued job. Dense-body column merging is unsolved and remains the largest accuracy lever.

