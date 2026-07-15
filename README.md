# Bring opencode auth to mini-SWE-agent

Use the subscriptions already configured in [opencode](https://opencode.ai/)
from [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent), without
copying API keys into another dotenv file.

Switch between Codex, OpenCode Go, and Z.AI Coding Plan with one environment
variable:

```sh
MSWEA_SUBSCRIPTION=codex mini
MSWEA_SUBSCRIPTION=opencode-go mini
MSWEA_SUBSCRIPTION=glm mini
```

## Why this exists

opencode already knows how to authenticate several coding subscriptions, but
mini-SWE-agent normally expects a provider API key such as `OPENAI_API_KEY`.
This adapter bridges the two tools:

```text
opencode auth.json -> adapter -> LiteLLM -> mini-SWE-agent
```

The adapter reads credentials at runtime. It does not copy tokens into mini's
configuration or trajectory files. Codex OAuth access tokens are refreshed
automatically when necessary.

## Supported subscriptions

| `MSWEA_SUBSCRIPTION` | opencode provider | Default model | Endpoint |
| --- | --- | --- | --- |
| `codex` | `openai` OAuth | `gpt-5.4` | ChatGPT Codex Responses API |
| `opencode-go` | `opencode-go` API | `glm-5.2` | OpenCode Go |
| `glm` | `zai-coding-plan` API | `glm-5.2` | Z.AI Coding Plan |

Aliases are available: `openai` means `codex`, `go` means `opencode-go`, and
`zai` / `glm-coding-ai` mean `glm`.

## Installation

Install mini-SWE-agent and this adapter into the same Python environment:

```sh
pipx install mini-swe-agent
pipx inject mini-swe-agent \
  git+https://github.com/renanliberato/mini-swe-agent-opencode-auth.git
```

Or install from a checkout:

```sh
git clone https://github.com/renanliberato/mini-swe-agent-opencode-auth.git
cd mini-swe-agent-opencode-auth
pip install -e .
```

Authenticate providers in opencode first:

```sh
opencode auth login
opencode auth list
```

Then pass the adapter as mini's model class:

```sh
mini \
  --model opencode-subscription \
  --model-class minisweagent_opencode_auth.OpenCodeSubscriptionsModel
```

For convenience, configure mini's global environment file with:

```dotenv
MSWEA_MODEL_NAME=opencode-subscription
MSWEA_MODEL_CLASS=minisweagent_opencode_auth.OpenCodeSubscriptionsModel
MSWEA_SUBSCRIPTION=codex
MSWEA_COST_TRACKING=ignore_errors
```

The stock mini launcher may require `--model-class`; newer/local launchers
that forward `MSWEA_MODEL_CLASS` can use the dotenv setting directly.

## Choosing models

```sh
MSWEA_CODEX_MODEL=gpt-5.4 \
  MSWEA_SUBSCRIPTION=codex mini --model opencode-subscription

MSWEA_OPENCODE_GO_MODEL=glm-5.2 \
  MSWEA_SUBSCRIPTION=opencode-go mini --model opencode-subscription

MSWEA_GLM_MODEL=glm-5.2 \
  MSWEA_SUBSCRIPTION=glm mini --model opencode-subscription
```

## Setting reasoning effort

Pass LiteLLM's `reasoning_effort` through mini's model configuration. The
available values depend on the model; for example, Codex models commonly
support `low`, `medium`, and `high`:

```sh
MSWEA_SUBSCRIPTION=codex \
  mini --model gpt-5.6-luna \
  -c mini.yaml \
  -c model.model_kwargs.reasoning_effort=high
```

Other examples:

```sh
mini --model gpt-5.6-luna -c mini.yaml -c model.model_kwargs.reasoning_effort=low
mini --model gpt-5.6-luna -c mini.yaml -c model.model_kwargs.reasoning_effort=medium
```

Use `reasoning_effort`, not opencode's catalog spelling `reasoningEffort`.
The explicit `-c mini.yaml` is intentional: when using `-c`, mini requires
the default config to be included before the override.

## Security notes

- Keep `~/.local/share/opencode/auth.json` private.
- Never commit `auth.json`, `.env` files containing tokens, or trajectories
  containing prompts and outputs.
- Credentials are passed in memory to LiteLLM and intentionally omitted from
  the adapter's serialized model configuration.
- The Codex refresh path updates opencode's existing credential store using an
  atomic replacement and preserves its file permissions.

## Limitations

- This targets mini-SWE-agent 2.4.5's model interface and LiteLLM integration.
- Reinstalling or upgrading mini-SWE-agent can require reinstalling this
  adapter into the new environment.
- Provider model availability and subscription limits are controlled by
  opencode and the upstream provider.
- Codex uses the Responses API and requires streaming; the adapter reconstructs
  streamed function-call output for mini-SWE-agent.

## Development

```sh
python -m compileall minisweagent_opencode_auth
```

Contributions and provider compatibility reports are welcome.

## License

MIT
