"""Anthropic client wrapper. Single-shot JSON output with one retry on parse failure."""

from __future__ import annotations

import json
import os
import re
from typing import Type, TypeVar

from anthropic import Anthropic
from pydantic import BaseModel, ValidationError

MODEL = "claude-sonnet-4-5"

T = TypeVar("T", bound=BaseModel)


def _client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return Anthropic(api_key=key)


def _extract_json(text: str) -> str:
    """Best-effort: pull the first JSON object from a response."""
    # Try fenced code block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Try raw {...}
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        return m.group(1)
    return text


def call_structured(
    system: str,
    user: str,
    schema: Type[T],
    max_tokens: int = 4096,
) -> T:
    """One call + one retry on validation failure (with error fed back in)."""
    client = _client()
    schema_json = json.dumps(schema.model_json_schema(), indent=2)

    full_system = (
        f"{system}\n\n"
        "Respond with a single JSON object matching this JSON Schema exactly. "
        "Do not include any prose outside the JSON.\n\n"
        f"SCHEMA:\n{schema_json}"
    )

    def _once(error_feedback: str = "") -> T:
        prompt = user if not error_feedback else (
            user
            + "\n\n---\nYour previous response failed validation with this error. "
            "Fix it and return only the corrected JSON object.\n"
            f"ERROR: {error_feedback}"
        )
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=full_system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        raw = _extract_json(text)
        try:
            return schema.model_validate_json(raw)
        except ValidationError as e:
            # bubble up so caller can decide whether to retry
            raise ValueError(str(e)) from e

    try:
        return _once()
    except ValueError as e:
        return _once(error_feedback=str(e))
