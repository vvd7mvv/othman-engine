"""الواجهة الموحدة للتفريغ: أي موديل بديل يكفي أن يطبّق Transcriber."""
from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> list[Word]:
        """audio: mono float32 بتردد config.SAMPLE_RATE."""
