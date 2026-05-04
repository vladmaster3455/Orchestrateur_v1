"""
Intégration du système multi-agents avancé avec Streamlit.
Point d'entrée pour utiliser l'orchestrateur dans l'application principale.
"""

import streamlit as st
from typing import Optional, Dict, Any
from datetime import datetime

from core.state import CentralState, TaskStatus
from core.orchestrator_advanced import AdvancedOrchestrator
from agents.autonomous_email_agent import AutonomousEmailAgent
from agents.autonomous_rag_agent import AutonomousRAGAgent
from config import config


class StreamlitOrchestratorAdapter:
    """
    Adaptateur pour intégrer l'orchestrateur avancé avec Streamlit.
    Gère l'interface utilisateur et la coordination backend.
    """

    def __init__(self):
        """Initialiser l'adaptateur avec état de session Streamlit."""
        if "central_state" not in st.session_state:
            st.session_state.central_state = CentralState()

        if "orchestrator" not in st.session_state:
            st.session_state.orchestrator = AdvancedOrchestrator(
                st.session_state.central_state
            )

            email_agent = AutonomousEmailAgent(st.session_state.central_state)
            rag_agent = AutonomousRAGAgent(st.session_state.central_state)

            st.session_state.orchestrator.register_agent(email_agent)
            st.session_state.orchestrator.register_agent(rag_agent)

        if "task_results" not in st.session_state:
            st.session_state.task_results = {}

    @property
    def orchestrator(self) -> AdvancedOrchestrator:
        """Get orchestrator instance."""
        return st.session_state.orchestrator

    @property
    def central_state(self) -> CentralState:
        """Get central state."""
        return st.session_state.central_state

    def create_and_execute_email_task(
        self,
        recipient: str,
        subject: str,
        body: str,
        priority: int = 1,
    ) -> Dict[str, Any]:
        """Create and execute an email task."""
        task = self.central_state.create_task(
            task_id=f"email_{datetime.now().timestamp()}",
            description=f"Send email to {recipient}",
            priority=priority,
            context={
                "to": recipient,
                "subject": subject,
                "body": body,
            },
        )

        result = self.orchestrator.execute_task(task)
        st.session_state.task_results[task.task_id] = result

        return result

    def create_and_execute_rag_task(
        self,
        question: str,
        priority: int = 1,
    ) -> Dict[str, Any]:
        """Create and execute a RAG task."""
        task = self.central_state.create_task(
            task_id=f"rag_{datetime.now().timestamp()}",
            description=f"Answer question: {question}",
            priority=priority,
            context={
                "question": question,
            },
        )

        result = self.orchestrator.execute_task(task)
        st.session_state.task_results[task.task_id] = result

        return result

    def get_orchestrator_dashboard(self) -> Dict[str, Any]:
        """Generate dashboard data."""
        report = self.orchestrator.generate_execution_report()
        return report

    def render_task_status(self, task_id: str) -> None:
        """Render task status in Streamlit."""
        task = self.central_state.tasks.get(task_id)

        if not task:
            st.error(f"Task {task_id} not found")
            return

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Status", task.status.value)

        with col2:
            if task.started_at:
                elapsed = (datetime.now() - task.started_at).total_seconds()
                st.metric("Duration (s)", f"{elapsed:.1f}")

        with col3:
            st.metric("Priority", task.priority)

        if task.result:
            st.json(task.result)

        if task.error:
            st.error(f"Error: {task.error}")

    def render_orchestrator_stats(self) -> None:
        """Render orchestrator statistics."""
        report = self.get_orchestrator_dashboard()
        summary = report['state_summary']

        st.subheader("System Overview")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Tasks", summary['total_tasks'])

        with col2:
            st.metric("Pending", summary['pending_tasks'])

        with col3:
            st.metric("Completed", summary['completed_tasks'])

        with col4:
            st.metric("Failed", summary['failed_tasks'])

        st.subheader("Quality Report")

        quality = report['quality_report']
        grade = quality['grade']
        score = quality['aggregate_score']

        col1, col2 = st.columns(2)

        with col1:
            st.metric("Overall Grade", grade)

        with col2:
            st.metric("Quality Score", f"{score:.1%}")

        st.subheader("Agent Performance")

        for agent_id, stats in report['agent_statistics'].items():
            with st.expander(f"Agent: {agent_id}"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Success Rate", f"{stats['success_rate']:.1%}")

                with col2:
                    st.metric("Total Actions", stats['total_actions'])

                with col3:
                    st.metric("Errors", stats['error_count'])

    def render_task_queue(self) -> None:
        """Render task queue."""
        pending_tasks = self.central_state.get_pending_tasks()

        if not pending_tasks:
            st.info("No pending tasks")
            return

        st.subheader(f"Pending Tasks ({len(pending_tasks)})")

        for task in pending_tasks:
            with st.expander(f"{task.task_id} - {task.description}"):
                col1, col2 = st.columns(2)

                with col1:
                    st.write(f"Priority: {task.priority}")
                    st.write(f"Status: {task.status.value}")

                with col2:
                    st.write(f"Created: {task.created_at.strftime('%H:%M:%S')}")
                    if task.assigned_agent:
                        st.write(f"Agent: {task.assigned_agent}")

    def render_action_history(self, agent_id: Optional[str] = None) -> None:
        """Render action history."""
        actions = self.central_state.get_action_history(agent_id)

        if not actions:
            st.info("No actions recorded")
            return

        st.subheader(f"Action History ({len(actions)} total)")

        for action in actions[-10:]:
            with st.expander(f"{action.agent_id} - {action.action_type.value}"):
                st.write(f"**Content**: {action.content}")
                st.write(f"**Status**: {action.status.value}")
                st.write(f"**Timestamp**: {action.timestamp.isoformat()}")

                if action.result:
                    st.json(action.result)

                if action.error:
                    st.error(f"Error: {action.error}")


def initialize_advanced_orchestrator():
    """Initialize the advanced orchestrator in Streamlit session."""
    if "adapter" not in st.session_state:
        st.session_state.adapter = StreamlitOrchestratorAdapter()

    return st.session_state.adapter
