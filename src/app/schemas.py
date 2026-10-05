"""Structured data contracts used by the home assistant API."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CalendarEvent(BaseModel):
    """A candidate home-calendar event extracted from a user's message."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "needs_clarification", "out_of_scope"] = Field(
        description=(
            "Use ready when a home event has a clear title and date; use "
            "needs_clarification when either is missing or ambiguous; use "
            "out_of_scope when the message is not a home-calendar event."
        )
    )
    title: NonEmptyText | None = Field(
        description="The event title, or null when it cannot be identified."
    )
    date_text: NonEmptyText | None = Field(
        description=(
            "The date or date phrase exactly as stated by the user, or null "
            "when none was provided. Do not calculate a calendar date."
        )
    )
    time_text: NonEmptyText | None = Field(
        description="The time or time phrase exactly as stated, or null if omitted."
    )
    participants: list[NonEmptyText] = Field(
        description="People explicitly named as participants; empty when none are named."
    )
    location: NonEmptyText | None = Field(
        description="The event location exactly as stated, or null if omitted."
    )
    clarifying_question: NonEmptyText | None = Field(
        description=(
            "One short question when status is needs_clarification; otherwise null."
        )
    )

    @field_validator(
        "title",
        "date_text",
        "time_text",
        "location",
        "clarifying_question",
        mode="before",
    )
    @classmethod
    def empty_optional_text_is_null(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().casefold() in {
            "",
            "unknown",
            "unspecified",
            "not specified",
            "not provided",
            "n/a",
        }:
            return None
        return value

    @field_validator("participants", mode="before")
    @classmethod
    def discard_empty_participants(cls, value: object) -> object:
        if isinstance(value, list):
            placeholders = {"", "unknown", "unspecified", "not specified", "not provided", "n/a"}
            return [
                item
                for item in value
                if not isinstance(item, str) or item.strip().casefold() not in placeholders
            ]
        return value

    @model_validator(mode="after")
    def validate_status_fields(self) -> "CalendarEvent":
        if self.status == "ready" and (not self.title or not self.date_text):
            raise ValueError("ready events require a title and date_text")
        if self.status == "needs_clarification" and not self.clarifying_question:
            raise ValueError("needs_clarification events require a clarifying_question")
        if self.status == "out_of_scope" and (
            any(value is not None for value in (self.title, self.date_text, self.time_text, self.location))
            or self.participants
            or self.clarifying_question is not None
        ):
            raise ValueError("out_of_scope responses cannot contain event details")
        return self


class EventExtractionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    temperature: float | None = Field(default=None, ge=0, le=1)


class EventExtractionResponse(BaseModel):
    event: CalendarEvent
    model: str
    latency_ms: int


class PendingActionSummary(BaseModel):
    id: str
    tool_name: str
    description: str
    expires_at: str


class ActionDecision(BaseModel):
    confirm: bool
