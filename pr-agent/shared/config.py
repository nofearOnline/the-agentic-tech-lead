"""Config loader. One YAML file (pr-agent/config.yaml) is the only source of
truth for models, pricing, and eval settings. Every version reads from it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

ModelRole = Literal[
    "generalist",
    "scout",
    "specialist_reasoning",
    "specialist_narrow",
    "tier1",
    "skeptic",
]


@dataclass(frozen=True)
class Pricing:
    """USD per 1M tokens, for one Anthropic model."""

    input: float
    input_cache_write: float
    input_cache_read: float
    output: float


@dataclass(frozen=True)
class RepoConfig:
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class EvalConfig:
    trials_per_pr: int
    max_cost_per_run_usd: float
    output_dir: str
    prs: tuple[int, ...]


@dataclass(frozen=True)
class Config:
    repo: RepoConfig
    models: dict[ModelRole, str]
    pricing: dict[str, Pricing]
    eval: EvalConfig
    source_path: Path
    backend: str = "auto"               # auto | sdk | cli
    model_ids: dict[str, str] = None  # type: ignore[assignment]  # alias -> snapshot id or "auto"

    def model_for(self, role: ModelRole) -> str:
        if role not in self.models:
            raise KeyError(f"No model configured for role {role!r}")
        return self.models[role]

    def pricing_for(self, model_id: str) -> Pricing:
        if model_id not in self.pricing:
            raise KeyError(
                f"No pricing entry for {model_id!r}. Add it to config.yaml under pricing:"
            )
        return self.pricing[model_id]

    @property
    def output_dir(self) -> Path:
        """Eval output dir resolved relative to the pr-agent folder."""
        base = self.source_path.parent
        out = Path(self.eval.output_dir)
        return out if out.is_absolute() else base / out


def _default_config_path() -> Path:
    """`pr-agent/config.yaml` regardless of where the caller is running from."""
    here = Path(__file__).resolve()
    # shared/config.py -> shared/ -> pr-agent/
    return here.parent.parent / "config.yaml"


def load_config(path: Path | str | None = None) -> Config:
    cfg_path = Path(path) if path else _default_config_path()
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    repo = RepoConfig(owner=raw["repo"]["owner"], name=raw["repo"]["name"])

    models: dict[ModelRole, str] = {}
    for role, model_id in raw["models"].items():
        models[role] = model_id  # type: ignore[index]

    pricing: dict[str, Pricing] = {}
    for model_id, prices in raw["pricing"].items():
        pricing[model_id] = Pricing(
            input=float(prices["input"]),
            input_cache_write=float(prices["input_cache_write"]),
            input_cache_read=float(prices["input_cache_read"]),
            output=float(prices["output"]),
        )

    eval_raw = raw["eval"]
    eval_cfg = EvalConfig(
        trials_per_pr=int(eval_raw["trials_per_pr"]),
        max_cost_per_run_usd=float(eval_raw["max_cost_per_run_usd"]),
        output_dir=str(eval_raw["output_dir"]),
        prs=tuple(int(n) for n in eval_raw["prs"]),
    )

    backend = str(raw.get("backend", "auto")).strip().lower() or "auto"
    model_ids = {str(k): str(v) for k, v in (raw.get("model_ids") or {}).items()}

    return Config(
        repo=repo,
        models=models,
        pricing=pricing,
        eval=eval_cfg,
        source_path=cfg_path,
        backend=backend,
        model_ids=model_ids,
    )


_DOTENV_LOADED = False


def load_dotenv(path: Path | str | None = None) -> None:
    """Load `pr-agent/.env` into os.environ (without overriding existing vars).

    Zero-dependency parser: `KEY=VALUE` per line, `#` comments, optional quotes.
    Idempotent. Existing environment variables always win.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED and path is None:
        return
    env_path = Path(path) if path else (_default_config_path().parent / ".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    if path is None:
        _DOTENV_LOADED = True


def require_anthropic_api_key() -> str:
    """Centralized check so every version dies with the same message."""
    load_dotenv()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set (checked environment and pr-agent/.env)."
        )
    return key
