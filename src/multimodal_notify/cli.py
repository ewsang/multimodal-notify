"""Core execution loop and event router for the multimodal notifier framework."""

import argparse
import logging
import queue
from pathlib import Path

from multimodal_notify.connectors import DiscordConnector
from multimodal_notify.config.secrets import Secrets
from multimodal_notify.core.message_producer import MessageProducer
from multimodal_notify.pipeline.worker_dispatcher import WorkerDispatcher
from multimodal_notify.profiles import PROFILE_REGISTRY

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "tmp"
LOG_FILE = LOG_DIR / "runtime.log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)


def build_connectors(secrets: Secrets, profile_config: dict) -> list:
    """Builds and returns a list of configured connector instances."""
    discord_cfg = profile_config.get("discord", {})
    channel_id = discord_cfg.get("channel_id")
    role_map = {
        key.upper(): value 
        for key, value in discord_cfg.get("roles", {}).items()
    }
    logging.debug(f"Channel ID: {channel_id}, Role Map: {role_map}")
    return [
        DiscordConnector(
            token=secrets.discord_token,
            channel_id=channel_id,
            role_map=role_map,
            profile_config=profile_config
        )
    ]


def main() -> None:
    """Main application runtime entry point."""
    parser = argparse.ArgumentParser(
        description="Multimodal Notification Engine"
    )
    parser.add_argument(
        "--strategies", nargs="+", choices=["ocr", "cv"], default=["ocr", "cv"]
    )
    parser.add_argument(
        "--profile", choices=PROFILE_REGISTRY.keys(), required=True
    )
    args = parser.parse_args()

    profile_config = PROFILE_REGISTRY[args.profile]
    profile_strategies = profile_config["strategies"]
    logging.info(f"Loaded profile: {args.profile.upper()}")

    secrets = Secrets()
    connectors = build_connectors(secrets, profile_config)
    event_queue = queue.Queue()

    message_producer = MessageProducer(
        connectors=connectors, profile_config=profile_config
    )

    dispatcher = WorkerDispatcher()
    dispatcher.initialize_workers(
        args.strategies, profile_strategies, event_queue
    )
    dispatcher.start_all()

    logging.info("Main Event Router active. Listening for thread events...")

    try:
        while True:
            try:
                event = event_queue.get(timeout=0.1)

                if event["source"] == "OCR":
                    logging.info(
                        f"📝 OCR verified event received: "
                        f"'{event.get('text_normalized')}'"
                    )
                    message_producer.handle_new_message(event)

                elif event["source"] == "CV":
                    logging.info(
                        f"🎯 CV match confirmed event payload received for "
                        f"template: '{event['template_name']}'"
                    )
                    message_producer.handle_new_message(event)

                event_queue.task_done()
                
            except queue.Empty:
                continue
                
    except KeyboardInterrupt:
        print("")
        logging.warning("Beginning application shutdown...")
        
    finally:
        logging.info("Shutting down active background thread workers...")
        dispatcher.stop_all()
        
        logging.info("Shutting down message producer and connectors...")
        message_producer.shutdown()
        
        logging.info("Application cleanly terminated.")


if __name__ == "__main__":
    main()
