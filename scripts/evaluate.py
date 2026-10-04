"""Rebuild the pilot CER table from committed ground truth and predictions."""
import json
from pathlib import Path

from newsrec.domain.page import Page
from newsrec.services.evaluation import evaluate

root = Path("bench/ablation")
truth = json.loads(Path("bench/ground-truth.json").read_text(encoding="utf-8"))
results = []
for run_path in sorted(root.glob("*.run.json")):
    run = json.loads(run_path.read_text(encoding="utf-8"))
    page_path = root / f'{run["config"]}.page.json'
    if "error" not in run and page_path.exists():
        page = Page.from_dict(json.loads(page_path.read_text(encoding="utf-8")))
        run.update(evaluate(page, truth["samples"]))
    results.append(run)
Path("bench/evaluation.json").write_text(json.dumps({"provenance": truth["provenance"], "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
lines = ["# Pilot OCR evaluation", "", truth["provenance"], "", truth["sampling"], "",
         "One-to-one line matching at IoU ≥ 0.5. Unmatched reference lines count as deletions. CER is character-weighted, not averaged per line. Extra predictions outside the sample are not scored. Layout recall here means sampled **line** recall, not article/block mAP. Simplified probes are occurrences of 国华军务台 across the whole prediction, a diagnostic rather than an accuracy score.", "",
         "| Configuration | CER | Errors / reference chars | Matched lines | Prediction time | Simplified probes |", "|---|---:|---:|---:|---:|---:|"]
for row in results:
    if "cer" in row:
        lines.append(f'| {row["config"]} | {row["cer"]:.1%} | {row["errors"]} / {row["reference_characters"]} | {row["matched_lines"]} / {row["sampled_lines"]} | {row["predict_s"]:.2f} s | {sum(row["simplified_probe_counts"].values())} |')
    else:
        lines.append(f'| {row["config"]} | unavailable | — | — | — | — |')
        lines.extend(["", f'{row["config"]}: `{row.get("error", "No prediction")}`'])
lines.extend(["", "## Scores by sampled region", "", "These are layout-aware scores: a missed/mis-segmented line contributes deletions. Dense-body errors must not be read as recognizer-only CER.", "", "| Configuration | Headline CER | Short news CER | Notice CER | Dense body CER |", "|---|---:|---:|---:|---:|"])
for row in results:
    if "cer" not in row:
        continue
    page = Page.from_dict(json.loads((root / f'{row["config"]}.page.json').read_text(encoding="utf-8")))
    scores = [evaluate(page, [s for s in truth["samples"] if s["region"] == region])["cer"] for region in ("headline", "news-body", "notice", "dense-body")]
    lines.append("| " + row["config"] + " | " + " | ".join(f"{score:.1%}" for score in scores) + " |")
lines.extend(["", "The sample is too small and readability-biased to settle the newspaper-wide default. Keep `structure` provisionally; independently review the transcription and expand dense-body samples before changing the default. The committed per-line predictions make every score inspectable.", "", "Reproduce: `uv run --extra gpu parse.py structure <scan>` to place the scan at `data/page.png`, then `uv run --extra gpu scripts/ablation.py` and `uv run scripts/evaluate.py`. Each configuration gets a fresh process, and `--extra gpu` is required on the ablation step: without Paddle every configuration raises, and the failure is reported without overwriting the committed run. Timing includes inference and layout postprocessing but excludes construction; this is a single measured prediction, not a warm-throughput benchmark.", "", f"These scores were measured on `{truth['image']}`, which is not committed -- recover it from commit `a430160`. The bboxes in `bench/ground-truth.json` are meaningless against any other scan.", ""])
Path("bench/EVALUATION.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
