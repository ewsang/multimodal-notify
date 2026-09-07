"""Background thread worker utilizing native macOS Quartz screen capture for computer vision."""

import logging
import time
import cv2
import numpy as np
from Quartz import (
    CGDataProviderCopyData,
    CGImageGetBytesPerRow,
    CGImageGetDataProvider,
    CGImageGetHeight,
    CGImageGetWidth,
)

from multimodal_notify.core.events import CvEvent
from multimodal_notify.pipeline.processors.cv_processor import CvProcessor
from multimodal_notify.pipeline.workers.base_worker import BaseWorker

log = logging.getLogger(__name__)


class CvWorker(BaseWorker):
    """Worker thread that captures display regions for visual template tracking."""

    def __init__(self, bbox: tuple, interval: float, event_queue: object, worker_name: str, strategy_config: dict) -> None:
        """Initializes the background thread structure and spins up its inner domain processor."""
        super().__init__(bbox, interval, event_queue, worker_name, strategy_config)
        self.processor = CvProcessor(strategy_config, worker_name=self.name)
        self.cooldown_seconds = self.processor.cooldown_seconds

    def process(self) -> None:
        """Captures the display sub-region and passes matrices to the processor engine."""
        cg_image = self.capture_screen_image()
        if not cg_image:
            return

        width = CGImageGetWidth(cg_image)
        height = CGImageGetHeight(cg_image)
        bytes_per_row = CGImageGetBytesPerRow(cg_image)
        provider = CGImageGetDataProvider(cg_image)
        data_bytes = CGDataProviderCopyData(provider)

        img_np = np.frombuffer(data_bytes, dtype=np.uint8).reshape((height, bytes_per_row))
        img_np = img_np[:, :width * 4].reshape((height, width, 4))
        frame = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)

        match_event = self.processor.process_frame(frame)

        if match_event:
            log.debug(f"[{self.name}] Match confirmed. Relaying template update details onto central queue.")
            self.event_queue.put(match_event)
            self.enter_cooldown()

    def enter_cooldown(self) -> None:
        """Suspends this worker thread using an interruptible low-overhead polling loop."""
        if self.cooldown_seconds <= 0:
            return

        log.info(f"[{self.name}] Entering hibernation cooldown mode for {self.cooldown_seconds}s.")
        ticks = int(self.cooldown_seconds)
        for _ in range(ticks):
            if not self.running:
                break
            time.sleep(1.0)
