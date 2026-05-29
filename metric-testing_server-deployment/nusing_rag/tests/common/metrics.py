from __future__ import annotations

from statistics import mean

from sklearn.metrics import accuracy_score, precision_recall_fscore_support


def safe_round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def average(values: list[float]) -> float:
    return safe_round(mean(values)) if values else 0.0


def classification_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, float]:
    if not y_true:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="macro",
        zero_division=0,
    )
    return {
        "accuracy": safe_round(accuracy_score(y_true, y_pred)),
        "precision": safe_round(precision),
        "recall": safe_round(recall),
        "f1": safe_round(f1),
    }
