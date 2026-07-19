"""Shared test helpers for Sequin's UI suites.

Kept here rather than copied per module: the pattern editor and the beat editor both drive
EVT_CHAR_HOOK directly, and two copies of the same fake key event is exactly the kind of
duplicate that silently drifts apart.
"""


class Key:
    """A stand-in for wx.KeyEvent, enough for the dialogs' EVT_CHAR_HOOK handlers.

    The grid dialogs own their keys through a char hook (a dialog eats Enter and Space
    before a child's own key handler ever runs), so the tests call those handlers directly
    with this instead of trying to synthesise real wx events.
    """

    def __init__(self, code, ctrl=False, shift=False, alt=False):
        self._code, self._ctrl, self._shift, self._alt = code, ctrl, shift, alt

    def GetKeyCode(self):
        return self._code

    def ControlDown(self):
        return self._ctrl

    def ShiftDown(self):
        return self._shift

    def AltDown(self):
        return self._alt

    def Skip(self):
        pass
