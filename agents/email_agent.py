import os
from config import config

def send_email(to_email: str, subject: str, body: str) -> dict:
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
        
        # Le SDK renvoie un objet avec message_id
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

def run(extracted: dict) -> str:
    """Point d'entree de l'agent Email."""
    to_email = extracted.get("email", "") or extracted.get("to", "")
    subject  = extracted.get("subject", "Sans objet")
    body     = extracted.get("body", "")

    if not to_email:
        return "Adresse email introuvable dans votre message."
    if not body:
        return "Corps de l'email introuvable."

    result = send_email(to_email, subject, body)
    if result["success"]:
        return result["response"]
    else:
        return result["error"]
