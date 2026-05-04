# AISenghor - Orchestrateur Multi-Agents IA

Projet fait dans le cadre de mon Master. C'est un orchestrateur multi-agents autonome en Python qui tourne sur Streamlit Cloud. Le but c'est pas juste un chatbot, c'est un vrai systeme ou plusieurs agents travaillent ensemble, se corrigent, et planifient des taches complexes.

---

## C'est quoi exactement ?

Un "orchestrateur" c'est un cerveau central qui recoit la demande de l'utilisateur, analyse ce qu'il veut faire, et decide quel agent doit s'en occuper. Mais la ou ca devient interessant c'est que le systeme peut aussi decomposer une tache complique en sous-taches, les executer, et se corriger si le resultat est pas bon.

Le routage est fait par un LLM qui lit dynamiquement la liste de tous les agents disponibles. Y'a pas de regles codees en dur genre "si le message contient 'email' alors...". C'est le LLM qui decide en lisant les descriptions des agents.

---

## Les agents

### Agents metier (ceux que l'utilisateur voit)

| Agent | Ce qu'il fait |
|-------|---------------|
| EMAIL | Redige et envoie de vrais emails via Brevo. Demande les infos manquantes si besoin. |
| RAG   | Repond a des questions sur des documents uploades (PDF, images, txt) via ChromaDB. |

### Agents systeme (internes, pour les taches complexes)

| Agent    | Role |
|----------|------|
| PLANNER  | Prend un objectif et le decompose en sous-taches avec dependances (graphe DAG) |
| EXECUTOR | Execute les sous-taches dans le bon ordre, en paralele si elles sont independantes |
| CRITIC   | Evalue le resultat avec un score entre 0 et 1, demande une revision si c'est pas bon |
| TOOL     | Utilise les outils disponibles : exec Python, lecture fichier, requete HTTP |

Total : 2 agents metier + 4 agents systeme = **6 agents**. Si on demande a l'orchestrateur combien d'agents il a, il repond 6 avec la description de chacun.

---

## La boucle autonome

Pour les taches complexes, le systeme utilise une vraie boucle de controle (pas un pipeline lineaire) :

```
Utilisateur -> LangGraph Router -> noeud AUTONOMOUS
                                        |
                                   PLANNER genere un plan (JSON avec dependances)
                                        |
                                   EXECUTOR execute les etapes
                                   (en parallele pour celles sans dependances)
                                        |
                                   CRITIC evalue : score entre 0 et 1
                                        |
                               score >= 0.7 ?
                               oui -> synthese et reponse finale
                               non -> feedback au PLANNER -> re-planning -> recommence
                               (max 5 iterations pour eviter les boucles infinies)
```

Le PLANNER lit le feedback du CRITIC sur le blackboard et revise son plan en consequence. C'est ca l'auto-correction.

---

## Utilisation avec LLaMA3 en local (avant d'avoir une cle API)

Si vous avez pas encore de cle Anthropic ou que vous voulez tester en local sans payer, vous pouvez utiliser LLaMA3 via Ollama. C'est ce qu'on faisait au debut du projet avant de migrer vers Claude Haiku pour les performances.

### Installation d'Ollama

```
# telecharger Ollama sur https://ollama.ai
# puis dans un terminal :
ollama pull llama3
ollama serve
```

### Changer le LLM dans orchestrator.py

Dans `orchestrator.py`, remplacez l'instantiation du LLM :

```Orchestrateur_v1/orchestrator.py#L1-5
# remplacer cette ligne :
_llm = ChatAnthropic(model="claude-haiku-4-5", api_key=config.LLM_API_KEY)

# par celle-ci :
from langchain_community.chat_models import ChatOllama
_llm = ChatOllama(model="llama3", base_url=config.OLLAMA_URL)
```

Idem dans `agents/specialist_agents.py` pour le LLM partage des agents specialises :

```Orchestrateur_v1/agents/specialist_agents.py#L1-5
# remplacer :
_shared_llm = ChatAnthropic(model="claude-haiku-4-5", api_key=config.LLM_API_KEY)

# par :
from langchain_community.chat_models import ChatOllama
_shared_llm = ChatOllama(model="llama3", base_url="http://localhost:11434")
```

Et dans le `.env` (ou `.env.example` a copier) :

```
OLLAMA_BASE_URL=http://localhost:11434
# laisser ANTHROPIC_API_KEY vide ou pas rempli
```

**Remarque** : LLaMA3 en local est plus lent et les reponses JSON structurees (pour le PLANNER et le CRITIC) sont moins fiables qu'avec Claude. Le systeme a des fallbacks pour gerer ca mais le taux de succes de la boucle autonome sera plus bas.

---

## Configuration des cles

