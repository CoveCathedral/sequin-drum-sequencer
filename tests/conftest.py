"""Shared fixtures for Sequin's UI tests.

One wx.App is created here for the whole suite — several test modules drive real dialogs,
and constructing a second wx.App would break them. If no display is available the UI
modules skip rather than fail, so the engine tests still run on a headless machine.
"""

import pytest

wx = pytest.importorskip("wx")

try:
    _APP = wx.App(False)
except Exception:  # pragma: no cover - no GUI available
    _APP = None


@pytest.fixture(scope="session", autouse=True)
def _require_display():
    if _APP is None:  # pragma: no cover - headless
        pytest.skip("no wx display available", allow_module_level=True)


@pytest.fixture(autouse=True)
def _silence_audio(monkeypatch):
    """No spoken output during tests, and stop any looping sound afterwards.

    Yields the list of spoken strings, so a test can assert on what NVDA would have said —
    the accessibility contract is 'every action speaks', so that list is the assertion
    surface for most of these tests.
    """
    from sequin.ui import speech
    spoken: list[str] = []
    monkeypatch.setattr(speech, "speak",
                        lambda text, interrupt=True: spoken.append(text))
    yield spoken
    try:
        import winsound
        winsound.PlaySound(None, 0)
    except Exception:  # pragma: no cover - non-Windows / no audio
        pass


@pytest.fixture()
def frame(tmp_path, monkeypatch):
    """A real SequinFrame with its settings file isolated to tmp_path."""
    import sequin.config as cfg
    from sequin.app import SequinFrame
    monkeypatch.setattr(cfg, "_config_dir", lambda app_name="Sequin": tmp_path)
    f = SequinFrame()
    yield f
    # Deterministic teardown: stop audio/timers, then flush the deferred Destroy so native
    # resources are freed between tests (there is no running event loop to process them).
    f.drums.dispose()
    f.metronome.dispose()
    f.Destroy()
    wx.SafeYield()


@pytest.fixture()
def drums(frame):
    """The Sequin (drums) panel — the subject of most UI tests."""
    return frame.drums
