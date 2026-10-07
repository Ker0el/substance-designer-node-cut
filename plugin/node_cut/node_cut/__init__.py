"""Node Cut - gives Substance 3D Designer a real Ctrl+X for graph nodes.

Designer has no cut command and no way to bind one: Preferences > Shortcuts
only covers node *creation* keys, and the graph menu offers Copy, Delete and
"Delete and relink" but no Cut. So this plugin owns the Ctrl+X key and replays
the two keystrokes Designer already understands, in order:

    Ctrl+C     (Designer's own "Copy selection", so the clipboard is filled
                with its native node format and a later Ctrl+V pastes normally)
    Backspace  (Designer's own "Delete and relink", so pulling a node out of
                the middle of a chain leaves that chain wired - undo works as
                usual)

Set CUT_MODE to "delete" to replay Delete instead, which takes the links with
it.

The replay is done with real injected input rather than synthetic events, so
Designer handles it exactly like you typing it. Before the delete key is sent
the plugin waits for the clipboard sequence number to change; if Designer never
wrote to the clipboard, nothing is deleted.
"""

import logging
import os
from functools import partial

import sd
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from sd.api.qtforpythonuimgrwrapper import QtForPythonUIMgrWrapper

from .keys import clipboard_sequence, inject_backspace, inject_ctrl_c, inject_delete

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

SHORTCUT = "Ctrl+X"
SHOW_TOOLBAR_BUTTON = True

# What Ctrl+X leaves behind once the copy has landed:
#   "relink" - replay Backspace, Designer's "Delete and relink". The node goes
#              away but the graph stays wired: whatever fed it now feeds what it
#              used to feed. This is what a cut is usually for - pulling a node
#              out of a chain without having to re-drag two links afterwards.
#   "delete" - replay Delete. The node and its links go together, leaving a gap.
CUT_MODE = "relink"

# "widget" scopes Ctrl+X to the graph view itself: plain text cut keeps working
# while you rename a node or edit a value field. Switch to "window" only if the
# key turns out not to reach the graph view on your build.
SHORTCUT_CONTEXT = "widget"

# Give the user's own key release time to reach the queue first.
PRE_INJECT_DELAY_MS = 40
# How long to wait for Designer to fill the clipboard before giving up.
COPY_TIMEOUT_MS = 2500
POLL_INTERVAL_MS = 25

# Resolved once: CUT_MODE never changes at runtime.
_DELETE_SELECTION = inject_delete if CUT_MODE == "delete" else inject_backspace
_DELETE_SELECTION_NAME = ("Delete" if CUT_MODE == "delete"
                          else "Backspace (delete and relink)")

PLUGIN_NAME = "Node Cut"
PLUGIN_VERSION = "1.0.2"

# ---------------------------------------------------------------------------
# Logging - a file next to the plugin, plus Designer's own runtime log
# ---------------------------------------------------------------------------

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(_PLUGIN_ROOT, "runtime.log")

_logger = None


def getLogger():
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("NodeCut")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    try:
        handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    except Exception:
        pass

    try:
        logger.addHandler(sd.getContext().createRuntimeLogHandler())
    except Exception:
        pass

    _logger = logger
    return logger


# ---------------------------------------------------------------------------
# Icon
# ---------------------------------------------------------------------------

_SCISSORS_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
 fill="none" stroke="#cfcfcf" stroke-width="1.7"
 stroke-linecap="round" stroke-linejoin="round">
  <circle cx="6" cy="18" r="2.8"/>
  <circle cx="6" cy="6" r="2.8"/>
  <line x1="8.5" y1="16.4" x2="20" y2="6.6"/>
  <line x1="8.5" y1="7.6" x2="20" y2="17.4"/>
