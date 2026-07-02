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
import llm_mode
import renderer
import slide_sync
import ui_theme
import validator

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
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._pdf_path = tk.StringVar()
        self._cover_title = tk.StringVar()
        self._output_dir = tk.StringVar()
        self._use_ai_titles = tk.BooleanVar(value=False)
        self._status = tk.StringVar(value="準備完了")
        self._busy = False
        self._current_slide_data: list[dict] | None = None
        self._title_vars: dict[int, tk.StringVar] = {}
        self._llm_model_ready = False

        self._style = ui_theme.apply_theme(root, font_family=font_family)
        self._build_ui()
        self._start_llm_preload()

    def _build_ui(self) -> None:
        """UI コンポーネントを構築する。"""
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1, minsize=360)
        self.root.grid_rowconfigure(2, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_body()
        self._build_footer()

    def _build_header(self) -> None:
        """トップバー（濃緑）+ 右上 LLM 状態バナー。"""
        header = tk.Frame(self.root, bg=ui_theme.GREEN_DEEP, padx=28, pady=18)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ttk.Label(header, text="Slide-Maker", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="PDF → slideData JSON → PowerPoint 下書き生成",
            style="HeaderSub.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self._llm_banner = tk.Label(
            header,
            text="AIモデルを起動中・・・",
            bg=ui_theme.BANNER_LOADING_BG,
            fg=ui_theme.BANNER_TEXT,
            font=(self._font_family, 10),
            padx=12,
            pady=4,
        )
        self._llm_banner.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(16, 0))

    def _build_body(self) -> None:
        """入力カード + JSON / AI タイトル（横分割）。"""
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

        action_row = ttk.Frame(card, style="Card.TFrame")
        action_row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        ttk.Label(action_row, text="②", style="Step.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(action_row, text="ルールベース → 作成", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 16))
        self._btn_json = ttk.Button(
            action_row, text="JSON 生成", style="Accent.TButton", command=self._on_generate_json,
        )
        self._btn_json.pack(side=tk.LEFT, padx=(8, 0))

        llm_row = ttk.Frame(card, style="Card.TFrame")
        llm_row.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(
            llm_row,
            text="各スライドのタイトル名をAIモデルで作成",
            variable=self._use_ai_titles,
        ).pack(side=tk.LEFT)
        ttk.Label(
            llm_row,
            text="model/gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf 配置時のみ有効",
            style="CardMuted.TLabel",
        ).pack(side=tk.LEFT, padx=(12, 0))

        self._progress_frame = ttk.Frame(card, style="Card.TFrame")
        self._progress_frame.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self._progress_label = ttk.Label(self._progress_frame, text="", style="CardMuted.TLabel")
        self._progress_label.pack(anchor="w")
        self._progress_bar = ttk.Progressbar(self._progress_frame, mode="determinate", maximum=100)
        self._progress_bar.pack(fill=tk.X, pady=(4, 0))
        self._progress_frame.grid_remove()

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
        ttk.Entry(parent, textvariable=textvariable).grid(row=row, column=2, sticky="ew", pady=6)

    def _build_json_section(self, card: ttk.Frame) -> None:
        """ステップ③④ — JSON構造 + AIモデルによるタイトル（横分割）。"""
        card.grid_rowconfigure(2, weight=1, minsize=220)
        card.grid_columnconfigure(0, weight=3)
        card.grid_columnconfigure(1, weight=2)

        header_row = ttk.Frame(card, style="Card.TFrame")
        header_row.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(header_row, text="③④", style="Step.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(header_row, text="slideData（編集可）", style="Section.TLabel").pack(side=tk.LEFT)

        self._draft_label = ttk.Label(
            card,
            text=(
                "これは下書きです。タイトルや文言は、下のJSONを直接編集して仕上げてください。"
                "右側のAIタイトル欄を編集した場合も、検証・スライド作成時に反映されます。"
            ),
            style="CardMuted.TLabel",
            wraplength=900,
            justify=tk.LEFT,
        )
        self._draft_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 6))

        # 左: JSON構造
        json_outer = tk.Frame(
            card,
            bg=ui_theme.WHITE,
            highlightbackground=ui_theme.BORDER,
            highlightthickness=1,
        )
        json_outer.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        json_outer.grid_rowconfigure(1, weight=1)
        json_outer.grid_columnconfigure(0, weight=1)

        ttk.Label(json_outer, text="JSON構造", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 4),
        )
        self._json_text = scrolledtext.ScrolledText(
            json_outer,
            wrap=tk.WORD,
            font=("Consolas", 11),
            bg=ui_theme.WHITE,
            fg=ui_theme.TEXT_MAIN,
            insertbackground=ui_theme.GREEN_EMERALD,
            relief=tk.FLAT,
            borderwidth=0,
            padx=8,
            pady=8,
        )
        self._json_text.grid(row=1, column=0, sticky="nsew")

        # 右: AIモデルによるタイトル
        title_outer = tk.Frame(
            card,
            bg=ui_theme.WHITE,
            highlightbackground=ui_theme.BORDER,
            highlightthickness=1,
        )
        title_outer.grid(row=2, column=1, sticky="nsew")
        title_outer.grid_rowconfigure(1, weight=1)
        title_outer.grid_columnconfigure(0, weight=1)

        ttk.Label(title_outer, text="AIモデルによるタイトル", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 4),
        )

        title_scroll_frame = ttk.Frame(title_outer, style="Card.TFrame")
        title_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        title_scroll_frame.grid_rowconfigure(0, weight=1)
        title_scroll_frame.grid_columnconfigure(0, weight=1)

        self._title_canvas = tk.Canvas(
            title_scroll_frame,
            bg=ui_theme.WHITE,
            highlightthickness=0,
            borderwidth=0,
        )
        self._title_scrollbar = ttk.Scrollbar(title_scroll_frame, orient=tk.VERTICAL, command=self._title_canvas.yview)
        self._title_inner = ttk.Frame(self._title_canvas, style="Card.TFrame")

        self._title_inner.bind(
            "<Configure>",
            lambda _e: self._title_canvas.configure(scrollregion=self._title_canvas.bbox("all")),
        )
        self._title_canvas_window = self._title_canvas.create_window((0, 0), window=self._title_inner, anchor="nw")
        self._title_canvas.configure(yscrollcommand=self._title_scrollbar.set)

        self._title_canvas.grid(row=0, column=0, sticky="nsew")
        self._title_scrollbar.grid(row=0, column=1, sticky="ns")

        card.bind("<Configure>", self._on_json_card_resize)

    def _on_json_card_resize(self, event: tk.Event) -> None:
        """下書きラベルの折り返し幅をカード幅に追従させる。"""
        wrap = max(400, event.width - 40)
        self._draft_label.configure(wraplength=wrap)
        canvas_width = max(200, (event.width // 2) - 40)
        self._title_canvas.itemconfig(self._title_canvas_window, width=canvas_width)

    def _build_footer(self) -> None:
        """ステップ⑤ + アクションボタン + ステータスバー。"""
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

    def _set_llm_banner(self, state: str) -> None:
        """右上 LLM 状態バナーを更新する。"""
        if state == "loading":
            self._llm_banner.configure(
                text="AIモデルを起動中・・・",
                bg=ui_theme.BANNER_LOADING_BG,
            )
        elif state == "ready":
            self._llm_banner.configure(
                text="AIモデル起動完了",
                bg=ui_theme.BANNER_READY_BG,
            )
            self._llm_model_ready = True
        else:
            self._llm_banner.configure(
                text="AIモデル未起動（ルールベースのみ）",
                bg=ui_theme.BANNER_WARN_BG,
            )
            self._llm_model_ready = False

    def _start_llm_preload(self) -> None:
        """起動直後に LLM をバックグラウンドでロードする。"""
        self._set_llm_banner("loading")

        def worker() -> None:
            model = llm_mode.load_model()
            state = "ready" if model is not None else "failed"
            self.root.after(0, lambda: self._set_llm_banner(state))

        threading.Thread(target=worker, daemon=True).start()

    def _show_progress(self, current: int, total: int, message: str) -> None:
        """AI 処理中プログレスバーを表示する。"""
        if total <= 0:
            self._hide_progress()
            return
        self._progress_frame.grid()
        pct = int(current / total * 100)
        self._progress_bar["value"] = pct
        self._progress_label.configure(text=f"{message}{current}/{total}件")

    def _hide_progress(self) -> None:
        """プログレスバーを非表示にする。"""
        self._progress_frame.grid_remove()
        self._progress_bar["value"] = 0
        self._progress_label.configure(text="")

    def _rebuild_title_entries(self, slide_data: list[dict]) -> None:
        """AI タイトル Entry リストを slideData から再構築する。"""
        for child in self._title_inner.winfo_children():
            child.destroy()
        self._title_vars.clear()

        for index, slide in enumerate(slide_data):
            if not slide_sync.should_get_ai_title(slide):
                continue
            row = ttk.Frame(self._title_inner, style="Card.TFrame")
            row.pack(fill=tk.X, pady=3, padx=4)
            ttk.Label(row, text=f"スライド{index + 1}", style="Card.TLabel", width=10).pack(
                side=tk.LEFT, padx=(0, 6),
            )
            var = tk.StringVar(value=str(slide.get("title", "")))
            self._title_vars[index] = var
            ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _refresh_json_from_data(self) -> None:
        """内部 slideData から JSON エディタを更新する。"""
        if self._current_slide_data is None:
            return
        text = json.dumps(self._current_slide_data, ensure_ascii=False, indent=2)
        self._json_text.delete("1.0", tk.END)
        self._json_text.insert(tk.END, text)

    def _merge_title_entries_into_data(
        self,
        slide_data: list[dict],
    ) -> list[dict]:
        """Entry 欄の最新タイトルを slideData に反映する。"""
        titles = {index: var.get() for index, var in self._title_vars.items()}
        return slide_sync.merge_ai_titles_into_slides(slide_data, titles)

    def _parse_json_with_titles(
        self,
    ) -> tuple[list[dict] | None, list[str], list[str]]:
        """JSON をパースし、AI タイトル Entry を反映した slideData を返す。"""
        text = self._json_text.get("1.0", tk.END)
        data, errors, warnings = validator.validate_json_text(text)
        if errors or data is None:
            return None, errors, warnings
        merged = self._merge_title_entries_into_data(data)
        return merged, [], warnings

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

    def _on_title_ready(self, slide_index: int, title: str) -> None:
        """AI タイトル1件完了時に Entry と JSON を更新する。"""
        if slide_index in self._title_vars:
            self._title_vars[slide_index].set(title)
        if self._current_slide_data and slide_index < len(self._current_slide_data):
            self._current_slide_data[slide_index]["title"] = title
            self._refresh_json_from_data()

    def _on_generate_json(self) -> None:
        """PDF から JSON を生成する。"""
        pdf = self._pdf_path.get().strip()
        if not pdf:
            messagebox.showwarning("入力不足", "PDF ファイルを選択してください。")
            return
        if not Path(pdf).is_file():
            messagebox.showerror("エラー", f"PDF が見つかりません:\n{pdf}")
            return

        cover_title = self._cover_title.get().strip()
        use_ai = self._use_ai_titles.get()
        self._set_busy(True, "JSON生成中...")
        if use_ai:
            self._show_progress(0, 1, "AIにより処理中・・・")

        def progress_callback(current: int, total: int, message: str) -> None:
            self.root.after(0, lambda: self._show_progress(current, total, message))

        def title_ready_callback(slide_index: int, title: str) -> None:
            self.root.after(0, lambda: self._on_title_ready(slide_index, title))

        def worker() -> None:
            try:
                model = llm_mode.load_model() if use_ai else None
                data, llm_note = json_builder.build_from_pdf(
                    pdf,
                    cover_title=cover_title or None,
                    use_ai_titles=use_ai,
                    progress_callback=progress_callback if use_ai else None,
                    title_ready_callback=title_ready_callback if use_ai else None,
                    model=model,
                )
                finish_status = llm_note or "JSON生成完了"
                self.root.after(0, lambda: self._finish_json_ok(data, finish_status))
            except Exception as exc:
                logger.exception("JSON 生成エラー")
                self.root.after(0, lambda: self._finish_error(f"JSON 生成エラー: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_json_ok(self, data: list[dict], status: str = "JSON生成完了") -> None:
        """JSON 生成成功時の UI 更新。"""
        self._current_slide_data = data
        self._rebuild_title_entries(data)
        self._refresh_json_from_data()
        self._hide_progress()
        self._set_busy(False, status)

    def _finish_error(self, msg: str) -> None:
        """エラー時の UI 更新。"""
        self._hide_progress()
        self._set_busy(False, "エラー")
        messagebox.showerror("エラー", msg)

    def _on_validate(self) -> None:
        """JSON を検証する（AI タイトル Entry を反映後）。"""
        data, errors, warnings = self._parse_json_with_titles()
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
        """PPTX を生成する（AI タイトル Entry を反映後）。"""
        data, errors, warnings = self._parse_json_with_titles()
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

    def _on_close(self) -> None:
        """アプリ終了時に LLM を解放する。"""
        llm_mode.unload_model()
        self.root.destroy()


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
