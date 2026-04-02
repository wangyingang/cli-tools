from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import OCRText


class OCRBackend(ABC):
    engine_name: str

    @abstractmethod
    def recognize(self, image) -> OCRText:
        raise NotImplementedError
