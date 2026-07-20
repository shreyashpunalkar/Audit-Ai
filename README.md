# AI Checksheet to JSON Converter

**Audit AI** is a production-ready web application that converts checksheet documents (Excel, PDF, DOCX) into structured JSON using AI.

---

## Features

- 📤 **Drag-and-drop upload** — Excel, PDF, DOCX (up to 25 MB)
- 🤖 **AI-powered extraction** — Gemini 1.5 Pro identifies metadata, checks, tables, remarks
- 🌳 **Interactive JSON viewer** — expand/collapse, search, syntax highlighting
- ✏️ **JSON editor** — edit and save extracted JSON with live validation
- ✅ **Schema validation** — auto-corrects common issues, shows warnings
- 📥 **Download / Copy** — download `.json` file or copy to clipboard
- 📊 **Processing status** — 6-stage animated progress tracker

---

## Project Structure

```
Audit-Ai/
├── backend/          # FastAPI Python backend
├── frontend/         # React 18 + Vite frontend
├── docker-compose.yml
└── .env.example
```

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 16 (or use Docker)
- Google Gemini API key → [Get one here](https://aistudio.google.com/app/apikey)
- Tesseract OCR (for image fallback): `brew install tesseract` on Mac

---

## Quick Start (Local Development)

### 1. Clone & Configure

```bash
git clone <repo>
cd Audit-Ai

# Configure backend
cp backend/.env.example backend/.env
# Edit backend/.env and set GEMINI_API_KEY
```

### 2. Backend Setup

```bash
cd backend

# Create virtualenv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start backend (auto-creates DB tables)
uvicorn app.main:app --reload --port 8000
```

Backend runs at: http://localhost:8000  
API docs: http://localhost:8000/api/docs

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:5173

---

## Docker Deployment (Production)

```bash
# 1. Set your Gemini API key in backend/.env
cp backend/.env.example backend/.env
# Edit GEMINI_API_KEY=your_key_here

# 2. Start all services
docker-compose up --build -d

# 3. Access the app
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/api/docs
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/upload` | Upload a document |
| POST | `/api/process/{id}` | Start AI extraction |
| GET | `/api/document/{id}` | Get document + JSON |
| PUT | `/api/document/{id}/json` | Update JSON |
| GET | `/api/download/{id}` | Download JSON file |
| DELETE | `/api/document/{id}` | Delete document |

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | **Required.** Google Gemini API key | — |
| `DATABASE_URL` | PostgreSQL async connection URL | localhost:5432 |
| `MAX_UPLOAD_SIZE_MB` | Max upload file size in MB | 25 |
| `ALLOWED_ORIGINS` | CORS allowed origins (comma-separated) | localhost:5173 |
| `UPLOAD_DIR` | Directory for uploaded files | ./uploads |

---

## Supported File Types

| Format | Extension | Extraction Method |
|--------|-----------|-------------------|
| Excel | .xlsx, .xls | pandas + openpyxl |
| PDF | .pdf | pdfplumber (text + tables) |
| Word | .docx | python-docx |

---

## Tech Stack

**Backend**: FastAPI · PostgreSQL · SQLAlchemy (async) · Google Gemini 1.5 Pro · pdfplumber · python-docx · pandas · pytesseract · Pydantic v2

**Frontend**: React 18 · Vite · Axios · Lucide React · Vanilla CSS (glassmorphism dark theme)

**Infrastructure**: Docker · Docker Compose · Nginx

---

## License

MIT