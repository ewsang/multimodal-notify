"""Pure domain processing engine handling single image template matching analysis."""

import logging
import os
import cv2
import numpy as np

log = logging.getLogger(__name__)


class CVProcessor:
    """Analytical engine that handles loading and matching a single image pattern template."""

    def __init__(self, strategy_config: dict, worker_name: str):
        """Initializes threshold and validates a single computer vision template asset."""
        self.worker_name = worker_name
        self.cooldown_seconds = strategy_config.get("cooldown_seconds", 900)
        self.template_name = strategy_config.get("template_name", "CB-23.png")
        self.match_threshold = strategy_config.get("match_threshold", 0.85)
        self.notification_message = strategy_config.get("notification_message", "")
        self.reaction_rules = strategy_config.get("reaction_rules", [])
        
        self.template_matrix = None

        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, "../../../assets", self.template_name)
        
        log.debug(f"[{self.worker_name}] Core engine loading template matrix file: {path}")
        self.template_matrix = cv2.imread(path, cv2.IMREAD_COLOR)
        
        if self.template_matrix is not None:
            h, w, c = self.template_matrix.shape
            log.debug(f"[{self.worker_name}] Success: Buffered tracking matrix ({w}x{h}, {c} channels)")
        else:
            log.error(f"[{self.worker_name}] Critical Configuration Error: Asset resolution failed at: {path}")

    def process_frame(self, frame: np.ndarray) -> dict | None:
        """Evaluates an image matrix against our single loaded template target."""
        if self.template_matrix is None:
            return None

        result = cv2.matchTemplate(frame, self.template_matrix, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)

        if max_val >= self.match_threshold:
            log.info(f"[{self.worker_name}] Match confirmed! (Score: {max_val:.2f} >= Threshold: {self.match_threshold})")
            return {
                "template_name": self.template_name,
                "notification_message": self.notification_message,
                "reaction_rules": self.reaction_rules
            }
            
        log.debug(
            f"[{self.worker_name}] Match rejected. Score: {max_val:.4f} (Required: {self.match_threshold})"
        )
        return None
