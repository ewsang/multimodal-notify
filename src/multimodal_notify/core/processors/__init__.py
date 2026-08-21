# core/processors/__init__.py
from .ocr_processor import OCRProcessor, levenshtein_distance

__all__ = ["OCRProcessor", "levenshtein_distance"]