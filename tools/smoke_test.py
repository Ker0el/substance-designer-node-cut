"""Offline smoke test for the Node Cut plugin.

Runs the plugin's Qt wiring against Designer's own embedded Python + PySide6,
with a stub `sd` module, so obvious mistakes surface without restarting
Designer. It never injects keystrokes into Designer.

    "E:\\3D\\Adobe Substance 3D Designer\\plugins\\pythonsdk\\python.exe" smoke_test.py
"""
import logging
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_PARENT = os.path.join(os.path.dirname(HERE), "plugin", "node_cut")


def designer_root_from_interpreter():
    """<root>\\plugins\\pythonsdk\\python.exe  ->  <root>"""
    pythonsdk = os.path.dirname(os.path.abspath(sys.executable))
    if os.path.basename(pythonsdk).lower() != "pythonsdk":
        return None
    plugins = os.path.dirname(pythonsdk)
    if os.path.basename(plugins).lower() != "plugins":
        return None
    return os.path.dirname(plugins)


DESIGNER_ROOT = os.environ.get("DESIGNER_ROOT") or designer_root_from_interpreter()
if not DESIGNER_ROOT or not os.path.isfile(os.path.join(DESIGNER_ROOT, "Qt6Core.dll")):
    sys.exit(
        "Run this with Designer's bundled interpreter, e.g.\n"
        '  "<Designer>\\plugins\\pythonsdk\\python.exe" %s\n'
        "or point DESIGNER_ROOT at your Designer install folder." % os.path.basename(__file__))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, PLUGIN_PARENT)

# Designer keeps the Qt6 DLLs in its own root rather than a PySide6/bin folder,
# so they have to be on the DLL search path before PySide6 will import.
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(DESIGNER_ROOT)
    os.add_dll_directory(os.path.join(DESIGNER_ROOT, "plugins", "pythonsdk"))
    os.add_dll_directory(os.path.join(DESIGNER_ROOT, "plugins", "pythonsdk", "DLLs"))


# ---------------------------------------------------------------------------
# Stub the `sd` module the plugin imports
# ---------------------------------------------------------------------------

class _FakeContext(object):
    def createRuntimeLogHandler(self):
        return logging.NullHandler()


sd_stub = types.ModuleType("sd")
sd_stub.getContext = lambda: _FakeContext()
sys.modules["sd"] = sd_stub

sd_api = types.ModuleType("sd.api")
sys.modules["sd.api"] = sd_api

wrapper_mod = types.ModuleType("sd.api.qtforpythonuimgrwrapper")


class QtForPythonUIMgrWrapper(object):
    """Only used for the type annotation, never instantiated here."""


wrapper_mod.QtForPythonUIMgrWrapper = QtForPythonUIMgrWrapper
sys.modules["sd.api.qtforpythonuimgrwrapper"] = wrapper_mod

# ---------------------------------------------------------------------------

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

app = QtWidgets.QApplication(sys.argv)

import node_cut  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print("%-58s %s%s" % (name, "OK" if condition else "FAIL",
                          "" if condition else "   <- " + str(detail)))
    if not condition:
        failures.append(name)


# --- icon ------------------------------------------------------------------
icon = node_cut.makeScissorsIcon()
check("scissors icon renders", not icon.isNull() and not icon.pixmap(22, 22).isNull())


# --- fake graph view + fake ui manager -------------------------------------
class FakeUIMgrQt(object):
    def __init__(self):
        self.mainWindow = QtWidgets.QMainWindow()
        self.graphView = QtWidgets.QWidget(self.mainWindow)
        self.canvas = QtWidgets.QWidget(self.graphView)
        self.lineEdit = QtWidgets.QLineEdit(self.graphView)
        self.lineEdit.setText("rename me")
        self.toolbarCalls = []
        # Designer reports nodes and graph objects in two separate lists.
        self.selectedNodes = [object(), object()]
        self.selectedObjects = []

    def getCurrentGraph(self):
        return object()

    def getGraphView(self, graphViewID):
        return self.graphView

    def getMainWindow(self):
        return self.mainWindow

    def getGraphSelectedNodesFromGraphViewID(self, graphViewID):
        return self.selectedNodes

    def getGraphSelectedObjectsFromGraphViewID(self, graphViewID):
        # A plain node selection shows up only in the *nodes* list.
        return self.selectedObjects

    def addActionToGraphViewToolbar(self, graphViewID, action):
        self.toolbarCalls.append(action)


