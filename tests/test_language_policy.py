from jarvis.voice.language import LanguagePolicy, signal_for_text


def test_devanagari_and_code_switch_metadata():
    signal = signal_for_text("Jarvis Blender डाउनलोड कर दो", "hi", 0.91)
    assert signal.primary == "hi"
    assert signal.script == "Devanagari"
    assert signal.code_switch is True
    assert signal.secondary == "en"
    assert signal.direction == "ltr"


def test_language_changes_per_turn_without_overwriting_preference():
    policy = LanguagePolicy()
    assert policy.observe("open Chrome", "en").primary == "en"
    assert policy.observe("अब Blender खोलो", "hi").primary == "hi"
    assert policy.conversation_language == "hi"
    assert policy.preferred_language == "auto"


def test_explicit_language_command_is_detected():
    policy = LanguagePolicy()
    assert policy.observe("अब हिंदी में बोलो", "auto").primary == "hi"
    assert policy.observe("switch to English", "auto").primary == "en"
