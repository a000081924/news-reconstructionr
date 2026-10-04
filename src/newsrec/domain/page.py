from dataclasses import dataclass
from math import isfinite

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BBox:
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self):
        if not all(isfinite(v) for v in self.to_list()) or self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("bbox must have finite coordinates and positive area")

    def to_list(self):
        return [self.x1, self.y1, self.x2, self.y2]

    def to_dict(self):
        return self.to_list()

    @classmethod
    def from_dict(cls, raw):
        return cls(*raw)


@dataclass
class Line:
    bbox: BBox
    text: str
    score: float

    def to_dict(self):
        return {"bbox": self.bbox.to_list(), "text": self.text, "score": self.score}

    @classmethod
    def from_dict(cls, raw):
        return cls(**{**raw, "bbox": BBox.from_dict(raw["bbox"])})


@dataclass
class Block:
    id: int
    order: int
    label: str
    bbox: BBox
    text: str
    lines: list[Line]

    def to_dict(self):
        return {"id": self.id, "order": self.order, "label": self.label,
                "bbox": self.bbox.to_list(), "text": self.text,
                "lines": [line.to_dict() for line in self.lines]}

    @classmethod
    def from_dict(cls, raw):
        return cls(**{**raw, "bbox": BBox.from_dict(raw["bbox"]),
                      "lines": [Line.from_dict(line) for line in raw["lines"]]})


@dataclass
class Page:
    engine: str
    width: int
    height: int
    image: str
    angle: int
    blocks: list[Block]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported page schema {self.schema_version}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("page dimensions must be positive")
        if len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("duplicate block id")
        if len({b.order for b in self.blocks}) != len(self.blocks):
            raise ValueError("duplicate reading order")
        if self.angle not in (0, 90):
            raise ValueError("unsupported page rotation")
        for b in self.blocks:
            if not isinstance(b.text, str) or not isinstance(b.label, str):
                raise ValueError("block text and label must be strings")
            for line in b.lines:
                if not isinstance(line.text, str) or not isfinite(line.score) or not 0 <= line.score <= 1:
                    raise ValueError("invalid line text or confidence")
            for box in [b.bbox, *(line.bbox for line in b.lines)]:
                if not (0 <= box.x1 < box.x2 <= self.width and 0 <= box.y1 < box.y2 <= self.height):
                    raise ValueError("bbox outside page")

    def to_dict(self):
        return {"schema_version": self.schema_version, "engine": self.engine,
                "width": self.width, "height": self.height, "image": self.image,
                "angle": self.angle, "blocks": [block.to_dict() for block in self.blocks]}

    @classmethod
    def from_dict(cls, raw):
        raw = dict(raw)
        raw["blocks"] = [Block.from_dict(b) for b in raw["blocks"]]
        return cls(**raw)
