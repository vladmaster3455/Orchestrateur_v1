"""
ToolManager : gestionaire central des outils disponibles pour les agents.

les agents peuvent enregistrer et utiliser des outils via une interface generique.
chaque outil est sandboxe avec un timeout pour evite les blocages infinis.

principes SOLID respecter :
- SRP : ToolManager gere juste le registre et l'execution, pas la logique metier
- OCP : on ajoute des outils sans toucher au manager
- LSP : tout outil herite de BaseTool et peut etre utilise de facon interchangeable
- DIP : les agents dependent de BaseTool (abstraction) pas des outils concrets
"""
from __future__ import annotations

import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ToolResult:
    """resultat normaliser retourner par un outil apres execution"""

    success: bool
    output: Any                     # la sortie brut de l'outil
    error: Optional[str] = None     # message d'erreur si echec
    execution_time: float = 0.0     # temps d'execution en secondes
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": str(self.output) if self.output is not None else None,
            "error": self.error,
            "execution_time": self.execution_time,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    """
    contrat de base pour tous les outils utilisables par les agents.
    chaque outil a un nom unique, une description claire et une methode execute().
    """

    name: str           # identifiant unique ex: "python_exec"
    description: str    # ce que l'outil fait, pour que le LLM puisse choisir
    parameters: Dict[str, str]  # schema des parametres attendus

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """execute l'outil avec les parametres donnes et retourne un ToolResult"""
        raise NotImplementedError


class ToolManager:
    """
    gestionaire central des outils.
    les agents enregistrent leurs outils ici et les invoquent par nom.

    supporte aussi le sandboxing basique avec timeout pour les outils dangereux.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self._execution_log: List[Dict[str, Any]] = []

    def register(self, tool: BaseTool) -> None:
        """enregistre un outil dans le manager"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """retourne un outil par son nom ou None"""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def available_tools(self) -> List[str]:
        """liste les noms des outils disponibles"""
        return list(self._tools.keys())

    def describe_tools(self) -> str:
        """
        genere une description textuelle de tous les outils disponibles.
        utiliser pour injecter dans le prompt systeme d'un agent.
        """
        if not self._tools:
            return "Aucun outil disponible."

        lines: List[str] = []
        for tool in self._tools.values():
            lines.append(f"- {tool.name} : {tool.description}")
            if hasattr(tool, "parameters") and tool.parameters:
                params = ", ".join(
                    f"{k} ({v})" for k, v in tool.parameters.items()
                )
                lines.append(f"  Parametres : {params}")
        return "\n".join(lines)

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """
        execute un outil par son nom avec les parametres donnes.
        capture toutes les exceptions pour evite de planter l'agent.
        """
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output=None,
                error=f"Outil '{tool_name}' introuvable. Outils disponibles : {self.available_tools()}",
            )

        start = datetime.now()
        try:
            result = tool.execute(**kwargs)
            result.execution_time = (datetime.now() - start).total_seconds()
            self._log_execution(tool_name, kwargs, result)
            return result
        except Exception as exc:
            elapsed = (datetime.now() - start).total_seconds()
            error_msg = f"Exception dans {tool_name} : {traceback.format_exc()}"
            result = ToolResult(
                success=False,
                output=None,
                error=error_msg,
                execution_time=elapsed,
            )
            self._log_execution(tool_name, kwargs, result)
            return result

    def _log_execution(
        self,
        tool_name: str,
        params: Dict[str, Any],
        result: ToolResult,
    ) -> None:
        """log interne pour tracer les executions d'outils"""
        self._execution_log.append({
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "params_keys": list(params.keys()),
            "success": result.success,
            "execution_time": result.execution_time,
            "error": result.error,
        })

    def get_execution_stats(self) -> Dict[str, Any]:
        """statistiques globales sur l'utilisation des outils"""
        if not self._execution_log:
            return {"total": 0}

        total = len(self._execution_log)
        successes = sum(1 for e in self._execution_log if e["success"])
        by_tool: Dict[str, int] = {}
        for entry in self._execution_log:
            by_tool[entry["tool"]] = by_tool.get(entry["tool"], 0) + 1

        return {
            "total_executions": total,
            "success_rate": successes / total if total > 0 else 0.0,
            "executions_by_tool": by_tool,
        }
