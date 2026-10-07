# Node Cut

**A `Ctrl+X` cut for Substance 3D Designer.**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![Designer](https://img.shields.io/badge/Substance%203D%20Designer-14.1%2B-orange.svg)

**English** · [中文](README.md)

![The scissors button in the graph view toolbar](docs/graph-toolbar.png)

Substance 3D Designer has no Cut command for graph nodes — `Ctrl+X` does nothing, and the
shortcut editor only lets you bind *node creation* keys. This plugin turns `Ctrl+X` into
copy-then-delete.

## Install

Download **`NodeCut-Setup_v1.0.1.exe`** from
[Releases](https://github.com/Ker0el/substance-designer-node-cut/releases) and run it —
click Next a few times, there is **no folder to pick**, it finds the right one itself.

> ⚠️ **Designer has to be restarted afterwards** — the plugin folder is only scanned at
> startup.
>
> Open any Substance graph; a scissors button at the end of the toolbar means it loaded.

Installing by hand works too: copy the `plugin/node_cut` folder into
`%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Designer\python\sduserplugins\`
(the result must be `...\sduserplugins\node_cut\pluginInfo.json`), or run `python install.py`.

## Usage

| Action | Result |
|---|---|
| Select nodes → `Ctrl+X` | Cut |
| `Ctrl+V` | Paste |
| `Ctrl+Z` | Undo the whole cut in one step |
| `Ctrl+X` while renaming a node | Still a plain text cut — no nodes are touched |

## How it works

It does not reimplement copy/paste. It **replays Designer's own `Ctrl+C` followed by its own
`Delete`**, so the clipboard ends up in Designer's native node format: `Ctrl+V` pastes
normally, even between Designer instances, and undo behaves exactly like deleting by hand.
Nothing inside Designer is modified.

`Delete` is only sent once Designer has actually written to the clipboard; if the copy does
not happen, **nothing is deleted**.

## Uninstall

Remove it from "Apps & features". If you installed by hand, delete this folder:

```
%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Designer\python\sduserplugins\node_cut\
```

Designer is unaffected either way — the plugin never touches its files.

## Troubleshooting

The log lives at `...\sduserplugins\node_cut\runtime.log`:

| What the log says | What it means |
|---|---|
| no `initializing` line | Designer was not restarted, or `pluginInfo.json` sits one folder too deep |
| `nothing selected` | The shortcut fired, but select a node in the graph view first |
| `did not write to the clipboard` | The copy failed and the delete was cancelled — please open an issue with the log |

## Compatibility

Windows · Substance 3D Designer 14.1+ (tested on 16.0.6) · Substance graphs only —
function graphs and FX-Maps are left alone.

## Development

```
# Offline smoke test, using Designer's own bundled Python. Never presses a key.
"<Designer>\plugins\pythonsdk\python.exe" tools/smoke_test.py

# Build the installer (needs Inno Setup 6)
cd installer && python stage.py && python mkrtf.py && "ISCC.exe" node_cut.iss
```

`installer/说明.txt` is the single source for the installer's info page; do not edit
`说明.rtf` directly.

## License

[MIT](LICENSE)
