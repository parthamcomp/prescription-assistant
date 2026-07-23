from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.extraction import extract_prescription_from_text
from app.models import ChatRequest, ChatResponse, OCRResult, Prescription, PrescriptionCreate
from app.ocr import extract_text_from_image
from app.rag import rag
from app.storage import store

def _reindex() -> None:
    rag.rebuild_index(store.list_all())


@asynccontextmanager
async def lifespan(app: FastAPI):
    _reindex()
    yield


app = FastAPI(
    title="Medical Prescription Assistant",
    description="Local prescription knowledge base with OCR and chat",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/prescriptions", response_model=list[Prescription])
async def list_prescriptions():
    return store.list_all()


@app.get("/api/prescriptions/{prescription_id}", response_model=Prescription)
async def get_prescription(prescription_id: str):
    prescription = store.get(prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return prescription


@app.post("/api/prescriptions", response_model=Prescription)
async def create_prescription(prescription: PrescriptionCreate):
    saved = store.create(prescription)
    _reindex()
    return saved


@app.put("/api/prescriptions/{prescription_id}", response_model=Prescription)
async def update_prescription(prescription_id: str, prescription: PrescriptionCreate):
    updated = store.update(prescription_id, prescription)
    if not updated:
        raise HTTPException(status_code=404, detail="Prescription not found")
    _reindex()
    return updated


@app.delete("/api/prescriptions/{prescription_id}")
async def delete_prescription(prescription_id: str):
    if not store.delete(prescription_id):
        raise HTTPException(status_code=404, detail="Prescription not found")
    _reindex()
    return {"deleted": True}


@app.post("/api/ocr", response_model=OCRResult)
async def ocr_prescription(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload an image file (JPEG, PNG, etc.)")

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 10 MB")

    try:
        raw_text = extract_text_from_image(image_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"OCR failed: {exc}") from exc

    if not raw_text:
        raise HTTPException(
            status_code=422,
            detail="No text detected. Try a clearer photo with good lighting.",
        )

    extracted = await extract_prescription_from_text(raw_text)
    return OCRResult(raw_text=raw_text, extracted=extracted)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    answer, sources = await rag.answer(question)
    return ChatResponse(answer=answer, sources=sources)


@app.post("/api/reindex")
async def reindex():
    _reindex()
    return {"indexed": len(store.list_all())}