from __future__ import annotations

import difflib
import re


def is_numeric_input(text: str) -> bool:
    cleaned = re.sub(r"[,，\s]+", " ", text.strip())
    return bool(cleaned) and all(token.isdigit() for token in cleaned.split())


def parse_number_input(text: str, options: list[str], node_type: str) -> list[str]:
    numbers = re.findall(r"\d+", text)
    selected: list[str] = []
    for number in numbers:
        index = int(number) - 1
        if 0 <= index < len(options) and options[index] not in selected:
            selected.append(options[index])
    if node_type == "single_choice" and len(selected) > 1:
        return selected[:1]
    return selected


def match_text_input(user_input: str, options: list[str], node_type: str) -> list[str]:
    text = user_input.strip()
    if not text:
        return []

    direct_matches = [
        option for option in options if option == text or text in option or option in text
    ]
    if direct_matches:
        return direct_matches[:1] if node_type == "single_choice" else direct_matches

    lowered_options = {option.lower(): option for option in options}
    match = difflib.get_close_matches(text.lower(), lowered_options.keys(), n=3, cutoff=0.45)
    resolved = [lowered_options[item] for item in match]
    if node_type == "single_choice" and resolved:
        return resolved[:1]
    return resolved


def resolve_user_input(
    user_input: str,
    question: str,
    options: list[str],
    node_type: str,
) -> tuple[list[str], str]:
    if is_numeric_input(user_input):
        selected = parse_number_input(user_input, options, node_type)
        if selected:
            return selected, "number"

    matched = match_text_input(user_input, options, node_type)
    if matched:
        return matched, "text"

    return [], "unclear"
