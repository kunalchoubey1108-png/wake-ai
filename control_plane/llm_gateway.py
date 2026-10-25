"""
LLM gateway interface.

BUILD-WEEK STUB (lablab rule): core AI functionality must be implemented during
3–8 Nov 2026. This module exposes an interface only — no prompts, no inference
calls, no API wiring. Callers use deterministic fallbacks in agent/*.py.
"""
from __future__ import annotations

from typing import Any, Protocol


class LLMGateway(Protocol):
    """Interface for Vultr Serverless Inference (or compatible) during build week."""

    def complete(self, *, system: str, user: str, **kwargs: Any) -> str:
        """Return model text. Not implemented until build week."""
        ...


class StubLLMGateway:
    """
    Deterministic stub. Raises if someone tries to call inference early.
    TODO(build-week): implement Vultr Serverless Inference client:
      - auth via VULTR_INFERENCE_API_KEY
      - base URL / model from settings
      - no secrets into sandbox
    Do NOT add prompts or live calls before kickoff.
    """

    def complete(self, *, system: str, user: str, **kwargs: Any) -> str:
        raise NotImplementedError(
            "LLM gateway is stubbed until hackathon build week (3–8 Nov 2026). "
            "Use agent deterministic fallbacks (planner/triage/narrator)."
        )


def get_llm_gateway() -> StubLLMGateway:
    return StubLLMGateway()
