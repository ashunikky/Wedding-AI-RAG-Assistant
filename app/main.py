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
from app.services.image_service import ImageService

image_service = ImageService()

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

# ------------------ HELPERS ------------------

def safe_str(val):
    """Safely convert any metadata value to lowercase string for comparison."""
    if val is None:
        return ""
    if isinstance(val, list):
        return ", ".join(str(i) for i in val if i is not None).lower()
    return str(val).lower()

# ------------------ EVENT ENGINE ------------------

def parse_datetime(date_str, time_str):
    return IST.localize(datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M"))


def calculate_event_status(start_dt, end_dt):
    now = datetime.now(IST)

    is_today = start_dt.date() == now.date()
    diff_seconds = (start_dt - now).total_seconds()

    if now < start_dt:
        status = "upcoming"
    elif now > end_dt:
        status = "completed"
    else:
        total = (end_dt - start_dt).total_seconds()
        elapsed = (now - start_dt).total_seconds()
        percent = (elapsed / total) * 100

        if percent <= 15:
            status = "just_started"
        elif percent <= 85:
            status = "live"
        else:
            status = "ending"

    if status in ["live", "just_started", "ending"]:
        time_hint = "ongoing"
    elif is_today and diff_seconds > 0 and diff_seconds <= 3600:
        time_hint = "starting very soon"
    elif is_today and diff_seconds > 0:
        time_hint = "happening today"
    elif 86400 < diff_seconds <= 172800:
        time_hint = "happening tomorrow"
    else:
        time_hint = "upcoming"

    return {
        "status": status,
        "is_today": is_today,
        "time_hint": time_hint,
        "minutes_to_start": int(diff_seconds / 60)
    }

# ------------------ IMAGE (SMART VERSION) ------------------

def normalize(text):
    return (
        (text or "")
        .lower()
        .replace("-", " ")
        .replace("_", " ")
        .replace(".", "")
        .strip()
    )


def extract_image_from_response(docs, answer, next_event=None):
    answer_norm = normalize(answer)

    best_match = None
    best_score = 0

    # 🔥 Alias support (for developer / Ashu case)
    aliases = {
        "ashu": "ashutosh",
        "dev": "developer"
    }

    # =========================================================
    # ✅ PRIORITY 1: NEXT EVENT (SOURCE OF TRUTH)
    # =========================================================
    if next_event:
        event_name = normalize(next_event.get("event") or next_event.get("title"))
        event_words = event_name.split()

        if any(w in answer_norm for w in event_words):
            image_id = next_event.get("image_id")
            if image_id:
                return image_service.get_url(image_id)

    # =========================================================
    # ✅ PRIORITY 2: SCORING-BASED MATCHING
    # =========================================================
    for d in docs:
        meta = d.metadata
        image_id = meta.get("image_id")

        if not image_id:
            continue

        event_val = normalize(meta.get("event"))
        title_val = normalize(meta.get("title"))
        name_val  = normalize(meta.get("name"))

        combined = f"{event_val} {title_val} {name_val}".strip()

        if not combined:
            continue

        words = combined.split()

        score = 0

        # ✅ Strong match: full name (very important for person)
        if name_val and name_val in answer_norm:
            score += 5

        # ✅ Title match
        if title_val and title_val in answer_norm:
            score += 3

        # ✅ Word-level match
        for w in words:
            if len(w) > 2 and w in answer_norm:
                score += 1

        # ✅ Alias match (Ashu → Ashutosh, dev → developer)
        for short, full in aliases.items():
            if short in answer_norm and full in combined:
                score += 3

        # ✅ Slight boost for person (helps developer/groom cases)
        if meta.get("type") == "person":
            score += 1

        # Track best match
        if score > best_score:
            best_score = score
            best_match = image_id

    # =========================================================
    # ✅ FINAL RETURN (NO FALLBACK — SAFE)
    # =========================================================
    if best_match:
        return image_service.get_url(best_match)

    return None
# ------------------ PINECONE ------------------

def fetch_by_filter(filter_dict, top_k=20):
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

    now = datetime.now(IST)

    events = []

    for meta in results:
        date = meta.get("date")
        start_time = meta.get("start_time")
        end_time = meta.get("end_time")

        if not date or not start_time or not end_time:
            continue

        date       = safe_str(date)
        start_time = safe_str(start_time)
        end_time   = safe_str(end_time)

        try:
            start_dt = parse_datetime(date, start_time)
            end_dt   = parse_datetime(date, end_time)
        except Exception:
            continue

        status_info = calculate_event_status(start_dt, end_dt)

        events.append({
            "meta": meta,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "status": status_info["status"],
            "is_today": status_info["is_today"],
            "time_hint": status_info["time_hint"],
            "minutes_to_start": status_info["minutes_to_start"]
        })

    # ✅ Always sort
    events.sort(key=lambda x: x["start_dt"])

    current_event_index = None
    next_event_index = None

    # =========================
    # ✅ CURRENT EVENT (STRICT)
    # =========================
    for i, e in enumerate(events):
        if e["start_dt"] <= now <= e["end_dt"]:
            current_event_index = i
            break

    # =========================
    # ✅ NEXT EVENT (STRICT FIX)
    # =========================
    future_events = [
        (i, e) for i, e in enumerate(events)
        if e["start_dt"] > now
    ]

    if future_events:
        next_event_index = future_events[0][0]  # already sorted

    # =========================
    # ❌ DO NOT FALLBACK TO STATUS
    # =========================

    blocks = []
    next_event_meta = None

    for i, e in enumerate(events):
        meta = e["meta"]

        is_current = "YES" if i == current_event_index else "NO"
        is_next    = "YES" if i == next_event_index else "NO"

        if is_next == "YES":
            next_event_meta = meta

        block = f"""
Title: {safe_str(meta.get("title"))}
Event: {safe_str(meta.get("event"))}
Date: {safe_str(meta.get("date"))}
Start Time: {safe_str(meta.get("start_time"))}
Location: {safe_str(meta.get("location"))}
Map: {(meta.get("map"))}

STATUS: {e["status"]}
CURRENT_EVENT: {is_current}
NEXT_EVENT: {is_next}
TODAY_EVENT: {"YES" if e["is_today"] else "NO"}
TIME_HINT: {e["time_hint"]}
MINUTES_TO_START: {e["minutes_to_start"]}
"""
        blocks.append(block)

    return "\n".join(blocks), next_event_meta

# ------------------ HOST ------------------

def get_host_block(role):
    results = fetch_by_filter({
        "type": "host",
        "side": {"$in": [role, "common"]}
    })

    return "\n".join([
        f"""
Host: {safe_str(meta.get("names"))}
Contact: {", ".join(meta.get("contact_numbers", []))}
"""
        for meta in results
    ])

# ------------------ ROUTES ------------------

@app.get("/")
def home():
    return {"message": "Wedding AI Backend Running 🚀"}


@app.post("/chat")
def chat(req: ChatRequest):

    try:
        # 🔍 RAG retrieval
        retriever = get_retriever(req.role)
        docs = retrieve_docs(retriever, req.query)

        # 🧭 Event status
        event_status_block, next_event = build_event_status_block(req.role)

        # 📞 Host
        host = get_host_block(req.role)

        # 🧾 Context
        rag_context = "\n".join([d.page_content for d in docs]) or ""

        # 🧠 Memory
        memory = get_memory(req.session_id)

        full_context = f"""
### EVENT_STATUS (TRUTH - DO NOT OVERRIDE)
{event_status_block}

### HOST INFO
{host}

### OTHER CONTEXT
{rag_context}
"""

        # 🕒 Time
        current_time = datetime.now(IST).strftime("%d %B %Y, %I:%M %p")

        # 🧠 Prompt
        prompt = build_prompt(
            req.role,
            full_context,
            memory,
            req.query,
            current_time=current_time
        )

        # 🤖 LLM CALL
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional wedding assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        # ✅ Extract answer AFTER response
        answer = response.choices[0].message.content

        # 📸 Extract image AFTER answer (correct logic)
        image_url = extract_image_from_response(docs, answer, next_event)

        # 💾 Memory
        update_memory(req.session_id, req.query, answer)

        return {
            "answer": answer,
            "sources": [d.metadata for d in docs],
            "image": image_url
        }

    except Exception as e:
        print("🔥 ERROR IN /chat:", str(e))
        return {
            "answer": "Something went wrong. Please try again.",
            "sources": [],
            "image": None
        }