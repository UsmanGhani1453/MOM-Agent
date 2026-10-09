from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    task: str = ""
    responsible_person: str = "Not specified"
    status: str = "Not specified"


class MeetingMinutes(BaseModel):
    meeting_title: str = ""
    date: str = ""
    participants: list[str] = Field(default_factory=list)
    summary: str = ""
    discussion_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    important_topics: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
