# core/dispatcher.py
import logging
from .workers import OCRWorker

WORKER_FACTORY = {
    "ocr": OCRWorker
}

class CoreDispatcher:
    def __init__(self):
        self.active_workers = []

    def initialize_workers(self, strategy_names, profile_strategies, event_queue):
        """
        Instantiates requested worker threads using unique bounding boxes 
        and time intervals specified by the runtime profile config.
        """
        for name in strategy_names:
            if name in WORKER_FACTORY:
                worker_class = WORKER_FACTORY[name]
                
                # Extract parameters tailored exclusively to this specific worker type
                strategy_config = profile_strategies.get(name, {})
                interval = strategy_config.get("interval", 0.500)
                bbox = strategy_config.get("bbox", (0, 0, 1920, 1080))
                
                # Instantiate worker utilizing its unique screen dimensions
                worker = worker_class(
                    bbox=bbox, 
                    interval=interval, 
                    event_queue=event_queue,
                    worker_name=f"{name.upper()}-Worker"
                )
                
                self.active_workers.append(worker)
                logging.info(f"[Dispatcher] Launched '{name.upper()}' thread. Region: {bbox} | Interval: {interval}s")
            else:
                logging.warning(f"[Dispatcher] Unknown strategy requested: '{name}'")

    def start_all(self):
        for worker in self.active_workers:
            worker.start()

    def stop_all(self):
        for worker in self.active_workers:
            worker.stop()
        for worker in self.active_workers:
            if worker.is_alive():
                worker.join()
