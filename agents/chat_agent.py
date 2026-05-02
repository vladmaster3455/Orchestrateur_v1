from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from .base_agent import BaseAgent


class ChatAgent(BaseAgent):
    name = "CHAT"
    description = "General-purpose conversational assistant."

    def run(self, extracted: dict, **kwargs) -> str:
        llm = kwargs.get("llm")
        history = kwargs.get("history", [])
        prompt = extracted.get("prompt", "")

        if llm is None:
            return "Le service de chat est indisponible pour le moment."

        messages = [
            SystemMessage(
                content="Tu es OrchestrateurSENGHOR, un assistant IA poli et tres intelligent. Reponds toujours en texte simple et professionnel."
            )
        ]
        for msg in history:
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg.get("content", "")))
            else:
                messages.append(AIMessage(content=msg.get("content", "")))
        messages.append(HumanMessage(content=prompt))

        res = llm.invoke(messages)
        return res.content
