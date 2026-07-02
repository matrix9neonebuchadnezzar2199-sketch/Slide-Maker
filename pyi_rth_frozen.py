"""PyInstaller runtime hook — frozen EXE 向け DLL 探索パス設定."""

from __future__ import annotations

import os
import sys


def _add_dll_dir(path: str) -> None:
    """Windows でネイティブ DLL 探索パスを追加する。"""
    if not path or not os.path.isdir(path):
        return
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(path)  # type: ignore[attr-defined]
    else:
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")


if getattr(sys, "frozen", False):
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        _add_dll_dir(meipass)
        _add_dll_dir(os.path.join(meipass, "llama_cpp", "lib"))
