import json
from typing import TypedDict, Annotated, Dict, Any, List
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field

from config import config

# --- Define State ---
class AgentState(TypedDict):
    history: List[Dict[str, str]]
    current_prompt: str
    selected_agent: str
    extracted_params: dict
    final_response: str
    explanation: str

# --- Output Model for Routing ---
class RouteOutput(BaseModel):
    agent: str = Field(description="Agent à utiliser (EMAIL, RAG, CHAT)")
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

# --- Nœuds (Nodes) ---
def router_node(state: AgentState):
    """Analyse l'intention et choisit le bon agent"""
    sys_prompt = """
    Tu es un routeur IA très intelligent. Choisis un agent parmi :
    - EMAIL : Si l'utilisateur veut envoyer un email. Tu dois extraire "to", "subject", et GÉNÉRER le "body". Le "body" DOIT être le message final rédigé et adressé au destinataire (par exemple "Bonjour, ..."). Ne te contente pas de copier la phrase de l'utilisateur, interprète son intention pour écrire le vrai contenu de l'email.
    - RAG : Si l'utilisateur pose une question sur un document. Extraire "question".
    - CHAT : Pour tout le reste. Extraire "intent".
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
    from agents.email_agent import run
    res = run(state["extracted_params"])
    return {
        "final_response": res,
        "explanation": f"L'agent EMAIL a été déclenché (LangGraph) avec les paramètres : {state['extracted_params']}"
    }

def rag_node(state: AgentState):
    from agents.rag_agent import run
    res = run(state["extracted_params"])
    return {
        "final_response": res,
        "explanation": "L'agent RAG a cherché la réponse dans votre document (via LangGraph)."
    }

def chat_node(state: AgentState):
    messages = [SystemMessage(content="Tu es OrchestrateurSENGHOR, un assistant IA poli et tres intelligent. Reponds toujours en texte simple et professionnel.")]
    for msg in state.get("history", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
            
    messages.append(HumanMessage(content=state["current_prompt"]))
    res = llm.invoke(messages)
    return {"final_response": res.content, "explanation": ""}

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
        "explanation": ""
    }
    
    try:
        final_state = graph.invoke(initial_state)
        return {
            "agent": final_state.get("selected_agent", "CHAT"),
            "response": final_state.get("final_response", "Erreur lors de la génération"),
            "explanation": final_state.get("explanation", "")
        }
    except Exception as e:
        return {
            "agent": "ERROR",
            "response": f"Erreur de l'orchestrateur (LangGraph) : {str(e)}",
            "explanation": ""
        }
