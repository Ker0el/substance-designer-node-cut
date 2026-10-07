"""Win32 helpers: keyboard injection and clipboard sequence probing.

The plugin replays the two keystrokes Designer already understands (Ctrl+C plus
a delete key) instead of reimplementing node copy/paste. Injected input goes
through the normal system input queue, so Designer handles them exactly as if
you had typed them yourself - same clipboard format, same undo behaviour.

The delete half is Backspace, which Designer binds to "Delete and relink": the
node goes away but its primary input connection is carried across, so pulling a
node out of the middle of a chain leaves the chain wired. Delete - which
removes the links with it - is kept here for the plugin's CUT_MODE = "delete".

Input events are inserted into the queue in order, so a batch is processed
before anything sent in a later batch. That is what lets us guarantee the copy
happens before the delete.
"""
import ctypes
import time
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

VK_CONTROL = 0x11
VK_DELETE = 0x2E
VK_BACK = 0x08
VK_C = 0x43


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
# legacy fallback, still honoured by every Windows version
_user32.keybd_event.argtypes = (wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_void_p)


def _key(vk, up=False, extended=False):
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)
    return inp


def _send(seq):
    """seq: list of (vk, up, extended). Returns events injected, or -2 if the
    SendInput path failed and the legacy keybd_event fallback was used."""
    if not seq:
        return 0
    arr = (_INPUT * len(seq))(*(_key(vk, up, ext) for vk, up, ext in seq))
    try:
        n = int(_user32.SendInput(len(seq), arr, ctypes.sizeof(_INPUT)))
    except Exception:
        n = 0
    if n == len(seq):
        return n
    # Fall back to the legacy API - same effect, no struct layout involved.
    try:
        for vk, up, ext in seq:
            flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if ext else 0)
            _user32.keybd_event(vk, 0, flags, None)
    except Exception:
        return -1
    return -2


def inject_ctrl_c():
    """Ctrl down, C down, C up, Ctrl up.

    Self contained on purpose: whatever the physical Ctrl key happens to be
    doing, the C press is seen as Ctrl+C, and Ctrl is left logically released
    afterwards so our later Delete is not read as Ctrl+Delete.
    """
    return _send([
        (VK_CONTROL, False, False),
        (VK_C, False, False),
        (VK_C, True, False),
        (VK_CONTROL, True, False),
    ])


def inject_delete():
    """Delete - removes the selection along with its links.

    Delete is an extended key, so it needs KEYEVENTF_EXTENDEDKEY; without that
    flag it arrives as the numpad Delete on some layouts.
    """
    return _send([
        (VK_DELETE, False, True),
        (VK_DELETE, True, True),
    ])


def inject_backspace():
    """Backspace - Designer's "Delete and relink".

    The node goes away but its primary input connection is carried over to
    whatever it was feeding. Unlike Delete this is not an extended key, so the
    flag stays off.
    """
    return _send([
        (VK_BACK, False, False),
        (VK_BACK, True, False),
    ])


def clipboard_sequence():
    """Windows bumps this every time the clipboard is written to.

    Comparing it before/after the injected Ctrl+C tells us whether Designer
    really put something on the clipboard, so we never delete nodes we failed
    to copy.
    """
    try:
        return int(_user32.GetClipboardSequenceNumber())
    except Exception:
        return 0


def sleep(seconds):
    time.sleep(seconds)
