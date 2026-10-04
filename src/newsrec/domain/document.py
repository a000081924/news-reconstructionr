from dataclasses import dataclass
from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True)
class PageRef:
    id: str
    document_id: str


@dataclass(frozen=True)
class Document:
    id: str
    name: str
    pages: list[PageRef]
