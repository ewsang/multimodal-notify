"""Automated profile discovery, processing, configuration schema mapping, and file registry parsing."""

from pathlib import Path
import yaml

PROFILE_REGISTRY = {}
PROFILES_DIR = Path(__file__).resolve().parent

yaml_files = list(PROFILES_DIR.glob("*.yaml")) + list(PROFILES_DIR.glob("*.YAML"))

for file_path in yaml_files:
    profile_key = file_path.stem
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        if config_data and "expected_messages" in config_data:
            yaml_strategies = config_data.get("strategies", {})
            processed_strategies = {}

            for strategy_name in ["ocr"]:
                strategy_config = yaml_strategies.get(strategy_name, {})
                bounds = strategy_config.get("bounds", {})
                processed_strategies[strategy_name] = {
                    "interval": strategy_config.get("interval", 0.500),
                    "bbox": (
                        bounds.get("x", 0),
                        bounds.get("y", 0),
                        bounds.get("width", 1920),
                        bounds.get("height", 1080)
                    )
                }

            PROFILE_REGISTRY[profile_key] = {
                "expected_messages": config_data["expected_messages"],
                "case_sensitive": config_data.get("case_sensitive", False),
                "match_threshold_pct": config_data.get("match_threshold_pct", 0.30),
                "strategies": processed_strategies,
                "discord": config_data.get("discord", {}),
                "parser_schema": config_data.get("parser_schema", {}),
                "message_filter_rules": config_data.get("message_filter_rules", {}),
                "reaction_rules": config_data.get("reaction_rules", [])
            }
    except Exception as e:
        print(f"[Warning] Failed to parse profile template file {file_path.name}: {e}")

__all__ = ["PROFILE_REGISTRY"]
