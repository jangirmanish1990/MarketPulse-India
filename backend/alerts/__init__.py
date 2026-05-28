"""Alert dispatch sub-package for MarketPulse India.

Exports the public surface used by the rest of the backend:
  - ``AlertPayload``  — Pydantic model carrying all signal data
  - ``dispatch_alert`` — single entry point that fans out to all channels
  - ``format_*``       — per-channel formatters (useful for previews / tests)
  - ``send_*``         — individual channel senders
  - ``SIGNAL_EMOJI``   — direction → emoji mapping
"""

from backend.alerts.dispatcher import (
    SIGNAL_EMOJI,
    AlertPayload,
    dispatch_alert,
    format_sms,
    format_telegram,
    format_whatsapp,
    send_sms,
    send_telegram,
    send_whatsapp,
)

__all__ = [
    "SIGNAL_EMOJI",
    "AlertPayload",
    "dispatch_alert",
    "format_sms",
    "format_telegram",
    "format_whatsapp",
    "send_sms",
    "send_telegram",
    "send_whatsapp",
]
