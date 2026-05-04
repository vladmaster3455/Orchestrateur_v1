"""
Orchestrateur LangGraph multi-agents.
Principe SOLID :
  - SRP : chaque noeud du graphe a une responsabilite unique.
  - OCP : on ajoute des agents sans modifier le graphe de routage.
  - LSP : tous les agents respectent le contrat BaseAgent/AgentResult.
  - ISP : l'orchestrateur expose uniquement route/continue_*.
  - DIP : depend du registry et de BaseAgent, pas des implementations concretes.

L'orchestrateur se connait lui-meme : il sait combien d'agents il possede,
leurs noms, leurs descriptions et leurs capacites. Il peut repondre a toute
question sur son propre fonctionnement.
"""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from agents import AgentRegistry, EmailAgent, RAGAgent
from agents.base_agent import AgentResult
from agents.specialist_agents import CriticAgent, ExecutorAgent, PlannerAgent, ToolAgent
from config import config
from core.memory import Blackboard
from core.orchestrator_advanced import AdvancedOrchestrator
from tools import FileReaderTool, HttpGetTool, PythonExecutorTool, ToolManager

# ---------------------------------------------------------------------------
# Registry : source de verite sur les agents disponibles
# ---------------------------------------------------------------------------
_registry = AgentRegistry()
_registry.register(EmailAgent())
_registry.register(RAGAgent())

# ---------------------------------------------------------------------------
# Systeme autonome avance : blackboard + agents specialises + orchestrateur
# ---------------------------------------------------------------------------
_blackboard = Blackboard()
_tool_manager = ToolManager()
_tool_manager.register(PythonExecutorTool())
_tool_manager.register(FileReaderTool())
_tool_manager.register(HttpGetTool())

_planner = PlannerAgent(_blackboard)
_executor = ExecutorAgent(_blackboard)
_critic = CriticAgent(_blackboard)
_tool_agent = ToolAgent(_blackboard, _tool_manager)

_advanced_orchestrator = AdvancedOrchestrator(
    planner=_planner,
    executor=_executor,
    critic=_critic,
    tool_agent=_tool_agent,
    blackboard=_blackboard,
)


# ---------------------------------------------------------------------------
# LLM partage (instance unique pour performance)
# ---------------------------------------------------------------------------
def _build_llm():
    """construit le LLM depuis la config, sans exposer le fournisseur dans le code."""
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=config.LLM_MODEL, api_key=config.LLM_API_KEY)  # type: ignore[call-arg]


_llm = _build_llm()


# ---------------------------------------------------------------------------
# Modele de sortie structure du routeur
# ---------------------------------------------------------------------------
class RouteDecision(BaseModel):
    agent: str = Field(
        description=(
            "Nom de l'agent a utiliser : EMAIL, RAG, AUTONOMOUS ou ORCHESTRATOR. "
            "Utiliser AUTONOMOUS pour les taches complexes qui necessitent planification, "
            "decomposition en sous-taches, ou plusieurs etapes de raisonnement. "
            "Utiliser ORCHESTRATOR pour toute question generale, "
            "y compris les questions sur le systeme lui-meme."
        )
    )
    extracted: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parametres extraits selon l'agent choisi.",
    )


_router_llm = _llm.with_structured_output(RouteDecision)


# ---------------------------------------------------------------------------
# Etat du graphe LangGraph
# ---------------------------------------------------------------------------
class OrchestratorState(TypedDict):
    history: List[Dict[str, str]]
    current_prompt: str
    selected_agent: str
    extracted_params: Dict[str, Any]
    final_response: str
    explanation: str
    pending_action: Dict[str, Any]
    autonomous_report: Dict[str, Any]


# ---------------------------------------------------------------------------
# Prompt systeme du routeur (auto-genere depuis le registry)
# ---------------------------------------------------------------------------
def _build_router_system_prompt() -> str:
    agent_block = _registry.describe_all()
    tools_list = ", ".join(_tool_manager.available_tools())
    return f"""Tu es le routeur intelligent de l'orchestrateur AISenghor.

Agents disponibles ({_registry.count()} agents metier enregistres) :
{agent_block}

Agents autonomes internes (toujours disponibles) :
- PLANNER / EXECUTOR / CRITIC / TOOL (coordonnes par la boucle autonome)
- Outils disponibles pour TOOL : {tools_list}

Regles de routage :
- Choisis EMAIL si l'utilisateur veut rediger ou envoyer un email.
  Extrais : "to" (adresse), "subject" (sujet), "body" (contenu/intention).
  Si l'adresse email est absente, retourne ORCHESTRATOR pour la demander.
- Choisis RAG si l'utilisateur pose une question sur un document ou veut
  analyser un fichier. Extrais : "question".
- Choisis AUTONOMOUS si la demande est complexe et necessite :
  * plusieurs etapes de traitement
  * une planification et decomposition en sous-taches
  * de l'execution de code Python, lecture de fichier ou requete HTTP
  * une tache de recherche/analyse/synthese approfondie
  Extrais : "task" (description complete de la tache).
- Choisis ORCHESTRATOR pour TOUT le reste : conversation generale,
  questions sur le systeme, questions sur les agents disponibles,
  demandes d'aide, questions simples.

Retourne toujours ORCHESTRATOR si tu manques d'informations pour completer la tache.
"""


