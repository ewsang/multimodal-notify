"""Applies profile-specific regex filters, evaluation matrices, and conditional emoji reaction layouts to events."""

import logging
import re


def evaluate_reaction_emojis(metadata: dict, profile_config: dict) -> list[str]:
    rules = profile_config.get("reaction_rules", [])
    if not metadata or not rules:
        return []

    matched_emojis = []
    normalized_meta = {str(k).upper().strip(): str(v).upper().strip() for k, v in metadata.items()}

    for rule in rules:
        emoji = rule.get("emoji")
        criteria = rule.get("criteria", {})
        if not emoji or not criteria:
            continue

        is_match = True
        for criterion_key, criterion_val in criteria.items():
            meta_key = str(criterion_key).upper().strip()
            expected_val = str(criterion_val).upper().strip()
            if normalized_meta.get(meta_key) != expected_val:
                is_match = False
                break

        if is_match:
            matched_emojis.append(emoji)

    return matched_emojis


def should_send_notification(matched_text: str, profile_config: dict) -> bool:
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
