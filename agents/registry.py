from typing import Dict

from .base_agent import BaseAgent


class AgentRegistry:
    """Central registry for runtime agent instances."""

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        key = agent.name.upper()
        self._agents[key] = agent

    def get(self, agent_name: str) -> BaseAgent | None:
        if not agent_name:
            return None
        return self._agents.get(agent_name.upper())

    def has(self, agent_name: str) -> bool:
        return self.get(agent_name) is not None
