"""Qwen Cloud client — this file is the Alibaba Cloud proof-of-deployment artifact.

The API is OpenAI-compatible, so we use the OpenAI SDK pointed at the
dashscope-intl endpoint (Alibaba Cloud / Qwen Cloud, Singapore region).
"""
import os
from openai import OpenAI

_CLIENT = None


def client() -> OpenAI:
    """Lazy singleton — the deterministic graph/spine can run without a key;
    only actual LLM calls require DASHSCOPE_API_KEY."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI(
            api_key=os.environ["DASHSCOPE_API_KEY"],
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
    return _CLIENT

# Distinct capabilities under a Qwen-only constraint come from model TIER:
# referee gets the larger model, advocates the cheap one (also caps token cost).
# Current DashScope tier (verify exact strings against the Model Studio model
# list — preview ids can shift). Stable fallback aliases: qwen-max / qwen-plus /
# qwen-flash. Distinct capabilities under a Qwen-only rule come from TIER:
REFEREE_MODEL = "qwen3.7-max"    # flagship reasoning — arbitrates negotiations
BASELINE_MODEL = "qwen3.6-plus"  # mid tier — the single-agent baseline
ADVOCATE_MODEL = "qwen3.6-flash" # cheap/fast tier — the 5 advocates (budget guard)


def chat(messages, model=ADVOCATE_MODEL, temperature=0.2, **kw):
    """Thin wrapper. Returns the assistant message content (str)."""
    resp = client().chat.completions.create(
        model=model, messages=messages, temperature=temperature, **kw
    )
    return resp.choices[0].message.content
