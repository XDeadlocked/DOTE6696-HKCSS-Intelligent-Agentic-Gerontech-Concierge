from __future__ import annotations

from dataclasses import dataclass, field

from app.logic_rule.engine import LogicRuleEngine, RecommendationSummary
from app.logic_rule.repository import LogicRuleRepository
from app.logic_rule.resolver import resolve_user_input


@dataclass(slots=True)
class LogicRuleRuntimeState:
    current_node: str
    pending_branches: list[str] = field(default_factory=list)
    collected_recommendations: list[str] = field(default_factory=list)
    qa_history: list[dict[str, object]] = field(default_factory=list)
    is_complete: bool = False


class LogicRuleService:
    def __init__(
        self,
        repository: LogicRuleRepository | None = None,
        engine: LogicRuleEngine | None = None,
    ) -> None:
        self.repository = repository or LogicRuleRepository()
        self.engine = engine or LogicRuleEngine(self.repository.load())

    def start_session(self) -> LogicRuleRuntimeState:
        return LogicRuleRuntimeState(current_node=self.engine.start_node)

    def get_current_question(self, state: LogicRuleRuntimeState) -> dict[str, object] | None:
        return self._build_question_payload(state, present=True)

    def get_recommendations(self, state: LogicRuleRuntimeState) -> list[RecommendationSummary]:
        return self.engine.get_recommendation_summary(state.collected_recommendations)

    def _build_question_payload(
        self,
        state: LogicRuleRuntimeState,
        present: bool,
    ) -> dict[str, object] | None:
        if not state.current_node or self.engine.is_recommend_node(state.current_node):
            return None
        node = self.engine.get_question_node(state.current_node)
        if not node:
            return None
        raw_question = node.get("question", "")
        return {
            "node_id": state.current_node,
            "question": raw_question,
            "raw_question": raw_question,
            "options": node.get("options", []),
            "node_type": node.get("type", "single_choice"),
        }

    def submit_answer(
        self,
        state: LogicRuleRuntimeState,
        user_input: str,
        selected_options: list[str] | None = None,
    ) -> dict[str, object]:
        question_payload = self._build_question_payload(state, present=False)
        if not question_payload:
            state.is_complete = True
            return {"status": "completed", "state": state}

        if selected_options:
            selected = [str(o).strip() for o in selected_options if o]
            method = "multi_select"
        else:
            selected, method = resolve_user_input(
                user_input=user_input,
                question=str(question_payload["question"]),
                options=list(question_payload["options"]),
                node_type=str(question_payload["node_type"]),
            )
        if not selected:
            return {
                "status": "reprompt",
                "reason": "unclear_input",
                "node_id": state.current_node,
            }

        next_nodes = self.engine.get_next_nodes(state.current_node, selected)
        state.qa_history.append(
            {
                "node_id": state.current_node,
                "question": question_payload["question"],
                "options": question_payload["options"],
                "node_type": question_payload["node_type"],
                "selected": selected,
                "next_nodes": next_nodes,
                "resolution_method": method,
            }
        )

        if not next_nodes:
            if state.pending_branches:
                state.current_node = state.pending_branches.pop(0)
            else:
                state.current_node = ""
                state.is_complete = True
                return {"status": "completed", "state": state}
        elif len(next_nodes) == 1:
            state.current_node = next_nodes[0]
        else:
            state.current_node = next_nodes[0]
            for branch in next_nodes[1:]:
                if branch not in state.pending_branches:
                    state.pending_branches.append(branch)

        recommendations = self._collect_available_recommendations(state)
        if recommendations and state.is_complete:
            return {
                "status": "completed",
                "recommendations": recommendations,
                "state": state,
            }
        if recommendations:
            return {
                "status": "recommendation",
                "recommendations": recommendations,
                "state": state,
            }
        return {
            "status": "next_question" if not state.is_complete else "completed",
            "question": self.get_current_question(state),
            "state": state,
        }

    def _collect_available_recommendations(
        self,
        state: LogicRuleRuntimeState,
    ) -> list[RecommendationSummary]:
        collected_now: list[str] = []
        while state.current_node and self.engine.is_recommend_node(state.current_node):
            if state.current_node not in state.collected_recommendations:
                state.collected_recommendations.append(state.current_node)
                collected_now.append(state.current_node)
            if state.pending_branches:
                state.current_node = state.pending_branches.pop(0)
            else:
                state.current_node = ""
                state.is_complete = True
        return self.engine.get_recommendation_summary(collected_now)
