"""Published JSON page contract (bbox arrays stay compatible with the prototype)."""
from typing import Literal

from pydantic import BaseModel, Field


class LineResponse(BaseModel):
    bbox: tuple[float, float, float, float]
    text: str
    score: float = Field(ge=0, le=1)


class BlockResponse(BaseModel):
    id: int
    order: int
    label: str
    bbox: tuple[float, float, float, float]
    text: str
    lines: list[LineResponse]


class PageResponse(BaseModel):
    schema_version: Literal[1]
    engine: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    image: str
    angle: Literal[0, 90]
    blocks: list[BlockResponse]
