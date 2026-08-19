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

from api_translate import DEFAULT_POLISH_PROMPT, DEFAULT_PROMPT, translate_book
from extract_epub import extract
from validate_translation import validate
from reconstruct_epub import rebuild
from package_epub import package


class EbookApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Ebook Translator")
        self.geometry("900x820")
        self.minsize(820, 740)
        self.epub: Path | None = None
        self.workspace: Path | None = None
        self.book: str | None = None
        self.range_files: list[str] = []
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
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Ebook Translator", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(root, text="EPUB → 抽取 → 翻譯 → 檢查 → 產出繁體中文 EPUB", foreground="gray").pack(anchor="w", pady=(3, 12))

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
        self.prompt_var = tk.StringVar(value=DEFAULT_PROMPT)
        self.polish_var = tk.BooleanVar(value=False)
        self.polish_prompt_var = tk.StringVar(value=DEFAULT_POLISH_PROMPT)
        self.glossary_text: tk.Text | None = None
        self.range_list: tk.Listbox | None = None

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)
        setup = ttk.Frame(notebook, padding=14)
        translation = ttk.Frame(notebook, padding=14)
        output = ttk.Frame(notebook, padding=14)
        notebook.add(setup, text="檔案與抽取")
        notebook.add(translation, text="翻譯")
        notebook.add(output, text="檢查與產出")

        # Setup tab
        self._path_row(setup, "輸入 Path", self.input_var, self.select_input_path)
        ttk.Label(setup, text="選擇包含 EPUB 的資料夾；只有一個 EPUB 時會自動選取。", foreground="gray").pack(anchor="w", padx=(108, 8), pady=(0, 8))
        self._path_row(setup, "EPUB", self.epub_var, self.select_epub)
        self._path_row(setup, "Working Path", self.working_var, self.select_working_path)
        ttk.Label(setup, text="留空時使用 EPUB 所在資料夾；Data、Translating 等工作資料會建立在此位置。", foreground="gray", wraplength=760).pack(anchor="w", padx=(108, 10), pady=(0, 12))
        actions = ttk.Frame(setup); actions.pack(fill="x", pady=4)
        self.extract_btn = ttk.Button(actions, text="抽取 TXT", command=self.extract_book, state="disabled")
        self.extract_btn.pack(side="left")
        self.source_btn = ttk.Button(actions, text="開啟原文資料夾", command=self.open_source, state="disabled")
        self.source_btn.pack(side="left", padx=8)
        self.translation_btn = ttk.Button(actions, text="開啟翻譯資料夾", command=self.open_translation, state="disabled")
        self.translation_btn.pack(side="left")
        ttk.Label(setup, text="抽取完成後，切換到「翻譯」頁面設定翻譯方式與範圍。", foreground="gray").pack(anchor="w", pady=(12, 0))

        # Translation tab
        mode = ttk.LabelFrame(translation, text="翻譯方式", padding=10); mode.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(mode, text="自己使用 AI 翻譯", variable=self.mode_var, value="manual", command=self._toggle_api).pack(side="left", padx=(0, 20))
        ttk.Radiobutton(mode, text="API 自動翻譯", variable=self.mode_var, value="api", command=self._toggle_api).pack(side="left")

        settings = ttk.LabelFrame(translation, text="翻譯設定", padding=10); settings.pack(fill="x", pady=(0, 10))
        self._api_row(settings, "翻譯 Prompt", self.prompt_var, multiline=True, height=5)
        ttk.Label(settings, text="這是主要翻譯規則；API 模式會直接送給模型，手動模式可複製後交給任何 LLM。", foreground="gray", wraplength=760).pack(anchor="w", padx=(108, 0), pady=(0, 6))
        glossary_row = ttk.Frame(settings); glossary_row.pack(fill="x", pady=4)
        ttk.Label(glossary_row, text="全局 Glossary", width=14).pack(side="left", anchor="n")
        self.glossary_text = tk.Text(glossary_row, height=5, wrap="word")
        self.glossary_text.pack(side="left", fill="both", expand=True)
        ttk.Label(settings, text="每行可寫：原文 = 固定譯名。Glossary 會套用到整本書的 API 翻譯。", foreground="gray").pack(anchor="w", padx=(108, 0), pady=(0, 5))
        polish = ttk.Frame(settings); polish.pack(fill="x", pady=4)
        ttk.Checkbutton(polish, text="翻譯後潤色", variable=self.polish_var, command=self._toggle_polish).pack(side="left", padx=(0, 10))
        self.polish_entry = ttk.Entry(polish, textvariable=self.polish_prompt_var)
        self.polish_entry.pack(side="left", fill="x", expand=True)
        self.polish_entry.configure(state="disabled")

        range_frame = ttk.LabelFrame(translation, text="翻譯範圍", padding=10); range_frame.pack(fill="both", expand=True, pady=(0, 10))
        ttk.Label(range_frame, text="預設：全部。可只選擇部分 XHTML/TXT；未選擇時 API 不會處理該檔案。", foreground="gray").pack(anchor="w")
        list_wrap = ttk.Frame(range_frame); list_wrap.pack(fill="both", expand=True, pady=6)
        self.range_list = tk.Listbox(list_wrap, selectmode=tk.MULTIPLE, height=8, exportselection=False)
        self.range_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.range_list.yview); scroll.pack(side="right", fill="y")
        self.range_list.configure(yscrollcommand=scroll.set)
        range_buttons = ttk.Frame(range_frame); range_buttons.pack(fill="x")
        ttk.Button(range_buttons, text="全選", command=self.select_all_range).pack(side="left")
        ttk.Button(range_buttons, text="清除選擇", command=self.clear_range).pack(side="left", padx=8)

        api = ttk.LabelFrame(translation, text="API 設定", padding=10); api.pack(fill="x", pady=(0, 10))
        self.api_widgets: list[tk.Widget] = []
        self._api_row(api, "API Base URL", self.base_url_var, widgets=self.api_widgets)
        self._api_row(api, "Model", self.model_var, widgets=self.api_widgets)
        key = ttk.Frame(api); key.pack(fill="x", pady=3); self.api_widgets.append(key)
        ttk.Label(key, text="API Key", width=14).pack(side="left")
        key_entry = ttk.Entry(key, textvariable=self.api_key_var, show="*"); key_entry.pack(side="left", fill="x", expand=True); self.api_widgets.append(key_entry)
        self._api_row(api, "每批字數", self.max_chars_var, widgets=self.api_widgets)
        ttk.Label(api, text="API Key 只存在目前程式執行期間，不會寫入 GitHub 或設定檔。", foreground="gray").pack(anchor="w", padx=(108, 0), pady=(3, 5))
        self.api_translate_btn = ttk.Button(api, text="開始 API 翻譯", command=self.api_translate, state="disabled")
        self.api_translate_btn.pack(anchor="w", padx=(108, 0))
        self.manual_btn = ttk.Button(translation, text="複製翻譯 Prompt", command=self.copy_manual_prompt)
        self.manual_btn.pack(anchor="w")

        # Output tab
        self._path_row(output, "輸出 Path", self.output_var, self.select_output_path)
        ttk.Label(output, text="留空時輸出到工作資料夾的 Translated。", foreground="gray").pack(anchor="w", padx=(108, 0), pady=(0, 12))
        row = ttk.Frame(output); row.pack(fill="x")
        ttk.Label(row, text="EPUB 格式", width=14).pack(side="left")
        ttk.Combobox(row, textvariable=self.style_var, values=("直式", "橫式"), state="readonly", width=14).pack(side="left")
        self.validate_btn = ttk.Button(row, text="檢查翻譯", command=self.validate_book, state="disabled"); self.validate_btn.pack(side="left", padx=(18, 8))
        self.build_btn = ttk.Button(row, text="產出 EPUB", command=self.build_book, state="disabled"); self.build_btn.pack(side="left")
        ttk.Label(output, text="API 翻譯或手動翻譯完成後，在這裡檢查，再產出精簡 EPUB。", foreground="gray").pack(anchor="w", pady=(12, 0))

        self.status = tk.StringVar(value="請先選擇輸入 Path 或 EPUB")
        ttk.Separator(root, orient="horizontal").pack(fill="x", pady=(8, 8))
        ttk.Label(root, textvariable=self.status, relief="sunken", anchor="w", padding=7).pack(fill="x")
        self._toggle_api()

    @staticmethod
    def _path_row(parent, label, variable, command):
        row = ttk.Frame(parent); row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=14).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="選擇", command=command).pack(side="left", padx=(8, 0))

    @staticmethod
    def _api_row(parent, label, variable, multiline=False, height=4, widgets=None):
        row = ttk.Frame(parent); row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=14).pack(side="left", anchor="n")
        if multiline:
            widget = tk.Text(row, height=height, wrap="word")
            widget.insert("1.0", variable.get())
            widget.pack(side="left", fill="both", expand=True)
            variable._text_widget = widget  # type: ignore[attr-defined]
        else:
            widget = ttk.Entry(row, textvariable=variable)
            widget.pack(side="left", fill="x", expand=True)
        if widgets is not None: widgets.extend([row, widget])

    def _toggle_api(self):
        state = "normal" if self.mode_var.get() == "api" else "disabled"
        for widget in self.api_widgets:
            try: widget.configure(state=state)
            except tk.TclError: pass
        self.api_translate_btn.configure(state="normal" if self.mode_var.get() == "api" and self.data_book_exists() else "disabled")

    def _toggle_polish(self):
        self.polish_entry.configure(state="normal" if self.polish_var.get() else "disabled")

    def data_book_exists(self):
        return self.workspace is not None and self.book is not None and self.data_book.is_dir()

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
        self.source_btn.config(state="normal"); self.translation_btn.config(state="normal")
        self.validate_btn.config(state="normal"); self.build_btn.config(state="normal")
        self.refresh_range(); self._toggle_api()

    def extract_book(self):
        if not self.epub or not self.workspace or not self.book: return
        if self.workspace.exists():
            if not messagebox.askyesno("重新抽取", f"工作資料夾已存在：\n{self.workspace}\n\n重新抽取會清除其中的 Data。是否繼續？"): return
            data = self.workspace / "Data"
            if data.exists(): shutil.rmtree(data)
        try:
            extract(self.epub, self.workspace / "Data", self.book)
            self.translation_dir.mkdir(parents=True, exist_ok=True)
            self._enable_after_extract(); self.status.set(f"抽取完成：{self.data_book / 'text'}")
        except Exception as exc:
            messagebox.showerror("抽取失敗", self.error_text(exc)); self.status.set("抽取失敗")

    def refresh_range(self):
        if not self.range_list or not self.data_book_exists(): return
        manifest = __import__("json").loads((self.data_book / "manifest.json").read_text(encoding="utf-8"))
        self.range_files = [str(Path(item["text"]).relative_to("text")).replace("\\", "/") for item in manifest["files"] if item.get("paragraph_count")]
        self.range_list.delete(0, tk.END)
        for name in self.range_files: self.range_list.insert(tk.END, name)
        self.select_all_range()

    def select_all_range(self):
        if self.range_list: self.range_list.select_set(0, tk.END)

    def clear_range(self):
        if self.range_list: self.range_list.selection_clear(0, tk.END)

    def selected_range(self):
        if not self.range_list or not self.range_files: return None
        return {self.range_files[i] for i in self.range_list.curselection()}

    def copy_manual_prompt(self):
        prompt = self._translation_prompt_text()
        self.clipboard_clear(); self.clipboard_append(prompt); self.update()
        messagebox.showinfo("已複製", "翻譯 Prompt 已複製到剪貼簿。\n\n你可以把它交給 ChatGPT、Claude、Grok 或其他 LLM。")

    def _translation_prompt_text(self):
        prompt_widget = getattr(self.prompt_var, "_text_widget", None)
        prompt = prompt_widget.get("1.0", "end").strip() if prompt_widget else self.prompt_var.get().strip()
        glossary = self.glossary_text.get("1.0", "end").strip() if self.glossary_text else ""
        parts = [prompt]
        if glossary: parts.append("\n全局 Glossary：\n" + glossary)
        if self.polish_var.get(): parts.append("\n翻譯後潤色：\n" + self.polish_prompt_var.get().strip())
        parts.append("\n請保留所有 [ID] 不變，只翻譯 ID 以下的文字，並以相同順序輸出。")
        return "\n".join(p for p in parts if p)

    def open_source(self):
        if self.data_book_exists(): os.startfile(self.data_book / "text")

    def open_translation(self):
        self.translation_dir.mkdir(parents=True, exist_ok=True); os.startfile(self.translation_dir)

    def api_translate(self):
        if not self.data_book_exists(): return
        api_key = self.api_key_var.get().strip(); base_url = self.base_url_var.get().strip(); model = self.model_var.get().strip()
        try: max_chars = int(self.max_chars_var.get().strip())
        except ValueError:
            messagebox.showerror("API 翻譯失敗", "每批字數必須是整數。"); return
        if max_chars < 1000 or not api_key or not base_url or not model:
            messagebox.showerror("API 翻譯失敗", "請填寫 API Base URL、Model、API Key，且每批字數至少為 1000。"); return
        prompt_widget = getattr(self.prompt_var, "_text_widget", None)
        prompt = prompt_widget.get("1.0", "end").strip() if prompt_widget else DEFAULT_PROMPT
        glossary = self.glossary_text.get("1.0", "end").strip() if self.glossary_text else ""
        try:
            self.api_translate_btn.config(state="disabled"); self.status.set("API 翻譯中，請勿關閉程式……"); self.update_idletasks()
            files, chunks = translate_book(self.data_book, self.workspace / "Translating", base_url, api_key, model, max_chars, prompt, glossary, self.polish_var.get(), self.polish_prompt_var.get(), self.selected_range())
            self.status.set(f"API 翻譯完成：{files} 個 TXT，{chunks} 個批次")
            messagebox.showinfo("API 翻譯完成", f"已完成 {files} 個 TXT，共 {chunks} 個 API 批次。\n\n現在可以執行「檢查翻譯」。")
        except Exception as exc:
            messagebox.showerror("API 翻譯失敗", self.error_text(exc)); self.status.set("API 翻譯失敗")
        finally:
            self._toggle_api()

    def validate_book(self):
        try:
            result = validate(self.data_book, self.workspace / "Translating", complete=True)
            if result:
                messagebox.showerror("檢查失敗", "翻譯資料未通過完整檢查。\n\n請檢查 ID、段落數量、空白翻譯及日文殘留。"); self.status.set("檢查失敗"); return False
            self.status.set("檢查通過"); messagebox.showinfo("檢查通過", "所有翻譯 TXT 均通過檢查。"); return True
        except Exception as exc:
            messagebox.showerror("檢查失敗", self.error_text(exc)); self.status.set("檢查失敗"); return False

    def build_book(self):
        if not self.data_book_exists():
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
