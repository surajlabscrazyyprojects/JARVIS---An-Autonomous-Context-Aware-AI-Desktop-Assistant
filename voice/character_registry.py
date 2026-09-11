"""
Authoritative Fish Audio character voice registry.

One registry, one source of truth. Character -> reference_id.
Uses verified voice IDs provided by project owner. No credentials here.
"""
from __future__ import annotations

import os
from typing import Dict, Optional

# Verified voice IDs (Fish S2.1 Pro Free)
_DEFAULT_REGISTRY: Dict[str, Dict[str, str]] = {
    "iron_man": {
        "reference_id": "14129c3e320149449d6bada6862f7338",
        "display_name": "JARVIS",
        "model": "s2.1-pro-free",
    },
    "spider_man": {
        "reference_id": "c6bfe5606e0d497586703898c87a6ac1",
        "display_name": "Spider-Man",
        "model": "s2.1-pro-free",
    },
    "thor": {
        "reference_id": "dac3dd7d6fb24f8f94dee720520e3594",
        "display_name": "Thor",
        "model": "s2.1-pro-free",
    },
    "thanos": {
        "reference_id": "747b5e2fdd9e4e60b5ecf274f6dd51",
        "display_name": "Thanos",
        "model": "s2.1-pro-free",
    },
}

# Aliases so HUD / agent can use various forms
_ALIASES = {
    "jarvis": "iron_man",
    "iron man": "iron_man",
    "iron-man": "iron_man",
    "tony": "iron_man",
    "spiderman": "spider_man",
    "spider-man": "spider_man",
    "miles": "spider_man",
    "spidy": "spider_man",
    "god of thunder": "thor",
    "mad titan": "thanos",
    "titan": "thanos",
}

def _env_override(key: str) -> Optional[str]:
    # Allow per-character env override: FISH_VOICE_IRON_MAN, etc.
    env_key = f"FISH_VOICE_{key.upper()}"
    v = os.environ.get(env_key)
    if v and v.strip():
        return v.strip()
    return None

def get_registry() -> Dict[str, Dict[str, str]]:
    reg = {}
    for char, info in _DEFAULT_REGISTRY.items():
        override = _env_override(char)
        if override:
            reg[char] = {**info, "reference_id": override}
        else:
            reg[char] = dict(info)
    # Also check generic overrides for legacy file-based IDs
    # e.g., FISH_REFERENCE_ID env
    return reg

def normalize_character(name: Optional[str]) -> str:
    if not name:
        return "iron_man"
    key = str(name).strip().lower()
    if key in _DEFAULT_REGISTRY:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    # fuzzy: contains
    for alias, canon in _ALIASES.items():
        if alias in key:
            return canon
    for canon in _DEFAULT_REGISTRY:
        if canon in key:
            return canon
    return "iron_man"

def get_voice_for_character(character: Optional[str]) -> Dict[str, str]:
    canon = normalize_character(character)
    reg = get_registry()
    return reg.get(canon, reg["iron_man"])

def get_reference_id(character: Optional[str]) -> str:
    return get_voice_for_character(character)["reference_id"]

def get_display_name(character: Optional[str]) -> str:
    return get_voice_for_character(character)["display_name"]

def list_characters() -> Dict[str, Dict[str, str]]:
    return get_registry()
