# profiles/__init__.py
import os
import yaml
from pathlib import Path

# This central registry will hold all loaded profile configurations
PROFILE_REGISTRY = {}

# 1. Target the absolute directory path containing this __init__.py file
PROFILES_DIR = Path(__file__).resolve().parent

# 2. Gather both lowercase and uppercase variations to prevent case-sensitive macOS skips
yaml_files = list(PROFILES_DIR.glob("*.yaml")) + list(PROFILES_DIR.glob("*.yaml".upper()))

# 3. Parse and populate the profile dictionary mappings
for file_path in yaml_files:
    profile_key = file_path.stem  # e.g., 'fortnite_droid_tycoon'
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
            
            # Schema validation: verify our agnostic expected_messages root exists
            if config_data and "expected_messages" in config_data:
                yaml_strategies = config_data.get("strategies", {})
                processed_strategies = {}

                # Map configurations explicitly for each available strategy engine
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
                    "expected_messages": config_data["expected_messages"], # ◄── Updated mapping key
                    "case_sensitive": config_data.get("case_sensitive", False),
                    "match_threshold_pct": config_data.get("match_threshold_pct", 0.30),
                    "strategies": processed_strategies
                }
                
    except Exception as e:
        print(f"[Warning] Failed to parse profile template file {file_path.name}: {e}")

__all__ = ["PROFILE_REGISTRY"]
