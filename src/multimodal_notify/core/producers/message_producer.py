"""Transforms normalized matching metrics into structured MessageEvent instances and broadcasts them."""
import logging
import time
from multimodal_notify.core.events.message_event import MessageEvent, OcrEvent, CvEvent

log = logging.getLogger(__name__)


class MessageProducer:
    """Transform raw worker records into standardized MessageEvents for dispatch."""

    def __init__(self, connectors: list, profile_config: dict) -> None:
        """Initialize producer engine with targets and profile rules."""
        self.connectors = connectors
        self.profile_config = profile_config

    def handle_new_message(self, event) -> None:
        """Process metrics from workers, extract metadata, and alert connectors."""
        if isinstance(event, OcrEvent):
            norm = event.text_normalized
            ocr = event.text_ocr
            source = event.source
            event_timestamp = event.timestamp if event.timestamp is not None else time.time()
            reaction_rules = event.reaction_rules
            metadata = dict(event.metadata)

        elif isinstance(event, CvEvent):
            norm = ""
            ocr = ""
            source = event.source
            event_timestamp = time.time()
            reaction_rules = event.reaction_rules
            metadata = {}

        else:
            log.warning(f"[MessageProducer] Unrecognized event class structure ignored: {type(event)}")
            return

        if not norm and isinstance(event, CvEvent):
            description = event.notification_message
        else:
            formatter = self.profile_config.get("format_message")
            description = formatter(norm, ocr) if formatter else norm

        tag_extractor = self.profile_config.get("extract_tags")
        if tag_extractor and norm:
            extracted_tags = tag_extractor(norm)
            if isinstance(extracted_tags, dict):
                metadata.update(extracted_tags)

        metadata["source"] = source
        metadata["reaction_rules"] = reaction_rules

        rich_message = MessageEvent(
            source=source,
            description=description,
            timestamp=event_timestamp,
            metadata=metadata,
        )

        for connector in self.connectors:
            connector.handle(rich_message)

    def shutdown(self) -> None:
        """Trigger graceful shutdown routines across active connectors."""
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
