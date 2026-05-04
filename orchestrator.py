import json
from typing import TypedDict, Annotated, Dict, Any, List
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field

from config import config
from agents import EmailAgent, RAGAgent, AgentRegistry

# --- Define State ---
class AgentState(TypedDict):
    history: List[Dict[str, str]]
    current_prompt: str
    selected_agent: str
    extracted_params: dict
    final_response: str
    explanation: str
    pending_action: dict

# --- Output Model for Routing ---
class RouteOutput(BaseModel):
    agent: str = Field(description="Agent à utiliser (EMAIL, RAG ou autre)")
    extracted: dict = Field(description="Paramètres extraits selon l'agent choisi. Par exemple 'question' pour le RAG.")

# ==============================================================================
# --- ANCIENNE IMPLEMENTATION (LLaMA 3) ---
# Lors de la V1 du projet, nous utilisions LLaMA 3 en local pour des raisons de 
# confidentialité via Ollama, avant de migrer vers Claude 3.5 Haiku pour des 
# performances et une rapidité accrues dans la V2.
#
# from langchain_community.chat_models import ChatOllama
#
# def get_llm():
#     return ChatOllama(model="llama3")
# ==============================================================================

# Instance globale pour la rapidité
llm = ChatAnthropic(model="claude-haiku-4-5", api_key=config.ANTHROPIC_API_KEY)
router_llm = llm.with_structured_output(RouteOutput)
agent_registry = AgentRegistry()
agent_registry.register(EmailAgent())
agent_registry.register(RAGAgent())

# --- Nœuds (Nodes) ---
def router_node(state: AgentState):
    """Analyse l'intention et choisit le bon agent"""
    sys_prompt = """
    Tu es un routeur IA très intelligent. Choisis un agent parmi :
    - EMAIL : Si l'utilisateur veut envoyer un email. Tu dois extraire "to", "subject", et GÉNÉRER le "body". Le "body" DOIT être le message final rédigé et adressé au destinataire (par exemple "Bonjour, ..."). Ne te contente pas de copier la phrase de l'utilisateur, interprète son intention pour écrire le vrai contenu de l'email. IMPORTANT: Si on n'a pas d'adresse email, retourne ORCHESTRATOR d'abord pour demander les infos.
    - RAG : Si l'utilisateur pose une question sur un document. Extraire "question".
    - ORCHESTRATOR : Pour tout le reste, l'orchestrateur gère directement.
    
    Retourne toujours ORCHESTRATOR si tu n'as pas assez d'informations pour compléter la tâche.
    """
    
    messages = [SystemMessage(content=sys_prompt)]
    for msg in state.get("history", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
            
    messages.append(HumanMessage(content=state["current_prompt"]))
    
    res = router_llm.invoke(messages)
    return {"selected_agent": res.agent, "extracted_params": res.extracted}

def email_node(state: AgentState):
    agent = agent_registry.get("EMAIL")
    if agent:
        raw = agent.run(state["extracted_params"])
        res = raw.get("response", "Erreur agent EMAIL.")
        pending_action = None
        if raw.get("status") == "needs_input":
            pending_action = {
                "agent": "EMAIL",
                "context": raw.get("context", {}),
                "missing_fields": raw.get("missing_fields", []),
            }
    else:
        res = "Agent EMAIL indisponible."
        pending_action = None
    return {
        "final_response": res,
        "explanation": f"L'agent EMAIL a été déclenché (LangGraph) avec les paramètres : {state['extracted_params']}",
        "pending_action": pending_action,
    }

def rag_node(state: AgentState):
    agent = agent_registry.get("RAG")
    if agent:
        raw = agent.run(state["extracted_params"])
        res = raw.get("response", "Erreur agent RAG.")
        pending_action = None
        if raw.get("status") == "needs_input":
            pending_action = {
                "agent": "RAG",
                "context": raw.get("context", {}),
            }
    else:
        res = "Agent RAG indisponible."
        pending_action = None
    return {
        "final_response": res,
        "explanation": "L'agent RAG a cherché la réponse dans votre document (via LangGraph).",
        "pending_action": pending_action,
    }

def chat_node(state: AgentState):
    """L'orchestrateur répond directement sans agent chat séparé"""
    sys_prompt = "Tu es l'orchestrateur IA AISenghor. Réponds de façon claire et utile."
    messages = [SystemMessage(content=sys_prompt)]
    
    for msg in state.get("history", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    
    messages.append(HumanMessage(content=state["current_prompt"]))
    res = llm.invoke(messages).content
    
    return {"final_response": res, "explanation": ""}

# --- Routage Conditionnel (Edges) ---
def decide_route(state: AgentState):
    agent = state.get("selected_agent", "CHAT").upper()
    if agent == "EMAIL": return "email"
    if agent == "RAG": return "rag"
    return "chat"

# --- Construction du Graphe (Graph Builder) ---
builder = StateGraph(AgentState)

builder.add_node("router", router_node)
builder.add_node("email", email_node)
builder.add_node("rag", rag_node)
builder.add_node("chat", chat_node)

builder.set_entry_point("router")

# Brancher le routeur vers les bons nœuds
builder.add_conditional_edges("router", decide_route)

# Finir le graphe après chaque agent
builder.add_edge("email", END)
builder.add_edge("rag", END)
builder.add_edge("chat", END)

# Compiler
graph = builder.compile()

# Point d'entrée pour l'application Streamlit
def route(prompt: str, chat_history: list) -> dict:
    initial_state = {
        "history": chat_history,
        "current_prompt": prompt,
        "selected_agent": "",
        "extracted_params": {},
        "final_response": "",
        "explanation": "",
        "pending_action": {}
    }
    
    try:
        final_state = graph.invoke(initial_state)
        return {
            "agent": final_state.get("selected_agent", "CHAT"),
            "response": final_state.get("final_response", "Erreur lors de la génération"),
            "explanation": final_state.get("explanation", ""),
            "pending_action": final_state.get("pending_action"),
        }
    except Exception as e:
        return {
            "agent": "ERROR",
            "response": f"Erreur de l'orchestrateur (LangGraph) : {str(e)}",
            "explanation": "",
            "pending_action": None,
        }


def continue_pending_email(user_text: str, pending_context: dict) -> dict:
    agent = agent_registry.get("EMAIL")
    if not agent:
        return {
            "agent": "EMAIL",
            "response": "Agent EMAIL indisponible.",
            "pending_action": None,
        }
    
    # Laisser l'agent EMAIL gérer la demande des champs et la rédaction
    raw = agent.run({}, user_text=user_text, pending_context=pending_context or {})
    
    pending_action = None
    if raw.get("status") == "needs_input":
        pending_action = {
            "agent": "EMAIL",
            "context": raw.get("context", {}),
            "missing_fields": raw.get("missing_fields", []),
        }
    
    return {
        "agent": "EMAIL",
        "response": raw.get("response", "Erreur agent EMAIL."),
        "pending_action": pending_action,
    }


def continue_pending_rag(user_text: str, pending_context: dict) -> dict:
    agent = agent_registry.get("RAG")
    if not agent:
        return {
            "agent": "RAG",
            "response": "Agent RAG indisponible.",
            "pending_action": None,
        }
    raw = agent.run({}, user_text=user_text, pending_context=pending_context or {})
    pending_action = None
    if raw.get("status") == "needs_input":
        pending_action = {
            "agent": "RAG",
            "context": raw.get("context", {}),
        }
    return {
        "agent": "RAG",
        "response": raw.get("response", "Erreur agent RAG."),
        "pending_action": pending_action,
    }
