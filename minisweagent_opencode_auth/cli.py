"""Convenience launcher for explicit provider/model/effort selections."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


MODEL_CLASS = "minisweagent_opencode_auth.OpenCodeSubscriptionsModel"
VALID_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "default"}
PROVIDERS = {
    "codex": ("codex", "MSWEA_CODEX_MODEL"),
    "openai": ("codex", "MSWEA_CODEX_MODEL"),
    "opencode-go": ("opencode-go", "MSWEA_OPENCODE_GO_MODEL"),
    "go": ("opencode-go", "MSWEA_OPENCODE_GO_MODEL"),
    "glm": ("glm", "MSWEA_GLM_MODEL"),
    "zai": ("glm", "MSWEA_GLM_MODEL"),
    "glm-coding-ai": ("glm", "MSWEA_GLM_MODEL"),
}


@dataclass(frozen=True)
class Selection:
    provider: str
    model: str
    effort: str | None


def parse_selector(selector: str) -> Selection:
    """Parse ``provider:model[@effort]`` and normalize provider aliases."""
    provider_name, separator, model_part = selector.partition(":")
    if not separator or not provider_name or not model_part:
        raise ValueError("selector must be provider:model[@effort], for example codex:gpt-5.6-luna@high")
    if provider_name not in PROVIDERS:
        choices = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown provider {provider_name!r}; choose one of: {choices}")

    model, effort_separator, effort = model_part.rpartition("@")
    if not effort_separator:
        model, effort = model_part, None
    if not model:
        raise ValueError("model name cannot be empty")
    if effort is not None:
        if not effort or effort not in VALID_EFFORTS:
            choices = ", ".join(sorted(VALID_EFFORTS))
            raise ValueError(f"unknown reasoning effort {effort!r}; choose one of: {choices}")

    provider, _ = PROVIDERS[provider_name]
    return Selection(provider=provider, model=model, effort=effort)


def build_environment(selection: Selection, base: dict[str, str] | None = None) -> dict[str, str]:
    """Build the environment consumed by the adapter and mini-SWE-agent."""
    environment = dict(os.environ if base is None else base)
    _, model_variable = PROVIDERS[selection.provider]
    environment["MSWEA_SUBSCRIPTION"] = selection.provider
    environment[model_variable] = selection.model
    environment["MSWEA_MODEL_NAME"] = "opencode-subscription"
    environment["MSWEA_MODEL_CLASS"] = MODEL_CLASS
    if selection.effort is None:
        environment.pop("MSWEA_REASONING_EFFORT", None)
    else:
        environment["MSWEA_REASONING_EFFORT"] = selection.effort
    return environment


def _reject_model_overrides(arguments: list[str]) -> None:
    forbidden = ("-m", "--model", "--model-class")
    for argument in arguments:
        if argument in forbidden or argument.startswith("--model=") or argument.startswith("--model-class="):
            raise ValueError("the selector already chooses the model; do not pass mini's --model or --model-class")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        print("Usage: mswea provider:model[@effort] [mini arguments ...]")
        print("Example: mswea codex:gpt-5.6-luna@high --yolo")
        print("Providers: codex, opencode-go, glm (aliases: openai, go, zai)")
        return 0 if arguments else 2

    try:
        selection = parse_selector(arguments[0])
        forwarded = arguments[1:]
        if forwarded[:1] == ["--"]:
            forwarded = forwarded[1:]
        _reject_model_overrides(forwarded)
    except ValueError as error:
        print(f"mswea: {error}", file=sys.stderr)
        return 2

    command = [
        "mini",
        "--model",
        "opencode-subscription",
        "--model-class",
        MODEL_CLASS,
        *forwarded,
    ]
    os.execvpe(command[0], command, build_environment(selection))
    return 0
