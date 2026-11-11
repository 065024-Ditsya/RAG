"""
Comparative analysis: Chroma vs Qdrant
Ingests the same parsed documents into Qdrant, then times a few sample
queries against both stores so you can report actual numbers.
"""
import time
from pathlib import Path

import chromadb
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, Settings
from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.vector_stores.qdrant import QdrantVectorStore
import qdrant_client

PARSED_DIR = Path("parsed")
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "org_docs"

Settings.embed_model = OllamaEmbedding(model_name="nomic-embed-text")
Settings.llm = Ollama(model="granite4.1:3b", request_timeout=120.0, context_window=8192)
Settings.node_parser = MarkdownNodeParser()

TEST_QUESTIONS = [
    "How many paid leave days do I get in a year?",
    "What happens if I lose a device with client data on it?",
    "What are the per diem allowances for domestic travel?",
]


def load_documents():
    all_docs = []
    for dept_dir in PARSED_DIR.iterdir():
        if not dept_dir.is_dir():
            continue
        reader = SimpleDirectoryReader(input_dir=str(dept_dir), required_exts=[".md"])
        docs = reader.load_data()
        for doc in docs:
            doc.metadata["department"] = dept_dir.name
        all_docs.extend(docs)
    return all_docs


def build_chroma_index(documents):
    start = time.time()
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
    elapsed = time.time() - start
    return index, elapsed


def build_qdrant_index(documents):
    start = time.time()
    client = qdrant_client.QdrantClient(host="localhost", port=6333)
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
    elapsed = time.time() - start
    return index, elapsed


def time_queries(index, label):
    engine = index.as_query_engine(similarity_top_k=5)
    results = []
    for q in TEST_QUESTIONS:
        start = time.time()
        response = engine.query(q)
        elapsed = time.time() - start
        results.append((q, elapsed, str(response)[:100]))
        print(f"  [{label}] '{q[:40]}...' -> {elapsed:.2f}s")
    return results


def main():
    print("Loading documents...")
    documents = load_documents()
    print(f"Loaded {len(documents)} documents\n")

    print("=== Building Chroma index ===")
    chroma_index, chroma_ingest_time = build_chroma_index(documents)
    print(f"Chroma ingestion time: {chroma_ingest_time:.2f}s\n")

    print("=== Building Qdrant index ===")
    qdrant_index, qdrant_ingest_time = build_qdrant_index(documents)
    print(f"Qdrant ingestion time: {qdrant_ingest_time:.2f}s\n")

    print("=== Query latency: Chroma ===")
    chroma_results = time_queries(chroma_index, "Chroma")

    print("\n=== Query latency: Qdrant ===")
    qdrant_results = time_queries(qdrant_index, "Qdrant")

    print("\n\n===== SUMMARY (copy into your report) =====")
    print(f"{'Metric':<30}{'Chroma':<15}{'Qdrant':<15}")
    print(f"{'Ingestion time (s)':<30}{chroma_ingest_time:<15.2f}{qdrant_ingest_time:<15.2f}")
    for i, q in enumerate(TEST_QUESTIONS):
        c_time = chroma_results[i][1]
        q_time = qdrant_results[i][1]
        print(f"Query {i+1} latency (s){'':<12}{c_time:<15.2f}{q_time:<15.2f}")


if __name__ == "__main__":
    main()
