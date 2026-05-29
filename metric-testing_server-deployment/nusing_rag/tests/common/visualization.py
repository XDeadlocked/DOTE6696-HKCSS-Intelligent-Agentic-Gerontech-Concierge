from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from tests.common.io import ensure_dir

plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Liberation Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _format_label(label: str, width: int = 18) -> str:
    normalized = label.replace("_", " ").replace("-", " ")
    return "\n".join(textwrap.wrap(normalized, width=width)) if len(normalized) > width else normalized


def save_bar_chart(
    path: Path,
    labels: list[str],
    values: list[float],
    title: str,
    ylabel: str,
) -> Path:
    ensure_dir(path.parent)
    sns.set_theme(style="whitegrid")
    formatted_labels = [_format_label(label, width=24) for label in labels]
    fig_height = max(4, len(labels) * 0.9)
    plt.figure(figsize=(10, fig_height))
    ax = sns.barplot(x=values, y=formatted_labels, orient="h")
    ax.set_title(title)
    ax.set_ylabel("")
    ax.set_xlabel(ylabel)
    ax.set_xlim(0, max(values) * 1.1 if values else 1)
    for index, value in enumerate(values):
        ax.text(value + 0.01, index, f"{value:.4f}", va="center", fontsize=9)
    plt.subplots_adjust(left=0.30, right=0.96, top=0.90, bottom=0.12)
    plt.savefig(path, dpi=150)
    plt.close()
    return path


def save_confusion_matrix_heatmap(
    path: Path,
    matrix: list[list[int]] | np.ndarray,
    labels: list[str],
    title: str,
    display_labels: list[str] | None = None,
) -> Path:
    ensure_dir(path.parent)
    sns.set_theme(style="whitegrid")
    shown_labels = display_labels or labels
    shown_labels = [_format_label(label, width=16) for label in shown_labels]
    plt.figure(figsize=(max(7, len(shown_labels) * 1.8), max(5, len(shown_labels) * 1.5)))
    ax = sns.heatmap(
        np.asarray(matrix),
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=shown_labels,
        yticklabels=shown_labels,
    )
    ax.set_title(title)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    plt.xticks(rotation=20, ha="right")
    plt.yticks(rotation=0)
    plt.subplots_adjust(left=0.22, right=0.96, top=0.90, bottom=0.20)
    plt.savefig(path, dpi=150)
    plt.close()
    return path
