from __future__ import annotations

import re
from typing import Any


VAGUE_RESULT_TEXTS = {
    "done",
    "ok",
    "okay",
    "looks good",
    "complete",
    "completed",
    "success",
    "successful",
    "passes",
    "passed",
    "fixed",
    "implemented",
    "seems fine",
    "probably passes",
    "all good",
}

FUTURE_CLAIM_PATTERNS = (
    "all five",
    "all settings",
    "future work complete",
    "future slices complete",
    "master prompt satisfied",
    "final goal complete",
)

COMPLETION_WORDS = {
    "updated",
    "changed",
    "complete",
    "completed",
    "set",
    "done",
    "also",
    "now",
    "routes",
    "route",
    "is",
    "are",
}


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip().strip(".,;:")


def _word_norm(value: str) -> str:
    return re.sub(r"[^a-z0-9/_.:=+>-]+", " ", value.lower()).strip()


def _token_phrase(value: str) -> str:
    return re.sub(r"[^a-z0-9/_.:=+>-]+", " ", value.lower()).strip().strip(".,;:")


def _add_token(tokens: list[dict[str, str]], *, source: str, token: Any, role: str) -> None:
    if not isinstance(token, str):
        return
    token = token.strip().strip("\"'`")
    if not token:
        return
    normalized = _compact(token)
    if len(normalized) < 2:
        return
    row = {"source": source, "token": token, "role": role}
    if row not in tokens:
        tokens.append(row)


def _line_parts(value: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    for sep in ("->", "=>", "="):
        if sep in value:
            left, right = value.split(sep, 1)
            if left.strip():
                parts.append((left.strip(), "route_path" if left.strip().startswith("/") else "key"))
            if right.strip():
                parts.append((right.strip(), "new_value"))
            break
    if ":" in value:
        left, right = value.split(":", 1)
        if left.strip():
            parts.append((left.strip(), "key"))
        if right.strip():
            parts.append((right.strip(), "new_value"))
    for match in re.findall(r"/[A-Za-z0-9_./:-]+", value):
        parts.append((match.rstrip(".,;:"), "route_path"))
    return parts


def _tokens_from_text(source: str, text: str) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    _add_token(tokens, source=source, token=text, role="exact_line")
    for part, role in _line_parts(text):
        _add_token(tokens, source=source, token=part, role=role)
    for key, value in re.findall(r"([A-Za-z0-9_.:/-]+)\s*(?:=|->|=>|:)\s*([A-Za-z0-9_.:/+-]+)", text):
        key = key.rstrip(".,;:")
        value = value.rstrip(".,;:")
        if key:
            _add_token(tokens, source=source, token=key, role="route_path" if key.startswith("/") else "key")
        if value:
            _add_token(tokens, source=source, token=value, role="new_value")
        if key and value:
            _add_token(tokens, source=source, token=f"{key}={value}", role="exact_line")
    for match in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]*", text):
        match = match.rstrip(".,;:")
        if len(match) >= 3:
            role = "file" if "." in match else "word"
            _add_token(tokens, source=source, token=match, role=role)
    return tokens


def _selected_obligations(proof_obligations: dict[str, Any], ids: set[str]) -> list[dict[str, Any]]:
    return [
        row
        for row in proof_obligations.get("obligations", [])
        if isinstance(row, dict) and row.get("obligation_id") in ids
    ]


def _selected_probes(probe_plan: dict[str, Any], ids: set[str]) -> list[dict[str, Any]]:
    return [
        row
        for row in probe_plan.get("probes", [])
        if isinstance(row, dict) and set(row.get("obligation_ids", [])) & ids
    ]