Les cles sont chargees depuis le fichier `.env` (jamais commite dans git).

```
cp .env.example .env
nano .env   # ou editez avec votre editeur prefere
```

Le fichier `.env.example` contient des valeurs placeholder que vous remplacez par vos vraies cles. Les variables d'environnement attendues sont documentees dans ce fichier exemple. Le code source ne contient aucune cle en dur, tout passe par `config.py` qui charge depuis l'env.

Pour Streamlit Cloud, mettez les memes valeurs dans Settings > Secrets de votre app (format TOML).

---

## Installation

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# editez .env avec vos cles
streamlit run app.py
```

---

## Structure du projet

```
Orchestrateur_v1/
    app.py                         interface Streamlit (couche affichage uniquement)
    orchestrator.py                graphe LangGraph + fonctions publiques (route, continue_*)
    config.py                      chargement des cles depuis .env ou Streamlit secrets

    agents/
        base_agent.py              BaseAgent + AgentCapability + AgentResult (contrats abstraits)
        email_agent.py             EmailAgent avec validator, composer et sender separes
        rag_agent.py               RAGAgent avec LlamaIndex + ChromaDB
        specialist_agents.py       PlannerAgent, CriticAgent, ExecutorAgent, ToolAgent
        registry.py                AgentRegistry avec describe_all() pour l'auto-description
        __init__.py

    core/
        memory.py                  AgentMemory (court/long terme) + Blackboard (memoire partagee)
        state.py                   CentralState, Task, TaskStatus, Action
        logging.py                 logging structure par agent
        quality.py                 PriorityCalculator, AgentScorer, QualityEvaluator
        orchestrator_advanced.py   AdvancedOrchestrator + boucle autonome + tri topologique DAG
        autonomous_agent.py        boucle Plan-Act-Observe-Reflect (base abstraite)

    tools/
        tool_manager.py            ToolManager + BaseTool + ToolResult
        builtin_tools.py           PythonExecutorTool, FileReaderTool, HttpGetTool
        __init__.py

    ui/
        sidebar.py                 barre laterale Streamlit
        styles.py                  CSS injecte dans l'app

    data/                          donnees generees (gitignored)
        documents/                 fichiers uploades
        chroma_db/                 base vectorielle persistante
        logs/                      logs structures JSON

    .env.example                   template de configuration (a copier en .env)
    requirements.txt
```

---

## Principes SOLID appliques

- **SRP** : chaque classe fait une seule chose. `EmailContentValidator` valide, `EmailComposer` redige, `BrevoEmailSender` envoie. C'est pas une seule grosse classe qui fait tout.
- **OCP** : pour ajouter un agent on cree une classe et on fait `_registry.register(MonAgent())`. On touche a rien d'autre.
- **LSP** : tous les agents heritent de `BaseAgent` et retournent un `AgentResult`. On peut les utiliser de facon interchangeable.
- **ISP** : l'orchestrateur expose seulement 3 fonctions publiques. Les agents exposent seulement `run()` et `capabilities`.
- **DIP** : l'orchestrateur depend de `BaseAgent` (abstraction), pas des classes concretes. Les prompts sont generes depuis `_registry.describe_all()` donc si on ajoute un agent le routeur le connait auto.

---

## Memoire et communication entre agents

Y'a trois niveaux de memoire :

1. **AgentMemory** : chaque agent a sa propre memoire court terme, long terme et episodique. Un agent peut se souvenir de ses erreurs et adapter son comportement.

2. **Blackboard** : tableau blanc partage entre tous les agents. Le PLANNER ecrit son plan dans `namespace='plan'`, l'EXECUTOR ecrit ses resultats dans `namespace='execution'`, le CRITIC ecrit son evaluation dans `namespace='critic'`. Chaque agent lit ce dont il a besoin sans connaitre les autres.

3. **Session Streamlit** : l'historique des conversations est garde dans `st.session_state`.

---

## Ajouter un nouvel agent

1. Creer `agents/mon_agent.py` qui herite de `BaseAgent`
2. Implementer `capabilities` (propriete) et `run()` qui retourne un `AgentResult`
3. Dans `orchestrator.py` faire `_registry.register(MonAgent())`
4. C'est tout. Le routeur LLM connait automatiquement le nouvel agent parce que les prompts sont construits depuis `_registry.describe_all()`.

---

## Ce qui est prevu pour la suite

- Support multi-LLM : Groq pour les taches simples (plus rapide), Claude Opus pour les taches complexes
- Persistance du blackboard entre sessions (actuellement reinitialie a chaque conversation)
- Agent WhatsApp via Twilio
- Monitoring en temps reel des scores et iterations dans la sidebar
- Tests unitaires par agent
