"""Exposes background capture threads for multi-modal polling strategies."""

from multimodal_notify.pipeline.workers.cv_worker import CVWorker
from multimodal_notify.pipeline.workers.ocr_worker import OCRWorker

__all__ = ["CVWorker", "OCRWorker"]