def extract_boundary_evidence_tokens(
    *,
    allowed_product_runtime_file: str | None = None,
    slice_change_boundary: dict[str, Any] | None = None,
    proof_obligations: dict[str, Any] | None = None,
    probe_plan: dict[str, Any] | None = None,
    selected_proof_obligation_ids: list[str] | None = None,
    actual_diff_text: str | None = None,
) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    selected = set(selected_proof_obligation_ids or [])
    if allowed_product_runtime_file:
        _add_token(tokens, source="allowed_product_runtime_file", token=allowed_product_runtime_file, role="file")

    boundary = slice_change_boundary or {}
    if boundary.get("section"):
        _add_token(tokens, source="slice_change_boundary", token=str(boundary["section"]).strip("[]"), role="section")
    for change in boundary.get("allowed_changes") or []:
        for key, role in (
            ("section", "section"),
            ("key", "key"),
            ("old_value", "old_value"),
            ("new_value", "new_value"),
            ("old_line", "exact_line"),
            ("new_line", "exact_line"),
        ):
            value = change.get(key)
            _add_token(tokens, source="slice_change_boundary", token=value, role=role)
            if isinstance(value, str):
                for part, part_role in _line_parts(value):
                    _add_token(tokens, source="slice_change_boundary", token=part, role=part_role)

    for obligation in _selected_obligations(proof_obligations or {}, selected):
        for target in obligation.get("target_boundaries", []) or []:
            _add_token(tokens, source="proof_obligation", token=target, role="file")
        claim = obligation.get("claim")
        if isinstance(claim, str):
            for token in _tokens_from_text("proof_obligation", claim):
                _add_token(tokens, source=token["source"], token=token["token"], role=token["role"])

    for probe in _selected_probes(probe_plan or {}, selected):
        expected = probe.get("expected_observation") or {}
        values = expected.values() if isinstance(expected, dict) else []
        for value in values:
            if isinstance(value, str):
                for token in _tokens_from_text("probe_expected_observation", value):
                    role = "expected_observation" if token["role"] == "exact_line" else token["role"]
                    _add_token(tokens, source=token["source"], token=token["token"], role=role)

    if actual_diff_text:
        for line in actual_diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                for token in _tokens_from_text("actual_product_diff", line[1:]):
                    _add_token(tokens, source=token["source"], token=token["token"], role=token["role"])
    return tokens


def is_vague_worker_claim(text: str) -> bool:
    normalized = _word_norm(text).rstrip(".")
    return normalized in VAGUE_RESULT_TEXTS


def _matched(tokens: list[dict[str, str]], text: str) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for row in tokens:
        if not _role_aware_token_match(row, text):
            continue
        matches.append(row)
    return matches


def _role_aware_token_match(row: dict[str, str], text: str) -> bool:
    token = row["token"]
    role = row["role"]
    token_norm = _token_phrase(token)
    if not token_norm:
        return False
    text_norm = _word_norm(text)
    text_compact = _compact(text)

    if role in {"exact_line", "expected_observation", "file", "route_path"}:
        return token_norm in text_compact

    if role in {"key", "section"}:
        phrase = token_norm.replace("_", " ")
        return _bounded_phrase_match(token_norm, text_norm) or _bounded_phrase_match(phrase, text_norm)

    if role in {"new_value", "old_value", "word"}:
        return _bounded_phrase_match(token_norm, text_norm)

    return _bounded_phrase_match(token_norm, text_norm)


def _bounded_phrase_match(phrase: str, text: str) -> bool:
    phrase = phrase.strip()
    if not phrase:
        return False
    pattern = re.compile(rf"(?<![a-z0-9_-]){re.escape(phrase)}(?![a-z0-9_-])")
    return bool(pattern.search(text))


def _has_role(matches: list[dict[str, str]], role: str) -> bool:
    return any(row["role"] == role for row in matches)


def _has_any_role(matches: list[dict[str, str]], roles: set[str]) -> bool:
    return any(row["role"] in roles for row in matches)


def _future_tokens(
    *,
    proof_obligations: dict[str, Any] | None,
    future_proof_obligation_ids: list[str] | None,
    slice_change_boundary: dict[str, Any] | None,
) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    for change in (slice_change_boundary or {}).get("forbidden_changes", []) or []:
        for key, role in (("key", "key"), ("new_value", "new_value"), ("old_value", "old_value"), ("section", "section")):
            _add_token(tokens, source="slice_change_boundary.forbidden_changes", token=change.get(key), role=role)
    for obligation in _selected_obligations(proof_obligations or {}, set(future_proof_obligation_ids or [])):
        for target in obligation.get("target_boundaries", []) or []:
            _add_token(tokens, source="future_proof_obligation", token=target, role="file")
        claim = obligation.get("claim")
        if isinstance(claim, str):
            for token in _tokens_from_text("future_proof_obligation", claim):
                if token["role"] in {"file", "route_path", "key", "new_value", "exact_line"}:
                    _add_token(tokens, source=token["source"], token=token["token"], role=token["role"])
    return tokens


