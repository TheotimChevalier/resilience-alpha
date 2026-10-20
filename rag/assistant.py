import base64
import hashlib
import hashlib
import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from glob import glob

from fastapi import Depends, FastAPI, Header, HTTPException
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", "/app/documents")
CHROMA_DIR = os.getenv("CHROMA_DIR", "/app/chroma")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
TOKEN_SECRET = os.getenv("AUTH_SIGNING_SECRET")
if not TOKEN_SECRET or len(TOKEN_SECRET) < 32:
    raise RuntimeError("AUTH_SIGNING_SECRET must contain at least 32 characters")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("rag-assistant")
retriever = None
llm = None


def _source_documents(source: str):
    relative_source = os.path.relpath(source, DOCUMENTS_DIR)
    documents = TextLoader(source, encoding="utf-8").load()
    for document in documents:
        document.metadata["source"] = relative_source
    return RecursiveCharacterTextSplitter(
        chunk_size=700,
        chunk_overlap=100,
        add_start_index=True,
    ).split_documents(documents)


def _sync_source(vectorstore, source: str) -> int:
    documents = _source_documents(source)
    relative_source = os.path.relpath(source, DOCUMENTS_DIR)
    ids = [
        hashlib.sha256(
            f"{relative_source}\0{index}\0{document.page_content}".encode("utf-8")
        ).hexdigest()
        for index, document in enumerate(documents)
    ]
    existing = vectorstore.get(where={"source": relative_source})
    existing_ids = set(existing["ids"])
    expected_ids = set(ids)
    stale_ids = existing_ids - expected_ids
    if stale_ids:
        vectorstore.delete(ids=sorted(stale_ids))
    missing_indexes = [
        index for index, identifier in enumerate(ids) if identifier not in existing_ids
    ]
    if missing_indexes:
        vectorstore.add_documents(
            [documents[index] for index in missing_indexes],
            ids=[ids[index] for index in missing_indexes],
        )
    return len(documents)


def _remove_deleted_sources(vectorstore, sources: list[str]) -> None:
    active_sources = {
        os.path.relpath(source, DOCUMENTS_DIR)
        for source in sources
    }
    existing = vectorstore.get()
    stale_ids = [
        identifier
        for identifier, metadata in zip(existing["ids"], existing["metadatas"])
        if metadata.get("source") not in active_sources
    ]
    if stale_ids:
        vectorstore.delete(ids=stale_ids)


def _decode_payload(encoded: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


def require_operator(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Operator bearer token required")
    try:
        header, payload, signature = authorization.removeprefix("Bearer ").split(".")
        signed = f"{header}.{payload}".encode("ascii")
        expected = base64.urlsafe_b64encode(
            hmac.new(TOKEN_SECRET.encode(), signed, hashlib.sha256).digest()
        ).rstrip(b"=").decode("ascii")
        claims = _decode_payload(payload)
        if (
            not hmac.compare_digest(signature, expected)
            or claims.get("iss") != "resilience-auth"
            or float(claims.get("exp", 0)) <= time.time()
        ):
            raise ValueError("invalid token")
        return claims["sub"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, base64.binascii.Error) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired operator token") from exc


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global retriever, llm
    sources = sorted(glob(os.path.join(DOCUMENTS_DIR, "**", "*.md"), recursive=True))
    if not sources:
        raise RuntimeError(f"No Markdown source documents found in {DOCUMENTS_DIR}")

    embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    vectorstore = Chroma(
        collection_name="resilience-alpha-operations-v2",
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
    )
    _remove_deleted_sources(vectorstore, sources)
    chunk_count = sum(_sync_source(vectorstore, source) for source in sources)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
    llm = OllamaLLM(model=LLM_MODEL, temperature=0.1, base_url=OLLAMA_BASE_URL)
    logger.info(
        "Indexed %s documentation chunks from %s using %s and %s.",
        chunk_count,
        len(sources),
        LLM_MODEL,
        EMBED_MODEL,
    )
    yield


app = FastAPI(
    title="Resilience Alpha Local Operator Assistant",
    version="1.0.0",
    lifespan=lifespan,
)


class Question(BaseModel):
    question: str = Field(min_length=5, max_length=1000)


@app.get("/health")
def health():
    if retriever is None or llm is None:
        raise HTTPException(status_code=503, detail="Assistant is not initialized")
    return {"status": "ok", "model": LLM_MODEL}


@app.post("/ask")
def ask(question: Question, _operator: str = Depends(require_operator)):
    if retriever is None or llm is None:
        raise HTTPException(status_code=503, detail="Assistant is not initialized")

    docs = retriever.invoke(question.question)
    if not docs:
        return {"answer": "Aucune procédure pertinente trouvée dans la documentation indexée.", "sources": []}

    context = "\n\n".join(
        f"[{doc.metadata.get('source', 'document')}]\n{doc.page_content}"
        for doc in docs
    )
    prompt = (
        "Tu es l'assistant local d'exploitation de Resilience Alpha. Réponds en français, "
        "de façon concise et uniquement à partir du contexte fourni. Si le contexte ne permet "
        "pas de répondre, indique-le clairement. Tu peux expliquer les procédures, mais ne "
        "déclenche jamais d'action ni ne demande de secrets.\n\n"
        f"Contexte documentaire:\n{context}\n\nQuestion: {question.question}"
    )
    answer = llm.invoke(prompt)
    return {
        "answer": answer,
        "sources": sorted({doc.metadata.get("source", "document") for doc in docs}),
    }
