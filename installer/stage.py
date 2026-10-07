"""把插件里「运行时要的」文件挑到 payload\\ 下 —— 安装包的 [Files] 只认 payload\\。

为什么要多这一步：Inno 的 [Files] 是一条条列出来的，插件那边加了新文件忘了同步，
**装出来的版本就会少文件，而本地开发树一切正常** —— 这类问题最难查
（Nuke 那份就栽过：两边都漏了 shortcut.txt，只有装出来的版本按快捷键没反应）。
所以这里整目录复制 + 排除开发文件，复制完把清单打出来，方便和 [Files] 对照。

[Files] 那边对 node_cut\\ 用的是 `*.py` 通配，所以**新增 python 模块不用改 [Files]**；
只有新增顶层文件/目录才要动它。

用法：
    python stage.py
"""
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "plugin", "node_cut")
DST = os.path.join(HERE, "payload", "node_cut")

# 开发用的东西，不进安装包
EXCLUDE_FILES = {".sdpackageignore", "makepackage.py", "runtime.log"}
EXCLUDE_DIRS = {"build", "__pycache__"}
EXCLUDE_EXT = {".pyc"}


def keep(name):
    if name in EXCLUDE_FILES or name.endswith(".pyc"):
        return False
    return os.path.splitext(name)[1] not in EXCLUDE_EXT


def main():
    if not os.path.isdir(SRC):
        print("找不到插件源目录：%s" % SRC)
        return 1

    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST)

    count = 0
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel = os.path.relpath(root, SRC)
        target = DST if rel == "." else os.path.join(DST, rel)
        os.makedirs(target, exist_ok=True)
        for name in sorted(files):
            if not keep(name):
                continue
            shutil.copy2(os.path.join(root, name), os.path.join(target, name))
            count += 1

    print("payload 就绪：%s" % DST)
    for root, dirs, files in os.walk(DST):
        dirs[:] = sorted(dirs)
        for name in sorted(files):
            full = os.path.join(root, name)
            print("    %-46s %6d 字节" % (os.path.relpath(full, DST), os.path.getsize(full)))

    # 装到用户机上以后，插件必须能在这两个位置找到东西
    must = [
        os.path.join(DST, "pluginInfo.json"),
        os.path.join(DST, "node_cut", "__init__.py"),
        os.path.join(DST, "node_cut", "keys.py"),
    ]
    missing = [p for p in must if not os.path.isfile(p)]
    if missing:
        print("\n缺少必需文件，安装包会装不完整：")
        for p in missing:
            print("    %s" % os.path.relpath(p, DST))
        return 1

    print("\n%d 个文件" % count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
