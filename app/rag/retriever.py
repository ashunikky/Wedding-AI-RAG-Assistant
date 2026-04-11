def retrieve_docs(retriever, query):
    docs = retriever.invoke(query)

    same_side = [d for d in docs if d.metadata.get("side") != "common"]
    common = [d for d in docs if d.metadata.get("side") == "common"]

    return same_side + common