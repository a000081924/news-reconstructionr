"""Engine JSON -> one page.json the viewer understands.

usage: uv run normalize.py vl|structure
"""

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
PAGE = ROOT / "data" / "page.png"


sys.path.insert(0, str(ROOT / "src"))
from newsrec.services.normalization import normalize, unrotate


def main(engine: str) -> None:
    out = ROOT / "out" / engine
    src = out / "page_res.json"
    if not src.exists():
        sys.exit(f"{src} missing -- run: uv run parse.py {engine}")
    d = json.loads(src.read_text(encoding="utf-8"))
    w, h = Image.open(PAGE).size

    page = normalize(d, engine, w, h, "data/page.png").to_dict()
    blocks = page["blocks"]
    angle = page["angle"]
    orphans = [line for block in blocks if block["label"] == "unassigned" for line in block["lines"]]
    (out / "page.json").write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    lines = sum(len(b["lines"]) for b in blocks)
    print(f"{out/'page.json'}: {len(blocks)} blocks, {lines} lines, "
          f"{len(orphans)} unassigned lines, angle={angle}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
