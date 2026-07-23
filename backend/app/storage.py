import json
import os
from pathlib import Path

from app.config import settings
from app.models import Prescription


class PrescriptionStore:
    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir or settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "prescriptions.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.file_path.exists():
            self._write([])

    def _read(self) -> list[dict]:
        with open(self.file_path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, records: list[dict]) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, default=str)

    def list_all(self) -> list[Prescription]:
        return [Prescription.model_validate(r) for r in self._read()]

    def get(self, prescription_id: str) -> Prescription | None:
        for record in self._read():
            if record.get("id") == prescription_id:
                return Prescription.model_validate(record)
        return None

    def create(self, prescription: Prescription) -> Prescription:
        records = self._read()
        records.append(prescription.model_dump(mode="json"))
        self._write(records)
        return prescription

    def update(self, prescription_id: str, prescription: Prescription) -> Prescription | None:
        records = self._read()
        for i, record in enumerate(records):
            if record.get("id") == prescription_id:
                prescription.id = prescription_id
                records[i] = prescription.model_dump(mode="json")
                self._write(records)
                return prescription
        return None

    def delete(self, prescription_id: str) -> bool:
        records = self._read()
        filtered = [r for r in records if r.get("id") != prescription_id]
        if len(filtered) == len(records):
            return False
        self._write(filtered)
        return True


store = PrescriptionStore()