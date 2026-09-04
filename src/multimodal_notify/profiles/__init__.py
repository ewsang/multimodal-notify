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
            
        if config_data and "strategies" in config_data:
            yaml_strategies = config_data.get("strategies", {})
            processed_strategies = {}
            
            for strategy_name in ["ocr", "cv"]:
                if strategy_name not in yaml_strategies:
                    continue
                    
                raw_config = yaml_strategies.get(strategy_name, {})
                bounds = raw_config.get("bounds", {})
                
                strategy_data = {
                    "interval": raw_config.get("interval", 0.500),
                    "bbox": (
                        bounds.get("x", 0),
                        bounds.get("y", 0),
                        bounds.get("width", 1920),
                        bounds.get("height", 1080),
                    ),
                    "strategy_config": raw_config
                }
                processed_strategies[strategy_name] = strategy_data
                
            PROFILE_REGISTRY[profile_key] = {
                "strategies": processed_strategies,
                "discord": config_data.get("discord", {}),
            }
    except Exception as e:
        print(f"[Warning] Failed to parse profile template file {file_path.name}: {e}")

__all__ = ["PROFILE_REGISTRY"]
