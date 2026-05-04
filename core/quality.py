"""
Système de scoring de qualité et priorités pour les agents et tâches.
Évalue la performance, la qualité et la pertinence des actions.
"""

from typing import Any, Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class QualityMetric(Enum):
    ACCURACY = "accuracy"
    SPEED = "speed"
    RESOURCE_EFFICIENCY = "resource_efficiency"
    RELIABILITY = "reliability"
    COMPLETENESS = "completeness"


class PriorityLevel(Enum):
    CRITICAL = 5
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    TRIVIAL = 1


@dataclass
class QualityScore:
    """Évaluation de qualité d'une action/tâche."""
    metric: QualityMetric
    score: float
    confidence: float
    timestamp: datetime
    explanation: Optional[str] = None

    def __post_init__(self):
        self.score = max(0.0, min(1.0, self.score))
        self.confidence = max(0.0, min(1.0, self.confidence))


class QualityEvaluator:
    """Évalue la qualité des actions et résultats."""

    @staticmethod
    def evaluate_accuracy(
        expected: Any,
        actual: Any,
        confidence: float = 0.8,
    ) -> QualityScore:
        """Évalue la précision d'un résultat."""
        if expected == actual:
            score = 1.0
        elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            diff = abs(expected - actual)
            max_val = max(abs(expected), abs(actual), 1)
            score = max(0.0, 1.0 - (diff / max_val))
        else:
            score = 0.0

        return QualityScore(
            metric=QualityMetric.ACCURACY,
            score=score,
            confidence=confidence,
            timestamp=datetime.now(),
        )

    @staticmethod
    def evaluate_speed(
        execution_time: float,
        expected_time: float = 5.0,
        confidence: float = 0.9,
    ) -> QualityScore:
        """Évalue la vitesse d'exécution."""
        ratio = execution_time / expected_time if expected_time > 0 else 0
        score = max(0.0, 1.0 - min(ratio / 2.0, 1.0))

        return QualityScore(
            metric=QualityMetric.SPEED,
            score=score,
            confidence=confidence,
            timestamp=datetime.now(),
        )

    @staticmethod
    def evaluate_resource_efficiency(
        resources_used: Dict[str, float],
        resources_available: Dict[str, float],
        confidence: float = 0.7,
    ) -> QualityScore:
        """Évalue l'efficacité des ressources utilisées."""
        if not resources_used or not resources_available:
            return QualityScore(
                metric=QualityMetric.RESOURCE_EFFICIENCY,
                score=1.0,
                confidence=0.5,
                timestamp=datetime.now(),
            )

        total_ratio = 0
        count = 0

        for resource, used in resources_used.items():
            available = resources_available.get(resource, used)
            if available > 0:
                ratio = used / available
                total_ratio += max(0.0, 1.0 - ratio)
                count += 1

        score = total_ratio / count if count > 0 else 0.5

        return QualityScore(
            metric=QualityMetric.RESOURCE_EFFICIENCY,
            score=score,
            confidence=confidence,
            timestamp=datetime.now(),
        )

    @staticmethod
    def evaluate_reliability(
        success_rate: float,
        error_count: int,
        total_attempts: int,
        confidence: float = 0.85,
    ) -> QualityScore:
        """Évalue la fiabilité d'un agent ou processus."""
        score = success_rate if success_rate >= 0 else 0.5

        if error_count > 0:
            error_ratio = error_count / total_attempts if total_attempts > 0 else 0
            score = max(0.0, score - error_ratio)

        return QualityScore(
            metric=QualityMetric.RELIABILITY,
            score=score,
            confidence=confidence,
            timestamp=datetime.now(),
        )

    @staticmethod
    def evaluate_completeness(
        required_fields: int,
        completed_fields: int,
        confidence: float = 0.9,
    ) -> QualityScore:
        """Évalue la complétude d'une tâche."""
        if required_fields <= 0:
            return QualityScore(
                metric=QualityMetric.COMPLETENESS,
                score=1.0,
                confidence=confidence,
                timestamp=datetime.now(),
            )

        score = completed_fields / required_fields
        score = min(1.0, score)

        return QualityScore(
            metric=QualityMetric.COMPLETENESS,
            score=score,
            confidence=confidence,
            timestamp=datetime.now(),
        )


