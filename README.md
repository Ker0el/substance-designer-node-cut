# Node Cut — Ctrl+X for Substance 3D Designer

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![Designer](https://img.shields.io/badge/Substance%203D%20Designer-14.1%2B-orange.svg)

**English** · [中文](#中文)

> Substance 3D Designer has no Cut command for graph nodes — `Ctrl+X` does nothing, and
> Preferences → Shortcuts can only bind *node creation* keys. This plugin gives `Ctrl+X`
> the standard copy-then-delete behaviour by replaying Designer's own `Ctrl+C` followed by
> its own `Delete`, so the clipboard ends up in Designer's native node format and
> `Ctrl+V` / `Ctrl+Z` behave exactly as usual.

![The Node Cut button in the graph view toolbar](docs/graph-toolbar.png)

*装上之后图形视图工具栏里会多一个剪刀按钮（红框），悬停显示「剪切选中的节点 (Ctrl+X)」。*

---

## 中文

### 为什么需要它

Substance 3D Designer 的图形视图**没有剪切**，这不是没找到，是三处都没有：

| 查的地方 | 结果 |
|---|---|
| 官方快捷键表，Graph View → When an object is selected | 只有 Copy / Duplicate / Duplicate without links / Delete / Backspace / Dock / Disable，**没有 Cut** |
| 图形视图右键菜单 | `Copy selection`、`Delete selection`、`Delete and relink`（这个是 Backspace）、`Duplicate selection`，**没有 Cut** |
| `Edit → Preferences → Shortcuts` | 只能给「创建节点」绑键（比如给 Blur 绑 B），图操作一个都绑不了 |

（右键菜单是从 `Adobe Substance 3D Designer.exe` 里把字符串挖出来确认的，仓库里的
`tools/exe_strings.py` 就是当时用的工具。另外 Designer 里确实存在 `Cut Selection` 这两个串，
但那属于 2D 视图的 SVG 工具，跟节点无关。）

所以「剪切」只能自己拼：`Ctrl+C` 然后 `Delete`。这个插件就是把这两步接到 `Ctrl+X` 上。

### 安装

**要求**：Windows，Substance 3D Designer 14.1 或更新。

1. 把 `plugin/node_cut` 整个文件夹拷到 Designer 的用户插件目录：

   ```
   %USERPROFILE%\Documents\Adobe\Adobe Substance 3D Designer\python\sduserplugins\
   ```

   拷完的路径应该是这样（`pluginInfo.json` 必须正好在 `node_cut` 这一层）：

   ```
   ...\sduserplugins\node_cut\pluginInfo.json
   ...\sduserplugins\node_cut\node_cut\__init__.py
   ```

2. **完全退出并重启 Designer。**

   Designer 只在启动时扫一次插件目录。装之前请先存盘。

3. 打开任意一个 Substance 图形，工具栏末尾应该多出一个**剪刀按钮**。看到它就说明插件加载成功了。

如果你是从仓库直接用的，也可以跑脚本自动部署：

```
python install.py
```

它会把 `plugin/node_cut` 拷到上面那个目录，并提示你是否需要重启 Designer。
（`install.py` 会去注册表读 Documents 的真实位置，所以 Documents 改过路径也能用。）

### 使用

| 操作 | 结果 |
|---|---|
| 选中节点 → `Ctrl+X` | 节点被剪走（在剪贴板里） |
| `Ctrl+V` | 贴回来，落在鼠标位置 |
| `Ctrl+Z` | 一步撤销整个剪切 |
| 重命名节点 / 编辑数值框时 `Ctrl+X` | **还是正常的文本剪切**，不会去删节点 |

`Ctrl+X` 的快捷键只挂在图形视图上，焦点在资源管理器或属性面板时不会误触。
（这一条有测试守着，见下面的「开发」。）

### 工作原理

Designer 自己是有「复制」和「删除」的 —— 插件做的是把这两个动作按顺序替用户按一遍：

```
Ctrl+X  →  按一次 Ctrl+C  →  等剪贴板真的被写入  →  按一次 Delete
```

关键在于**没有自己实现节点复制粘贴**，也没有碰 Designer 的任何内部状态。走的是
Windows 标准的键盘输入通道，Designer 收到的是正常按键，因此用的还是它自己原本的逻辑：

- 复制：剪贴板里是 Designer 原生的节点格式，所以 `Ctrl+V` 能正常粘贴，跨窗口、跨 Designer 实例也都成立。
- 删除：Designer 自己的「Delete selection」命令，所以撤销行为和手动删一模一样。

插件没有自己序列化节点，也没有替换任何文件。

两次按键按顺序进入事件队列，**顺序有保证** —— 复制一定发生在删除之前。

### 它不会删掉你复制不出来的东西

发出 `Ctrl+C` 之后，插件会盯着 Windows 的**剪贴板序号**。只有确认 Designer 真的往剪贴板写了东西，
才会按下 `Delete`；超时没等到就**什么都不删**，节点原样保留，同时弹一次提示并写进日志。

所以要出问题也只会是「按了没反应」，不会变成「节点没了但剪贴板是空的」。

### 设置

都在 `plugin/node_cut/node_cut/__init__.py` 顶部，改完重新部署 + 重启 Designer：

| 常量 | 默认 | 作用 |
|---|---|---|
| `SHORTCUT` | `"Ctrl+X"` | 想换别的键改这里。 |
| `SHORTCUT_CONTEXT` | `"widget"` | `"widget"` = 只有焦点在图形视图里才响应；改成 `"window"` 则整个 Designer 窗口内都响应。 |
| `SHOW_TOOLBAR_BUTTON` | `True` | 改成 `False` 就不往工具栏加剪刀按钮。 |
| `PRE_INJECT_DELAY_MS` | `40` | 按下 Ctrl+C 之前先等一会儿，让用户自己的按键先落地。 |
| `COPY_TIMEOUT_MS` | `2500` | 等剪贴板写入的超时时间。 |

### 日志与排查

每次加载、每次 `Ctrl+X` 都会写日志：

```
%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Designer\python\sduserplugins\node_cut\runtime.log
```

正常一次剪切：

```
[INFO]  Node Cut v1.0.1: initializing (Designer 16.0.6, SIG='Ctrl+X')
[INFO]  graph view 6191864352: Ctrl+X installed
[DEBUG] Ctrl+X: selection in graph view 6191864352 {'nodes': 1, 'objects': 0}
[INFO]  Ctrl+X: copy requested (Ctrl+C injected=4, clipboard seq=18625)
[INFO]  Ctrl+X: clipboard updated after 57 ms -> deleting
```

| 日志里看到 | 说明 | 怎么办 |
|---|---|---|
| 完全没有 `initializing` | 插件没被加载 | 检查 `pluginInfo.json` 是不是正好在 `sduserplugins\node_cut\` 这一层，路径多一层就扫不到 |
| `nothing selected` | 快捷键到了，但 Designer 认为没选中东西 | 先在图形视图里点一下节点再按 |
| `Designer did not write to the clipboard` | 复制没成功，已取消删除 | 见下 |
| 日志是空的 / 没有启动记录 | 没重启 Designer | 完全退出再开 |

最后一种如果反复出现，把 `runtime.log` 发到 Issues。

### 兼容性

- 测试环境：Windows 11 + Substance 3D Designer 16.0.6。
- 插件只用了 14.1 起就有的 Python API（`registerGraphViewCreatedCallback` /
  `getGraphView` / `addActionToGraphViewToolbar` / `getGraphSelectedNodesFromGraphViewID`），
  和 Adobe 自带的「节点对齐工具」用的是同一套。
- **只对 Substance 图形生效**。函数图（Substance function graph）和 FX-Map 里 Python API
  取不到当前图形，插件会主动跳过，不接管那里的按键。
- 只支持 Windows（用的是 Win32 `SendInput`）。

### 卸载

删掉这个目录就干净了，Designer 本身一个字节都没被改过：

```
%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Designer\python\sduserplugins\node_cut\
```

删完重启 Designer 即恢复原样。

### 仓库结构

```
plugin/node_cut/          插件本体，拷进 sduserplugins 的就是这个文件夹
    pluginInfo.json       插件元数据
    node_cut/__init__.py  插件主体：绑快捷键、选中判定、复制-等待-删除流程
    node_cut/keys.py      Windows 键盘输入 + 剪贴板序号
    makepackage.py        打 .sdplugin 包用（Adobe 官方模板原样）
install.py                把插件部署到 sduserplugins
tools/smoke_test.py       离线自测，不需要启动 Designer
tools/exe_strings.py      从 Designer.exe 里挖菜单字符串（当初用来确认没有 Cut）
docs/graph-toolbar.png    README 配图
```

### 开发

**离线自测**（用 Designer 自带的 Python，不需要 Designer 在跑，也不会真的按任何键）：

```
"<Designer安装目录>\plugins\pythonsdk\python.exe" tools/smoke_test.py
```

覆盖 16 项：图标渲染、QAction 绑定与作用域、焦点判定、剪贴板序号、
以及两条关键假设 —— 「行编辑框会抢走 Ctrl+X（所以重命名时不会误删节点）」
和「节点选中必须从 nodes 列表读，不能从 objects 列表读」。

用别的 Python 跑也行，设一下 `DESIGNER_ROOT` 环境变量指到 Designer 安装目录即可。

**打包成 `.sdplugin`**：

```
cd plugin/node_cut && python makepackage.py   # 产物在 build/
```

---

## English

Substance 3D Designer has no Cut for graph nodes. The official shortcut list has
`Copy` / `Delete` / `Delete and relink` but no `Cut`, and `Edit → Preferences → Shortcuts`
only lets you bind *node creation* keys — graph operations cannot be bound at all.

This plugin gives `Ctrl+X` the standard copy-then-delete behaviour.

**How it works** — it does not reimplement node copy/paste. It replays a `Ctrl+C` followed
by a `Delete`, so Designer's own copy and delete commands run: the clipboard ends up in
Designer's native node format (so `Ctrl+V` pastes normally, even across Designer
instances), and `Ctrl+Z` undoes the whole cut in one step. Nothing inside Designer is
modified.

**Safety** — the plugin only sends `Delete` after Windows' clipboard sequence number
confirms Designer actually wrote to the clipboard. If the copy fails, nothing is deleted.

**Install** (Windows, Designer 14.1+)

1. Copy `plugin/node_cut` into
   `%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Designer\python\sduserplugins\`
   so that the file ends up at `...\sduserplugins\node_cut\pluginInfo.json`.
2. Fully restart Designer — the plugin folder is only scanned at startup.
3. A scissors button appears at the end of the graph view toolbar when it has loaded.

Or run `python install.py`, which deploys it and locates your real Documents folder.

**Usage** — select nodes, press `Ctrl+X`, paste with `Ctrl+V`, undo with `Ctrl+Z`.
The shortcut is scoped to the graph view, so `Ctrl+X` still cuts *text* while you
rename a node or edit a value field.

**Log** — `...\sduserplugins\node_cut\runtime.log` records every load and every cut;
please attach it to bug reports.

## License

MIT — see [LICENSE](LICENSE).
