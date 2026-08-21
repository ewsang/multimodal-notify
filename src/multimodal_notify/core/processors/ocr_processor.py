# core/processors/ocr_processor.py
import time
import logging
import threading

def levenshtein_distance(a, b):
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a

    previous = range(len(b) + 1)
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            insert = previous[j] + 1
            delete = current[j - 1] + 1
            replace = previous[j - 1] + (ca != cb)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]

class OCRProcessor:
    def __init__(self, profile_config):
        self.config = profile_config
        self.canonical_messages = self.config["expected_messages"]

        # Thread-safe timeline tracking infrastructure
        self.messages_lock = threading.Lock()
        self.messages = []
        self.next_message_id = 1
        self.dedup_window = 8.0

    def normalize_ocr_text(self, raw_text):
        cleaned_text = raw_text.strip()
        if not cleaned_text:
            return None

        is_case_sensitive = self.config.get("case_sensitive", False)
        if not is_case_sensitive:
            cleaned_text = cleaned_text.upper()

        best_match = None
        min_distance = float("inf")
        for keyword in self.canonical_messages:
            target = keyword if is_case_sensitive else keyword.upper()
            distance = levenshtein_distance(cleaned_text, target)
            if distance < min_distance:
                min_distance = distance
                best_match = keyword
        threshold_pct = self.config.get("match_threshold_pct", 0.30)
        max_allowed_dist = int(len(best_match) * threshold_pct)

        if min_distance > max_allowed_dist:
            logging.debug(
                f"[Processor] Unreliable text discarded: '{raw_text}' "
                f"(Best match: '{best_match}', Dist: {min_distance}/{max_allowed_dist})"
            )
            return None

        return {
            "text_ocr": raw_text,
            "text_normalized": best_match
        }

    def process_frame_text(self, raw_text_block):
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
            
            # Map unexpired instances within tracking window
            for m in self.messages:
                if now - m["last_seen"] <= self.dedup_window:
                    norm = m["text_normalized"]
                    if norm not in active_history_instances:
                        active_history_instances[norm] = []
                    active_history_instances[norm].append(m)

            processed_frame_counts = {}
            # Match separate concurrent instances
            for processed in valid_lines:
                norm = processed["text_normalized"]
                processed_frame_counts[norm] = processed_frame_counts.get(norm, 0) + 1
                
                instance_index = processed_frame_counts[norm] - 1
                history_list = active_history_instances.get(norm, [])

                # Identify active duplicate messages
                if instance_index < len(history_list):
                    history_list[instance_index]["last_seen"] = now
                    logging.debug(f"[Deduplicator] Renewed active message for ID {history_list[instance_index]['id']} ({norm})")
                else:
                    new_record = {
                        "id": self.next_message_id,
                        "text_ocr": processed["text_ocr"],
                        "text_normalized": norm,
                        "timestamp": now,
                        "last_seen": now
                    }
                    self.messages.append(new_record)
                    self.next_message_id += 1
                    new_message_records.append(new_record)
                    logging.info(f"[Processor] Expected message: '{processed['text_ocr']}' -> '{norm}'")
                    
        return new_message_records
