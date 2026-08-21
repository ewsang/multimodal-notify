import time
import logging
import objc
import Quartz.CoreGraphics
import Vision
from core.workers.base_worker import BaseWorker

class OCRWorker(BaseWorker):
    def __init__(self, bbox, interval, event_queue, worker_name):
        """
        bbox: tuple (x, y, w, h) - safely clamped by BaseWorker
        interval: float - polling delay in seconds
        event_queue: queue.Queue - thread-safe channel back to runtime.py
        """
        super().__init__(bbox, interval, event_queue, worker_name="OCR-Worker")

    def _capture_and_extract(self):
        """
        Handles the raw macOS-native heavy lifting.
        Captures the region with Quartz and extracts text using Apple's Vision framework.
        """
        x, y, w, h = self.bbox
        region_rect = Quartz.CGRectMake(x, y, w, h)
        main_display = Quartz.CGMainDisplayID()
        
        # 1. Native Hardware Screen Grab
        cg_image = Quartz.CGDisplayCreateImageForRect(main_display, region_rect)
        if not cg_image:
            raise RuntimeError("Quartz failed to capture screen region.")
            
        # 2. Configure Apple Vision Request
        text_request = Vision.VNRecognizeTextRequest.alloc().init()
        text_request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        
        # 3. Process the native CGImage data through macOS Neural Engine/GPU
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        success, error = handler.performRequests_error_([text_request], objc.nil)
        if not success:
            raise RuntimeError(f"Vision OCR request failed: {error}")
            
        # 4. Compile the top text string candidates
        results = text_request.results()
        extracted_text = []
        
        if results:
            for observation in results:
                top_candidate = observation.topCandidates_(1).firstObject()
                if top_candidate:
                    extracted_text.append(top_candidate.string())
                    
        return "\n".join(extracted_text)

    def run(self):
        """The continuous non-blocking polling loop running in its own background thread."""
        self.running = True
        logging.info(f"Native Apple Vision OCR active. Monitoring safe region: {self.bbox}")

        while self.running:
            loop_start_time = time.time()
            
            try:
                # Fire off our compartmentalized helper
                sanitized_text = self._capture_and_extract().strip()
                
                # If text is found, pass it to our pipeline queue instead of returning!
                if sanitized_text:
                    logging.debug(f"Vision engine raw match: {repr(sanitized_text)}")
                    
                    event_payload = {
                        "source": "OCR",
                        "timestamp": time.time(),
                        "raw_data": sanitized_text
                    }
                    
                    # Dispatch to runtime event queue
                    self.event_queue.put(event_payload)

            except Exception as e:
                logging.exception(f"Exception caught inside native OCR execution loop: {e}")

            # Smart interval calculations (protects your CPU against drift)
            elapsed = time.time() - loop_start_time
            sleep_time = max(0.01, self.interval - elapsed)
            
            time.sleep(sleep_time)

        logging.info("Native OCR Worker thread cleanly terminated.")
