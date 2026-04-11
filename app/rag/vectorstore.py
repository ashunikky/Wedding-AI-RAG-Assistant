from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from app.config import OPENAI_API_KEY, PINECONE_API_KEY

# ------------------ EMBEDDING ------------------

embedding = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=OPENAI_API_KEY
)

# ------------------ PINECONE INIT ------------------

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index("wedding-ai")

# ------------------ RETRIEVER ------------------

class PineconeRetriever:
    def __init__(self, role):
        self.role = role

    def invoke(self, query):
        query_vector = embedding.embed_query(query)

        results = index.query(
            vector=query_vector,
            top_k=7,
            include_metadata=True,
            filter={
                "side": {"$in": [self.role, "common"]}
            }
        )

        docs = []

        for match in results["matches"]:
            metadata = match["metadata"]

            # recreate Document-like object
            docs.append(type("Doc", (), {
                "page_content": metadata.get("text", ""),
                "metadata": metadata
            }))

        return docs


# ------------------ PUBLIC FUNCTION ------------------

def get_retriever(role):
    return PineconeRetriever(role)