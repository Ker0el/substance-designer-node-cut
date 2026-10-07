"""Deploy the Node Cut plugin into Substance Designer's user plugin folder.

    python install.py

Designer only scans that folder at startup, so Designer has to be restarted
for the plugin to load (or for a re-deploy to take effect).
"""
import os
import shutil
import subprocess
import sys

PLUGIN_NAME = "node_cut"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "plugin", PLUGIN_NAME)
DESIGNER_EXE = r"E:\3D\Adobe Substance 3D Designer\Adobe Substance 3D Designer.exe"


def user_plugin_dir():
    """.../Documents/Adobe/Adobe Substance 3D Designer/python/sduserplugins

    The Documents folder can be redirected, so ask the shell where it really
    is instead of assuming %USERPROFILE%\\Documents.
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        personal, _ = winreg.QueryValueEx(key, "Personal")
        winreg.CloseKey(key)
        personal = os.path.expandvars(personal)
        if os.path.isdir(personal):
            return os.path.join(personal, "Adobe", "Adobe Substance 3D Designer",
                                "python", "sduserplugins")
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents", "Adobe",
                        "Adobe Substance 3D Designer", "python", "sduserplugins")


def designer_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Adobe Substance 3D Designer.exe",
             "/FO", "CSV", "/NH"],
            capture_output=True, text=True).stdout
        return "Adobe Substance 3D Designer.exe" in out
    except Exception:
        return False


def main():
    if not os.path.isdir(SRC):
        print("source plugin folder not found: %s" % SRC)
        return 1

    target_root = user_plugin_dir()
    target = os.path.join(target_root, PLUGIN_NAME)
    os.makedirs(target_root, exist_ok=True)

    if os.path.isdir(target):
        # Designer keeps runtime.log open while it is running, so a plain
        # rmtree would fail on it; that file is regenerated anyway.
        shutil.rmtree(target, ignore_errors=True)
        if os.path.isdir(target):
            stuck = [name for name in os.listdir(target)
                     if os.path.isfile(os.path.join(target, name))]
            if stuck:
                print("note: Designer is holding %s - it will be recreated on "
                      "the next run" % ", ".join(stuck))
    os.makedirs(target, exist_ok=True)
    shutil.copytree(SRC, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "runtime.log"))

    print("installed: %s" % target)
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            print("    %s" % os.path.relpath(os.path.join(root, name), target))

    if designer_running():
        print()
        print("Designer is running - restart it, the plugin folder is only "
              "scanned at startup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
