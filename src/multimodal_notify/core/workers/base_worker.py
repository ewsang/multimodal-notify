"""Abstract base worker class providing screen boundary clamping and thread lifecycle controls."""

import abc
import logging
import queue
import threading
import time

import mss
from Quartz.CoreGraphics import CGDisplayCreateImageForRect, CGMainDisplayID, CGRectMake


class BaseWorker(threading.Thread, abc.ABC):
    """Abstract background thread orchestrating periodic screen capture processing loops."""

    def __init__(
        self,
        bbox: tuple,
        interval: float,
        event_queue: queue.Queue,
        worker_name: str,
        strategy_config: dict
    ):
        """Initializes the thread context and applies screen boundary coordinate clamping."""
        super().__init__(name=worker_name, daemon=True)
        self.running = False
        self.interval = interval
        self.event_queue = event_queue
        self.strategy_config = strategy_config
        self.bbox = self._clamp_to_screen_bounds(bbox)

    def _clamp_to_screen_bounds(self, bbox):
        """Clamps coordinate regions to fit safely within the primary monitor boundaries."""
        x, y, w, h = bbox
        with mss.mss() as sct:
            primary = sct.monitors[1]
            screen_w = primary["width"]
            screen_h = primary["height"]
            
            safe_x = max(0, min(x, screen_w - 1))
            safe_y = max(0, min(y, screen_h - 1))
            safe_w = max(1, min(w, screen_w - safe_x))
            safe_h = max(1, min(h, screen_h - safe_y))
            
            if (x, y, w, h) != (safe_x, safe_y, safe_w, safe_h):
                logging.warning(
                    f"[{self.__class__.__name__}] Bounding box adjusted from "
                    f"{(x, y, w, h)} to {(safe_x, safe_y, safe_w, safe_h)} for safety."
                )
            return (safe_x, safe_y, safe_w, safe_h)

    def capture_screen_image(self):
        """Captures the designated bounding box region via direct top-level C-function references.

        Returns:
            CGImageRef or None: The low-level macOS system image capture object.
        """
        x, y, w, h = self.bbox
        region_rect = CGRectMake(x, y, w, h)
        main_display = CGMainDisplayID()
        return CGDisplayCreateImageForRect(main_display, region_rect)

    def run(self):
        """Executes the continuous periodic looping sequence driving child engine tasks."""
        self.running = True
        logging.info("Thread driving loop started.")
        
        while self.running:
            loop_start_time = time.time()
            try:
                self.process()
            except Exception as e:
                logging.exception(f"Exception caught inside [{self.name}] execution segment: {e}")

            elapsed = time.time() - loop_start_time
            sleep_time = max(0.01, self.interval - elapsed)
            time.sleep(sleep_time)

        logging.info("Thread cleanly terminated.")

    def stop(self):
        """Signals the active execution loop to halt processing on the next iteration."""
        self.running = False

    @abc.abstractmethod
    def process(self):
        """Abstract implementation hook for executing concrete worker frame analysis."""
        pass