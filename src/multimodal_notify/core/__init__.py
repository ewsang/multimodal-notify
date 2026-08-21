import logging
import os

os.makedirs("../../tmp", exist_ok=True)

LOG_FORMAT = "%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        # Output to file for tailing
        logging.FileHandler("tmp/runtime.log", mode="a", encoding="utf-8"),
        # Keep output visible in your active terminal terminal
        logging.StreamHandler() 
    ]
)
