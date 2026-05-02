import os
import re
from config import config
from .base_agent import BaseAgent


class EmailAgent(BaseAgent):
    name = "EMAIL"
    description = "Agent d'envoi d'emails via Brevo."

    @staticmethod
    def _extract_email(text: str) -> str:
        match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
        return match.group(0) if match else ""

    def _build_missing_prompt(self, missing_fields: list[str]) -> str:
        if missing_fields == ["to"]:
            return "Il me manque l'adresse email du destinataire. Peux-tu me la donner ?"
        if missing_fields == ["body"]:
            return "Il me manque le contenu du message. Peux-tu me donner le texte a envoyer ?"
        return "Il me manque des informations pour envoyer l'email (destinataire et/ou message). Peux-tu completer ?"

    def send_email(self, to_email: str, subject: str, body: str) -> dict:
        """Envoie un email via l'API REST de Brevo (Sendinblue)."""
        if not config.BREVO_API_KEY:
            return {
                "success": False,
                "error": "Cle API Brevo manquante. Verifiez BREVO_API_KEY."
            }

        try:
            import sib_api_v3_sdk
            from sib_api_v3_sdk.rest import ApiException

            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key['api-key'] = config.BREVO_API_KEY

            api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                sender={"name": "Orchestrateur IA", "email": config.EMAIL_FROM},
                to=[{"email": to_email}],
                subject=subject,
                html_content=f"<p>{body.replace(chr(10), '<br>')}</p>",
                text_content=body
            )

            api_response = api_instance.send_transac_email(send_smtp_email)
            email_id = getattr(api_response, "message_id", "N/A")

            return {
                "success": True,
                "email_id": email_id,
                "response": (
                    f"**L'email a été envoyé avec succès à {to_email} !**\n\n"
                    f"**Sujet :** {subject}\n\n"
                    f"**Message :** {body}\n\n"
                    f"---\n"
                    f"*Astuce : Vérifiez votre boîte de réception ou demandez au destinataire de vérifier la sienne. Pensez également à jeter un œil dans le dossier **Spams / Courriers indésirables** !*"
                )
            }
        except ApiException as e:
            return {
                "success": False,
                "error": f"Erreur de l'API Brevo : {e}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Erreur locale lors de l'envoi de l'email : {str(e)}"
            }

    def run(self, extracted: dict, **kwargs) -> dict:
        """Point d'entree de l'agent Email avec boucle de retroaction."""
        pending_context = kwargs.get("pending_context") or {}
        user_text = (kwargs.get("user_text") or "").strip()

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
        body = (
            extracted.get("body", "")
            or pending_context.get("body", "")
        )

        # If user is answering a follow-up, try to fill missing fields.
        if user_text:
            if not to_email:
                to_email = self._extract_email(user_text)
            if not body:
                if user_text != to_email:
                    body = user_text

        missing_fields = []
        if not to_email:
            missing_fields.append("to")
        if not body:
            missing_fields.append("body")

        if missing_fields:
            return {
                "status": "needs_input",
                "response": self._build_missing_prompt(missing_fields),
                "missing_fields": missing_fields,
                "context": {"to": to_email, "subject": subject, "body": body},
            }

        result = self.send_email(to_email, subject, body)
        if result["success"]:
            return {
                "status": "completed",
                "response": result["response"],
                "context": {"to": to_email, "subject": subject, "body": body},
            }
        return {
            "status": "failed",
            "response": "Je n'ai pas pu envoyer l'email pour le moment. Reessayez dans quelques instants.",
            "context": {"to": to_email, "subject": subject, "body": body},
        }


_email_agent = EmailAgent()


def run(extracted: dict) -> str:
    """Backward-compatible wrapper."""
    result = _email_agent.run(extracted)
    return result.get("response", "Erreur lors du traitement de l'email.")
