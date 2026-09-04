"""Background thread worker utilizing native macOS Quartz screen capture and the Apple Vision OCR framework."""

import logging
import re

import objc
from Vision import (
    VNImageRequestHandler,
    VNRecognizeTextRequest,
    VNRequestTextRecognitionLevelAccurate,
)

from multimodal_notify.core.message_filter import should_send_notification
from multimodal_notify.pipeline.processors.ocr_processor import OCRProcessor
from multimodal_notify.pipeline.workers.base_worker import BaseWorker

log = logging.getLogger(__name__)


class OCRWorker(BaseWorker):
    """Worker thread that captures display regions for on-screen text recognition."""

    def __init__(
        self, 
        bbox: tuple, 
        interval: float, 
        event_queue: object, 
        worker_name: str, 
        strategy_config: dict
    ):
        """Initializes the worker with text-tracking bounds and configurations."""
        super().__init__(
            bbox, interval, event_queue, worker_name, strategy_config
        )
        self.strategy_config = strategy_config
        self.processor = OCRProcessor(strategy_config, worker_name=self.name)

    def _capture_and_extract(self) -> str:
        """Captures the target display region and extracts text using Apple Vision."""
        cg_image = self.capture_screen_image()
        if not cg_image:
            raise RuntimeError("Quartz failed to capture screen region.")

        text_request = VNRecognizeTextRequest.alloc().init()
        text_request.setRecognitionLevel_(
            VNRequestTextRecognitionLevelAccurate
        )
        
        handler = (
            VNImageRequestHandler.alloc()
            .initWithCGImage_options_(cg_image, None)
        )
        success, error = handler.performRequests_error_(
            [text_request], objc.nil
        )
        
        if not success:
            raise RuntimeError(f"Vision OCR request failed: {error}")

        results = text_request.results()
        extracted_text = []
        if results:
            for observation in results:
                top_candidate = observation.topCandidates_(1).firstObject()
                if top_candidate:
                    extracted_text.append(top_candidate.string())
        return "\n".join(extracted_text)

    def process(self) -> None:
        """Extracts, normalizes, dedupes, filters, and passes final entries to the central event loop."""
        try:
            sanitized_text = self._capture_and_extract().strip()
            if not sanitized_text:
                return
        except Exception as e:
            log.error(f"[{self.name}] Extraction failure: {e}")
            return

        new_instances = self.processor.process_frame_text(sanitized_text)

        schema = self.strategy_config.get("parser_schema", {})
        pattern_str = schema.get("regex_pattern")
        pattern = re.compile(pattern_str) if pattern_str else None
        mappings = schema.get("rule_mappings", {})

        for instance in new_instances:
            raw_text = instance['text_normalized']

            if should_send_notification(raw_text, self.strategy_config):
                log.info(
                    f"[{self.name}] ✅ Message verified: '{raw_text}'. "
                    f"Routing payload upstream."
                )

                extracted_metadata = {}
                if pattern:
                    match = pattern.search(raw_text)
                    if match:
                        for metadata_key, group_index in mappings.items():
                            try:
                                extracted_metadata[metadata_key] = (
                                    match.group(group_index).strip()
                                )
                            except IndexError:
                                log.warning(
                                    f"[{self.name}] Config error: Group index "
                                    f"{group_index} not found for key "
                                    f"'{metadata_key}'"
                                )

                payload = {
                    "source": "OCR",
                    "id": instance["id"],
                    "text_ocr": instance["text_ocr"],
                    "text_normalized": raw_text,
                    "timestamp": instance["timestamp"],
                    "reaction_rules": self.strategy_config.get(
                        "reaction_rules", []
                    )
                }
                payload.update(extracted_metadata)

                self.event_queue.put(payload)
            else:
                log.debug(
                    f"[{self.name}] 🚫 Message filtered out: '{raw_text}'"
                )
