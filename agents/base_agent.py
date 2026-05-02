from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Common contract for all AI agents."""

    name: str
    description: str

    @abstractmethod
    def run(self, extracted: dict, **kwargs) -> str:
        """Execute the agent and return a user-facing response."""
        raise NotImplementedError
