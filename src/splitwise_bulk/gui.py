"""Simplified desktop app: upload CSV → review → upload to Splitwise."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from splitwise_bulk.api import SplitwiseClient, SplitwiseError
from splitwise_bulk.importer import import_transactions
from splitwise_bulk.local_server import DEFAULT_PORT, LocalOrderServer
from splitwise_bulk.models import GroupContext, SplitMode
from splitwise_bulk.order_ingest import order_key, orders_to_transactions
from splitwise_bulk.settings import get_saved_api_key, load_app_env, load_settings, save_settings
from splitwise_bulk.simple_csv import CURRENCY, parse_expense_csv, split_mode_csv_value

# ── Theme ────────────────────────────────────────────────────────────────────
TEAL = "#01696F"
TEAL_DARK = "#0C4E54"
TEAL_LIGHT = "#E6F3F4"
BG = "#F4F3EF"
WHITE = "#FFFFFF"
SURFACE_ALT = "#EEEDEA"
BORDER = "#C8C5BD"
TEXT = "#1C1B18"
TEXT_SECONDARY = "#44433E"
TEXT_MUTED = "#5E5C57"
SUCCESS = "#2D6A1E"
SUCCESS_BG = "#E8F5E4"
ERROR = "#9B1B5A"
ERROR_BG = "#FCE8F3"
WARNING_BG = "#FFF3E6"
WARNING = "#8B4513"

FONT_FAMILY = "Helvetica Neue"
FONT_H1 = (FONT_FAMILY, 20, "bold")
FONT_H2 = (FONT_FAMILY, 15, "bold")
FONT_BODY = (FONT_FAMILY, 13)
FONT_TABLE = (FONT_FAMILY, 13)
FONT_TABLE_HEAD = (FONT_FAMILY, 13, "bold")
FONT_MONO = ("Menlo", 12)
FONT_BTN = (FONT_FAMILY, 13, "bold")

SPLIT_CHOICES = [
    ("split_half", "Split half (50/50)"),
    ("full_other", "Full other (other person owes all)"),
]


def format_date_display(date_iso: str | None) -> str:
    if not date_iso:
        return ""
    try:
        parsed = datetime.strptime(date_iso[:10], "%Y-%m-%d")
    except ValueError:
        return date_iso[:10]
    return parsed.strftime("%d/%m/%Y")


class SplitwiseBulkApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        load_app_env()

        self.title("Splitwise FastTrack")
        self.configure(bg=BG)
        self.minsize(980, 700)
        self.geometry("1100x820")

        self.settings = load_settings()
        self.client: SplitwiseClient | None = None
        self.current_user: dict = {}
        self.group_members: list[dict] = []
        self.browser_transactions: list = []
        self.csv_transactions: list = []
        self.browser_order_keys: set[str] = set()
        self.csv_order_keys: set[str] = set()
        self._order_lock = threading.Lock()
        self.loaded_file: Path | None = None
        self.local_server: LocalOrderServer | None = None

        self._configure_styles()
        self._build_ui()
        self._restore_settings()
        self._start_local_server()
        self._bring_to_front()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.api_key_var.get().strip():
            self.after(400, self._connect)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook.Tab", font=FONT_BODY, padding=[20, 10])
        style.configure(
            "Treeview",
            font=FONT_TABLE,
            rowheight=34,
            background=WHITE,
            fieldbackground=WHITE,
            foreground=TEXT,
        )
        style.configure(
            "Treeview.Heading",
            font=FONT_TABLE_HEAD,
            background=SURFACE_ALT,
            foreground=TEXT,
            padding=[8, 10],
        )
        style.map("Treeview", background=[("selected", TEAL)], foreground=[("selected", WHITE)])
        style.configure("TCombobox", font=FONT_BODY, padding=6)

    def _primary_btn(self, parent, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            font=FONT_BTN,
            bg=TEAL,
            fg=WHITE,
            activebackground=TEAL_DARK,
            relief="flat",
            padx=18,
            pady=10,
            cursor="hand2",
            command=command,
        )

    def _secondary_btn(self, parent, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            font=FONT_BODY,
            bg=WHITE,
            fg=TEXT,
            relief="solid",
            bd=1,
            padx=14,
            pady=9,
            cursor="hand2",
            command=command,
        )

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=TEAL)
        header.pack(fill="x")
        tk.Label(
            header,
            text="  Splitwise FastTrack",
            font=(FONT_FAMILY, 18, "bold"),
            bg=TEAL,
            fg=WHITE,
            pady=14,
        ).pack(side="left")
        tk.Label(
            header,
            text="CSV · browser sync · Splitwise  ·  INR only",
            font=FONT_BODY,
            bg=TEAL,
            fg="#D0EBEC",
            padx=20,
        ).pack(side="right")

        self.group_var = tk.StringVar(value="(connect first)")
        self.other_var = tk.StringVar(value="")

        self._build_connect_bar()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.tab_browser = ttk.Frame(self.nb)
        self.tab_csv = ttk.Frame(self.nb)
        self.nb.add(self.tab_browser, text="  1. Browser Sync  ")
        self.nb.add(self.tab_csv, text="  2. CSV Upload  ")

        self._build_browser_tab()
        self._build_csv_tab()

        bar = tk.Frame(self, bg=WHITE)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=BORDER, height=1).pack(fill="x")
        self.status_var = tk.StringVar(value="Browser Sync tab — open Amazon order history with Tampermonkey running.")
        tk.Label(bar, textvariable=self.status_var, font=FONT_BODY, bg=WHITE, fg=TEXT, anchor="w", padx=16, pady=10).pack(
            fill="x"
        )

    def _build_connect_bar(self) -> None:
        inner = tk.Frame(self, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)
        inner.pack(fill="x")

        row = tk.Frame(inner, bg=WHITE)
        row.pack(fill="x", padx=20, pady=10)
        self.api_key_var = tk.StringVar()
        self.api_key_entry = tk.Entry(
            row, textvariable=self.api_key_var, font=FONT_MONO, show="•", bg=WHITE, relief="solid", bd=1
        )
        self.api_key_entry.pack(side="left", fill="x", expand=True, ipady=6, ipadx=6)
        self._secondary_btn(row, "Show", self._toggle_key).pack(side="left", padx=(8, 0))
        self.connect_btn = self._primary_btn(row, "Connect", self._connect)
        self.connect_btn.pack(side="left", padx=(8, 0))
        self.conn_label = tk.Label(row, text="Not connected", font=FONT_BODY, bg=WHITE, fg=TEXT_MUTED)
        self.conn_label.pack(side="left", padx=(16, 0))

    def _build_group_row(self, parent, *, combo_attr: str, other_frame_attr: str, other_combo_attr: str) -> ttk.Combobox:
        group_row = tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)
        group_row.pack(fill="x", pady=(0, 12), ipadx=16, ipady=12)
        tk.Label(group_row, text="Upload to group:", font=FONT_H2, bg=WHITE, fg=TEXT).pack(
            side="left", padx=(0, 12)
        )
        combo = ttk.Combobox(
            group_row, textvariable=self.group_var, state="readonly", width=44, font=FONT_BODY
        )
        combo.pack(side="left", fill="x", expand=True)
        combo.bind("<<ComboboxSelected>>", self._on_group_selected)
        setattr(self, combo_attr, combo)
        other_frame = tk.Frame(group_row, bg=WHITE)
        setattr(self, other_frame_attr, other_frame)
        tk.Label(other_frame, text="Other person:", font=FONT_BODY, bg=WHITE, fg=TEXT).pack(
            side="left", padx=(0, 8)
        )
        other_combo = ttk.Combobox(
            other_frame, textvariable=self.other_var, state="readonly", width=24, font=FONT_BODY
        )
        other_combo.pack(side="left")
        setattr(self, other_combo_attr, other_combo)
        other_frame.pack_forget()
        return combo

    def _build_entries_panel(
        self,
        frame,
        *,
        source: str,
        title: str,
        subtitle: str,
    ) -> None:
        px = 32
        hdr = tk.Frame(frame, bg=BG)
        hdr.pack(fill="x", padx=px, pady=(16, 6))
        tk.Label(hdr, text=title, font=FONT_H1, bg=BG, fg=TEXT).pack(side="left")
        count_label = tk.Label(hdr, text="", font=FONT_H2, bg=BG, fg=TEAL)
        count_label.pack(side="left", padx=12)
        setattr(self, f"{source}_count_label", count_label)

        tk.Label(frame, text=subtitle, font=FONT_BODY, bg=BG, fg=TEXT_SECONDARY, anchor="w").pack(
            fill="x", padx=px, pady=(0, 10)
        )
        self._build_group_row(
            frame,
            combo_attr=f"{source}_group_combo",
            other_frame_attr=f"{source}_other_frame",
            other_combo_attr=f"{source}_other_combo",
        )

        tools = tk.Frame(frame, bg=BG)
        tools.pack(fill="x", padx=px, pady=(0, 8))
        self._secondary_btn(tools, "Remove selected", lambda s=source: self._remove_rows(s)).pack(side="left")
        self._secondary_btn(tools, "Edit split…", lambda s=source: self._edit_split(s)).pack(side="left", padx=8)
        if source == "browser":
            self._secondary_btn(tools, "Clear all synced", self._clear_browser_entries).pack(side="left", padx=8)

        footer = tk.Frame(frame, bg=TEAL_LIGHT, highlightthickness=1, highlightbackground=BORDER)
        footer.pack(side="bottom", fill="x", padx=px, pady=(8, 12))
        progress = tk.DoubleVar(value=0)
        ttk.Progressbar(footer, variable=progress, maximum=100).pack(fill="x", padx=16, pady=(8, 0))
        setattr(self, f"{source}_progress", progress)
        footer_inner = tk.Frame(footer, bg=TEAL_LIGHT)
        footer_inner.pack(fill="x", padx=16, pady=12)
        hint = tk.Label(
            footer_inner,
            text="Connect to Splitwise above, pick a group, then confirm.",
            font=FONT_BODY,
            bg=TEAL_LIGHT,
            fg=TEXT_SECONDARY,
            anchor="w",
        )
        hint.pack(side="left", fill="x", expand=True)
        setattr(self, f"{source}_confirm_hint", hint)
        btn = self._primary_btn(
            footer_inner,
            "Confirm & Upload to Splitwise",
            lambda s=source: self._confirm_upload(s),
        )
        btn.configure(state="disabled")
        btn.pack(side="right", padx=(12, 0))
        setattr(self, f"{source}_confirm_btn", btn)

        table_wrap = tk.Frame(frame, bg=BORDER, padx=1, pady=1)
        table_wrap.pack(fill="both", expand=True, padx=px, pady=4)
        inner = tk.Frame(table_wrap, bg=WHITE)
        inner.pack(fill="both", expand=True)
        cols = ("date", "description", "amount", "split")
        tree = ttk.Treeview(inner, columns=cols, show="headings", height=12)
        for col, width in zip(cols, (110, 460, 110, 180)):
            tree.heading(col, text=col.replace("_", " ").title())
            tree.column(col, width=width, anchor="w")
        tree.tag_configure("even", background=WHITE)
        tree.tag_configure("odd", background=SURFACE_ALT)
        tree.tag_configure("full_other", background=WARNING_BG, foreground=WARNING)
        vsb = ttk.Scrollbar(inner, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(inner, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        inner.grid_rowconfigure(0, weight=1)
        inner.grid_columnconfigure(0, weight=1)
        tree.bind("<Double-1>", lambda _e, s=source: self._edit_split(s))
        tree.bind("<<TreeviewSelect>>", lambda _e, s=source: self._on_select_row(s))
        setattr(self, f"{source}_tree", tree)

    def _build_browser_tab(self) -> None:
        frame = self.tab_browser
        px = 32

        sync_box = tk.LabelFrame(
            frame,
            text="  Tampermonkey browser sync  ",
            font=FONT_H2,
            bg=SUCCESS_BG,
            fg=SUCCESS,
            padx=16,
            pady=12,
        )
        sync_box.pack(fill="x", padx=px, pady=(12, 8))
        tk.Label(
            sync_box,
            text=(
                "1. Install tampermonkey/splitwise-order-export.user.js\n"
                "2. Open order history (e.g. amazon.in/your-orders/orders)\n"
                "3. Visible orders sync here automatically while you browse"
            ),
            font=FONT_BODY,
            bg=SUCCESS_BG,
            fg=TEXT,
            justify="left",
            anchor="w",
        ).pack(fill="x")
        self.sync_label = tk.Label(
            sync_box,
            text=f"● Listening on http://127.0.0.1:{DEFAULT_PORT}",
            font=FONT_MONO,
            bg=SUCCESS_BG,
            fg=SUCCESS,
            anchor="w",
        )
        self.sync_label.pack(fill="x", pady=(8, 0))

        self._build_entries_panel(
            frame,
            source="browser",
            title="Synced orders",
            subtitle="Orders from Amazon, Apollo, Urban Company appear below. Edit, then upload.",
        )

    def _build_csv_tab(self) -> None:
        frame = self.tab_csv
        px = 32

        tk.Label(frame, text="Upload CSV file", font=FONT_H1, bg=BG, fg=TEXT).pack(
            anchor="w", padx=px, pady=(12, 6)
        )
        tk.Label(
            frame,
            text="Columns: date (DD/MM/YY), description, amount (INR), type of split",
            font=FONT_BODY,
            bg=BG,
            fg=TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x", padx=px, pady=(0, 8))

        file_box = tk.Frame(frame, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)
        file_box.pack(fill="x", padx=px, pady=(0, 8), ipadx=16, ipady=12)
        self.file_label = tk.Label(file_box, text="No file selected", font=FONT_BODY, bg=WHITE, fg=TEXT_SECONDARY, anchor="w")
        self.file_label.pack(fill="x", pady=(0, 8))
        btn_row = tk.Frame(file_box, bg=WHITE)
        btn_row.pack(anchor="w")
        self._secondary_btn(btn_row, "Choose CSV…", self._pick_csv).pack(side="left")
        self.load_btn = self._primary_btn(btn_row, "Load CSV", self._load_csv)
        self.load_btn.configure(state="disabled")
        self.load_btn.pack(side="left", padx=(10, 0))

        self._build_entries_panel(
            frame,
            source="csv",
            title="CSV entries",
            subtitle="Review loaded rows, edit if needed, then confirm upload.",
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _txns(self, source: str) -> list:
        return self.browser_transactions if source == "browser" else self.csv_transactions

    def _keys(self, source: str) -> set[str]:
        return self.browser_order_keys if source == "browser" else self.csv_order_keys

    def _tree(self, source: str) -> ttk.Treeview:
        return getattr(self, f"{source}_tree")

    def _count_label(self, source: str) -> tk.Label:
        return getattr(self, f"{source}_count_label")

    def _confirm_btn(self, source: str) -> tk.Button:
        return getattr(self, f"{source}_confirm_btn")

    def _confirm_hint(self, source: str) -> tk.Label:
        return getattr(self, f"{source}_confirm_hint")

    def _progress(self, source: str) -> tk.DoubleVar:
        return getattr(self, f"{source}_progress")

    def _other_frame(self, source: str) -> tk.Frame:
        return getattr(self, f"{source}_other_frame")

    def _other_combo(self, source: str) -> ttk.Combobox:
        return getattr(self, f"{source}_other_combo")

    def _group_combos(self) -> list[ttk.Combobox]:
        return [self.browser_group_combo, self.csv_group_combo]

    def _other_combos(self) -> list[ttk.Combobox]:
        return [self.browser_other_combo, self.csv_other_combo]

    def _other_frames(self) -> list[tk.Frame]:
        return [self.browser_other_frame, self.csv_other_frame]

    def _set_status(self, msg: str) -> None:
        self.status_var.set(msg)

    def _toggle_key(self) -> None:
        show = self.api_key_entry.cget("show")
        self.api_key_entry.configure(show="" if show == "•" else "•")

    def _bring_to_front(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))

    def _restore_settings(self) -> None:
        key = get_saved_api_key() or self.settings.get("api_key", "")
        if key:
            self.api_key_var.set(key)

    def _start_local_server(self) -> None:
        try:
            self.local_server = LocalOrderServer(self._receive_orders, port=DEFAULT_PORT)
            self.local_server.start()
        except OSError as exc:
            self.local_server = None
            if hasattr(self, "sync_label"):
                self.sync_label.configure(
                    text=f"✗ Could not start listener on port {DEFAULT_PORT}: {exc}",
                    fg=ERROR,
                    bg=ERROR_BG,
                )

    def _receive_orders(self, orders: list[dict], source: str) -> tuple[int, int]:
        group_id = self._parse_group_id() or 0
        with self._order_lock:
            new_txns, added, skipped = orders_to_transactions(
                orders,
                source=source,
                existing_keys=self._keys("browser"),
                start_row=len(self.browser_transactions),
                default_group_id=group_id,
            )
            if new_txns:
                self.browser_transactions.extend(new_txns)
                for index, txn in enumerate(self.browser_transactions, start=1):
                    txn.row_num = index
        if added:
            self.after(0, lambda count=added, src=source: self._on_browser_orders(count, src))
        return added, skipped

    def _on_browser_orders(self, count: int, source: str) -> None:
        self._refresh_table("browser")
        total = len(self.browser_transactions)
        self._set_status(f"Added {count} from {source} — {total} in Browser Sync")
        self.nb.select(self.tab_browser)
        if hasattr(self, "sync_label"):
            self.sync_label.configure(
                text=f"● Listening · last sync: +{count} from {source} ({total} total)"
            )

    def _clear_browser_entries(self) -> None:
        if not self.browser_transactions:
            return
        if not messagebox.askyesno("Clear", "Remove all synced browser orders?"):
            return
        self.browser_transactions.clear()
        self.browser_order_keys.clear()
        self._refresh_table("browser")
        self._set_status("Cleared all synced browser orders.")

    def _on_close(self) -> None:
        if self.local_server:
            self.local_server.stop()
        payload: dict = {}
        if self.api_key_var.get().strip():
            payload["api_key"] = self.api_key_var.get().strip()
        if self.group_var.get():
            payload["group"] = self.group_var.get()
        if self.other_var.get():
            payload["other"] = self.other_var.get()
        save_settings(payload)
        self.destroy()

    def _parse_group_id(self) -> int | None:
        value = self.group_var.get()
        if "(" not in value:
            return None
        try:
            return int(value.rsplit("(", 1)[1].rstrip(")"))
        except ValueError:
            return None

    def _parse_other_id(self) -> int | None:
        value = self.other_var.get()
        if "(" not in value:
            return None
        try:
            return int(value.rsplit("(", 1)[1].rstrip(")"))
        except ValueError:
            return None

    def _other_display_name(self) -> str:
        value = self.other_var.get()
        if "(" not in value:
            return "Other"
        return value.split("(")[0].strip() or "Other"

    def _needs_other_person(self, source: str) -> bool:
        return any(t.split_mode is SplitMode.WIFE_OWES_FULL for t in self._txns(source))

    def _update_confirm_state(self, source: str) -> None:
        txns = self._txns(source)
        btn = self._confirm_btn(source)
        hint = self._confirm_hint(source)
        tab_name = "Browser Sync" if source == "browser" else "CSV Upload"

        if not txns:
            btn.configure(state="disabled")
            hint.configure(
                text="No entries yet — sync from browser or load a CSV on the other tab.",
                fg=TEXT_SECONDARY,
            )
            return

        btn.configure(state="normal")

        missing: list[str] = []
        if not self.client:
            missing.append("connect to Splitwise above")
        if self._parse_group_id() is None:
            missing.append("select a group")
        if self._needs_other_person(source) and self._parse_other_id() is None:
            missing.append("select other person for full_other rows")

        if missing:
            hint.configure(
                text=f"Before upload ({tab_name}): " + " · ".join(missing),
                fg=WARNING,
            )
        else:
            hint.configure(
                text=f"Ready — upload {len(txns)} expense(s) to Splitwise.",
                fg=SUCCESS,
            )

    # ── Connect ──────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("API key", "Paste your Splitwise API key first.")
            return
        self.connect_btn.configure(state="disabled", text="Connecting…")

        def worker() -> None:
            try:
                client = SplitwiseClient(key)
                user = client.get_current_user()
                groups = client.get_groups()
                self.after(0, lambda: self._on_connected(client, user, groups))
            except Exception as exc:
                self.after(0, lambda: self._on_connect_fail(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_connected(self, client: SplitwiseClient, user: dict, groups: list[dict]) -> None:
        self.client = client
        self.current_user = user
        self.connect_btn.configure(state="normal", text="Connect")
        name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        self.conn_label.configure(text=f"✓ Connected as {name}", fg=SUCCESS)
        labels = [f"{g['name']} ({g['id']})" for g in groups]
        for combo in self._group_combos():
            combo["values"] = labels
        saved = self.settings.get("group", "")
        if saved in labels:
            self.group_var.set(saved)
        elif labels:
            self.group_var.set(labels[0])
        self._on_group_selected()
        save_settings({"api_key": self.api_key_var.get().strip()})
        self._set_status(f"Connected as {name}. Browser Sync or CSV Upload — pick a tab.")
        self._update_confirm_state("browser")
        self._update_confirm_state("csv")

    def _on_connect_fail(self, error: str) -> None:
        self.connect_btn.configure(state="normal", text="Connect")
        self.conn_label.configure(text=f"✗ {error}", fg=ERROR)
        messagebox.showerror("Connection failed", error)

    def _on_group_selected(self, _event=None) -> None:
        group_id = self._parse_group_id()
        if group_id is None or not self.client:
            return

        def worker() -> None:
            try:
                members = self.client.get_group_members(group_id)
                self.after(0, lambda: self._populate_other(members))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Group", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_other(self, members: list[dict]) -> None:
        self.group_members = members
        current_id = int(self.current_user.get("id", 0))
        others = [m for m in members if m["id"] != current_id]
        labels = [f"{m['name']} ({m['id']})" for m in others]
        for combo in self._other_combos():
            combo["values"] = labels

        show_other = self._needs_other_person("browser") or self._needs_other_person("csv")
        for frame in self._other_frames():
            if show_other:
                frame.pack(side="left", padx=(16, 0))
            else:
                frame.pack_forget()

        saved = self.settings.get("other", "")
        if saved in labels:
            self.other_var.set(saved)
        elif len(labels) == 1:
            self.other_var.set(labels[0])
        elif labels:
            self.other_var.set(labels[0])

        group_id = self._parse_group_id()
        if group_id is not None:
            for t in self.browser_transactions + self.csv_transactions:
                t.group_id = group_id
        self._update_confirm_state("browser")
        self._update_confirm_state("csv")

    # ── CSV ──────────────────────────────────────────────────────────────────

    def _pick_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select expense CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.loaded_file = Path(path)
            self.file_label.configure(text=str(self.loaded_file))
            self.load_btn.configure(state="normal")
            self._set_status(f"Selected {self.loaded_file.name} — click Load entries.")

    def _load_csv(self) -> None:
        if not self.loaded_file:
            return
        try:
            self.csv_transactions = parse_expense_csv(self.loaded_file)
            self.csv_order_keys = set()
            for t in self.csv_transactions:
                key = order_key("csv", (t.date or "")[:10], t.description, t.cost)
                t.ingest_key = key
                self.csv_order_keys.add(key)
        except Exception as exc:
            messagebox.showerror("CSV error", str(exc))
            return
        if not self.csv_transactions:
            messagebox.showinfo("Empty", "No rows found in CSV.")
            return
        group_id = self._parse_group_id()
        if group_id is not None:
            for t in self.csv_transactions:
                t.group_id = group_id
        self._refresh_table("csv")
        self._set_status(f"Loaded {len(self.csv_transactions)} entries — review and confirm on CSV Upload tab.")
        self.nb.select(self.tab_csv)
        if not self.client:
            messagebox.showinfo(
                "Entries loaded",
                f"Loaded {len(self.csv_transactions)} rows.\n\n"
                "Next steps:\n"
                "1. Connect to Splitwise above (if not already)\n"
                "2. Select your group\n"
                "3. Click Confirm & Upload to Splitwise",
            )

    def _refresh_table(self, source: str) -> None:
        tree = self._tree(source)
        txns = self._txns(source)
        tree.delete(*tree.get_children())
        other_name = self._other_display_name()
        for i, t in enumerate(txns):
            tag = "full_other" if t.split_mode is SplitMode.WIFE_OWES_FULL else ("even" if i % 2 == 0 else "odd")
            tree.insert(
                "",
                "end",
                iid=str(t.row_num),
                tags=(tag,),
                values=(
                    format_date_display(t.date),
                    t.description,
                    f"₹{t.cost}",
                    t.split_mode.label_for(other_name),
                ),
            )
        self._count_label(source).configure(text=f"{len(txns)} entries")
        if self._needs_other_person(source) and self.group_members:
            self._other_frame(source).pack(side="left", padx=(16, 0))
        self._update_confirm_state(source)

    def _txn(self, source: str, row_id: str):
        num = int(row_id)
        return next((t for t in self._txns(source) if t.row_num == num), None)

    def _on_select_row(self, source: str, _event=None) -> None:
        tree = self._tree(source)
        sel = tree.selection()
        if sel:
            vals = tree.item(sel[0], "values")
            if len(vals) >= 2:
                self._set_status(f"Selected: {vals[1]}  ·  {vals[2]}  ·  {vals[3]}")

    def _remove_rows(self, source: str) -> None:
        tree = self._tree(source)
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("Remove", "Select rows to remove.")
            return
        if not messagebox.askyesno("Remove", f"Remove {len(sel)} row(s)?"):
            return
        remove = {int(s) for s in sel}
        txns = self._txns(source)
        removed = [t for t in txns if t.row_num in remove]
        if source == "browser":
            self.browser_transactions = [t for t in txns if t.row_num not in remove]
            for t in removed:
                if t.ingest_key:
                    self.browser_order_keys.discard(t.ingest_key)
        else:
            self.csv_transactions = [t for t in txns if t.row_num not in remove]
            for t in removed:
                key = t.ingest_key or order_key("csv", (t.date or "")[:10], t.description, t.cost)
                self.csv_order_keys.discard(key)
        remaining = self._txns(source)
        for i, t in enumerate(remaining, start=1):
            t.row_num = i
        self._refresh_table(source)

    def _edit_split(self, source: str) -> None:
        tree = self._tree(source)
        sel = tree.selection()
        if not sel or len(sel) > 1:
            messagebox.showinfo("Edit", "Select one row to edit.")
            return
        txn = self._txn(source, sel[0])
        if txn is None:
            return

        dialog = tk.Toplevel(self)
        dialog.title("Edit split")
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("420x200")

        tk.Label(dialog, text=txn.description, font=FONT_BODY, bg=BG, fg=TEXT, wraplength=380).pack(
            padx=20, pady=(16, 8)
        )
        current = split_mode_csv_value(txn.split_mode)
        var = tk.StringVar(value=current)
        combo = ttk.Combobox(
            dialog,
            textvariable=var,
            values=[v for v, _ in SPLIT_CHOICES],
            state="readonly",
            font=FONT_BODY,
            width=30,
        )
        combo.pack(padx=20, pady=8, anchor="w")

        def apply() -> None:
            txn.split_mode = SplitMode.from_text(var.get(), SplitMode.HALF)
            dialog.destroy()
            self._refresh_table(source)
            if self.group_members:
                self._populate_other(self.group_members)

        row = tk.Frame(dialog, bg=BG)
        row.pack(pady=12, padx=20, anchor="e")
        self._secondary_btn(row, "Cancel", dialog.destroy).pack(side="left", padx=6)
        self._primary_btn(row, "Apply", apply).pack(side="left")

    # ── Upload ───────────────────────────────────────────────────────────────

    def _confirm_upload(self, source: str) -> None:
        txns = self._txns(source)
        if not txns:
            messagebox.showwarning("No entries", "Sync orders or load a CSV first.")
            return
        if not self.client:
            messagebox.showwarning("Not connected", "Connect to Splitwise above.")
            return
        group_id = self._parse_group_id()
        if group_id is None:
            messagebox.showwarning("Group", "Select a Splitwise group.")
            return
        if self._needs_other_person(source) and self._parse_other_id() is None:
            messagebox.showwarning("Other person", "Select who owes full for full_other rows.")
            return

        count = len(txns)
        group_name = self.group_var.get().split("(")[0].strip()
        if not messagebox.askyesno(
            "Confirm upload",
            f"Upload {count} expense(s) to \"{group_name}\" on Splitwise?",
        ):
            return

        for t in txns:
            t.group_id = group_id

        other_id = self._parse_other_id()
        group_context = None
        if self._needs_other_person(source) and other_id is not None:
            group_context = GroupContext(
                group_id=group_id,
                current_user_id=int(self.current_user["id"]),
                partner_user_id=other_id,
                partner_name=self._other_display_name(),
            )

        btn = self._confirm_btn(source)
        btn.configure(state="disabled", text="Uploading…")
        self._progress(source).set(10)
        client = self.client
        upload_txns = list(txns)

        def worker() -> None:
            results = import_transactions(
                upload_txns,
                client,
                dry_run=False,
                group_context=group_context,
            )
            self.after(0, lambda: self._on_upload_done(source, results))

        threading.Thread(target=worker, daemon=True).start()

    def _on_upload_done(self, source: str, results: list) -> None:
        btn = self._confirm_btn(source)
        btn.configure(state="normal", text="Confirm & Upload to Splitwise")
        self._progress(source).set(100)
        ok = sum(1 for r in results if r.status.value == "success")
        failed = sum(1 for r in results if r.status.value == "error")

        if failed:
            errors = "\n".join(r.message for r in results if r.status.value == "error")[:500]
            messagebox.showerror("Upload finished", f"{ok} uploaded, {failed} failed.\n\n{errors}")
        else:
            messagebox.showinfo("Success", f"Uploaded {ok} expense(s) to Splitwise.")
            if source == "browser":
                self.browser_transactions.clear()
                self.browser_order_keys.clear()
            else:
                self.csv_transactions.clear()
                self.csv_order_keys.clear()
                self.loaded_file = None
                self.file_label.configure(text="No file selected")
                self.load_btn.configure(state="disabled")
            self._refresh_table(source)
            self._progress(source).set(0)

        self._set_status(f"Upload complete — {ok} ok, {failed} failed")


def main() -> None:
    print("Splitwise FastTrack — opening…")
    app = SplitwiseBulkApp()
    app.mainloop()


if __name__ == "__main__":
    main()
