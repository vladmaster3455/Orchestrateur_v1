"""
Registre central des agents.
Principe SOLID :
  - SRP : uniquement gerer l'enregistrement et la decouverte des agents.
  - OCP : on ajoute des agents sans modifier ce fichier.
  - DIP : depend de BaseAgent, pas des classes concretes.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .base_agent import BaseAgent


class AgentRegistry:
    """Registre d'instances d'agents actives au runtime."""

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Enregistre un agent. La cle est son nom en majuscules."""
        self._agents[agent.name.upper()] = agent

    def get(self, agent_name: str) -> Optional[BaseAgent]:
        """Retourne l'agent correspondant ou None."""
        if not agent_name:
            return None
        return self._agents.get(agent_name.upper())

    def has(self, agent_name: str) -> bool:
        """Indique si un agent est enregistre."""
        return self.get(agent_name) is not None

    def all_agents(self) -> List[BaseAgent]:
        """Retourne tous les agents enregistres."""
        return list(self._agents.values())

    def agent_names(self) -> List[str]:
        """Retourne la liste des noms d'agents disponibles."""
        return list(self._agents.keys())

    def describe_all(self) -> str:
        """
        Produit une description textuelle de tous les agents et leurs capacites.
        Utilise par l'orchestrateur pour repondre aux questions sur ses propres capacites.
        """
        if not self._agents:
            return "Aucun agent n'est enregistre pour le moment."

        lines: List[str] = []
        for agent in self._agents.values():
            lines.append(f"Agent : {agent.name}")
            lines.append(f"  Description : {agent.description}")
            lines.append("  Capacites :")
            for cap in agent.capabilities:
                lines.append(f"    - {cap.name} : {cap.description}")
                if cap.examples:
                    examples_str = ", ".join(f'"{e}"' for e in cap.examples)
                    lines.append(f"      Exemples : {examples_str}")
            lines.append("")
        return "\n".join(lines).strip()

    def count(self) -> int:
        """Retourne le nombre d'agents enregistres."""
        return len(self._agents)
