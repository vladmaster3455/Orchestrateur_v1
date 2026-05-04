"""
orchestrateur avance : le vrai cerveau du systeme multi-agents.

implemente la boucle autonome complete :
  Analyse -> Plan -> Execute -> Observe -> Critique -> Ajuste -> Repete

caracteristiques importantes :
- selection d'agent par scoring (pas de logique hardcodee)
- re-planning dynamique quand le CriticAgent desapprouve
- execution asynchrone des etapes independantes (asyncio)
- collaboration entre agents via le Blackboard
- condition de terminaison : score >= seuil ou max iterations atteint
- rapport d'execution detaille en fin de boucle

c'est pas un pipeline lineaire bete, chaque iteration peut changer
completement le plan en fonction des resultats et du feedback.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.logging import SystemLogger
from core.memory import Blackboard
from core.quality import PriorityCalculator
from core.state import CentralState

# seuil de qualite pour terminer la boucle automatiquement
CONVERGENCE_THRESHOLD = 0.7
# nombre max d'iterations pour evite les boucles infinies
MAX_ITERATIONS = 5


@dataclass
class AutonomousLoopResult:
    """
    resultat complet d'une execution de la boucle autonome.
    contient toutes les informations pour le rapport final.
    """

    task_description: str
    iterations: int
    final_score: float
    converged: bool
    final_response: str
    plan_history: List[Dict[str, Any]] = field(default_factory=list)
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    critic_history: List[Dict[str, Any]] = field(default_factory=list)
    agent_scores: Dict[str, float] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task_description,
            "iterations": self.iterations,
            "final_score": self.final_score,
            "converged": self.converged,
            "final_response": self.final_response,
            "plan_history": self.plan_history,
            "execution_history": self.execution_history,
            "critic_history": self.critic_history,
            "agent_scores": self.agent_scores,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


class AgentScorer:
    """
    calcule un score de pertinence pour chaque agent en fonction de la tache.
    le scoring est base sur :
    - les stats historiques de l'agent (taux de succes, nb d'erreurs)
    - la charge actuelle (nb de taches en cours)
    - la pertinence par rapport au type de tache

    ca evite la logique hardcodee "toujours utiliser PLANNER en premier"
    et permet au systeme de s'adapter dynamiquement.
    """

    @staticmethod
    def score_agents(
        agents: Dict[str, Any],
        task_context: str,
        preferred_type: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        retourne un dict {agent_name: score} trie par score decroissant.
        le score le plus haut = l'agent le plus adapte pour cette tache.
        """
        scores: Dict[str, float] = {}

        for agent_name, agent in agents.items():
            success_count = getattr(agent, "success_count", 0)
            error_count = getattr(agent, "error_count", 0)
            total = success_count + error_count

            error_rate = error_count / total if total > 0 else 0.0
            reliability = max(0.0, 1.0 - error_rate)

            # bonus si c'est le type prefere pour ce tour
            type_bonus = 0.2 if preferred_type and agent_name == preferred_type else 0.0

            score = (
                PriorityCalculator.calculate_agent_priority(
                    queue_size=0,  # on a pas de queue dans cette version
                    error_rate=error_rate,
                    avg_execution_time=1.0,
                    reliability=reliability,
                )
                + type_bonus
            )

            scores[agent_name] = round(min(1.0, score), 4)

        return scores

    @staticmethod
    def best_agent(scores: Dict[str, float]) -> Optional[str]:
        """retourne le nom de l'agent avec le meilleur score"""
        if not scores:
            return None
        return max(scores.items(), key=lambda x: x[1])[0]


