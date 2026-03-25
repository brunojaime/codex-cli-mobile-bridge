from __future__ import annotations

from backend.app.infrastructure.speech.base import (
    SpeechSynthesizer,
    SpeechSynthesizerStatus,
    SpeechSynthesisUnavailableError,
    SynthesizedSpeech,
)


class DisabledSpeechSynthesizer(SpeechSynthesizer):
    def status(self) -> SpeechSynthesizerStatus:
        return SpeechSynthesizerStatus(
            backend="disabled",
            ready=False,
            detail="Speech synthesis is disabled.",
        )

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        response_format: str | None = None,
        instructions: str | None = None,
    ) -> SynthesizedSpeech:
        raise SpeechSynthesisUnavailableError(
            "Speech synthesis is not configured for this server."
        )