# ---------------------------------------------------------------------------
# Prompt systeme de l'orchestrateur (noeud chat)
# ---------------------------------------------------------------------------
def _build_orchestrator_system_prompt() -> str:
    agent_block = _registry.describe_all()
    agent_names = ", ".join(_registry.agent_names())
    count = _registry.count()
    tools_list = ", ".join(_tool_manager.available_tools())

    return f"""Tu es AISenghor, un orchestrateur IA multi-agents autonome.

Tu coordonnes {count} agent(s) metier specialise(s) : {agent_names}.
Tu disposes aussi d'une boucle autonome interne avec 4 agents systeme :
- PLANNER : decompose les taches complexes en sous-taches
- EXECUTOR : execute les sous-taches en respectant les dependances
- CRITIC   : evalue la qualite et demande une revision si necessaire
- TOOL     : utilise les outils ({tools_list})

Description detaillee de tes agents metier :
{agent_block}

Directives :
- Reponds toujours en francais de facon claire et professionnelle.
- Si on te demande combien d'agents tu as, reponds avec exactitude :
  {count} agent(s) metier + 4 agents systeme internes = {count + 4} agents au total.
- Si on te demande quels agents tu as, liste tous les agents.
- Si on te demande ce que tu sais faire, decris toutes tes capacites.
- Ne produis aucun emoji dans tes reponses.
- Pour les taches complexes multi-etapes, explique que tu peux utiliser
  ta boucle autonome (PLANNER -> EXECUTOR -> CRITIC).
"""


# ---------------------------------------------------------------------------
# Noeuds du graphe
# ---------------------------------------------------------------------------


def _router_node(state: OrchestratorState) -> Dict[str, Any]:
    """Analyse l'intention et choisit le bon agent."""
    system_prompt = _build_router_system_prompt()
    messages: List = [SystemMessage(content=system_prompt)]

    for msg in state.get("history", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=state["current_prompt"]))

    raw_decision = _router_llm.invoke(messages)
    decision = (
        raw_decision
        if isinstance(raw_decision, RouteDecision)
        else RouteDecision.model_validate(raw_decision)
    )
    return {
        "selected_agent": decision.agent,
        "extracted_params": decision.extracted,
    }


def _email_node(state: OrchestratorState) -> Dict[str, Any]:
    """Delegue a l'agent EMAIL."""
    agent = _registry.get("EMAIL")
    if not agent:
        return {
            "final_response": "L'agent EMAIL n'est pas disponible.",
            "explanation": "Agent EMAIL absent du registry.",
            "pending_action": None,
        }

    result: AgentResult = agent.run(state["extracted_params"])
    pending_action = None
    if result.status == "needs_input":
        pending_action = {
            "agent": "EMAIL",
            "context": result.context,
            "missing_fields": result.missing_fields,
        }

    return {
        "final_response": result.response,
        "explanation": (
            f"L'agent EMAIL a traite la demande avec le statut : {result.status}."
        ),
        "pending_action": pending_action,
        "autonomous_report": {},
    }


def _rag_node(state: OrchestratorState) -> Dict[str, Any]:
    """Delegue a l'agent RAG."""
    agent = _registry.get("RAG")
    if not agent:
        return {
            "final_response": "L'agent RAG n'est pas disponible.",
            "explanation": "Agent RAG absent du registry.",
            "pending_action": None,
            "autonomous_report": {},
        }

    result: AgentResult = agent.run(state["extracted_params"])
    pending_action = None
    if result.status == "needs_input":
        pending_action = {
            "agent": "RAG",
            "context": result.context,
        }

    return {
        "final_response": result.response,
        "explanation": "L'agent RAG a cherche la reponse dans le document indexe.",
        "pending_action": pending_action,
        "autonomous_report": {},
    }


