"""Helpers for OpenAI/Anthropic gateway clients (canonical integration path)."""
from __future__ import annotations

from typing import Dict, Optional

from .telemetry.context import encode_sdk_context_header_value


def gateway_headers(
    *,
    agent_id: str,
    agent_name: Optional[str] = None,
    resource_type: str = "agent",
    env: Optional[str] = None,
    region: Optional[str] = None,
    hostname: Optional[str] = None,
) -> Dict[str, str]:
    """
    Return ``extra_headers`` for official OpenAI/Anthropic SDK clients pointed at Kimss.

    Includes agent attribution plus optional ``X-Kimss-SDK-Context`` for named call sites.
    """
    aid = (agent_id or "").strip()
    if not aid:
        raise ValueError("agent_id is required")
    headers: Dict[str, str] = {"X-Kimss-Agent-Id": aid}
    name = (agent_name or "").strip()
    if name:
        headers["X-Kimss-Agent-Name"] = name
    try:
        headers["X-Kimss-SDK-Context"] = encode_sdk_context_header_value(
            resource_type=resource_type,
            resource_name=aid,
            env=env,
            region=region,
            hostname=hostname,
        )
    except Exception:
        pass
    return headers
