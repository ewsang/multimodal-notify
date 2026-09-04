"""Base structure definitions for outbound platform connection handlers."""

from abc import ABC, abstractmethod


class BaseConnector(ABC):
    """Abstract class outlining core event handling for system message broadcasters."""

    def __init__(
        self,
        connector_name: str
    ):
        """Initializes the base connector with a uniform tracking name."""
        self.name = connector_name

    @abstractmethod
    def handle(self, event):
        """Abstract method implemented by subclasses to process outbound event records."""
        pass
