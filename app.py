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
import ui_theme
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

    def __init__(self, root: tk.Tk, *, font_family: str) -> None:
        self.root = root
        self._font_family = font_family
        self.root.title(APP_TITLE)
        self.root.minsize(ui_theme.MIN_WINDOW_WIDTH, ui_theme.MIN_WINDOW_HEIGHT)
        self.root.geometry(ui_theme.DEFAULT_GEOMETRY)

        self._pdf_path = tk.StringVar()
        self._cover_title = tk.StringVar()
        self._output_dir = tk.StringVar()
        self._mode = tk.StringVar(value="rule")
        self._use_llm_title_fix = tk.BooleanVar(value=False)
        self._status = tk.StringVar(value="準備完了")
        self._busy = False

        self._style = ui_theme.apply_theme(root, font_family=font_family)
        self._build_ui()

    def _build_ui(self) -> None:
        """UI コンポーネントを構築する（操作領域を固定し、JSON領域だけ伸縮）。"""
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1, minsize=360)
        self.root.grid_rowconfigure(2, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_body()
        self._build_footer()

    def _build_header(self) -> None:
        """トップバー（濃緑）。"""
        header = tk.Frame(self.root, bg=ui_theme.GREEN_DEEP, padx=28, pady=18)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ttk.Label(header, text="Slide-Maker", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="PDF → slideData JSON → PowerPoint 下書き生成",
            style="HeaderSub.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _build_body(self) -> None:
        """入力カード + JSON エディタ（中央のみ伸縮）。"""
        body = ttk.Frame(self.root, padding=(22, 18))
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=0)
        body.grid_rowconfigure(1, weight=1, minsize=260)
        body.grid_columnconfigure(0, weight=1)

        input_card = self._make_card(body, row=0)
        self._build_input_section(input_card)

        json_card = self._make_card(body, row=1, pady_top=12)
        self._build_json_section(json_card)

    def _make_card(self, parent: ttk.Frame, *, row: int, pady_top: int = 0) -> ttk.Frame:
        """クリーム色のカード枠を作る。"""
        outer = tk.Frame(
            parent,
            bg=ui_theme.CARD_BORDER,
            highlightbackground=ui_theme.CARD_BORDER,
            highlightthickness=1,
        )
        outer.grid(row=row, column=0, sticky="nsew", pady=(pady_top, 0))
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        card = ttk.Frame(outer, style="Card.TFrame", padding=18)
        card.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        card.grid_columnconfigure(0, minsize=46)
        card.grid_columnconfigure(1, minsize=210)
        card.grid_columnconfigure(2, weight=1, minsize=360)
        card.grid_columnconfigure(3, minsize=104)
        return card

    def _build_input_section(self, card: ttk.Frame) -> None:
        """ステップ①②の入力欄。"""
        ttk.Label(card, text="入力", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 14),
        )

        self._add_labeled_entry(card, row=1, step="①", label="PDF", textvariable=self._pdf_path)
        self._btn_pdf = ttk.Button(card, text="参照...", command=self._on_select_pdf)
        self._btn_pdf.grid(row=1, column=3, sticky="ew", padx=(12, 0), pady=6)

        self._add_labeled_entry(
            card,
            row=2,
            step="",
            label="プレゼンのタイトル（表紙）",
            textvariable=self._cover_title,
        )

        mode_row = ttk.Frame(card, style="Card.TFrame")
        mode_row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        ttk.Label(mode_row, text="②", style="Step.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(mode_row, text="モード", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 16))
        ttk.Radiobutton(mode_row, text="ルールベース", variable=self._mode, value="rule").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(mode_row, text="LLM", variable=self._mode, value="llm").pack(side=tk.LEFT, padx=(12, 4))
        self._btn_json = ttk.Button(
            mode_row, text="JSON 生成", style="Accent.TButton", command=self._on_generate_json,
        )
        self._btn_json.pack(side=tk.LEFT, padx=(24, 0))

        llm_row = ttk.Frame(card, style="Card.TFrame")
        llm_row.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(
            llm_row,
            text="LLMでタイトルを整える（実験的・下書き補助）",
            variable=self._use_llm_title_fix,
        ).pack(side=tk.LEFT)
        ttk.Label(
            llm_row,
            text="model/*.gguf 配置時のみ有効。長い content/table タイトルを短縮します。",
            style="CardMuted.TLabel",
        ).pack(side=tk.LEFT, padx=(12, 0))

    def _add_labeled_entry(
        self,
        parent: ttk.Frame,
        *,
        row: int,
        step: str,
        label: str,
        textvariable: tk.StringVar,
    ) -> None:
        """固定4列のラベル + Entry 行。"""
        ttk.Label(parent, text=step, style="Step.TLabel").grid(row=row, column=0, sticky="w", pady=6)

        ttk.Label(parent, text=label, style="Card.TLabel").grid(
            row=row, column=1, sticky="w", padx=(0, 14), pady=6,
        )
        entry = ttk.Entry(parent, textvariable=textvariable)
        entry.grid(row=row, column=2, sticky="ew", pady=6)

    def _build_json_section(self, card: ttk.Frame) -> None:
        """ステップ③④ JSON エディタ。"""
        card.grid_rowconfigure(2, weight=1, minsize=220)
        card.grid_columnconfigure(0, weight=1)

        header_row = ttk.Frame(card, style="Card.TFrame")
        header_row.grid(row=0, column=0, sticky="ew")
        ttk.Label(header_row, text="③④", style="Step.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(
            header_row,
            text="slideData JSON（編集可）",
            style="Section.TLabel",
        ).pack(side=tk.LEFT)

        self._draft_label = ttk.Label(
            card,
            text=(
                "これは下書きです。タイトルや文言は、下のJSONを直接編集して仕上げてください。"
                "特に表紙タイトルと各スライドのタイトルは、内容に合わせて浄書することをおすすめします。"
            ),
            style="CardMuted.TLabel",
            wraplength=900,
            justify=tk.LEFT,
        )
        self._draft_label.grid(row=1, column=0, sticky="ew", pady=(8, 6))

        text_frame = tk.Frame(
            card,
            bg=ui_theme.WHITE,
            highlightbackground=ui_theme.BORDER,
            highlightthickness=1,
        )
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self._json_text = scrolledtext.ScrolledText(
            text_frame,
            wrap=tk.WORD,
            font=("Consolas", 12),
            bg=ui_theme.WHITE,
            fg=ui_theme.TEXT_MAIN,
            insertbackground=ui_theme.GREEN_EMERALD,
            relief=tk.FLAT,
            borderwidth=0,
            padx=8,
            pady=8,
        )
        self._json_text.grid(row=0, column=0, sticky="nsew")

        card.bind("<Configure>", self._on_json_card_resize)

    def _on_json_card_resize(self, event: tk.Event) -> None:
        """下書きラベルの折り返し幅をカード幅に追従させる。"""
        wrap = max(400, event.width - 40)
        self._draft_label.configure(wraplength=wrap)

    def _build_footer(self) -> None:
        """ステップ⑤ + アクションボタン + ステータスバー（常に表示）。"""
        footer_wrap = tk.Frame(self.root, bg=ui_theme.APP_BG)
        footer_wrap.grid(row=2, column=0, sticky="ew")
        footer_wrap.grid_columnconfigure(0, weight=1)

        footer_outer = tk.Frame(
            footer_wrap,
            bg=ui_theme.CARD_BORDER,
            highlightbackground=ui_theme.CARD_BORDER,
            highlightthickness=1,
        )
        footer_outer.grid(row=0, column=0, sticky="ew", padx=22, pady=(0, 10))
        footer_outer.grid_columnconfigure(0, weight=1)

        footer_card = ttk.Frame(footer_outer, style="Card.TFrame", padding=16)
        footer_card.grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        footer_card.grid_columnconfigure(0, minsize=46)
        footer_card.grid_columnconfigure(1, minsize=96)
        footer_card.grid_columnconfigure(2, weight=1, minsize=320)

        ttk.Label(footer_card, text="⑤", style="Step.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer_card, text="出力先", style="Card.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 14))
        ttk.Entry(footer_card, textvariable=self._output_dir).grid(row=0, column=2, sticky="ew", padx=(0, 12))
        self._btn_out = ttk.Button(footer_card, text="参照...", command=self._on_select_output)
        self._btn_out.grid(row=0, column=3, sticky="e")

        action_row = ttk.Frame(footer_card, style="Card.TFrame")
        action_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        self._btn_validate = ttk.Button(action_row, text="検証", command=self._on_validate)
        self._btn_validate.pack(side=tk.LEFT, padx=(0, 10))
        self._btn_build = ttk.Button(
            action_row, text="スライド作成", style="Accent.TButton", command=self._on_build_pptx,
        )
        self._btn_build.pack(side=tk.LEFT)

        status_bar = tk.Frame(footer_wrap, bg=ui_theme.GREEN_DEEP, padx=16, pady=8)
        status_bar.grid(row=1, column=0, sticky="ew")
        ttk.Label(status_bar, text="状態:", style="Status.TLabel").pack(side=tk.LEFT)
        ttk.Label(status_bar, textvariable=self._status, style="StatusValue.TLabel").pack(side=tk.LEFT, padx=(6, 0))

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
            if not self._cover_title.get().strip():
                self._cover_title.set(json_builder.suggest_cover_title_from_stem(Path(path).stem))

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
        cover_title = self._cover_title.get().strip()
        use_llm_title_fix = self._use_llm_title_fix.get() and mode == "rule"
        self._set_busy(True, "JSON生成中...")

        def progress_callback(current: int, total: int, message: str) -> None:
            self.root.after(
                0,
                lambda c=current, t=total, m=message: self._status.set(f"{m} ({c}/{t})"),
            )

        def worker() -> None:
            try:
                data, llm_note = json_builder.build_from_pdf(
                    pdf,
                    mode=mode,  # type: ignore[arg-type]
                    cover_title=cover_title or None,
                    use_llm_title_fix=use_llm_title_fix,
                    progress_callback=progress_callback if use_llm_title_fix else None,
                )
                text = json.dumps(data, ensure_ascii=False, indent=2)
                finish_status = llm_note or "JSON生成完了"
                self.root.after(0, lambda: self._finish_json_ok(text, finish_status))
            except LlmModeNotImplementedError as exc:
                self.root.after(0, lambda: self._finish_error(str(exc)))
            except Exception as exc:
                logger.exception("JSON 生成エラー")
                self.root.after(0, lambda: self._finish_error(f"JSON 生成エラー: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_json_ok(self, text: str, status: str = "JSON生成完了") -> None:
        """JSON 生成成功時の UI 更新。"""
        self._json_text.delete("1.0", tk.END)
        self._json_text.insert(tk.END, text)
        self._set_busy(False, status)

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
    SlideMakerApp(root, font_family=family)
    root.mainloop()


if __name__ == "__main__":
    run_app()
