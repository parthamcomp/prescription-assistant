import json
import re
from datetime import date

import httpx

from app.config import settings
from app.models import Medication, Prescription

EXTRACTION_PROMPT = """You are a medical prescription data extractor. Given OCR text from a doctor's prescription, extract structured information.

Return ONLY valid JSON with this exact schema (no markdown, no explanation):
{
  "doctor_name": "string",
  "date_of_visit": "YYYY-MM-DD or null",
  "complaint": "string",
  "diagnosis": "string",
  "medications": [
    {"name": "string", "dosage": "string", "frequency": "string", "duration": "string"}
  ],
  "child_age": "string",
  "child_weight": "string",
  "additional_notes": "string"
}

Use empty strings for unknown fields. If date is unclear, use null.
OCR text:
"""


def _parse_date(value: str | None) -> date | None:
    if not value or value == "null":
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _fallback_extract(raw_text: str) -> Prescription:
    """Rule-based fallback when Ollama is unavailable."""
    medications: list[Medication] = []
    med_patterns = re.findall(
        r"(?i)(?:rx|tab|syrup|cap|drops?)[:\s]*([^\n,;]+)",
        raw_text,
    )
    for name in med_patterns[:5]:
        medications.append(Medication(name=name.strip()))

    date_match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", raw_text)
    visit_date = None
    if date_match:
        raw = date_match.group(1).replace("/", "-")
        parts = raw.split("-")
        if len(parts) == 3 and len(parts[2]) == 2:
            parts[2] = "20" + parts[2]
        if len(parts[0]) == 4:
            visit_date = _parse_date("-".join(parts))

    return Prescription(
        doctor_name="",
        date_of_visit=visit_date,
        complaint="",
        diagnosis="",
        medications=medications,
        child_age="",
        child_weight="",
        additional_notes=raw_text[:500] if raw_text else "",
        source_text=raw_text,
    )


async def extract_prescription_from_text(raw_text: str) -> Prescription:
    prompt = EXTRACTION_PROMPT + raw_text

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            response.raise_for_status()
            body = response.json()
            content = body.get("response", "{}")
            data = json.loads(content)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError):
        return _fallback_extract(raw_text)

    medications = [
        Medication(
            name=m.get("name", ""),
            dosage=m.get("dosage", ""),
            frequency=m.get("frequency", ""),
            duration=m.get("duration", ""),
        )
        for m in data.get("medications", [])
    ]

    return Prescription(
        doctor_name=data.get("doctor_name", ""),
        date_of_visit=_parse_date(data.get("date_of_visit")),
        complaint=data.get("complaint", ""),
        diagnosis=data.get("diagnosis", ""),
        medications=medications,
        child_age=data.get("child_age", ""),
        child_weight=data.get("child_weight", ""),
        additional_notes=data.get("additional_notes", ""),
        source_text=raw_text,
    )