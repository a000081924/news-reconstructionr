"""Isolated evaluation predictions. Leaves the original timing evidence untouched."""
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from newsrec.domain.engines import LEAN
from newsrec.services.recognition import build_pipeline
from newsrec.services.normalization import normalize

CONFIGS = {
    "lean": LEAN,
    "cht_srvdet": {**LEAN, "text_recognition_model_name": "chinese_cht_PP-OCRv3_mobile_rec"},
    "mrec_srvdet": {**LEAN, "text_recognition_model_name": "PP-OCRv5_mobile_rec"},
    **{f"v6_{size}": {**LEAN, "text_detection_model_name": f"PP-OCRv6_{size}_det", "text_recognition_model_name": f"PP-OCRv6_{size}_rec"} for size in ("tiny", "small", "medium")},
}
SCAN = "data/page.png"  # produced by: uv run parse.py structure <image>
root = Path("bench/ablation")
root.mkdir(parents=True, exist_ok=True)


def child(name):
    start = perf_counter()
    try:
        pipeline = build_pipeline("structure", CONFIGS[name])
        construct = perf_counter() - start
        start = perf_counter()
        result = next(iter(pipeline.predict(SCAN)))
        elapsed = perf_counter() - start
        raw = result.json["res"]
        with Image.open(SCAN) as scan:
            width, height = scan.size
        page = normalize(raw, name, width, height, SCAN)
        (root / f"{name}.page.json").write_text(json.dumps(page.to_dict(), ensure_ascii=False), encoding="utf-8")
        report = {"config": name, "construct_s": round(construct, 2), "predict_s": round(elapsed, 2)}
        pipeline.close()
    except Exception as exc:
        # Report the failure but leave the committed run on disk: without a GPU every
        # config raises, and writing that would erase the measurements it stands for.
        print(json.dumps({"config": name, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
        return
    (root / f"{name}.run.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if os.getenv("NEWSREC_ABLATION_CHILD") == "1":
        child(sys.argv[1])
    else:
        for name in sys.argv[1:] or CONFIGS:
            subprocess.run([sys.executable, __file__, name], env={**os.environ, "NEWSREC_ABLATION_CHILD": "1"}, check=True, timeout=600)
