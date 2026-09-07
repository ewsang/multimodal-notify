"""Thread lifecycle manager for initializing, starting, and gracefully stopping capture workers."""

import logging
from typing import List

from multimodal_notify.pipeline.workers.cv_worker import CvWorker
from multimodal_notify.pipeline.workers.ocr_worker import OcrWorker

WORKER_FACTORY = {
    "cv": CvWorker,
    "ocr": OcrWorker,
}


class WorkerDispatcher:
    """Manage active worker threads and balanced terminations."""

    def __init__(self) -> None:
        self.active_workers: List = []

    def initialize_workers(self, strategy_names: list, profile_strategies: dict, event_queue: object) -> None:
        """Instantiate distinct worker threads from requested strategy layouts."""
        for name in strategy_names:
            if name in WORKER_FACTORY:
                worker_class = WORKER_FACTORY[name]
                processed_data = profile_strategies.get(name, {})

                interval = processed_data.get("interval", 0.500)
                bbox = processed_data.get("bbox", (0, 0, 1920, 1080))
                inner_strategy_config = processed_data.get("strategy_config", {})

                worker = worker_class(
                    bbox=bbox,
                    interval=interval,
                    event_queue=event_queue,
                    worker_name=f"{name.upper()}-Worker",
                    strategy_config=inner_strategy_config
                )
                self.active_workers.append(worker)
                logging.info(f"[Dispatcher] Initialized thread '{name.upper()}-Worker'.")
            else:
                logging.warning(f"[Dispatcher] Unknown strategy requested: '{name}'")

    def start_all(self) -> None:
        """Start all background worker threads."""
        for worker in self.active_workers:
            worker.start()

    def stop_all(self) -> None:
        """Gracefully stop all running worker threads."""
        for worker in self.active_workers:
            worker.stop()
        for worker in self.active_workers:
            if worker.is_alive():
                worker.join()
