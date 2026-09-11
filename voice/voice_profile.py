"""
Voice-profile abstraction.

A voice profile is a directory under <project>/voices/<id>/ containing:
- reference.wav   (the speaker reference audio; required for voice cloning)
- reference.txt   (the transcript of reference.wav; required)
- metadata.json   ({id, name, description, reference_audio, reference_text, enabled})

Voice identity is fully independent from emotion and character personality.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from .config import VoiceConfig, PROJECT_ROOT


@dataclass
class VoiceProfile:
    id: str
    name: str
    description: str = ""
    reference_audio: str = "reference.wav"
    reference_text: str = ""
    enabled: bool = True
    base_dir: Optional[Path] = None

    # runtime cache (not serialized)
    _audio_bytes: Optional[bytes] = None

    @property
    def dir(self) -> Path:
        root = self.base_dir or (PROJECT_ROOT / "voices")
        return Path(root) / self.id

    def reference_path(self) -> Path:
        return self.dir / self.reference_audio

    def is_ready(self) -> bool:
        p = self.reference_path()
        return p.exists() and p.stat().st_size > 0 and bool(self.reference_text.strip())

    def load_audio(self) -> bytes:
        if self._audio_bytes is None:
            self._audio_bytes = self.reference_path().read_bytes()
        return self._audio_bytes

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_audio_bytes", None)
        d.pop("base_dir", None)
        d["ready"] = self.is_ready()
        return d


class VoiceProfileManager:
    def __init__(self, cfg: VoiceConfig):
        self.cfg = cfg
        self.profiles: dict[str, VoiceProfile] = {}
        # Compat: old field voice_active renamed to voice
        self.active: str = getattr(cfg, "voice_active", None) or getattr(cfg, "voice", "am_michael")
        self._scan()

    # -- discovery ------------------------------------------------------
    def _scan(self):
        self.profiles.clear()
        voices_dir = self.cfg.voices_dir
        if not voices_dir.exists():
            voices_dir.mkdir(parents=True, exist_ok=True)
            # Fish Audio is now the sole provider — no local reference.wav needed.
            # Only create a placeholder if explicitly using a local engine.
            if getattr(self.cfg, "engine", "fish") not in ("fish",):
                self._create_default_profile(voices_dir)
        for d in sorted(voices_dir.iterdir()):
            if d.is_dir():
                meta = d / "metadata.json"
                if meta.exists():
                    try:
                        data = json.loads(meta.read_text(encoding="utf-8"))
                        prof = VoiceProfile(
                            id=data.get("id", d.name),
                            name=data.get("name", d.name),
                            description=data.get("description", ""),
                            reference_audio=data.get("reference_audio", "reference.wav"),
                            reference_text=data.get("reference_text", ""),
                            enabled=bool(data.get("enabled", True)),
                        )
                        prof.base_dir = self.cfg.voices_dir
                        self.profiles[prof.id] = prof
                    except Exception:
                        continue
        # Fish Audio: no local profiles required — keep empty, don't auto-create.
        if getattr(self.cfg, "engine", "fish") == "fish":
            if self.active not in self.profiles:
                self.active = self.active or "fish"
            return
        if not self.profiles:
            self._create_default_profile(voices_dir)
        if self.active not in self.profiles:
            self.active = next(iter(self.profiles))

    def _create_default_profile(self, voices_dir: Path):
        d = voices_dir / "jarvis"
        d.mkdir(parents=True, exist_ok=True)
        meta = {
            "id": "jarvis",
            "name": "JARVIS",
            "description": "Default J.A.R.V.I.S. reference voice. Drop reference.wav "
                           "(~6-10s clean speech) and reference.txt (its transcript) here.",
            "reference_audio": "reference.wav",
            "reference_text": "",
            "enabled": True,
        }
        (d / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        # Placeholder README so the user knows what to add.
        (d / "README.txt").write_text(
            "To use a custom voice, add:\n"
            "  reference.wav  - 6-10 seconds of clean speech from the desired speaker\n"
            "  reference.txt  - the exact transcript of reference.wav\n"
            "The local TTS engine (kokoro/orpheus) can use reference clips where supported.\n"
            "No cloud/API key is required. See docs/voice-system.md.\n",
            encoding="utf-8",
        )
        prof = VoiceProfile(**meta)
        prof.base_dir = self.cfg.voices_dir
        self.profiles["jarvis"] = prof

    # -- API ------------------------------------------------------------
    def list(self) -> list[dict]:
        return [p.to_dict() for p in self.profiles.values()]

    def get(self, vid: Optional[str] = None) -> Optional[VoiceProfile]:
        vid = vid or self.active
        return self.profiles.get(vid)

    def active_profile(self) -> Optional[VoiceProfile]:
        return self.profiles.get(self.active)

    def set_active(self, vid: str) -> bool:
        if vid not in self.profiles:
            return False
        if not self.profiles[vid].enabled:
            return False
        self.active = vid
        # Compat for both old and new config field names
        if hasattr(self.cfg, "voice_active"):
            self.cfg.voice_active = vid
        if hasattr(self.cfg, "voice"):
            self.cfg.voice = vid
        self.cfg.save_state()
        return True

    def add(self, profile: VoiceProfile, reference_wav: Optional[bytes] = None,
            reference_text: Optional[str] = None) -> bool:
        d = profile.dir
        d.mkdir(parents=True, exist_ok=True)
        if reference_wav is not None:
            (d / profile.reference_audio).write_bytes(reference_wav)
        if reference_text is not None:
            profile.reference_text = reference_text
        (d / "metadata.json").write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        self.profiles[profile.id] = profile
        return True

    def remove(self, vid: str) -> bool:
        prof = self.profiles.get(vid)
        if not prof:
            return False
        shutil.rmtree(prof.dir, ignore_errors=True)
        self.profiles.pop(vid, None)
        if self.active == vid and self.profiles:
            self.active = next(iter(self.profiles))
        return True