class AdvancedOrchestrator:
    """
    orchestrateur avance qui coordonne PlannerAgent, ExecutorAgent, CriticAgent et ToolAgent.

    la boucle autonome tourne jusqu'a convergence (score suffisant)
    ou jusqu'au nombre max d'iterations.

    le systeme peut aussi executer des taches simples en mode direct
    sans passer par la boucle complete (pour les taches legeres).
    """

    def __init__(
        self,
        planner: Any,
        executor: Any,
        critic: Any,
        tool_agent: Any,
        blackboard: Blackboard,
        central_state: Optional[CentralState] = None,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.critic = critic
        self.tool_agent = tool_agent
        self.blackboard = blackboard
        self.central_state = central_state or CentralState()
        self.logger = SystemLogger()

        # registre interne des agents pour le scoring
        self._agents: Dict[str, Any] = {
            "PLANNER": planner,
            "EXECUTOR": executor,
            "CRITIC": critic,
            "TOOL": tool_agent,
        }

    def run_autonomous_loop(
        self,
        task_description: str,
        max_iterations: int = MAX_ITERATIONS,
        convergence_threshold: float = CONVERGENCE_THRESHOLD,
    ) -> AutonomousLoopResult:
        """
        boucle autonome principale.

        a chaque iteration :
        1. PLANNER genere ou revise le plan (prend en compte le feedback du CRITIC)
        2. EXECUTOR execute le plan etape par etape (respect des dependances DAG)
        3. CRITIC evalue le resultat et donne un score + feedback
        4. si score >= seuil : on s'arrete (convergence)
        5. sinon : iteration suivante avec re-planning base sur le feedback

        c'est une vraie boucle de controle, pas un pipeline lineaire.
        """
        result = AutonomousLoopResult(
            task_description=task_description,
            iterations=0,
            final_score=0.0,
            converged=False,
            final_response="",
        )

        self.logger.log_workflow(
            f"autonomous_loop:{task_description[:50]}",
            "started",
            {"max_iterations": max_iterations, "threshold": convergence_threshold},
        )

        # nettoyer le blackboard pour cette nouvelle session
        self.blackboard.clear_all()

        current_score = 0.0
        iteration = 0

        try:
            while iteration < max_iterations:
                iteration += 1
                self.logger.log_task_event(
                    f"iteration_{iteration}",
                    f"Debut iteration {iteration}/{max_iterations}",
                )

                # --- PHASE 1 : SCORING pour choisir l'agent de planification ---
                # on calcule le score de tous les agents avant de decider
                # ca permet de detecter si un agent est en train de planter
                agent_scores = AgentScorer.score_agents(
                    self._agents,
                    task_description,
                    preferred_type="PLANNER",
                )
                result.agent_scores = agent_scores

                # --- PHASE 2 : PLANNER ---
                plan_result = self.planner.run(task_description, iteration=iteration)
                result.plan_history.append(
                    {
                        "iteration": iteration,
                        "steps_count": len(plan_result.get("steps", [])),
                        "complexity": plan_result.get("complexity", "unknown"),
                        "success": plan_result.get("success", False),
                    }
                )

                if not plan_result.get("success") or not plan_result.get("steps"):
                    # le planner a echoue, on essaie quand meme de continuer
                    self.logger.log_task_event(
                        f"iteration_{iteration}",
                        "Planner a echoue, tentative sans plan structure",
                    )
                    break

                # --- PHASE 3 : EXECUTOR (avec support async des etapes independantes) ---
                exec_result = asyncio.run(
                    self._execute_async(task_description, plan_result.get("steps", []))
                )
                result.execution_history.append(
                    {
                        "iteration": iteration,
                        "results_count": len(exec_result.get("results", [])),
                        "summary": exec_result.get("summary", ""),
                        "success": exec_result.get("success", False),
                    }
                )

                # --- PHASE 4 : CRITIC ---
                critic_result = self.critic.run(task_description)
                current_score = critic_result.get("score", 0.0)
                approved = critic_result.get("approved", False)

                result.critic_history.append(
                    {
                        "iteration": iteration,
                        "score": current_score,
                        "approved": approved,
                        "feedback": critic_result.get("feedback", ""),
                        "needs_replanning": critic_result.get(
                            "needs_replanning", False
                        ),
                    }
                )

                self.logger.log_task_event(
                    f"iteration_{iteration}",
                    f"Score critique : {current_score:.2f}, approuve : {approved}",
                )

                # --- PHASE 5 : CONDITION DE TERMINAISON ---
                if current_score >= convergence_threshold or approved:
                    result.converged = True
                    self.logger.log_workflow(
                        f"autonomous_loop:{task_description[:50]}",
                        "converged",
                        {"score": current_score, "iteration": iteration},
                    )
                    break

                # si pas approuve, le planner re-planifiera en prenant en compte le feedback
                # le feedback est deja sur le blackboard, le prochain appel planner.run() le lira
                self.logger.log_task_event(
                    f"iteration_{iteration}",
                    f"Score insuffisant ({current_score:.2f} < {convergence_threshold}), re-planning...",
                )

        except Exception as exc:
            result.error = str(exc)
            self.logger.log_workflow(
                f"autonomous_loop:{task_description[:50]}",
                "error",
                {"error": str(exc)},
            )

        # --- PHASE 6 : SYNTHESE DU RESULTAT FINAL ---
        result.iterations = iteration
        result.final_score = current_score
        result.finished_at = datetime.now().isoformat()
        result.final_response = self._synthesize_response(result)

        self.logger.log_workflow(
            f"autonomous_loop:{task_description[:50]}",
            "completed",
            {
                "iterations": iteration,
                "final_score": current_score,
                "converged": result.converged,
            },
        )

        return result

    async def _execute_async(
        self,
        task_description: str,
        steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        execute les etapes du plan de maniere asynchrone quand c'est possible.
        les etapes sans dependances sont executees en parallele.
        les etapes avec dependances attendent leurs predecesseurs.

        c'est le mecanisme de parallelisation qui rend le systeme plus rapide
        pour les plans avec des etapes independantes.
        """
        if not steps:
            return {"results": [], "summary": "Aucune etape.", "success": True}

        # grouper les etapes par niveau de dependance (tri topologique)
        levels = self._topological_sort(steps)

        all_results: List[Dict[str, Any]] = []
        completed_steps: set = set()

        for level in levels:
            # les etapes du meme niveau n'ont pas de dependances entre elles
            # on peut les executer en parallele avec asyncio.gather
            tasks = [
                asyncio.to_thread(self._execute_single_step, step, task_description)
                for step in level
            ]
            level_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, step_result in enumerate(level_results):
                if isinstance(step_result, Exception):
                    step_result = {
                        "step_id": level[i].get("id", "?"),
                        "success": False,
                        "error": str(step_result),
                        "output": None,
                    }
                if isinstance(step_result, dict):
                    all_results.append(step_result)
                completed_steps.add(level[i].get("id", ""))

        # ecrire les resultats sur le blackboard pour le CriticAgent
        self.blackboard.write(
            "execution", "results", all_results, author="EXECUTOR_ASYNC"
        )
        self.blackboard.write(
            "execution",
            "summary",
            f"{len(all_results)} etapes executees en {len(levels)} niveaux parallelises.",
            author="EXECUTOR_ASYNC",
        )

        return {
            "results": all_results,
            "summary": f"{len(all_results)} etapes executees en {len(levels)} niveaux parallelises.",
            "success": all(
                r.get("success", False) for r in all_results if isinstance(r, dict)
            ),
        }

    def _topological_sort(
        self, steps: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """
        trie les etapes par niveaux de dependance.
        retourne une liste de listes : chaque sous-liste est un niveau
        dont les etapes peuvent etre executees en parallele.
        """
        if not steps:
            return []

        step_map = {s.get("id", str(i)): s for i, s in enumerate(steps)}
        in_degree: Dict[str, int] = {s_id: 0 for s_id in step_map}

        for step in steps:
            for dep in step.get("depends_on", []):
                if dep in in_degree:
                    in_degree[step.get("id", "")] = (
                        in_degree.get(step.get("id", ""), 0) + 1
                    )

        levels: List[List[Dict[str, Any]]] = []
        remaining = dict(in_degree)

        while remaining:
            # prendre toutes les etapes avec in_degree == 0 (pas de dependances non satisfaites)
            current_level = [
                step_map[s_id]
                for s_id, degree in remaining.items()
                if degree == 0 and s_id in step_map
            ]

            if not current_level:
                # cycle detecte, on ajoute tout le reste dans un niveau final
                current_level = [
                    step_map[s_id] for s_id in remaining if s_id in step_map
                ]
                levels.append(current_level)
                break

            levels.append(current_level)

            # supprimer les etapes traitees et mettre a jour les in-degrees
            processed = {s.get("id", "") for s in current_level}
            remaining = {
                s_id: degree
                for s_id, degree in remaining.items()
                if s_id not in processed
            }

            for s_id in list(remaining.keys()):
                step = step_map.get(s_id)
                if step:
                    deps_done = sum(
                        1 for dep in step.get("depends_on", []) if dep in processed
                    )
                    remaining[s_id] = max(0, remaining[s_id] - deps_done)

        return levels

    def _execute_single_step(
        self,
        step: Dict[str, Any],
        task_context: str,
    ) -> Dict[str, Any]:
        """execute une seule etape, utilise par _execute_async via asyncio.to_thread"""
        # deleger a l'executor ou au tool_agent selon le type d'etape
        agent_type = step.get("agent", "EXECUTOR").upper()
        step_desc = step.get("description", "etape inconnue")

        if agent_type == "TOOL":
            result = self.tool_agent.run(step_desc)
        else:
            result = self.executor._execute_step(step, task_context)

        return result

    def _synthesize_response(self, result: AutonomousLoopResult) -> str:
        """
        synthetise une reponse finale lisible depuis l'historique d'execution.
        extrait les outputs des etapes reussies et les presente de facon coherente.
        """
        if result.error:
            return f"La boucle autonome a rencontre une erreur : {result.error}"

        exec_results = self.blackboard.read("execution", "results", default=[])

        if not exec_results:
            return (
                "La boucle autonome a termine sans produire de resultats exploitables."
            )

        # extraire les outputs des etapes reussies
        outputs = []
        for r in exec_results:
            if isinstance(r, dict) and r.get("success") and r.get("output"):
                desc = r.get("description", "")
                out = r.get("output", "")
                if desc and out:
                    outputs.append(f"**{desc}**\n{out}")

        if outputs:
            response_parts = [
                f"Tache accomplie en {result.iterations} iteration(s) "
                f"(score final : {result.final_score:.0%}).\n"
            ]
            response_parts.extend(outputs)

            if not result.converged:
                response_parts.append(
                    f"\nNote : le systeme n'a pas atteint le seuil de convergence "
                    f"({CONVERGENCE_THRESHOLD:.0%}) apres {result.iterations} iterations. "
                    "Le resultat peut etre partiel."
                )

            return "\n\n".join(response_parts)

        # fallback : resume textuel
        summary = self.blackboard.read("execution", "summary", "Execution terminee.")
        return (
            f"{summary}\n\n"
            f"Iterations : {result.iterations} | "
            f"Score final : {result.final_score:.0%} | "
            f"Convergence : {'oui' if result.converged else 'non'}"
        )

    def get_system_report(self) -> Dict[str, Any]:
        """
        rapport complet sur l'etat du systeme.
        utile pour le monitoring et le debug depuis l'interface.
        """
        agent_stats = {}
        for name, agent in self._agents.items():
            success = getattr(agent, "success_count", 0)
            errors = getattr(agent, "error_count", 0)
            total = success + errors
            agent_stats[name] = {
                "success_count": success,
                "error_count": errors,
                "total_runs": total,
                "success_rate": success / total if total > 0 else 0.0,
            }

        return {
            "timestamp": datetime.now().isoformat(),
            "agents": agent_stats,
            "blackboard_summary": self.blackboard.summary(),
            "convergence_threshold": CONVERGENCE_THRESHOLD,
            "max_iterations": MAX_ITERATIONS,
        }
