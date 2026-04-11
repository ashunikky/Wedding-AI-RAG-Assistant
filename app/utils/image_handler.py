def get_image(query):
    q = query.lower()

    if "bride" in q:
        return "https://via.placeholder.com/300?text=Bride"
    elif "groom" in q:
        return "https://via.placeholder.com/300?text=Groom"
    elif "haldi" in q or "mehendi" in q:
        return "https://via.placeholder.com/300?text=Event"

    return None