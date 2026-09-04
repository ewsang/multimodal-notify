"""Exposes background capture threads for multi-modal polling strategies."""

from multimodal_notify.core.workers.cv_worker import CVWorker
from multimodal_notify.core.workers.ocr_worker import OCRWorker

__all__ = ["CVWorker", "OCRWorker"]
