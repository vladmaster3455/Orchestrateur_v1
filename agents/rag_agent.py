"""
Agent RAG : analyse et interrogation de documents via LlamaIndex + ChromaDB.
Principe SOLID :
  - SRP : responsabilite unique = repondre a des questions sur des documents.
  - OCP : les strategies d'extraction et d'indexation sont extensibles.
  - LSP : respecte entierement le contrat BaseAgent.
  - DIP : depend d'abstractions (config, LlamaIndex) pas d'implementations concretes.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import config

from .base_agent import AgentCapability, AgentResult, BaseAgent

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

DOCUMENTS_DIR = Path("data/documents")
CHROMA_DIR = Path("data/chroma_db")
DOCUMENTS_DIR.mkdir(exist_ok=True, parents=True)
CHROMA_DIR.mkdir(exist_ok=True, parents=True)

# Index partage en session (singleton de module)
_index = None


# ----------------------------------------------------------------------
# Helpers LlamaIndex / LLM
# ----------------------------------------------------------------------


# modeles de fallback charges depuis l'env (LLM_FALLBACK_MODELS dans .env)
# si non defini, liste vide : le systeme utilise uniquement LLM_MODEL
_LLM_FALLBACKS = [
    m.strip() for m in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if m.strip()
]


def _llm_model_candidates() -> List[str]:
    """retourne la liste des modeles a essayer dans l'ordre."""
    preferred = config.LLM_MODEL.strip()
    seen: set = set()
    result: List[str] = []
    for m in [preferred] + _LLM_FALLBACKS:
        m = m.strip()
        if m and m not in seen:
            seen.add(m)
            result.append(m)
    return result


def _get_embed_model():
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    return HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")


def _get_llm():
    from llama_index.llms.anthropic import Anthropic

    return Anthropic(api_key=config.LLM_API_KEY, model=_llm_model_candidates()[0])


# ----------------------------------------------------------------------
# Extraction de texte (OCR via vision LLM si necessaire)
# ----------------------------------------------------------------------


def _extract_text_via_vision(file_path: str) -> str:
    """Extrait le texte d'un fichier. Utilise le LLM vision pour les scans et images."""
    import base64

    from anthropic import Anthropic

    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".txt":
        return path.read_text(encoding="utf-8")

    client = Anthropic(api_key=config.LLM_API_KEY)

    def ocr_image_bytes(img_bytes: bytes, media_type: str) -> str:
        b64_data = base64.b64encode(img_bytes).decode("utf-8")
        last_error: Optional[Exception] = None
        for model_name in _llm_model_candidates():
            try:
                payload: Any = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Extrais tout le texte de cette image avec precision. "
                                    "S'il n'y a pas de texte, reponds simplement '[AUCUN TEXTE]'. "
                                    "Ne rajoute aucun commentaire."
                                ),
                            },
                        ],
                    }
                ]
                message = client.messages.create(
                    model=model_name,
                    max_tokens=4096,
                    messages=payload,  # type: ignore[arg-type]
                )
                first = message.content[0]
                # .text existe sur TextBlock, on utilise getattr pour les autres types
                return str(getattr(first, "text", str(first)))
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(
            f"OCR indisponible pour tous les modeles configures : {last_error}"
        )

    if ext in [".png", ".jpg", ".jpeg"]:
        media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
        return ocr_image_bytes(path.read_bytes(), media_type)

    if ext == ".pdf":
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        full_text = ""
        for page in doc:
            page_text = str(page.get_text("text")).strip()
            if len(page_text) > 50:
                full_text += page_text + "\n\n"
            else:
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                ocr_text = ocr_image_bytes(img_bytes, "image/png")
                if "[AUCUN TEXTE]" not in ocr_text:
                    full_text += ocr_text + "\n\n"
        return full_text

    return ""


# ----------------------------------------------------------------------
# Indexation et interrogation
# ----------------------------------------------------------------------


def build_index_from_file(file_path: str) -> Dict[str, Any]:
    """
    Construit un index RAG a partir d'un fichier (PDF, TXT, Image).
    Stocke dans ChromaDB local.
    """
    global _index
    try:
        import chromadb
        from llama_index.core import (
            Document,
            Settings,
            StorageContext,
            VectorStoreIndex,
        )
        from llama_index.vector_stores.chroma import ChromaVectorStore

        Settings.embed_model = _get_embed_model()
        Settings.llm = _get_llm()

        extracted_text = _extract_text_via_vision(file_path)

        if not extracted_text.strip():
            return {
                "success": False,
                "error": "Aucun texte n'a pu etre extrait de ce document.",
            }

        documents = [
            Document(text=extracted_text, metadata={"file_name": Path(file_path).name})
        ]

        chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        chroma_collection = chroma_client.get_or_create_collection("rag_docs")
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        _index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=False,
        )

        return {
            "success": True,
            "response": (
                f"Document indexe avec succes.\n\n"
                f"**Fichier :** {Path(file_path).name}\n"
                f"**Sections creees :** {len(documents)}\n\n"
                "Vous pouvez maintenant poser vos questions sur ce document."
            ),
        }
    except Exception as e:
        print(f"[RAG][build_index_from_file] {e}")
        return {
            "success": False,
            "error": (
                "Le document n'a pas pu etre indexe. "
                "Verifiez la cle API ou reessayez dans quelques instants."
            ),
        }


