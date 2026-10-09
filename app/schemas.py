from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    task: str = ""
    responsible_person: str = "Not specified"
    status: str = "Not specified"


class Motion(BaseModel):
    """A formal motion. Only filled in when the transcript actually states it."""
    text: str = ""
    moved_by: str = ""
    seconded_by: str = ""
    result: str = ""  # e.g. "Carried", "Carried unanimously", "Defeated"


class MeetingMinutes(BaseModel):
    meeting_title: str = ""
    date: str = ""
    location: str = ""
    start_time: str = ""
    end_time: str = ""
    participants: list[str] = Field(default_factory=list)
    absent: list[str] = Field(default_factory=list)
    summary: str = ""
    discussion_points: list[str] = Field(default_factory=list)
    motions: list[Motion] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    important_topics: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
