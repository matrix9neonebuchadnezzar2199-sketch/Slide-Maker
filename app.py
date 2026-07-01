"""PDF → PowerPoint 変換ツール — tkinter GUI エントリポイント."""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import tkinter as tk
import tkinter.font as tkfont

import json_builder
import renderer
import validator
from llm_mode import LlmModeNotImplementedError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

APP_TITLE = "PDF2PPTX — Slide-Maker"


def _enable_windows_dpi_awareness() -> None:
    """高 DPI 環境でのぼやけを軽減する。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _pick_ui_font_family() -> str:
    """日本語 UI 向けフォントを選ぶ。"""
    for family in ("Yu Gothic UI", "Meiryo UI", "Meiryo", "Segoe UI"):
        if family in tkfont.families():
            return family
    return "TkDefaultFont"


def _resolve_output_path(output_dir: str, pdf_path: str) -> Path:
    """出力 pptx パスを決定する（同名衝突時はタイムスタンプ付与）。"""
    stem = Path(pdf_path).stem
    out = Path(output_dir) / f"{stem}.pptx"
    if not out.exists():
        return out
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(output_dir) / f"{stem}_{ts}.pptx"


class SlideMakerApp:
    """メインアプリケーションウィンドウ。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.minsize(800, 600)
        self.root.geometry("1000x700")

        self._pdf_path = tk.StringVar()
        self._output_dir = tk.StringVar()
        self._mode = tk.StringVar(value="rule")
        self._status = tk.StringVar(value="準備完了")
        self._busy = False

        self._build_ui()

    def _build_ui(self) -> None:
        """UI コンポーネントを構築する。"""
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)

        # --- ステップ① PDF 選択 ---
        pdf_row = ttk.Frame(top)
        pdf_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(pdf_row, text="① PDF:").pack(side=tk.LEFT)
        ttk.Entry(pdf_row, textvariable=self._pdf_path, width=70).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        self._btn_pdf = ttk.Button(pdf_row, text="参照...", command=self._on_select_pdf)
        self._btn_pdf.pack(side=tk.LEFT)

        # --- ステップ② モード選択 + JSON 生成 ---
        mode_row = ttk.Frame(top)
        mode_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(mode_row, text="② モード:").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="ルールベース", variable=self._mode, value="rule").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(mode_row, text="LLM", variable=self._mode, value="llm").pack(side=tk.LEFT, padx=4)
        self._btn_json = ttk.Button(mode_row, text="JSON 生成", command=self._on_generate_json)
        self._btn_json.pack(side=tk.LEFT, padx=8)

        # --- ステップ③④ JSON 編集エリア ---
        mid = ttk.Frame(self.root, padding=(8, 0))
        mid.pack(fill=tk.BOTH, expand=True)
        ttk.Label(mid, text="③④ slideData JSON（編集可）:").pack(anchor=tk.W)
        self._json_text = scrolledtext.ScrolledText(mid, wrap=tk.WORD, font=("Consolas", 11))
        self._json_text.pack(fill=tk.BOTH, expand=True, pady=4)

        # --- ステップ⑤ 検証・出力 ---
        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill=tk.X)

        out_row = ttk.Frame(bottom)
        out_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(out_row, text="⑤ 出力先:").pack(side=tk.LEFT)
        ttk.Entry(out_row, textvariable=self._output_dir, width=60).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        self._btn_out = ttk.Button(out_row, text="参照...", command=self._on_select_output)
        self._btn_out.pack(side=tk.LEFT)

        action_row = ttk.Frame(bottom)
        action_row.pack(fill=tk.X, pady=(4, 0))
        self._btn_validate = ttk.Button(action_row, text="検証", command=self._on_validate)
        self._btn_validate.pack(side=tk.LEFT, padx=(0, 8))
        self._btn_build = ttk.Button(action_row, text="スライド作成", command=self._on_build_pptx)
        self._btn_build.pack(side=tk.LEFT)

        status_row = ttk.Frame(bottom)
        status_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(status_row, text="状態:").pack(side=tk.LEFT)
        ttk.Label(status_row, textvariable=self._status).pack(side=tk.LEFT, padx=4)

    def _set_busy(self, busy: bool, status: str = "") -> None:
        """処理中フラグとボタン状態を切り替える。"""
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for btn in (self._btn_pdf, self._btn_json, self._btn_validate, self._btn_out, self._btn_build):
            btn.configure(state=state)
        if status:
            self._status.set(status)

    def _on_select_pdf(self) -> None:
        """PDF ファイルを選択する。"""
        path = filedialog.askopenfilename(
            title="PDF を選択",
            filetypes=[("PDF", "*.pdf"), ("すべて", "*.*")],
        )
        if path:
            self._pdf_path.set(path)
            if not self._output_dir.get():
                self._output_dir.set(str(Path(path).parent))

    def _on_select_output(self) -> None:
        """出力先フォルダを選択する。"""
        path = filedialog.askdirectory(title="出力先フォルダを選択")
        if path:
            self._output_dir.set(path)

    def _on_generate_json(self) -> None:
        """PDF から JSON を生成する。"""
        pdf = self._pdf_path.get().strip()
        if not pdf:
            messagebox.showwarning("入力不足", "PDF ファイルを選択してください。")
            return
        if not Path(pdf).is_file():
            messagebox.showerror("エラー", f"PDF が見つかりません:\n{pdf}")
            return

        mode = self._mode.get()
        self._set_busy(True, "JSON生成中...")

        def worker() -> None:
            try:
                data = json_builder.build_from_pdf(pdf, mode=mode)  # type: ignore[arg-type]
                text = json.dumps(data, ensure_ascii=False, indent=2)
                self.root.after(0, lambda: self._finish_json_ok(text))
            except LlmModeNotImplementedError as exc:
                self.root.after(0, lambda: self._finish_error(str(exc)))
            except Exception as exc:
                logger.exception("JSON 生成エラー")
                self.root.after(0, lambda: self._finish_error(f"JSON 生成エラー: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_json_ok(self, text: str) -> None:
        """JSON 生成成功時の UI 更新。"""
        self._json_text.delete("1.0", tk.END)
        self._json_text.insert(tk.END, text)
        self._set_busy(False, "JSON生成完了")

    def _finish_error(self, msg: str) -> None:
        """エラー時の UI 更新。"""
        self._set_busy(False, "エラー")
        messagebox.showerror("エラー", msg)

    def _on_validate(self) -> None:
        """JSON を検証する。"""
        text = self._json_text.get("1.0", tk.END)
        data, errors, warnings = validator.validate_json_text(text)
        if errors:
            messagebox.showwarning(
                "検証失敗",
                "以下の問題が見つかりました:\n\n" + "\n".join(errors),
            )
            self._status.set(f"検証失敗 ({len(errors)} 件)")
            return

        slide_count = len(data) if data else 0
        msg = f"スキーマ検証に合格しました。\nスライド数: {slide_count}"
        if warnings:
            msg += "\n\n【注意】\n" + "\n".join(warnings)
            messagebox.showwarning("検証成功（注意あり）", msg)
            self._status.set(f"検証成功（警告 {len(warnings)} 件）")
        else:
            messagebox.showinfo("検証成功", msg)
            self._status.set("検証成功")

    def _on_build_pptx(self) -> None:
        """PPTX を生成する。"""
        text = self._json_text.get("1.0", tk.END)
        data, errors, warnings = validator.validate_json_text(text)
        if errors:
            messagebox.showerror(
                "検証エラー",
                "スライド作成前の検証に失敗しました:\n\n" + "\n".join(errors[:10]),
            )
            return

        if warnings:
            proceed = messagebox.askyesno(
                "注意",
                "以下の警告があります。続行しますか？\n\n" + "\n".join(warnings),
            )
            if not proceed:
                return

        out_dir = self._output_dir.get().strip()
        if not out_dir:
            messagebox.showwarning("入力不足", "出力先フォルダを指定してください。")
            return
        if not Path(out_dir).is_dir():
            messagebox.showerror("エラー", f"出力先フォルダが存在しません:\n{out_dir}")
            return

        pdf = self._pdf_path.get().strip()
        out_path = _resolve_output_path(out_dir, pdf or "output")
        self._set_busy(True, "スライド生成中...")

        def worker() -> None:
            try:
                renderer.build_pptx(data, str(out_path))
                self.root.after(0, lambda: self._finish_pptx_ok(str(out_path)))
            except Exception as exc:
                logger.exception("PPTX 生成エラー")
                self.root.after(0, lambda: self._finish_error(f"PPTX 生成エラー: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_pptx_ok(self, out_path: str) -> None:
        """PPTX 生成成功時の UI 更新。"""
        self._set_busy(False, "完了")
        messagebox.showinfo("完了", f"スライドを作成しました:\n{out_path}")


def run_app() -> None:
    """アプリケーションを起動する。"""
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    family = _pick_ui_font_family()
    root.option_add("*Font", (family, 11))
    SlideMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    run_app()
