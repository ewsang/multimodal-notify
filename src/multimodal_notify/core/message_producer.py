"""Transforms normalized matching metrics into structured MessageEvent instances and broadcasts them to active connectors."""

import re
from multimodal_notify.core.events.message_event import MessageEvent, MessageField


class MessageProducer:

    def __init__(self, connectors, profile_config):
        self.connectors = connectors
        self.profile_config = profile_config

    def handle_new_message(self, record):
        norm = record["text_normalized"]
        ocr = record["text_ocr"]
        source = record.get("source", "OCR")

        formatter = self.profile_config.get("format_message")
        description = formatter(norm, ocr) if formatter else norm

        tag_extractor = self.profile_config.get("extract_tags")
        metadata = tag_extractor(norm) if tag_extractor else {}
        metadata["source"] = source

        if source == "OCR" and "parser_schema" in self.profile_config:
            schema = self.profile_config["parser_schema"]
            pattern_str = schema.get("regex_pattern")

            if pattern_str:
                pattern = re.compile(pattern_str)
                match = pattern.search(norm)

                if match:
                    mappings = schema.get("rule_mappings", {})
                    metadata["tier"] = match.group(mappings.get("tier")).strip()
                    metadata["rarity"] = match.group(mappings.get("rarity")).strip()

        event = MessageEvent(
            description=description,
            timestamp=record["timestamp"],
            metadata=metadata,
        )

        for connector in self.connectors:
            connector.handle(event)
