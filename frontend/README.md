# Newspaper workbench

From this directory, run `bun install`, then `bun run dev`. Vite proxies the API to
the backend on `127.0.0.1:8000`. Run `bun run build` before starting the backend to
serve this application's production bundle from the same origin.

Checks: `bun run check`, `bun test`, `bun run build`.

Upload a scan, select an enabled engine and choose **Recognize**. Real layout and
recognized-line events appear over the scan. TIFF previews become available after
server normalization. Select a text region, edit its lines and choose **Save
correction**. Corrections are stored by the backend and included in each export.
**Undo all page edits** restores OCR text and permits another recognition run.

The selected page, engine, region and active job identifier are stored locally.
Reloading reconstructs a running job from its persisted snapshot and resumes SSE
after the last event. View controls include fit page/width, zoom, blur and
**Compare**, which puts a divider on the page itself: drag its handle to wipe
between the original scan and the reconstruction. The divider is a real slider —
focus it and use arrow keys (Shift for ten-point steps), Home for all
reconstruction, End for all original. WebGL2 is optional: if it is unavailable,
the original scan and recognized text remain visible.

`src/lib/api.ts` owns the HTTP contract. `render/layout.ts` generates pure glyph
commands tested without DOM stubs. `render/blur-gl.ts` scopes and disposes its own
WebGL resources. The components use Svelte 5 runes; canvas,
image-loading and ResizeObserver effects bridge browser APIs and clean up on
replacement/unmount.
