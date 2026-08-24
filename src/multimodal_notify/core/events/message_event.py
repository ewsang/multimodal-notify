from dataclasses import dataclass, field
from typing import Optional, List, Dict

@dataclass
class MessageField:
    name: str
    value: str
    inline: bool = False

@dataclass
class MessageEvent:
    description: str

    timestamp: Optional[float] = None
    color: Optional[int] = None

    author: Optional[str] = None
    author_url: Optional[str] = None
    author_icon_url: Optional[str] = None

    thumbnail_url: Optional[str] = None

    title: Optional[str] = None
    title_url: Optional[str] = None

    fields: List[MessageField] = field(default_factory=list)

    footer: Optional[str] = None

    message_type: Optional[str] = None

    metadata: Dict[str, str] = field(default_factory=dict)
