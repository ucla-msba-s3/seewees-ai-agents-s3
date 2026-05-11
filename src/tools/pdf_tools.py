from __future__ import annotations

from dataclasses import dataclass
import os
import hashlib

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _embedding_provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", os.getenv("LLM_PROVIDER", "openai")).strip().lower()


def _embedding_model(provider: str) -> str:
    if provider == "gemini":
        return os.getenv("EMBEDDING_MODEL", "models/text-embedding-004")
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def _get_embeddings():
    provider = _embedding_provider()
    if provider == "gemini":
        if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
            raise RuntimeError(
                "Gemini embeddings selected but no GOOGLE_API_KEY or GEMINI_API_KEY is set. "
                "Create a free-tier key in Google AI Studio and add it to .env."
            )
        if not _env_bool("GEMINI_FREE_TIER_ONLY", True):
            raise RuntimeError(
                "GEMINI_FREE_TIER_ONLY is disabled. Refusing to build Gemini embeddings in paid-mode settings."
            )
        if _env_bool("GOOGLE_GENAI_USE_VERTEXAI", False):
            raise RuntimeError(
                "GOOGLE_GENAI_USE_VERTEXAI is enabled. Free-tier guard only allows the Gemini Developer API via Google AI Studio."
            )
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(model=_embedding_model(provider))

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=_embedding_model(provider))

    raise ValueError(f"Unsupported EMBEDDING_PROVIDER={provider!r}. Use 'openai' or 'gemini'.")


@dataclass
class PdfRag:
    persist_dir: str = "chroma_db"
    collection_name: str = "business_context"

    def _fingerprint(self, pdf_path: str) -> str:
        """Stable fingerprint to detect if this exact PDF has been indexed."""
        st = os.stat(pdf_path)
        payload = f"{os.path.abspath(pdf_path)}|{st.st_size}|{int(st.st_mtime)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def build(self, pdf_path: str) -> Chroma:
        # Ensure persist dir exists before we touch it
        os.makedirs(self.persist_dir, exist_ok=True)

        provider = _embedding_provider()
        model = _embedding_model(provider)
        embeddings = _get_embeddings()
        collection_name = f"{self.collection_name}_{provider}_{hashlib.sha1(model.encode('utf-8')).hexdigest()[:8]}"
        vectordb = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=self.persist_dir,
        )

        fp = self._fingerprint(pdf_path)
        marker = os.path.join(self.persist_dir, f".indexed_{collection_name}_{fp}")

        # If marker exists AND collection is non-empty, reuse
        if os.path.exists(marker):
            try:
                if vectordb._collection.count() > 0:
                    return vectordb
            except Exception:
                # If count check fails, fall through and rebuild
                pass

        docs = PyPDFLoader(pdf_path).load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150)
        chunks = splitter.split_documents(docs)

        vectordb.add_documents(chunks)

        with open(marker, "w", encoding="utf-8") as f:
            f.write(fp)

        return vectordb

    def retriever(self, vectordb: Chroma, k: int = 6):
        return vectordb.as_retriever(search_kwargs={"k": k})
