"""Base structure definitions for outbound platform connection handlers."""

from abc import ABC, abstractmethod


class BaseConnector:
    """Abstract class outlining core event handling for system message broadcasters."""
    
    def __init__(self, connector_name: str):
        self.name = connector_name

    def handle(self, event) -> None:
        """Handle an incoming message event."""
        raise NotImplementedError

    def is_connected(self) -> bool:
        """Fallback check confirming if the connector is ready."""
        return True