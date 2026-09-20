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