uiMgrQt = FakeUIMgrQt()
node_cut._installOnGraphView(7, uiMgrQt)

entry = node_cut._installed.get(7)
check("graph view registered", entry is not None)
check("toolbar action handed to Designer", len(uiMgrQt.toolbarCalls) == 1)

action = entry["shortcutAction"] if entry else None
check("action shortcut is Ctrl+X",
      action is not None and action.shortcut() == QtGui.QKeySequence("Ctrl+X"))
check("action owned by graph view",
      action is not None and action.parent() is uiMgrQt.graphView)
check("shortcut scoped to graph view",
      action is not None and action.shortcutContext() == QtCore.Qt.WidgetWithChildrenShortcut)

# The plugin must not have touched anything Designer-level yet.
check("no injection happened at install time", len(node_cut._installed) == 1)

# Regression: Designer reports nodes and graph objects in two separate lists.
# A plain node selection must not read as "nothing selected".
counts = node_cut._selectionCounts(uiMgrQt, 7)
check("node-only selection is counted",
      counts.get("nodes") == 2 and counts.get("objects") == 0, counts)


# --- focus guard ------------------------------------------------------------
# focusWidget() only tracks anything once a window is actually shown/active,
# otherwise it returns None (and _focusInside deliberately treats that as
# "cannot tell, do not block").
uiMgrQt.mainWindow.show()
try:
    app.setActiveWindow(uiMgrQt.mainWindow)
except Exception:
    pass
app.processEvents()
print("      [debug] focusWidget after show = %r"
      % QtWidgets.QApplication.focusWidget())

check("_focusInside(True) when nothing focused", node_cut._focusInside(uiMgrQt.graphView))

uiMgrQt.canvas.setFocus()
app.processEvents()
check("_focusInside(True) for a child widget", node_cut._focusInside(uiMgrQt.graphView))

# A focusable widget that lives outside the graph view (e.g. the Explorer).
outside = QtWidgets.QLineEdit(uiMgrQt.mainWindow)
outside.show()
outside.setFocus()
app.processEvents()
print("      [debug] focusWidget with outside focused = %r"
      % QtWidgets.QApplication.focusWidget())
check("_focusInside(False) for a widget outside the graph view",
      not node_cut._focusInside(uiMgrQt.graphView))


# --- the assumption the whole design rests on -------------------------------
# Qt lets a focused text widget claim Ctrl+X via ShortcutOverride. That is what
# keeps our global-ish shortcut from hijacking "cut this text" while renaming a
# node. Verified here directly instead of with QTest, which Adobe strips out.
uiMgrQt.lineEdit.setText("rename me")
uiMgrQt.lineEdit.setFocus()

override = QtGui.QKeyEvent(QtCore.QEvent.ShortcutOverride, QtCore.Qt.Key_X,
                           QtCore.Qt.ControlModifier)
QtWidgets.QApplication.sendEvent(uiMgrQt.lineEdit, override)
check("line edit claims Ctrl+X (text cut wins over the plugin)", override.isAccepted())

# ...and a plain widget does NOT claim it, so the shortcut is free to fire.
plain = QtWidgets.QWidget(uiMgrQt.graphView)
plain.setFocus()
override2 = QtGui.QKeyEvent(QtCore.QEvent.ShortcutOverride, QtCore.Qt.Key_X,
                            QtCore.Qt.ControlModifier)
QtWidgets.QApplication.sendEvent(plain, override2)
check("plain graph canvas does not claim Ctrl+X", not override2.isAccepted())

# The action really is reachable from the graph view's action list, which is
# what Qt walks when resolving the shortcut.
check("action is attached to the graph view widget",
      action is not None and action in uiMgrQt.graphView.actions())


# --- keys helper ------------------------------------------------------------
from node_cut import keys  # noqa: E402

seq = keys.clipboard_sequence()
check("clipboard_sequence() returns a number", isinstance(seq, int) and seq > 0, seq)
check("empty injection is a no-op", keys._send([]) == 0)


# --- what Ctrl+X injects after the copy -------------------------------------
# The delete half has to be Backspace: that is the key Designer binds to
# "Delete and relink", so the chain behind the removed node stays connected.
# Capture the sequences instead of sending them.
captured = []
originalSend = keys._send
keys._send = lambda sequence: captured.append(sequence) or 0
try:
    keys.inject_backspace()
    keys.inject_delete()
    keys.inject_ctrl_release()
finally:
    keys._send = originalSend

