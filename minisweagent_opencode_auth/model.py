"""Use subscriptions already authenticated by opencode.

Select one with MSWEA_SUBSCRIPTION=codex|opencode-go|glm. Credentials are
read at runtime from opencode's auth.json and are never copied into mini's
configuration or trajectory files.
"""

import base64
import fcntl
import json
import os
import tempfile
import time
import urllib.parse
import urllib.request
import warnings
from pathlib import Path
from typing import Any

from minisweagent.models.litellm_model import LitellmModel
from minisweagent.models.litellm_response_model import LitellmResponseModel


AUTH_PATH = Path(os.path.expanduser(os.getenv("OPENCODE_AUTH_PATH", "~/.local/share/opencode/auth.json")))
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


def _read_auth() -> dict[str, Any]:
    try:
        return json.loads(AUTH_PATH.read_text())
    except FileNotFoundError as exc:
        raise RuntimeError(f"opencode credentials not found at {AUTH_PATH}; run `opencode auth login`") from exc


def _jwt_account_id(token: str) -> str | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return (
            claims.get("chatgpt_account_id")
            or claims.get("https://api.openai.com/auth", {}).get("chatgpt_account_id")
            or next((x.get("id") for x in claims.get("organizations", []) if x.get("id")), None)
        )
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def _refresh_codex_if_needed() -> dict[str, Any]:
    auth = _read_auth().get("openai")
    if not auth or auth.get("type") != "oauth":
        raise RuntimeError("OpenAI OAuth is not configured in opencode; run `opencode auth login`")
    if auth.get("access") and int(auth.get("expires", 0)) > int(time.time() * 1000) + 60_000:
        return auth

    lock_path = AUTH_PATH.with_suffix(".mini-swe-agent.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        all_auth = _read_auth()
        auth = all_auth.get("openai", {})
        if auth.get("access") and int(auth.get("expires", 0)) > int(time.time() * 1000) + 60_000:
            return auth

        body = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": auth.get("refresh", ""),
                "client_id": CODEX_CLIENT_ID,
            }
        ).encode()
        request = urllib.request.Request(
            "https://auth.openai.com/oauth/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            tokens = json.load(response)

        updated = {
            "type": "oauth",
            "refresh": tokens.get("refresh_token", auth.get("refresh")),
            "access": tokens["access_token"],
            "expires": int(time.time() * 1000) + int(tokens.get("expires_in", 3600)) * 1000,
        }
        account_id = (
            _jwt_account_id(tokens.get("id_token", ""))
            or _jwt_account_id(tokens["access_token"])
            or auth.get("accountId")
        )
        if account_id:
            updated["accountId"] = account_id
        all_auth["openai"] = updated

        mode = AUTH_PATH.stat().st_mode & 0o777
        fd, temporary = tempfile.mkstemp(prefix="auth.", suffix=".json", dir=AUTH_PATH.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(all_auth, stream, indent=2)
                stream.write("\n")
            os.chmod(temporary, mode)
            os.replace(temporary, AUTH_PATH)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return updated


class _CodexResponsesModel(LitellmResponseModel):
    """Adapt the Codex subscription endpoint, which requires streaming."""

    def _query(self, messages: list[dict[str, str]], **kwargs):
        import litellm

        stream = litellm.responses(
            model=self.config.model_name,
            input=messages,
            tools=[
                {
                    "type": "function",
                    "name": "bash",
                    "description": "Execute a bash command in the current working directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                    "strict": False,
                }
            ],
            **(self.config.model_kwargs | {"store": False, "stream": True} | kwargs),
        )
        output_items = {}
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Pydantic serializer warnings:.*")
            for event in stream:
                item = getattr(event, "item", None)
                output_index = getattr(event, "output_index", None)
                if item is not None and output_index is not None:
                    output_items[output_index] = item
        if stream.completed_response is None:
            raise RuntimeError("Codex stream ended without a completed response")
        response = getattr(stream.completed_response, "response", stream.completed_response)
        # LiteLLM currently leaves response.output empty for the Codex SSE
        # endpoint, even though output_item.done events contain complete items.
        items = getattr(response, "output", None) or [output_items[index] for index in sorted(output_items)]
        return _CodexResponse(response, items)


class _CodexResponse:
    """Minimal response object avoiding LiteLLM's noisy SSE serialization warnings."""

    def __init__(self, response, output_items):
        self.id = getattr(response, "id", None)
        self.status = getattr(response, "status", "completed")
        self.incomplete_details = getattr(response, "incomplete_details", None)
        self.output = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in output_items]

    def model_dump(self, mode=None):
        return {"id": self.id, "object": "response", "status": self.status, "output": self.output}


class OpenCodeSubscriptionsModel:
    """Delegate to the correct mini model while reusing opencode credentials."""

    ALIASES = {
        "codex": "codex",
        "openai": "codex",
        "opencode-go": "opencode-go",
        "go": "opencode-go",
        "glm": "glm",
        "glm-coding-ai": "glm",
        "zai": "glm",
        "z.ai": "glm",
    }

    def __init__(self, model_name: str = "opencode-subscription", model_kwargs: dict | None = None, **kwargs):
        requested = os.getenv("MSWEA_SUBSCRIPTION", "codex").strip().lower()
        try:
            self.subscription = self.ALIASES[requested]
        except KeyError as exc:
            choices = ", ".join(sorted(self.ALIASES))
            raise ValueError(f"Unknown MSWEA_SUBSCRIPTION={requested!r}; choose one of: {choices}") from exc

        common = dict(kwargs)
        common["cost_tracking"] = "ignore_errors"
        supplied = dict(model_kwargs or {})
        supplied.pop("api_key", None)
        supplied.pop("api_base", None)
        if "reasoning_effort" not in supplied:
            effort = os.getenv("MSWEA_REASONING_EFFORT")
            if effort:
                supplied["reasoning_effort"] = effort

        if self.subscription == "codex":
            auth = _refresh_codex_if_needed()
            selected = os.getenv("MSWEA_CODEX_MODEL", "gpt-5.4")
            if model_name != "opencode-subscription":
                selected = model_name.removeprefix("openai/")
            headers = {"originator": "opencode", "User-Agent": "opencode/mini-swe-agent"}
            if auth.get("accountId"):
                headers["ChatGPT-Account-Id"] = auth["accountId"]
            common["model_name"] = f"openai/{selected}"
            common["model_kwargs"] = supplied | {
                "api_base": "https://chatgpt.com/backend-api/codex",
                "api_key": auth["access"],
                "extra_headers": headers,
            }
            self._model = _CodexResponsesModel(**common)
        else:
            provider = "opencode-go" if self.subscription == "opencode-go" else "zai-coding-plan"
            auth = _read_auth().get(provider)
            if not auth or auth.get("type") != "api":
                raise RuntimeError(f"{provider} is not authenticated in opencode; run `opencode auth login`")
            variable = "MSWEA_OPENCODE_GO_MODEL" if provider == "opencode-go" else "MSWEA_GLM_MODEL"
            selected = os.getenv(variable, "glm-5.2")
            if model_name != "opencode-subscription":
                selected = model_name.split("/", 1)[-1]
            base = "https://opencode.ai/zen/go/v1" if provider == "opencode-go" else "https://api.z.ai/api/coding/paas/v4"
            common["model_name"] = f"openai/{selected}"
            common["model_kwargs"] = supplied | {"api_base": base, "api_key": auth["key"]}
            self._model = LitellmModel(**common)

        self.model_name = self._model.config.model_name

    def query(self, *args, **kwargs):
        return self._model.query(*args, **kwargs)

    def format_message(self, *args, **kwargs):
        return self._model.format_message(*args, **kwargs)

    def format_observation_messages(self, *args, **kwargs):
        return self._model.format_observation_messages(*args, **kwargs)

    def get_template_vars(self, **kwargs):
        values = self._model.get_template_vars(**kwargs)
        values["model_kwargs"] = {"credentials": "opencode auth.json"}
        return values

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "model": {
                        "model_name": self.model_name,
                        "subscription": self.subscription,
                        "credentials": "opencode auth.json (not serialized)",
                    },
                    "model_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }
