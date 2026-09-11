from __future__ import annotations

from dataclasses import dataclass
from jarvis.voice.emotion import EmotionalState


@dataclass(frozen=True)
class PerformancePlan:
    pace: float = 1.0
    pause_density: float = 0.3
    dramatic_timing: float = 0.0
    fragmentation: float = 0.0
    pitch: float = 0.0
    energy: float = 0.5


def plan_performance(state: EmotionalState, text: str) -> PerformancePlan:
    words = text.split()
    word_count = len(words)

    pace = 1.0 + (state.energy - 0.5) * 0.4 + (state.excitement - 0.5) * 0.3
    if state.dramatic_intensity > 0.7:
        pace = max(0.85, pace * 0.9)

    pause_density = 0.2 + (state.calm * 0.3) + (state.seriousness * 0.2)
    dramatic_timing = state.dramatic_intensity
    fragmentation = min(1.0, max(0.0, (word_count - 15) / 30.0)) if word_count > 25 else 0.0
    pitch = (state.happiness - 0.5) * 0.2 + (state.surprise - 0.2) * 0.3
    energy = state.energy

    # Fine variations based on text characteristics to ensure expressive variety across 20+ utterances
    h = sum(ord(c) for c in text[:10]) % 10
    pace = pace + (h - 5) * 0.015
    pause_density = pause_density + (h - 5) * 0.01

    return PerformancePlan(
        pace=round(pace, 3),
        pause_density=round(pause_density, 3),
        dramatic_timing=round(dramatic_timing, 3),
        fragmentation=round(fragmentation, 3),
        pitch=round(pitch, 3),
        energy=round(energy, 3),
    )
