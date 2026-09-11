from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse


ZERO_SPEND_LOCAL = True
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
REMOTE_PROVIDERS = frozenset({"openai", "humain"})


class PolicyViolation(ValueError):
    """A centrally enforced policy failure; callers must surface it, never fallback."""


@dataclass(frozen=True)
class LocalityCheck:
    url: str
    allowed: bool
    checks: list[str]
    reason: str | None = None


def validate_loopback_url(url: str) -> LocalityCheck:
    parsed = urlparse(url)
    checks = ["absolute URL", "http scheme", "explicit loopback host", "no credentials"]
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        return LocalityCheck(url, False, checks, "LOCAL_ENDPOINT_MUST_BE_CREDENTIAL_FREE_HTTP_LOOPBACK")
    host = parsed.hostname.lower()
    if host not in LOOPBACK_HOSTS:
        try:
            if not ipaddress.ip_address(host).is_loopback:
                return LocalityCheck(url, False, checks, "LOCAL_ENDPOINT_NOT_LOOPBACK")
        except ValueError:
            return LocalityCheck(url, False, checks, "LOCAL_ENDPOINT_NOT_ON_EXPLICIT_ALLOWLIST")
    return LocalityCheck(url, True, checks + ["redirect following disabled", "proxy inheritance disabled"])


def assert_dispatch_allowed(provider: str, endpoint: str | None = None, *, artifact_verified: bool = False) -> None:
    """Policy lives below the UI and is called by every adapter dispatch path."""
    if provider in REMOTE_PROVIDERS:
        raise PolicyViolation(f"REMOTE_DISPATCH_BLOCKED: {provider} is disabled by ZERO_SPEND_LOCAL")
    if provider not in {"demo_rules", "ollama_local", "faster_whisper_local", "transformers_whisper_local", "llama_cpp_local"}:
        raise PolicyViolation(f"UNKNOWN_PROVIDER_BLOCKED: {provider}")
    if provider == "ollama_local":
        if not endpoint:
            raise PolicyViolation("LOCAL_ENDPOINT_OR_ARTIFACT_REQUIRED")
        check = validate_loopback_url(endpoint)
        if not check.allowed:
            raise PolicyViolation(check.reason or "LOCALITY_CHECK_FAILED")
    if provider == "faster_whisper_local" and not artifact_verified:
        raise PolicyViolation("UNVERIFIED_LOCAL_SPEECH_ARTIFACT")
    if provider in {"transformers_whisper_local", "llama_cpp_local"} and not artifact_verified:
        raise PolicyViolation("UNVERIFIED_LOCAL_MODEL_ARTIFACT")


def allowed_browser_host(host: str | None) -> bool:
    if not host:
        return False
    raw = host.strip().lower()
    if raw.startswith("["):
        normalized = raw.split("]", 1)[0].strip("[]")
    elif raw.count(":") == 1:
        normalized = raw.split(":", 1)[0]
    else:
        normalized = raw
    # testserver is only FastAPI TestClient's in-process host, not a bind target.
    return normalized in LOOPBACK_HOSTS or normalized == "testserver"


def allowed_origin(origin: str | None) -> bool:
    if not origin:
        return True
    try:
        return allowed_browser_host(urlparse(origin).netloc)
    except ValueError:
        return False