check("backspace is down/up and NOT an extended key",
      captured[0] == [(keys.VK_BACK, False, False), (keys.VK_BACK, True, False)],
      captured[0])
check("delete is down/up and flagged extended",
      captured[1] == [(keys.VK_DELETE, False, True), (keys.VK_DELETE, True, True)],
      captured[1])
check("ctrl release is a lone Ctrl-up",
      captured[2] == [(keys.VK_CONTROL, True, False)], captured[2])
check("default CUT_MODE resolves to Backspace (delete and relink)",
      node_cut.CUT_MODE == "relink"
      and node_cut._DELETE_SELECTION is keys.inject_backspace,
      "%s -> %s" % (node_cut.CUT_MODE, node_cut._DELETE_SELECTION_NAME))


# --- selected links ---------------------------------------------------------
# Designer's Python API cannot describe a selected connection - SDGraphObject
# is documented as "an object in a graph that is neither a node nor a
# connection". A wire selection therefore looks like an empty selection up
# there, and has to be picked up from Qt instead. Both routes are checked: the
# scene probe, and the fallback for when the probe cannot reach a scene (links
# must keep working there too).
def spin(milliseconds):
    deadline = time.time() + milliseconds / 1000.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)


class FakeScene(object):
    def __init__(self):
        self.items = []

    def selectedItems(self):
        return self.items


class FakeSceneView(QtWidgets.QWidget):
    """A graph view whose scene can be queried, like Designer's own."""

    def __init__(self, parent=None):
        super(FakeSceneView, self).__init__(parent)
        self._scene = FakeScene()

    def scene(self):
        return self._scene


check("scene probe on None is 'cannot tell'", node_cut._sceneSelectedCount(None) is None)
check("scene probe on a plain widget is 'cannot tell'",
      node_cut._sceneSelectedCount(QtWidgets.QWidget()) is None)

sceneView = FakeSceneView(uiMgrQt.mainWindow)
check("scene probe reads an empty scene", node_cut._sceneSelectedCount(sceneView) == 0)
sceneView._scene.items.append(object())
check("scene probe counts selected items", node_cut._sceneSelectedCount(sceneView) == 1)

linkView = FakeSceneView(uiMgrQt.mainWindow)
plainView = QtWidgets.QWidget(uiMgrQt.mainWindow)
node_cut._installed[99] = {"graphView": linkView, "shortcutAction": None, "toolbarAction": None}
node_cut._installed[98] = {"graphView": plainView, "shortcutAction": None, "toolbarAction": None}

injected = []
originalSend = keys._send
keys._send = lambda sequence: injected.append(sequence) or 0
try:
    uiMgrQt.selectedNodes = []
    uiMgrQt.selectedObjects = []

    # Nothing selected anywhere - the graph must be left alone.
    node_cut._doCut(graphViewID=99, mainWindow=uiMgrQt.mainWindow,
                    uiMgrQt=uiMgrQt, requireFocus=False)
    spin(150)
    check("empty scene selection injects nothing", injected == [], injected)

    # A wire is selected: the API sees no nodes, Qt sees one selected item.
    # Ctrl has to be released first, or the Delete lands as Ctrl+Delete, which
    # Designer ignores - that is what the user is still holding from Ctrl+X.
    linkView._scene.items.append(object())
    node_cut._doCut(graphViewID=99, mainWindow=uiMgrQt.mainWindow,
                    uiMgrQt=uiMgrQt, requireFocus=False)
    spin(150)
    check("a selected connection releases Ctrl, then injects a plain Delete",
          injected == [[(keys.VK_CONTROL, True, False)],
                       [(keys.VK_DELETE, False, True), (keys.VK_DELETE, True, True)]],
          injected)

    # No reachable scene: still attempt the delete rather than bailing out.
    injected[:] = []
    node_cut._doCut(graphViewID=98, mainWindow=uiMgrQt.mainWindow,
                    uiMgrQt=uiMgrQt, requireFocus=False)
    spin(150)
    check("view without a scene still attempts Delete",
          len(injected) == 2 and injected[1][0][0] == keys.VK_DELETE, injected)
finally:
    keys._send = originalSend
    node_cut._installed.pop(99, None)
    node_cut._installed.pop(98, None)
    uiMgrQt.selectedNodes = [object(), object()]

uiMgrQt.mainWindow.close()

print()
if failures:
    print("FAILED: %d" % len(failures))
    for name in failures:
        print("   - %s" % name)
    sys.exit(1)
print("all checks passed")
