from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RecommendationSummary:
    node_id: str
    content: str
    device_tag: str
    category_id: str


class LogicRuleEngine:
    def __init__(self, rule_data: dict[str, Any]) -> None:
        self.rule_data = rule_data
        self.nodes = rule_data.get("nodes", {})
        self.recommend_nodes = rule_data.get("recommend_nodes", {})
        self.meta = rule_data.get("meta", {})
        self.start_node = self.meta.get("start_node", "node_01_role")

    def is_recommend_node(self, node_id: str) -> bool:
        return node_id in self.recommend_nodes

    def get_question_node(self, node_id: str) -> dict[str, Any] | None:
        return self.nodes.get(node_id)

    def get_next_nodes(self, node_id: str, selected_options: list[str]) -> list[str]:
        node = self.nodes.get(node_id)
        if not node:
            return []
        next_map = node.get("next", {})
        next_nodes: list[str] = []
        for option in selected_options:
            next_node = next_map.get("*") if "*" in next_map else next_map.get(option)
            if not next_node:
                continue
            if isinstance(next_node, list):
                for item in next_node:
                    if item not in next_nodes:
                        next_nodes.append(item)
            elif next_node not in next_nodes:
                next_nodes.append(next_node)
        return next_nodes

    def get_recommendation_summary(self, recommend_ids: list[str]) -> list[RecommendationSummary]:
        result: list[RecommendationSummary] = []
        seen: set[str] = set()
        for recommend_id in recommend_ids:
            node = self.recommend_nodes.get(recommend_id)
            if not node or recommend_id in seen:
                continue
            seen.add(recommend_id)
            result.append(
                RecommendationSummary(
                    node_id=recommend_id,
                    content=node.get("content", recommend_id),
                    device_tag=node.get("device_tag", ""),
                    category_id=node.get("category_id", ""),
                )
            )
        return result