</svg>"""


def makeScissorsIcon(size=22):
    try:
        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(_SCISSORS_SVG))
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        return QtGui.QIcon(pixmap)
    except Exception:
        return QtGui.QIcon()


# ---------------------------------------------------------------------------
# Plugin state
# ---------------------------------------------------------------------------

_graphViewCreatedCallbackID = 0
# graphViewID -> dict(graphView=..., shortcutAction=..., toolbarAction=...)
_installed = {}
_warnedOnce = False


def _selectionCounts(uiMgrQt, graphViewID):
    """Selected nodes and selected graph objects, counted separately.

    Designer keeps these in two different lists: nodes come from
    getGraphSelectedNodesFromGraphViewID, while comments/frames/navigation
    pins come from getGraphSelectedObjectsFromGraphViewID. Asking only the
    second one reports "nothing selected" for every node selection.
    """
    counts = {}
    for label, getter in (("nodes", "getGraphSelectedNodesFromGraphViewID"),
                          ("objects", "getGraphSelectedObjectsFromGraphViewID")):
        try:
            selection = getattr(uiMgrQt, getter)(graphViewID)
            counts[label] = len(selection) if selection else 0
        except Exception as exc:
            counts[label] = "error: %s" % exc
    return counts


def _warnOnce(mainWindow, message):
    global _warnedOnce
    if _warnedOnce:
        return
    _warnedOnce = True
    try:
        QtWidgets.QMessageBox.warning(mainWindow, PLUGIN_NAME, message)
    except Exception:
        pass


def _focusInside(graphView):
    """True when keyboard focus sits on the graph view or one of its children."""
    try:
        focus = QtWidgets.QApplication.focusWidget()
    except Exception:
        return True
    if focus is None:
        return True
    if focus is graphView:
        return True
    try:
        return graphView.isAncestorOf(focus)
    except Exception:
        return True


def _doCut(*_triggeredArg, graphViewID, mainWindow, uiMgrQt, requireFocus=True):
    """Copy, wait for the clipboard, then delete the selection.

    The delete half is whichever key CUT_MODE picked - Backspace ("delete and
    relink") by default, so the graph stays wired behind the removed node.
    """
    log = getLogger()

    # Only meaningful when the graph view is the thing under the cursor. Qt
    # already blocks this for text fields, this covers the other panels.
    # A toolbar click is an explicit request, so it skips this check.
    entry = _installed.get(graphViewID)
    graphView = entry.get("graphView") if entry else None
    if requireFocus and graphView is not None and not _focusInside(graphView):
        log.debug("Ctrl+X ignored: focus is not inside graph view %s", graphViewID)
        return

    counts = _selectionCounts(uiMgrQt, graphViewID)
    selected = sum(n for n in counts.values() if isinstance(n, int))
    if selected == 0:
        log.debug("Ctrl+X ignored: nothing selected in graph view %s %s",
                  graphViewID, counts)
        return
    log.debug("Ctrl+X: selection in graph view %s %s", graphViewID, counts)

    sequenceBefore = clipboard_sequence()
    injected = inject_ctrl_c()
    log.info("Ctrl+X: copy requested (Ctrl+C injected=%s, clipboard seq=%s)",
             injected, sequenceBefore)

    deadline = QtCore.QElapsedTimer()
    deadline.start()

    def pollForCopy():
        if clipboard_sequence() != sequenceBefore:
            log.info("Ctrl+X: clipboard updated after %d ms -> removing "
                     "selection with %s", deadline.elapsed(),
                     _DELETE_SELECTION_NAME)
            _DELETE_SELECTION()
            return
        if deadline.elapsed() >= COPY_TIMEOUT_MS:
            log.warning(
                "Ctrl+X: Designer did not write to the clipboard within %d ms, "
                "so nothing was deleted (nodes are still there).", COPY_TIMEOUT_MS)
            _warnOnce(mainWindow,
                      "%s\n\n无法复制选中的节点，已取消删除 —— 你的节点还在。\n"
                      "详情见日志：\n%s" % (PLUGIN_NAME, LOG_PATH))
            return
        QtCore.QTimer.singleShot(POLL_INTERVAL_MS, pollForCopy)

    QtCore.QTimer.singleShot(PRE_INJECT_DELAY_MS, pollForCopy)


def _installOnGraphView(graphViewID, uiMgrQt):
    log = getLogger()

    if graphViewID in _installed:
        return
    # Graph types the Python API cannot see (e.g. function graphs) have no
    # current graph, so leave their keys alone.
    if not uiMgrQt.getCurrentGraph():
        log.debug("graph view %s: unsupported type, skipped", graphViewID)
        return

    graphView = uiMgrQt.getGraphView(graphViewID)
    mainWindow = uiMgrQt.getMainWindow()
    if graphView is None or mainWindow is None:
        log.warning("graph view %s: could not resolve widget, skipped", graphViewID)
        return

    # The shortcut lives on the graph view itself, so Ctrl+X keeps doing plain
    # text cut while you are renaming a node or editing a value field.
    shortcutAction = QtGui.QAction(graphView)
    shortcutAction.setObjectName("com.starxcc.nodecut.shortcut")
    shortcutAction.setText(SHORTCUT)
    shortcutAction.setShortcut(QtGui.QKeySequence(SHORTCUT))
    if SHORTCUT_CONTEXT == "widget":
        shortcutAction.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
    else:
        shortcutAction.setShortcutContext(QtCore.Qt.WindowShortcut)
    shortcutAction.triggered.connect(
        partial(_doCut, graphViewID=graphViewID, mainWindow=mainWindow,
                uiMgrQt=uiMgrQt))
    graphView.addAction(shortcutAction)

    toolbarAction = None
    if SHOW_TOOLBAR_BUTTON:
        # A separate action on purpose: two actions sharing one key would trip
        # Qt's ambiguous-shortcut handling.
        toolbarAction = QtGui.QAction(mainWindow)
        toolbarAction.setObjectName("com.starxcc.nodecut.toolbar")
        toolbarAction.setText("Cut")
        toolbarAction.setToolTip("剪切选中的节点 (Ctrl+X)")
        toolbarAction.setIcon(makeScissorsIcon())
        toolbarAction.triggered.connect(
            partial(_doCut, graphViewID=graphViewID, mainWindow=mainWindow,
                    uiMgrQt=uiMgrQt, requireFocus=False))
        try:
            uiMgrQt.addActionToGraphViewToolbar(graphViewID, toolbarAction)
        except Exception:
            log.exception("graph view %s: could not add toolbar button", graphViewID)
            toolbarAction = None

    _installed[graphViewID] = {
        "graphView": graphView,
        "shortcutAction": shortcutAction,
        "toolbarAction": toolbarAction,
    }

    def onDestroyed(*_args, graphViewID=graphViewID):
        _installed.pop(graphViewID, None)

    graphView.destroyed.connect(onDestroyed)
    log.info("graph view %s: Ctrl+X installed", graphViewID)


def _removeAll():
    for entry in list(_installed.values()):
        for key in ("toolbarAction", "shortcutAction"):
            action = entry.get(key)
            if action is not None:
                try:
                    action.setEnabled(False)
                    action.setParent(None)
                    action.deleteLater()
                except Exception:
                    pass
    _installed.clear()


# ---------------------------------------------------------------------------
# Plugin entry points
# ---------------------------------------------------------------------------

def initializeSDPlugin():
    global _graphViewCreatedCallbackID

    log = getLogger()
    app = sd.getContext().getSDApplication()
    uiMgrQt = app.getQtForPythonUIMgr()
    if uiMgrQt is None:
        log.error("%s: Qt UI manager unavailable, plugin disabled", PLUGIN_NAME)
        return

    log.info("=" * 60)
    log.info("%s v%s: initializing (Designer %s, SIG=%r)", PLUGIN_NAME,
             PLUGIN_VERSION, app.getVersion(), SHORTCUT)

    _graphViewCreatedCallbackID = uiMgrQt.registerGraphViewCreatedCallback(
        partial(_installOnGraphView, uiMgrQt=uiMgrQt))

    # Graph views that already exist by the time the plugin loads.
    try:
        uiMgrSd = app.getUIMgr()
        count = uiMgrSd.getGraphViewIDCount()
        for index in range(count):
            _installOnGraphView(uiMgrSd.getGraphViewIDAt(index), uiMgrQt)
    except Exception:
        log.exception("%s: could not enumerate existing graph views", PLUGIN_NAME)


def uninitializeSDPlugin():
    log = getLogger()
    app = sd.getContext().getSDApplication()
    uiMgrQt = app.getQtForPythonUIMgr()

    log.info("%s: uninitializing", PLUGIN_NAME)

    if uiMgrQt is not None and _graphViewCreatedCallbackID:
        try:
            uiMgrQt.unregisterCallback(_graphViewCreatedCallbackID)
        except Exception:
            pass
    _removeAll()
