"""
Système de mémoire avancé pour agents autonomes.
Supporte la mémorisation contextuelle, apprentissage et persistance.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum
import json
from pathlib import Path


class MemoryType(Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    WORKING = "working"


class MemoryEntry:
    def __init__(
        self,
        content: str,
        memory_type: MemoryType,
        tags: List[str] = None,
        importance: float = 0.5,
        metadata: Dict[str, Any] = None,
    ):
        self.content = content
        self.memory_type = memory_type
        self.tags = tags or []
        self.importance = max(0.0, min(1.0, importance))
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.access_count = 0
        self.last_accessed = None

    def increment_access(self):
        self.access_count += 1
        self.last_accessed = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "type": self.memory_type.value,
            "tags": self.tags,
            "importance": self.importance,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }


class AgentMemory:
    """Gestionnaire de mémoire pour un agent autonome."""

    def __init__(self, agent_id: str, max_short_term: int = 100):
        self.agent_id = agent_id
        self.max_short_term = max_short_term
        self.memories: Dict[str, List[MemoryEntry]] = {
            mem_type.value: [] for mem_type in MemoryType
        }
        self.access_history: List[Dict[str, Any]] = []

    def store(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        tags: List[str] = None,
        importance: float = 0.5,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """Store a memory entry."""
        entry = MemoryEntry(content, memory_type, tags, importance, metadata)
        self.memories[memory_type.value].append(entry)

        if memory_type == MemoryType.SHORT_TERM:
            if len(self.memories[MemoryType.SHORT_TERM.value]) > self.max_short_term:
                self.memories[MemoryType.SHORT_TERM.value].pop(0)

    def retrieve(
        self,
        tags: List[str] = None,
        memory_type: Optional[MemoryType] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """Retrieve memories by tags and type."""
        if memory_type:
            candidates = self.memories[memory_type.value]
        else:
            candidates = []
            for mem_list in self.memories.values():
                candidates.extend(mem_list)

        if tags:
            candidates = [
                m for m in candidates
                if any(tag in m.tags for tag in tags)
            ]

        candidates.sort(key=lambda m: (m.importance, m.access_count), reverse=True)
        result = candidates[:limit]

        for entry in result:
            entry.increment_access()

        return result

    def consolidate(self) -> None:
        """Consolidate short-term memories to long-term."""
        short_term = self.memories[MemoryType.SHORT_TERM.value]
        to_consolidate = [
            m for m in short_term
            if m.importance >= 0.7 or m.access_count >= 3
        ]

        for memory in to_consolidate:
            memory.memory_type = MemoryType.LONG_TERM
            self.memories[MemoryType.LONG_TERM.value].append(memory)
            short_term.remove(memory)

    def get_context_summary(self, limit: int = 5) -> str:
        """Generate a summary of relevant memories for context."""
        all_memories = []
        for mem_list in self.memories.values():
            all_memories.extend(mem_list)

        all_memories.sort(
            key=lambda m: (m.importance, m.access_count),
            reverse=True
        )

        summary = "\n".join([m.content for m in all_memories[:limit]])
        return summary

    def export(self, filepath: str) -> None:
        """Export memories to JSON file."""
        data = {
            "agent_id": self.agent_id,
            "exported_at": datetime.now().isoformat(),
            "memories": {
                mem_type: [m.to_dict() for m in entries]
                for mem_type, entries in self.memories.items()
            },
        }
        Path(filepath).write_text(json.dumps(data, indent=2))

    def clear(self, memory_type: Optional[MemoryType] = None) -> None:
        """Clear memories."""
        if memory_type:
            self.memories[memory_type.value] = []
        else:
            for key in self.memories:
                self.memories[key] = []
