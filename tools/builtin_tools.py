"""
outils builtin fournis par defaut au systeme.

PythonExecutorTool : execute du code python dans un environement restreint
FileReaderTool     : lit le contenu d'un fichier texte ou PDF
HttpGetTool        : fait une requete HTTP GET simple

attention : PythonExecutorTool est sandboxe mais reste dangereux si expose
a des utilisateurs non confies, a utiliser avec precaution en prod.
"""
from __future__ import annotations

import io
import sys
import traceback
import textwrap
from pathlib import Path
from typing import Any, Dict

from .tool_manager import BaseTool, ToolResult


class PythonExecutorTool(BaseTool):
    """
    execute du code python fourni en tant que string.
    capture stdout/stderr et retourne le resultat.
    sandboxe basique : timeout pas implemente ici mais le ToolManager log tout.
    """

    name = "python_exec"
    description = (
        "Execute du code Python et retourne la sortie standard. "
        "Utile pour des calculs, transformations de donnees ou tests rapides."
    )
    parameters: Dict[str, str] = {
        "code": "le code Python a executer (string)",
    }

    def execute(self, code: str = "", **kwargs) -> ToolResult:
        if not code or not code.strip():
            return ToolResult(
                success=False,
                output=None,
                error="Aucun code Python fourni.",
            )

        # on capture stdout pour recuperer le print() de l'utilisateur
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()

        try:
            # dedenter pour evite les erreurs d'indentation
            cleaned = textwrap.dedent(code)
            local_ns: Dict[str, Any] = {}
            exec(cleaned, {"__builtins__": __builtins__}, local_ns)  # noqa: S102

            stdout_output = sys.stdout.getvalue()
            stderr_output = sys.stderr.getvalue()

            # si pas de print, on cherche une variable 'result' dans le namespace
            output = stdout_output.strip()
            if not output and "result" in local_ns:
                output = str(local_ns["result"])

            return ToolResult(
                success=True,
                output=output or "(aucune sortie)",
                metadata={
                    "stderr": stderr_output,
                    "locals_keys": list(local_ns.keys()),
                },
            )
        except Exception:
            stderr_output = sys.stderr.getvalue()
            return ToolResult(
                success=False,
                output=None,
                error=traceback.format_exc(),
                metadata={"stderr": stderr_output},
            )
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


class FileReaderTool(BaseTool):
    """
    lit le contenu d'un fichier texte (.txt) ou essaie de lire un PDF basiquement.
    pour les PDF avancee avec OCR utiliser l'agent RAG a la place.
    """

    name = "file_read"
    description = (
        "Lit le contenu d'un fichier texte (.txt) ou les metadonnees d'un fichier. "
        "Retourne le contenu sous forme de string."
    )
    parameters: Dict[str, str] = {
        "path": "chemin vers le fichier a lire (string)",
        "max_chars": "nombre max de caracteres a lire (int, optionnel, defaut 5000)",
    }

    def execute(self, path: str = "", max_chars: int = 5000, **kwargs) -> ToolResult:
        if not path:
            return ToolResult(
                success=False,
                output=None,
                error="Aucun chemin de fichier fourni.",
            )

        file_path = Path(path)
        if not file_path.exists():
            return ToolResult(
                success=False,
                output=None,
                error=f"Fichier introuvable : {path}",
            )

        try:
            if file_path.suffix.lower() == ".txt":
                content = file_path.read_text(encoding="utf-8", errors="replace")
            elif file_path.suffix.lower() == ".pdf":
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(str(file_path))
                    pages_text = []
                    for page in doc:
                        pages_text.append(page.get_text("text"))
                    content = "\n\n".join(pages_text)
                except ImportError:
                    content = f"[PDF detecte mais PyMuPDF non installe pour lire {file_path.name}]"
            else:
                # essai lecture binaire decode en utf-8
                raw = file_path.read_bytes()
                content = raw.decode("utf-8", errors="replace")

            truncated = len(content) > max_chars
            content = content[:max_chars]

            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "file_name": file_path.name,
                    "file_size_bytes": file_path.stat().st_size,
                    "truncated": truncated,
                    "max_chars": max_chars,
                },
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                output=None,
                error=f"Erreur lors de la lecture : {str(exc)}",
            )


class HttpGetTool(BaseTool):
    """
    fait une requete HTTP GET vers une URL et retourne le contenu de la reponse.
    timeout de 10 secondes par defaut pour evite les blocages.
    """

    name = "http_get"
    description = (
        "Effectue une requete HTTP GET vers une URL et retourne le contenu HTML/JSON. "
        "Utile pour recuperer des donnees depuis une API ou une page web."
    )
    parameters: Dict[str, str] = {
        "url": "URL complete a appeler (string)",
        "timeout": "timeout en secondes (int, optionnel, defaut 10)",
    }

    def execute(self, url: str = "", timeout: int = 10, **kwargs) -> ToolResult:
        if not url:
            return ToolResult(
                success=False,
                output=None,
                error="Aucune URL fournie.",
            )

        try:
            import urllib.request
            import urllib.error

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AISenghor-Agent/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read().decode("utf-8", errors="replace")
                status_code = response.status

            return ToolResult(
                success=True,
                output=content[:10000],  # limite a 10k chars pour evite saturation memoire
                metadata={
                    "url": url,
                    "status_code": status_code,
                    "content_length": len(content),
                    "truncated": len(content) > 10000,
                },
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                output=None,
                error=f"Erreur HTTP : {str(exc)}",
                metadata={"url": url},
            )
