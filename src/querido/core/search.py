"""Cheap command discovery over the existing overview metadata."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)?")
_K1 = 1.5
_B = 0.75


@dataclass(frozen=True)
class SearchDoc:
    name: str
    description: str
    category: str
    subcommands: list[str]
    term_freqs: Counter[str]
    length: int
    field_terms: dict[str, set[str]]


def search_commands(
    intent: str,
    commands: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """Return ranked command matches for a natural-language intent."""
    query_terms = _tokenize(intent)
    docs = [_build_doc(command) for command in commands]
    doc_count = len(docs)
    avgdl = sum(doc.length for doc in docs) / doc_count if docs else 0.0
    doc_freqs = _document_frequencies(docs)

    results = []
    for doc in docs:
        score = _bm25_score(query_terms, doc, doc_freqs, avgdl, doc_count)
        score += _phrase_bonus(intent, doc)
        if score <= 0:
            continue
        results.append(
            {
                "name": doc.name,
                "description": doc.description,
                "category": doc.category,
                "score": round(score, 3),
                "rationale": _build_rationale(query_terms, doc),
                "matched_terms": [term for term in query_terms if term in doc.term_freqs],
                "subcommands": doc.subcommands,
                "help_command": f"qdo {doc.name} --help",
            }
        )

    results.sort(key=lambda item: (-float(item["score"]), str(item["name"])))
    limited = results[: max(limit, 0)]
    return {
        "query": intent,
        "searched_command_count": len(commands),
        "result_count": len(limited),
        "results": limited,
    }


def search_next_steps(result: dict[str, Any]) -> list[dict[str, str]]:
    """Suggest deterministic follow-ups for a search result set."""
    matches = result.get("results") or []
    if not matches:
        return [
            {
                "cmd": "qdo overview",
                "why": "No strong command match; browse the full CLI reference.",
            }
        ]

    top = matches[0]
    steps = [
        {
            "cmd": str(top.get("help_command") or f"qdo {top.get('name', '')} --help").strip(),
            "why": "Inspect flags and examples for the top-ranked command.",
        }
    ]
    if len(matches) > 1:
        steps.append(
            {
                "cmd": "qdo overview",
                "why": "Compare the top matches against the full command reference.",
            }
        )
    return steps


def _build_doc(command: dict[str, Any]) -> SearchDoc:
    name = str(command.get("name") or "")
    description = str(command.get("description") or "")
    category = str(command.get("category") or "")
    subcommands = [str(value) for value in command.get("subcommands") or []]
    options = [str(opt.get("flag", "")) for opt in command.get("options") or []]
    output_keys = sorted(_flatten_shape_keys(command.get("output_shape")))

    name_terms = _tokenize(name)
    description_terms = _tokenize(description)
    category_terms = _tokenize(category)
    subcommand_terms = _tokenize(" ".join(subcommands))
    option_terms = _tokenize(" ".join(options))
    output_terms = _tokenize(" ".join(output_keys))

    weighted_terms = (
        name_terms * 5
        + description_terms * 3
        + subcommand_terms * 2
        + category_terms
        + option_terms
        + output_terms
    )
    term_freqs = Counter(weighted_terms)
    field_terms = {
        "name": set(name_terms),
        "description": set(description_terms),
        "category": set(category_terms),
        "subcommands": set(subcommand_terms),
        "options": set(option_terms),
        "output": set(output_terms),
    }
    return SearchDoc(
        name=name,
        description=description,
        category=category,
        subcommands=subcommands,
        term_freqs=term_freqs,
        length=sum(term_freqs.values()),
        field_terms=field_terms,
    )


def _tokenize(text: str) -> list[str]:
    terms: list[str] = []
    for token in _TOKEN_RE.findall(text.lower()):
        terms.append(token)
        if "-" in token or "_" in token:
            terms.extend(part for part in re.split(r"[-_]", token) if part and part != token)
    return terms


def _flatten_shape_keys(value: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path
            yield from _flatten_shape_keys(child, path)
    elif isinstance(value, list):
        for child in value:
            yield from _flatten_shape_keys(child, prefix)


def _document_frequencies(docs: list[SearchDoc]) -> Counter[str]:
    doc_freqs: Counter[str] = Counter()
    for doc in docs:
        doc_freqs.update(doc.term_freqs.keys())
    return doc_freqs


def _bm25_score(
    query_terms: list[str],
    doc: SearchDoc,
    doc_freqs: Counter[str],
    avgdl: float,
    doc_count: int,
) -> float:
    if not query_terms or not doc.length or avgdl <= 0:
        return 0.0

    score = 0.0
    query_counts = Counter(query_terms)
    total_docs = max(doc_count, 1)
    for term, qf in query_counts.items():
        tf = doc.term_freqs.get(term, 0)
        if not tf:
            continue
        df = doc_freqs.get(term, 0)
        idf = math.log(1.0 + ((total_docs - df + 0.5) / (df + 0.5)))
        denom = tf + _K1 * (1.0 - _B + _B * (doc.length / avgdl))
        score += qf * idf * ((tf * (_K1 + 1.0)) / denom)
    return score


def _phrase_bonus(intent: str, doc: SearchDoc) -> float:
    intent_lc = intent.lower().strip()
    if not intent_lc:
        return 0.0

    bonus = 0.0
    name_lc = doc.name.lower()
    desc_lc = doc.description.lower()
    subcommands_lc = " ".join(doc.subcommands).lower()

    if intent_lc == name_lc:
        bonus += 8.0
    if intent_lc in name_lc:
        bonus += 3.0
    if intent_lc in desc_lc:
        bonus += 2.0
    if intent_lc in subcommands_lc:
        bonus += 1.5

    matched_name_terms = len(set(_tokenize(intent)) & doc.field_terms["name"])
    bonus += matched_name_terms * 0.8
    return bonus


def _build_rationale(query_terms: list[str], doc: SearchDoc) -> str:
    reasons: list[str] = []
    for field, label in (
        ("name", "name"),
        ("description", "description"),
        ("subcommands", "subcommands"),
        ("options", "options"),
        ("output", "output shape"),
    ):
        matches = sorted(set(query_terms) & doc.field_terms[field])
        if matches:
            reasons.append(f"{label}: {', '.join(matches[:3])}")
    if not reasons:
        return "weak semantic match across command metadata"
    return "; ".join(reasons)
