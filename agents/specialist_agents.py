"""
les 4 types d'agents specialises du systeme.

PlannerAgent  : decompose un objectif en sous-taches, genere un plan DAG
CriticAgent   : evalue la qualite d'un plan ou d'une reponse, donne un score et un feedback
ExecutorAgent : execute une tache concrete en utilisant les outils disponibles
ToolAgent     : specialiste dans l'utilisation d'un ou plusieurs outils specifiques

chaque agent implemente le cycle perceive -> reason -> decide -> act
et utilise le blackboard pour communiquer avec les autres agents.

note : on utilise le LLM pour le raisonnement reel, pas des regles hardcodees.
c'est ca la difference entre un vrai systeme autonome et un pipeline lineaire bete.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from config import config
from core.logging import AgentLogger
from core.memory import AgentMemory, Blackboard, MemoryType


def _build_llm():
    """construit le LLM depuis la config, sans nom de fournisseur dans le code."""
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=config.LLM_MODEL, api_key=config.LLM_API_KEY)  # type: ignore[call-arg]


# instance LLM partagee, instanciee une seule fois au chargement du module
_shared_llm = _build_llm()


@dataclass
class AgentPerception:
    """ce qu'un agent percoit de l'etat courant du systeme"""

    task_description: str
    blackboard_context: Dict[str, Any] = field(default_factory=dict)
    memory_context: str = ""
    iteration: int = 0
    max_iterations: int = 5


@dataclass
class AgentDecision:
    """la decision prise par un agent apres son raisonnement"""

    action: str  # ce que l'agent decide de faire
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    reasoning: str = ""  # explication du raisonnement, utile pour le CriticAgent
    stop: bool = False  # si True, l'agent considere la tache terminee


class PlannerAgent:
    """
    agent de planification.
    prend un objectif haut niveau et le decompose en sous-taches ordonnees.
    genere un plan sous forme de DAG (graphe orienté acyclique) en JSON.

    le plan est ecrit sur le blackboard namespace 'plan' pour que les autres
    agents puissent le lire et l'executer.
    """

    name = "PLANNER"
    description = "Decompose un objectif complexe en sous-taches ordonnees et les ecrit sur le blackboard."

    def __init__(self, blackboard: Blackboard) -> None:
        self.blackboard = blackboard
        self.memory = AgentMemory("PLANNER")
        self.logger = AgentLogger("PLANNER")
        self.success_count = 0
        self.error_count = 0

    def perceive(self, task_description: str, iteration: int = 0) -> AgentPerception:
        """
        percoit l'etat courant : tache a resoudre + contexte du blackboard.
        l'agent regarde aussi ses memoires pour voir si il a deja traite des taches similaires.
        """
        bb_context = {
            "existing_plan": self.blackboard.read("plan", "steps"),
            "critic_feedback": self.blackboard.read("critic", "feedback"),
            "execution_results": self.blackboard.read("execution", "results"),
        }
        memory_ctx = self.memory.get_context_summary(limit=3)

        return AgentPerception(
            task_description=task_description,
            blackboard_context=bb_context,
            memory_context=memory_ctx,
            iteration=iteration,
        )

    def reason(self, perception: AgentPerception) -> str:
        """
        raisonnement LLM : genere un plan en JSON a partir de la perception.
        si il y a un feedback du CriticAgent, le plan est revise en consequence.
        c'est le mecanisme de re-planning dynamique.
        """
        critic_feedback = perception.blackboard_context.get("critic_feedback", "")
        existing_plan = perception.blackboard_context.get("existing_plan")

        if existing_plan and critic_feedback:
            system_content = (
                "Tu es un agent de planification expert. "
                "Tu as deja cree un plan mais le CriticAgent a trouve des problemes. "
                "Revise le plan en prenant en compte le feedback.\n\n"
                f"Feedback du CriticAgent : {critic_feedback}\n\n"
                "Retourne UNIQUEMENT un JSON valide avec cette structure :\n"
                '{"steps": [{"id": "step_1", "description": "...", "agent": "EXECUTOR|TOOL", '
                '"depends_on": [], "params": {}}], "estimated_complexity": "low|medium|high"}\n'
                "Ne rajoute aucun texte en dehors du JSON."
            )
        else:
            system_content = (
                "Tu es un agent de planification expert. "
                "Decompose l'objectif suivant en sous-taches claires et ordonnees.\n\n"
                "Retourne UNIQUEMENT un JSON valide avec cette structure :\n"
                '{"steps": [{"id": "step_1", "description": "...", "agent": "EXECUTOR|TOOL", '
                '"depends_on": [], "params": {}}], "estimated_complexity": "low|medium|high"}\n'
                "Utilise 'EXECUTOR' pour les taches generales et 'TOOL' pour les taches "
                "necessitant un outil specifique (calcul, fichier, API). "
                "Ne rajoute aucun texte en dehors du JSON."
            )

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(
                content=f"Objectif a planifier : {perception.task_description}"
            ),
        ]

        response = _shared_llm.invoke(messages)
        return str(response.content)

    def decide(self, raw_reasoning: str) -> AgentDecision:
        """parse le JSON retourne par le LLM et construit une decision structuree"""
        try:
            # on essaie d'extraire le JSON meme si le LLM a mis du texte autour
            raw = raw_reasoning.strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

            plan_data = json.loads(raw)
            steps = plan_data.get("steps", [])
            complexity = plan_data.get("estimated_complexity", "medium")

            return AgentDecision(
                action="create_plan",
                params={"steps": steps, "complexity": complexity},
                confidence=0.85,
                reasoning=f"Plan genere avec {len(steps)} etapes, complexite : {complexity}",
            )
        except (json.JSONDecodeError, ValueError) as exc:
            self.error_count += 1
            return AgentDecision(
                action="create_plan",
                params={
                    "steps": [
                        {
                            "id": "step_1",
                            "description": raw_reasoning[:200],
                            "agent": "EXECUTOR",
                            "depends_on": [],
                            "params": {},
                        }
                    ],
                    "complexity": "low",
                },
                confidence=0.4,
                reasoning=f"Parsing JSON echoue ({exc}), plan de secours avec 1 etape",
            )

    def act(self, decision: AgentDecision) -> Dict[str, Any]:
        """
        ecrit le plan sur le blackboard pour que les autres agents puissent le lire.
        stocke aussi en memoire episodique pour les prochaines planifications.
        """
        steps = decision.params.get("steps", [])
        complexity = decision.params.get("complexity", "medium")

        self.blackboard.write("plan", "steps", steps, author=self.name)
        self.blackboard.write("plan", "complexity", complexity, author=self.name)
        self.blackboard.write(
            "plan", "created_at", datetime.now().isoformat(), author=self.name
        )
        self.blackboard.write(
            "plan", "confidence", decision.confidence, author=self.name
        )

        self.memory.store(
            content=f"Plan cree : {len(steps)} etapes, complexite {complexity}",
            memory_type=MemoryType.EPISODIC,
            tags=["planning"],
            importance=0.7,
        )

        self.success_count += 1
        self.logger.log_action(
            action="plan_created",
            details=f"{len(steps)} etapes, complexite {complexity}",
            metadata={"steps_count": len(steps), "confidence": decision.confidence},
        )

        return {
            "success": True,
            "steps": steps,
            "complexity": complexity,
            "confidence": decision.confidence,
        }

    def run(self, task_description: str, iteration: int = 0) -> Dict[str, Any]:
        """point d'entree principal : percoit -> raisonne -> decide -> agit"""
        try:
            perception = self.perceive(task_description, iteration)
            raw_reasoning = self.reason(perception)
            decision = self.decide(raw_reasoning)
            result = self.act(decision)
            return result
        except Exception as exc:
            self.error_count += 1
            self.logger.log_error(str(exc))
            return {"success": False, "error": str(exc), "steps": []}


