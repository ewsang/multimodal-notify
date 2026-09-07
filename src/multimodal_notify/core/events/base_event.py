"""Base data layout interface shared by all framework pipeline events."""
from dataclasses import dataclass, field
import time


@dataclass(frozen=True, kw_only=True)
class BaseEvent:
    """Abstract baseline structural layout for framework messages."""

    source: str
    timestamp: float = field(default_factory=time.time)
