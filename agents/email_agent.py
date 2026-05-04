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
        if missing_fields == ["body"]:
            return "Quel est le contexte ou le contenu du message que tu veux envoyer ? Donne-moi au moins quelques phrases pour que je puisse rédiger un email professionnel (minimum 20 caractères)."
        if missing_fields == ["to"]:
            return "À quelle adresse email dois-je envoyer ce message ?"
        if "body" in missing_fields:
            return "D'abord, quel est le contexte/contenu du message ? Raconte-moi ce que tu veux communiquer (minimum 20 caractères)."
        return "Il me manque des informations pour envoyer l'email (contexte et destinataire). Peux-tu completer ?"
    
    def _is_valid_body(self, body: str) -> tuple[bool, str]:
        """Vérifie que le body a assez de contenu."""
        if not body:
            return False, "Le message est vide."
        
        body_clean = body.strip()
        if len(body_clean) < 10:
            return False, f"Le message est trop court ({len(body_clean)} caractères). Donne-moi au moins 10 caractères de contenu valide."
        
        # Reject single words or very basic greetings
        if body_clean.lower() in ["salut", "bonjour", "hello", "hi", "allo", "coucou", "ok", "non", "oui"]:
            return False, f"'{body_clean}' n'est pas assez détaillé pour un email. Explique ce que tu veux communiquer."
        
        return True, ""

    def _refine_body_professionally(self, body: str, to_email: str) -> tuple[str, str]:
        """Rédige un email professionnel via Claude et génère un sujet.
        Retourne: (body, subject)
        """
        try:
            from langchain_anthropic import ChatAnthropic
            from langchain_core.messages import SystemMessage, HumanMessage
            
            if not config.ANTHROPIC_API_KEY:
                return body, "Sans objet"
            
            llm = ChatAnthropic(model="claude-haiku-4-5", api_key=config.ANTHROPIC_API_KEY)
            
            # Générer le sujet et le corps
            sys_prompt = f"""Tu es un expert en rédaction d'emails professionnels.
Basé sur cette demande: '{body}'

Génère DEUX choses (séparées par |SEP|):
1. Un SUJET court et clair pour l'email (max 10 mots)
2. Le CORPS de l'email professionnel (avec salutation Bonjour/Madame/Monsieur et signature)

Format strict: SUJET|SEP|CORPS

Ne mets RIEN d'autre, pas d'explications."""
            
            messages = [
                SystemMessage(content=sys_prompt),
                HumanMessage(content="Génère l'email professionnel.")
            ]
            
            response = llm.invoke(messages).content.strip()
            
            # Parser la réponse
            if "|SEP|" in response:
                parts = response.split("|SEP|")
                subject = parts[0].strip() if parts[0] else "Sans objet"
                improved_body = parts[1].strip() if len(parts) > 1 else body
            else:
                # Fallback si format incorrect
                subject = "Sans objet"
                improved_body = response
            
            return improved_body, subject
        except:
            return body, "Sans objet"  # En cas d'erreur

    def send_email(self, to_email: str, subject: str, body: str) -> dict:
        """Envoie un email via l'API REST de Brevo (Sendinblue)."""
        if not config.BREVO_API_KEY:
            return {
                "success": False,
                "error": "Cle API Brevo manquante. Verifiez BREVO_API_KEY."
            }
        
        # Réécrire le body de manière professionnelle et générer un sujet intelligent
        if len(body.strip()) > 5 and not body.startswith("Sans objet"):
            refined_body, intelligent_subject = self._refine_body_professionally(body, to_email)
            body = refined_body
            # Utiliser le sujet généré si on n'avait que "Sans objet"
            if subject == "Sans objet":
                subject = intelligent_subject

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
            # Check if it looks like an email first
            extracted_email = self._extract_email(user_text)
            if extracted_email and not to_email:
                to_email = extracted_email
            # Otherwise, treat it as body content if we don't have a body yet
            elif not body and not extracted_email:
                body = user_text
            elif not body and extracted_email:
                # User gave us an email but we need body - keep looking for body
                if len(user_text.replace(extracted_email, "").strip()) > 0:
                    body = user_text.replace(extracted_email, "").strip()

        # Valider le body s'il a été défini
        body_valid = True
        body_error = ""
        if body:
            body_valid, body_error = self._is_valid_body(body)
            if not body_valid:
                # Rejeter le body invalide
                body = ""

        missing_fields = []
        if not body:
            missing_fields.append("body")
        if not to_email:
            missing_fields.append("to")

        if missing_fields:
            # Si le body n'était pas valide, ajouter le message d'erreur
            if body_error:
                error_response = self._build_missing_prompt(missing_fields) + f"\n\n❌ {body_error}"
            else:
                error_response = self._build_missing_prompt(missing_fields)
            
            return {
                "status": "needs_input",
                "response": error_response,
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
