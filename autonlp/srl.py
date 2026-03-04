from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SRLArgument:
    role: str
    text: str
    score: float = 0.7


class BaseSRLProvider:
    def predict(self, sentence_text: str) -> list[SRLArgument]:
        raise NotImplementedError


class NullSRLProvider(BaseSRLProvider):
    def predict(self, sentence_text: str) -> list[SRLArgument]:
        return []


ROLE_TO_LABEL = {
    "ARGM-TMP": "TIME",
    "TMP": "TIME",
    "ARGM-LOC": "LOC",
    "LOC": "LOC",
    "ARGM-MNR": "METHOD",
    "MNR": "METHOD",
    "ARGM-PRP": "PURPOSE",
    "PRP": "PURPOSE",
    "ARGM-EXT": "VALUE",
    "EXT": "VALUE",
    "ARGM-DIR": "LOC",
    "DIR": "LOC",
}


def map_srl_role_to_label(role: str) -> str:
    return ROLE_TO_LABEL.get(role.upper(), "UNKNOWN")