"""Background thread worker utilizing native macOS Quartz capture and Apple Vision OCR."""

import logging
import re
from typing import List
import objc
from Vision import (
    VNImageRequestHandler,
    VNRecognizeTextRequest,
    VNRequestTextRecognitionLevelAccurate,
)

from multimodal_notify.core.events import OcrEvent
from multimodal_notify.pipeline.processors.ocr_processor import OcrProcessor
from multimodal_notify.pipeline.workers.base_worker import BaseWorker

log = logging.getLogger(__name__)


class OcrWorker(BaseWorker):
    """Capture screen regions for on-screen text recognition."""

    def __init__(self, bbox: tuple, interval: float, event_queue: object, worker_name: str, strategy_config: dict) -> None:
        """Initialize worker with tracking bounds and configuration."""
        super().__init__(bbox, interval, event_queue, worker_name, strategy_config)
        self.strategy_config = strategy_config
        self.processor = OcrProcessor(strategy_config, worker_name=self.name)

    def _capture_and_extract(self) -> str:
        """Capture display region and extract text using Apple Vision OCR."""
        cg_image = self.capture_screen_image()
        if not cg_image:
            raise RuntimeError("Quartz failed to capture screen region.")

        text_request = VNRecognizeTextRequest.alloc().init()
        text_request.setRecognitionLevel_(VNRequestTextRecognitionLevelAccurate)

        handler = VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        success, error = handler.performRequests_error_([text_request], objc.nil)

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

    def _should_send_notification(self, matched_text: str, profile_config: dict) -> bool:
        """Checks matched text against parsing schemas and matrix filter criteria to determine notification viability."""
        schema = profile_config.get("parser_schema", {})
        rules_container = profile_config.get("message_filter_rules", {})
        matrix = rules_container.get("matrix", {})

        logging.debug(f"Evaluating schema: {schema}, rules container: {rules_container}, matrix: {matrix} for text: '{matched_text}'")
        if not schema or not matrix:
            return True

        try:
            pattern_str = schema.get("regex_pattern")
            pattern = re.compile(pattern_str)
            match = pattern.search(matched_text)
            if not match:
                logging.debug(f"Filter Drop: Text '{matched_text}' did not match profile regex pattern structure.")
                return False

            mappings = schema.get("rule_mappings", {})
            tier_group_idx = mappings.get("tier")
            rarity_group_idx = mappings.get("rarity")
            
            extracted_tier = match.group(tier_group_idx)
            extracted_rarity = match.group(rarity_group_idx)
            logging.debug(f"Extracted Parameters: Tier='{extracted_tier}', Rarity='{extracted_rarity}' from text '{matched_text}'")

            if extracted_rarity in matrix:
                allowed_tiers = matrix[extracted_rarity]
                return extracted_tier in allowed_tiers

            return False
        except Exception as e:
            logging.error(f"Error evaluating text schema constraints: {e}")
            return False

    def process(self) -> None:
        """Extract, normalize, deduplicate, filter, and queue text frames."""
        try:
            sanitized_text = self._capture_and_extract().strip()
            if not sanitized_text:
                return
        except Exception as e:
            log.error(f"[{self.name}] Extraction failure: {e}")
            return

        new_instances: List[OcrEvent] = self.processor.process_frame_text(sanitized_text)

        schema = self.strategy_config.get("parser_schema", {})
        pattern_str = schema.get("regex_pattern")
        pattern = re.compile(pattern_str) if pattern_str else None
        mappings = schema.get("rule_mappings", {})

        for instance in new_instances:
            raw_text = instance.text_normalized

            if self._should_send_notification(raw_text, self.strategy_config):
                log.info(f"[{self.name}] ✅ Message verified: '{raw_text}'. Routing payload upstream.")

                extracted_metadata = {}
                if pattern:
                    match = pattern.search(raw_text)
                    if match:
                        for metadata_key, group_index in mappings.items():
                            try:
                                extracted_metadata[metadata_key] = match.group(group_index).strip()
                            except IndexError:
                                log.warning(
                                    f"[{self.name}] Config error: Group index "
                                    f"{group_index} not found for key '{metadata_key}'"
                                )

                instance.metadata.update(extracted_metadata)
                
                self.event_queue.put(instance)
            else:
                log.info(f"[{self.name}] 🚫 Message filtered out: '{raw_text}'")
