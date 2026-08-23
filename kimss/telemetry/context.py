"""
Resolve lightweight execution metadata in the *client* process for Usage Hub.

Host environment is cached (env vars change rarely). Source file path is computed
per call — do not cache it globally, or every request would share the first path.
"""
from __future__ import annotations

import base64
import functools
import inspect
import json
import os
import socket
from typing import Any, Dict, Optional


def _kimss_package_dir() -> str:
    try:
        import kimss  # noqa: WPS433 — runtime import for package root

        return os.path.normcase(os.path.abspath(os.path.dirname(kimss.__file__)))
    except Exception:
        return ""


@functools.lru_cache(maxsize=1)
def get_host_environment() -> str:
    """Azure App Service, AWS Lambda, Kubernetes, GCP, GitHub Actions, or local dev label."""
    site = (os.environ.get("WEBSITE_SITE_NAME") or "").strip()
    if site:
        return site[:512]
    fn = (os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or "").strip()
    if fn:
        region = (os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "").strip()
        return (f"AWS Lambda:{fn}" + (f" ({region})" if region else ""))[:512]
    k8s_ns = (os.environ.get("KUBERNETES_SERVICE_HOST") or "").strip()
    if k8s_ns:
        pod = (os.environ.get("HOSTNAME") or "").strip()
        return (f"Kubernetes:{pod}" if pod else "Kubernetes")[:512]
    gcp_svc = (os.environ.get("K_SERVICE") or "").strip()
    if gcp_svc:
        return f"GCP Cloud Run:{gcp_svc}"[:512]
    gh = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if gh:
        return f"GitHub:{gh}"[:512]
    if (os.environ.get("GITHUB_ACTION") or "").strip() or (os.environ.get("CI") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return "GitHub-CI"[:512]
    if (os.environ.get("DOCKER_CONTAINER") or os.environ.get("KIMSS_IN_DOCKER") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return "Docker"[:512]
    try:
        host = socket.gethostname()
        if host and host.lower() not in ("localhost",):
            return f"Host:{host}"[:512]
    except OSError:
        pass
    return "Local/Dev"


def get_sdk_source_location(*, max_frames: int = 25, max_len: int = 512) -> str:
    """First stack frame outside the installed ``kimss`` package; relative path when possible."""
    skip_root = _kimss_package_dir()
    frame = inspect.currentframe()
    depth = 0
    try:
        while frame is not None and depth < max_frames:
            depth += 1
            frame = frame.f_back
            if frame is None:
                break
            code = getattr(frame, "f_code", None)
            if code is None:
                continue
            path = str(getattr(code, "co_filename", "") or "")
            if not path or path.startswith("<"):
                continue
            ap = os.path.normcase(os.path.abspath(path))
            if skip_root and ap.startswith(skip_root):
                continue
            cwd = ""
            try:
                cwd = os.getcwd()
            except OSError:
                cwd = ""
            try:
                rel = os.path.relpath(path, cwd) if cwd and os.path.exists(cwd) else os.path.basename(path)
            except ValueError:
                rel = os.path.basename(path)
            rel = rel.replace("\\", "/")
            if len(rel) > max_len:
                rel = rel[-max_len:]
            return rel
    finally:
        del frame
    return "Unknown"


def build_sdk_execution_context(
    *,
    resource_type: str,
    resource_name: str,
    env: Optional[str] = None,
    region: Optional[str] = None,
    hostname: Optional[str] = None,
) -> Dict[str, str]:
    rt = (resource_type or "agent").strip().lower()
    if rt not in ("agent", "model"):
        rt = "agent"
    name = (resource_name or "").strip()[:512]
    out: Dict[str, str] = {
        "host_environment": get_host_environment(),
        "source_location": get_sdk_source_location(),
        "resource_type": rt,
        "resource_name": name,
    }
    hn = (hostname or "").strip()
    if not hn:
        try:
            hn = socket.gethostname()
        except OSError:
            hn = ""
    if hn:
        out["hostname"] = hn[:256]
    customer_env = (env or os.environ.get("KIMSS_CALLER_ENV") or os.environ.get("ENV") or "").strip()
    if customer_env:
        out["env"] = customer_env[:64]
    reg = (region or os.environ.get("KIMSS_CALLER_REGION") or os.environ.get("AWS_REGION") or "").strip()
    if reg:
        out["region"] = reg[:64]
    return out


def encode_sdk_context_header_value(
    *,
    resource_type: str,
    resource_name: str,
    env: Optional[str] = None,
    region: Optional[str] = None,
    hostname: Optional[str] = None,
) -> str:
    """Base64url JSON for ``X-Kimss-SDK-Context`` (ASCII, no padding)."""
    payload = build_sdk_execution_context(
        resource_type=resource_type,
        resource_name=resource_name,
        env=env,
        region=region,
        hostname=hostname,
    )
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_sdk_context_header_value(raw: str) -> Optional[Dict[str, Any]]:
    """Parse header from server-side validation tests (not used in SDK hot path)."""
    s = (raw or "").strip()
    if not s:
        return None
    pad = "=" * ((4 - len(s) % 4) % 4)
    try:
        data = base64.urlsafe_b64decode(s + pad)
        obj = json.loads(data.decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None
