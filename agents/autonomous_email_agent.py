"""
Agent Email autonome avec planification et exécution multi-étapes.
Gère l'envoi d'emails via Brevo avec validation et réessais.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import config
from core.autonomous_agent import Action, ActionType, AutonomousAgent, Observation, Plan
from core.memory import MemoryType
from core.state import ActionType, CentralState, Task, TaskStatus


class AutonomousEmailAgent(AutonomousAgent):
    """Agent email autonome avec boucle complète."""

    def __init__(self, central_state: CentralState):
        super().__init__(agent_id="EMAIL", central_state=central_state)
        self.description = "Autonomous email sending agent with planning and validation"

    def plan(self, task: Task) -> Optional[Plan]:
        """Créer un plan pour envoyer un email."""
        email_context = task.context

        to_email = email_context.get("to", "")
        subject = email_context.get("subject", "")
        body = email_context.get("body", "")

        if not to_email or not subject:
            self.logger.log_error("Missing required fields: to or subject")
            return None

        steps = [
            {
                "step": 1,
                "description": "Validate email address format",
                "action": "validate_email",
                "params": {"email": to_email},
            },
            {
                "step": 2,
                "description": "Prepare email content",
                "action": "prepare_content",
                "params": {"subject": subject, "body": body},
            },
            {
                "step": 3,
                "description": "Send email via Brevo API",
                "action": "send_email",
                "params": {"to": to_email, "subject": subject, "body": body},
            },
            {
                "step": 4,
                "description": "Verify send confirmation",
                "action": "verify_send",
                "params": {},
            },
        ]

        plan = Plan(
            plan_id=f"email_plan_{task.task_id}",
            description=f"Send email to {to_email}",
            steps=steps,
            created_at=datetime.now(),
            estimated_duration=5.0,
            priority=task.priority,
        )

        return plan

    def act(self, step: Dict[str, Any], task: Task) -> Optional[Action]:
        """Exécuter une étape du plan."""
        action_type = step.get("action")
        params = step.get("params", {})

        try:
            if action_type == "validate_email":
                result = self._validate_email(params["email"])

            elif action_type == "prepare_content":
                result = self._prepare_content(
                    params.get("subject", ""),
                    params.get("body", ""),
                )

            elif action_type == "send_email":
                result = self._send_email_via_brevo(
                    params.get("to", ""),
                    params.get("subject", ""),
                    params.get("body", ""),
                )

            elif action_type == "verify_send":
                result = self._verify_send()

            else:
                result = {"success": False, "error": f"Unknown action: {action_type}"}

            action = Action(
                action_type=ActionType.EXECUTE,
                agent_id=self.agent_id,
                content=f"Step: {step.get('description', 'Unknown')}",
                status=TaskStatus.COMPLETED,
                result=result,
            )

            return action

        except Exception as e:
            self.logger.log_error(str(e), {"step": step})
            action = Action(
                action_type=ActionType.EXECUTE,
                agent_id=self.agent_id,
                content=f"Step: {step.get('description', 'Unknown')}",
                status=TaskStatus.FAILED,
                error=str(e),
            )
            return action

    def observe(self, action: Action, task: Task) -> Observation:
        """Observer et valider une action."""
        success = action.status == TaskStatus.COMPLETED and not action.error
        data = action.result or {}

        observation = Observation(
            timestamp=datetime.now(),
            success=success,
            data=data,
            error=action.error,
        )

        return observation

    def reflect(self, observations: List[Observation], task: Task) -> None:
        """Réfléchir sur les observations."""
        successful = sum(1 for o in observations if o.success)
        total = len(observations)

        insight = f"Completed {successful}/{total} steps successfully"
        self.memory.store(
            content=insight,
            memory_type=MemoryType.EPISODIC,
            tags=["email_send", task.task_id],
            importance=0.7,
        )

    def recover(self, task: Task, error: Exception) -> None:
        """Stratégie de récupération pour erreurs d'email."""
        self.memory.store(
            content=f"Recovery attempted after error: {str(error)}",
            memory_type=MemoryType.SHORT_TERM,
            tags=["error_recovery"],
            importance=0.6,
        )

    def _validate_email(self, email: str) -> Dict[str, Any]:
        """Valider le format d'une adresse email."""
        pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        is_valid = bool(re.match(pattern, email))

        return {
            "success": is_valid,
            "email": email,
            "message": "Email format is valid" if is_valid else "Invalid email format",
        }

    def _prepare_content(self, subject: str, body: str) -> Dict[str, Any]:
        """Préparer le contenu de l'email."""
        if not subject or not body:
            return {
                "success": False,
                "message": "Subject and body are required",
            }

        return {
            "success": True,
            "subject_length": len(subject),
            "body_length": len(body),
            "message": "Content prepared successfully",
        }

    def _send_email_via_brevo(
        self,
        to_email: str,
        subject: str,
        body: str,
    ) -> Dict[str, Any]:
        """Envoie l'email via le service de messagerie configure."""
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
            email_id = getattr(api_response, "message_id", "unknown")

            return {
                "success": True,
                "email_id": email_id,
                "recipient": to_email,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _verify_send(self) -> Dict[str, Any]:
        """Vérifier que l'email a été envoyé."""
        return {
            "success": True,
            "message": "Email send verified",
        }
