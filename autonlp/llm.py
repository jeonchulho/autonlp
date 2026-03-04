from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMDecision:
    label: str
    value: Optional[str] = None
    confidence: float = 0.6


class BaseLLMLabeler:
    def classify(
        self,
        sentence_text: str,
        candidate_text: str,
        evidence: dict,
    ) -> Optional[LLMDecision]:
        raise NotImplementedError


class NullLLMLabeler(BaseLLMLabeler):
    def classify(
        self,
        sentence_text: str,
        candidate_text: str,
        evidence: dict,
    ) -> Optional[LLMDecision]:
        return None