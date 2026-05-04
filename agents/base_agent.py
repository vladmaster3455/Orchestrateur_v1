"""
Contrat de base pour tous les agents du systeme.
Principe SOLID :
  - SRP : chaque agent a une seule responsabilite metier.
  - OCP : on etend sans modifier cette base.
  - LSP : toute sous-classe respecte ce contrat.
  - ISP : interface minimale et cohesive.
  - DIP : l'orchestrateur depend de cette abstraction, pas des implementations.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentCapability:
    """Decrit une capacite connue d'un agent (utilise par l'orchestrateur)."""
    name: str
    description: str
    required_params: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)


@dataclass
class AgentResult:
    """Resultat normalise retourne par tout agent."""
    status: str          # "completed" | "needs_input" | "failed"
    response: str        # Texte destine a l'utilisateur
    context: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "response": self.response,
            "context": self.context,
            "missing_fields": self.missing_fields,
            "metadata": self.metadata,
        }


class BaseAgent(ABC):
    """
    Contrat commun pour tous les agents IA.
    Chaque agent doit declarer son nom, sa description et ses capacites
    afin que l'orchestrateur puisse se decrire lui-meme avec precision.
    """

    name: str
    description: str

    @property
    @abstractmethod
    def capabilities(self) -> List[AgentCapability]:
        """Liste des capacites que cet agent peut accomplir."""
        raise NotImplementedError

    @abstractmethod
    def run(self, extracted: Dict[str, Any], **kwargs) -> AgentResult:
        """
        Execute l'agent et retourne un AgentResult normalise.

        Args:
            extracted: parametres extraits par le routeur LLM.
            **kwargs:  user_text, pending_context pour les conversations multi-tours.
        """
        raise NotImplementedError
