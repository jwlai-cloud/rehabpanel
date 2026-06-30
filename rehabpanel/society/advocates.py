"""The five advocate agents. Each runs on the cheap Qwen tier and argues from
ONE objective — that single-lens focus is what makes them distinct capabilities
rather than five copies of the same generalist.

Each advocate exposes:
  - critique(draft) -> list of objections [{patient_id, slot_id, severity, reason}]
  - propose_swap(objection, state) -> {move, marginal_value, reason}

TODO(claude-code): flesh out the LLM calls using prompts/<name>.md as the
system prompt. Keep messages SHORT to protect the token budget.
"""
from pathlib import Path
from ..qwen_client import chat, ADVOCATE_MODEL

PROMPTS = Path(__file__).resolve().parent / "prompts"
ADVOCATES = ["priority", "window", "continuity", "capacity", "preference"]


def _system(name):
    return (PROMPTS / f"{name}.md").read_text()


class Advocate:
    def __init__(self, name):
        self.name = name
        self.system = _system(name)

    def critique(self, draft, context):
        """Return objections with 1-10 severity. TODO: parse JSON from LLM."""
        # msg = [{"role":"system","content":self.system},
        #        {"role":"user","content": render_draft(draft, context)}]
        # return parse(chat(msg, model=ADVOCATE_MODEL))
        raise NotImplementedError

    def propose_swap(self, objection, state):
        """Return a swap + the marginal value the advocate places on the trade."""
        raise NotImplementedError


def build_all():
    return {n: Advocate(n) for n in ADVOCATES}
