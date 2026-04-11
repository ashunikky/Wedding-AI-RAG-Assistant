session_memory = {}

def get_memory(session_id):
    return session_memory.get(session_id, [])

def update_memory(session_id, query, answer):
    if session_id not in session_memory:
        session_memory[session_id] = []

    session_memory[session_id].append({
        "query": query,
        "answer": answer
    })

    # Keep last 5 messages
    session_memory[session_id] = session_memory[session_id][-5:]