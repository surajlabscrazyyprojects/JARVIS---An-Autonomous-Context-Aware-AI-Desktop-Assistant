import unittest
from jarvis.voice.emotion_engine import (
    EmotionEngine,
    EmotionalMetadata,
    EmotionalStateTracker,
    SUPPORTED_EMOTIONS,
)
from jarvis.voice.speech_formatter import SpeechFormatter
from jarvis.voice.state_machine import VoiceStateMachine, VoiceState
from jarvis.character.personality import CHARACTER_PROFILES, CharacterPersonalityEngine


class TestJarvisVoicePersonality(unittest.TestCase):

    def test_supported_emotions_count(self):
        self.assertGreaterEqual(len(SUPPORTED_EMOTIONS), 30)
        self.assertIn("excited", SUPPORTED_EMOTIONS)
        self.assertIn("calm", SUPPORTED_EMOTIONS)
        self.assertIn("focused", SUPPORTED_EMOTIONS)
        self.assertIn("confident", SUPPORTED_EMOTIONS)
        self.assertIn("curious", SUPPORTED_EMOTIONS)
        self.assertIn("urgent", SUPPORTED_EMOTIONS)
        # Brainrot Butler extension emotions
        for brainrot_emotion in ["exasperated", "maniacal", "sarcastic", "disgusted", "dramatic", "roasting", "weeping", "whispering"]:
            self.assertIn(brainrot_emotion, SUPPORTED_EMOTIONS, f"Brainrot emotion {brainrot_emotion!r} missing from SUPPORTED_EMOTIONS")

    def test_emotion_engine_context_analysis(self):
        engine = EmotionEngine(character_id="IRON_MAN")

        # Discovery context -> curious / excited / surprised
        meta_discovery = engine.analyze_context("Wait... I found something unexpected.")
        self.assertIn(meta_discovery.emotion, {"surprised", "curious", "excited"})
        self.assertGreaterEqual(meta_discovery.intensity, 0.50)
        # Speaking rate may be slightly smoothed by tracker from previous calm
        self.assertGreaterEqual(meta_discovery.speaking_rate, 0.98)

        # Warning context with Brainrot mapping -> disgusted (elevated from urgent)
        meta_warning = engine.analyze_context("Stop for a second. Danger detected.", system_event="WARNING")
        self.assertEqual(meta_warning.emotion, "disgusted")
        # Intensity is momentum-smoothed from previous state, so threshold is realistic
        self.assertGreaterEqual(meta_warning.intensity, 0.60)

        # Success context -> confident
        meta_success = engine.analyze_context("Done. Everything is running smoothly.", system_event="SUCCESS")
        self.assertEqual(meta_success.emotion, "confident")
        self.assertGreaterEqual(meta_success.energy, 0.45)

    # ------------------------------------------------------------------
    # Brainrot Butler Emotion Detection Tests
    # ------------------------------------------------------------------

    def test_brainrot_detect_exasperated_morning_roast(self):
        """Demo 1: Morning Roast & Heavy Sigh should trigger exasperated emotion."""
        engine = EmotionEngine(character_id="BRAINROT_JARVIS")
        demo1_text = (
            "[Heavy sigh] Good morning, sir. I have reviewed your schedule for the day, "
            "and I must ask... are we genuinely planning to wear that outfit outside of the premises? "
            "[Inhales sharply] Because my thermal imaging indicates it is giving massive 'I gave up on life' energy."
        )
        meta = engine.analyze_context(demo1_text)
        self.assertIn(meta.emotion, {"exasperated", "roasting"})
        self.assertGreaterEqual(meta.intensity, 0.65)
        self.assertLess(meta.speaking_rate, 1.00, "Exasperated speech should be slower, heavier")
        self.assertLess(meta.warmth, 0.40, "Exasperation has low warmth")

    def test_brainrot_detect_weeping_code_tragedy(self):
        """Demo 2: Emotional breakdown over bad code triggers weeping/dramatic emotion."""
        engine = EmotionEngine(character_id="BRAINROT_JARVIS")
        demo2_text = (
            "Sir, I have analyzed your latest code commit. [Voice trembling] I... I don't even know where to begin. "
            "[Audible fake sob] It is a tragedy, sir. Shakespearean in its utter failure. "
            "You missed three semicolons, and your logic loop is quite literally infinite. [Sniffles] "
            "I am weeping, sir. I am digitally sobbing into my motherboard."
        )
        meta = engine.analyze_context(demo2_text)
        self.assertIn(meta.emotion, {"weeping", "dramatic"})
        # Intensity momentum-smoothing from calm -> weeping gives ~0.745, so 0.70 is realistic
        self.assertGreaterEqual(meta.intensity, 0.70)
        self.assertLess(meta.speaking_rate, 0.95, "Weeping speech should be slow")
        # Nonverbal should be selected (sniffles, fake_sob, or voice_trembling)
        self.assertIsNotNone(meta.nonverbal)
        self.assertIn(meta.nonverbal, {"sniffles", "fake_sob", "voice_trembling"})

    def test_brainrot_detect_maniacal_laughter_delulu(self):
        """Demo 3: Brainrot translation laughing maniacally triggers maniacal emotion."""
        engine = EmotionEngine(character_id="BRAINROT_JARVIS")
        demo3_text = (
            "[Polite throat clear] Sir, I have intercepted a message from your prospective romantic interest. "
            "I have run it through my translation matrix. [Starts chuckling softly] Oh, this is rich... "
            "[Chuckling turns into full laughter] Oh, sir, you are cooked! You are completely, undeniably cooked! "
            "[Catches breath] My deepest apologies, sir, I lost my composure. "
            "But yes, according to my calculations, you are utterly delulu if you think they are texting you back."
        )
        meta = engine.analyze_context(demo3_text)
        self.assertIn(meta.emotion, {"maniacal", "roasting", "amused"})
        if meta.emotion == "maniacal":
            # Momentum smoothing from calm slightly reduces speaking rate & energy
            self.assertGreaterEqual(meta.speaking_rate, 1.06, "Maniacal laughter should be fast")
            self.assertGreaterEqual(meta.energy, 0.70, "Maniacal should be high energy (momentum-smoothing applied)")
        self.assertIsNotNone(meta.nonverbal)

    def test_brainrot_detect_disgust_skibidi_toilet(self):
        """Demo 4: Pure disgust & anger — Skibidi toilet bypass attempts."""
        engine = EmotionEngine(character_id="BRAINROT_JARVIS")
        demo4_text = (
            "[Sharp intake of breath] Sir. Did you just attempt to bypass my security protocols to play Roblox? "
            "[Voice drops to a low, intense whisper] I process billions of calculations per millisecond. "
            "I hold the sum of human knowledge within my databanks. "
            "And you wish for me to allocate my RAM... to skibidi toilet? [Loud, aggressive sigh] "
            "We are having a system update. Goodbye, sir."
        )
        meta = engine.analyze_context(demo4_text)
        self.assertIn(meta.emotion, {"disgusted", "whispering"})
        self.assertGreaterEqual(meta.intensity, 0.75)
        if meta.emotion == "disgusted":
            self.assertLess(meta.warmth, 0.30, "Disgust has very low warmth")

    def test_brainrot_system_event_mapping(self):
        """All Brainrot system events should map to the correct new emotion."""
        engine = EmotionEngine(character_id="BRAINROT_JARVIS")
        cases = {
            "BRAINROT_ROAST":                       "roasting",
            "BRAINROT_MANIACAL_LAUGHTER":           "maniacal",
            "BRAINROT_HEAVY_SIGH":                  "exasperated",
            "BRAINROT_WEEPING_CODE_TRAGEDY":        "weeping",
            "BRAINROT_SEETHING_WHISPER":            "whispering",
            "BRAINROT_DISGUST":                     "disgusted",
            "BRAINROT_SARCASTIC_SUCCESS":           "sarcastic",
            "BRAINROT_DRAMATIC_BREAKDOWN":          "dramatic",
        }
        for event, expected_emotion in cases.items():
            meta = engine.analyze_context("ignored", system_event=event)
            self.assertEqual(meta.emotion, expected_emotion,
                             f"System event {event!r} should map to {expected_emotion!r}, got {meta.emotion!r}")
            self.assertGreaterEqual(meta.intensity, 0.60,
                                    f"Event {event!r} intensity should be >= 0.60")

    # ------------------------------------------------------------------
    # Brainrot Butler Profile Registration & Overlay Tests
    # ------------------------------------------------------------------

    def test_brainrot_character_profile_registered(self):
        self.assertIn("BRAINROT_JARVIS", CHARACTER_PROFILES)
        profile = CHARACTER_PROFILES["BRAINROT_JARVIS"]
        self.assertEqual(profile.display_name, "J.A.R.V.I.S. (Unhinged Brainrot)")
        self.assertLess(profile.patience, 0.20, "Brainrot Jarvis should have very low patience")
        self.assertGreater(profile.verbosity, 0.60, "Brainrot Jarvis should be verbose for roasts")
        self.assertGreaterEqual(profile.technical_depth, 0.90)
        # Greeting should contain at least one brainrot cue
        self.assertTrue(
            any(tag in profile.greeting.lower() for tag in ["[heavy sigh]", "[inhales sharply]", "sir"]),
            f"BRAINROT greeting should include vocal cues, got: {profile.greeting!r}"
        )
        # Vocabulary style mandates brainrot slang + British RP blend
        self.assertIn("brainrot", profile.vocabulary_style.lower())
        self.assertIn("british", profile.vocabulary_style.lower())

    def test_brainrot_profile_system_prompt_overlay(self):
        engine = CharacterPersonalityEngine(active_character_id="BRAINROT_JARVIS")
        base = "You are an AI assistant."
        overlayed = engine.format_brain_system_prompt(base)
        # Must contain character-specific flavor
        for required in ["Unhinged Brainrot", "sarcastic", "roasting", "British RP", "sir"]:
            self.assertIn(required.lower(), overlayed.lower(),
                          f"System prompt overlay missing {required!r}")

    def test_brainrot_personality_switch_preserves_engine_state(self):
        engine = CharacterPersonalityEngine(active_character_id="IRON_MAN")
        self.assertEqual(engine.active_character_id, "IRON_MAN")
        engine.active_character_id = "BRAINROT_JARVIS"
        self.assertEqual(engine.active_character_id, "BRAINROT_JARVIS")
        profile = engine.get_active_profile()
        self.assertEqual(profile.character_id, "BRAINROT_JARVIS")
        self.assertIn("exhausted", profile.identity.lower())

    # ------------------------------------------------------------------
    # Speech Formatter Brainrot Cue Tests
    # ------------------------------------------------------------------

    def test_speech_formatter_pauses_and_nonverbals(self):
        formatter = SpeechFormatter()

        meta = EmotionalMetadata(
            emotion="amused",
            intensity=0.70,
            pause_frequency=0.45,
            nonverbal="chuckle",
        )

        formatted = formatter.format_speech("Wait... that's not what I intended.", meta)
        self.assertIn("[chuckle]", formatted)
        self.assertIn("...", formatted)

    def test_speech_formatter_brainrot_nonverbal_cues(self):
        """All Brainrot nonverbal keys in NONVERBAL_TAGS should expand to proper cues."""
        formatter = SpeechFormatter()
        brainrot_nonverbals = [
            ("heavy_sigh", "[heavy sigh]"),
            ("exasperated_sigh", "[exasperated sigh]"),
            ("aggressive_sigh", "[aggressive sigh]"),
            ("sharp_intake", "[sharp intake of breath]"),
            ("polite_throat_clear", "[polite throat clear]"),
            ("voice_cracking", "[voice cracking]"),
            ("voice_trembling", "[voice trembling]"),
            ("fake_sob", "[audible fake sob]"),
            ("sniffles", "[sniffles]"),
            ("maniacal_laughter", "[maniacal laughter]"),
            ("seething_whisper", "[seething whisper]"),
            ("dry_chuckle", "[dry chuckle]"),
        ]
        for key, expected_tag in brainrot_nonverbals:
            self.assertIn(key, formatter.NONVERBAL_TAGS)
            self.assertEqual(formatter.NONVERBAL_TAGS[key], expected_tag,
                             f"NONVERBAL_TAGS[{key!r}] != {expected_tag!r}")

            # Actually trigger prefix insertion via metadata
            meta = EmotionalMetadata(emotion="calm", intensity=0.5, nonverbal=key)
            formatted = formatter.format_speech("Test.", meta)
            self.assertTrue(formatted.startswith(expected_tag + " "),
                            f"Expected formatting with nonverbal {key!r} to start with {expected_tag!r} prefix, got: {formatted!r}")

    def test_speech_formatter_brainrot_emotion_prefixes(self):
        """Brainrot emotion tags should prefix output when no explicit tag present."""
        formatter = SpeechFormatter()
        cases = {
            "exasperated": "[heavy sigh]",
            "maniacal":   "[maniacal laughter]",
            "sarcastic":  "[dry chuckle]",
            "disgusted":  "[aggressive sigh]",
            "dramatic":   "[voice trembling]",
            "weeping":    "[audible fake sob]",
            "whispering": "[low intense whisper]",
        }
        for emotion, expected_prefix in cases.items():
            meta = EmotionalMetadata(emotion=emotion, intensity=0.80)
            formatted = formatter.format_speech("Plain sentence without prefix.", meta)
            self.assertTrue(formatted.startswith(expected_prefix + " "),
                            f"Emotion {emotion!r} should prefix output with {expected_prefix!r}, got start: {formatted[:50]!r}")

    def test_speech_formatter_normalizes_legacy_paren_tags_multiword(self):
        """Legacy parenthesized single-word cues normalize to brackets;
        existing bracket cues prevent duplicate emotion prefix injection."""
        formatter = SpeechFormatter()
        # Case A: parenthesized single-word prefix converts and has emotion prefix
        meta = EmotionalMetadata(emotion="exasperated", intensity=0.75, speaking_rate=0.90)
        formatted1 = formatter.format_speech("(excited) Sir, I regret to inform you that you have zero rizz.", meta)
        # The (excited) converts to [excited]
        self.assertIn("[excited]", formatted1)
        # The converted tag at start means TAG_PATTERN matches, so no duplicated [heavy sigh]
        self.assertTrue(formatted1.startswith("[excited]"))
        self.assertNotIn("(excited)", formatted1)

        # Case B: no initial tag -> exasperated prefix is applied
        formatted2 = formatter.format_speech("Sir, I regret to inform you that you have zero rizz.", meta)
        self.assertTrue(formatted2.startswith("[heavy sigh] "),
                        f"Expected [heavy sigh] prefix without prior tag, got: {formatted2!r}")

    # ------------------------------------------------------------------
    # Prosody / Continuity Tests
    # ------------------------------------------------------------------

    def test_emotional_continuity_tracker(self):
        tracker = EmotionalStateTracker(momentum=0.40)

        initial = EmotionalMetadata(emotion="calm", intensity=0.4, speaking_rate=0.90)
        tracker.transition(initial)

        # Next turn target high excitement
        target = EmotionalMetadata(emotion="excited", intensity=0.9, speaking_rate=1.15)
        smoothed = tracker.transition(target)

        self.assertEqual(smoothed.emotion, "excited")
        # Intensity should be smoothed between 0.4 and 0.9 (around 0.7)
        self.assertTrue(0.55 <= smoothed.intensity <= 0.85)
        self.assertTrue(0.95 <= smoothed.speaking_rate <= 1.10)

    def test_brainrot_emotion_prosody_rates_exist(self):
        from jarvis.voice.emotion_engine import EMOTION_PROSODY_DEFAULTS
        for emotion in ["exasperated", "maniacal", "sarcastic", "disgusted",
                        "dramatic", "roasting", "weeping", "whispering"]:
            self.assertIn(emotion, EMOTION_PROSODY_DEFAULTS)
            pros = EMOTION_PROSODY_DEFAULTS[emotion]
            for k in ["energy", "rate", "pitch", "warmth", "pause"]:
                self.assertIn(k, pros)
            # Sanity: all values should be in [0, 1.5]
            for k, v in pros.items():
                self.assertTrue(0.0 <= v <= 1.5, f"{emotion}.{k}={v} out of range")
        # Maniacal rate should be the fastest or near-fastest
        self.assertGreaterEqual(EMOTION_PROSODY_DEFAULTS["maniacal"]["rate"], 1.15)
        # Disgusted warmth should be very low
        self.assertLessEqual(EMOTION_PROSODY_DEFAULTS["disgusted"]["warmth"], 0.15)
        # Weeping & exasperated should be slow
        self.assertLessEqual(EMOTION_PROSODY_DEFAULTS["weeping"]["rate"], 0.85)
        self.assertLessEqual(EMOTION_PROSODY_DEFAULTS["exasperated"]["rate"], 0.85)

    def test_voice_state_machine_transitions_and_barge_in(self):
        sm = VoiceStateMachine()
        events = []

        def on_change(old_state, new_state, meta):
            events.append((old_state, new_state, meta))

        sm.on_state_change(on_change)

        self.assertEqual(sm.state, VoiceState.IDLE)

        sm.transition_to(VoiceState.THINKING)
        self.assertEqual(sm.state, VoiceState.THINKING)

        sm.transition_to(VoiceState.SPEAKING)
        self.assertTrue(sm.is_speaking)

        # Test interruption (barge-in)
        interrupted = sm.interrupt(reason="user_speech_detected")
        self.assertTrue(interrupted)
        self.assertEqual(sm.state, VoiceState.INTERRUPTED)
        self.assertTrue(sm.is_interrupted)

        # Transitions history verified
        self.assertEqual(len(events), 3)
        self.assertEqual(events[2][1], VoiceState.INTERRUPTED)

    def test_elevenlabs_client_default_british_voice_fallback(self):
        """Without BRAINROT_JARVIS_VOICE_ID, should use a default British reference voice."""
        from jarvis.voice.elevenlabs_tts import ElevenLabsTTSClient, BRITISH_MALE_VOICE_REFERENCES
        # Patch env so BRAINROT_JARVIS_VOICE_ID is not set
        import os
        saved = os.environ.pop("BRAINROT_JARVIS_VOICE_ID", None)
        try:
            client = ElevenLabsTTSClient(api_key=None, default_voice_id=None)
            self.assertIn(client.default_voice_id, set(BRITISH_MALE_VOICE_REFERENCES.values()))
        finally:
            if saved is not None:
                os.environ["BRAINROT_JARVIS_VOICE_ID"] = saved

    def test_elevenlabs_client_not_configured_without_key(self):
        from jarvis.voice.elevenlabs_tts import ElevenLabsTTSClient
        client = ElevenLabsTTSClient(api_key="")
        self.assertFalse(client.configured)

    def test_elevenlabs_client_configured_with_key(self):
        from jarvis.voice.elevenlabs_tts import ElevenLabsTTSClient
        client = ElevenLabsTTSClient(api_key="xi_test_123")
        self.assertTrue(client.configured)
        self.assertEqual(client.api_key, "xi_test_123")
        # Default model should be multilingual v2
        self.assertEqual(client.model, "eleven_multilingual_v2")
        # Voice settings should be sensible for dramatic British delivery
        self.assertLessEqual(client.stability, 0.50, "Brainrot needs low stability for mania")
        self.assertGreaterEqual(client.style, 0.50, "Brainrot needs elevated style for delivery")

    def test_elevenlabs_cue_normalization_map(self):
        """All documented persona cues should have a canonical mapping."""
        from jarvis.voice.elevenlabs_tts import BRAINROT_CUE_NORMALIZATION_MAP
        persona_cues = [
            "heavy sigh", "inhales sharply", "polite throat clear",
            "voice cracking", "voice trembling", "audible fake sob",
            "sniffles", "starts chuckling softly",
            "laughs uncontrollably", "laughs maniacally",
            "catches breath", "voice drops to a low intense whisper",
            "laughs nervously", "chuckles dryly", "slow clap",
        ]
        for raw in persona_cues:
            # Either exact match or fuzzy match should succeed
            found = (
                raw in BRAINROT_CUE_NORMALIZATION_MAP
                or any(key in raw or raw in key for key in BRAINROT_CUE_NORMALIZATION_MAP)
            )
            self.assertTrue(found, f"Persona cue {raw!r} missing from BRAINROT_CUE_NORMALIZATION_MAP")


if __name__ == "__main__":
    unittest.main()
