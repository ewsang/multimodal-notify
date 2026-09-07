"""Data schemas representing specific extraction data found by worker processors."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
from multimodal_notify.core.events.base_event import BaseEvent


@dataclass
class MessageField:
    """Helper field structure containing explicit Discord embed components."""

    name: str
    value: str
    inline: bool = False


@dataclass(frozen=True, kw_only=True)
class MessageEvent(BaseEvent):
    """Refactored event wrapper routing engine metadata out to connectors."""

    description: str
    message_type: str = "plain_text"
    color: Optional[int] = None
    author: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class OcrEvent(MessageEvent):
    """Data container captured by screen OCR processing pipelines."""

    id: str
    text_ocr: str
    text_normalized: str
    reaction_rules: List[dict]


@dataclass(frozen=True, kw_only=True)
class CvEvent(MessageEvent):
    """Data container captured by template computer vision processing pipelines."""

    frame: np.ndarray
    template_name: str
    notification_message: str
    reaction_rules: List[dict]