def load_existing_index() -> bool:
    """Charge l'index ChromaDB existant s'il y en a un."""
    global _index
    try:
        import chromadb
        from llama_index.core import Settings, StorageContext, VectorStoreIndex
        from llama_index.vector_stores.chroma import ChromaVectorStore

        Settings.embed_model = _get_embed_model()
        Settings.llm = _get_llm()

        chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        chroma_collection = chroma_client.get_or_create_collection("rag_docs")

        if chroma_collection.count() == 0:
            return False

        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        _index = VectorStoreIndex.from_vector_store(
            vector_store,
            storage_context=storage_context,
        )
        return True
    except Exception:
        return False


def query_document(question: str) -> str:
    """Repond a une question sur le document indexe."""
    global _index

    if _index is None:
        loaded = load_existing_index()
        if not loaded or _index is None:
            return (
                "Aucun document indexe pour l'instant.\n\n"
                "Uploadez d'abord un fichier PDF ou TXT, "
                "puis posez votre question."
            )

    try:
        assert _index is not None
        query_engine = _index.as_query_engine(similarity_top_k=3)
        prompt = (
            question + "\n\n(IMPORTANT : Formulez votre reponse en francais, "
            "meme si les documents sont dans une autre langue.)"
        )
        response = query_engine.query(prompt)
        return f"**Reponse RAG :**\n\n{response!s}"
    except Exception as e:
        print(f"[RAG][query_document] {e}")
        return (
            "Impossible d'interroger le document pour le moment. "
            "Reessayez dans quelques instants."
        )


def reset_index() -> str:
    """Reinitialise la base ChromaDB et le cache."""
    global _index
    _index = None
    try:
        if CHROMA_DIR.exists():
            shutil.rmtree(CHROMA_DIR)
            CHROMA_DIR.mkdir(exist_ok=True)
        if DOCUMENTS_DIR.exists():
            shutil.rmtree(DOCUMENTS_DIR)
            DOCUMENTS_DIR.mkdir(exist_ok=True)
        return "Base de connaissances reinitialisee avec succes."
    except Exception as e:
        return f"Erreur lors de la reinitialisation : {str(e)}"


# ----------------------------------------------------------------------
# Agent
# ----------------------------------------------------------------------


class RAGAgent(BaseAgent):
    """
    Agent specialise dans la question-reponse sur des documents indexes.
    """

    name = "RAG"
    description = (
        "Analyse et interroge des documents (PDF, images, textes). "
        "Repond a des questions basees sur le contenu indexe."
    )

    @property
    def capabilities(self) -> List[AgentCapability]:
        return [
            AgentCapability(
                name="question_document",
                description=(
                    "Repond a une question en cherchant la reponse dans les documents "
                    "prealablement uploades et indexes."
                ),
                required_params=["question"],
                examples=[
                    "Quel est le theme principal de ce document ?",
                    "Resume les trois points cles du rapport",
                    "Quelle est la conclusion de cette etude ?",
                ],
            ),
            AgentCapability(
                name="indexation_document",
                description=(
                    "Indexe un document PDF, TXT ou image (PNG, JPG) "
                    "pour permettre des recherches semantiques dessus."
                ),
                required_params=["file"],
                examples=[
                    "Charge ce PDF et reponds a mes questions",
                    "Analyse ce document et dis-moi ce qu'il contient",
                ],
            ),
        ]

    def run(self, extracted: Dict[str, Any], **kwargs) -> AgentResult:
        question = (
            extracted.get("question", "") or kwargs.get("user_text", "")
        ).strip()
        pending_context: Dict[str, Any] = kwargs.get("pending_context") or {}

        if not question:
            question = (pending_context.get("question", "") or "").strip()

        if not question:
            return AgentResult(
                status="needs_input",
                response="Quelle question souhaitez-vous poser sur le document ?",
                context=pending_context,
            )

        has_index = _index is not None or load_existing_index()
        if not has_index:
            return AgentResult(
                status="needs_input",
                response=(
                    "Aucun document indexe pour l'instant. "
                    "Uploadez un document, puis je repondrai automatiquement a votre question."
                ),
                context={"question": question},
            )

        answer = query_document(question)
        if answer.startswith("Impossible d'interroger"):
            return AgentResult(
                status="failed",
                response=answer,
                context={"question": question},
            )

        return AgentResult(
            status="completed",
            response=answer,
            context={"question": question},
        )
