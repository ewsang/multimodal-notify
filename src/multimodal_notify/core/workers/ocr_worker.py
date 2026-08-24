"""Background thread worker utilizing native macOS Quartz screen capture and the Apple Vision OCR framework."""

import logging
import time
import objc
import Quartz
import Vision
from multimodal_notify.core.workers.base_worker import BaseWorker


class OCRWorker(BaseWorker):

    def __init__(self, bbox, interval, event_queue, worker_name="OCR-Worker"):
        super().__init__(bbox, interval, event_queue, worker_name)

    def _capture_and_extract(self):
        x, y, w, h = self.bbox
        region_rect = Quartz.CGRectMake(x, y, w, h)
        main_display = Quartz.CGMainDisplayID()
        cg_image = Quartz.CGDisplayCreateImageForRect(main_display, region_rect)

        if not cg_image:
            raise RuntimeError("Quartz failed to capture screen region.")

        text_request = Vision.VNRecognizeTextRequest.alloc().init()
        text_request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)

        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        success, error = handler.performRequests_error_([text_request], objc.nil)

        if not success:
            raise RuntimeError(f"Vision OCR request failed: {error}")

        results = text_request.results()
        extracted_text = []

        if results:
            for observation in results:
                top_candidate = observation.topCandidates_(1).firstObject()
                if top_candidate:
                    extracted_text.append(top_candidate.string())

        return "\n".join(extracted_text)

    def run(self):
        self.running = True
        logging.info(f"Native Apple Vision OCR active. Monitoring safe region: {self.bbox}")

        while self.running:
            loop_start_time = time.time()

            try:
                sanitized_text = self._capture_and_extract().strip()

                if sanitized_text:
                    logging.debug(f"Vision engine raw match: {repr(sanitized_text)}")
                    event_payload = {
                        "source": "OCR",
                        "timestamp": time.time(),
                        "raw_data": sanitized_text
                    }
                    self.event_queue.put(event_payload)

            except Exception as e:
                logging.exception(f"Exception caught inside native OCR execution loop: {e}")

            elapsed = time.time() - loop_start_time
            sleep_time = max(0.01, self.interval - elapsed)
            time.sleep(sleep_time)

        logging.info("Native OCR Worker thread cleanly terminated.")
