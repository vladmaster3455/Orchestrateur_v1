"""
Agent Email : envoi de courriels professionnels via un service de messagerie.
Principe SOLID :
  - SRP : responsabilite unique = rediger et envoyer des emails.
  - OCP : les strategies de validation/redaction sont extensibles.
  - LSP : respecte entierement le contrat BaseAgent.
  - DIP : depend de config (abstraction), pas du fournisseur directement.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from config import config

from .base_agent import AgentCapability, AgentResult, BaseAgent


class EmailContentValidator:
    """
    Valide le contenu d'un email avant envoi.
    SRP : responsabilite unique de validation.
    """

    _TRIVIAL_PHRASES = frozenset(
        {
            "salut",
            "bonjour",
            "hello",
            "hi",
            "allo",
            "coucou",
            "ok",
            "non",
            "oui",
        }
    )
    _MIN_BODY_LENGTH = 10

    @classmethod
    def extract_email_address(cls, text: str) -> str:
        match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
        return match.group(0) if match else ""

    @classmethod
    def validate_body(cls, body: str) -> Tuple[bool, str]:
        """Retourne (valide, message_erreur)."""
        if not body:
            return False, "Le message est vide."
        cleaned = body.strip()
        if len(cleaned) < cls._MIN_BODY_LENGTH:
            return False, (
                f"Le message est trop court ({len(cleaned)} caracteres). "
                f"Donnez-moi au moins {cls._MIN_BODY_LENGTH} caracteres de contenu."
            )
        if cleaned.lower() in cls._TRIVIAL_PHRASES:
            return False, (
                f"'{cleaned}' n'est pas suffisant pour un email. "
                "Expliquez ce que vous voulez communiquer."
            )
        return True, ""


class EmailComposer:
    """
    Redige un email professionnel via le LLM configure.
    SRP : responsabilite unique de redaction.
    """

    def compose(self, raw_body: str) -> Tuple[str, str]:
        """
        Retourne (corps_professionnel, sujet).
        En cas d'erreur, retourne le corps brut et 'Sans objet'.
        """
        try:
            from langchain_anthropic import ChatAnthropic
            from langchain_core.messages import HumanMessage, SystemMessage

            if not config.LLM_API_KEY:
                return raw_body, "Sans objet"

            llm = ChatAnthropic(model=config.LLM_MODEL, api_key=config.LLM_API_KEY)  # type: ignore[call-arg]
            sys_prompt = (
                f"Tu es un expert en redaction d'emails professionnels. "
                f"Basé sur cette demande : '{raw_body}'\n\n"
                "Genere DEUX parties separees par |SEP| :\n"
                "1. Un SUJET court et clair (max 10 mots)\n"
                "2. Le CORPS de l'email professionnel (salutation et signature incluses)\n\n"
                "Format strict : SUJET|SEP|CORPS\n"
                "Ne rajoute aucun commentaire."
            )
            raw_resp = llm.invoke(
                [
                    SystemMessage(content=sys_prompt),
                    HumanMessage(content="Genere l'email professionnel."),
                ]
            )
            response = str(raw_resp.content).strip()

            if "|SEP|" in response:
                parts = response.split("|SEP|", 1)
                subject = parts[0].strip() or "Sans objet"
                body = parts[1].strip() or raw_body
            else:
                subject = "Sans objet"
                body = response or raw_body

            return body, subject
        except Exception:
            return raw_body, "Sans objet"


class BrevoEmailSender:
    """
    Envoie un email via le service de messagerie configure.
    SRP : responsabilite unique d'envoi.
    """

    def send(self, to_email: str, subject: str, body: str) -> Dict[str, Any]:
        if not config.MAILER_API_KEY:
            return {
                "success": False,
                "error": "Cle du service d'emails manquante. Verifiez votre .env.",
            }

        try:
            import sib_api_v3_sdk

            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key["api-key"] = config.MAILER_API_KEY

            api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
                sib_api_v3_sdk.ApiClient(configuration)
            )
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                sender={"name": "Orchestrateur IA", "email": config.SENDER_EMAIL},
                to=[{"email": to_email}],
                subject=subject,
                html_content=f"<p>{body.replace(chr(10), '<br>')}</p>",
                text_content=body,
            )
            api_response = api_instance.send_transac_email(send_smtp_email)
            email_id = getattr(api_response, "message_id", "N/A")
            return {"success": True, "email_id": email_id}

        except Exception as e:
            return {"success": False, "error": str(e)}


class EmailAgent(BaseAgent):
    """
    Agent specialise dans la redaction et l'envoi d'emails professionnels.
    Orchestre le validator, le composer et le sender.
    """

    name = "EMAIL"
    description = (
        "Redige et envoie des emails professionnels. "
        "Peut gerer des demandes en plusieurs tours si des informations manquent."
    )

    def __init__(
        self,
        validator: Optional[EmailContentValidator] = None,
        composer: Optional[EmailComposer] = None,
        sender: Optional[BrevoEmailSender] = None,
    ) -> None:
        # DIP : les collaborateurs sont injectables
        self._validator = validator or EmailContentValidator()
        self._composer = composer or EmailComposer()
        self._sender = sender or BrevoEmailSender()

    @property
    def capabilities(self) -> List[AgentCapability]:
        return [
            AgentCapability(
                name="envoi_email",
                description=(
                    "Redige un email professionnel et l'envoie a l'adresse indiquee. "
                    "Demande le destinataire et le contexte si non fournis."
                ),
                required_params=["to", "body"],
                examples=[
                    "Envoie un email a alice@example.com pour reporter notre reunion de demain",
                    "Ecris un email de candidature a rh@societe.fr",
                ],
            )
        ]

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    def run(self, extracted: Dict[str, Any], **kwargs) -> AgentResult:
        """
        Point d'entree de l'agent Email avec boucle de retroaction multi-tours.
        """
        pending_context: Dict[str, Any] = kwargs.get("pending_context") or {}
        user_text: str = (kwargs.get("user_text") or "").strip()

        to_email, subject, body = self._resolve_fields(
            extracted, pending_context, user_text
        )

        body_valid, body_error = (
            self._validator.validate_body(body) if body else (False, "")
        )

        if not body_valid:
            if body_error:
                body = ""  # rejeter le corps invalide

        missing = self._compute_missing(to_email, body)
        if missing:
            prompt = self._build_missing_prompt(missing, body_error)
            return AgentResult(
                status="needs_input",
                response=prompt,
                missing_fields=missing,
                context={"to": to_email, "subject": subject, "body": body},
            )

        # Composition professionnelle + envoi
        composed_body, composed_subject = self._composer.compose(body)
        if subject == "Sans objet":
            subject = composed_subject

        result = self._sender.send(to_email, subject, composed_body)

        if result["success"]:
            return AgentResult(
                status="completed",
                response=(
                    f"L'email a ete envoye avec succes a {to_email}.\n\n"
                    f"**Sujet :** {subject}\n\n"
                    f"**Message :**\n{composed_body}\n\n"
                    "---\n"
                    "Verifiez votre boite de reception. "
                    "En cas d'absence, consultez le dossier Spams."
                ),
                context={"to": to_email, "subject": subject, "body": composed_body},
            )

        return AgentResult(
            status="failed",
            response="L'email n'a pas pu etre envoye. Reessayez dans quelques instants.",
            context={"to": to_email, "subject": subject, "body": composed_body},
        )

    # ------------------------------------------------------------------
    # Methodes privees
    # ------------------------------------------------------------------

    def _resolve_fields(
        self,
        extracted: Dict[str, Any],
        pending_context: Dict[str, Any],
        user_text: str,
    ) -> Tuple[str, str, str]:
        """Consolide les champs depuis les differentes sources."""
        to_email = (
            extracted.get("email", "")
            or extracted.get("to", "")
            or pending_context.get("to", "")
        )
        subject = (
            extracted.get("subject", "")
            or pending_context.get("subject", "")
            or "Sans objet"
        )
        body = extracted.get("body", "") or pending_context.get("body", "")

        if user_text:
            extracted_email = self._validator.extract_email_address(user_text)
            if extracted_email and not to_email:
                to_email = extracted_email
            elif not body and not extracted_email:
                body = user_text
            elif not body and extracted_email:
                remainder = user_text.replace(extracted_email, "").strip()
                if remainder:
                    body = remainder

        return to_email, subject, body

    def _compute_missing(self, to_email: str, body: str) -> List[str]:
        missing: List[str] = []
        if not body:
            missing.append("body")
        if not to_email:
            missing.append("to")
        return missing

    def _build_missing_prompt(self, missing_fields: List[str], body_error: str) -> str:
        base: str
        if missing_fields == ["body"]:
            base = (
                "Quel est le contexte ou le contenu du message que vous voulez envoyer ? "
                "Donnez-moi quelques phrases pour que je puisse rediger un email professionnel."
            )
        elif missing_fields == ["to"]:
            base = "A quelle adresse email dois-je envoyer ce message ?"
        elif "body" in missing_fields:
            base = (
                "Il me manque le contenu du message et l'adresse du destinataire. "
                "Pouvez-vous me donner ces informations ?"
            )
        else:
            base = "Il me manque des informations pour envoyer l'email."

        if body_error:
            base += f"\n\nNote : {body_error}"
        return base
