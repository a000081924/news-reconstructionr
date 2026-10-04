"""The sole Paddle import boundary. Two real stages, using the existing parser.

The adapter targets the pinned PaddleOCR/PaddleX API. Layout and OCR run separately;
Paddle's own layout postprocessor retains its reading-order and block-merging logic.
"""
import os
import sys
from pathlib import Path
from time import perf_counter
from typing import Iterator, Protocol

from newsrec.domain.engines import ENGINES
from newsrec.services.normalization import normalize, unrotate

_DLL_HANDLES = []


def build_pipeline(engine, kwargs=None):
    if os.name == "nt" and not _DLL_HANDLES:
        for directory in Path(sys.prefix, "Lib", "site-packages", "nvidia").glob("*/bin"):
            _DLL_HANDLES.append(os.add_dll_directory(str(directory)))
    if engine == "vl":
        from paddleocr import PaddleOCRVL
        return PaddleOCRVL()
    from paddleocr import PPStructureV3
    return PPStructureV3(**(kwargs if kwargs is not None else ENGINES[engine].pipeline_kwargs))


class OCREngine(Protocol):
    def recognize(self, image_path: str) -> Iterator[dict]: ...


class PaddleEngine:
    def __init__(self, engine="structure"):
        if not ENGINES[engine].interactive:
            raise ValueError("VL is offline-only; use parse.py vl")
        self.engine = engine
        self.wrapper = build_pipeline(engine)
        self.pipeline = self.wrapper.paddlex_pipeline
        # PaddleX wraps the concrete pipeline for device/batch scheduling.
        if hasattr(self.pipeline, "_pipeline"):
            self.pipeline = self.pipeline._pipeline

    def close(self):
        self.wrapper.close()

    def recognize(self, image_path):
        import cv2
        p = self.pipeline
        start = perf_counter()
        def event(stage, **data):
            return {"stage": stage, "elapsed_ms": round((perf_counter() - start) * 1000), **data}
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError("cannot read normalized image")
        h, w = image.shape[:2]
        pre = next(iter(p.doc_preprocessor_pipeline([image], use_doc_unwarping=False)))
        rotated = pre["output_img"]
        angle = pre.get("angle", 0)
        fix = unrotate(angle, w, h)
        yield event("preprocessed", angle=angle)
        layout = next(iter(p.layout_det_model([rotated])))
        yield event("layout", width=w, height=h, blocks=[
            {"id": i, "bbox": [float(v) for v in fix(box["coordinate"])], "label": box["label"]}
            for i, box in enumerate(layout["boxes"])
        ])
        region = next(iter(p.region_detection_model([rotated], layout_nms=True, layout_merge_bboxes_mode="small")))
        ocr = next(iter(p.general_ocr_pipeline([rotated], use_textline_orientation=True)))
        ocr["rec_labels"] = ["text"] * len(ocr["rec_texts"])
        # Page-level detections only (~448 here). get_layout_parsing_res below re-recognises
        # the regions this pass missed and grows overall_ocr_res to the final ~577 lines, so
        # the streamed count is legitimately lower than the finished page.
        yield event("lines", lines=[{"bbox": fix(box), "text": text, "score": float(score)}
                    for box, text, score in zip(ocr["rec_boxes"].tolist(), ocr["rec_texts"], ocr["rec_scores"])])
        parsed = p.get_layout_parsing_res(rotated, region_det_res=region,
            layout_det_res=layout, overall_ocr_res=ocr, table_res_list=[], seal_res_list=[],
            chart_res_list=[], formula_res_list=[], text_rec_score_thresh=None,
            markdown_ignore_labels=p.markdown_ignore_labels)
        raw = {"width": rotated.shape[1], "height": rotated.shape[0],
            "doc_preprocessor_res": {"angle": angle},
            "overall_ocr_res": ocr.json["res"],
            "parsing_res_list": [{"block_id": b.index, "block_order": b.order_index,
                "block_label": b.label, "block_content": b.content,
                "block_bbox": [float(v) for v in b.bbox]} for b in parsed]}
        page = normalize(raw, self.engine, w, h)
        yield event("done", page=page.to_dict())
