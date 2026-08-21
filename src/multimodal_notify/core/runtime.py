# core/runtime.py
import argparse
import queue
import logging
from .dispatcher import CoreDispatcher
from .processors.ocr_processor import OCRProcessor
from profiles import PROFILE_REGISTRY

def main():
    parser = argparse.ArgumentParser(description="Multimodal Poller Runtime Engine")
    parser.add_argument("--strategies", nargs="+", choices=["ocr"], default=["ocr"])
    parser.add_argument("--profile", choices=PROFILE_REGISTRY.keys(), required=True)
    args = parser.parse_args()

    # Instantiatethread-safe Queue object
    event_queue = queue.Queue()

    # Load profile configuration
    profile_config = PROFILE_REGISTRY[args.profile]
    profile_strategies = profile_config["strategies"]
    logging.info(f"Loaded Profile: {args.profile.upper()}")

    ocr_processor = OCRProcessor(profile_config)
    
    dispatcher = CoreDispatcher()
    dispatcher.initialize_workers(args.strategies, profile_strategies, event_queue)
    dispatcher.start_all()

    logging.info("Main Event Router active. Listening for thread events...")

    try:
        while True:
            try:
                event = event_queue.get(timeout=0.1)
                
                # Route event by processor source
                if event["source"] == "OCR":
                    new_instances = ocr_processor.process_frame_text(event["raw_data"])
                    for instance in new_instances:
                        print(f"New message instance: {instance['text_normalized']}")

                # Tell the queue the task is complete
                event_queue.task_done()
                
            except queue.Empty:
                continue
                
    except KeyboardInterrupt:
        logging.info("Shutting down core runtime.")
    finally:
        dispatcher.stop_all()

if __name__ == "__main__":
    main()
