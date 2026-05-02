import os
import shutil
from pathlib import Path
from config import config

# Compatibility fix for generated protobuf classes in some transitive deps.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

DOCUMENTS_DIR = Path("documents")
CHROMA_DIR    = Path("chroma_db")
DOCUMENTS_DIR.mkdir(exist_ok=True)
CHROMA_DIR.mkdir(exist_ok=True)

_index = None  # Cache de l'index en session


def _get_embed_model():
    """Charge le modele d'embeddings local (sentence-transformers)."""
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    return HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")


def _get_llm():
    """Retourne le LLM Anthropic pour LlamaIndex."""
    from llama_index.llms.anthropic import Anthropic
    return Anthropic(api_key=config.ANTHROPIC_API_KEY, model="claude-3-5-haiku-20241022")

def _extract_text_via_vision(file_path: str) -> str:
    """Extrait le texte via lecture standard ou via Claude Vision (OCR) pour les scans/images."""
    import base64
    from anthropic import Anthropic
    
    path = Path(file_path)
    ext = path.suffix.lower()
    
    if ext == ".txt":
        return path.read_text(encoding="utf-8")
        
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    
    def ocr_image_bytes(img_bytes, media_type):
        b64_data = base64.b64encode(img_bytes).decode("utf-8")
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}},
                    {"type": "text", "text": "Extrais tout le texte de cette image avec précision. S'il n'y a pas de texte, réponds simplement '[AUCUN TEXTE]'. Ne rajoute aucun commentaire."}
                ],
            }]
        )
        return message.content[0].text

    if ext in [".png", ".jpg", ".jpeg"]:
        media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
        return ocr_image_bytes(path.read_bytes(), media_type)
        
    if ext == ".pdf":
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        full_text = ""
        for page in doc:
            page_text = page.get_text("text").strip()
            # Si le texte fait moins de 50 caracteres, c'est probablement un scan
            if len(page_text) > 50:
                full_text += page_text + "\n\n"
            else:
                # Fallback OCR via Claude Vision
                pix = page.get_pixmap(dpi=150)  # dpi 150 est suffisant pour OCR
                img_bytes = pix.tobytes("png")
                ocr_text = ocr_image_bytes(img_bytes, "image/png")
                if "[AUCUN TEXTE]" not in ocr_text:
                    full_text += ocr_text + "\n\n"
        return full_text
        
    return ""


def build_index_from_file(file_path: str) -> dict:
    """
    Construit un index RAG a partir d'un fichier (PDF, TXT, Image).
    Stocke dans ChromaDB local.
    """
    global _index
    try:
        import chromadb
        from llama_index.core import VectorStoreIndex, Settings, Document
        from llama_index.vector_stores.chroma import ChromaVectorStore
        from llama_index.core import StorageContext

        # Config LlamaIndex
        Settings.embed_model = _get_embed_model()
        Settings.llm         = _get_llm()

        # Extraire le texte (avec OCR si necessaire)
        extracted_text = _extract_text_via_vision(file_path)
        
        if not extracted_text.strip():
            return {"success": False, "error": "Aucun texte n'a pu être extrait de ce document."}

        documents = [Document(text=extracted_text, metadata={"file_name": Path(file_path).name})]

        # ChromaDB
        chroma_client     = chromadb.PersistentClient(path=str(CHROMA_DIR))
        chroma_collection = chroma_client.get_or_create_collection("rag_docs")

        vector_store    = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        _index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=False
        )

        return {
            "success": True,
            "response": (
                f"Document indexe avec succes !\n\n"
                f"**Fichier :** {Path(file_path).name}\n"
                f"**Chunks crees :** {len(documents)} sections\n\n"
                f"Vous pouvez maintenant poser vos questions sur ce document."
            )
        }
    except Exception as e:
        return {"success": False, "error": f"Erreur lors de l'indexation : {str(e)}"}


def load_existing_index() -> bool:
    """Charge l'index ChromaDB existant s'il y en a un."""
    global _index
    try:
        import chromadb
        from llama_index.core import VectorStoreIndex, Settings
        from llama_index.vector_stores.chroma import ChromaVectorStore
        from llama_index.core import StorageContext

        Settings.embed_model = _get_embed_model()
        Settings.llm         = _get_llm()

        chroma_client     = chromadb.PersistentClient(path=str(CHROMA_DIR))
        chroma_collection = chroma_client.get_or_create_collection("rag_docs")

        if chroma_collection.count() == 0:
            return False

        vector_store    = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        _index = VectorStoreIndex.from_vector_store(
            vector_store,
            storage_context=storage_context
        )
        return True
    except Exception:
        return False


def query_document(question: str) -> str:
    """Repond a une question sur le document indexe."""
    global _index

    if _index is None:
        loaded = load_existing_index()
        if not loaded:
            return (
                "Aucun document indexe pour l'instant.\n\n"
                "**Uploadez d'abord un fichier PDF ou TXT** via le panneau lateral, "
                "puis posez votre question."
            )

    try:
        query_engine = _index.as_query_engine(similarity_top_k=3)
        # Forcer la reponse en francais
        prompt = question + "\n\n(IMPORTANT : Tu dois obligatoirement formuler ta réponse en français, même si les documents sont en anglais ou dans une autre langue.)"
        response     = query_engine.query(prompt)
        return f"**Reponse RAG :**\n\n{str(response)}"
    except Exception as e:
        return f"Erreur lors de la recherche : {str(e)}"


def reset_index() -> str:
    """Reinitialise la base ChromaDB."""
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


def run(extracted: dict) -> str:
    """Point d'entree de l'agent RAG."""
    question = extracted.get("question", "")
    if not question:
        return "Question introuvable dans votre message."
    return query_document(question)
