"""Transforms normalized matching metrics into structured MessageEvent instances and broadcasts them to active connectors."""

import logging
import time

from multimodal_notify.core.events.message_event import MessageEvent

log = logging.getLogger(__name__)


class MessageProducer:
    """Transforms raw worker records into standardized MessageEvents and dispatches them to connectors."""

    def __init__(self, connectors: list, profile_config: dict):
        """Initializes the producer engine with target connectors and active profile rules."""
        self.connectors = connectors
        self.profile_config = profile_config

    def handle_new_message(self, record: dict) -> None:
        """Processes normalized metrics from workers, extracts metadata schemas, and alerts connectors."""
        norm = record.get("text_normalized", "")
        ocr = record.get("text_ocr", "")
        source = record.get("source", "OCR")

        if not norm and "notification_message" in record:
            description = record["notification_message"]
        else:
            formatter = self.profile_config.get("format_message")
            description = formatter(norm, ocr) if formatter else norm
        
        tag_extractor = self.profile_config.get("extract_tags")
        metadata = tag_extractor(norm) if tag_extractor and norm else {}

        metadata["source"] = source
        metadata["reaction_rules"] = record.get("reaction_rules", [])

        ignored_keys = {
            "source", "id", "text_ocr", "text_normalized", 
            "timestamp", "reaction_rules", "frame", "notification_message"
        }
        for key, value in record.items():
            if key not in ignored_keys:
                metadata[key] = value

        event_timestamp = (
            record.get("timestamp") 
            if record.get("timestamp") is not None 
            else time.time()
        )

        event = MessageEvent(
            description=description,
            timestamp=event_timestamp,
            metadata=metadata,
        )
        
        for connector in self.connectors:
            connector.handle(event)

    def shutdown(self) -> None:
        """Triggers shutdown routines across all active broadcasting connectors."""
        for connector in self.connectors:
            if hasattr(connector, "shutdown") and callable(connector.shutdown):
                try:
                    connector.shutdown()
                except Exception as e:
                    log.error(
                        f"Failed to cleanly shut down connector "
                        f"{connector.__class__.__name__}: {e}", 
                        exc_info=True
                    )
