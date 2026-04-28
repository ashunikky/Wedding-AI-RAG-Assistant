# Wedding AI Assistant (RAG-Based)

An AI-powered Wedding Assistant built to help guests get real-time event information naturally—just like asking a human host.

This project combines **React + FastAPI + OpenAI + Pinecone** to create a multilingual, role-aware, time-aware wedding assistant that answers guest queries about functions, timings, locations, contacts, and event guidance.

Live URL (FastAPI) : https://wedding-ai-rag-assistant-backend.onrender.com/

---

## 🚀 Features

### 🧠 Conversational Wedding Assistant

Guests can ask natural questions like:

* “Haldi kab hai?”
* “Abhi kya chal raha hai?”
* “Next function kya hai?”
* “Venue ka location bhejo”
* “Coordinator ka contact number kya hai?”

The assistant responds naturally in the same language as the user.

---

### 🎭 Role-Based Context (Critical)

Supports role-specific responses for:

* `ladkewale`
* `ladkiwale`
* `common`

This prevents data leakage and ensures the assistant provides only relevant information for that side.

---

### ⏱️ Real-Time Event Awareness

The backend computes live event status using IST-based time logic:

* upcoming
* just_started
* live
* ending
* completed

This removes LLM hallucination around time-sensitive answers.

---

### 🔥 Deterministic Next Event Logic

Instead of letting the LLM guess the next function, the backend:

* sorts events by time
* detects the nearest upcoming event
* injects it as the highest-priority context

This ensures accurate “next event” responses.

---

### 🌍 Multilingual Support

Supports natural responses in:

* Hindi
* Hinglish
* English

The assistant detects the user’s language and replies accordingly.

---

### 📍 Maps + Contact Assistance

Provides:

* Google Maps links
* Host / coordinator contact info
* Event directions and guidance

---

### 🖼️ Image Mapping

Relevant images can be mapped to events and shown alongside responses for a richer guest experience.

---

## 🏗️ Tech Stack

### Backend

* FastAPI
* Python

### AI / RAG

* OpenAI GPT (`gpt-5.4-mini`)
* OpenAI Embeddings (`text-embedding-3-small`)
* Pinecone Vector Database
* LangChain

### Other

* Session memory
* JSON-based structured event storage
* Prompt engineering with deterministic control blocks

---

## 📂 Project Structure

```text
backend/
│── app/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── rag/
│   │   ├── retriever.py
│   │   ├── ingest.py
│   │   ├── vectorstore.py
│   │   └── prompt.py
│   ├── memory/
│   │   └── session_memory.py
│   └── utils/
│       └── image_handler.py
│
│── data/
│   ├── ladkewale/
│   ├── ladkiwale/
│   └── common/
│
│── requirements.txt
│── .env
```

---

## 🧩 How RAG Works

### Stored Data

Structured JSON documents containing:

* events
* timings
* locations
* map links
* notes
* hosts
* contact numbers
* family information

---

### Retrieval Flow

```text
User Query
→ Role-Based Retrieval
→ Event Status Injection
→ Host Info Injection
→ Session Memory
→ Prompt Building
→ LLM Response
```

---

### Why This Matters

RAG alone was not enough.

Real users asked:

* “Abhi kya chal raha hai?”
* “Next function kya hai?”

Even with correct data, the LLM often selected the wrong event because semantic retrieval does not guarantee correct temporal reasoning.

This was solved by moving time reasoning into the backend instead of relying on the LLM.

---

## ⚙️ Setup Instructions

## 1. Clone Repository

```bash
git clone https://github.com/ashunikky/Wedding-AI-RAG-Assistant.git
```

---

## 2. Backend Setup

```bash
cd Wedding-AI-RAG-Assistant
```

Create virtual environment (using uv + conda if preferred)

```bash
uv sync
```

Install dependencies

```bash
pip install -r requirements.txt
```

---

## 3. Environment Variables

Create `.env`

```env
OPENAI_API_KEY=your_openai_key
PINECONE_API_KEY=your_pinecone_key
```

---

## 4. Run Data Ingestion

```bash
uv run python -m app.rag.ingest
```

This:

* reads JSON files
* creates embeddings
* uploads vectors to Pinecone

---

## 5. Run Backend

```bash
uv run uvicorn app.main:app --reload
```

Swagger docs:

```text
http://localhost:8000/docs
```

---

## 6. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

---

## 🚀 Deployment

### Backend

Deployed on Render

### Vector DB

Pinecone (cloud)

---

## 🔥 Key Problems Solved

### ❌ Wrong Next Event Detection

Fixed by:

* sorting events by time
* injecting `NEXT_EVENT`

---

### ❌ Tense Errors

Fixed by:

* backend event status engine
* strict prompt enforcement

---

### ❌ Role Mixing

Fixed by:

* Pinecone metadata filtering

---

### ❌ Contact Retrieval Failure

Fixed by:

* structured host metadata injection

---

## 🎯 Core Insight

**RAG alone is not enough for real-world assistants.**

For production systems, deterministic control over:

* time
* role
* intent
* next actions

is often more important than better prompting.

---

## Future Improvements

* Admin panel for event updates
* Smart intent detection
* Event timeline UI
* Google Maps route integration
* Cost optimization + caching
* Production analytics

---

## Author

Built as a real-world production-focused AI assistant project to solve wedding guest coordination problems using practical RAG architecture instead of demo-only chatbot logic.
