"""
Agent autonome avancé avec boucle plan-act-observe-reflect.
Supporte la planification, l'exécution multi-actions et l'apprentissage.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from core.logging import AgentLogger
from core.memory import AgentMemory, MemoryType
from core.state import Action, ActionType, CentralState, Task, TaskStatus


class AgentState(Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    ERROR_RECOVERY = "error_recovery"


@dataclass
class Plan:
    """Représente un plan avec plusieurs étapes."""

    plan_id: str
    description: str
    steps: List[Dict[str, Any]]
    created_at: datetime
    estimated_duration: float
    priority: int = 0


@dataclass
class Observation:
    """Résultat d'une observation."""

    timestamp: datetime
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert observation to dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "data": self.data,
            "error": self.error,
        }


class AutonomousAgent(ABC):
    """Agent autonome avancé avec boucle autonome complète."""

    def __init__(
        self,
        agent_id: str,
        central_state: CentralState,
        max_iterations: int = 10,
        timeout: float = 300.0,
    ):
        self.agent_id = agent_id
        self.central_state = central_state
        self.max_iterations = max_iterations
        self.timeout = timeout

        self.memory = AgentMemory(agent_id)
        self.logger = AgentLogger(agent_id)
        self.current_state = AgentState.IDLE
        self.current_plan: Optional[Plan] = None
        self.action_history: List[Action] = []
        self.error_count = 0
        self.success_count = 0

    def run_autonomous_loop(
        self,
        task: Task,
        max_iterations: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Boucle autonome complète: Plan -> Act -> Observe -> Reflect -> Repeat.
        """
        max_iterations = max_iterations or self.max_iterations
        iteration = 0
        start_time = datetime.now()

        self.logger.log_action(
            action="autonomous_loop_start",
            details=f"Starting loop for task {task.task_id}",
            metadata={"max_iterations": max_iterations},
        )

        result = {
            "task_id": task.task_id,
            "iterations": 0,
            "completed": False,
            "actions": [],
            "observations": [],
            "final_state": None,
            "error": None,
        }

        while iteration < max_iterations:
            iteration += 1

            try:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > self.timeout:
                    result["error"] = "Timeout exceeded"
                    break

                if not task or task.status == TaskStatus.COMPLETED:
                    result["completed"] = True
                    break

                self._log_iteration(iteration, task)

                plan = self._plan_phase(task)
                if not plan:
                    break

                action_results = self._act_phase(plan, task)
                if not action_results:
                    break

                observations = self._observe_phase(action_results, task)
                self._reflect_phase(observations, task)

                result["actions"].extend(action_results)
                result["observations"].extend([o.to_dict() for o in observations])

                if self._should_stop_loop(task, observations):
                    result["completed"] = True
                    break

            except Exception as e:
                self.error_count += 1
                self.logger.log_error(str(e), {"iteration": iteration})
                result["error"] = str(e)
                self._error_recovery(task, e)
                break

            finally:
                result["iterations"] = iteration

        self.current_state = AgentState.IDLE
        self.logger.log_action(
            action="autonomous_loop_end",
            details=f"Loop ended after {iteration} iterations",
            metadata=result,
        )

        return result

    def _plan_phase(self, task: Task) -> Optional[Plan]:
        """Phase de planification: créer un plan pour accomplir la tâche."""
        self.current_state = AgentState.PLANNING

        try:
            plan = self.plan(task)

            if plan:
                self.memory.store(
                    content=f"Plan created: {plan.description}",
                    memory_type=MemoryType.EPISODIC,
                    tags=["planning", task.task_id],
                    importance=0.7,
                )

                self.logger.log_plan(plan.description, plan.steps)
                self.current_plan = plan

            return plan

        except Exception as e:
            self.logger.log_error(f"Error in planning phase: {str(e)}")
            return None

    def _act_phase(self, plan: Plan, task: Task) -> List[Action]:
        """Phase d'exécution: exécuter les actions du plan."""
        self.current_state = AgentState.EXECUTING
        actions = []

        for i, step in enumerate(plan.steps):
            try:
                action = self.act(step, task)

                if action:
                    action.status = TaskStatus.COMPLETED
                    self.central_state.add_action(action)
                    self.action_history.append(action)
                    actions.append(action)

                    self.logger.log_action(
                        action=f"step_{i}",
                        details=step.get("description", ""),
                        status="success",
                    )

            except Exception as e:
                self.logger.log_error(f"Error in step {i}: {str(e)}")
                action = Action(
                    action_type=ActionType.EXECUTE,
                    agent_id=self.agent_id,
                    content=str(step),
                    status=TaskStatus.FAILED,
                    error=str(e),
                )
                actions.append(action)
                break

        self.success_count += len(
            [a for a in actions if a.status == TaskStatus.COMPLETED]
        )

        return actions

    def _observe_phase(self, actions: List[Action], task: Task) -> List[Observation]:
        """Phase d'observation: vérifier les résultats des actions."""
        self.current_state = AgentState.OBSERVING
        observations = []

        for action in actions:
            try:
                observation = self.observe(action, task)
                observations.append(observation)

                self.memory.store(
                    content=f"Observation: {observation.data}",
                    memory_type=MemoryType.SHORT_TERM,
                    tags=["observation", task.task_id],
                    importance=0.6,
                )

            except Exception as e:
                obs = Observation(
                    timestamp=datetime.now(),
                    success=False,
                    data={},
                    error=str(e),
                )
                observations.append(obs)

        return observations

    def _reflect_phase(self, observations: List[Observation], task: Task) -> None:
        """Phase de réflexion: apprendre des observations."""
        self.current_state = AgentState.REFLECTING

        try:
            self.reflect(observations, task)

            successful_obs = [o for o in observations if o.success]
            if successful_obs:
                insight = self._extract_insights(successful_obs)
                self.memory.store(
                    content=insight,
                    memory_type=MemoryType.LONG_TERM,
                    tags=["insight", task.task_id],
                    importance=0.8,
                )

        except Exception as e:
            self.logger.log_error(f"Error in reflection phase: {str(e)}")

    def _error_recovery(self, task: Task, error: Exception) -> None:
        """Récupération d'erreur avec stratégies de fallback."""
        self.current_state = AgentState.ERROR_RECOVERY

        recovery_action = Action(
            action_type=ActionType.ERROR_RECOVERY,
            agent_id=self.agent_id,
            content=f"Attempting recovery from error: {str(error)}",
            status=TaskStatus.RUNNING,
        )

        try:
            self.recover(task, error)
            recovery_action.status = TaskStatus.COMPLETED
            recovery_action.result = {"recovery_successful": True}

        except Exception as recovery_error:
            recovery_action.status = TaskStatus.FAILED
            recovery_action.error = str(recovery_error)
            self.logger.log_error(f"Recovery failed: {str(recovery_error)}")

        self.central_state.add_action(recovery_action)

    def _should_stop_loop(self, task: Task, observations: List[Observation]) -> bool:
        """Détermine si la boucle doit s'arrêter."""
        if not observations:
            return False

        successful = sum(1 for o in observations if o.success)
        total = len(observations)

        return successful == total and task.status == TaskStatus.COMPLETED

    def _log_iteration(self, iteration: int, task: Task) -> None:
        """Log détails d'une itération."""
        self.logger.log_action(
            action="iteration",
            details=f"Iteration {iteration} for task {task.task_id}",
            status="running",
        )

    def _extract_insights(self, observations: List[Observation]) -> str:
        """Extrait des insights des observations réussies."""
        if not observations:
            return "No successful observations"

        key_learnings = []
        for obs in observations:
            if obs.data:
                key_learnings.append(str(obs.data))

        return f"Learned: {'; '.join(key_learnings)}"

    @abstractmethod
    def plan(self, task: Task) -> Optional[Plan]:
        """
        Créer un plan pour accomplir la tâche.
        À implémenter par les subclasses.
        """
        raise NotImplementedError

    @abstractmethod
    def act(self, step: Dict[str, Any], task: Task) -> Optional[Action]:
        """
        Exécuter une étape du plan.
        À implémenter par les subclasses.
        """
        raise NotImplementedError

    @abstractmethod
    def observe(self, action: Action, task: Task) -> Observation:
        """
        Observer et valider les résultats d'une action.
        À implémenter par les subclasses.
        """
        raise NotImplementedError

    def reflect(self, observations: List[Observation], task: Task) -> None:
        """
        Réfléchir sur les observations.
        Peut être surchargée par les subclasses.
        """
        pass

    def recover(self, task: Task, error: Exception) -> None:
        """
        Stratégie de récupération d'erreur.
        Peut être surchargée par les subclasses.
        """
        pass
