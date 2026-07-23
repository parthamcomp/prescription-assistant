import httpx

from app.config import settings
from app.models import Prescription


def _prescription_to_document(p: Prescription) -> str:
    meds = "\n".join(
        f"  - {m.name}: {m.dosage}, {m.frequency}, for {m.duration}"
        for m in p.medications
    )
    return f"""Visit ID: {p.id}
Doctor: {p.doctor_name}
Date: {p.date_of_visit or 'unknown'}
Child age: {p.child_age}
Child weight: {p.child_weight}
Complaint: {p.complaint}
Diagnosis: {p.diagnosis}
Medications:
{meds or '  (none recorded)'}
Notes: {p.additional_notes}
"""


class PrescriptionRAG:
    def __init__(self):
        self._chroma = None
        self._collection = None
        self._embedder = None

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(settings.embedding_model)
        return self._embedder

    def _get_collection(self):
        if self._collection is None:
            import chromadb

            self._chroma = chromadb.PersistentClient(path=f"{settings.data_dir}/chroma")
            self._collection = self._chroma.get_or_create_collection(
                name=settings.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def rebuild_index(self, prescriptions: list[Prescription]) -> None:
        collection = self._get_collection()
        embedder = self._get_embedder()

        existing = collection.get()
        if existing["ids"]:
            collection.delete(ids=existing["ids"])

        if not prescriptions:
            return

        documents = [_prescription_to_document(p) for p in prescriptions]
        ids = [p.id for p in prescriptions]
        embeddings = embedder.encode(documents).tolist()

        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=[
                {
                    "doctor_name": p.doctor_name,
                    "date_of_visit": str(p.date_of_visit or ""),
                }
                for p in prescriptions
            ],
        )

    def query(self, question: str, top_k: int = 4) -> list[tuple[str, str]]:
        collection = self._get_collection()
        if collection.count() == 0:
            return []

        embedder = self._get_embedder()
        query_embedding = embedder.encode([question]).tolist()

        results = collection.query(
            query_embeddings=query_embedding,
            n_results=min(top_k, collection.count()),
        )

        docs = results.get("documents", [[]])[0]
        ids = results.get("ids", [[]])[0]
        return list(zip(ids, docs))

    async def answer(self, question: str) -> tuple[str, list[str]]:
        contexts = self.query(question)
        if not contexts:
            return (
                "No prescription records found. Upload prescriptions first, then ask questions.",
                [],
            )

        context_block = "\n\n---\n\n".join(doc for _, doc in contexts)
        source_labels = [
            f"Visit {pid}" for pid, _ in contexts
        ]

        system_prompt = """You are a record-keeping assistant for a parent reviewing their child's past medical prescriptions.
You are NOT a medical professional and you are NOT being asked to recommend, decide, or advise on any dosage.
Your only job is to report facts that a licensed doctor already recorded in the past, exactly as written in the records you are given. This is retrieval of history, not new medical advice.

Rules:
- If a record shows a medication, dosage, and duration a doctor already prescribed, report those exact recorded values.
- If a record contains the exact medication, dosage, and duration relevant to the question, state that recorded information directly and confidently as your primary answer. Do not open with a disclaimer about lacking general medical guidance — only mention that if no relevant record exists at all.
- If the question mentions a symptom (e.g. "rash") that relates to a diagnosis or complaint in the records (e.g. "dermatitis"), you may make that connection to find the relevant record.
- If the specific fact is not in the records, say you don't have that information. Do not guess or add anything not written.
- Be concise and cite which visit(s) your answer comes from when possible.

Example — Question: "How much Paracetamol was given for the fever?"
Record shows: Paracetamol 5ml, three times a day, for 5 days.
Correct answer: "The record shows Paracetamol was given at 5ml, three times a day, for 5 days. (Visit 1234...)"
"""

        user_prompt = f"""PRESCRIPTION RECORDS:
{context_block}

QUESTION: {question}"""

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                answer = response.json().get("message", {}).get("content", "").strip()
                if answer:
                    return answer, source_labels
        except httpx.HTTPError:
            pass

        return (
            f"Found relevant records but Ollama is unavailable. Raw context:\n\n{context_block[:2000]}",
            source_labels,
        )


rag = PrescriptionRAG()