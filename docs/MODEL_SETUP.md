# Model setup in simple language

## What changed

The analysis code now talks through `stocktrading\llm_provider.py`. You can choose **Gemini**,
**NVIDIA's hosted API**, or an **OpenAI-compatible local/remote server** without
rewriting indicators, prompts, rules or the dashboard.

The existing default remains Gemini. No actual inference request is made just
by opening the dashboard. Batch analysis, single-stock analysis and News Picks
all use the chosen provider. Source evidence, requested model, generation settings,
model proposal and rule overrides are recorded for batch/single analysis.
There is no automatic switch to another provider when one fails.

## NVIDIA hosted API: the easiest route if your account supports the model

1. On your personal laptop, open https://build.nvidia.com/ and sign in.
2. Open the model you want, review its terms and generate an API key using the
   site's current instructions. Copy the exact **model ID** from its API example.
3. Edit your local `.env` in the project folder. Do not paste the key in Python.
4. Set these values, replacing the two placeholders:

```dotenv
LLM_PROVIDER=nvidia
NVIDIA_API_KEY=YOUR_OWN_KEY
LLM_MODEL=EXACT_MODEL_ID_FROM_YOUR_ACCOUNT
LLM_BASE_URL=
LLM_TIMEOUT_SECONDS=90
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0
LLM_JSON_MODE=false
```

5. Stop and restart Streamlit:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m streamlit run dashboard.py
```

6. Open **System Info -> Model setup**. Confirm the provider/model shown.
   Press **List models available to this endpoint** to check the configured ID.
   This lists models; it does not send stock analysis or prove inference permissions.
7. Run a single-stock analysis first. Missing keys, unavailable models, timeouts
   and invalid/incomplete responses are shown as errors/unavailable analysis,
   not successful predictions.

### Important finding about the model we originally discussed

The model was **NVIDIA Nemotron Nano 9B v2**. Its planned hosted request ID is
`nvidia/nvidia-nemotron-nano-9b-v2`; its weights ID is
`nvidia/NVIDIA-Nemotron-Nano-9B-v2`. These are different identifiers.

NVIDIA's official model page still documents it. However, it was **absent** from
the public hosted `/v1/models` listing retrieved on 2026-10-25. The adapter retains
that planned ID as the NVIDIA default for compatibility, but do not assume that
leaving `LLM_MODEL` empty will work on the hosted service.

Choose an ID actually offered to your account, or run the original weights on
a compatible server. Public listing examples observed included
`nvidia/nemotron-nano-3-30b-a3b` and `nvidia/nemotron-3.5-lightning-30b-a3b`;
listing is not a benchmark, entitlement or guarantee of future availability.
No authenticated NVIDIA inference was performed in this implementation session.

The model page says commercial use is permitted under the **NVIDIA Open Model
License Agreement**. Hosted trial service has separate trial terms. This is not
a promise of a permanently free API, and open weights are not automatically an
OSI-open-source license. Check current terms before company/commercial use.

## Run the planned 9B model locally

This option needs a separately running inference server. **The app does not
download model weights or install CUDA/vLLM/NIM.** A compatible GPU, adequate
RAM/VRAM, drivers and a supported runtime are your responsibility. An ordinary
company laptop is not assumed to be suitable.

NVIDIA documents Linux GPU deployments and Transformers, TensorRT-LLM and vLLM.
Its reference vLLM launch uses the weights ID above, `--trust-remote-code` and
`--mamba_ssm_cache_dtype float32`. Review the model code and use a runtime/version
that supports its hybrid Mamba architecture; do not assume every model runner
or quantization format supports it. Follow the current official model guide.
NIM/container licensing may differ from access to the weights.

Once your personal machine's server exposes OpenAI-compatible
`/v1/chat/completions`, configure the **app**:

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_MODEL=nvidia/NVIDIA-Nemotron-Nano-9B-v2
LLM_API_KEY=
```

Use the model ID actually advertised by your server; it may be a configured
alias instead of the weights ID. If it requires authentication, set `LLM_API_KEY`.
For a remote server, use HTTPS. Plain HTTP is allowed only for loopback.
No NVIDIA API key is required merely to call an unauthenticated local server.
GPU memory depends on precision, runtime and context; there is no verified
hardware-fit claim for your laptop. Local inference still has hardware/energy costs.

## Switch models later

| What you want to change | What you edit in `.env` |
| --- | --- |
| Another model at the same endpoint | `LLM_MODEL` |
| NVIDIA cloud to local server | `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL`, `LLM_MODEL`, optionally `LLM_API_KEY` |
| Back to Gemini | `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-2.5-flash`, `GEMINI_API_KEY` |
| Longer response allowance | `LLM_MAX_TOKENS` (128-32768); larger limits may cost more |
| Slow server timeout | `LLM_TIMEOUT_SECONDS` (1-600) |
| Sampling behaviour | `LLM_TEMPERATURE` (0-2); default 0 does not guarantee reproducibility |
| Server supports JSON-object mode | `LLM_JSON_MODE=true`; leave false if it rejects `response_format` |

Restart the app after editing. Clear `LLM_MODEL` when changing providers if you
want that provider's default; otherwise an old provider-specific model ID stays.
The app sends `/no_think` for Nano 9B v2, as its official documentation describes,
to request a final answer rather than a reasoning trace. Other models use their
provider defaults; reasoning-only or truncated output is rejected.
Existing environment variables take precedence over `.env` values.

For a fundamentally different API protocol, implement an additional adapter in
`stocktrading\llm_provider.py`; changing a URL cannot make incompatible protocols equivalent.

## Exactly what is sent

The chosen endpoint receives technical evidence, manually imported financial and
institutional context, available news, strategy instructions and source references.
Only use information you are authorized to send. API keys are not included in
prompts or audit metadata. The register identifies supplied evidence and optional
model-reported citations; it does not claim to reveal internal model reasoning.
Data/model failures produce WAIT/unavailable analysis and never trigger orders.

## Official references checked

- https://docs.api.nvidia.com/nim/reference/llm-apis
- https://docs.api.nvidia.com/nim/reference/nvidia-nvidia-nemotron-nano-9b-v2
- https://integrate.api.nvidia.com/v1/models
- https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/

The model-specific generated API schema page contained unrelated model metadata;
it was not used as evidence for the 9B model's license or exact hosted availability.
Model selection should ultimately compare evidence faithfulness, JSON reliability,
abstention, latency and cost on the same held-out cases, not marketing benchmarks.
