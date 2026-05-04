"""
Configuration du système avancé multi-agents.
Paramètres optimisés pour production.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class AdvancedSystemConfig:
    """Configuration du système avancé."""

    MEMORY_CONFIG = {
        "max_short_term_entries": 100,
        "consolidation_threshold_importance": 0.7,
        "consolidation_threshold_access_count": 3,
        "export_interval_seconds": 300,
    }

    TASK_QUEUE_CONFIG = {
        "max_priority": 5,
        "default_priority": 1,
        "max_retries": 3,
        "timeout_seconds": 300,
    }

    AGENT_CONFIG = {
        "max_autonomous_iterations": 10,
        "agent_timeout_seconds": 300.0,
        "error_recovery_enabled": True,
    }

    WORKFLOW_CONFIG = {
        "retry_backoff_strategy": "exponential",
        "max_workflow_retries": 3,
        "workflow_timeout_seconds": 600,
    }

    QUALITY_CONFIG = {
        "evaluation_enabled": True,
        "quality_weights": {
            "accuracy": 0.3,
            "speed": 0.2,
            "resource_efficiency": 0.2,
            "reliability": 0.2,
            "completeness": 0.1,
        },
        "min_quality_score_for_success": 0.6,
    }

    LOGGING_CONFIG = {
        "log_dir": "logs",
        "log_level": "INFO",
        "json_export_enabled": True,
        "max_log_entries_memory": 1000,
    }

    PRIORITY_CONFIG = {
        "urgency_weight": 0.4,
        "impact_weight": 0.4,
        "dependencies_weight": 0.2,
        "queue_score_weight": 0.25,
        "error_score_weight": 0.25,
        "speed_score_weight": 0.25,
        "reliability_score_weight": 0.25,
    }

    VALIDATION_CONFIG = {
        "strict_mode": True,
        "auto_retry_on_validation_fail": True,
        "max_validation_retries": 3,
    }

    PERFORMANCE_CONFIG = {
        "memory_limit_mb": 500,
        "action_history_limit": 10000,
        "cleanup_interval_seconds": 3600,
        "parallel_tasks_max": 5,
    }


class SystemConfigManager:
    """Manager pour les configurations du système."""

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._config = AdvancedSystemConfig()

    @classmethod
    def get_config(cls) -> AdvancedSystemConfig:
        """Get configuration instance."""
        manager = cls()
        return manager._config

    @classmethod
    def update_config(cls, key: str, value: Any) -> None:
        """Update a configuration value."""
        manager = cls()
        if hasattr(manager._config, key):
            setattr(manager._config, key, value)

    @classmethod
    def get_memory_config(cls) -> Dict[str, Any]:
        """Get memory configuration."""
        return cls.get_config().MEMORY_CONFIG

    @classmethod
    def get_task_queue_config(cls) -> Dict[str, Any]:
        """Get task queue configuration."""
        return cls.get_config().TASK_QUEUE_CONFIG

    @classmethod
    def get_agent_config(cls) -> Dict[str, Any]:
        """Get agent configuration."""
        return cls.get_config().AGENT_CONFIG

    @classmethod
    def get_workflow_config(cls) -> Dict[str, Any]:
        """Get workflow configuration."""
        return cls.get_config().WORKFLOW_CONFIG

    @classmethod
    def get_quality_config(cls) -> Dict[str, Any]:
        """Get quality configuration."""
        return cls.get_config().QUALITY_CONFIG

    @classmethod
    def get_logging_config(cls) -> Dict[str, Any]:
        """Get logging configuration."""
        return cls.get_config().LOGGING_CONFIG

    @classmethod
    def get_priority_config(cls) -> Dict[str, Any]:
        """Get priority configuration."""
        return cls.get_config().PRIORITY_CONFIG


def get_advanced_system_config() -> AdvancedSystemConfig:
    """Convenience function to get config."""
    return SystemConfigManager.get_config()
