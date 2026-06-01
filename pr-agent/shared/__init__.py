"""Shared utilities used by every version of the PR-review agent.

Importable as a package so that v1_single_shot, v2_..., bench, etc. can all
write `from shared import ...`. Keep this surface tight; if a helper is
specific to one version, it should live in that version's folder.
"""

from .config import Config, ModelRole, Pricing, load_config
from .cost import compute_cost, Usage, add_usage, EMPTY_USAGE
from .llm import CallResult, call, extract_fenced_json
from .pr import PullRequest, fetch_pull_request, parse_pr_arg
from .types import Finding

__all__ = [
    "Config",
    "ModelRole",
    "Pricing",
    "load_config",
    "compute_cost",
    "Usage",
    "add_usage",
    "EMPTY_USAGE",
    "call",
    "CallResult",
    "extract_fenced_json",
    "PullRequest",
    "fetch_pull_request",
    "parse_pr_arg",
    "Finding",
]
