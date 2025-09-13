# core/notifier_router.py
"""
Notifier router: choose SES (default) or SMTP based on NOTIFIER_BACKEND env var.
Usage:
    from core.notifier_router import send_email_alert
    send_email_alert("Subject", "Body")
Env:
    NOTIFIER_BACKEND = "ses" | "smtp"   (default: "ses")
"""

import os
from core.logger import get_company_logger

_logger = get_company_logger("notifier_router")

# Cache chosen backend module
_backend_mod = None
_backend_name = None

def _load_backend(preferred: str | None = None):
    global _backend_mod, _backend_name
    if _backend_mod:
        return _backend_mod, _backend_name

    preferred = (preferred or os.environ.get("NOTIFIER_BACKEND", "ses")).strip().lower()

    # Try preferred first
    tried = []
    def _try(name: str):
        tried.append(name)
        try:
            if name == "ses":
                from core import notifier_ses as mod
            elif name == "smtp":
                # your existing Gmail SMTP notifier file (original notifier.py)
                from core import notifier as mod
            else:
                return None
            return mod
        except Exception as e:
            _logger.warning(f"Notifier backend '{name}' unavailable: {e}")
            return None

    mod = _try(preferred)
    if mod is None:
        # Fallback order: SES -> SMTP
        for candidate in ( "ses", "smtp" ):
            if candidate == preferred:  # already tried
                continue
            mod = _try(candidate)
            if mod:
                preferred = candidate
                break

    if mod is None:
        # Final safety: no-op backend to avoid crashes
        class _Noop:
            @staticmethod
            def send_email_alert(subject: str, body: str):
                _logger.error("❌ No notifier backend available; email not sent.")
        _backend_mod, _backend_name = _Noop(), "noop"
    else:
        _backend_mod, _backend_name = mod, preferred
        _logger.info(f"📬 Using notifier backend: '{_backend_name}'")

    return _backend_mod, _backend_name


def get_backend_name() -> str:
    """Return the resolved backend name: 'ses', 'smtp', or 'noop'."""
    _, name = _load_backend(None)
    return name


def send_email_alert(subject: str, body: str, *, backend: str | None = None):
    """
    Route the send to the selected backend.
    Pass backend='ses' or 'smtp' to override per-call (rarely needed).
    """
    mod, _ = _load_backend(backend)
    return mod.send_email_alert(subject, body)
