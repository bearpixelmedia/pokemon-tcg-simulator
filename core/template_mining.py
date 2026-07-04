from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

_STOPWORDS = {
    "a",
    "an",
    "the",
    "to",
    "your",
    "opponent",
    "this",
    "that",
    "of",
    "and",
    "from",
    "with",
    "for",
    "in",
    "on",
    "is",
    "are",
    "if",
    "you",
    "then",
}


@dataclass(frozen=True)
class ClauseCluster:
    signature: str
    frequency: int
    samples: list[str]
    suggested_template_name: str
    pseudo_regex: str
    primary_tokens: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "frequency": self.frequency,
            "samples": self.samples,
            "suggested_template_name": self.suggested_template_name,
            "pseudo_regex": self.pseudo_regex,
            "primary_tokens": self.primary_tokens,
        }


def normalize_clause(text: str) -> str:
    normalized = text.strip().lower()
    normalized = normalized.replace("’", "'")
    normalized = normalized.replace("pokemon", "pokémon")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def clause_signature(text: str) -> str:
    normalized = normalize_clause(text)
    normalized = re.sub(r"\d+", "{n}", normalized)
    normalized = re.sub(r"'s", "", normalized)
    normalized = re.sub(r"\b(?:heads|tails)\b", "{coin_result}", normalized)
    normalized = re.sub(r"\b(?:basic|special)\b", "{energy_class}", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z']+", text.lower())
    return [token for token in tokens if token not in _STOPWORDS and len(token) > 2]


def _sanitize_template_name(signature: str) -> str:
    raw = re.sub(r"\{[^}]+\}", "var", signature)
    raw = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_")
    if not raw:
        return "template_candidate"
    if len(raw) > 48:
        raw = raw[:48].rstrip("_")
    return f"candidate_{raw}"


def _pseudo_regex_from_signature(signature: str) -> str:
    escaped = re.escape(signature)
    escaped = escaped.replace(r"\{n\}", r"(?P<num>\\d+)")
    escaped = escaped.replace(r"\{coin_result\}", r"(?P<coin_result>heads|tails)")
    escaped = escaped.replace(r"\{energy_class\}", r"(?P<energy_class>basic|special)")
    return rf"^{escaped}$"


def mine_unresolved_templates(
    coverage_report: dict[str, Any], top_n: int = 25, sample_size: int = 3
) -> dict[str, Any]:
    unresolved_entries = coverage_report.get("top_unresolved_clauses", []) or []
    signature_counter = Counter()
    signature_samples: dict[str, list[str]] = defaultdict(list)
    token_counter: dict[str, Counter[str]] = defaultdict(Counter)

    for entry in unresolved_entries:
        if isinstance(entry, list) and len(entry) >= 2:
            clause = str(entry[0])
            frequency = int(entry[1])
        elif isinstance(entry, tuple) and len(entry) >= 2:
            clause = str(entry[0])
            frequency = int(entry[1])
        else:
            clause = str(entry)
            frequency = 1

        signature = clause_signature(clause)
        signature_counter[signature] += frequency

        if len(signature_samples[signature]) < sample_size and clause not in signature_samples[signature]:
            signature_samples[signature].append(clause)

        for token in _tokenize(signature):
            token_counter[signature][token] += frequency

    clusters: list[ClauseCluster] = []
    for signature, frequency in signature_counter.most_common(top_n):
        top_tokens = [token for token, _ in token_counter[signature].most_common(5)]
        cluster = ClauseCluster(
            signature=signature,
            frequency=frequency,
            samples=signature_samples[signature],
            suggested_template_name=_sanitize_template_name(signature),
            pseudo_regex=_pseudo_regex_from_signature(signature),
            primary_tokens=top_tokens,
        )
        clusters.append(cluster)

    total_unresolved = int(coverage_report.get("summary", {}).get("unresolved_text_blocks", 0))
    clustered_count = sum(cluster.frequency for cluster in clusters)

    return {
        "total_unresolved_blocks": total_unresolved,
        "clustered_unresolved_blocks": clustered_count,
        "coverage_of_unresolved_by_clusters_percent": round(
            (clustered_count / total_unresolved * 100) if total_unresolved else 0, 2
        ),
        "clusters": [cluster.to_dict() for cluster in clusters],
    }