def _autonomous_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    Noeud de la boucle autonome.
    Prend en charge les taches complexes qui necessitent planification,
    decomposition, execution multi-etapes et auto-correction.
    C'est le noeud le plus puissant du systeme.
    """
    task = state["extracted_params"].get("task", "") or state["current_prompt"]

    loop_result = _advanced_orchestrator.run_autonomous_loop(task)

    return {
        "final_response": loop_result.final_response,
        "explanation": (
            f"Boucle autonome : {loop_result.iterations} iteration(s), "
            f"score={loop_result.final_score:.0%}, "
            f"convergence={'oui' if loop_result.converged else 'non'}."
        ),
        "pending_action": None,
        "autonomous_report": loop_result.to_dict(),
    }


def _orchestrator_node(state: OrchestratorState) -> Dict[str, Any]:
    """
    L'orchestrateur repond directement, en connaissance de ses propres capacites.
    Gere les questions generales ET les questions sur les agents disponibles.
    """
    system_prompt = _build_orchestrator_system_prompt()
    messages: List = [SystemMessage(content=system_prompt)]

    for msg in state.get("history", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=state["current_prompt"]))

    response_text: str = str(_llm.invoke(messages).content)
    return {
        "final_response": response_text,
        "explanation": "",
        "pending_action": None,
        "autonomous_report": {},
    }


# ---------------------------------------------------------------------------
# Routage conditionnel
# ---------------------------------------------------------------------------


def _decide_route(state: OrchestratorState) -> str:
    agent = state.get("selected_agent", "ORCHESTRATOR").upper()
    if agent == "EMAIL":
        return "email"
    if agent == "RAG":
        return "rag"
    if agent == "AUTONOMOUS":
        return "autonomous"
    return "orchestrator"


# ---------------------------------------------------------------------------
# Construction et compilation du graphe
# ---------------------------------------------------------------------------

_builder = StateGraph(OrchestratorState)
_builder.add_node("router", _router_node)
_builder.add_node("email", _email_node)
_builder.add_node("rag", _rag_node)
_builder.add_node("orchestrator", _orchestrator_node)
_builder.add_node("autonomous", _autonomous_node)

_builder.set_entry_point("router")
_builder.add_conditional_edges("router", _decide_route)
_builder.add_edge("email", END)
_builder.add_edge("rag", END)
_builder.add_edge("orchestrator", END)
_builder.add_edge("autonomous", END)

_graph = _builder.compile()


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def route(prompt: str, chat_history: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Point d'entree principal : route une requete utilisateur vers le bon agent.

    Args:
        prompt: message de l'utilisateur.
        chat_history: historique de la conversation sous forme de liste de dicts.

    Returns:
        dict avec les cles : agent, response, explanation, pending_action.
    """
    initial_state: OrchestratorState = {
        "history": chat_history,
        "current_prompt": prompt,
        "selected_agent": "",
        "extracted_params": {},
        "final_response": "",
        "explanation": "",
        "pending_action": {},
        "autonomous_report": {},
    }

    try:
        final_state = _graph.invoke(initial_state)
        return {
            "agent": final_state.get("selected_agent", "ORCHESTRATOR"),
            "response": final_state.get(
                "final_response", "Erreur lors de la generation."
            ),
            "explanation": final_state.get("explanation", ""),
            "pending_action": final_state.get("pending_action"),
            "autonomous_report": final_state.get("autonomous_report", {}),
        }
    except Exception as exc:
        return {
            "agent": "ERROR",
            "response": f"Erreur de l'orchestrateur : {str(exc)}",
            "explanation": "",
            "pending_action": None,
        }


def continue_pending_email(
    user_text: str, pending_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Continue un dialogue multi-tours avec l'agent EMAIL.

    Args:
        user_text: reponse de l'utilisateur au tour precedent.
        pending_context: contexte accumule par l'agent.

    Returns:
        dict avec : agent, response, pending_action.
    """
    agent = _registry.get("EMAIL")
    if not agent:
        return {
            "agent": "EMAIL",
            "response": "L'agent EMAIL n'est pas disponible.",
            "pending_action": None,
        }

    result: AgentResult = agent.run(
        {}, user_text=user_text, pending_context=pending_context or {}
    )

    pending_action = None
    if result.status == "needs_input":
        pending_action = {
            "agent": "EMAIL",
            "context": result.context,
            "missing_fields": result.missing_fields,
        }

    return {
        "agent": "EMAIL",
        "response": result.response,
        "pending_action": pending_action,
    }


def continue_pending_rag(
    user_text: str, pending_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Continue un dialogue multi-tours avec l'agent RAG.

    Args:
        user_text: question ou reponse de l'utilisateur.
        pending_context: contexte accumule par l'agent.

    Returns:
        dict avec : agent, response, pending_action.
    """
    agent = _registry.get("RAG")
    if not agent:
        return {
            "agent": "RAG",
            "response": "L'agent RAG n'est pas disponible.",
            "pending_action": None,
        }

    result: AgentResult = agent.run(
        {}, user_text=user_text, pending_context=pending_context or {}
    )

    pending_action = None
    if result.status == "needs_input":
        pending_action = {
            "agent": "RAG",
            "context": result.context,
        }

    return {
        "agent": "RAG",
        "response": result.response,
        "pending_action": pending_action,
    }
