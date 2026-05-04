"""
Agent RAG autonome avec planification et exécution multi-étapes.
Gère la recherche documentaire et l'extraction d'informations.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

from core.autonomous_agent import AutonomousAgent, Plan, Observation, ActionType
from core.state import Task, TaskStatus, CentralState, Action, ActionType
from core.memory import MemoryType
from config import config


class AutonomousRAGAgent(AutonomousAgent):
    """Agent RAG autonome avec boucle complète."""

    def __init__(self, central_state: CentralState):
        super().__init__(agent_id="RAG", central_state=central_state)
        self.description = "Autonomous RAG agent with document search and retrieval"
        self.llm = None
        self.vector_store = None
        self._init_llm()

    def _init_llm(self) -> None:
        """Initialiser le LLM et le store vectoriel."""
        try:
            from langchain_anthropic import ChatAnthropic
            self.llm = ChatAnthropic(
                model="claude-haiku-4-5",
                api_key=config.ANTHROPIC_API_KEY,
            )
        except Exception as e:
            self.logger.log_error(f"Failed to initialize LLM: {str(e)}")

    def plan(self, task: Task) -> Optional[Plan]:
        """Créer un plan pour répondre une question documentaire."""
        rag_context = task.context
        question = rag_context.get("question", "")

        if not question:
            self.logger.log_error("No question provided")
            return None

        steps = [
            {
                "step": 1,
                "description": "Parse and analyze the question",
                "action": "analyze_question",
                "params": {"question": question},
            },
            {
                "step": 2,
                "description": "Search document index",
                "action": "search_documents",
                "params": {"question": question},
            },
            {
                "step": 3,
                "description": "Retrieve relevant passages",
                "action": "retrieve_passages",
                "params": {"question": question},
            },
            {
                "step": 4,
                "description": "Generate response with context",
                "action": "generate_response",
                "params": {"question": question},
            },
            {
                "step": 5,
                "description": "Validate and rank answer",
                "action": "validate_answer",
                "params": {},
            },
        ]

        plan = Plan(
            plan_id=f"rag_plan_{task.task_id}",
            description=f"Answer question: {question[:50]}...",
            steps=steps,
            created_at=datetime.now(),
            estimated_duration=10.0,
            priority=task.priority,
        )

        return plan

    def act(self, step: Dict[str, Any], task: Task) -> Optional[Action]:
        """Exécuter une étape du plan RAG."""
        action_type = step.get("action")
        params = step.get("params", {})

        try:
            if action_type == "analyze_question":
                result = self._analyze_question(params.get("question", ""))

            elif action_type == "search_documents":
                result = self._search_documents(params.get("question", ""))

            elif action_type == "retrieve_passages":
                result = self._retrieve_passages(params.get("question", ""))

            elif action_type == "generate_response":
                result = self._generate_response(
                    params.get("question", ""),
                    task.context.get("retrieved_passages", []),
                )

            elif action_type == "validate_answer":
                result = self._validate_answer(
                    task.context.get("generated_response", "")
                )

            else:
                result = {"success": False, "error": f"Unknown action: {action_type}"}

            action = Action(
                action_type=ActionType.EXECUTE,
                agent_id=self.agent_id,
                content=f"Step: {step.get('description', 'Unknown')}",
                status=TaskStatus.COMPLETED,
                result=result,
            )

            task.context[f"step_{step.get('step')}_result"] = result

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
        """Observer et valider une action RAG."""
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
        """Réfléchir sur la qualité de la réponse."""
        successful = sum(1 for o in observations if o.success)
        total = len(observations)

        confidence = successful / total if total > 0 else 0

        self.memory.store(
            content=f"RAG response generated with {confidence:.1%} confidence",
            memory_type=MemoryType.EPISODIC,
            tags=["rag_response", task.task_id],
            importance=min(1.0, confidence + 0.2),
        )

    def _analyze_question(self, question: str) -> Dict[str, Any]:
        """Analyser la question pour extraire les concepts clés."""
        keywords = question.lower().split()
        return {
            "success": True,
            "question": question,
            "keywords": keywords,
            "complexity": "simple" if len(keywords) < 5 else "complex",
        }

    def _search_documents(self, question: str) -> Dict[str, Any]:
        """Chercher dans l'index documentaire."""
        return {
            "success": True,
            "query": question,
            "documents_found": 0,
            "message": "Document index search completed",
        }

    def _retrieve_passages(self, question: str) -> Dict[str, Any]:
        """Récupérer les passages pertinents."""
        return {
            "success": True,
            "query": question,
            "passages": [],
            "message": "Passage retrieval completed",
        }

    def _generate_response(
        self,
        question: str,
        passages: List[str] = None,
    ) -> Dict[str, Any]:
        """Générer une réponse basée sur les passages."""
        if not self.llm:
            return {
                "success": False,
                "error": "LLM not initialized",
            }

        try:
            context = "\n".join(passages) if passages else "No context available"

            prompt = f"""Based on the following context, answer this question:

Question: {question}

Context:
{context}

Please provide a clear and accurate answer."""

            response = self.llm.invoke(prompt)
            answer = response.content if hasattr(response, 'content') else str(response)

            return {
                "success": True,
                "question": question,
                "answer": answer,
                "passages_used": len(passages or []),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _validate_answer(self, answer: str) -> Dict[str, Any]:
        """Valider la qualité de la réponse."""
        if not answer:
            return {
                "success": False,
                "message": "No answer provided",
            }

        quality_score = min(1.0, len(answer) / 1000.0)

        return {
            "success": True,
            "answer_length": len(answer),
            "quality_score": quality_score,
            "message": "Answer validation completed",
        }
