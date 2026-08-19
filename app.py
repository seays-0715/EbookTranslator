from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from api_translate import translate_book
from extract_epub import extract
from validate_translation import validate
from reconstruct_epub import rebuild
from package_epub import package


class EbookApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Ebook Translator")
        self.geometry("820x760")
        self.minsize(760, 700)
        self.epub: Path | None = None
        self.workspace: Path | None = None
        self.book: str | None = None
        self._build_ui()

    @property
    def data_book(self) -> Path:
        assert self.workspace and self.book
        return self.workspace / "Data" / self.book

    @property
    def translation_dir(self) -> Path:
        assert self.workspace and self.book
        return self.workspace / "Translating" / self.book

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Ebook Translator", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(frame, text="選擇 EPUB → 抽取文字 → 手動或 API 翻譯 → 檢查 → 產出繁體中文 EPUB", wraplength=760).pack(anchor="w", pady=(4, 16))

        self.input_var = tk.StringVar()
        self.working_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.epub_var = tk.StringVar()
        self.style_var = tk.StringVar(value="直式")
        self.mode_var = tk.StringVar(value="manual")
        self.base_url_var = tk.StringVar(value="https://api.openai.com/v1")
        self.model_var = tk.StringVar(value="gpt-5-mini")
        self.api_key_var = tk.StringVar()
        self.max_chars_var = tk.StringVar(value="24000")

        step1 = ttk.LabelFrame(frame, text="步驟 1：選擇檔案", padding=12)
        step1.pack(fill="x", pady=(0, 10))
        self._path_row(step1, "輸入 Path", self.input_var, self.select_input_path)
        ttk.Label(step1, text="選擇包含 EPUB 的資料夾；如果只有一個 EPUB，會自動選取。", foreground="gray").pack(anchor="w", padx=(108, 0), pady=(0, 8))
        self._file_row(step1, "EPUB", self.epub_var, self.select_epub)

        step2 = ttk.LabelFrame(frame, text="步驟 2：抽取文字與翻譯", padding=12)
        step2.pack(fill="x", pady=(0, 10))
        self._path_row(step2, "Working Path", self.working_var, self.select_working_path)
        ttk.Label(step2, text="Data、Translating 等工作資料會建立在此位置。留空時使用 EPUB 所在資料夾。", foreground="gray", wraplength=700).pack(anchor="w", padx=(108, 0), pady=(0, 10))

        action = ttk.Frame(step2)
        action.pack(fill="x")
        self.extract_btn = ttk.Button(action, text="抽取 TXT", command=self.extract_book, state="disabled")
        self.extract_btn.pack(side="left", padx=(0, 8))
        self.source_btn = ttk.Button(action, text="開啟原文資料夾", command=self.open_source, state="disabled")
        self.source_btn.pack(side="left", padx=8)
        self.translation_btn = ttk.Button(action, text="開啟翻譯資料夾", command=self.open_translation, state="disabled")
        self.translation_btn.pack(side="left", padx=8)

        mode = ttk.Frame(step2)
        mode.pack(fill="x", pady=(14, 4))
        ttk.Label(mode, text="翻譯方式", width=14).pack(side="left")
        ttk.Radiobutton(mode, text="自己使用 AI 翻譯", variable=self.mode_var, value="manual", command=self._toggle_api).pack(side="left", padx=(0, 18))
        ttk.Radiobutton(mode, text="API 自動翻譯", variable=self.mode_var, value="api", command=self._toggle_api).pack(side="left")

        self.api_frame = ttk.Frame(step2)
        self.api_frame.pack(fill="x", pady=(8, 0))
        self._api_row(self.api_frame, "API Base URL", self.base_url_var)
        self._api_row(self.api_frame, "Model", self.model_var)
        key_row = ttk.Frame(self.api_frame)
        key_row.pack(fill="x", pady=3)
        ttk.Label(key_row, text="API Key", width=14).pack(side="left")
        ttk.Entry(key_row, textvariable=self.api_key_var, show="*").pack(side="left", fill="x", expand=True)
        self._api_row(self.api_frame, "每批字數", self.max_chars_var)
        ttk.Label(self.api_frame, text="API Key 只存在目前程式執行期間，不會寫入 GitHub 或設定檔。每批會在 paragraph 邊界自動切割。", foreground="gray", wraplength=700).pack(anchor="w", padx=(108, 0), pady=(3, 0))
        self.api_translate_btn = ttk.Button(self.api_frame, text="開始 API 翻譯", command=self.api_translate, state="disabled")
        self.api_translate_btn.pack(anchor="w", padx=(108, 8), pady=(8, 0))

        self.manual_hint = ttk.Label(step2, text="手動模式：把抽取出的 TXT 交給你選擇的 AI 翻譯，完成後放回 Translating 資料夾。", foreground="gray", wraplength=700)
        self.manual_hint.pack(anchor="w", pady=(8, 0))

        step3 = ttk.LabelFrame(frame, text="步驟 3：檢查並產出", padding=12)
        step3.pack(fill="x", pady=(0, 10))
        self._path_row(step3, "輸出 Path", self.output_var, self.select_output_path)
        ttk.Label(step3, text="留空時輸出到工作資料夾的 Translated。", foreground="gray").pack(anchor="w", padx=(108, 0), pady=(0, 10))
        row = ttk.Frame(step3)
        row.pack(fill="x")
        ttk.Label(row, text="EPUB 格式", width=14).pack(side="left")
        ttk.Combobox(row, textvariable=self.style_var, values=("直式", "橫式"), state="readonly", width=14).pack(side="left")
        self.validate_btn = ttk.Button(row, text="檢查翻譯", command=self.validate_book, state="disabled")
        self.validate_btn.pack(side="left", padx=(18, 8))
        self.build_btn = ttk.Button(row, text="產出 EPUB", command=self.build_book, state="disabled")
        self.build_btn.pack(side="left", padx=8)
        ttk.Label(step3, text="API 翻譯完成後會自動產生翻譯 TXT；手動模式則由你自行放回。", foreground="gray").pack(anchor="w", pady=(8, 0))

        self.status = tk.StringVar(value="請先選擇輸入 Path 或 EPUB")
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(4, 10))
        ttk.Label(frame, textvariable=self.status, relief="sunken", anchor="w", padding=7).pack(fill="x", side="bottom")
        self._toggle_api()

    @staticmethod
    def _path_row(parent, label, variable, command):
        row = ttk.Frame(parent); row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=14).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="選擇", command=command).pack(side="left", padx=(8, 0))

    @staticmethod
    def _file_row(parent, label, variable, command):
        EbookApp._path_row(parent, label, variable, command)

    @staticmethod
    def _api_row(parent, label, variable):
        row = ttk.Frame(parent); row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=14).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)

    def _toggle_api(self):
        state = "normal" if self.mode_var.get() == "api" else "disabled"
        for child in self.api_frame.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass
        self.manual_hint.configure(state="normal" if self.mode_var.get() == "manual" else "disabled")

    def select_input_path(self):
        path = filedialog.askdirectory(title="選擇輸入資料夾")
        if path:
            self.input_var.set(path); self.status.set(f"輸入 Path：{path}"); self._load_epubs_from_input()

    def select_working_path(self):
        path = filedialog.askdirectory(title="選擇工作資料夾")
        if path:
            self.working_var.set(path); self._refresh_workspace()

    def select_output_path(self):
        path = filedialog.askdirectory(title="選擇輸出資料夾")
        if path: self.output_var.set(path)

    def _load_epubs_from_input(self):
        root = Path(self.input_var.get().strip())
        if not root.is_dir(): return
        epubs = sorted(root.glob("*.epub"))
        if len(epubs) == 1: self._set_epub(epubs[0])
        elif epubs: self.select_epub()

    def _refresh_workspace(self):
        if self.epub:
            base = Path(self.working_var.get().strip()) if self.working_var.get().strip() else self.epub.parent
            self.workspace = base / f"{self.epub.stem}_ebook"

    def _set_epub(self, path: Path):
        self.epub = path; self.epub_var.set(str(path))
        if not self.working_var.get().strip(): self.working_var.set(str(path.parent))
        self._refresh_workspace(); self.book = path.stem
        self.extract_btn.config(state="normal"); self.status.set(f"已選擇：{self.epub.name}")

    def select_epub(self):
        initial = self.input_var.get().strip() or None
        path = filedialog.askopenfilename(title="選擇 EPUB", initialdir=initial, filetypes=[("EPUB", "*.epub")])
        if path: self._set_epub(Path(path))

    @staticmethod
    def error_text(exc):
        return str(exc) or f"{type(exc).__name__}: 未提供錯誤訊息"

    def _enable_after_extract(self):
        for button in (self.source_btn, self.translation_btn, self.validate_btn, self.build_btn, self.api_translate_btn):
            button.config(state="normal")

    def extract_book(self):
        if not self.epub or not self.workspace or not self.book: return
        if self.workspace.exists():
            if not messagebox.askyesno("重新抽取", f"工作資料夾已存在：\n{self.workspace}\n\n重新抽取會清除其中的 Data。是否繼續？"): return
            data = self.workspace / "Data"
            if data.exists(): shutil.rmtree(data)
        try:
            extract(self.epub, self.workspace / "Data", self.book)
            self.translation_dir.mkdir(parents=True, exist_ok=True)
            self._enable_after_extract()
            self.status.set(f"抽取完成：{self.data_book / 'text'}")
        except Exception as exc:
            messagebox.showerror("抽取失敗", self.error_text(exc)); self.status.set("抽取失敗")

    def open_source(self):
        if self.data_book.exists(): os.startfile(self.data_book / "text")

    def open_translation(self):
        self.translation_dir.mkdir(parents=True, exist_ok=True); os.startfile(self.translation_dir)

    def api_translate(self):
        if not self.data_book.is_dir(): return
        api_key = self.api_key_var.get().strip()
        base_url = self.base_url_var.get().strip()
        model = self.model_var.get().strip()
        try: max_chars = int(self.max_chars_var.get().strip())
        except ValueError:
            messagebox.showerror("API 翻譯失敗", "每批字數必須是整數。"); return
        if not api_key or not base_url or not model:
            messagebox.showerror("API 翻譯失敗", "請填寫 API Base URL、Model 及 API Key。"); return
        try:
            self.api_translate_btn.config(state="disabled"); self.status.set("API 翻譯中，請勿關閉程式……"); self.update_idletasks()
            files, chunks = translate_book(self.data_book, self.workspace / "Translating", base_url, api_key, model, max_chars)
            self.api_translate_btn.config(state="normal")
            self.status.set(f"API 翻譯完成：{files} 個 TXT，{chunks} 個批次")
            messagebox.showinfo("API 翻譯完成", f"已完成 {files} 個 TXT，共 {chunks} 個 API 批次。\n\n現在可以執行「檢查翻譯」。")
        except Exception as exc:
            self.api_translate_btn.config(state="normal")
            messagebox.showerror("API 翻譯失敗", self.error_text(exc)); self.status.set("API 翻譯失敗")

    def validate_book(self):
        try:
            result = validate(self.data_book, self.workspace / "Translating", complete=True)
            if result:
                messagebox.showerror("檢查失敗", "翻譯資料未通過完整檢查。\n\n請檢查 ID、段落數量、空白翻譯及日文殘留。")
                self.status.set("檢查失敗"); return False
            self.status.set("檢查通過"); messagebox.showinfo("檢查通過", "所有翻譯 TXT 均通過檢查。"); return True
        except Exception as exc:
            messagebox.showerror("檢查失敗", self.error_text(exc)); self.status.set("檢查失敗"); return False

    def build_book(self):
        if not self.data_book.is_dir():
            messagebox.showerror("產出 EPUB 失敗", "請先執行「抽取 TXT」。"); return
        try:
            translation_files = list(self.translation_dir.rglob("*.txt")) if self.translation_dir.is_dir() else []
            if translation_files and validate(self.data_book, self.workspace / "Translating", complete=False):
                messagebox.showerror("產出 EPUB 失敗", "翻譯資料未通過檢查。請修正後再產出。"); self.status.set("翻譯檢查失敗"); return
            self.status.set("正在重建 EPUB……"); self.update_idletasks()
            missing = rebuild(self.data_book, self.workspace / "Translating")
            template_name = "vertical" if self.style_var.get() == "直式" else "horizontal"
            template_root = ROOT / "template" / template_name
            output_dir = Path(self.output_var.get().strip()) if self.output_var.get().strip() else self.workspace / "Translated"
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / f"{self.book}_repacked_{template_name}.epub"
            package(self.data_book, template_root, output)
            detail = f"\n\n有 {missing} 個段落沒有翻譯，因此保留原文。" if missing else ""
            self.status.set(f"完成：{output}")
            if messagebox.askyesno("完成", f"精簡 EPUB 已生成：\n{output}{detail}\n\n要開啟輸出資料夾嗎？"):
                os.startfile(output.parent)
        except Exception as exc:
            messagebox.showerror("產出 EPUB 失敗", self.error_text(exc)); self.status.set("產出 EPUB 失敗")


if __name__ == "__main__":
    EbookApp().mainloop()
