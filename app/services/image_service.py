import json

class ImageService:
    def __init__(self, path="data/image_url.json"):
        with open(path, "r", encoding="utf-8") as f:
            self.registry = json.load(f)

    def get_url(self, image_id: str):
        if not image_id:
            return None

        obj = self.registry.get(image_id)
        if not obj:
            return None

        return obj.get("url")