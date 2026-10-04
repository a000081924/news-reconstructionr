from dataclasses import dataclass, field

OFF = dict(use_table_recognition=False, use_formula_recognition=False,
           use_seal_recognition=False, use_chart_recognition=False, use_doc_unwarping=False)
LEAN = dict(use_textline_orientation=True, text_recognition_batch_size=32,
            textline_orientation_batch_size=32, **OFF)


@dataclass(frozen=True)
class EngineSpec:
    id: str
    label: str
    description: str
    interactive: bool
    pipeline_kwargs: dict = field(default_factory=dict)


ENGINES = {
    "structure": EngineSpec("structure", "PP-StructureV3", "Lean server OCR; provisional default pending CER.", True, LEAN),
    "cht": EngineSpec("cht", "Traditional Chinese", "Server detector with Traditional Chinese recognizer.", True,
                      {**LEAN, "text_recognition_model_name": "chinese_cht_PP-OCRv3_mobile_rec"}),
    "vl": EngineSpec("vl", "PaddleOCR-VL", "Vision-language recognition. Offline only: without vLLM it decodes one "
                     "block at a time and needs 21-35 minutes a page, so run it with parse.py vl.", False),
}
