"""SpeechPlanner - turns an assistant reply into speech-sized, emotion-tagged
chunks (§11, §15). Sentence chunk N is synthesized while chunk N-1 plays.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import VoiceConfig
from .emotion import CharacterProfile, EmotionDirector, SpeechPerformance
from .preprocess import preprocess_text, segment_sentences
from .tts_backend import TTSError


@dataclass
class SpeechChunk:
    text: str  # visible clean text (UI-safe, no internal markers)
    emotion: str = "neutral"
    speed: float = 1.0
    pitch_cents: int = 0
    energy: float = 0.5
    priority: str = "normal"
    performance: SpeechPerformance = field(default_factory=SpeechPerformance)
    tts_text: str = ""  # TTS-bound text (may carry model-correct emotion cues)


class SpeechPlanner:
    def __init__(self, cfg: VoiceConfig):
        self.cfg = cfg
        self.director = EmotionDirector(CharacterProfile())

    def plan(self, text: str, override_emotion: Optional[str] = None,
             priority: str = "normal",
             speaking_rate: Optional[float] = None,
             cue_model: Optional[str] = None) -> list[SpeechChunk]:
        """Split + tag a reply into speech chunks. Raises TTSError if unusable.

        cue_model: Fish model id for S2.1 cue rendering (e.g. s2.1-pro-free).
        When None, tts_text == text (no cues — safe default).
        """
        from .cues import render_cues, sanitize_user_text
        cleaned = sanitize_user_text(preprocess_text(text))
        if not cleaned:
            raise TTSError("empty text after preprocessing")
        segs = (segment_sentences(cleaned) if self.cfg.sentence_segmentation
                else [cleaned])
        chunks: list[SpeechChunk] = []
        for i, seg in enumerate(segs):
            override = override_emotion if i == 0 else None
            perf = self.director.classify(
                seg, override=override, mode=self.cfg.emotion_mode,
                base_intensity=self.cfg.emotion_intensity,
                intensity=self.cfg.emotion_intensity)
            if speaking_rate:
                try:
                    perf.speed = max(0.7, min(1.6, perf.speed / float(speaking_rate)))
                except (TypeError, ValueError):
                    pass
            tts = render_cues(seg, perf.emotion, perf.intensity,
                              model=cue_model or "") if cue_model else seg
            chunks.append(SpeechChunk(
                text=seg,
                emotion=perf.emotion,
                speed=perf.speed,
                pitch_cents=perf.pitch_cents,
                energy=perf.energy,
                priority=priority,
                performance=perf,
                tts_text=tts or seg,
            ))
        return chunks