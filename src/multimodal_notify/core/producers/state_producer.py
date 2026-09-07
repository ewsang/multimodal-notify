"""Orchestrates internal system and telemetry event notification delivery."""

import logging

from multimodal_notify.core.events.state_event import StateEvent

log = logging.getLogger(__name__)


class StateProducer:
    """Format and dispatch system telemetry status events to connectors."""

    def __init__(self, connectors: list, profile_config: dict):
        """Initialize producer with delivery pipelines and user configs."""
        self.connectors = connectors
        self.profile_config = profile_config

    def handle_state_change(self, event: StateEvent) -> None:
        """Translate StateEvent into standard layout and route to endpoints."""
        if not self.profile_config.get("enable_system_notifications", True):
            return

        log.debug(
            f"[StateProducer] Dispatching system notification across "
            f"{len(self.connectors)} connector(s)."
        )
        
        for connector in self.connectors:
            try:
                connector.handle_new_message(event) 
            except Exception as e:
                log.error(
                    f"[StateProducer] Failed to route state alert via "
                    f"{connector.__class__.__name__}: {e}"
                )

    def shutdown(self) -> None:
        """Wind down persistent resources managed by the state engine."""
        log.info("State producer tracking hooks terminated.")
