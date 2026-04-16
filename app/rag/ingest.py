import os
import json
from datetime import datetime
import pytz

from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from app.config import OPENAI_API_KEY

from pinecone import Pinecone
from app.config import PINECONE_API_KEY

# ------------------ CONFIG ------------------

DATA_PATH = "data"
IST = pytz.timezone("Asia/Kolkata")

embedding = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=OPENAI_API_KEY
)

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index("wedding-ai")

# ------------------ HELPERS ------------------

# In convert_to_text, the title line should use the person's name if available
def convert_to_text(title, data):
    lines = [f"Title: {title}"]
    name = data.get("name")
    if name:
        lines.append(f"Name: {name}")   # ← ensures name is prominent for retrieval
    for key, value in data.items():
        if key == "name":
            continue  # already added
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        lines.append(f"{key.replace('_', ' ').title()}: {value}")
    return "\n".join(lines)


def parse_event_times(content):
    """
    Convert start_time and end_time into timestamps
    """
    try:
        date = content.get("date")
        start = content.get("start_time")
        end = content.get("end_time")

        if not date or not start or not end:
            return None, None

        start_dt = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{date} {end}", "%Y-%m-%d %H:%M")

        start_dt = IST.localize(start_dt)
        end_dt = IST.localize(end_dt)

        return int(start_dt.timestamp()), int(end_dt.timestamp())

    except Exception as e:
        return None, None

def clean_metadata(metadata):
    cleaned = {}
    # Fields that must always be strings, never lists
    FORCE_STRING_FIELDS = {"event", "title", "type", "side", "date", 
                           "start_time", "end_time", "location", "map", 
                           "note", "food", "name", "status"}

    for k, v in metadata.items():
        if v is None:
            continue
        elif k in FORCE_STRING_FIELDS:
            # Force these to always be plain strings
            cleaned[k] = ", ".join(str(i) for i in v) if isinstance(v, list) else str(v)
        elif isinstance(v, list):
            cleaned[k] = [str(i) for i in v if i is not None]
        elif isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        else:
            cleaned[k] = str(v)

    return cleaned

def load_json_files():
    documents = []

    for side in ["ladkewale", "ladkiwale", "common"]:
        folder_path = os.path.join(DATA_PATH, side)

        if not os.path.exists(folder_path):
            continue

        for file in os.listdir(folder_path):
            if file.endswith(".json"):
                file_path = os.path.join(folder_path, file)

                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                    for item in data:
                        title = item.get("title", "")
                        content = item.get("data", {})

                        # ⚠️ Avoid mutating original metadata
                        metadata = dict(item.get("metadata", {}))

                        # ✅ Always include side
                        metadata["side"] = side

                        # ✅ Convert structured → text for embeddings
                        text = convert_to_text(title, content)

                        # ================== EVENT HANDLING ==================
                        if metadata.get("type") == "event":

                            # 🔥 Smart location handling
                            location = content.get("location")

                            if not location:
                                origin = content.get("origin_location")
                                destination = content.get("destination_location")

                                if origin and destination:
                                    location = f"{origin} to {destination}"
                                elif origin:
                                    location = origin
                                elif destination:
                                    location = destination

                            # 🔥 Smart map handling
                            map_link = (
                                content.get("map")
                                or content.get("origin_map")
                                or content.get("destination_map")
                            )

                            clean_data = {
                                "title": title,
                                "event": content.get("event"),
                                "date": content.get("date"),
                                "start_time": content.get("start_time"),
                                "end_time": content.get("end_time"),
                                "location": location,
                                "map": map_link,
                                "note": content.get("note"),
                                "food": content.get("food"),
                                "image_id": content.get("image_id"),
                            }

                            # ✅ Remove None values
                            clean_data = {k: v for k, v in clean_data.items() if v is not None}

                            metadata.update(clean_data)

                            # 🔥 Add timestamps (CRITICAL for event sorting)
                            start_ts, end_ts = parse_event_times(content)

                            if start_ts and end_ts:
                                metadata["start_timestamp"] = start_ts
                                metadata["end_timestamp"] = end_ts

                                # 🔥 BONUS: store start_ts separately for sorting
                                metadata["event_start_ts"] = start_ts

                        # ================== HOST / COORDINATOR ==================
                        elif metadata.get("type") == "person":

                            name = content.get("name")
                            numbers = content.get("contact_numbers")
                            image_id = content.get("image_id")  # 🔥 IMPORTANT

                            metadata.update({
                                "title": title,
                                "name": name,
                                "image_id": image_id,  # 🔥 ADD THIS
                            })

                            # ✅ Ensure list format
                            if isinstance(numbers, list) and len(numbers) > 0:
                                metadata["contact_numbers"] = numbers
                            elif isinstance(numbers, str):
                                metadata["contact_numbers"] = [numbers]

                        # ================== FINAL CLEANUP ==================

                        # ✅ Store text for better retrieval
                        metadata["text"] = text

                        # ✅ Clean metadata (remove None, empty, invalid types)
                        metadata = clean_metadata(metadata)

                        # ✅ Create vector (stable ID to avoid duplicates)
                        documents.append({
                            "id": f"{side}-{hash(text)}",
                            "values": embedding.embed_query(text),
                            "metadata": metadata
                        })

    return documents

# ------------------ INGEST ------------------

def ingest():
    print("🔄 Loading data...")
    docs = load_json_files()

    print(f"📄 Loaded {len(docs)} documents")

    if not docs:
        print("❌ No documents found!")
        return

    print("🧹 Clearing Pinecone index (if exists)...")

    try:
        index.delete(delete_all=True)
        print("✅ Existing vectors cleared")
    except Exception:
        print("ℹ️ No existing vectors found (first run)")

    print("🧠 Uploading to Pinecone...")

    batch_size = 100

    for i in range(0, len(docs), batch_size):
        index.upsert(vectors=docs[i:i+batch_size])

    print("✅ Ingestion complete!")


if __name__ == "__main__":
    ingest()