# Pilot OCR evaluation

Visually transcribed by the coding assistant from the source scan crops on 2026-09-17; not independently human-reviewed. Pilot sample, not full-page ground truth.

Four spatially separated strata: large international-news headline, one complete short veterans news item, public-notice heading/closing, and 16 physical text columns from two adjacent rows of dense government news. Column boxes follow the printed horizontal separator, not the detector merges. Legible regions selected visually; not a random/full-page sample.

One-to-one line matching at IoU ≥ 0.5. Unmatched reference lines count as deletions. CER is character-weighted, not averaged per line. Extra predictions outside the sample are not scored. Layout recall here means sampled **line** recall, not article/block mAP. Simplified probes are occurrences of 国华军务台 across the whole prediction, a diagnostic rather than an accuracy score.

| Configuration | CER | Errors / reference chars | Matched lines | Prediction time | Simplified probes |
|---|---:|---:|---:|---:|---:|
| cht_srvdet | 75.6% | 198 / 262 | 12 / 29 | 26.99 s | 1 |
| lean | 67.9% | 178 / 262 | 12 / 29 | 29.00 s | 16 |
| mrec_srvdet | 72.5% | 190 / 262 | 12 / 29 | 23.77 s | 27 |
| v6_medium | 85.9% | 225 / 262 | 12 / 29 | 21.70 s | 35 |
| v6_small | 68.3% | 179 / 262 | 12 / 29 | 20.66 s | 11 |
| v6_tiny | 76.0% | 199 / 262 | 25 / 29 | 9.00 s | 16 |

## Scores by sampled region

These are layout-aware scores: a missed/mis-segmented line contributes deletions. Dense-body errors must not be read as recognizer-only CER.

| Configuration | Headline CER | Short news CER | Notice CER | Dense body CER |
|---|---:|---:|---:|---:|
| cht_srvdet | 36.0% | 31.8% | 72.7% | 100.0% |
| lean | 12.0% | 12.1% | 63.6% | 100.0% |
| mrec_srvdet | 24.0% | 24.2% | 72.7% | 100.0% |
| v6_medium | 100.0% | 51.5% | 54.5% | 100.0% |
| v6_small | 28.0% | 13.6% | 27.3% | 100.0% |
| v6_tiny | 68.0% | 22.7% | 63.6% | 100.0% |

The sample is too small and readability-biased to settle the newspaper-wide default. Keep `structure` provisionally; independently review the transcription and expand dense-body samples before changing the default. The committed per-line predictions make every score inspectable.

Reproduce: `uv run --extra gpu parse.py structure <scan>` to place the scan at `data/page.png`, then `uv run --extra gpu scripts/ablation.py` and `uv run scripts/evaluate.py`. Each configuration gets a fresh process, and `--extra gpu` is required on the ablation step: without Paddle every configuration raises, and the failure is reported without overwriting the committed run. Timing includes inference and layout postprocessing but excludes construction; this is a single measured prediction, not a warm-throughput benchmark.

These scores were measured on `台灣民報_25Sep1946_P.1.tif`, which is not committed -- recover it from commit `a430160`. The bboxes in `bench/ground-truth.json` are meaningless against any other scan.
