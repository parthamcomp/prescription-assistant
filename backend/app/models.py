from datetime import date
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Medication(BaseModel):
    name: str = ""
    dosage: str = ""
    frequency: str = ""
    duration: str = ""


class Prescription(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    doctor_name: str = ""
    date_of_visit: Optional[date] = None
    complaint: str = ""
    diagnosis: str = ""
    medications: list[Medication] = Field(default_factory=list)
    child_age: str = ""
    child_weight: str = ""
    additional_notes: str = ""
    source_text: str = ""


class PrescriptionCreate(Prescription):
    pass


class OCRResult(BaseModel):
    raw_text: str
    extracted: Prescription


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)