"""Input contract for the future audit feature; examples are synthetic."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: str
    status: Literal["ordered", "available", "not_documented"]
    value: str | None = None
    unit: str | None = None
    available_at: datetime | None = None


class PatientRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    synthetic: Literal[True]
    age: int = Field(ge=0, le=120)
    diagnosis: str
    encounter: Literal["inpatient"]
    review_at: datetime
    severe: bool | None
    allergy_status: Literal["documented", "denied", "unknown"]
    observations: list[Observation]
    note: str
