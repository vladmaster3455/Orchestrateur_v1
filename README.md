# Multi-Agent Orchestrator 

Projet d'orchestrateur multi-agents en Python pour mon Master. C'est fait pour tourner sur **Streamlit Cloud** et c'est full gratuit (pas besoin de sortir la CB).

## C'est quoi le projet ?

En gros, c'est un "cerveau" central  qui reçoit ton message et décide quel agent doit bosser. 
Il y a 4 agents : WhatsApp, Email, RAG (pour tes docs) et un Chat normal et dautre en cours .

## Structure du projet

Dossier principal : orchestrator/
- app.py (le front Streamlit)
- orchestrator.py (le cerveau qui route)
- agents/ (le dossier avec les scripts des agents)
- documents/ (là où vont tes PDF)
- chroma_db/ (la base de données pour le RAG)
- .env.example (le modèle pour tes clés)
- requirements.txt (les librairies a installer)

---

## Les API Keys (Free tier)

1. LLM API : ou download LLM en local ou Go sur AI Studio pour chopper la `GOOGLE_API_KEY`. au liue de llama3 en local
2. Twilio : Crée un compte trial pour WhatsApp (récupère le SID et le TOKEN).
3. Resend ,Brevo: Pour les emails. Crée une clé sur leur site.

---

## Test de l'Agent Email (Resend)

Si tu veux tester l'envoi d'email directement en ligne de commande (bash) pour voir si ta clé marche, tu peux copier-coller ce code dans ton terminal :

```bash
# Remplace RE_YOUR_API_KEY par ta vraie clé Resend
curl -X POST '[https://api.resend.com/emails](https://api.resend.com/emails)' \\
     -H 'Authorization: Bearer RE_YOUR_API_KEY' \\
     -H 'Content-Type: application/json' \\
     -d '{
       "from": "onboarding@resend.dev",
       "to": "ton-email@example.com",
       "subject": "Test Master Projet",
       "html": "<strong>Ça marche !</strong> L’agent email est bien configuré."
     }'

"""

### Installation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt


### Configuration
cp .env.example .env
nano .env


###
streamlit run app.py"""
 