def _matches_boundary_combo(matches: list[dict[str, str]]) -> bool:
    exact_line_match = _has_any_role(matches, {"exact_line", "expected_observation"})
    file_match = _has_role(matches, "file")
    route_match = _has_role(matches, "route_path")
    value_match = _has_any_role(matches, {"new_value", "old_value"})
    key_or_section_match = _has_any_role(matches, {"key", "section"})
    return bool(
        exact_line_match
        or (file_match and value_match)
        or (file_match and route_match)
        or (route_match and value_match)
        or (key_or_section_match and value_match)
    )


def _matches_future_boundary_combo(matches: list[dict[str, str]]) -> bool:
    exact_line_match = _has_any_role(matches, {"exact_line", "expected_observation"})
    route_match = _has_role(matches, "route_path")
    value_match = _has_any_role(matches, {"new_value", "old_value"})
    key_or_section_match = _has_any_role(matches, {"key", "section"})
    return bool(
        exact_line_match
        or (route_match and value_match)
        or (key_or_section_match and value_match)
    )


def detect_future_boundary_claim(
    worker_text: str,
    *,
    proof_obligations: dict[str, Any] | None = None,
    future_proof_obligation_ids: list[str] | None = None,
    slice_change_boundary: dict[str, Any] | None = None,
) -> bool:
    normalized = _word_norm(worker_text)
    if any(pattern in normalized for pattern in FUTURE_CLAIM_PATTERNS):
        return True
    words = set(normalized.split())
    if {"without", "unchanged", "reserved"}.intersection(words):
        return False
    future_matches = _matched(
        _future_tokens(
            proof_obligations=proof_obligations,
            future_proof_obligation_ids=future_proof_obligation_ids,
            slice_change_boundary=slice_change_boundary,
        ),
        worker_text,
    )
    return bool(_matches_future_boundary_combo(future_matches) and COMPLETION_WORDS.intersection(words))


def match_worker_claim_to_current_boundary(
    *,
    worker_text: str,
    allowed_product_runtime_file: str | None = None,
    slice_change_boundary: dict[str, Any] | None = None,
    proof_obligations: dict[str, Any] | None = None,
    probe_plan: dict[str, Any] | None = None,
    selected_proof_obligation_ids: list[str] | None = None,
    future_proof_obligation_ids: list[str] | None = None,
    actual_diff_text: str | None = None,
) -> dict[str, Any]:
    tokens = extract_boundary_evidence_tokens(
        allowed_product_runtime_file=allowed_product_runtime_file,
        slice_change_boundary=slice_change_boundary,
        proof_obligations=proof_obligations,
        probe_plan=probe_plan,
        selected_proof_obligation_ids=selected_proof_obligation_ids,
        actual_diff_text=actual_diff_text,
    )
    matched = _matched(tokens, worker_text)
    exact_line_match = _has_any_role(matched, {"exact_line", "expected_observation"})
    file_match = _has_role(matched, "file")
    route_match = _has_role(matched, "route_path")
    value_match = _has_any_role(matched, {"new_value", "old_value"})
    key_or_section_match = _has_any_role(matched, {"key", "section"})
    word_matches = [row for row in matched if row["role"] == "word"]
    mentions_current = (
        _matches_boundary_combo(matched)
        or (file_match and len(word_matches) >= 2)
    )
    future_tokens = _future_tokens(
        proof_obligations=proof_obligations,
        future_proof_obligation_ids=future_proof_obligation_ids,
        slice_change_boundary=slice_change_boundary,
    )
    future_matches = _matched(future_tokens, worker_text)
    return {
        "mentions_current_boundary": bool(mentions_current),
        "matched_evidence": matched,
        "missing_required_evidence": [] if mentions_current else ["current_boundary_evidence"],
        "mentions_future_boundary": detect_future_boundary_claim(
            worker_text,
            proof_obligations=proof_obligations,
            future_proof_obligation_ids=future_proof_obligation_ids,
            slice_change_boundary=slice_change_boundary,
        ),
        "future_matches": future_matches,
        "vague": is_vague_worker_claim(worker_text),
    }
