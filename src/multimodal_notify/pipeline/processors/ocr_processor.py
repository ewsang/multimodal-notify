"""Text normalization and Levenshtein distance deduplication processor."""

import logging
import threading
import time
from typing import List
from multimodal_notify.core.events import OcrEvent


def levenshtein_distance(a: str, b: str) -> int:
    """Calculate minimum edit operations to transform string a into b."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            insert = previous[j] + 1
            delete = current[j - 1] + 1
            replace = previous[j - 1] + (ca != cb)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]


class OcrProcessor:
    """Normalize extracted text and map sequences to a unified timeline."""

    def __init__(self, strategy_config: dict, worker_name: str) -> None:
        """Initialize fuzzy caches using profile strategy rules."""
        self.worker_name = worker_name
        self.strategy_config = strategy_config

        self.canonical_messages = strategy_config.get("expected_messages", [])
        self.is_case_sensitive = strategy_config.get("case_sensitive", False)
        self.match_threshold_pct = strategy_config.get("match_threshold_pct", 0.30)

        self.messages_lock = threading.Lock()
        self.messages: List[dict] = []
        self.next_message_id = 1
        self.dedup_window = 8.0

    def normalize_ocr_text(self, raw_text: str) -> dict | None:
        """Fuzzy match raw string targets against expected message registries."""
        cleaned_text = raw_text.strip()
        if not cleaned_text:
            return None

        if not self.is_case_sensitive:
            cleaned_text = cleaned_text.upper()

        best_match = None
        min_distance = float("inf")

        for keyword in self.canonical_messages:
            target = keyword if self.is_case_sensitive else keyword.upper()
            distance = levenshtein_distance(cleaned_text, target)
            if distance < min_distance:
                min_distance = distance
                best_match = keyword

        max_allowed_dist = int(len(best_match) * self.match_threshold_pct) if best_match else 0

        if not best_match or min_distance > max_allowed_dist:
            logging.debug(
                f"[{self.worker_name}] Unreliable text discarded: '{raw_text}' "
                f"(Best match: '{best_match}', Dist: {min_distance}/{max_allowed_dist})"
            )
            return None

        return {
            "text_ocr": raw_text,
            "text_normalized": best_match
        }

    def process_frame_text(self, raw_text_block: str) -> List[OcrEvent]:
        """Parse multi-line text payloads to update or yield unique records."""
        lines = [line.strip() for line in raw_text_block.split("\n") if line.strip()]
        now = time.time()
        valid_lines = []

        for line in lines:
            processed = self.normalize_ocr_text(line)
            if processed:
                valid_lines.append(processed)

        new_message_records = []

        with self.messages_lock:
            active_history_instances = {}
            for m in self.messages:
                if now - m["last_seen"] <= self.dedup_window:
                    norm = m["text_normalized"]
                    if norm not in active_history_instances:
                        active_history_instances[norm] = []
                    active_history_instances[norm].append(m)

            processed_frame_counts = {}
            for processed in valid_lines:
                norm = processed["text_normalized"]
                processed_frame_counts[norm] = processed_frame_counts.get(norm, 0) + 1
                instance_index = processed_frame_counts[norm] - 1

                history_list = active_history_instances.get(norm, [])
                if instance_index < len(history_list):
                    history_list[instance_index]["last_seen"] = now
                    logging.debug(
                        f"[{self.worker_name}] Renewed duplicate message ID "
                        f"{history_list[instance_index]['id']} ({norm})"
                    )
                else:
                    new_record = OcrEvent(
                        source=f"processor.ocr.{self.worker_name}",
                        id=str(self.next_message_id),
                        text_ocr=processed["text_ocr"],
                        text_normalized=norm,
                        reaction_rules=self.strategy_config.get("reaction_rules", []),
                        metadata={"engine_version": "1.0.0"},
                        description=f"Fuzzy OCR Match: {norm}"
                    )

                    self.messages.append({
                        "id": self.next_message_id,
                        "text_normalized": norm,
                        "last_seen": now
                    })
                    self.next_message_id += 1
                    new_message_records.append(new_record)

        return new_message_records
