from __future__ import annotations


class VoiceError(Exception):
    pass


class VoiceInitError(VoiceError):
    pass


class VoiceNotReadyError(VoiceError):
    pass


class VoiceSynthesisError(VoiceError):
    pass
