export interface Medication {
  name: string;
  dosage: string;
  frequency: string;
  duration: string;
}

export interface Prescription {
  id?: string;
  doctor_name: string;
  date_of_visit: string | null;
  complaint: string;
  diagnosis: string;
  medications: Medication[];
  child_age: string;
  child_weight: string;
  additional_notes: string;
  source_text?: string;
}

export interface OCRResult {
  raw_text: string;
  extracted: Prescription;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

export const emptyMedication = (): Medication => ({
  name: "",
  dosage: "",
  frequency: "",
  duration: "",
});

export const emptyPrescription = (): Prescription => ({
  doctor_name: "",
  date_of_visit: null,
  complaint: "",
  diagnosis: "",
  medications: [emptyMedication()],
  child_age: "",
  child_weight: "",
  additional_notes: "",
});

const API_BASE = import.meta.env.VITE_API_URL || "";

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg).join(", ")
      : detail || "Request failed";
    throw new Error(message);
  }
  return res.json();
}

export const prescriptionsApi = {
  list: () => api<Prescription[]>("/api/prescriptions"),
  create: (p: Prescription) =>
    api<Prescription>("/api/prescriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(p),
    }),
  update: (id: string, p: Prescription) =>
    api<Prescription>(`/api/prescriptions/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(p),
    }),
  delete: (id: string) =>
    api<{ deleted: boolean }>(`/api/prescriptions/${id}`, { method: "DELETE" }),
  ocr: async (file: File): Promise<OCRResult> => {
    const form = new FormData();
    form.append("file", file);
    return api<OCRResult>("/api/ocr", { method: "POST", body: form });
  },
  chat: (question: string) =>
    api<{ answer: string; sources: string[] }>("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }),
};