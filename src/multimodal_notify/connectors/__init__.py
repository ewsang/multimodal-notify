"""Exposes broadcast connector interfaces for dispatching system events."""

from .discord_connector import DiscordConnector

__all__ = ["DiscordConnector"]
