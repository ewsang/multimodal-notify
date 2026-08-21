import threading
import abc
import logging
import mss

class BaseWorker(threading.Thread, abc.ABC):
    def __init__(self, bbox, interval, event_queue, worker_name):
        super().__init__(daemon=True)
        self.bbox = self._clamp_to_screen_bounds(bbox)
        self.interval = interval
        self.running = False
        self.event_queue = event_queue
        self.worker_name = worker_name

    def _clamp_to_screen_bounds(self, bbox):
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
            logging.warning(f"[{self.__class__.__name__}] Bounding box adjusted from {(x,y,w,h)} to {(safe_x, safe_y, safe_w, safe_h)} for safety.")

        return (safe_x, safe_y, safe_w, safe_h)

    def stop(self):
        self.running = False

    @abc.abstractmethod
    def run(self):
        pass
