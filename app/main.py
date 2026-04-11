from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from openai import OpenAI
from datetime import datetime
import pytz

from app.models import ChatRequest
from app.config import OPENAI_API_KEY
from app.rag.vectorstore import get_retriever, index, embedding
from app.rag.retriever import retrieve_docs
from app.rag.prompt import build_prompt
from app.memory.session_memory import get_memory, update_memory
from app.utils.image_handler import get_image

# ------------------ INIT ------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=OPENAI_API_KEY)
IST = pytz.timezone("Asia/Kolkata")

# ------------------ EVENT STATUS ENGINE ------------------

def parse_datetime(date_str, time_str):
    return IST.localize(datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M"))


def calculate_event_status(start_dt, end_dt):
    now = datetime.now(IST)

    if now < start_dt:
        return "upcoming"
    elif now > end_dt:
        return "completed"
    else:
        total = (end_dt - start_dt).total_seconds()
        elapsed = (now - start_dt).total_seconds()

        percent = (elapsed / total) * 100

        if percent <= 15:
            return "just_started"
        elif percent <= 85:
            return "live"
        else:
            return "ending"


# ------------------ PINECONE HELPERS ------------------

def fetch_by_filter(filter_dict, top_k=20):
    """
    Generic Pinecone metadata fetch using dummy query
    """
    dummy_embedding = embedding.embed_query("wedding")

    results = index.query(
        vector=dummy_embedding,
        top_k=top_k,
        include_metadata=True,
        filter=filter_dict
    )

    return [m["metadata"] for m in results["matches"]]


# ------------------ EVENT STATUS BLOCK ------------------

def build_event_status_block(role):
    results = fetch_by_filter({
        "type": "event",
        "side": {"$in": [role, "common"]}
    })

    blocks = []

    for meta in results:
        date = meta.get("date")
        start_time = meta.get("start_time")
        end_time = meta.get("end_time")

        if not date or not start_time or not end_time:
            continue

        start_dt = parse_datetime(date, start_time)
        end_dt = parse_datetime(date, end_time)

        status = calculate_event_status(start_dt, end_dt)

        block = f"""
Title: {meta.get("title", "")}
Event: {meta.get("event", "")}
Date: {date}
Start Time: {start_time}
End Time: {end_time}
Location: {meta.get("location", "")}
Map: {meta.get("map", "")}
STATUS: {status}
"""
        blocks.append(block)

    return "\n".join(blocks)


# ------------------ HOST BLOCK ------------------

def get_host_block(role):
    results = fetch_by_filter({
        "type": "host",
        "side": {"$in": [role, "common"]}
    })

    blocks = []

    for meta in results:
        block = f"""
Host: {meta.get("names", "")}
Contact: {", ".join(meta.get("contact_numbers", []))}
"""
        blocks.append(block)

    return "\n".join(blocks)


# ------------------ ROUTES ------------------

@app.get("/")
def home():
    return {"message": "Wedding AI Backend Running 🚀"}


@app.post("/chat")
def chat(req: ChatRequest):

    # 🔍 RAG retrieval
    retriever = get_retriever(req.role)
    docs = retrieve_docs(retriever, req.query)

    # 📞 Host
    host = get_host_block(req.role)

    rag_context = "\n".join([d.page_content for d in docs]) or ""

    # 🧠 Memory
    memory = get_memory(req.session_id)

    # 🧭 Event status
    event_status_block = build_event_status_block(req.role)

    full_context = f"""
### EVENT_STATUS (TRUTH - DO NOT OVERRIDE)
{event_status_block}

### HOST INFO (USE WHEN NEEDED)
{host}

### OTHER CONTEXT
{rag_context}
"""

    # 🕒 Current time
    current_time = datetime.now(IST).strftime("%d %B %Y, %I:%M %p")

    # 🧠 Prompt
    prompt = build_prompt(
        req.role,
        full_context,
        memory,
        req.query,
        current_time=current_time
    )

    # 🤖 LLM
    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": "You are a professional wedding assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    answer = response.choices[0].message.content

    # 💾 Memory
    update_memory(req.session_id, req.query, answer)

    return {
        "answer": answer,
        "sources": [d.metadata for d in docs],
        "image": get_image(req.query)
    }