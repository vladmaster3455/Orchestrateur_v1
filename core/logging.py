"""
Système de logging structuré et observabilité pour le système multi-agents.
"""

import logging
import json
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path
from enum import Enum


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredLogger:
    """Logger structuré pour production."""

    def __init__(self, name: str, log_dir: str = "data/logs"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True, parents=True)

        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        self.json_log_file = self.log_dir / f"{name}_structured.jsonl"
        self.text_log_file = self.log_dir / f"{name}.log"

        self._setup_handlers()
        self.entries: list = []

    def _setup_handlers(self) -> None:
        """Configure logging handlers."""
        json_handler = logging.FileHandler(self.json_log_file, mode='a')
        json_handler.setLevel(logging.DEBUG)

        text_handler = logging.FileHandler(self.text_log_file, mode='a')
        text_handler.setLevel(logging.DEBUG)
        text_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        text_handler.setFormatter(text_formatter)

        self.logger.addHandler(json_handler)
        self.logger.addHandler(text_handler)

    def log(
        self,
        level: LogLevel,
        message: str,
        agent_id: Optional[str] = None,
        action: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a structured entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "logger": self.name,
            "message": message,
            "agent_id": agent_id,
            "action": action,
            "metadata": metadata or {},
        }
        self.entries.append(entry)

        log_method = getattr(self.logger, level.value.lower())
        log_method(json.dumps(entry))

    def debug(self, message: str, **kwargs) -> None:
        self.log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self.log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self.log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self.log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        self.log(LogLevel.CRITICAL, message, **kwargs)

    def get_entries(
        self,
        agent_id: Optional[str] = None,
        level: Optional[LogLevel] = None,
        limit: int = 100,
    ) -> list:
        """Retrieve log entries with filtering."""
        results = self.entries

        if agent_id:
            results = [e for e in results if e.get("agent_id") == agent_id]

        if level:
            results = [e for e in results if e.get("level") == level.value]

        return results[-limit:]

    def export_entries(self, filepath: str) -> None:
        """Export log entries to JSON file."""
        Path(filepath).write_text(
            json.dumps(self.entries, indent=2)
        )

    def clear(self) -> None:
        """Clear in-memory entries."""
        self.entries = []


class AgentLogger:
    """Logger spécialisé pour un agent."""

    def __init__(self, agent_id: str, log_dir: str = "data/logs"):
        self.agent_id = agent_id
        self.structured_logger = StructuredLogger(f"agent_{agent_id}", log_dir)

    def log_action(
        self,
        action: str,
        details: str,
        status: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an agent action."""
        message = f"[{action}] {details} (status: {status})"
        level = LogLevel.ERROR if status == "error" else LogLevel.INFO
        self.structured_logger.log(
            level,
            message,
            agent_id=self.agent_id,
            action=action,
            metadata=metadata or {},
        )

    def log_plan(self, plan: str, steps: list) -> None:
        """Log agent planning."""
        self.structured_logger.info(
            f"Agent plan created with {len(steps)} steps",
            agent_id=self.agent_id,
            action="plan",
            metadata={"plan": plan, "steps": steps},
        )

    def log_error(self, error: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Log an error."""
        self.structured_logger.error(
            f"Error: {error}",
            agent_id=self.agent_id,
            metadata=context or {},
        )

    def get_history(self, limit: int = 50) -> list:
        """Get agent action history."""
        return self.structured_logger.get_entries(
            agent_id=self.agent_id,
            limit=limit,
        )


class SystemLogger:
    """Global system logger."""

    def __init__(self, log_dir: str = "data/logs"):
        self.structured_logger = StructuredLogger("system", log_dir)

    def log_workflow(
        self,
        workflow_name: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log workflow execution."""
        level = LogLevel.ERROR if status == "error" else LogLevel.INFO
        self.structured_logger.log(
            level,
            f"Workflow {workflow_name} - {status}",
            action="workflow",
            metadata=metadata or {},
        )

    def log_agent_communication(
        self,
        sender: str,
        recipient: str,
        message: str,
    ) -> None:
        """Log agent communication."""
        self.structured_logger.info(
            f"Communication from {sender} to {recipient}",
            action="communication",
            metadata={"sender": sender, "recipient": recipient, "message": message},
        )

    def log_task_event(
        self,
        task_id: str,
        event: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log task event."""
        self.structured_logger.info(
            f"Task {task_id}: {event}",
            action="task",
            metadata={"task_id": task_id, "event": event, **(metadata or {})},
        )

    def get_system_logs(self, limit: int = 100) -> list:
        """Get system logs."""
        return self.structured_logger.get_entries(limit=limit)
