from __future__ import annotations

import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from paperflow.ai.claude_adapter import ClaudeAdapter
from paperflow.ai.codex_adapter import CodexAdapter
from paperflow.ai.mock_adapter import MockAdapter
from paperflow.workspace import AIProfile, ProviderConfig


SAFE_CODEX_ARGS = {
    "--ephemeral",
    "--skip-git-repo-check",
    "--disable",
    "--config",
}
SAFE_CLAUDE_ARGS = {
    "--no-session-persistence",
    "--verbose",
}
DANGEROUS_FRAGMENTS = {
    "dangerously",
    "full-access",
    "workspace-write",
    "bypass",
    "approval",
    "permission-mode",
    "allowedtools",
    "disallowedtools",
}


@dataclass(frozen=True)
class CapabilityReport:
    provider: str
    available: bool
    executable: str
    version: str = ""
    analyze_help_available: bool = False
    detail: str = ""


@dataclass(frozen=True)
class Provenance:
    provider: str
    model: str
    analysis_profile: str
    prompt_version: str
    schema_version: int
    paper_content_hash: str
    created_at: str
    publisher: str = ""


def validate_extra_args(provider: str, values: list[str]) -> list[str]:
    allowed = SAFE_CODEX_ARGS if provider == "codex" else SAFE_CLAUDE_ARGS
    for value in values:
        normalized = value.casefold()
        if any(fragment in normalized for fragment in DANGEROUS_FRAGMENTS):
            raise ValueError(f"Dangerous {provider} argument is forbidden: {value}")
        if value.startswith("-") and value.split("=", 1)[0] not in allowed:
            raise ValueError(
                f"Unsupported {provider} argument: {value}; allowed flags: "
                f"{', '.join(sorted(allowed))}"
            )
    return list(values)


class AIProvider(ABC):
    name: str

    def __init__(self, root: Path, config: ProviderConfig):
        self.root = root
        self.config = config
        validate_extra_args(self.name, config.extra_args)

    @abstractmethod
    def check_available(self) -> CapabilityReport: ...

    def list_models(self) -> list[str]:
        # CLI providers generally expose user-configured aliases rather than a
        # stable machine-readable model catalogue.
        return [self.config.model] if self.config.model else ["<cli-default>"]

    def validate_config(self) -> None:
        validate_extra_args(self.name, self.config.extra_args)

    @abstractmethod
    def analyze(self, metadata: Any, text_path: Path, profile: AIProfile) -> Any: ...

    def get_provenance(
        self,
        *,
        profile_name: str,
        prompt_version: str,
        schema_version: int,
        paper_content_hash: str,
        created_at: str,
        publisher: str = "",
    ) -> Provenance:
        return Provenance(
            provider=self.name,
            model=self.config.model,
            analysis_profile=profile_name,
            prompt_version=prompt_version,
            schema_version=schema_version,
            paper_content_hash=paper_content_hash,
            created_at=created_at,
            publisher=publisher,
        )


class CLIProvider(AIProvider):
    analyze_subcommand: list[str]

    def check_available(self) -> CapabilityReport:
        executable = shutil.which(self.config.executable)
        if not executable:
            return CapabilityReport(
                provider=self.name,
                available=False,
                executable=self.config.executable,
                detail="executable not found on PATH",
            )
        try:
            version = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            help_result = subprocess.run(
                [executable, *self.analyze_subcommand, "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CapabilityReport(
                provider=self.name,
                available=False,
                executable=executable,
                detail=str(exc),
            )
        return CapabilityReport(
            provider=self.name,
            available=version.returncode == 0 and help_result.returncode == 0,
            executable=executable,
            version=(version.stdout or version.stderr).strip().splitlines()[0],
            analyze_help_available=help_result.returncode == 0,
            detail=(
                ""
                if version.returncode == 0 and help_result.returncode == 0
                else "CLI version or analysis help probe failed"
            ),
        )


class CodexProvider(CLIProvider):
    name = "codex"
    analyze_subcommand = ["exec"]

    def analyze(self, metadata: Any, text_path: Path, profile: AIProfile) -> Any:
        model = profile.model or self.config.model or None
        return CodexAdapter(
            self.root,
            timeout=profile.timeout_seconds,
            model=model,
            executable=self.config.executable,
            profile=self.config.profile,
            reasoning_effort=(
                profile.reasoning_effort or self.config.reasoning_effort
            ),
            extra_args=self.config.extra_args,
        ).analyze(metadata, text_path)


class ClaudeProvider(CLIProvider):
    name = "claude"
    analyze_subcommand = []

    def analyze(self, metadata: Any, text_path: Path, profile: AIProfile) -> Any:
        model = profile.model or self.config.model or None
        return ClaudeAdapter(
            self.root,
            timeout=profile.timeout_seconds,
            model=model,
            executable=self.config.executable,
            extra_args=self.config.extra_args,
        ).analyze(metadata, text_path)


class MockProvider(AIProvider):
    name = "mock"

    def check_available(self) -> CapabilityReport:
        return CapabilityReport(
            provider=self.name,
            available=True,
            executable="in-process",
            version="deterministic-v1",
            analyze_help_available=True,
        )

    def analyze(self, metadata: Any, text_path: Path, profile: AIProfile) -> Any:
        return MockAdapter().analyze(metadata, text_path)


def make_provider(name: str, root: Path, config: ProviderConfig) -> AIProvider:
    providers = {
        "codex": CodexProvider,
        "claude": ClaudeProvider,
        "mock": MockProvider,
    }
    try:
        return providers[name](root, config)
    except KeyError as exc:
        raise ValueError(f"Unknown AI provider: {name}") from exc


def capability_summary(root: Path, configs: dict[str, ProviderConfig]) -> list[dict[str, Any]]:
    return [
        asdict(make_provider(name, root, config).check_available())
        for name, config in configs.items()
    ]


def explain_profile(
    profile_name: str,
    profiles: dict[str, AIProfile],
    providers: dict[str, ProviderConfig],
) -> dict[str, Any]:
    profile = profiles[profile_name]
    provider = providers[profile.provider]
    return {
        "profile": profile_name,
        "provider": profile.provider,
        "model": profile.model or provider.model or "<cli-default>",
        "timeout_seconds": profile.timeout_seconds,
        "reasoning_effort": profile.reasoning_effort or provider.reasoning_effort,
        "fallback_profile": profile.fallback_profile,
        "reuse_feed_analysis": profile.reuse_feed_analysis,
        "reanalyze_when": profile.reanalyze_when,
    }
