from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Condition:
    label: str
    text: str
    value: Optional[str] = None
    normalized: Optional[dict] = None
    confidence: float = 0.0
    source: str = "rule"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SentenceExtraction:
    text: str
    predicate: Optional[str] = None
    subject: Optional[str] = None
    object: Optional[str] = None
    object_normalized: Optional[str] = None
    object_items: list[str] = field(default_factory=list)
    recipients: list[str] = field(default_factory=list)
    conditions: list[Condition] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["conditions"] = [c.to_dict() for c in self.conditions]
        return data


@dataclass
class ExtractionResult:
    text: str
    sentences: list[SentenceExtraction]

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "sentences": [s.to_dict() for s in self.sentences],
        }