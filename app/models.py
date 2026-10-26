"""Request/response shapes.

The stroke model is intentionally permissive: a pen stroke carries `points`, a
rectangle carries `geometry`, and a text note carries `text` and `font`. All three
live in one collection with no migration between them, which is the flexible-schema
property the project set out to demonstrate.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Tool = Literal["pen", "eraser", "line", "rect", "ellipse", "text"]


class Point(BaseModel):
    x: float
    y: float
    p: float = 0.5  # pen pressure, when the device reports it


class Style(BaseModel):
    color: str = "#111827"
    width: float = 3.0
    opacity: float = 1.0
    # Eraser strokes are stored as ordinary strokes drawn with a cut-out blend
    # mode, so replay stays correct on any background colour.
    blend: Literal["source-over", "destination-out"] = "source-over"


class Geometry(BaseModel):
    x: float
    y: float
    w: float
    h: float


class StrokeCreate(BaseModel):
    tool: Tool = "pen"
    style: Style = Field(default_factory=Style)
    points: list[Point] | None = None
    geometry: Geometry | None = None
    text: str | None = None
    font: str | None = None
    clientMsgId: str | None = None


class StrokeStyleUpdate(BaseModel):
    """The UPDATE half of CRUD: restyle a stroke that already exists."""

    color: str | None = None
    width: float | None = None
    opacity: float | None = None


class RoomCreate(BaseModel):
    name: str = "Untitled board"
    background: str = "#ffffff"
    createdBy: str = "anonymous"
    gridVisible: bool = True


class RoomUpdate(BaseModel):
    name: str | None = None
    background: str | None = None
    gridVisible: bool | None = None
    isArchived: bool | None = None


class Participant(BaseModel):
    userId: str
    userName: str
    color: str = "#2563eb"
    lastSeenAt: datetime | None = None


class RoomOut(BaseModel):
    id: str
    code: str
    name: str
    background: str
    settings: dict[str, Any]
    participants: list[Participant] = []
    strokeCount: int = 0
    createdBy: str
    createdAt: datetime
    updatedAt: datetime
    lastActivityAt: datetime
    isArchived: bool = False


class JoinRequest(BaseModel):
    userId: str
    userName: str
