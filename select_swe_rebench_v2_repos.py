#!/usr/bin/env python3
"""Filter SWE-rebench-V2 records by repository, task type, difficulty, and language."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shlex
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


DEFAULT_REPOS = [
    "HypothesisWorks/hypothesis",
    "JoshuaKGoldberg/create-typescript-app",
    "TanStack/router",
    "aio-libs/aiohttp",
    "apiflask/apiflask",
    "crawler-commons/crawler-commons",
    "elastic/synthetics",
    "eslint/eslint",
    "getmoto/moto",
    "jhipster/generator-jhipster",
    "jhipster/jhipster-lite",
    "kestra-io/kestra",
    "pallets/click",
    "pallets/werkzeug",
    "pandas-dev/pandas",
    "samuelcolvin/pydantic",
    "serverless/serverless",
    "tannerlinsley/react-query",
    "tipsy/javalin",
    "vuejs/eslint-plugin-vue",
]

BUG_CATEGORIES = {
    "minor_bug",
    "major_bug",
    "regression_bug",
    "edge_case_bug",
    "critical_bug",
    "performance_bug",
    "security_bug",
    "core_bug",
    "bug_fix",
}
FEATURE_CATEGORIES = {
    "core_feat",
    "integration_feat",
    "ui_ux_feat",
    "documentation_enh",
    "dev_ops_enh",
    "performance_feat",
}
LANGUAGE_ALIASES = {
    "javascript": "js",
    "typescript": "ts",
}


def load_repo_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return [line.strip() for line in text.splitlines() if line.strip()]

    if isinstance(value, list):
        values = value
    elif isinstance(value, dict):
        values = value.get("repos", list(value))
    else:
        raise ValueError(f"Repository file must contain a list or object: {path}")
    return [str(repo).strip() for repo in values if str(repo).strip()]


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def test_file_key(value: str) -> str:
    try:
        tokens = shlex.split(value, posix=True)
    except ValueError:
        tokens = value.split()
    for token in tokens:
        if token.startswith("-"):
            continue
        return token.split("::", 1)[0]
    return "__unknown__"


def downsample_pass_to_pass(values: Any, max_count: int, seed: str) -> list[Any]:
    if not isinstance(values, list):
        return []
    if max_count <= 0 or len(values) <= max_count:
        return list(values)

    seed_bytes = hashlib.sha256(seed.encode("utf-8")).digest()[:8]
    rng = random.Random(int.from_bytes(seed_bytes, "big"))
    groups: dict[str, list[Any]] = {}
    for value in values:
        key = test_file_key(value) if isinstance(value, str) else "__unknown__"
        groups.setdefault(key, []).append(value)

    group_keys = sorted(groups)
    rng.shuffle(group_keys)
    for group in groups.values():
        rng.shuffle(group)

    sampled: list[Any] = []
    while len(sampled) < max_count:
        added = False
        for key in group_keys:
            if groups[key]:
                sampled.append(groups[key].pop())
                added = True
                if len(sampled) >= max_count:
                    break
        if not added:
            break
    return sampled


def compact_record(row: dict[str, Any], max_pass_to_pass: int) -> dict[str, Any]:
    metadata = ((row.get("meta") or {}).get("llm_metadata") or {})
    categories = list(metadata.get("pr_categories") or [])
    compacted = {
        "instance_id": row.get("instance_id"),
        "repo": row.get("repo"),
        "base_commit": row.get("base_commit"),
        "language": row.get("language"),
        "task_type": task_type_name(row),
        "task_categories": categories,
        "difficulty": metadata.get("difficulty"),
        "problem_statement": row.get("problem_statement"),
        "patch": row.get("patch"),
        "test_patch": row.get("test_patch"),
        "FAIL_TO_PASS": row.get("FAIL_TO_PASS") or [],
        "PASS_TO_PASS": downsample_pass_to_pass(
            row.get("PASS_TO_PASS"),
            max_pass_to_pass,
            str(row.get("instance_id") or ""),
        ),
        "install_config": row.get("install_config"),
    }
    return compacted


def category_flags(row: dict[str, Any]) -> tuple[bool, bool]:
    metadata = ((row.get("meta") or {}).get("llm_metadata") or {})
    categories = set(metadata.get("pr_categories") or [])
    return bool(categories & BUG_CATEGORIES), bool(categories & FEATURE_CATEGORIES)


def task_type_name(row: dict[str, Any]) -> str:
    has_bug, has_feature = category_flags(row)
    if has_bug and has_feature:
        return "mixed"
    if has_bug:
        return "bug"
    if has_feature:
        return "feat"
    return "mixed"


def normalized_language(value: Any) -> str:
    language = str(value or "unknown").strip().lower()
    return LANGUAGE_ALIASES.get(language, language)


def matches_filters(
    row: dict[str, Any],
    task_types: set[str] | None,
    difficulties: set[str] | None,
    languages: set[str] | None,
) -> bool:
    has_bug, has_feature = category_flags(row)
    if task_types and not (("bug" in task_types and has_bug) or ("feat" in task_types and has_feature)):
        return False

    difficulty = str(
        (((row.get("meta") or {}).get("llm_metadata") or {}).get("difficulty"))
        or "unknown"
    ).lower()
    if difficulties and difficulty not in difficulties:
        return False
    if languages and normalized_language(row.get("language")) not in languages:
        return False
    return True


def select_records(
    source: Path,
    repositories: set[str],
    task_types: set[str] | None,
    difficulties: set[str] | None,
    languages: set[str] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parquet = pq.ParquetFile(source)
    all_repo_records: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for batch in parquet.iter_batches():
        for row in batch.to_pylist():
            repo = row.get("repo")
            if repo not in repositories:
                continue
            all_repo_records.append(row)
            if matches_filters(row, task_types, difficulties, languages):
                selected.append(row)
    return all_repo_records, selected


def build_stats(
    source: Path,
    requested_repos: list[str],
    all_repo_records: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    filters: dict[str, Any],
) -> dict[str, Any]:
    all_by_repo: dict[str, list[dict[str, Any]]] = {repo: [] for repo in requested_repos}
    selected_by_repo: dict[str, list[dict[str, Any]]] = {repo: [] for repo in requested_repos}
    for row in all_repo_records:
        all_by_repo[row["repo"]].append(row)
    for row in selected:
        selected_by_repo[row["repo"]].append(row)

    repo_stats: dict[str, dict[str, Any]] = {}
    for repo in requested_repos:
        rows = all_by_repo[repo]
        selected_rows = selected_by_repo[repo]
        difficulty_counts = Counter(
            str((((row.get("meta") or {}).get("llm_metadata") or {}).get("difficulty")) or "unknown")
            for row in rows
        )
        type_counts = Counter(task_type_name(row) for row in rows)
        repo_stats[repo] = {
            "count": len(rows),
            "bug": type_counts["bug"],
            "feat": type_counts["feat"],
            "mixed": type_counts["mixed"],
            "easy": difficulty_counts["easy"],
            "medium": difficulty_counts["medium"],
            "hard": difficulty_counts["hard"],
            "unknown_difficulty": difficulty_counts["unknown"],
            "selected_count": len(selected_rows),
        }

    type_counts = Counter(task_type_name(row) for row in all_repo_records)
    difficulty_counts = Counter(
        str((((row.get("meta") or {}).get("llm_metadata") or {}).get("difficulty")) or "unknown")
        for row in all_repo_records
    )
    language_counts = Counter(normalized_language(row.get("language")) for row in selected)
    return {
        "source": str(source),
        "filters": filters,
        "requested_repo_count": len(requested_repos),
        "matched_repo_count": sum(bool(all_by_repo[repo]) for repo in requested_repos),
        "missing_repos": [repo for repo in requested_repos if not all_by_repo[repo]],
        "source_records_for_repositories": len(all_repo_records),
        "selected_records": len(selected),
        "source_task_type_counts": dict(sorted(type_counts.items())),
        "source_difficulty_counts": dict(sorted(difficulty_counts.items())),
        "selected_language_counts": dict(sorted(language_counts.items())),
        "repositories": repo_stats,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select repositories from the SWE-rebench-V2 parquet dataset."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("SWE-rebench-V2/train-00000-of-00001.parquet"),
        help="Input SWE-rebench-V2 parquet file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("SWE-rebench-V2/selected_20_repos"),
        help="Output directory for the selected JSON file, statistics, and README.",
    )
    parser.add_argument(
        "--repo",
        action="append",
        dest="repos",
        help="Repository to include; repeat this option for multiple repositories.",
    )
    parser.add_argument(
        "--repo-file",
        type=Path,
        help="Text file with one owner/repo per line, or JSON list/object.",
    )
    parser.add_argument(
        "--task-type",
        nargs="+",
        choices=("bug", "feat"),
        help="Keep records containing any bug or feature category. Mixed records match either value.",
    )
    parser.add_argument(
        "--difficulty",
        nargs="+",
        choices=("easy", "medium", "hard"),
        help="Keep one or more difficulty values; omitted means all values.",
    )
    parser.add_argument(
        "--language",
        nargs="+",
        help="Keep one or more source languages, such as python, java, js, ts, or typescript.",
    )
    parser.add_argument(
        "--output-file",
        default="selected_data.json",
        help="Name of the single selected JSON array inside --output-dir.",
    )
    parser.add_argument(
        "--max-pass-to-pass",
        type=int,
        default=30,
        help="Maximum PASS_TO_PASS entries per record; use 0 to keep all entries.",
    )
    parser.add_argument(
        "--no-compact",
        action="store_true",
        help="Keep all original source fields and do not downsample PASS_TO_PASS.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repos and args.repo_file:
        raise SystemExit("Use --repo or --repo-file, not both.")

    if args.repos:
        repositories = args.repos
    elif args.repo_file:
        repositories = load_repo_file(args.repo_file)
    else:
        repositories = DEFAULT_REPOS

    repositories = list(dict.fromkeys(repositories))
    if not repositories:
        raise SystemExit("No repositories were selected.")
    if not args.source.is_file():
        raise FileNotFoundError(f"Input parquet file not found: {args.source}")

    task_types = set(args.task_type) if args.task_type else None
    difficulties = set(args.difficulty) if args.difficulty else None
    languages = {
        LANGUAGE_ALIASES.get(language.lower(), language.lower())
        for language in args.language
    } if args.language else None

    all_repo_records, selected = select_records(
        args.source,
        set(repositories),
        task_types,
        difficulties,
        languages,
    )
    selected_for_stats = selected
    if not args.no_compact:
        selected = [compact_record(row, args.max_pass_to_pass) for row in selected]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    output_path = args.output_dir / args.output_file
    write_json(output_path, selected)
    filters = {
        "task_type": sorted(task_types) if task_types else None,
        "difficulty": sorted(difficulties) if difficulties else None,
        "language": sorted(languages) if languages else None,
        "compact": not args.no_compact,
        "max_pass_to_pass": None if args.no_compact else args.max_pass_to_pass,
    }
    stats = build_stats(
        args.source,
        repositories,
        all_repo_records,
        selected_for_stats,
        filters,
    )
    write_json(args.output_dir / "statistics.json", stats)

    print(f"source_records\t{stats['source_records_for_repositories']}")
    print(f"selected_records\t{stats['selected_records']}")
    print(f"matched_repos\t{stats['matched_repo_count']}/{stats['requested_repo_count']}")
    print(f"output\t{output_path}")
    print(f"statistics\t{args.output_dir / 'statistics.json'}")
    return 0 if not stats["missing_repos"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
