"""
ingestion/ingest.py
--------------------
Loads every parsed Markdown file under parsed/<department>/, tags each with
its department as metadata, chunks it with MarkdownNodeParser (chunking by
heading/table structure rather than raw sentence-splitting -- this was a
deliberate fix after the default SentenceSplitter was found to split a
multi-row leave-policy table mid-table, causing incomplete answers), embeds
the chunks with a local Ollama embedding model, and stores everything in a
persistent Chroma collection.

Run:
    python ingestion/ingest.py
"""

from pathlib import Path

import chromadb
from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARSED_DIR = PROJECT_ROOT / "parsed"
CHROMA_DIR = str(PROJECT_ROOT / "chroma_db")
COLLECTION_NAME = "org_docs"

DEPARTMENTS = ["HR", "Finance", "Legal", "Customer_Service", "IT"]

# Configure global settings: local embedding model, cloud LLM (used only if
# anything downstream calls Settings.llm during indexing), and the Markdown-
# aware node parser that fixed the table-splitting issue.
Settings.embed_model = OllamaEmbedding(model_name="nomic-embed-text")
Settings.llm = Ollama(model="gpt-oss:20b-cloud", request_timeout=120.0, context_window=8192)
Settings.node_parser = MarkdownNodeParser()


def load_documents():
    documents = []
    for dept in DEPARTMENTS:
        dept_dir = PARSED_DIR / dept
        if not dept_dir.exists():
            continue

        dept_docs = []
        for md_file in sorted(dept_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            dept_docs.append(
                Document(
                    text=text,
                    metadata={"file_name": md_file.name, "department": dept},
                )
            )

        print(f"Loaded {len(dept_docs)} doc(s) from {dept}")
        documents.extend(dept_docs)

    return documents


def main():
    documents = load_documents()
    print(f"\nTotal documents loaded: {len(documents)}")

    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    print("Embedding and indexing into Chroma... (this may take a few minutes)")
    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )

    print(f"\nDone. Vector store saved to ./{Path(CHROMA_DIR).name}")


if __name__ == "__main__":
    main()
