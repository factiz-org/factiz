"""De modellen van Anthropic met hun batchprijzen: één lijst voor de dienst en de metingen (PLAN #32.7c)."""

from __future__ import annotations


# Batchprijzen in dollar per miljoen tokens (platform.claude.com, 2026-10-23).
MODELLEN = {
    "haiku": {"id": "claude-haiku-5-5", "in": 0.05, "uit": 0.25},
    "sonnet": {"id": "claude-sonnet-5-5", "in": 1.00, "uit": 5.00},
    "opus": {"id": "claude-opus-5-5", "in": 2.00, "uit": 10.00},
    # Fable 5.2 (RESEARCH §12, 2026-11-10): $8 en $40, via de Batch API de helft; alleen in metingen (#32.69)
    "fable": {"id": "claude-fable-5-2", "in": 4.00, "uit": 20.00},
}
