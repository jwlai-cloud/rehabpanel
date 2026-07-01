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


def is_offline() -> bool:
    """True => run the deterministic reference negotiator instead of calling
    Qwen. Lets CI, tests, and judges reproduce the benchmark gap key-free
    (without burning the $40 voucher); the live demo runs with the key for real
    agents. Force either way with REHABPANEL_OFFLINE=1 / =0."""
    flag = os.environ.get("REHABPANEL_OFFLINE")
    if flag is not None:
        return flag == "1"
    return not os.environ.get("DASHSCOPE_API_KEY")

# Distinct capabilities under a Qwen-only constraint come from model TIER:
# referee gets the larger model, advocates the cheap one (also caps token cost).
# Current DashScope tier (verify exact strings against the Model Studio model
# list — preview ids can shift). Stable fallback aliases: qwen-max / qwen-plus /
# qwen-flash. Distinct capabilities under a Qwen-only rule come from TIER:
REFEREE_MODEL = "qwen3.7-max"    # flagship reasoning — arbitrates negotiations
BASELINE_MODEL = "qwen3.6-plus"  # mid tier — the single-agent baseline
ADVOCATE_MODEL = "qwen3.6-flash" # cheap/fast tier — the 5 advocates (budget guard)


def chat(messages, model=ADVOCATE_MODEL, temperature=0.2, **kw):
    """Thin wrapper. Returns the assistant message content (str).

    Qwen3 models are reasoning models — their default 'thinking' output is large
    and slow. The advocates only need short structured JSON, so we disable it
    (enable_thinking=False) — ~10x fewer output tokens + faster, which matters for
    both latency and the $40 voucher. Callers can override via extra_body."""
    extra = {"enable_thinking": False}
    extra.update(kw.pop("extra_body", None) or {})   # tolerate an explicit extra_body=None
    resp = client().chat.completions.create(
        model=model, messages=messages, temperature=temperature, extra_body=extra, **kw
    )
    return resp.choices[0].message.content
