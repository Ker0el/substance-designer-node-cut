"""Offline smoke test for the Node Cut plugin.

Runs the plugin's Qt wiring against Designer's own embedded Python + PySide6,
with a stub `sd` module, so obvious mistakes surface without restarting
Designer. It never injects keystrokes into Designer.

    "E:\\3D\\Adobe Substance 3D Designer\\plugins\\pythonsdk\\python.exe" smoke_test.py
"""
import logging
import os
import sys
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

    def getCurrentGraph(self):
        return object()

    def getGraphView(self, graphViewID):
        return self.graphView

    def getMainWindow(self):
        return self.mainWindow

    def getGraphSelectedNodesFromGraphViewID(self, graphViewID):
        return [object(), object()]

    def getGraphSelectedObjectsFromGraphViewID(self, graphViewID):
        # Designer reports nodes and graph objects separately; a plain node
        # selection shows up only in the *nodes* list.
        return []

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

uiMgrQt.mainWindow.close()

print()
if failures:
    print("FAILED: %d" % len(failures))
    for name in failures:
        print("   - %s" % name)
    sys.exit(1)
print("all checks passed")
