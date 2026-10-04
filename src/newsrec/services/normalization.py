from newsrec.domain.page import Page


def unrotate(angle: int, w: int, h: int):
    """Map a bbox from the preprocessor's rotated frame back onto the original scan.

    The doc-orientation model turns this vertical-Chinese page CCW by 90 so the
    horizontal-text recogniser can read the columns; we undo that. Only 0 and 90 are
    verified against the scan -- anything else should fail loudly rather than silently
    misplace every block.
    """
    if angle == 0:
        return lambda b: [b[0], b[1], b[2], b[3]]
    if angle == 90:
        return lambda b: [w - b[3], b[0], w - b[1], b[2]]
    raise NotImplementedError(f"rotation {angle} not verified; check a crop first")


def normalize(d: dict, engine: str, w: int, h: int, image: str = "") -> Page:
    angle = d.get("doc_preprocessor_res", {}).get("angle", 0)
    if (d["width"], d["height"]) == (w, h):
        angle = 0
    fix = unrotate(angle, w, h)

    # block_order is 1..N over the blocks that got one; the rest (mastheads, page
    # furniture) carry None. block_id is a different numbering space, so falling back
    # to it would interleave the two and scramble the reading order -- park the
    # unordered blocks after the ordered ones instead.
    nxt = max((b["block_order"] for b in d["parsing_res_list"]
               if b["block_order"] is not None), default=0)
    blocks = []
    for b in d["parsing_res_list"]:
        order = b["block_order"]
        if order is None:
            nxt += 1
            order = nxt
        blocks.append({
            "id": b["block_id"],
            "order": order,
            "label": b["block_label"],
            "bbox": fix(b["block_bbox"]),
            "text": b["block_content"],
            "lines": [],
        })

    # Text lines are page-level, not nested under blocks: attach each to the block
    # whose (rotated-frame) box contains its centre.
    ocr = d.get("overall_ocr_res", {})
    orphans = []
    for box, text, score in zip(ocr.get("rec_boxes", []), ocr.get("rec_texts", []),
                                ocr.get("rec_scores", [])):
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        line = {"bbox": fix(box), "text": text, "score": round(score, 3)}
        for raw, blk in zip(d["parsing_res_list"], blocks):
            x1, y1, x2, y2 = raw["block_bbox"]
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                blk["lines"].append(line)
                break
        else:
            orphans.append(line)

    # Recognised text the layout model left uncovered. Kept, but labelled so the
    # gap stays visible instead of silently disappearing from the reconstruction.
    if orphans:
        xs = [c for l in orphans for c in (l["bbox"][0], l["bbox"][2])]
        ys = [c for l in orphans for c in (l["bbox"][1], l["bbox"][3])]
        blocks.append({
            "id": max((b["id"] for b in blocks), default=-1) + 1, "order": max((b["order"] for b in blocks), default=0) + 1,
            "label": "unassigned", "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "text": "\n".join(l["text"] for l in orphans), "lines": orphans,
        })

    # Lines arrive in detection order; within a block, read top-to-bottom then right-to-left.
    for blk in blocks:
        blk["lines"].sort(key=lambda l: (-l["bbox"][2], l["bbox"][1]))
    blocks.sort(key=lambda b: b["order"])

    orders = [b["order"] for b in blocks]
    assert len(orders) == len(set(orders)), f"duplicate reading-order indices: {len(orders)-len(set(orders))}"
    assert all(0 <= b["bbox"][0] < b["bbox"][2] <= w and 0 <= b["bbox"][1] < b["bbox"][3] <= h
               for b in blocks), "bbox outside page after unrotation"

    page = {"engine": engine, "width": w, "height": h, "image": image,
            "angle": angle, "blocks": blocks}
    return Page.from_dict(page)
