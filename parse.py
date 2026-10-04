"""Run one PaddleOCR page-parsing pipeline on a newspaper scan.

usage: uv run parse.py vl|structure [image]

The scan is normalised once into data/page.png (gitignored); the other offline
tools read that, so pass an image here and they all follow.
"""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent / "src"))
from newsrec.services.recognition import build_pipeline
from newsrec.domain.engines import ENGINES

ROOT = Path(__file__).parent
PAGE = ROOT / "data" / "page.png"


def page_png(source: str = "") -> str:
    """Any dropped scan -> RGB PNG under an ASCII path that cv2.imread can open.

    (A 1-bit TIFF under a non-ASCII filename defeats it on both counts.)
    """
    if source:
        PAGE.parent.mkdir(exist_ok=True)
        Image.open(source).convert("RGB").save(PAGE)
    elif not PAGE.exists():
        sys.exit(f"{PAGE} missing -- pass a scan: uv run parse.py {{engine}} <image>")
    return str(PAGE)


def main(engine: str, source: str = "") -> None:
    if engine not in ENGINES:
        sys.exit("usage: parse.py " + "|".join(ENGINES) + " [image]")
    page = page_png(source)
    pipeline = build_pipeline(engine)

    out = ROOT / "out" / engine
    out.mkdir(parents=True, exist_ok=True)
    for res in pipeline.predict(page):
        res.save_to_json(str(out))
        res.save_to_markdown(str(out))
        res.save_to_img(str(out))
    print(f"wrote {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3]) if len(sys.argv) > 1 else main("")
