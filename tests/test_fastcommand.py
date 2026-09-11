"""Tests for FastCommandCore — deterministic parser, registries, executor,
ownership arbitration and core gating (spec §42 acceptance matrix)."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.fastcommand import (
    AudioOwnershipManager,
    AudioOwnershipMode,
    FastCommandCore,
    FastCommandExecutor,
    FastCommandParser,
    FastCommandRegistry,
    FastCommandSTT,
    FastResponseSpeaker,
)
from jarvis.fastcommand.parser import (
    BROWSER_BACK,
    BROWSER_CLOSE_TAB,
    BROWSER_FORWARD,
    BROWSER_NEW_TAB,
    BROWSER_NEXT_TAB,
    BROWSER_PREV_TAB,
    BROWSER_REFRESH,
    ESCALATE,
    FILE_CREATE,
    FILE_FIND,
    GET_BRIGHTNESS,
    GET_VOLUME,
    MEDIA_NEXT,
    MEDIA_PAUSE,
    MEDIA_PLAY,
    MEDIA_PLAY_PAUSE,
    MEDIA_PREVIOUS,
    MEDIA_STOP,
    MISSING_PARAM,
    MUTE,
    OPEN_APP,
    OPEN_SITE,
    OPEN_URL,
    SEARCH_SITE,
    SET_BRIGHTNESS,
    SET_VOLUME,
    UNMUTE,
    FastCommand,
)


@pytest.fixture
def registry() -> FastCommandRegistry:
    return FastCommandRegistry()


@pytest.fixture
def parser(registry: FastCommandRegistry) -> FastCommandParser:
    return FastCommandParser(registry=registry)


@pytest.fixture
def executor(registry: FastCommandRegistry) -> FastCommandExecutor:
    from jarvis.windows import AudioAdapter, DisplayAdapter, MediaAdapter

    real = FastCommandExecutor(registry=registry)
    real.audio = AudioAdapter()
    real.display = DisplayAdapter()
    real.media = MediaAdapter()
    return real


@pytest.fixture
def ownership(tmp_path) -> AudioOwnershipManager:
    return AudioOwnershipManager(state_file=tmp_path / "owner.json", owner="test")


@pytest.fixture
def speaker() -> "_FakeSpeaker":
    return _FakeSpeaker()


@pytest.fixture
def stt() -> FastCommandSTT:
    return FastCommandSTT()


VALUE_COMMANDS: list[tuple[str, int]] = [
    ("volume 60", 60),
    ("volume 10", 10),
    ("volume 100", 100),
    ("volume 60 kar", 60),
    ("volume ko 60 pe kar", 60),
    ("volume ko 60 par karo", 60),
    ("set volume to 60", 60),
    ("volume 60 percent", 60),
    ("volume ko sixty percent karo", 60),
    ("set the volume to forty percent", 40),
    ("volume to hundred", 100),
    ("volume twenty", 20),
    ("brightness 50", 50),
    ("set brightness to 50", 50),
    ("brightness 50 percent", 50),
    ("brightness ko 50 pe kar", 50),
    ("brightness 50 kar", 50),
    ("brightness 40 pe kar", 40),
    ("brightness fifty percent kar", 50),
]


@pytest.mark.parametrize("text,expected", VALUE_COMMANDS)
def test_value_commands(parser: FastCommandParser, text: str, expected: int) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.value == expected


GET_VALUE_COMMANDS: list[tuple[str, str]] = [
    ("volume kya hai", GET_VOLUME),
    ("what is the volume", GET_VOLUME),
    ("current volume", GET_VOLUME),
    ("volume batao", GET_VOLUME),
    ("brightness kya hai", GET_BRIGHTNESS),
    ("what is the brightness", GET_BRIGHTNESS),
    ("brightness check", GET_BRIGHTNESS),
]


@pytest.mark.parametrize("text,intent", GET_VALUE_COMMANDS)
def test_get_value_commands(parser: FastCommandParser, text: str, intent: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == intent
    assert cmd.value is None


MUTE_COMMANDS: list[tuple[str, str]] = [
    ("mute", MUTE),
    ("mute kar", MUTE),
    ("mute karo", MUTE),
    ("sound band kar", MUTE),
    ("volume mute", MUTE),
    ("aawaz band kar", MUTE),
    ("unmute", UNMUTE),
    ("unmute kar", UNMUTE),
    ("mute off", UNMUTE),
    ("sound on kar", UNMUTE),
    ("volume on", UNMUTE),
    ("unmute karo", UNMUTE),
]


@pytest.mark.parametrize("text,intent", MUTE_COMMANDS)
def test_mute_commands(parser: FastCommandParser, text: str, intent: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == intent
    assert cmd.value is None


MISSING_VALUE_PHRASES: list[str] = [
    "volume",
    "volume kar",
    "volume set kar",
    "volume to",
    "brightness",
    "brightness kar",
]


@pytest.mark.parametrize("text", MISSING_VALUE_PHRASES)
def test_missing_value_never_guesses(parser: FastCommandParser, text: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == MISSING_PARAM
    assert cmd.value is None
    assert cmd.missing in ("volume_value", "brightness_value")


MEDIA_COMMANDS: list[tuple[str, str]] = [
    ("play", MEDIA_PLAY),
    ("play kar", MEDIA_PLAY),
    ("play karo", MEDIA_PLAY),
    ("resume", MEDIA_PLAY),
    ("continue", MEDIA_PLAY),
    ("bajao", MEDIA_PLAY),
    ("play the music", MEDIA_PLAY),
    ("play song", MEDIA_PLAY),
    ("pause", MEDIA_PAUSE),
    ("pause kar", MEDIA_PAUSE),
    ("pause karo", MEDIA_PAUSE),
    ("thama do", MEDIA_PAUSE),
    ("play pause", MEDIA_PLAY_PAUSE),
    ("pause play", MEDIA_PLAY_PAUSE),
    ("play pause kar", MEDIA_PLAY_PAUSE),
    ("toggle", MEDIA_PLAY_PAUSE),
    ("next", MEDIA_NEXT),
    ("next song", MEDIA_NEXT),
    ("next track", MEDIA_NEXT),
    ("skip", MEDIA_NEXT),
    ("skip song", MEDIA_NEXT),
    ("aage badhao", MEDIA_NEXT),
    ("next kar", MEDIA_NEXT),
    ("song change", MEDIA_NEXT),
    ("previous", MEDIA_PREVIOUS),
    ("previous song", MEDIA_PREVIOUS),
    ("previous track", MEDIA_PREVIOUS),
    ("prev", MEDIA_PREVIOUS),
    ("back song", MEDIA_PREVIOUS),
    ("pichla song", MEDIA_PREVIOUS),
    ("previous kar", MEDIA_PREVIOUS),
    ("stop", MEDIA_STOP),
    ("stop kar", MEDIA_STOP),
    ("stop the music", MEDIA_STOP),
    ("rok", MEDIA_STOP),
    ("rok do", MEDIA_STOP),
    ("band kar", MEDIA_STOP),
    ("band karo", MEDIA_STOP),
]


@pytest.mark.parametrize("text,intent", MEDIA_COMMANDS)
def test_media_commands(parser: FastCommandParser, text: str, intent: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == intent
    assert cmd.value is None


BROWSER_COMMANDS: list[tuple[str, str]] = [
    ("refresh", BROWSER_REFRESH),
    ("reload", BROWSER_REFRESH),
    ("refresh page", BROWSER_REFRESH),
    ("page refresh kar", BROWSER_REFRESH),
    ("reload kar", BROWSER_REFRESH),
    ("back", BROWSER_BACK),
    ("go back", BROWSER_BACK),
    ("peeche ja", BROWSER_BACK),
    ("wapis ja", BROWSER_BACK),
    ("forward", BROWSER_FORWARD),
    ("go forward", BROWSER_FORWARD),
    ("forward ja", BROWSER_FORWARD),
    ("new tab", BROWSER_NEW_TAB),
    ("naya tab", BROWSER_NEW_TAB),
    ("tab kholo", BROWSER_NEW_TAB),
    ("open new tab", BROWSER_NEW_TAB),
    ("close tab", BROWSER_CLOSE_TAB),
    ("tab band kar", BROWSER_CLOSE_TAB),
    ("close this tab", BROWSER_CLOSE_TAB),
    ("next tab", BROWSER_NEXT_TAB),
    ("tab change", BROWSER_NEXT_TAB),
    ("previous tab", BROWSER_PREV_TAB),
    ("pichla tab", BROWSER_PREV_TAB),
    ("last tab", BROWSER_PREV_TAB),
]


@pytest.mark.parametrize("text,intent", BROWSER_COMMANDS)
def test_browser_commands(parser: FastCommandParser, text: str, intent: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == intent
    assert cmd.value is None


OPEN_TARGETS: list[tuple[str, str]] = [
    ("open notepad", "notepad"),
    ("open calculator", "calculator"),
    ("open chrome", "chrome"),
    ("open vscode", "vscode"),
    ("open visual studio code", "vscode"),
    ("open after effects", "after effects"),
    ("open ae", "after effects"),
    ("open premiere pro", "premiere pro"),
    ("open spotify", "spotify"),
    ("open youtube", "youtube"),
    ("open wikipedia", "wikipedia"),
    ("chrome kholo", "chrome"),
    ("notepad kholo", "notepad"),
    ("notepad khol", "notepad"),
    ("chrome chalao", "chrome"),
    ("youtube kholo", "youtube"),
    ("spotify kholo", "spotify"),
    ("open whatsapp", "whatsapp"),
    ("open the chrome", "chrome"),
]


@pytest.mark.parametrize("text,target", OPEN_TARGETS)
def test_open_app_and_site(parser: FastCommandParser, text: str, target: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.app is not None or cmd.site is not None


SEARCH_CASES: list[tuple[str, str, str]] = [
    ("youtube pe physics wallah search kar", "youtube", "physics wallah"),
    ("physics wallah youtube pe search kar", "youtube", "physics wallah"),
    ("search physics wallah on youtube", "youtube", "physics wallah"),
    ("youtube par physics wallah dhoondo", "youtube", "physics wallah"),
    ("wikipedia pe gravity search kar", "wikipedia", "gravity"),
    ("wikipedia pe gravity search karo", "wikipedia", "gravity"),
    ("indian hacker youtube pe search kar", "youtube", "indian hacker"),
    ("google pe python tutorial search kar", "google", "python tutorial"),
    ("github pe fastapi search kar", "github", "fastapi"),
]


@pytest.mark.parametrize("text,site,query", SEARCH_CASES)
def test_site_search_word_orders(
    parser: FastCommandParser, text: str, site: str, query: str
) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == SEARCH_SITE
    assert cmd.site == site
    assert cmd.query == query


def test_site_search_url_construction(registry: FastCommandRegistry) -> None:
    url = registry.search_url_for("youtube", "physics wallah")
    assert url == "https://www.youtube.com/results?search_query=physics+wallah"
    url = registry.search_url_for("wikipedia", "gravity")
    assert url == "https://en.wikipedia.org/w/index.php?search=gravity"
    url = registry.search_url_for("stackoverflow", "python")
    assert url == "https://stackoverflow.com/search?q=python"


@pytest.mark.parametrize("site", ["instagram", "x"])
def test_unsupported_site_search_returns_none(registry: FastCommandRegistry, site: str) -> None:
    assert registry.search_url_for(site, "query") is None


OPEN_URLS: list[str] = [
    "open https://example.com/page?q=1",
    "open http://example.com",
    "open www.youtube.com/watch?v=abc",
    "open youtube.com",
    "go to github.com",
    "go to youtube.com/watch?v=dQw4w9WgXcQ",
]


@pytest.mark.parametrize("text", OPEN_URLS)
def test_open_url_commands(parser: FastCommandParser, text: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == OPEN_URL
    assert cmd.value is None


MISSING_OPEN_TARGETS: list[str] = [
    "open",
    "kholo",
    "khol",
    "open kar",
    "launch",
    "search",
    "search kar",
]


@pytest.mark.parametrize("text", MISSING_OPEN_TARGETS)
def test_missing_open_target(parser: FastCommandParser, text: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == MISSING_PARAM
    assert cmd.value is None
    assert cmd.missing == "target"


CREATE_CASES: list[tuple[str, str, str, str | None]] = [
    ("create folder Projects", "Projects", "folder", None),
    ("create folder Projects in Documents", "Projects", "folder", "Documents"),
    ("create file hello.txt in Documents", "hello.txt", "file", "Documents"),
    ("create a python file named Jarvis Agent in Documents", "Jarvis Agent", "python", "Documents"),
    ("create file notes.txt", "notes.txt", "file", None),
]


@pytest.mark.parametrize("text,name,kind,loc", CREATE_CASES)
def test_file_create_parse(
    parser: FastCommandParser, text: str, name: str, kind: str, loc: str | None
) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == FILE_CREATE
    assert cmd.file_kind == kind
    assert cmd.name == name
    assert cmd.location == loc


FIND_CASES: list[tuple[str, str]] = [
    ("find my physics notes", "physics notes"),
    ("find physics notes", "physics notes"),
    ("search for blender files", "blender files"),
    ("dhoondo my blender files", "blender files"),
    ("where is my jarvis agent", "jarvis agent"),
]


@pytest.mark.parametrize("text,query", FIND_CASES)
def test_file_find_parse(parser: FastCommandParser, text: str, query: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == FILE_FIND
    assert cmd.query == query


CREATE_ALONE_PHRASES: list[str] = ["create file", "create a file", "create folder"]


@pytest.mark.parametrize("text", CREATE_ALONE_PHRASES)
def test_create_file_alone_asks(parser: FastCommandParser, text: str) -> None:
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == MISSING_PARAM
    assert cmd.value is None
    assert cmd.missing == "file_info"


ESCALATION_PHRASES: list[str] = [
    "I want the best beginner Blender tutorial",
    "find the best physics wallah video",
    "recommend a good movie",
    "which is better vscode or pycharm",
    "how to install python",
    "what is the best laptop",
    "top rated phones 2026",
    "explain quantum physics",
]


@pytest.mark.parametrize("text", ESCALATION_PHRASES)
def test_escalation_phrases(parser: FastCommandParser, text: str) -> None:
    assert parser.is_escalation(text) is True


def test_platform_search_with_best_is_still_fast(parser: FastCommandParser) -> None:
    text = "youtube pe best blender tutorial search kar"
    assert parser.is_escalation(text) is False
    cmd = parser.parse(text)
    assert cmd is not None
    assert cmd.intent == SEARCH_SITE
    assert cmd.value is None


PLAIN_COMMANDS: list[str] = ["volume 60", "open notepad", "pause", "refresh page", "brightness 50"]


@pytest.mark.parametrize("text", PLAIN_COMMANDS)
def test_plain_commands_never_escalate(parser: FastCommandParser, text: str) -> None:
    assert parser.is_escalation(text) is False


UNRECOGNIZED_PHRASES: list[str] = ["hello there", "what time is it", "thanks a lot", "ok bye"]


@pytest.mark.parametrize("text", UNRECOGNIZED_PHRASES)
def test_unrecognized_returns_none(parser: FastCommandParser, text: str) -> None:
    assert parser.parse(text) is None


# ---------------------------------------------------------------------------
# Ownership arbitration
# ---------------------------------------------------------------------------


def test_ownership_default_fast(ownership: AudioOwnershipManager) -> None:
    assert ownership.mode == AudioOwnershipMode.FAST_COMMAND
    assert ownership.can_listen
    assert ownership.can_speak


def test_ownership_jarvis_locks_fast(ownership: AudioOwnershipManager) -> None:
    assert ownership.enter_jarvis()
    assert ownership.mode == AudioOwnershipMode.JARVIS
    assert not ownership.can_listen
    assert not ownership.can_speak


def test_ownership_release_restores_fast(ownership: AudioOwnershipManager) -> None:
    ownership.enter_jarvis()
    ownership.release()
    assert ownership.mode == AudioOwnershipMode.FAST_COMMAND
    assert ownership.can_listen


def test_ownership_disabled_blocks_everything(ownership: AudioOwnershipManager) -> None:
    ownership.disable()
    assert ownership.mode == AudioOwnershipMode.DISABLED
    assert not ownership.can_listen
    assert not ownership.enter_jarvis()


def test_ownership_state_file_written(ownership: AudioOwnershipManager, tmp_path: Path) -> None:
    ownership.enter_jarvis()
    data = (tmp_path / "owner.json").read_text(encoding="utf-8")
    assert "JARVIS_MODE" in data


def test_ownership_transitioning_blocks_listening(ownership: AudioOwnershipManager) -> None:
    ownership.transition_to(AudioOwnershipMode.JARVIS)
    assert not ownership.can_listen


# ---------------------------------------------------------------------------
# Executor (real Windows adapters)
# ---------------------------------------------------------------------------


def test_executor_volume_roundtrip(executor: FastCommandExecutor) -> None:
    result = executor.execute(FastCommand(SET_VOLUME, value=40))
    assert result.success
    assert result.verified
    assert result.data.get("actual") == 40
    before = executor.audio.get_volume().data.get("volume_percent")
    r = executor.execute(FastCommand(GET_VOLUME))
    assert r.data.get("volume") == before


def test_executor_brightness_roundtrip(executor: FastCommandExecutor) -> None:
    result = executor.execute(FastCommand(SET_BRIGHTNESS, value=50))
    if result.status == "UNSUPPORTED":
        return
    assert result.success
    assert result.verified
    assert result.data.get("brightness_percent") == 50


def test_executor_mute_unmute(executor: FastCommandExecutor) -> None:
    r = executor.execute(FastCommand(MUTE))
    assert r.success
    assert r.verified
    r2 = executor.execute(FastCommand(UNMUTE))
    assert r2.success
    assert r2.verified


def test_executor_media_key_delivered_honest(executor: FastCommandExecutor) -> None:
    r = executor.execute(FastCommand(MEDIA_PLAY))
    assert r.success
    assert r.status == "DELIVERED"
    assert not r.verified


def test_executor_browser_key_delivered_honest(executor: FastCommandExecutor) -> None:
    r = executor.execute(FastCommand(BROWSER_NEW_TAB))
    assert r.success
    assert r.status == "DELIVERED"
    assert not r.verified


def test_executor_unknown_app_fails_honestly(executor: FastCommandExecutor) -> None:
    r = executor.execute(FastCommand(OPEN_APP, app="zzz_no_such_app"))
    assert not r.success
    assert r.response_key == "app_not_found"


def test_executor_file_create_and_find(registry: FastCommandRegistry, tmp_path: Path) -> None:
    exec_ = FastCommandExecutor(registry=registry, find_roots=[tmp_path])
    assert exec_._resolve_location("Documents") == tmp_path
    r = exec_.execute(FastCommand(FILE_CREATE, name="Jarvis Agent", file_kind="python"))
    assert r.success
    assert r.verified
    assert (tmp_path / "Jarvis Agent.py").exists()
    r2 = exec_.execute(FastCommand(FILE_CREATE, name="Projects", file_kind="folder"))
    assert r2.success
    assert r2.verified
    assert (tmp_path / "Projects").is_dir()
    (tmp_path / "physics notes.txt").write_text("x", encoding="utf-8")
    r3 = exec_.execute(FastCommand(FILE_FIND, query="physics notes"))
    assert r3.success
    assert any("physics notes" in str(m) for m in r3.data.get("matches", []))


def test_executor_file_create_never_overwrites(
    registry: FastCommandRegistry, tmp_path: Path
) -> None:
    exec_ = FastCommandExecutor(registry=registry, find_roots=[tmp_path])
    target = tmp_path / "keep.txt"
    target.write_text("original", encoding="utf-8")
    r = exec_.execute(FastCommand(FILE_CREATE, name="keep.txt", file_kind="file"))
    assert r.success
    assert r.verified
    assert target.read_text(encoding="utf-8") == "original"


# ---------------------------------------------------------------------------
# Core gating (deterministic fakes)
# ---------------------------------------------------------------------------


class _FakeSpeaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, command: FastCommand) -> object:
        from jarvis.fastcommand import FastCommandResult

        self.calls.append(command.intent)
        return FastCommandResult(
            command.intent,
            success=True,
            status="VERIFIED",
            verified=True,
            response_key="volume_set",
            params={"value": 60},
        )


def _make_core(
    ownership: AudioOwnershipManager,
    parser: FastCommandParser,
    executor: object,
    speaker: object,
    confidence_threshold: float = 0.3,
) -> FastCommandCore:
    return FastCommandCore(
        ownership=ownership,
        parser=parser,
        executor=executor,
        speaker=speaker,
        confidence_threshold=confidence_threshold,
    )


def test_core_ignores_while_jarvis_mode(
    ownership: AudioOwnershipManager, parser: FastCommandParser
) -> None:
    executor = _FakeExecutor()
    speaker = _FakeSpeaker()
    core = _make_core(ownership, parser, executor, speaker)
    ownership.enter_jarvis()
    record = core.handle_utterance("volume 60", confidence=0.9)
    assert record is None
    assert executor.calls == []


def test_core_ignores_low_confidence(
    ownership: AudioOwnershipManager, parser: FastCommandParser
) -> None:
    executor = _FakeExecutor()
    speaker = _FakeSpeaker()
    core = _make_core(ownership, parser, executor, speaker)
    record = core.handle_utterance("volume 60", confidence=0.1)
    assert record is None
    assert executor.calls == []


def test_core_executes_and_speaks_fixed_response(
    ownership: AudioOwnershipManager, parser: FastCommandParser
) -> None:
    executor = _FakeExecutor()
    speaker = _FakeSpeaker()
    core = _make_core(ownership, parser, executor, speaker)
    record = core.handle_utterance("volume 60", confidence=0.9)
    assert record is not None
    assert record.executed
    assert executor.calls == [SET_VOLUME]
    assert speaker.spoken == ["Sure. I've set the volume to 60% as requested."]


def test_core_escalation_does_not_execute(
    ownership: AudioOwnershipManager, parser: FastCommandParser
) -> None:
    executor = _FakeExecutor()
    speaker = _FakeSpeaker()
    core = _make_core(ownership, parser, executor, speaker)
    record = core.handle_utterance("I want the best beginner Blender tutorial", confidence=0.9)
    assert record is not None
    assert not record.executed
    assert executor.calls == []
    assert any("Say Jarvis" in s for s in speaker.spoken)


def test_core_missing_param_asks_not_guesses(
    ownership: AudioOwnershipManager, parser: FastCommandParser
) -> None:
    executor = _FakeExecutor()
    speaker = _FakeSpeaker()
    core = _make_core(ownership, parser, executor, speaker)
    record = core.handle_utterance("volume", confidence=0.9)
    assert record is not None
    assert not record.executed
    assert executor.calls == []
    assert any("What volume level" in s for s in speaker.spoken)


def test_core_unknown_phrase_silent(
    ownership: AudioOwnershipManager, parser: FastCommandParser, speaker: _FakeSpeaker
) -> None:
    executor = _FakeExecutor()
    core = _make_core(ownership, parser, executor, speaker)
    record = core.handle_utterance("hello there", confidence=0.9)
    assert record is None
    assert speaker.spoken == []


def test_core_resumes_after_jarvis_release(
    ownership: AudioOwnershipManager, parser: FastCommandParser
) -> None:
    executor = _FakeExecutor()
    speaker = _FakeSpeaker()
    ownership.enter_jarvis()
    core = _make_core(ownership, parser, executor, speaker)
    r1 = core.handle_utterance("volume 60", confidence=0.9)
    assert r1 is None
    assert executor.calls == []
    ownership.release()
    r2 = core.handle_utterance("volume 60", confidence=0.9)
    assert r2 is not None
    assert r2.executed
    assert executor.calls == [SET_VOLUME]


def test_stt_not_ready_without_model(stt: FastCommandSTT) -> None:
    assert not stt.ready
    text, conf = stt.transcribe(b"\x00" * 16000)
    assert text == ""
    assert conf == 0.0