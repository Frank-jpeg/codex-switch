from __future__ import annotations

import importlib.util
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk
from pathlib import Path

import __main__ as rt

if not hasattr(rt, "PROFILE_MODE_OFFICIAL_ONLY"):
    main_path = Path(__file__).with_name("CODEX切换器.py")
    spec = importlib.util.spec_from_file_location("codex_switcher_runtime", main_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载运行时模块：{main_path}")
    runtime_module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("codex_switcher_runtime", runtime_module)
    spec.loader.exec_module(runtime_module)
    rt = runtime_module


PROFILE_MODE_ORDER = [
    rt.PROFILE_MODE_OFFICIAL_ONLY,
    rt.PROFILE_MODE_OFFICIAL_PLUS_PROXY,
    rt.PROFILE_MODE_PROXY_ONLY,
]


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CODEX 切换器 v2")
        self.app_data = rt.load_app_data()
        rt.fit_window_to_screen(
            self.root,
            1120,
            700,
            940,
            600,
            width_ratio=0.58,
            height_ratio=0.64,
            saved_geometry=self.app_data.get("settings", {}).get("main_window_geometry", ""),
        )
        self.root.configure(bg=rt.DARK_BG)
        self.combo_profiles: dict[str, dict] = {}
        self.official_snapshots: dict[str, dict] = {}
        self.settings: dict = {}
        self.active_profile_id = ""
        self.live_state: dict = {}

        self.search_window: object | None = None
        self.repair_window: object | None = None
        self.form_profile_id = ""

        self.current_mode_var = tk.StringVar(value="-")
        self.current_official_var = tk.StringVar(value="-")
        self.current_line_var = tk.StringVar(value="-")
        self.current_base_url_var = tk.StringVar(value="-")
        self.current_auth_kind_var = tk.StringVar(value="-")
        self.session_health_var = tk.StringVar(value="会话状态未自动扫描；需要时点“会话修复”查看")
        self.status_var = tk.StringVar(value="系统就绪")
        self.search_query_var = tk.StringVar()
        self.search_tip_var = tk.StringVar(value="输入关键词后按回车，直接搜索聊天记录")

        self.display_name_var = tk.StringVar()
        self.profile_mode_var = tk.StringVar()
        self.official_snapshot_var = tk.StringVar()
        self.provider_name_var = tk.StringVar()
        self.provider_base_url_var = tk.StringVar()
        self.provider_api_key_var = tk.StringVar()
        self.notes_var = tk.StringVar()
        self.api_key_visible_var = tk.BooleanVar(value=False)

        self.model_check_status_var = tk.StringVar(value="未检测")
        self.model_check_summary_var = tk.StringVar(value="选中一个中转相关档案后，可手动测试线路。")
        self.model_result_text: scrolledtext.ScrolledText | None = None
        self.provider_api_key_entry: ttk.Entry | None = None
        self.api_key_toggle_btn: ttk.Button | None = None
        self.fetch_models_btn: ttk.Button | None = None
        self.health_check_btn: ttk.Button | None = None
        self.copy_models_btn: ttk.Button | None = None
        self.clear_models_btn: ttk.Button | None = None
        self.is_checking_models = False
        self.model_task_serial = 0
        self.model_task_contexts: dict[int, dict] = {}

        self.snapshot_label_to_id: dict[str, str] = {}
        self.snapshot_id_to_label: dict[str, str] = {}

        self.official_frame: tk.Frame | None = None
        self.proxy_frame: tk.Frame | None = None
        self.snapshot_hint_label: tk.Label | None = None
        self.snapshot_combo: ttk.Combobox | None = None
        self.listbox: tk.Listbox | None = None
        self.prepare_official_btn: ttk.Button | None = None
        self.restore_official_btn: ttk.Button | None = None

        self.setup_styles()
        self.build_ui()
        self.register_macos_reopen_handler()
        self.root.protocol("WM_DELETE_WINDOW", self.close_main_window)
        self.refresh(select_active=True)

    def register_macos_reopen_handler(self) -> None:
        try:
            self.root.createcommand("::tk::mac::ReopenApplication", self.show_main_window)
        except tk.TclError:
            pass
        try:
            self.root.createcommand("::tk::mac::Quit", self.close_main_window)
        except tk.TclError:
            pass

    def show_main_window(self, *_args: object) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def save_main_window_geometry(self) -> None:
        try:
            self.root.update_idletasks()
            geometry = self.root.geometry()
        except tk.TclError:
            return
        self.app_data.setdefault("settings", rt.default_settings())
        self.app_data["settings"]["main_window_geometry"] = geometry
        self.persist_app_data()

    def close_main_window(self) -> None:
        self.save_main_window_geometry()
        self.root.destroy()

    def setup_styles(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        self.root.option_add("*TCombobox*Listbox.background", rt.DARK_FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", rt.DARK_TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", rt.DARK_SELECT_BG)
        self.root.option_add("*TCombobox*Listbox.selectForeground", rt.DARK_SELECT_FG)

        style.configure(
            "TButton",
            font=("Microsoft YaHei UI", 12),
            padding=(9, 4),
            background=rt.DARK_PANEL_ALT,
            foreground=rt.DARK_TEXT,
            bordercolor=rt.DARK_BORDER,
            lightcolor=rt.DARK_BORDER,
            darkcolor=rt.DARK_BORDER,
            focuscolor="",
        )
        style.map(
            "TButton",
            background=[("pressed", rt.DARK_BORDER), ("active", rt.DARK_BUTTON_HOVER), ("disabled", rt.DARK_PANEL)],
            foreground=[("disabled", rt.DARK_DISABLED)],
        )
        style.configure(
            "Primary.TButton",
            font=("Microsoft YaHei UI", 12, "bold"),
            background=rt.DARK_ACCENT,
            foreground=rt.DARK_SELECT_FG,
            bordercolor=rt.DARK_ACCENT,
            lightcolor=rt.DARK_ACCENT,
            darkcolor=rt.DARK_ACCENT,
            focuscolor="",
        )
        style.map(
            "Primary.TButton",
            background=[("pressed", rt.DARK_ACCENT_ACTIVE), ("active", rt.DARK_ACCENT_ACTIVE), ("disabled", rt.DARK_PANEL_ALT)],
            foreground=[("disabled", rt.DARK_DISABLED)],
        )
        style.configure(
            "Icon.TButton",
            font=("Microsoft YaHei UI", 12),
            padding=(7, 4),
            background=rt.DARK_PANEL_ALT,
            foreground=rt.DARK_TEXT,
            bordercolor=rt.DARK_BORDER,
            focuscolor="",
        )
        style.map("Icon.TButton", background=[("pressed", rt.DARK_BORDER), ("active", rt.DARK_BUTTON_HOVER)])

        style.configure(
            "TEntry",
            font=("Microsoft YaHei UI", 12),
            fieldbackground=rt.DARK_FIELD,
            foreground=rt.DARK_TEXT,
            insertcolor=rt.DARK_TEXT,
            bordercolor=rt.DARK_BORDER,
            lightcolor=rt.DARK_BORDER,
            darkcolor=rt.DARK_BORDER,
        )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", rt.DARK_PANEL_ALT), ("readonly", rt.DARK_FIELD)],
            foreground=[("disabled", rt.DARK_DISABLED)],
        )
        style.configure(
            "TCombobox",
            fieldbackground=rt.DARK_FIELD,
            foreground=rt.DARK_TEXT,
            background=rt.DARK_PANEL_ALT,
            arrowcolor=rt.DARK_TEXT,
            bordercolor=rt.DARK_BORDER,
            lightcolor=rt.DARK_BORDER,
            darkcolor=rt.DARK_BORDER,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", rt.DARK_FIELD)],
            foreground=[("readonly", rt.DARK_TEXT)],
            selectbackground=[("readonly", rt.DARK_FIELD)],
            selectforeground=[("readonly", rt.DARK_TEXT)],
        )
        style.configure("TCheckbutton", background=rt.DARK_PANEL, foreground=rt.DARK_TEXT, focuscolor="", font=("Microsoft YaHei UI", 12))
        style.map("TCheckbutton", background=[("active", rt.DARK_PANEL)], foreground=[("disabled", rt.DARK_DISABLED)])

        style.configure("Vertical.TScrollbar", background=rt.DARK_PANEL_ALT, bordercolor=rt.DARK_BG, arrowcolor=rt.DARK_MUTED, troughcolor=rt.DARK_BG)
        style.configure("Horizontal.TScrollbar", background=rt.DARK_PANEL_ALT, bordercolor=rt.DARK_BG, arrowcolor=rt.DARK_MUTED, troughcolor=rt.DARK_BG)
        style.configure("Treeview", background=rt.DARK_FIELD, fieldbackground=rt.DARK_FIELD, foreground=rt.DARK_TEXT, bordercolor=rt.DARK_BORDER, rowheight=28)
        style.map("Treeview", background=[("selected", rt.DARK_SELECT_BG)], foreground=[("selected", rt.DARK_SELECT_FG)])
        style.configure("Treeview.Heading", background=rt.DARK_PANEL_ALT, foreground=rt.DARK_TEXT, bordercolor=rt.DARK_BORDER, font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("TNotebook", background=rt.DARK_BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", 12), padding=(10, 5), background=rt.DARK_PANEL_ALT, foreground=rt.DARK_MUTED, bordercolor=rt.DARK_BORDER)
        style.map("TNotebook.Tab", background=[("selected", rt.DARK_PANEL)], foreground=[("selected", rt.DARK_ACCENT), ("active", rt.DARK_TEXT)])

    def build_ui(self) -> None:
        main_wrap = tk.Frame(self.root, bg=rt.DARK_BG)
        main_wrap.pack(fill="both", expand=True, padx=8, pady=8)

        left_frame = tk.Frame(main_wrap, bg=rt.SIDEBAR_BG, highlightbackground=rt.DARK_BORDER, highlightthickness=1, width=350)
        left_frame.pack(side="left", fill="both", padx=(0, 8))
        left_frame.pack_propagate(False)

        left_head = tk.Frame(left_frame, bg=rt.SIDEBAR_BG)
        left_head.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(left_head, text="组合档案", font=("Microsoft YaHei UI", 15, "bold"), bg=rt.SIDEBAR_BG, fg=rt.SIDEBAR_TEXT).pack(side="left")

        left_actions = tk.Frame(left_frame, bg=rt.SIDEBAR_BG)
        left_actions.pack(fill="x", padx=10, pady=(0, 6))
        self.prepare_official_btn = ttk.Button(left_actions, text="接入官方", command=self.prepare_official_login)
        self.prepare_official_btn.pack(side="left", fill="x", expand=True)
        ttk.Button(left_actions, text="保存官方", command=self.save_current_official_account).pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.restore_official_btn = ttk.Button(left_actions, text="恢复状态", command=self.restore_official_login_prep)
        self.restore_official_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        left_actions_row2 = tk.Frame(left_frame, bg=rt.SIDEBAR_BG)
        left_actions_row2.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Button(left_actions_row2, text="导入 CC", command=self.import_cc_switch_profiles).pack(side="left", fill="x", expand=True)

        list_frame = tk.Frame(left_frame, bg=rt.SIDEBAR_BG)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            list_frame,
            font=("Microsoft YaHei UI", 14),
            bg=rt.SIDEBAR_FIELD,
            fg=rt.SIDEBAR_TEXT,
            selectbackground=rt.DARK_SELECT_BG,
            selectforeground=rt.DARK_SELECT_FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=rt.DARK_BORDER,
            yscrollcommand=scrollbar.set,
            activestyle="none",
            exportselection=False,
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.switch_selected())
        self.listbox.bind("<Delete>", lambda _event: self.delete_selected_profile())

        left_bottom = tk.Frame(left_frame, bg=rt.SIDEBAR_BG)
        left_bottom.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(left_bottom, text="切换选中", command=self.switch_selected, style="Primary.TButton").pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(left_bottom, text="新建", command=self.clear_form).pack(side="left", expand=True, fill="x", padx=(4, 4))
        ttk.Button(left_bottom, text="删除", command=self.delete_selected_profile).pack(side="left", expand=True, fill="x", padx=(4, 0))

        right_frame = tk.Frame(main_wrap, bg=rt.DARK_BG)
        right_frame.pack(side="left", fill="both", expand=True)

        status_card = tk.Frame(right_frame, bg=rt.DARK_PANEL, highlightbackground=rt.DARK_BORDER, highlightthickness=1)
        status_card.pack(fill="x", pady=(0, 8))

        status_head = tk.Frame(status_card, bg=rt.DARK_PANEL)
        status_head.pack(fill="x", padx=12, pady=(10, 5))
        tk.Label(status_head, text="当前生效状态", font=("Microsoft YaHei UI", 14, "bold"), bg=rt.DARK_PANEL, fg=rt.DARK_ACCENT).pack(side="left")
        ttk.Button(status_head, text="刷新状态", command=lambda: self.refresh(select_active=False)).pack(side="right")
        ttk.Button(status_head, text="会话修复", command=self.open_repair_window).pack(side="right", padx=(0, 6))
        ttk.Button(status_head, text="高级搜索", command=self.open_search_window).pack(side="right", padx=(0, 6))
        ttk.Button(status_head, text="当前生成档案", command=self.create_profile_from_current_config).pack(side="right", padx=(0, 6))

        status_grid = tk.Frame(status_card, bg=rt.DARK_PANEL)
        status_grid.pack(fill="x", padx=12, pady=(0, 8))
        cards = [
            ("当前模式", self.current_mode_var),
            ("当前官方账号", self.current_official_var),
            ("当前线路", self.current_line_var),
            ("当前 Base URL", self.current_base_url_var),
            ("当前鉴权类型", self.current_auth_kind_var),
        ]
        for index, (title, variable) in enumerate(cards):
            card = self.build_status_card(status_grid, title, variable)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0))
            status_grid.columnconfigure(index, weight=1)

        status_hint = tk.Frame(status_card, bg=rt.DARK_PANEL)
        status_hint.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(status_hint, textvariable=self.session_health_var, bg=rt.DARK_PANEL, fg=rt.DARK_MUTED, font=("Microsoft YaHei UI", 11)).pack(side="left")

        edit_card = tk.Frame(right_frame, bg=rt.DARK_PANEL, highlightbackground=rt.DARK_BORDER, highlightthickness=1)
        edit_card.pack(fill="x", pady=(0, 8))

        edit_head = tk.Frame(edit_card, bg=rt.DARK_PANEL)
        edit_head.pack(fill="x", padx=12, pady=(10, 5))
        tk.Label(edit_head, text="组合档案编辑", font=("Microsoft YaHei UI", 14, "bold"), bg=rt.DARK_PANEL, fg=rt.DARK_TEXT).pack(side="left")
        tk.Label(
            edit_head,
            text="先选模式，再展开需要填写的字段。切换成功后始终建议完全退出并重启 Codex。",
            bg=rt.DARK_PANEL,
            fg=rt.DARK_MUTED,
            font=("Microsoft YaHei UI", 11),
        ).pack(side="right")

        form_wrap = tk.Frame(edit_card, bg=rt.DARK_PANEL)
        form_wrap.pack(fill="x", padx=12, pady=(0, 8))
        form_wrap.columnconfigure(1, weight=1)

        tk.Label(form_wrap, text="档案名称", font=("Microsoft YaHei UI", 12), bg=rt.DARK_PANEL, fg=rt.DARK_MUTED).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(form_wrap, textvariable=self.display_name_var, font=("Microsoft YaHei UI", 13)).grid(row=0, column=1, sticky="we", padx=(8, 0), pady=4)

        tk.Label(form_wrap, text="切换模式", font=("Microsoft YaHei UI", 12), bg=rt.DARK_PANEL, fg=rt.DARK_MUTED).grid(row=1, column=0, sticky="w", pady=4)
        mode_combo = ttk.Combobox(
            form_wrap,
            textvariable=self.profile_mode_var,
            values=[rt.PROFILE_MODE_LABELS[key] for key in PROFILE_MODE_ORDER],
            state="readonly",
            font=("Microsoft YaHei UI", 12),
        )
        mode_combo.grid(row=1, column=1, sticky="we", padx=(8, 0), pady=4)
        mode_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_profile_mode_changed())

        self.official_frame = tk.Frame(form_wrap, bg=rt.DARK_PANEL)
        self.official_frame.grid(row=2, column=0, columnspan=2, sticky="we")
        self.official_frame.columnconfigure(1, weight=1)
        tk.Label(self.official_frame, text="官方账号", font=("Microsoft YaHei UI", 12), bg=rt.DARK_PANEL, fg=rt.DARK_MUTED).grid(row=0, column=0, sticky="w", pady=4)
        self.snapshot_combo = ttk.Combobox(
            self.official_frame,
            textvariable=self.official_snapshot_var,
            state="readonly",
            font=("Microsoft YaHei UI", 12),
        )
        self.snapshot_combo.grid(row=0, column=1, sticky="we", padx=(8, 0), pady=4)
        self.snapshot_hint_label = tk.Label(
            self.official_frame,
            text="如果这里为空，先在 Codex 里登录官方，再点左侧“保存当前官方账号”。",
            bg=rt.DARK_PANEL,
            fg=rt.DARK_MUTED,
            font=("Microsoft YaHei UI", 11),
        )
        self.snapshot_hint_label.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(0, 4))

        self.proxy_frame = tk.Frame(form_wrap, bg=rt.DARK_PANEL)
        self.proxy_frame.grid(row=3, column=0, columnspan=2, sticky="we")
        self.proxy_frame.columnconfigure(1, weight=1)

        tk.Label(self.proxy_frame, text="线路名称", font=("Microsoft YaHei UI", 12), bg=rt.DARK_PANEL, fg=rt.DARK_MUTED).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(self.proxy_frame, textvariable=self.provider_name_var, font=("Microsoft YaHei UI", 13)).grid(row=0, column=1, sticky="we", padx=(8, 0), pady=4)

        tk.Label(self.proxy_frame, text="Base URL", font=("Microsoft YaHei UI", 12), bg=rt.DARK_PANEL, fg=rt.DARK_MUTED).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(self.proxy_frame, textvariable=self.provider_base_url_var, font=("Consolas", 13)).grid(row=1, column=1, sticky="we", padx=(8, 0), pady=4)

        tk.Label(self.proxy_frame, text="API Key", font=("Microsoft YaHei UI", 12), bg=rt.DARK_PANEL, fg=rt.DARK_MUTED).grid(row=2, column=0, sticky="w", pady=4)
        provider_key_row = tk.Frame(self.proxy_frame, bg=rt.DARK_PANEL)
        provider_key_row.grid(row=2, column=1, sticky="we", padx=(8, 0), pady=4)
        provider_key_row.columnconfigure(0, weight=1)
        self.provider_api_key_entry = ttk.Entry(provider_key_row, textvariable=self.provider_api_key_var, font=("Consolas", 13), show="*")
        self.provider_api_key_entry.grid(row=0, column=0, sticky="we")
        self.api_key_toggle_btn = ttk.Button(provider_key_row, text="显示", width=4, command=self.toggle_api_key_visibility, style="Icon.TButton")
        self.api_key_toggle_btn.grid(row=0, column=1, sticky="e", padx=(6, 0))

        tk.Label(self.proxy_frame, text="备注", font=("Microsoft YaHei UI", 12), bg=rt.DARK_PANEL, fg=rt.DARK_MUTED).grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(self.proxy_frame, textvariable=self.notes_var, font=("Microsoft YaHei UI", 12)).grid(row=3, column=1, sticky="we", padx=(8, 0), pady=4)

        edit_actions = tk.Frame(edit_card, bg=rt.DARK_PANEL)
        edit_actions.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(edit_actions, text="保存并切换", command=self.save_and_switch, style="Primary.TButton").pack(side="right")
        ttk.Button(edit_actions, text="仅保存", command=self.save_profile).pack(side="right", padx=(0, 6))
        tk.Label(edit_actions, text="切换写入失败时会同时回滚 auth.json 和 config.toml。", bg=rt.DARK_PANEL, fg=rt.DARK_MUTED, font=("Microsoft YaHei UI", 11)).pack(side="left", pady=(3, 0))

        tools_notebook = ttk.Notebook(right_frame)
        tools_notebook.pack(fill="both", expand=True)

        probe_tab = tk.Frame(tools_notebook, bg=rt.DARK_PANEL)
        tools_notebook.add(probe_tab, text="连通性测试")

        probe_head = tk.Frame(probe_tab, bg=rt.DARK_PANEL)
        probe_head.pack(fill="x", padx=12, pady=(10, 4))
        self.fetch_models_btn = ttk.Button(probe_head, text="获取模型列表", command=self.start_fetch_models)
        self.fetch_models_btn.pack(side="left")
        self.health_check_btn = ttk.Button(probe_head, text="测试连接", command=self.start_health_check, style="Primary.TButton")
        self.health_check_btn.pack(side="left", padx=(6, 0))
        self.copy_models_btn = ttk.Button(probe_head, text="复制结果", command=self.copy_model_results)
        self.copy_models_btn.pack(side="left", padx=(6, 0))
        self.clear_models_btn = ttk.Button(probe_head, text="清空", command=lambda: self.clear_model_results(cancel_running=True))
        self.clear_models_btn.pack(side="left", padx=(6, 0))
        tk.Label(probe_head, textvariable=self.model_check_status_var, font=("Microsoft YaHei UI", 12, "bold"), bg=rt.DARK_PANEL, fg=rt.DARK_ACCENT).pack(side="right")

        tk.Label(probe_tab, textvariable=self.model_check_summary_var, font=("Microsoft YaHei UI", 12), bg=rt.DARK_PANEL, fg=rt.DARK_MUTED).pack(anchor="w", padx=12, pady=(3, 4))
        self.model_result_text = scrolledtext.ScrolledText(
            probe_tab,
            font=("Microsoft YaHei UI", 12),
            bg=rt.DARK_FIELD,
            fg=rt.DARK_TEXT,
            insertbackground=rt.DARK_TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=rt.DARK_BORDER,
        )
        self.model_result_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.set_model_result_text("选中一个中转相关档案后，点击“测试连接”。\n\n这个检测现在只是辅助工具，不再拦截切换。")

        search_tab = tk.Frame(tools_notebook, bg=rt.DARK_PANEL)
        tools_notebook.add(search_tab, text="快捷搜索")
        search_wrap = tk.Frame(search_tab, bg=rt.DARK_PANEL)
        search_wrap.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(search_wrap, text="快速查找聊天记录", font=("Microsoft YaHei UI", 13, "bold"), bg=rt.DARK_PANEL, fg=rt.DARK_TEXT).pack(anchor="w", pady=(0, 8))
        search_row = tk.Frame(search_wrap, bg=rt.DARK_PANEL)
        search_row.pack(fill="x")
        search_entry = ttk.Entry(search_row, textvariable=self.search_query_var, font=("Microsoft YaHei UI", 13))
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<Return>", lambda _event: self.run_quick_search())
        ttk.Button(search_row, text="搜索", command=self.run_quick_search, style="Primary.TButton").pack(side="left", padx=(6, 0))
        tk.Label(search_wrap, textvariable=self.search_tip_var, font=("Microsoft YaHei UI", 12), bg=rt.DARK_PANEL, fg=rt.DARK_MUTED).pack(anchor="w", pady=(8, 0))

        status_bar = tk.Label(self.root, textvariable=self.status_var, anchor="w", bg=rt.DARK_PANEL_ALT, fg=rt.DARK_MUTED, font=("Microsoft YaHei UI", 11), padx=10, pady=4)
        status_bar.pack(side="bottom", fill="x")
        self.update_api_key_visibility()

    def build_status_card(self, master: tk.Misc, title: str, variable: tk.StringVar) -> tk.Frame:
        card = tk.Frame(master, bg=rt.DARK_PANEL_ALT, highlightbackground=rt.DARK_BORDER, highlightthickness=1)
        tk.Label(card, text=title, bg=rt.DARK_PANEL_ALT, fg=rt.DARK_MUTED, font=("Microsoft YaHei UI", 11)).pack(anchor="w", padx=8, pady=(5, 1))
        tk.Label(card, textvariable=variable, bg=rt.DARK_PANEL_ALT, fg=rt.DARK_TEXT, font=("Microsoft YaHei UI", 12, "bold"), justify="left", wraplength=180).pack(anchor="w", padx=8, pady=(0, 6))
        return card

    def mode_key_from_label(self, label: str) -> str:
        for key, value in rt.PROFILE_MODE_LABELS.items():
            if value == label:
                return key
        return rt.PROFILE_MODE_PROXY_ONLY

    def mode_label_from_key(self, mode: str) -> str:
        return rt.PROFILE_MODE_LABELS.get(mode, rt.PROFILE_MODE_LABELS[rt.PROFILE_MODE_PROXY_ONLY])

    def get_ordered_profile_ids(self) -> list[str]:
        return sorted(
            self.combo_profiles,
            key=lambda profile_id: (
                rt.profile_name_compare_key(self.combo_profiles[profile_id].get("display_name", "")),
                profile_id,
            ),
        )

    def get_selected_profile_id(self) -> str:
        if not self.listbox:
            return ""
        selection = self.listbox.curselection()
        if not selection:
            return ""
        ordered_ids = self.get_ordered_profile_ids()
        if selection[0] >= len(ordered_ids):
            return ""
        return ordered_ids[selection[0]]

    def build_profile_list_text(self, profile_id: str, profile: dict) -> str:
        prefix = "★ " if profile_id == self.active_profile_id else "  "
        mode_badge = rt.PROFILE_MODE_BADGES.get(profile.get("profile_type", ""), "[档案]")
        return f"{prefix}{mode_badge} {profile.get('display_name', profile_id)}"

    def refresh_snapshot_choices(self) -> None:
        self.snapshot_label_to_id = {}
        self.snapshot_id_to_label = {}
        labels: list[str] = []
        for snapshot_id in sorted(
            self.official_snapshots,
            key=lambda item: (
                rt.profile_name_compare_key(self.official_snapshots[item].get("display_name", "")),
                item,
            ),
        ):
            label = rt.describe_snapshot(self.official_snapshots[snapshot_id])
            labels.append(label)
            self.snapshot_label_to_id[label] = snapshot_id
            self.snapshot_id_to_label[snapshot_id] = label
        if self.snapshot_combo is not None:
            self.snapshot_combo.configure(values=labels)
        if self.snapshot_hint_label is not None:
            if labels:
                hint = "纯官方和官方+中转都从这里选官方快照；正文已存进 macOS 钥匙串。"
                if rt.has_official_onboarding_session(self.app_data):
                    hint = "你正在官方接入流程中：先去 Codex 用官方账号登录，登录完再点“保存当前官方账号”；如要放弃，可点“恢复接入前状态”。"
                self.snapshot_hint_label.configure(text=hint)
            else:
                hint = "还没有官方账号。先在 Codex 里登录官方，再点左侧“保存当前官方账号”。"
                if rt.has_official_onboarding_session(self.app_data):
                    hint = "你正在官方接入流程中：先去 Codex 用官方账号登录，登录完再点“保存当前官方账号”；如要放弃，可点“恢复接入前状态”。"
                self.snapshot_hint_label.configure(text=hint)

    def refresh(self, select_active: bool, target_profile_id: str = "") -> None:
        self.app_data = rt.load_app_data()
        self.combo_profiles = self.app_data["combo_profiles"]
        self.official_snapshots = self.app_data["official_snapshots"]
        self.settings = self.app_data["settings"]
        self.live_state = rt.summarize_live_state(self.app_data)
        self.active_profile_id = self.live_state["active_profile_id"]
        onboarding_active = rt.has_active_official_onboarding_session(self.app_data, self.live_state)
        onboarding_residue = rt.has_official_onboarding_session(self.app_data) and not onboarding_active

        if onboarding_active and self.live_state.get("provider_id") == "openai":
            self.current_mode_var.set("等待官方登录")
            self.current_official_var.set("待登录")
            self.current_line_var.set("OpenAI Official")
            self.current_base_url_var.set("-")
            self.current_auth_kind_var.set("未登录")
        else:
            self.current_mode_var.set(self.live_state["mode_label"])
            self.current_official_var.set(self.live_state["official_account_label"])
            self.current_line_var.set(self.live_state["current_line_label"])
            self.current_base_url_var.set(self.live_state["base_url_label"])
            self.current_auth_kind_var.set(self.live_state["auth_kind_label"])

        self.session_health_var.set("会话状态未自动扫描；需要时点“会话修复”查看")
        self.refresh_snapshot_choices()
        if self.prepare_official_btn is not None:
            self.prepare_official_btn.configure(state="disabled" if onboarding_active else "normal")
        if self.restore_official_btn is not None:
            self.restore_official_btn.configure(state="normal" if rt.has_official_onboarding_session(self.app_data) else "disabled")

        previous_id = self.get_selected_profile_id()
        if self.listbox is not None:
            self.listbox.delete(0, tk.END)
            ordered_ids = self.get_ordered_profile_ids()
            for profile_id in ordered_ids:
                self.listbox.insert(tk.END, self.build_profile_list_text(profile_id, self.combo_profiles[profile_id]))

            wanted_id = self.active_profile_id if select_active else (target_profile_id or previous_id)
            if wanted_id and wanted_id in self.combo_profiles:
                index = ordered_ids.index(wanted_id)
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(index)
                self.listbox.activate(index)
                self.listbox.see(index)
                self.load_profile_to_form(wanted_id)
            elif not self.form_profile_id:
                self.clear_form(reset_selection=False)

        if onboarding_active:
            self.status_var.set("已进入官方接入流程：去 Codex 登录官方，完成后回来点“保存当前官方账号”")
        elif onboarding_residue:
            self.status_var.set("发现上次未完成的官方接入残留。可点“恢复接入前状态”清理，或重新点“准备接入官方账号”。")
        else:
            self.status_var.set("已刷新当前 live 状态")

    def on_select(self, _event: object) -> None:
        profile_id = self.get_selected_profile_id()
        if profile_id:
            self.load_profile_to_form(profile_id)
            self.clear_model_results(cancel_running=True)

    def on_profile_mode_changed(self) -> None:
        self.update_form_sections()
        self.clear_model_results(cancel_running=True)

    def update_form_sections(self) -> None:
        mode = self.mode_key_from_label(self.profile_mode_var.get())
        if self.official_frame is not None:
            if mode in {rt.PROFILE_MODE_OFFICIAL_ONLY, rt.PROFILE_MODE_OFFICIAL_PLUS_PROXY}:
                self.official_frame.grid()
            else:
                self.official_frame.grid_remove()
        if self.proxy_frame is not None:
            if mode in {rt.PROFILE_MODE_OFFICIAL_PLUS_PROXY, rt.PROFILE_MODE_PROXY_ONLY}:
                self.proxy_frame.grid()
            else:
                self.proxy_frame.grid_remove()

    def update_api_key_visibility(self) -> None:
        visible = self.api_key_visible_var.get()
        if self.provider_api_key_entry is not None:
            self.provider_api_key_entry.configure(show="" if visible else "*")
        if self.api_key_toggle_btn is not None:
            self.api_key_toggle_btn.configure(text="隐藏" if visible else "显示")

    def toggle_api_key_visibility(self) -> None:
        self.api_key_visible_var.set(not self.api_key_visible_var.get())
        self.update_api_key_visibility()

    def set_form_from_profile(self, profile: dict) -> None:
        self.display_name_var.set(profile.get("display_name", ""))
        self.profile_mode_var.set(self.mode_label_from_key(profile.get("profile_type", rt.PROFILE_MODE_PROXY_ONLY)))
        snapshot_id = str(profile.get("official_snapshot_id") or "")
        self.official_snapshot_var.set(self.snapshot_id_to_label.get(snapshot_id, ""))
        self.provider_name_var.set(profile.get("provider_name", ""))
        self.provider_base_url_var.set(profile.get("provider_base_url", ""))
        self.provider_api_key_var.set(profile.get("provider_api_key", ""))
        self.notes_var.set(profile.get("notes", ""))
        self.update_form_sections()
        self.update_api_key_visibility()

    def load_profile_to_form(self, profile_id: str) -> None:
        profile = self.combo_profiles.get(profile_id)
        if not profile:
            return
        self.form_profile_id = profile_id
        self.set_form_from_profile(profile)

    def clear_form(self, reset_selection: bool = True) -> None:
        self.form_profile_id = ""
        if reset_selection and self.listbox is not None:
            self.listbox.selection_clear(0, tk.END)
        default_mode = rt.PROFILE_MODE_OFFICIAL_PLUS_PROXY if self.official_snapshots else rt.PROFILE_MODE_PROXY_ONLY
        self.display_name_var.set("")
        self.profile_mode_var.set(self.mode_label_from_key(default_mode))
        first_snapshot_label = next(iter(self.snapshot_label_to_id.keys()), "")
        self.official_snapshot_var.set(first_snapshot_label)
        self.provider_name_var.set("")
        self.provider_base_url_var.set("")
        self.provider_api_key_var.set("")
        self.notes_var.set("")
        self.update_form_sections()
        self.update_api_key_visibility()
        self.clear_model_results(cancel_running=True)
        self.status_var.set("表单已清空，可新建组合档案")

    def resolve_selected_snapshot_id(self) -> str:
        return self.snapshot_label_to_id.get(self.official_snapshot_var.get().strip(), "")

    def resolve_profile_id_for_save(self, display_name: str) -> str:
        if self.form_profile_id and self.form_profile_id in self.combo_profiles:
            return self.form_profile_id
        selected_id = self.get_selected_profile_id()
        if selected_id and selected_id in self.combo_profiles:
            return selected_id
        normalized = display_name.casefold()
        for profile_id, existing in self.combo_profiles.items():
            if str(existing.get("display_name") or "").casefold() == normalized:
                return profile_id
        return rt.make_profile_id(display_name, set(self.combo_profiles.keys()))

    def collect_form(self) -> tuple[str, dict]:
        display_name = self.display_name_var.get().strip()
        mode = self.mode_key_from_label(self.profile_mode_var.get())
        official_snapshot_id = self.resolve_selected_snapshot_id()
        provider_name = self.provider_name_var.get().strip()
        provider_base_url = self.provider_base_url_var.get().strip()
        provider_api_key = self.provider_api_key_var.get().strip()
        notes = self.notes_var.get().strip()

        if not display_name:
            raise ValueError("档案名称不能为空。")
        if mode in {rt.PROFILE_MODE_OFFICIAL_ONLY, rt.PROFILE_MODE_OFFICIAL_PLUS_PROXY} and not official_snapshot_id:
            raise ValueError("请先选择一个官方账号。")
        if mode in {rt.PROFILE_MODE_OFFICIAL_PLUS_PROXY, rt.PROFILE_MODE_PROXY_ONLY}:
            if not provider_name:
                raise ValueError("中转线路名称不能为空。")
            if not provider_base_url:
                raise ValueError("Base URL 不能为空。")
            if not provider_api_key:
                raise ValueError("API Key 不能为空。")
            provider_base_url = rt.normalize_api_base_url(provider_base_url)
        if mode == rt.PROFILE_MODE_OFFICIAL_ONLY:
            provider_name = ""
            provider_base_url = ""
            provider_api_key = ""

        profile_id = self.resolve_profile_id_for_save(display_name)
        existing = self.combo_profiles.get(profile_id, {})
        previous_signature = rt.build_profile_signature(existing) if existing else ()
        profile = rt.sanitize_combo_profile(
            profile_id,
            {
                "profile_id": profile_id,
                "profile_type": mode,
                "display_name": display_name,
                "official_snapshot_id": official_snapshot_id,
                "provider_name": provider_name,
                "provider_base_url": provider_base_url,
                "provider_api_key": provider_api_key,
                "provider_mode": rt.PROVIDER_MODE_RESPONSES_DIRECT,
                "verification_status": existing.get("verification_status", rt.VERIFICATION_NEVER),
                "last_verified_at": existing.get("last_verified_at", ""),
                "last_verified_summary": existing.get("last_verified_summary", ""),
                "created_at": existing.get("created_at", rt.now_iso_text()),
                "updated_at": rt.now_iso_text(),
                "last_used_at": existing.get("last_used_at", ""),
                "notes": notes,
            },
        )
        if previous_signature and previous_signature != rt.build_profile_signature(profile):
            profile["verification_status"] = rt.VERIFICATION_NEVER
            profile["last_verified_at"] = ""
            profile["last_verified_summary"] = ""
        return profile_id, profile

    def persist_app_data(self) -> None:
        rt.save_app_data(self.app_data)

    def save_profile(self) -> None:
        try:
            profile_id, profile = self.collect_form()
            existed = profile_id in self.combo_profiles
            self.app_data["combo_profiles"][profile_id] = profile
            self.form_profile_id = profile_id
            self.persist_app_data()
            self.refresh(select_active=False, target_profile_id=profile_id)
            self.status_var.set("组合档案已更新" if existed else "组合档案已保存")
            messagebox.showinfo("保存成功", "组合档案已更新。" if existed else "组合档案已保存。", parent=self.root)
        except Exception as exc:
            self.status_var.set(f"保存失败: {exc}")
            messagebox.showerror("保存失败", str(exc), parent=self.root)

    def switch_to_profile(self, profile_id: str) -> None:
        if rt.has_active_official_onboarding_session(self.app_data):
            raise ValueError("当前正在接入官方账号。请先完成保存，或点“恢复接入前状态”。")

        profile = self.combo_profiles.get(profile_id)
        if not profile:
            raise ValueError("组合档案不存在。")

        mode = profile.get("profile_type", "")

        official_label = "-"
        snapshot_id = profile.get("official_snapshot_id", "")
        if snapshot_id:
            official_label = rt.describe_snapshot(self.official_snapshots.get(snapshot_id, {}))
        line_label = profile.get("provider_name") or "官方直连"
        base_url = profile.get("provider_base_url") or "-"
        confirm_lines = [
            f"目标档案：{profile.get('display_name', profile_id)}",
            f"模式：{rt.PROFILE_MODE_LABELS.get(mode, mode)}",
            f"官方账号：{official_label}",
            f"线路：{line_label}",
            f"Base URL：{base_url}",
            "",
            "继续切换吗？",
        ]
        confirmed = messagebox.askyesno("确认切换", "\n".join(confirm_lines), parent=self.root)
        if not confirmed:
            self.status_var.set("已取消切换")
            return

        result = rt.apply_combo_profile(profile, self.app_data)
        profile["last_used_at"] = rt.now_iso_text()
        target_snapshot_id = result.get("official_snapshot_id", "")
        if target_snapshot_id and target_snapshot_id in self.official_snapshots:
            self.official_snapshots[target_snapshot_id]["last_used_at"] = rt.now_iso_text()
        self.persist_app_data()
        self.refresh(select_active=True)

        restart_text = "切换成功。\n\n请完全退出并重启 Codex。"
        if result["current_provider_family"] != result["target_provider_family"]:
            open_repair = messagebox.askyesno(
                "切换成功",
                restart_text + "\n\n这次属于 官方 <-> custom 家族切换。\n如遇到旧会话不显示或供应商不一致，可选做一次会话修复。\n\n现在打开会话修复吗？",
                parent=self.root,
            )
            if open_repair:
                self.open_repair_window()
        else:
            messagebox.showinfo("切换成功", restart_text, parent=self.root)
        self.status_var.set("切换成功，等待你重启 Codex")

    def switch_selected(self) -> None:
        try:
            profile_id = self.get_selected_profile_id()
            if not profile_id:
                raise ValueError("请先选中一个组合档案。")
            self.switch_to_profile(profile_id)
        except Exception as exc:
            self.status_var.set(f"切换失败: {exc}")
            messagebox.showerror("切换失败", str(exc), parent=self.root)

    def save_and_switch(self) -> None:
        try:
            profile_id, profile = self.collect_form()
            self.app_data["combo_profiles"][profile_id] = profile
            self.form_profile_id = profile_id
            self.persist_app_data()
            self.refresh(select_active=False, target_profile_id=profile_id)
            self.switch_to_profile(profile_id)
        except Exception as exc:
            self.status_var.set(f"操作失败: {exc}")
            messagebox.showerror("操作失败", str(exc), parent=self.root)

    def delete_selected_profile(self) -> None:
        try:
            profile_id = self.get_selected_profile_id()
            if not profile_id:
                raise ValueError("请先选中一个组合档案。")
            profile = self.combo_profiles.get(profile_id)
            if not profile:
                raise ValueError("组合档案不存在。")
            extra_tip = ""
            if profile_id == self.active_profile_id:
                extra_tip = "\n当前正在使用这个档案，删除只会删保存记录，不会改 live 配置。"
            confirmed = messagebox.askyesno(
                "确认删除",
                f"确定删除“{profile.get('display_name', profile_id)}”吗？{extra_tip}",
                parent=self.root,
            )
            if not confirmed:
                self.status_var.set("已取消删除")
                return
            self.app_data["combo_profiles"].pop(profile_id, None)
            self.persist_app_data()
            self.form_profile_id = ""
            self.refresh(select_active=False)
            self.status_var.set("组合档案已删除")
        except Exception as exc:
            self.status_var.set(f"删除失败: {exc}")
            messagebox.showerror("删除失败", str(exc), parent=self.root)

    def run_quick_search(self) -> None:
        try:
            query = self.search_query_var.get().strip()
            if not query:
                raise ValueError("请输入搜索关键词")
            self.open_search_window()
            if not self.search_window:
                return
            self.search_window.query_var.set(query)
            self.search_window.focus()
            self.search_window.run_search()
            self.search_tip_var.set(f"已搜索: {query}")
        except Exception as exc:
            self.search_tip_var.set(f"搜索失败: {exc}")
            messagebox.showerror("搜索失败", str(exc), parent=self.root)

    def open_search_window(self) -> None:
        if self.search_window and self.search_window.is_alive():
            self.search_window.focus()
            return
        self.search_window = rt.ChatSearchWindow(self.root)

    def open_repair_window(self) -> None:
        if self.repair_window and self.repair_window.is_alive():
            self.repair_window.focus()
            return
        self.repair_window = rt.SessionRepairWindow(self.root)

    def prepare_official_login(self) -> None:
        try:
            confirmed = messagebox.askyesno(
                "准备接入官方账号",
                "这会先备份你当前的纯中转 live 状态，然后把 live 配置切成“官方可登录准备态”。\n\n请先确认 Codex 已经完全退出。\n\n接下来你需要：\n1. 点确定，完成准备\n2. 再打开 Codex，用官方账号登录\n3. 回到这里点“保存当前官方账号”\n\n现在继续吗？",
                parent=self.root,
            )
            if not confirmed:
                self.status_var.set("已取消准备官方账号")
                return
            rt.prepare_live_state_for_official_login(self.app_data)
            self.refresh(select_active=False)
            messagebox.showinfo(
                "已准备完成",
                "已切到官方可登录准备态。\n\n现在再打开 Codex，用官方账号登录。\n登录完成后，回到这里点“保存当前官方账号”。",
                parent=self.root,
            )
        except Exception as exc:
            self.status_var.set(f"准备官方账号失败: {exc}")
            messagebox.showerror("准备官方账号失败", str(exc), parent=self.root)

    def restore_official_login_prep(self) -> None:
        try:
            confirmed = messagebox.askyesno(
                "恢复接入前状态",
                "这会把当前 live 配置恢复到你开始接入官方账号之前的状态。\n\n现在继续吗？",
                parent=self.root,
            )
            if not confirmed:
                self.status_var.set("已取消恢复接入前状态")
                return
            state = rt.restore_live_state_from_official_onboarding(self.app_data)
            self.refresh(select_active=False)
            warning = str(state.get("restore_warning") or "").strip()
            if warning:
                self.status_var.set(warning)
                messagebox.showwarning("已清理残留接入状态", warning, parent=self.root)
            else:
                self.status_var.set(f"已恢复到接入前状态：{state['mode_label']} / {state['current_line_label']}")
                messagebox.showinfo("恢复成功", "已恢复到接入前状态。请按需要重启 Codex。", parent=self.root)
        except Exception as exc:
            self.status_var.set(f"恢复接入前状态失败: {exc}")
            messagebox.showerror("恢复接入前状态失败", str(exc), parent=self.root)

    def save_current_official_account(self) -> None:
        try:
            auth_text = rt.read_text(rt.AUTH_PATH)
            if rt.has_active_official_onboarding_session(self.app_data) and rt.detect_auth_kind(auth_text) != rt.AUTH_KIND_OFFICIAL:
                raise ValueError("你还没在 Codex 里完成官方登录。请先完全退出并重启 Codex，用官方账号登录后再回来保存。")
            default_name = rt.detect_official_identity_hint(auth_text) or f"官方账号{len(self.official_snapshots) + 1}"
            name = simpledialog.askstring("保存当前官方账号", "给这个官方账号起个名字：", initialvalue=default_name, parent=self.root)
            if name is None:
                self.status_var.set("已取消保存官方账号")
                return
            meta = rt.save_current_official_snapshot(self.app_data, name)
            created_profile_id, created_new_profile = rt.ensure_official_only_profile_for_snapshot(self.app_data, meta)
            if rt.has_official_onboarding_session(self.app_data):
                rt.clear_official_onboarding(self.app_data)
            self.refresh(select_active=False)
            self.status_var.set("官方账号已保存到 macOS 钥匙串")
            extra = ""
            if created_new_profile:
                extra = f"\n\n已自动创建档案：{self.combo_profiles.get(created_profile_id, {}).get('display_name', created_profile_id)}"
            messagebox.showinfo("保存成功", f"已保存官方账号：{rt.describe_snapshot(meta)}{extra}", parent=self.root)
        except Exception as exc:
            self.status_var.set(f"保存官方账号失败: {exc}")
            messagebox.showerror("保存官方账号失败", str(exc), parent=self.root)

    def create_profile_from_current_config(self) -> None:
        try:
            draft = rt.build_profile_from_live_state(self.app_data)
            self.form_profile_id = ""
            if self.listbox is not None:
                self.listbox.selection_clear(0, tk.END)
            self.set_form_from_profile(draft)
            self.status_var.set("已把当前 live 配置读入表单，可改名后保存")
        except Exception as exc:
            self.status_var.set(f"生成失败: {exc}")
            messagebox.showerror("生成失败", str(exc), parent=self.root)

    def choose_cc_switch_profiles(self, cc_profiles: list[dict], skipped_invalid: int) -> list[dict] | None:
        existing_proxy_pairs = {
            (
                rt.normalize_base_url_for_compare(profile.get("provider_base_url", "")),
                profile.get("provider_api_key", "").strip(),
            )
            for profile in self.combo_profiles.values()
            if profile.get("profile_type") == rt.PROFILE_MODE_PROXY_ONLY
        }

        candidates = []
        for index, profile in enumerate(cc_profiles):
            pair = (
                rt.normalize_base_url_for_compare(profile.get("base_url", "")),
                profile.get("api_key", "").strip(),
            )
            duplicate = pair in existing_proxy_pairs
            candidates.append(
                {
                    "index": index,
                    "profile": profile,
                    "duplicate": duplicate,
                    "status": "已存在" if duplicate else "可导入",
                }
            )

        result: dict[str, list[dict] | None] = {"profiles": None}
        dialog = tk.Toplevel(self.root)
        dialog.title("导入 CC Switch 线路")
        rt.fit_window_to_screen(dialog, 900, 520, 780, 420)
        dialog.configure(bg=rt.DARK_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = tk.Frame(dialog, bg=rt.DARK_BG)
        outer.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(outer, text=f"把 CC Switch 的单线路导入成“纯中转”组合档案（无效跳过 {skipped_invalid} 条）", bg=rt.DARK_BG, fg=rt.DARK_TEXT, font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(0, 10))

        table_frame = tk.Frame(outer, bg=rt.DARK_PANEL, highlightbackground=rt.DARK_BORDER, highlightthickness=1)
        table_frame.pack(fill="both", expand=True)
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical")
        y_scroll.pack(side="right", fill="y")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal")
        x_scroll.pack(side="bottom", fill="x")
        tree = ttk.Treeview(
            table_frame,
            columns=("status", "name", "base_url", "api_key"),
            show="headings",
            selectmode="extended",
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )
        tree.heading("status", text="状态")
        tree.heading("name", text="名称")
        tree.heading("base_url", text="Base URL")
        tree.heading("api_key", text="API Key")
        tree.column("status", width=80, anchor="center", stretch=False)
        tree.column("name", width=210, anchor="w")
        tree.column("base_url", width=360, anchor="w")
        tree.column("api_key", width=120, anchor="w", stretch=False)
        tree.tag_configure("duplicate", foreground=rt.DARK_DISABLED)
        tree.pack(side="left", fill="both", expand=True)
        y_scroll.config(command=tree.yview)
        x_scroll.config(command=tree.xview)

        importable_ids: list[str] = []
        for candidate in candidates:
            profile = candidate["profile"]
            item_id = str(candidate["index"])
            tag = "duplicate" if candidate["duplicate"] else ""
            tree.insert(
                "",
                "end",
                iid=item_id,
                values=(candidate["status"], profile["name"], profile["base_url"], rt.mask_secret(profile["api_key"])),
                tags=(tag,) if tag else (),
            )
            if not candidate["duplicate"]:
                importable_ids.append(item_id)

        if importable_ids:
            tree.selection_set(*importable_ids)

        summary_var = tk.StringVar()

        def selected_importable_profiles() -> list[dict]:
            selected: list[dict] = []
            for item_id in tree.selection():
                candidate = candidates[int(item_id)]
                if not candidate["duplicate"]:
                    selected.append(candidate["profile"])
            return selected

        def update_summary(_event: object | None = None) -> None:
            summary_var.set(f"已选 {len(selected_importable_profiles())} 条 / 可导入 {len(importable_ids)} 条")

        def cancel() -> None:
            result["profiles"] = None
            dialog.destroy()

        def confirm() -> None:
            selected = selected_importable_profiles()
            if not selected:
                messagebox.showwarning("未选择", "请至少选择一条可导入线路。", parent=dialog)
                return
            result["profiles"] = selected
            dialog.destroy()

        tree.bind("<<TreeviewSelect>>", update_summary)

        action_row = tk.Frame(outer, bg=rt.DARK_BG)
        action_row.pack(fill="x", pady=(12, 0))
        tk.Label(action_row, textvariable=summary_var, bg=rt.DARK_BG, fg=rt.DARK_MUTED, font=("Microsoft YaHei UI", 12)).pack(side="left")
        ttk.Button(action_row, text="取消", command=cancel).pack(side="right")
        ttk.Button(action_row, text="导入选中", command=confirm, style="Primary.TButton").pack(side="right", padx=(0, 8))

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        update_summary()
        dialog.wait_window()
        return result["profiles"]

    def import_cc_switch_profiles(self) -> None:
        try:
            cc_profiles, skipped_invalid = rt.load_cc_switch_codex_profiles()
            if not cc_profiles:
                raise ValueError("CC Switch 里没有可导入的 Codex 线路。")
            selected_profiles = self.choose_cc_switch_profiles(cc_profiles, skipped_invalid)
            if selected_profiles is None:
                self.status_var.set("已取消导入")
                return

            existing_proxy_pairs = {
                (
                    rt.normalize_base_url_for_compare(profile.get("provider_base_url", "")),
                    profile.get("provider_api_key", "").strip(),
                )
                for profile in self.combo_profiles.values()
                if profile.get("profile_type") == rt.PROFILE_MODE_PROXY_ONLY
            }

            imported_count = 0
            skipped_duplicate = 0
            for raw_profile in selected_profiles:
                pair = (
                    rt.normalize_base_url_for_compare(raw_profile.get("base_url", "")),
                    raw_profile.get("api_key", "").strip(),
                )
                if pair in existing_proxy_pairs:
                    skipped_duplicate += 1
                    continue
                display_name = f"纯中转-{raw_profile['name']}"
                profile_id = rt.make_profile_id(display_name, set(self.combo_profiles.keys()))
                self.app_data["combo_profiles"][profile_id] = rt.sanitize_combo_profile(
                    profile_id,
                    {
                        "profile_type": rt.PROFILE_MODE_PROXY_ONLY,
                        "display_name": display_name,
                        "official_snapshot_id": "",
                        "provider_name": raw_profile["name"],
                        "provider_base_url": rt.normalize_api_base_url(raw_profile["base_url"]),
                        "provider_api_key": raw_profile["api_key"],
                        "provider_mode": rt.PROVIDER_MODE_RESPONSES_DIRECT,
                        "verification_status": rt.VERIFICATION_NEVER,
                        "notes": "从 CC Switch 导入",
                    },
                )
                existing_proxy_pairs.add(pair)
                imported_count += 1

            if imported_count == 0:
                self.status_var.set("没有导入到新内容")
                messagebox.showinfo("无需导入", f"重复跳过：{skipped_duplicate} 条\n无效跳过：{skipped_invalid} 条", parent=self.root)
                return

            self.persist_app_data()
            self.refresh(select_active=False)
            self.status_var.set(f"已导入 {imported_count} 条纯中转档案")
            messagebox.showinfo("导入成功", f"已导入：{imported_count} 条\n重复跳过：{skipped_duplicate} 条\n无效跳过：{skipped_invalid} 条", parent=self.root)
        except Exception as exc:
            self.status_var.set(f"导入失败: {exc}")
            messagebox.showerror("导入失败", str(exc), parent=self.root)

    def set_model_result_text(self, content: str) -> None:
        if not self.model_result_text:
            return
        self.model_result_text.configure(state="normal")
        self.model_result_text.delete("1.0", tk.END)
        self.model_result_text.insert("1.0", content)
        self.model_result_text.configure(state="disabled")

    def copy_model_results(self) -> None:
        try:
            if not self.model_result_text:
                return
            content = self.model_result_text.get("1.0", tk.END).strip()
            if not content:
                raise ValueError("当前没有可复制的检测结果。")
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.status_var.set("检测结果已复制到剪贴板")
        except Exception as exc:
            self.status_var.set(f"复制失败: {exc}")
            messagebox.showerror("复制失败", str(exc), parent=self.root)

    def clear_model_results(self, cancel_running: bool = False) -> None:
        if cancel_running:
            self.model_task_serial += 1
            self.is_checking_models = False
            self.model_task_contexts.clear()
            self.set_model_buttons_state(False)
        self.model_check_status_var.set("未检测")
        self.model_check_summary_var.set("选中一个中转相关档案后，可手动测试线路。")
        self.set_model_result_text("选中一个中转相关档案后，点击“测试连接”。")

    def set_model_buttons_state(self, disabled: bool) -> None:
        state = "disabled" if disabled else "normal"
        for widget in (self.fetch_models_btn, self.health_check_btn, self.copy_models_btn, self.clear_models_btn):
            if widget is not None:
                widget.configure(state=state)

    def resolve_probe_inputs_from_form(self) -> tuple[str, str]:
        mode = self.mode_key_from_label(self.profile_mode_var.get())
        if mode == rt.PROFILE_MODE_OFFICIAL_ONLY:
            raise ValueError("纯官方档案不需要测试连接。")
        base_url = self.provider_base_url_var.get().strip()
        api_key = self.provider_api_key_var.get().strip()
        if not base_url:
            raise ValueError("请先填写 Base URL。")
        if not api_key:
            raise ValueError("请先填写 API Key。")
        return rt.normalize_api_base_url(base_url), api_key

    def resolve_probe_profile_id(self) -> str:
        if self.form_profile_id and self.form_profile_id in self.combo_profiles:
            return self.form_profile_id
        selected_id = self.get_selected_profile_id()
        if selected_id and selected_id in self.combo_profiles:
            return selected_id
        return ""

    def update_verification_for_profile(self, profile_id: str, status: str, summary: str) -> None:
        profile = self.app_data["combo_profiles"].get(profile_id)
        if not profile:
            return
        profile["verification_status"] = status
        profile["last_verified_at"] = rt.now_iso_text()
        profile["last_verified_summary"] = summary
        profile["updated_at"] = rt.now_iso_text()
        self.persist_app_data()

    def start_fetch_models(self) -> None:
        if self.is_checking_models:
            self.status_var.set("已有检测任务在进行中")
            return
        try:
            base_url, api_key = self.resolve_probe_inputs_from_form()
        except Exception as exc:
            self.model_check_status_var.set("不可用")
            self.model_check_summary_var.set(str(exc))
            self.set_model_result_text(str(exc))
            self.status_var.set(f"检测失败: {exc}")
            return
        self.is_checking_models = True
        self.model_task_serial += 1
        task_id = self.model_task_serial
        self.model_task_contexts[task_id] = {"action": "fetch"}
        self.set_model_buttons_state(True)
        self.model_check_status_var.set("检测中")
        self.model_check_summary_var.set("正在获取 /models ...")
        self.set_model_result_text("正在请求 /models，请稍候...")
        self.status_var.set("正在获取模型列表")
        threading.Thread(target=self.run_model_fetch_worker, args=(base_url, api_key, task_id), daemon=True).start()

    def start_health_check(self) -> None:
        if self.is_checking_models:
            self.status_var.set("已有检测任务在进行中")
            return
        try:
            base_url, api_key = self.resolve_probe_inputs_from_form()
        except Exception as exc:
            self.model_check_status_var.set("不可用")
            self.model_check_summary_var.set(str(exc))
            self.set_model_result_text(str(exc))
            self.status_var.set(f"检测失败: {exc}")
            return
        self.is_checking_models = True
        self.model_task_serial += 1
        task_id = self.model_task_serial
        self.model_task_contexts[task_id] = {
            "action": "health_check",
            "profile_id": self.resolve_probe_profile_id(),
        }
        self.set_model_buttons_state(True)
        self.model_check_status_var.set("检测中")
        self.model_check_summary_var.set("正在执行 /models + 最小聊天请求 双重检测...")
        self.set_model_result_text("步骤 1/2：请求 /models\n步骤 2/2：最小聊天请求\n\n请稍候...")
        self.status_var.set("正在测试连接")
        threading.Thread(target=self.run_health_check_worker, args=(base_url, api_key, task_id), daemon=True).start()

    def finish_model_task(self, task_id: int) -> None:
        self.is_checking_models = False
        self.set_model_buttons_state(False)
        self.model_task_contexts.pop(task_id, None)

    def apply_probe_result_to_profile(self, task_id: int, ok: bool, summary_text: str) -> None:
        context = self.model_task_contexts.get(task_id, {})
        if context.get("action") != "health_check":
            return
        profile_id = context.get("profile_id", "")
        if not profile_id:
            return
        self.update_verification_for_profile(profile_id, rt.VERIFICATION_SUCCESS if ok else rt.VERIFICATION_FAILED, summary_text)
        self.refresh(select_active=False, target_profile_id=profile_id)

    def update_model_panel(self, status_text: str, summary_text: str, body_text: str, ok: bool, status_bar_text: str, task_id: int) -> None:
        if task_id != self.model_task_serial:
            return
        self.apply_probe_result_to_profile(task_id, ok, summary_text)
        self.model_check_status_var.set(status_text)
        self.model_check_summary_var.set(summary_text)
        self.set_model_result_text(body_text)
        self.status_var.set(status_bar_text)
        self.finish_model_task(task_id)

    def handle_model_task_error(self, exc: Exception, action_label: str, task_id: int) -> None:
        message = str(exc)

        def _apply() -> None:
            self.update_model_panel("不可用", message, f"{action_label}失败\n\n{message}", False, f"{action_label}失败: {message}", task_id)

        self.root.after(0, _apply)

    def run_model_fetch_worker(self, base_url: str, api_key: str, task_id: int) -> None:
        try:
            models = rt.fetch_models(base_url, api_key)
            lines = [
                "模型列表获取成功",
                "",
                f"Base URL: {base_url}",
                f"模型数量: {len(models)}",
                "",
                "模型列表：",
                *models,
            ]
            summary = f"获取到 {len(models)} 个模型"
            self.root.after(0, lambda: self.update_model_panel("可用", summary, "\n".join(lines), True, "模型列表获取成功", task_id))
        except Exception as exc:
            self.handle_model_task_error(exc, "获取模型列表", task_id)

    def run_health_check_worker(self, base_url: str, api_key: str, task_id: int) -> None:
        try:
            models = rt.fetch_models(base_url, api_key)
            probe_model = rt.pick_probe_model(models)
            try:
                rt.probe_chat(base_url, api_key, probe_model)
            except Exception as exc:
                lines = [
                    "双重检测未通过",
                    "",
                    "步骤 1/2：/models 成功",
                    f"模型数量: {len(models)}",
                    "",
                    f"步骤 2/2：/chat/completions 失败（检测模型：{probe_model}）",
                    str(exc),
                    "",
                    "模型列表：",
                    *models,
                ]
                summary = "模型列表可获取，但聊天请求失败"
                self.root.after(0, lambda: self.update_model_panel("不可用", summary, "\n".join(lines), False, f"测试连接失败: {exc}", task_id))
                return
            lines = [
                "双重检测通过",
                "",
                "步骤 1/2：/models 成功",
                f"模型数量: {len(models)}",
                "",
                "步骤 2/2：/chat/completions 成功",
                f"检测模型: {probe_model}",
                "",
                "模型列表：",
                *models,
            ]
            summary = f"已验证成功，检测模型：{probe_model}"
            self.root.after(0, lambda: self.update_model_panel("可用", summary, "\n".join(lines), True, "测试连接通过", task_id))
        except Exception as exc:
            self.handle_model_task_error(exc, "测试连接", task_id)
