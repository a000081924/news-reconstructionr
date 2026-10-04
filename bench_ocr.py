"""Time PP-StructureV3 configurations on the newspaper page.

Separates one-time pipeline construction from per-page inference: a persistent
server pays construction once at startup, so only the warm predict time is what
a user actually waits for.

usage: uv run bench_ocr.py [config ...]
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from newsrec.services.recognition import build_pipeline

ROOT = Path(__file__).parent
PAGE = ROOT / "data" / "page.png"

# Everything a newspaper page never needs. The baseline loads all of it.
OFF = dict(use_table_recognition=False, use_formula_recognition=False,
           use_seal_recognition=False, use_chart_recognition=False,
           use_doc_unwarping=False)

CONFIGS = {
    "baseline":    dict(use_textline_orientation=True),
    "lean":        dict(use_textline_orientation=True, text_recognition_batch_size=32,
                        textline_orientation_batch_size=32, **OFF),
    "lean_noori":  dict(use_textline_orientation=False, text_recognition_batch_size=32, **OFF),
    "mobile":      dict(use_textline_orientation=True, text_recognition_batch_size=32,
                        textline_orientation_batch_size=32,
                        text_detection_model_name="PP-OCRv5_mobile_det",
                        text_recognition_model_name="PP-OCRv5_mobile_rec", **OFF),
    "cht":         dict(use_textline_orientation=True, text_recognition_batch_size=32,
                        textline_orientation_batch_size=32,
                        text_detection_model_name="PP-OCRv5_mobile_det",
                        text_recognition_model_name="chinese_cht_PP-OCRv3_mobile_rec", **OFF),
    # Isolate the recogniser: keep the server detector's line recall, swap only rec.
    "cht_srvdet":  dict(use_textline_orientation=True, text_recognition_batch_size=32,
                        textline_orientation_batch_size=32,
                        text_recognition_model_name="chinese_cht_PP-OCRv3_mobile_rec", **OFF),
    "mrec_srvdet": dict(use_textline_orientation=True, text_recognition_batch_size=32,
                        textline_orientation_batch_size=32,
                        text_recognition_model_name="PP-OCRv5_mobile_rec", **OFF),
}


def page_png() -> str:
    if not PAGE.exists():
        sys.exit(f"{PAGE} missing -- run: uv run parse.py structure <image>")
    return str(PAGE)


def run(name: str, kwargs: dict, repeats: int) -> dict:
    t0 = time.perf_counter()
    pipeline = build_pipeline("structure", kwargs)
    construct = time.perf_counter() - t0

    src, predicts, res = page_png(), [], None
    for _ in range(repeats):
        t0 = time.perf_counter()
        res = list(pipeline.predict(src))[0]
        predicts.append(time.perf_counter() - t0)

    d = res.json["res"] if hasattr(res, "json") else {}
    ocr = d.get("overall_ocr_res", {})
    texts = list(ocr.get("rec_texts", []))
    (ROOT / "bench" / f"{name}.json").write_text(
        json.dumps({"texts": texts}, ensure_ascii=False, indent=1), encoding="utf-8")

    return {"config": name, "construct_s": round(construct, 1),
            "cold_s": round(predicts[0], 1), "warm_s": round(predicts[-1], 1),
            "blocks": len(d.get("parsing_res_list", [])), "lines": len(texts),
            "chars": sum(len(t) for t in texts)}


def main(names: list[str]) -> None:
    (ROOT / "bench").mkdir(exist_ok=True)

    # One config per process. Constructing several pipelines in one process leaves the
    # earlier models resident, so later configs time under VRAM pressure they would
    # never see in the server -- the first run measured 29s and 75s for near-identical work.
    if os.environ.get("BENCH_CHILD") != "1":
        import subprocess
        results = []
        for name in names or CONFIGS:
            print(f"\n=== {name} ===", flush=True)
            one = ROOT / "bench" / f"{name}.result.json"
            # Cleared here, not in the child: a child that dies on import or is killed for
            # VRAM never runs its own cleanup, and its predecessor's numbers would be read
            # back as this run's.
            one.unlink(missing_ok=True)
            proc = subprocess.run([sys.executable, __file__, name],
                                  env={**os.environ, "BENCH_CHILD": "1"})
            results.append(json.loads(one.read_text(encoding="utf-8")) if one.exists()
                           else {"config": name, "error": f"exit {proc.returncode}"})
            # Partial runs are normal -- results.json is whichever configs you asked for --
            # but a failed one must not replace the committed timings with its error.
            if not any("error" in r for r in results):
                (ROOT / "bench" / "results.json").write_text(
                    json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        report(results)
        return

    name = names[0]
    try:
        # Baseline is slow and only needs a before-number; others get a warm run.
        result = run(name, CONFIGS[name], 1 if name == "baseline" else 2)
    except Exception as exc:
        result = {"config": name, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    (ROOT / "bench" / f"{name}.result.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8")


def report(results: list[dict]) -> None:

    print("\n config          construct  cold   warm  blocks lines chars")
    for r in results:
        if "error" in r:
            print(f" {r['config']:<15} {r['error']}")
        else:
            print(f" {r['config']:<15} {r['construct_s']:>7}s {r['cold_s']:>6}s"
                  f" {r['warm_s']:>6}s {r['blocks']:>6} {r['lines']:>5} {r['chars']:>6}")


if __name__ == "__main__":
    main(sys.argv[1:])
