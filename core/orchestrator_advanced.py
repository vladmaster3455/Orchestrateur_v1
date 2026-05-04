"""
Orchestrateur avancé multi-agents avec gestion de workflows complexes.
Gère la décomposition de tâches, priorités, retry, validation et coordination.
"""

from typing import Any, Dict, List, Optional, Callable, Tuple
from datetime import datetime
from enum import Enum
import asyncio

from core.state import CentralState, Task, TaskStatus, Action, ActionType
from core.autonomous_agent import AutonomousAgent
from core.logging import SystemLogger
from core.quality import PriorityCalculator, AggregateScorer, QualityEvaluator


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class WorkflowNode:
    """Un noeud dans un workflow DAG."""

    def __init__(
        self,
        node_id: str,
        handler: Callable,
        dependencies: List[str] = None,
        retry_policy: Dict[str, Any] = None,
        fallback_handler: Optional[Callable] = None,
    ):
        self.node_id = node_id
        self.handler = handler
        self.dependencies = dependencies or []
        self.retry_policy = retry_policy or {"max_retries": 3, "backoff": "exponential"}
        self.fallback_handler = fallback_handler
        self.result = None
        self.error = None


class AdvancedOrchestrator:
    """
    Orchestrateur avancé pour coordonner plusieurs agents autonomes.
    Gère les workflows complexes, priorités, et validation.
    """

    def __init__(self, central_state: CentralState):
        self.central_state = central_state
        self.agents: Dict[str, AutonomousAgent] = {}
        self.logger = SystemLogger()
        self.workflows: Dict[str, Dict[str, Any]] = {}
        self.task_queue: List[Task] = []
        self.validation_rules: Dict[str, Callable] = {}

    def register_agent(self, agent: AutonomousAgent) -> None:
        """Enregistrer un agent autonome."""
        self.agents[agent.agent_id] = agent
        self.logger.log_workflow(
            f"Agent registered: {agent.agent_id}",
            "success",
        )

    def register_validation_rule(
        self,
        rule_id: str,
        validator: Callable[[Dict[str, Any]], bool],
    ) -> None:
        """Enregistrer une règle de validation."""
        self.validation_rules[rule_id] = validator

    def decompose_complex_task(
        self,
        parent_task: Task,
    ) -> List[Task]:
        """
        Décomposer une tâche complexe en sous-tâches.
        Crée une hierarchie de tâches avec dépendances.
        """
        subtasks = []

        steps = parent_task.context.get("steps", [])
        for i, step in enumerate(steps):
            subtask_id = f"{parent_task.task_id}_step_{i}"

            subtask = self.central_state.create_task(
                task_id=subtask_id,
                description=step.get("description", f"Subtask {i}"),
                priority=parent_task.priority,
                context=step.get("context", {}),
                dependencies=[subtasks[-1].task_id] if subtasks else [],
            )

            subtask.context["parent_task"] = parent_task.task_id
            subtasks.append(subtask)

        parent_task.subtasks = [t.task_id for t in subtasks]
        self.logger.log_task_event(
            parent_task.task_id,
            f"Decomposed into {len(subtasks)} subtasks",
        )

        return subtasks

    def prioritize_queue(self) -> List[Task]:
        """
        Trier la queue de tâches selon les priorités dynamiques.
        Considère l'urgence, l'impact et les dépendances.
        """
        pending_tasks = self.central_state.get_pending_tasks()

        scoring_list = []
        for task in pending_tasks:
            urgency = task.context.get("urgency", 0.5)
            impact = task.context.get("impact", 0.5)
            dependent_count = len([
                t for t in pending_tasks
                if task.task_id in t.dependencies
            ])

            adjusted_priority = PriorityCalculator.calculate_priority(
                base_priority=task.priority,
                urgency=urgency,
                impact=impact,
                dependencies_count=dependent_count,
            )

            scoring_list.append((task, adjusted_priority))

        scoring_list.sort(key=lambda x: x[1], reverse=True)
        self.task_queue = [task for task, _ in scoring_list]

        return self.task_queue

    def assign_task_to_agent(self, task: Task) -> Optional[str]:
        """
        Assigner une tâche au meilleur agent disponible.
        Considère les compétences, la charge actuelle et l'historique.
        """
        if not self.agents:
            return None

        agent_scores = {}

        for agent_id, agent in self.agents.items():
            queue_size = len([
                t for t in self.central_state.tasks.values()
                if t.assigned_agent == agent_id and t.status == TaskStatus.RUNNING
            ])

            error_rate = (
                agent.error_count / (agent.success_count + agent.error_count + 1)
            )

            avg_exec_time = (
                sum(len(a.to_dict().get("content", "")) for a in agent.action_history) /
                max(1, len(agent.action_history))
            )

            reliability = max(0.0, 1.0 - error_rate)

            score = PriorityCalculator.calculate_agent_priority(
                queue_size=queue_size,
                error_rate=error_rate,
                avg_execution_time=avg_exec_time,
                reliability=reliability,
            )

            agent_scores[agent_id] = score

        if not agent_scores:
            return None

        best_agent = max(agent_scores.items(), key=lambda x: x[1])[0]
        task.assigned_agent = best_agent

        self.central_state.update_task(task.task_id, assigned_agent=best_agent)

        self.logger.log_task_event(
            task.task_id,
            f"Assigned to agent {best_agent}",
            {"agent_scores": agent_scores},
        )

        return best_agent

    def execute_workflow(
        self,
        workflow_name: str,
        nodes: Dict[str, WorkflowNode],
    ) -> Dict[str, Any]:
        """
        Exécuter un workflow DAG avec gestion des dépendances et erreurs.
        """
        self.logger.log_workflow(workflow_name, "started")

        workflow_result = {
            "workflow": workflow_name,
            "status": WorkflowStatus.RUNNING.value,
            "nodes": {},
            "errors": [],
            "start_time": datetime.now().isoformat(),
        }

        executed = set()
        failed = set()

        while len(executed) < len(nodes):
            made_progress = False

            for node_id, node in nodes.items():
                if node_id in executed or node_id in failed:
                    continue

                deps_satisfied = all(dep in executed for dep in node.dependencies)

                if not deps_satisfied:
                    continue

                made_progress = True
                result = self._execute_node_with_retry(node)

                if result["success"]:
                    executed.add(node_id)
                    workflow_result["nodes"][node_id] = result
                else:
                    failed.add(node_id)
                    workflow_result["errors"].append(result["error"])

                    if node.fallback_handler:
                        fallback_result = self._execute_fallback(node, result)
                        workflow_result["nodes"][f"{node_id}_fallback"] = fallback_result
                        if fallback_result["success"]:
                            executed.add(node_id)

            if not made_progress:
                remaining = set(nodes.keys()) - executed - failed
                workflow_result["errors"].append(
                    f"Workflow stuck: {remaining} nodes cannot be executed"
                )
                break

        workflow_result["end_time"] = datetime.now().isoformat()

        if len(failed) == 0:
            workflow_result["status"] = WorkflowStatus.COMPLETED.value
            self.logger.log_workflow(workflow_name, "completed")
        else:
            workflow_result["status"] = WorkflowStatus.FAILED.value
            self.logger.log_workflow(workflow_name, "failed", workflow_result)

        self.workflows[workflow_name] = workflow_result
        return workflow_result

    def _execute_node_with_retry(self, node: WorkflowNode) -> Dict[str, Any]:
        """Exécuter un noeud avec stratégie de retry."""
        max_retries = node.retry_policy.get("max_retries", 3)
        backoff = node.retry_policy.get("backoff", "exponential")

        for attempt in range(max_retries + 1):
            try:
                result = node.handler()

                return {
                    "success": True,
                    "result": result,
                    "attempts": attempt + 1,
                }

            except Exception as e:
                if attempt < max_retries:
                    wait_time = self._calculate_backoff(attempt, backoff)
                    self.logger.structured_logger.warning(
                        f"Node {node.node_id} failed, retrying in {wait_time}s",
                        action="retry",
                    )

                else:
                    return {
                        "success": False,
                        "error": str(e),
                        "attempts": attempt + 1,
                    }

        return {
            "success": False,
            "error": "Max retries exceeded",
            "attempts": max_retries + 1,
        }

    def _execute_fallback(
        self,
        node: WorkflowNode,
        original_error: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Exécuter un gestionnaire de fallback."""
        try:
            result = node.fallback_handler(original_error)
            return {
                "success": True,
                "result": result,
                "is_fallback": True,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "is_fallback": True,
            }

    def _calculate_backoff(self, attempt: int, strategy: str) -> float:
        """Calculer le délai d'attente pour un retry."""
        if strategy == "exponential":
            return min(2 ** attempt, 60)
        elif strategy == "linear":
            return attempt * 5
        else:
            return 1

    def validate_result(
        self,
        task: Task,
        result: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Valider un résultat contre les règles de validation.
        Retourne (is_valid, error_message).
        """
        validation_rules = task.context.get("validation_rules", [])

        for rule_id in validation_rules:
            if rule_id not in self.validation_rules:
                continue

            validator = self.validation_rules[rule_id]

            try:
                is_valid = validator(result)

                if not is_valid:
                    return (False, f"Validation rule '{rule_id}' failed")

            except Exception as e:
                return (False, f"Error running validation '{rule_id}': {str(e)}")

        return (True, None)

    def execute_task(self, task: Task) -> Dict[str, Any]:
        """
        Exécuter une tâche avec validation et gestion d'erreurs.
        """
        agent_id = self.assign_task_to_agent(task)

        if not agent_id or agent_id not in self.agents:
            task.error = "No suitable agent found"
            self.central_state.update_task(task.task_id, status=TaskStatus.FAILED)
            return {"success": False, "error": "No suitable agent"}

        agent = self.agents[agent_id]
        self.central_state.update_task(task.task_id, status=TaskStatus.RUNNING)

        try:
            result = agent.run_autonomous_loop(task)

            is_valid, validation_error = self.validate_result(task, result)

            if not is_valid:
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    self.central_state.update_task(
                        task.task_id,
                        status=TaskStatus.PENDING,
                    )
                    return self.execute_task(task)

                else:
                    task.error = validation_error
                    self.central_state.update_task(
                        task.task_id,
                        status=TaskStatus.FAILED,
                        error=validation_error,
                    )
                    return {"success": False, "error": validation_error}

            self.central_state.update_task(
                task.task_id,
                status=TaskStatus.COMPLETED,
                result=result,
            )

            return {"success": True, "result": result}

        except Exception as e:
            task.error = str(e)
            self.central_state.update_task(
                task.task_id,
                status=TaskStatus.FAILED,
                error=str(e),
            )
            return {"success": False, "error": str(e)}

    def generate_execution_report(self) -> Dict[str, Any]:
        """Générer un rapport d'exécution détaillé."""
        state_summary = self.central_state.get_state_summary()

        quality_scores = []

        for task_id, task in self.central_state.tasks.items():
            if task.status == TaskStatus.COMPLETED and task.result:
                score = QualityEvaluator.evaluate_completeness(
                    required_fields=len(task.context.get("required_fields", [])),
                    completed_fields=len(task.result.get("completed_fields", [])),
                )
                quality_scores.append(score)

        aggregate_quality = (
            AggregateScorer.aggregate_scores(quality_scores)
            if quality_scores
            else 0.0
        )

        return {
            "timestamp": datetime.now().isoformat(),
            "state_summary": state_summary,
            "workflow_count": len(self.workflows),
            "completed_workflows": sum(
                1 for w in self.workflows.values()
                if w["status"] == WorkflowStatus.COMPLETED.value
            ),
            "failed_workflows": sum(
                1 for w in self.workflows.values()
                if w["status"] == WorkflowStatus.FAILED.value
            ),
            "agent_statistics": self._get_agent_stats(),
            "quality_report": AggregateScorer.generate_quality_report(
                quality_scores,
                aggregate_quality,
            ),
        }

    def _get_agent_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques de tous les agents."""
        stats = {}

        for agent_id, agent in self.agents.items():
            total_actions = len(agent.action_history)
            success_rate = (
                agent.success_count / total_actions
                if total_actions > 0
                else 0
            )

            stats[agent_id] = {
                "total_actions": total_actions,
                "success_count": agent.success_count,
                "error_count": agent.error_count,
                "success_rate": success_rate,
                "memory_size": len(agent.memory.memories),
            }

        return stats
