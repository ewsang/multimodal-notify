"""Environment variable loading and structural secrets validation interface."""

import os

from dotenv import load_dotenv


class Secrets:
    """Loads sensitive project credentials and configuration tokens from environment files."""

    def __init__(self):
        """Initializes secrets context and executes environment configuration extraction."""
        load_dotenv()
        self.discord_token = os.getenv("DISCORD_BOT_TOKEN")