class CriticAgent:
    """
    agent d'evaluation (critique).
    lit le plan et les resultats d'execution sur le blackboard,
    evalue la qualite et la coherence, donne un score et un feedback actionnable.

    le feedback est ecrit sur le blackboard pour que le PlannerAgent puisse
    reviser son plan si necessaire. c'est le mecanisme de self-correction.
    """

    name = "CRITIC"
    description = "Evalue la qualite d'un plan ou d'un resultat et fournit un feedback pour l'ameliorer."

    # seuil en dessous duquel on demande une revision du plan
    REVISION_THRESHOLD = 0.6

    def __init__(self, blackboard: Blackboard) -> None:
        self.blackboard = blackboard
        self.memory = AgentMemory("CRITIC")
        self.logger = AgentLogger("CRITIC")
        self.success_count = 0
        self.error_count = 0

    def perceive(self, context: str) -> AgentPerception:
        """percoit le plan actuel et les resultats d'execution pour les evaluer"""
        bb_context = {
            "plan_steps": self.blackboard.read("plan", "steps"),
            "plan_complexity": self.blackboard.read("plan", "complexity"),
            "execution_results": self.blackboard.read("execution", "results"),
            "previous_feedback": self.blackboard.read("critic", "feedback"),
        }
        return AgentPerception(
            task_description=context,
            blackboard_context=bb_context,
        )

    def reason(self, perception: AgentPerception) -> str:
        """
        evalue via le LLM la qualite du plan et des resultats.
        retourne un JSON avec un score et un feedback.
        """
        plan_steps = perception.blackboard_context.get("plan_steps", [])
        exec_results = perception.blackboard_context.get("execution_results", [])

        context_str = f"Objectif initial : {perception.task_description}\n"
        if plan_steps:
            context_str += f"Plan avec {len(plan_steps)} etapes : {json.dumps(plan_steps, ensure_ascii=False)}\n"
        if exec_results:
            context_str += f"Resultats d'execution : {json.dumps(exec_results, ensure_ascii=False)}\n"

        system_content = (
            "Tu es un agent critique expert. Evalue la qualite du plan et des resultats fournis.\n\n"
            "Criteres d'evaluation :\n"
            "- Completude : est-ce que toutes les etapes necessaires sont presentes ?\n"
            "- Coherence : les etapes sont-elles dans le bon ordre et coherentes ?\n"
            "- Qualite des resultats : les resultats correspondent-ils a l'objectif ?\n\n"
            "Retourne UNIQUEMENT un JSON valide :\n"
            '{"score": 0.0-1.0, "approved": true/false, '
            '"feedback": "...", "improvements": ["..."]}\n'
            "score >= 0.7 = approuve. Ne rajoute aucun texte en dehors du JSON."
        )

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=context_str),
        ]

        response = _shared_llm.invoke(messages)
        return str(response.content)

    def decide(self, raw_reasoning: str) -> AgentDecision:
        """parse l'evaluation du LLM"""
        try:
            raw = raw_reasoning.strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

            eval_data = json.loads(raw)
            score = float(eval_data.get("score", 0.5))
            approved = bool(eval_data.get("approved", score >= self.REVISION_THRESHOLD))
            feedback = eval_data.get("feedback", "")
            improvements = eval_data.get("improvements", [])

            return AgentDecision(
                action="evaluate",
                params={
                    "score": score,
                    "approved": approved,
                    "feedback": feedback,
                    "improvements": improvements,
                },
                confidence=0.8,
                reasoning=feedback,
                stop=approved,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            self.error_count += 1
            return AgentDecision(
                action="evaluate",
                params={
                    "score": 0.5,
                    "approved": True,
                    "feedback": "Evaluation impossible, on continue quand meme.",
                    "improvements": [],
                },
                confidence=0.3,
                reasoning=f"Parsing echoue : {exc}",
                stop=True,
            )

    def act(self, decision: AgentDecision) -> Dict[str, Any]:
        """ecrit l'evaluation sur le blackboard pour que le planner puisse s'adapter"""
        score = decision.params.get("score", 0.5)
        feedback = decision.params.get("feedback", "")
        approved = decision.params.get("approved", True)
        improvements = decision.params.get("improvements", [])

        self.blackboard.write("critic", "score", score, author=self.name)
        self.blackboard.write("critic", "feedback", feedback, author=self.name)
        self.blackboard.write("critic", "approved", approved, author=self.name)
        self.blackboard.write("critic", "improvements", improvements, author=self.name)
        self.blackboard.write(
            "critic", "evaluated_at", datetime.now().isoformat(), author=self.name
        )

        self.memory.store(
            content=f"Evaluation : score={score:.2f}, approuve={approved}",
            memory_type=MemoryType.EPISODIC,
            tags=["evaluation"],
            importance=min(1.0, score + 0.2),
        )

        self.success_count += 1
        self.logger.log_action(
            action="evaluated",
            details=f"score={score:.2f}, approuve={approved}",
            metadata={"score": score, "approved": approved},
        )

        return {
            "success": True,
            "score": score,
            "approved": approved,
            "feedback": feedback,
            "needs_replanning": not approved,
        }

    def run(self, context: str) -> Dict[str, Any]:
        """point d'entree principal"""
        try:
            perception = self.perceive(context)
            raw_reasoning = self.reason(perception)
            decision = self.decide(raw_reasoning)
            result = self.act(decision)
            return result
        except Exception as exc:
            self.error_count += 1
            self.logger.log_error(str(exc))
            return {
                "success": False,
                "error": str(exc),
                "approved": True,
                "needs_replanning": False,
            }


class ExecutorAgent:
    """
    agent d'execution.
    lit le plan depuis le blackboard, execute chaque etape dans l'ordre,
    respecte les dependances entre etapes (DAG).

    ecrit les resultats sur le blackboard pour que le CriticAgent puisse les evaluer.
    """

    name = "EXECUTOR"
    description = "Execute les etapes d'un plan en respectant les dependances et ecrit les resultats."

    def __init__(self, blackboard: Blackboard) -> None:
        self.blackboard = blackboard
        self.memory = AgentMemory("EXECUTOR")
        self.logger = AgentLogger("EXECUTOR")
        self.success_count = 0
        self.error_count = 0

    def perceive(self, task_description: str) -> AgentPerception:
        """lit le plan depuis le blackboard"""
        bb_context = {
            "steps": self.blackboard.read("plan", "steps", default=[]),
            "complexity": self.blackboard.read("plan", "complexity", default="medium"),
        }
        return AgentPerception(
            task_description=task_description,
            blackboard_context=bb_context,
        )

    def reason(self, perception: AgentPerception) -> str:
        """
        genere une reponse pour chaque etape du plan via le LLM.
        si c'est une etape TOOL, on appelle l'outil ; sinon on utilise le LLM directement.
        """
        steps = perception.blackboard_context.get("steps", [])
        if not steps:
            return json.dumps({"results": [], "summary": "Aucune etape a executer."})

        results = []
        completed_steps: set = set()

        # respecter les dependances : on execute dans l'ordre topologique
        remaining = list(steps)
        max_passes = len(remaining) * 2  # securite anti-boucle infinie
        passes = 0

        while remaining and passes < max_passes:
            passes += 1
            made_progress = False

            for step in list(remaining):
                deps = step.get("depends_on", [])
                # verifie que toutes les dependances sont satisfaites
                if all(d in completed_steps for d in deps):
                    result = self._execute_step(step, perception.task_description)
                    results.append(result)
                    completed_steps.add(step.get("id", ""))
                    remaining.remove(step)
                    made_progress = True

            if not made_progress:
                # dependances circulaires ou impossibles, on execute le reste quand meme
                for step in remaining:
                    result = self._execute_step(step, perception.task_description)
                    results.append(result)
                    completed_steps.add(step.get("id", ""))
                remaining = []

        summary = f"{len(results)} etapes executees."
        return json.dumps({"results": results, "summary": summary}, ensure_ascii=False)

    def _execute_step(self, step: Dict[str, Any], task_context: str) -> Dict[str, Any]:
        """execute une etape individuelle via le LLM"""
        step_desc = step.get("description", "etape inconnue")
        step_id = step.get("id", "?")

        messages = [
            SystemMessage(
                content=(
                    "Tu es un agent d'execution expert. "
                    "Accomplis l'etape suivante de maniere precise et concise. "
                    f"Contexte global de la tache : {task_context}"
                )
            ),
            HumanMessage(content=f"Etape a executer : {step_desc}"),
        ]

        try:
            response = _shared_llm.invoke(messages)
            output = str(response.content)
            return {
                "step_id": step_id,
                "description": step_desc,
                "output": output,
                "success": True,
            }
        except Exception as exc:
            self.error_count += 1
            return {
                "step_id": step_id,
                "description": step_desc,
                "output": None,
                "success": False,
                "error": str(exc),
            }

    def decide(self, raw_reasoning: str) -> AgentDecision:
        """parse les resultats d'execution"""
        try:
            data = json.loads(raw_reasoning)
            results = data.get("results", [])
            summary = data.get("summary", "")
            all_success = all(r.get("success", False) for r in results)

            return AgentDecision(
                action="execute_plan",
                params={"results": results, "summary": summary},
                confidence=0.9 if all_success else 0.5,
                reasoning=summary,
                stop=True,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return AgentDecision(
                action="execute_plan",
                params={"results": [], "summary": f"Erreur parsing : {exc}"},
                confidence=0.3,
                reasoning=str(exc),
                stop=True,
            )

    def act(self, decision: AgentDecision) -> Dict[str, Any]:
        """ecrit les resultats sur le blackboard"""
        results = decision.params.get("results", [])
        summary = decision.params.get("summary", "")

        self.blackboard.write("execution", "results", results, author=self.name)
        self.blackboard.write("execution", "summary", summary, author=self.name)
        self.blackboard.write(
            "execution", "executed_at", datetime.now().isoformat(), author=self.name
        )

        self.memory.store(
            content=f"Execution : {summary}",
            memory_type=MemoryType.EPISODIC,
            tags=["execution"],
            importance=0.6,
        )

        self.success_count += 1
        self.logger.log_action(
            action="executed",
            details=summary,
            metadata={"results_count": len(results)},
        )

        return {
            "success": True,
            "results": results,
            "summary": summary,
        }

    def run(self, task_description: str) -> Dict[str, Any]:
        """point d'entree principal"""
        try:
            perception = self.perceive(task_description)
            raw_reasoning = self.reason(perception)
            decision = self.decide(raw_reasoning)
            result = self.act(decision)
            return result
        except Exception as exc:
            self.error_count += 1
            self.logger.log_error(str(exc))
            return {
                "success": False,
                "error": str(exc),
                "results": [],
                "summary": str(exc),
            }


class ToolAgent:
    """
    agent specialiste dans l'utilisation d'outils.
    utilise le LLM pour choisir le bon outil, preparer les parametres,
    executer l'outil via le ToolManager et interpreter le resultat.

    c'est le seul agent qui a acces direct au ToolManager.
    """

    name = "TOOL"
    description = "Selectionne et utilise les outils disponibles pour accomplir une tache concrete."

    def __init__(self, blackboard: Blackboard, tool_manager: Any) -> None:
        self.blackboard = blackboard
        self.tool_manager = tool_manager
        self.memory = AgentMemory("TOOL")
        self.logger = AgentLogger("TOOL")
        self.success_count = 0
        self.error_count = 0

    def perceive(self, task_description: str) -> AgentPerception:
        """percoit la tache et les outils disponibles"""
        bb_context = {
            "available_tools": self.tool_manager.available_tools(),
            "tools_description": self.tool_manager.describe_tools(),
        }
        return AgentPerception(
            task_description=task_description,
            blackboard_context=bb_context,
        )

    def reason(self, perception: AgentPerception) -> str:
        """demande au LLM de choisir l'outil et les parametres"""
        tools_desc = perception.blackboard_context.get(
            "tools_description", "Aucun outil."
        )

        system_content = (
            "Tu es un agent specialiste des outils. "
            "Choisis l'outil le plus adapte pour accomplir la tache et prepare les parametres.\n\n"
            f"Outils disponibles :\n{tools_desc}\n\n"
            "Retourne UNIQUEMENT un JSON valide :\n"
            '{"tool_name": "...", "params": {}, "reasoning": "..."}\n'
            "Si aucun outil n'est adapte, utilise tool_name='none'. "
            "Ne rajoute aucun texte en dehors du JSON."
        )

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=f"Tache : {perception.task_description}"),
        ]

        response = _shared_llm.invoke(messages)
        return str(response.content)

    def decide(self, raw_reasoning: str) -> AgentDecision:
        """parse la decision du LLM sur l'outil a utiliser"""
        try:
            raw = raw_reasoning.strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

            data = json.loads(raw)
            tool_name = data.get("tool_name", "none")
            params = data.get("params", {})
            reasoning = data.get("reasoning", "")

            return AgentDecision(
                action="use_tool",
                params={"tool_name": tool_name, "tool_params": params},
                confidence=0.8,
                reasoning=reasoning,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return AgentDecision(
                action="use_tool",
                params={"tool_name": "none", "tool_params": {}},
                confidence=0.2,
                reasoning=f"Impossible de parser la decision : {exc}",
            )

    def act(self, decision: AgentDecision) -> Dict[str, Any]:
        """execute l'outil choisi et ecrit le resultat sur le blackboard"""
        tool_name = decision.params.get("tool_name", "none")
        tool_params = decision.params.get("tool_params", {})

        if tool_name == "none" or not self.tool_manager.has(tool_name):
            result_data = {
                "success": False,
                "output": None,
                "error": f"Outil '{tool_name}' non disponible ou non necessaire.",
                "tool_used": tool_name,
            }
        else:
            tool_result = self.tool_manager.execute(tool_name, **tool_params)
            result_data = {
                "success": tool_result.success,
                "output": tool_result.output,
                "error": tool_result.error,
                "tool_used": tool_name,
                "execution_time": tool_result.execution_time,
            }

        self.blackboard.write("tool_results", tool_name, result_data, author=self.name)

        importance = 0.7 if result_data["success"] else 0.4
        self.memory.store(
            content=f"Outil {tool_name} : {'succes' if result_data['success'] else 'echec'}",
            memory_type=MemoryType.SHORT_TERM,
            tags=["tool_use", tool_name],
            importance=importance,
        )

        if result_data["success"]:
            self.success_count += 1
        else:
            self.error_count += 1

        self.logger.log_action(
            action="tool_used",
            details=f"tool={tool_name}, success={result_data['success']}",
            metadata=result_data,
        )

        return result_data

    def run(self, task_description: str) -> Dict[str, Any]:
        """point d'entree principal"""
        try:
            perception = self.perceive(task_description)
            raw_reasoning = self.reason(perception)
            decision = self.decide(raw_reasoning)
            result = self.act(decision)
            return result
        except Exception as exc:
            self.error_count += 1
            self.logger.log_error(str(exc))
            return {"success": False, "error": str(exc), "tool_used": "none"}
