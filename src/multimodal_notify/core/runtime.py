"""Core execution loop and event router for the multimodal notifier framework."""

import argparse
import queue
import logging
from pathlib import Path
from multimodal_notify.core.message_producer import MessageProducer
from multimodal_notify.core.worker_dispatcher import WorkerDispatcher
from multimodal_notify.core.processors.ocr_processor import OCRProcessor
from multimodal_notify.core.secrets import Secrets
from multimodal_notify.profiles import PROFILE_REGISTRY
from multimodal_notify.connectors import DiscordConnector
from multimodal_notify.core.message_filter import should_send_notification

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "tmp"
LOG_FILE = LOG_DIR / "runtime.log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def build_connectors(secrets, profile_config):
    discord_cfg = profile_config.get("discord", {})
    channel_id = discord_cfg.get("channel_id")
    role_map = { key.upper(): value for key, value in discord_cfg.get("roles", {}).items() }
    logging.debug(f"Channel ID: {channel_id}, Role Map: {role_map}")
    return [
        DiscordConnector(
            token=secrets.discord_token,
            channel_id=channel_id,
            role_map=role_map,
            profile_config=profile_config
        )
    ]

def main():
    parser = argparse.ArgumentParser(description="Multimodal Poller Runtime Engine")
    parser.add_argument("--strategies", nargs="+", choices=["ocr"], default=["ocr"])
    parser.add_argument("--profile", choices=PROFILE_REGISTRY.keys(), required=True)
    args = parser.parse_args()

    # Load profile configuration
    profile_config = PROFILE_REGISTRY[args.profile]
    profile_strategies = profile_config["strategies"]
    logging.info(f"Loaded Profile: {args.profile.upper()}")

    # Load secrets from .env
    secrets = Secrets()

    # Build connector instances
    connectors = build_connectors(secrets, profile_config)

    # Thread-safe queue
    event_queue = queue.Queue()

    # Instantiate processors
    ocr_processor = OCRProcessor(profile_config)
    message_producer = MessageProducer(
        connectors=connectors,
        profile_config=profile_config
    )

    dispatcher = WorkerDispatcher()
    dispatcher.initialize_workers(args.strategies, profile_strategies, event_queue)
    dispatcher.start_all()

    logging.info("Main Event Router active. Listening for thread events...")

    try:
        while True:
            try:
                event = event_queue.get(timeout=0.1)
                
                if event["source"] == "OCR":
                    new_instances = ocr_processor.process_frame_text(event["raw_data"])
                    
                    for instance in new_instances:
                        raw_text = instance['text_normalized']
                        if should_send_notification(raw_text, profile_config):
                            logging.info(f"✅ Message sent: '{raw_text}'")
                            message_producer.handle_new_message(instance)
                        else:
                            logging.info(f"🚫 Message filtered: '{raw_text}'")
                            
                event_queue.task_done()
                
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        logging.info("Shutting down core runtime.")
    finally:
        dispatcher.stop_all()

if __name__ == "__main__":
    main()