class PriorityCalculator:
    """Calcule les priorités des tâches dynamiquement."""

    @staticmethod
    def calculate_priority(
        base_priority: int,
        urgency: float = 0.5,
        impact: float = 0.5,
        dependencies_count: int = 0,
        weight_urgency: float = 0.4,
        weight_impact: float = 0.4,
        weight_dependencies: float = 0.2,
    ) -> int:
        """
        Calcule une priorité ajustée.

        base_priority: priorité initiale (1-5)
        urgency: valeur 0-1 (0=pas urgent, 1=très urgent)
        impact: valeur 0-1 (0=faible impact, 1=fort impact)
        dependencies_count: nombre de tâches dépendantes
        """
        urgency = max(0.0, min(1.0, urgency))
        impact = max(0.0, min(1.0, impact))

        dep_score = min(1.0, dependencies_count / 10.0)

        adjusted_priority = (
            (urgency * weight_urgency) +
            (impact * weight_impact) +
            (dep_score * weight_dependencies)
        )

        final_priority = int(base_priority + (adjusted_priority * 2))
        return max(1, min(5, final_priority))

    @staticmethod
    def calculate_agent_priority(
        queue_size: int,
        error_rate: float,
        avg_execution_time: float,
        reliability: float = 0.8,
    ) -> float:
        """
        Calcule la priorité d'allocation d'un agent.
        Plus la valeur est élevée, plus l'agent devrait recevoir de tâches.
        """
        queue_score = 1.0 / (1.0 + queue_size / 10.0)
        error_score = max(0.0, 1.0 - error_rate)
        speed_score = max(0.0, 1.0 - (avg_execution_time / 30.0))
        reliability_score = reliability

        priority = (
            (queue_score * 0.25) +
            (error_score * 0.25) +
            (speed_score * 0.25) +
            (reliability_score * 0.25)
        )

        return priority


class AggregateScorer:
    """Agrège les scores de qualité pour un jugement global."""

    @staticmethod
    def aggregate_scores(
        scores: List[QualityScore],
        weights: Optional[Dict[QualityMetric, float]] = None,
    ) -> float:
        """
        Agrège les scores de qualité avec poids optionnels.
        Retourne un score global 0-1.
        """
        if not scores:
            return 0.0

        if weights is None:
            weights = {
                QualityMetric.ACCURACY: 0.3,
                QualityMetric.SPEED: 0.2,
                QualityMetric.RESOURCE_EFFICIENCY: 0.2,
                QualityMetric.RELIABILITY: 0.2,
                QualityMetric.COMPLETENESS: 0.1,
            }

        total_weight = 0.0
        weighted_score = 0.0

        for score in scores:
            metric_weight = weights.get(score.metric, 0.1)
            confidence_adjusted = score.score * score.confidence

            weighted_score += confidence_adjusted * metric_weight
            total_weight += metric_weight

        if total_weight == 0:
            return 0.0

        aggregate = weighted_score / total_weight
        return max(0.0, min(1.0, aggregate))

    @staticmethod
    def generate_quality_report(
        scores: List[QualityScore],
        aggregate: float,
    ) -> Dict[str, Any]:
        """Génère un rapport de qualité détaillé."""
        metrics_summary = {}

        for score in scores:
            metric_name = score.metric.value
            if metric_name not in metrics_summary:
                metrics_summary[metric_name] = []
            metrics_summary[metric_name].append({
                "score": score.score,
                "confidence": score.confidence,
                "timestamp": score.timestamp.isoformat(),
            })

        return {
            "aggregate_score": aggregate,
            "grade": AggregateScorer._score_to_grade(aggregate),
            "metrics": metrics_summary,
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def _score_to_grade(score: float) -> str:
        """Convertit un score numérique en note letter."""
        if score >= 0.9:
            return "A"
        elif score >= 0.8:
            return "B"
        elif score >= 0.7:
            return "C"
        elif score >= 0.6:
            return "D"
        else:
            return "F"
