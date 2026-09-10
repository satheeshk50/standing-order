from typing import Any

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "ui"


class EventCatalogEntry(BaseModel):
    event_type: str
    label: str
    default_payload: dict[str, Any]
    is_terminal: bool
    always_wakes: bool
