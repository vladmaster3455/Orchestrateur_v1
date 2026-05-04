"""
État central partagé pour le système multi-agents.
Gère le contexte global, l'historique et la communication entre agents.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ActionType(Enum):
    PLAN = "plan"
    EXECUTE = "execute"
    OBSERVE = "observe"
    COMMUNICATE = "communicate"
    ERROR_RECOVERY = "error_recovery"


@dataclass
class Action:
    """Représente une action exécutée par un agent."""

    action_type: ActionType
    agent_id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.COMPLETED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.action_type.value,
            "agent_id": self.agent_id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class Task:
    """Une tâche à accomplir."""

    task_id: str
    description: str
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    subtasks: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status.value,
            "assigned_agent": self.assigned_agent,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "subtasks": self.subtasks,
            "dependencies": self.dependencies,
            "context": self.context,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }


class CentralState:
    """État central partagé pour tous les agents."""

    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.actions: List[Action] = []
        self.context: Dict[str, Any] = {}
        self.agent_states: Dict[str, Dict[str, Any]] = {}
        self.communication_log: List[Dict[str, Any]] = []
        self.created_at = datetime.now()

    def create_task(
        self,
        task_id: str,
        description: str,
        priority: int = 0,
        context: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
    ) -> Task:
        """Create a new task."""
        task = Task(
            task_id=task_id,
            description=description,
            priority=priority,
            context=context or {},
            dependencies=dependencies or [],
        )
        self.tasks[task_id] = task
        return task

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        assigned_agent: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[Task]:
        """Update task status and metadata."""
        task = self.tasks.get(task_id)
        if not task:
            return None

        if status:
            task.status = status
            if status == TaskStatus.RUNNING and not task.started_at:
                task.started_at = datetime.now()
            elif status == TaskStatus.COMPLETED:
                task.completed_at = datetime.now()

        if assigned_agent:
            task.assigned_agent = assigned_agent

        if result is not None:
            task.result = result

        if error:
            task.error = error

        return task

    def add_action(self, action: Action) -> None:
        """Record an action."""
        self.actions.append(action)

    def get_agent_context(self, agent_id: str) -> Dict[str, Any]:
        """Get context specific to an agent."""
        return self.agent_states.get(agent_id, {})

    def update_agent_context(self, agent_id: str, context: Dict[str, Any]) -> None:
        """Update agent-specific context."""
        if agent_id not in self.agent_states:
            self.agent_states[agent_id] = {}
        self.agent_states[agent_id].update(context)

    def add_communication(
        self,
        sender_id: str,
        recipient_id: str,
        message: str,
        message_type: str = "info",
    ) -> None:
        """Log inter-agent communication."""
        self.communication_log.append(
            {
                "timestamp": datetime.now().isoformat(),
                "sender": sender_id,
                "recipient": recipient_id,
                "message": message,
                "type": message_type,
            }
        )

    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.PENDING]

    def get_running_tasks(self) -> List[Task]:
        """Get all running tasks."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.RUNNING]

    def get_action_history(self, agent_id: Optional[str] = None) -> List[Action]:
        """Get action history, optionally filtered by agent."""
        if agent_id:
            return [a for a in self.actions if a.agent_id == agent_id]
        return self.actions

    def get_state_summary(self) -> Dict[str, Any]:
        """Get a summary of the current state."""
        return {
            "timestamp": datetime.now().isoformat(),
            "total_tasks": len(self.tasks),
            "pending_tasks": len(self.get_pending_tasks()),
            "running_tasks": len(self.get_running_tasks()),
            "completed_tasks": len(
                [t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]
            ),
            "failed_tasks": len(
                [t for t in self.tasks.values() if t.status == TaskStatus.FAILED]
            ),
            "total_actions": len(self.actions),
            "agents_active": list(self.agent_states.keys()),
            "communication_count": len(self.communication_log),
        }

    def export(self, filepath: str) -> None:
        """Export state to JSON file."""
        from pathlib import Path

        data = {
            "created_at": self.created_at.isoformat(),
            "exported_at": datetime.now().isoformat(),
            "tasks": {task_id: task.to_dict() for task_id, task in self.tasks.items()},
            "actions": [action.to_dict() for action in self.actions],
            "communication_log": self.communication_log,
            "agent_states": self.agent_states,
            "summary": self.get_state_summary(),
        }
        Path(filepath).write_text(json.dumps(data, indent=2))

    def clear(self) -> None:
        """Clear all state."""
        self.tasks = {}
        self.actions = []
        self.context = {}
        self.agent_states = {}
        self.communication_log = []
