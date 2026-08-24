"""Environment variable loading and structural secrets validation interface."""

import os
from dotenv import load_dotenv


class Secrets:

    def __init__(self):
        load_dotenv()
        self.discord_token = os.getenv("DISCORD_BOT_TOKEN")
