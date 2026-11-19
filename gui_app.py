import os
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.lines as mlines
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Import repository modules
import cleaning.product_clean as pro_p
import cleaning.stock_clean as stock_p
import cleaning.purchase_clean as pur_p
from cleaning.sales_clean import clean_basic_fields
from analysis.sales_analysis import (
    compute_week_comparison,
    compute_market_distributions,
    compute_model_sell_through,
    compute_weekly_aggregations_with_derivatives,
    compute_inventory_predictions_for_both,
    get_week_boundaries,
)


# ==============================================================================
# HELPER: DataFrame to ttk.Treeview Renderer
# ==============================================================================
class DataFrameTable(ttk.Frame):
    """Scrollable Treeview widget to display any pandas DataFrame cleanly."""

    def __init__(self, parent, df: pd.DataFrame = None, max_rows: int = 500):
        super().__init__(parent)
        self.tree = ttk.Treeview(self, show="headings")
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        if df is not None:
            self.load_dataframe(df, max_rows=max_rows)

    def load_dataframe(self, df: pd.DataFrame, max_rows: int = 500):
        self.tree.delete(*self.tree.get_children())
        if df is None or df.empty:
            self.tree["columns"] = ("Info",)
            self.tree.heading("Info", text="Notice")
            self.tree.column("Info", width=300, anchor="center")
            self.tree.insert("", "end", values=("No data available for this selection.",))
            return

        display_df = df.head(max_rows).copy()
        cols = list(display_df.columns)
        self.tree["columns"] = cols

        for col in cols:
            self.tree.heading(col, text=str(col))
            self.tree.column(col, width=max(110, min(220, len(str(col)) * 12)), anchor="center")

        for _, row in display_df.iterrows():
            formatted_vals = []
            for val in row:
                if pd.isna(val):
                    formatted_vals.append("")
                elif isinstance(val, (pd.Timestamp, np.datetime64)):
                    formatted_vals.append(pd.Timestamp(val).strftime("%d-%m-%Y"))
                elif isinstance(val, (float, np.floating)):
                    formatted_vals.append(f"{val:,.2f}")
                else:
                    formatted_vals.append(str(val))
            self.tree.insert("", "end", values=formatted_vals)


# ==============================================================================
# HELPER: Multi-Select Dropdown Checklist Menu
# ==============================================================================
class ProductMultiSelectDropdown(ttk.Frame):
    """Menubutton with checkbuttons allowing users to select/deselect products."""

    def __init__(self, parent, products: list[str], on_change_callback):
        super().__init__(parent)
        self.products = sorted(list(set(str(p) for p in products if pd.notna(p))))
        self.on_change_callback = on_change_callback
        self.vars: dict[str, tk.BooleanVar] = {}

        self.menubutton = ttk.Menubutton(
            self, text=f"Products ({len(self.products)} selected)", direction="below"
        )
        self.menu = tk.Menu(self.menubutton, tearoff=False)
        self.menubutton["menu"] = self.menu
        self.menubutton.pack(side="left", padx=4)

        btn_all = ttk.Button(self, text="Select All", width=9, command=self.select_all)
        btn_all.pack(side="left", padx=2)

        btn_none = ttk.Button(self, text="Clear All", width=9, command=self.deselect_all)
        btn_none.pack(side="left", padx=2)

        self._build_menu()

    def _build_menu(self):
        self.menu.delete(0, "end")
        self.vars.clear()
        for prod in self.products:
            var = tk.BooleanVar(value=True)
            self.vars[prod] = var
            self.menu.add_checkbutton(
                label=prod,
                variable=var,
                onvalue=True,
                offvalue=False,
                command=self._handle_toggle,
            )
        self._update_label()

    def set_products(self, products: list[str]):
        self.products = sorted(list(set(str(p) for p in products if pd.notna(p))))
        self._build_menu()

    def _handle_toggle(self):
        self._update_label()
        if self.on_change_callback:
            self.on_change_callback()

    def _update_label(self):
        selected = self.get_selected()
        self.menubutton.config(text=f"Products ({len(selected)}/{len(self.products)} selected)")

    def select_all(self):
        for var in self.vars.values():
            var.set(True)
        self._handle_toggle()

    def deselect_all(self):
        for var in self.vars.values():
            var.set(False)
        self._handle_toggle()

    def get_selected(self) -> list[str]:
        return [prod for prod, var in self.vars.items() if var.get()]


# ==============================================================================
# HELPER: Switchable Table / Stock Prediction Line Plot View (Market-Aware)
# ==============================================================================
class TableOrStockPlotPanel(ttk.Frame):
    """
    Reusable view supporting:
    - Toggle between Table and Line Plot
    - Multi-select product dropdown
    - Prediction Mode ('With Reorder Plan' vs 'Without Reorder Plan')
    - Market Scope ('Total' vs specific Market like 'ES', 'DE', etc.) with market-specific filtering
    """

    def __init__(
            self,
            parent,
            table_df: pd.DataFrame,
            pred_full_df: pd.DataFrame,
            pred_no_orders_df: pd.DataFrame,
            sales_full_df: pd.DataFrame = None,
            weekly_sku_df: pd.DataFrame = None,
            target_date: str = "09-11-2025",
            find_latest_monday: bool = True,
            product_col: str = "Producto",
            plot_title: str = "Stock Trajectory (Real vs. Predicted)",
            is_running_low_tab: bool = False,
    ):
        super().__init__(parent)
        self.base_table_df = table_df.copy() if table_df is not None else pd.DataFrame()
        self.pred_full_df = pred_full_df.copy() if pred_full_df is not None else pd.DataFrame()
        self.pred_no_orders_df = pred_no_orders_df.copy() if pred_no_orders_df is not None else pd.DataFrame()
        self.sales_full_df = sales_full_df.copy() if sales_full_df is not None else pd.DataFrame()
        self.weekly_sku_df = weekly_sku_df.copy() if weekly_sku_df is not None else pd.DataFrame()
        self.target_date = target_date
        self.find_latest_monday = find_latest_monday
        self.product_col = product_col if product_col in self.base_table_df.columns else "SKU"
        self.plot_title = plot_title
        self.is_running_low_tab = is_running_low_tab

        self.view_mode = tk.StringVar(value="table")
        self.stock_mode = tk.StringVar(value="with_incoming")
        self.market_mode = tk.StringVar(value="Total")

        # --- Top Controls Bar ---
        ctrl_frame = ttk.Frame(self, padding=(8, 6))
        ctrl_frame.pack(fill="x")

        ttk.Label(ctrl_frame, text="View:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        ttk.Radiobutton(
            ctrl_frame, text="Table", variable=self.view_mode, value="table", command=self._switch_view
        ).pack(side="left", padx=2)
        ttk.Radiobutton(
            ctrl_frame, text="Line Plot", variable=self.view_mode, value="plot", command=self._switch_view
        ).pack(side="left", padx=2)

        ttk.Separator(ctrl_frame, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Label(ctrl_frame, text="Prediction Mode:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        ttk.Radiobutton(
            ctrl_frame, text="With Reorder Plan",
            variable=self.stock_mode, value="with_incoming", command=self._on_control_changed
        ).pack(side="left", padx=2)
        ttk.Radiobutton(
            ctrl_frame, text="Without Reorder Plan",
            variable=self.stock_mode, value="without_incoming", command=self._on_control_changed
        ).pack(side="left", padx=2)

        ttk.Separator(ctrl_frame, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Label(ctrl_frame, text="Market Scope:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))

        available_markets = ["Total"]
        if not self.sales_full_df.empty and "Mercado" in self.sales_full_df.columns:
            available_markets += sorted(self.sales_full_df["Mercado"].dropna().unique().tolist())

        self.market_combo = ttk.Combobox(
            ctrl_frame, textvariable=self.market_mode, values=available_markets, width=8, state="readonly"
        )
        self.market_combo.pack(side="left", padx=4)
        self.market_combo.bind("<<ComboboxSelected>>", lambda e: self._on_control_changed())

        ttk.Separator(ctrl_frame, orient="vertical").pack(side="left", fill="y", padx=8)

        # Initial products dropdown setup
        current_table_df = self._get_market_filtered_table()
        available_products = (
            current_table_df[self.product_col].dropna().unique().tolist()
            if not current_table_df.empty and self.product_col in current_table_df.columns
            else []
        )
        self.dropdown = ProductMultiSelectDropdown(
            ctrl_frame, products=available_products, on_change_callback=self._refresh_content
        )
        self.dropdown.pack(side="left")

        # --- Content Container ---
        self.content_frame = ttk.Frame(self)
        self.content_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.table_widget = DataFrameTable(self.content_frame)
        self.plot_container = ttk.Frame(self.content_frame)

        self.fig, self.ax = plt.subplots(figsize=(9, 4.8), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_container)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self._switch_view()

    def _get_market_filtered_table(self) -> pd.DataFrame:
        """Filters the table dataframe so that running low / excess items correspond specifically to the selected market."""
        if self.base_table_df.empty:
            return self.base_table_df

        selected_market = self.market_mode.get()
        if selected_market == "Total" or not self.is_running_low_tab or self.sales_full_df.empty or "Mercado" not in self.sales_full_df.columns:
            return self.base_table_df

        # If a specific market is selected, compute market-specific sales share per SKU
        active_pred_df = self.pred_full_df if self.stock_mode.get() == "with_incoming" else self.pred_no_orders_df
        if active_pred_df.empty or "SKU" not in active_pred_df.columns:
            return self.base_table_df

        # Keep the SKUs that actually sell in this market (stock and demand scale by the same share,
        # so a SKU that runs out in total also runs out in every market that buys it)
        market_share, _ = self._market_share_by_sku(selected_market)

        filtered_rows = []
        for _, row in self.base_table_df.iterrows():
            ratio = market_share.get(row.get("SKU"), 0.0)
            if pd.notna(ratio) and float(ratio) > 0:
                filtered_rows.append(row)

        if not filtered_rows:
            return self.base_table_df.iloc[0:0]
        return pd.DataFrame(filtered_rows)

    def _on_control_changed(self):
        new_table_df = self._get_market_filtered_table()
        available_products = (
            new_table_df[self.product_col].dropna().unique().tolist()
            if not new_table_df.empty and self.product_col in new_table_df.columns
            else []
        )
        self.dropdown.set_products(available_products)
        self._refresh_content()

    def _switch_view(self):
        self.table_widget.pack_forget()
        self.plot_container.pack_forget()

        if self.view_mode.get() == "table":
            self.table_widget.pack(fill="both", expand=True)
        else:
            self.plot_container.pack(fill="both", expand=True)
        self._refresh_content()

    def _get_filtered_table(self) -> pd.DataFrame:
        market_tbl = self._get_market_filtered_table()
        if market_tbl.empty:
            return market_tbl
        selected = set(self.dropdown.get_selected())
        if not selected:
            return market_tbl.iloc[0:0]
        return market_tbl[market_tbl[self.product_col].astype(str).isin(selected)].copy()

    def _refresh_content(self):
        filtered_df = self._get_filtered_table()
        if self.view_mode.get() == "table":
            self.table_widget.load_dataframe(filtered_df)
        else:
            active_pred_df = (
                self.pred_full_df if self.stock_mode.get() == "with_incoming" else self.pred_no_orders_df
            )
            selected_market = self.market_mode.get()
            self._render_stock_plot(filtered_df, active_pred_df, selected_market)

    # ------------------------------------------------------------------
    # Market scope helpers
    # The warehouse keeps ONE stock pool per SKU (no stock-by-market table), so a market's
    # "slice" of stock is allocated pro rata to that market's share of each SKU's recent demand.
    # ------------------------------------------------------------------
    def _market_sales_base(self) -> pd.DataFrame:
        """Cleaned sales lines without influencer gifts (cached)."""
        cached = getattr(self, "_market_sales_cache", None)
        if cached is not None:
            return cached

        sales = self.sales_full_df
        if sales is None or sales.empty or not {"Mercado", "SKU", "Unidades", "Fecha"}.issubset(sales.columns):
            self._market_sales_cache = pd.DataFrame()
            return self._market_sales_cache

        sales = sales.copy()
        if "Etiquetas" in sales.columns:
            sales = sales[~sales["Etiquetas"].astype(str).str.contains("influencer", case=False, na=False)]
        sales["Fecha"] = pd.to_datetime(sales["Fecha"], errors="coerce", dayfirst=True)
        sales["Unidades"] = pd.to_numeric(sales["Unidades"], errors="coerce").fillna(0)
        self._market_sales_cache = sales.dropna(subset=["Fecha"])
        return self._market_sales_cache

    def _market_share_by_sku(self, market: str, lookback_weeks: int = 12):
        """Returns (share per SKU, fallback share).

        share = the market's units / total units of that SKU over the last `lookback_weeks`
        before the forecast start. SKUs with no sales in the window use the market's overall share.
        """
        sales = self._market_sales_base()
        if sales.empty:
            return pd.Series(dtype=float), 0.0

        end = get_week_boundaries(self.target_date, self.find_latest_monday)["current_end"]
        upto = sales[sales["Fecha"] < end + pd.Timedelta(days=1)]
        window = upto[upto["Fecha"] > end - pd.Timedelta(weeks=lookback_weeks)]
        if window.empty:
            window = upto
        if window.empty:
            return pd.Series(dtype=float), 0.0

        total = window.groupby("SKU")["Unidades"].sum()
        in_market = window[window["Mercado"] == market].groupby("SKU")["Unidades"].sum()
        share = (in_market.reindex(total.index).fillna(0.0) / total.where(total > 0)).clip(0.0, 1.0)

        total_units = total.sum()
        fallback = float(in_market.sum() / total_units) if total_units > 0 else 0.0
        return share, min(max(fallback, 0.0), 1.0)

    def _market_weekly_units(self, market: str) -> pd.DataFrame:
        """Real weekly units per SKU sold in one market (same shape as the weekly SKU table)."""
        sales = self._market_sales_base()
        if sales.empty:
            return pd.DataFrame(columns=["SKU", "week_start", "units"])

        in_market = sales[sales["Mercado"] == market].copy()
        in_market["week_start"] = in_market["Fecha"].dt.normalize() - pd.to_timedelta(
            in_market["Fecha"].dt.dayofweek, unit="D"
        )
        return (
            in_market.groupby(["SKU", "week_start"], as_index=False)["Unidades"].sum()
            .rename(columns={"Unidades": "units"})
        )

    def _render_stock_plot(self, filtered_df: pd.DataFrame, active_pred_df: pd.DataFrame, selected_market: str):
        self.ax.clear()

        if filtered_df.empty or active_pred_df.empty:
            self.ax.text(0.5, 0.5, "No products selected or no prediction data available.",
                         ha="center", va="center", fontsize=11, color="gray")
            self.canvas.draw()
            return

        selected_items = set(filtered_df[self.product_col].astype(str).unique())
        match_col = self.product_col if self.product_col in active_pred_df.columns else "SKU"
        sub_pred = active_pred_df[active_pred_df[match_col].astype(str).isin(selected_items)].copy()

        if sub_pred.empty:
            self.ax.text(0.5, 0.5, "No matching SKU stock forecast found.",
                         ha="center", va="center", fontsize=11, color="gray")
            self.canvas.draw()
            return

        weeks = get_week_boundaries(self.target_date, self.find_latest_monday)
        current_end = weeks["current_end"]

        hist_dates = [current_end - pd.Timedelta(weeks=i) for i in range(3, -1, -1)]
        pred_dates = [current_end + pd.Timedelta(weeks=i) for i in range(0, 9)]

        stock_cols = ["current_stock"] + [f"ending_stock_week_{k}" for k in range(1, 9)]
        existing_stock_cols = [c for c in stock_cols if c in sub_pred.columns]

        if selected_market == "Total" or "SKU" not in sub_pred.columns:
            plot_pred = sub_pred
            hist_source = self.weekly_sku_df
        else:
            # Market slice of the warehouse: every SKU's stock trajectory x the market's demand share of that SKU
            share, fallback_share = self._market_share_by_sku(selected_market)
            factor = sub_pred["SKU"].map(share).fillna(fallback_share).clip(0.0, 1.0)
            plot_pred = sub_pred.copy()
            plot_pred[existing_stock_cols] = plot_pred[existing_stock_cols].mul(factor, axis=0)
            hist_source = self._market_weekly_units(selected_market)

        agg_pred = plot_pred.groupby(match_col)[existing_stock_cols].sum().reset_index()

        color_cycle = plt.cm.tab10.colors
        product_handles = []

        for idx, row in agg_pred.iterrows():
            label_name = str(row[match_col])
            color = color_cycle[idx % len(color_cycle)]
            w0_stock = float(row["current_stock"])

            # History: walk back from today's stock adding back each past week's sales
            hist_vals = [w0_stock]
            if hist_source is not None and not hist_source.empty and "SKU" in sub_pred.columns:
                skus_for_prod = sub_pred[sub_pred[match_col].astype(str) == label_name]["SKU"].unique()
                sku_hist = hist_source[hist_source["SKU"].isin(skus_for_prod)]
                if not sku_hist.empty and "week_start" in sku_hist.columns:
                    running_back = w0_stock
                    for k in range(3):  # last 3 weeks, most recent first (zero-sales weeks count as 0)
                        hi = current_end - pd.Timedelta(weeks=k)
                        lo = hi - pd.Timedelta(weeks=1)
                        wk_units = sku_hist.loc[
                            (sku_hist["week_start"] > lo) & (sku_hist["week_start"] <= hi), "units"
                        ].sum()
                        running_back += float(wk_units)
                        hist_vals.insert(0, running_back)

            while len(hist_vals) < len(hist_dates):
                hist_vals.insert(0, hist_vals[0])
            active_hist_dates = hist_dates[-len(hist_vals):]

            pred_vals = [w0_stock] + [float(row.get(f"ending_stock_week_{k}", 0)) for k in range(1, 9)]

            # Real line (solid)
            self.ax.plot(
                active_hist_dates,
                hist_vals,
                linestyle="-",
                marker="o",
                markersize=4,
                linewidth=2,
                color=color,
            )
            # Predicted line (dotted)
            self.ax.plot(
                pred_dates,
                pred_vals,
                linestyle=":",
                marker="o",
                markersize=4,
                linewidth=2,
                color=color,
            )

            product_handles.append(mlines.Line2D([], [], color=color, lw=2, marker='o', markersize=4, label=label_name))

        self.ax.axvline(x=current_end, color="#555555", linestyle="--", linewidth=1, alpha=0.7)
        self.ax.text(current_end, self.ax.get_ylim()[1] * 0.92, "  Forecast Start", fontsize=8, color="#444444")

        mode_desc = "With Reorder Plan" if self.stock_mode.get() == "with_incoming" else "Without Reorder Plan"
        self.ax.set_title(f"{self.plot_title} | Scope: {selected_market} | Mode: {mode_desc}", fontsize=10,
                          fontweight="bold")
        self.ax.set_xlabel("Calendar Date (End of Week)")
        self.ax.set_ylabel("Stock Units")

        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m-%Y'))
        self.fig.autofmt_xdate(rotation=20)
        self.ax.grid(True, linestyle="--", alpha=0.4)

        style_handles = [
            mlines.Line2D([], [], color="#555555", linestyle="-", lw=2, label="Real (Solid)"),
            mlines.Line2D([], [], color="#555555", linestyle=":", lw=2, label="Predicted (Dotted)")
        ]

        self.ax.legend(
            handles=product_handles + style_handles,
            bbox_to_anchor=(1.02, 1),
            loc='upper left',
            fontsize=8,
            borderaxespad=0.
        )

        self.fig.tight_layout(rect=[0, 0, 0.85, 1])
        self.canvas.draw()


# ==============================================================================
# WINDOW 2: INTERACTIVE CLEANING POPUP DIALOG
# ==============================================================================
class CleaningResolutionDialog(tk.Toplevel):
    """Pops up during cleaning to let the user resolve price mismatches and invalid market codes."""

    def __init__(self, parent, mismatch_records: list[dict], invalid_markets: list[dict], default_country: str = "ES"):
        super().__init__(parent)
        self.title("Data Cleaning — User Decisions Required")
        self.geometry("760x540")
        self.transient(parent)
        self.grab_set()

        self.default_country = default_country
        self.price_choices: dict[int, tk.StringVar] = {}
        self.market_entries: dict[str, tk.StringVar] = {}
        self.confirmed = False

        header = ttk.Label(
            self,
            text="Review & Resolve Cleaning Discrepancies",
            font=("Segoe UI", 13, "bold"),
            padding=(12, 10),
        )
        header.pack(fill="x")

        sub = ttk.Label(
            self,
            text="Please choose how each price mismatch and invalid market code should be handled before running analysis.",
            padding=(12, 0, 12, 8),
        )
        sub.pack(fill="x")

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=12, pady=4)

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        mkt_box = ttk.LabelFrame(scroll_frame, text="1. Invalid Market / Country Codes", padding=10)
        mkt_box.pack(fill="x", pady=(4, 10), padx=4)

        if not invalid_markets:
            ttk.Label(mkt_box, text="✓ All market codes are valid.").pack(anchor="w")
        else:
            for item in invalid_markets:
                inv_code = item["market"]
                count = item["rows_affected"]
                row_f = ttk.Frame(mkt_box)
                row_f.pack(fill="x", pady=3)

                ttk.Label(
                    row_f,
                    text=f"Invalid Market '{inv_code}' ({count} rows affected)  →  Replace with:",
                    width=52,
                ).pack(side="left")

                var = tk.StringVar(value=default_country)
                self.market_entries[inv_code] = var
                ttk.Entry(row_f, textvariable=var, width=12).pack(side="left", padx=6)

        price_box = ttk.LabelFrame(
            scroll_frame,
            text=f"2. Unit Price Discrepancies ({len(mismatch_records)} found)",
            padding=10,
        )
        price_box.pack(fill="x", pady=(4, 10), padx=4)

        if not mismatch_records:
            ttk.Label(price_box, text="✓ No unit price discrepancies found between Sales and Product Master.").pack(
                anchor="w")
        else:
            bulk_f = ttk.Frame(price_box)
            bulk_f.pack(fill="x", pady=(0, 8))
            ttk.Button(
                bulk_f, text="Keep All Sales Prices [1]", command=lambda: self._set_all_prices("1")
            ).pack(side="left", padx=(0, 6))
            ttk.Button(
                bulk_f, text="Use All Product Master Prices [2]", command=lambda: self._set_all_prices("2")
            ).pack(side="left")

            for rec in mismatch_records:
                idx = rec["index"]
                var = tk.StringVar(value="1")
                self.price_choices[idx] = var

                card = ttk.Frame(price_box, relief="groove", padding=6)
                card.pack(fill="x", pady=3)

                info_text = f"SKU: {rec['sku']}  |  Date: {rec['fecha']}"
                ttk.Label(card, text=info_text, font=("Segoe UI", 9, "bold")).pack(anchor="w")

                opt_f = ttk.Frame(card)
                opt_f.pack(fill="x", pady=(2, 0))
                ttk.Radiobutton(
                    opt_f,
                    text=f"[1] Keep Sales Price: {rec['sales_price']:.2f} €",
                    variable=var,
                    value="1",
                ).pack(side="left", padx=(0, 16))
                ttk.Radiobutton(
                    opt_f,
                    text=f"[2] Use Product Master Price: {rec['prod_price']:.2f} €",
                    variable=var,
                    value="2",
                ).pack(side="left")

        footer = ttk.Frame(self, padding=12)
        footer.pack(fill="x")
        ttk.Button(
            footer,
            text="Apply Cleaning Decisions & Run Analysis →",
            command=self._on_confirm,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_confirm)

    def _set_all_prices(self, choice_val: str):
        for var in self.price_choices.values():
            var.set(choice_val)

    def _on_confirm(self):
        self.confirmed = True
        self.destroy()

    def get_decisions(self):
        price_map = {idx: var.get() for idx, var in self.price_choices.items()}
        market_map = {
            inv: (var.get().strip().upper() or self.default_country)
            for inv, var in self.market_entries.items()
        }
        return price_map, market_map


# ==============================================================================
# WINDOW 3: MAIN ANALYTICS DASHBOARD WINDOW
# ==============================================================================
class AnalyticsDashboardWindow(tk.Toplevel):
    """Main results window containing all 6 requested analytical tabs."""

    def __init__(self, master, results: dict, target_date: str, find_latest_monday: bool):
        super().__init__(master)
        self.title(f"Sales & Inventory Analytics Dashboard — Target Date: {target_date}")
        self.geometry("1360x840")
        self.minsize(1040, 680)

        self.results = results
        self.target_date = target_date
        self.find_latest_monday = find_latest_monday

        self.protocol("WM_DELETE_WINDOW", master.destroy)

        mode_str = "Closest Monday (Full Week)" if find_latest_monday else "Exact Start Date (7-Day Window)"
        top_bar = ttk.Frame(self, padding=(12, 8))
        top_bar.pack(fill="x")
        ttk.Label(
            top_bar,
            text=f"Sales & Inventory Analysis  |  Reference Date: {target_date} ({mode_str})",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._build_weekly_summary_tab()
        self._build_distribution_tab()
        self._build_products_marked_tab()
        self._build_running_low_tab()
        self._build_excess_tab()
        self._build_proposals_tab()

    def _build_weekly_summary_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Weekly Summary")

        sub_nb = ttk.Notebook(tab)
        sub_nb.pack(fill="both", expand=True, padx=8, pady=8)

        week_comp = self.results["week_comparison"]

        for label, key in [
            ("With Special Sales Included", "with_special_sales"),
            ("Without Special Sales", "without_special_sales"),
        ]:
            sub_frame = ttk.Frame(sub_nb, padding=8)
            sub_nb.add(sub_frame, text=label)

            summary_dict = week_comp[key]
            df_summary = pd.DataFrame.from_dict(summary_dict, orient="index").reset_index()
            df_summary.rename(
                columns={
                    "index": "Period",
                    "Unidades": "Units Sold",
                    "net_revenue": "Net Revenue (€)",
                    "margin": "Margin (€)",
                },
                inplace=True,
            )

            tbl_frame = ttk.LabelFrame(sub_frame, text="Weekly Performance Comparison Table", padding=6)
            tbl_frame.pack(fill="x", pady=(0, 8))
            tbl = DataFrameTable(tbl_frame, df_summary, max_rows=20)
            tbl.configure(height=150)
            tbl.pack(fill="x")

            chart_frame = ttk.LabelFrame(sub_frame, text="Weekly Metrics Bar Chart", padding=6)
            chart_frame.pack(fill="both", expand=True)

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.0), dpi=100)
            periods = df_summary["Period"].tolist()
            short_labels = ["Current\nWeek", "Previous\nWeek", "Last Year\n(Actual)", "Last Year\n(Normalized)"]
            x = np.arange(len(periods))

            bars1 = ax1.bar(x, df_summary["Units Sold"], width=0.5, color="#2b5c8f")
            ax1.set_title("Units Sold by Period", fontweight="bold", fontsize=10)
            ax1.set_xticks(x)
            ax1.set_xticklabels(short_labels, fontsize=8.5)
            ax1.set_ylabel("Units")
            ax1.grid(axis="y", linestyle="--", alpha=0.4)
            for bar in bars1:
                h = bar.get_height()
                ax1.annotate(f"{h:,.0f}", xy=(bar.get_x() + bar.get_width() / 2, h),
                             xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)

            w = 0.35
            bars_rev = ax2.bar(x - w / 2, df_summary["Net Revenue (€)"], width=w, label="Net Revenue (€)",
                               color="#3a8f6e")
            bars_mar = ax2.bar(x + w / 2, df_summary["Margin (€)"], width=w, label="Margin (€)", color="#e08e45")
            ax2.set_title("Net Revenue & Margin (€)", fontweight="bold", fontsize=10)
            ax2.set_xticks(x)
            ax2.set_xticklabels(short_labels, fontsize=8.5)
            ax2.set_ylabel("Euros (€)")
            ax2.legend(fontsize=8.5)
            ax2.grid(axis="y", linestyle="--", alpha=0.4)
            for bar in bars_rev:
                h = bar.get_height()
                ax2.annotate(f"{h:,.0f}", xy=(bar.get_x() + bar.get_width() / 2, h),
                             xytext=(0, 3), textcoords="offset points", ha="center", fontsize=7.5)
            for bar in bars_mar:
                h = bar.get_height()
                ax2.annotate(f"{h:,.0f}", xy=(bar.get_x() + bar.get_width() / 2, h),
                             xytext=(0, 3), textcoords="offset points", ha="center", fontsize=7.5)

            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=chart_frame)
            canvas.get_tk_widget().pack(fill="both", expand=True)
            canvas.draw()

    def _build_distribution_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Distribution")

        dist = self.results["distributions"]
        share_pct = dist.get("special_price_unit_share", 0.0) * 100

        banner = ttk.Label(
            tab,
            text=f"Special Price Unit Share (Current Week):  {share_pct:.2f}% of total units sold",
            font=("Segoe UI", 11, "bold"),
            padding=(6, 4, 6, 10),
        )
        banner.pack(anchor="w")

        grid_frame = ttk.Frame(tab)
        grid_frame.pack(fill="both", expand=True)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)
        grid_frame.columnconfigure(2, weight=1)
        grid_frame.rowconfigure(0, weight=1)

        sections = [
            ("By Market (Mercado)", dist.get("by_market")),
            ("By Section (Sección)", dist.get("by_section")),
            ("By Category (Categoría)", dist.get("by_category")),
        ]

        for col_idx, (title, df) in enumerate(sections):
            lf = ttk.LabelFrame(grid_frame, text=title, padding=6)
            lf.grid(row=0, column=col_idx, sticky="nsew", padx=5, pady=4)
            tbl = DataFrameTable(lf, df)
            tbl.pack(fill="both", expand=True)

    def _build_products_marked_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Products Marked")

        sub_nb = ttk.Notebook(tab)
        sub_nb.pack(fill="both", expand=True, padx=8, pady=8)

        models_perf = self.results["models_perf"]["with_special_sales"]
        pred_full = self.results["predictions"]["with_special_sales"]["full_predictions"]
        pred_no_orders = self.results["predictions_no_orders"]["with_special_sales"]["full_predictions"]
        sales_full = self.results.get("sales_full", pd.DataFrame())
        weekly_sku = self.results["weekly_tables"]["with_special_sales"]["SKU"]

        best_frame = ttk.Frame(sub_nb)
        sub_nb.add(best_frame, text="Top 10 Best Selling Products")
        TableOrStockPlotPanel(
            best_frame,
            table_df=models_perf["top_10_best"],
            pred_full_df=pred_full,
            pred_no_orders_df=pred_no_orders,
            sales_full_df=sales_full,
            weekly_sku_df=weekly_sku,
            target_date=self.target_date,
            find_latest_monday=self.find_latest_monday,
            product_col="Producto",
            plot_title="Top 10 Best Selling — Stock Trajectory",
        ).pack(fill="both", expand=True)

        worst_frame = ttk.Frame(sub_nb)
        sub_nb.add(worst_frame, text="Top 10 Worst Selling Products")
        TableOrStockPlotPanel(
            worst_frame,
            table_df=models_perf["top_10_worst"],
            pred_full_df=pred_full,
            pred_no_orders_df=pred_no_orders,
            sales_full_df=sales_full,
            weekly_sku_df=weekly_sku,
            target_date=self.target_date,
            find_latest_monday=self.find_latest_monday,
            product_col="Producto",
            plot_title="Top 10 Worst Selling — Stock Trajectory",
        ).pack(fill="both", expand=True)

    def _build_running_low_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Running Low")

        pred_data = self.results["predictions"]["with_special_sales"]
        pred_no_orders_data = self.results["predictions_no_orders"]["with_special_sales"]
        sales_full = self.results.get("sales_full", pd.DataFrame())

        full_pred = pred_data["full_predictions"]
        deficit_mask = pd.Series(False, index=full_pred.index)
        for k in range(1, 9):
            deficit_mask = deficit_mask | (full_pred[f"ending_stock_week_{k}"] <= 0)
        # Ignore SKUs with zero predicted demand (e.g. 0 stock and not selling): they are not "running low"
        deficit_mask = deficit_mask & (full_pred["predicted_8w_sales"] > 0)
        sold_out_df = full_pred[deficit_mask].copy()

        weekly_sku = self.results["weekly_tables"]["with_special_sales"]["SKU"]

        priority_cols = [
            "SKU", "Producto", "Categoría", "current_stock", "predicted_8w_sales",
            "total_incoming_8w", "projected_ending_stock", "recommended_reorder_date", "recommended_order_units"
        ]
        ordered_cols = [c for c in priority_cols if c in sold_out_df.columns]
        display_df = sold_out_df[ordered_cols] if not sold_out_df.empty else sold_out_df

        prod_col = "Producto" if "Producto" in display_df.columns else "SKU"
        TableOrStockPlotPanel(
            tab,
            table_df=display_df,
            pred_full_df=pred_data["full_predictions"],
            pred_no_orders_df=pred_no_orders_data["full_predictions"],
            sales_full_df=sales_full,
            weekly_sku_df=weekly_sku,
            target_date=self.target_date,
            find_latest_monday=self.find_latest_monday,
            product_col=prod_col,
            plot_title="Running Low Products — Stock Trajectory",
            is_running_low_tab=True,
        ).pack(fill="both", expand=True)

    def _build_excess_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Excess")

        pred_data = self.results["predictions"]["with_special_sales"]
        pred_no_orders_data = self.results["predictions_no_orders"]["with_special_sales"]
        not_sold_df = pred_data["not_sold_at_all"].copy()
        sales_full = self.results.get("sales_full", pd.DataFrame())
        weekly_sku = self.results["weekly_tables"]["with_special_sales"]["SKU"]

        priority_cols = [
            "SKU", "Producto", "Categoría", "Subcategoría", "Drop",
            "current_stock", "predicted_8w_sales", "projected_ending_stock"
        ]
        ordered_cols = [c for c in priority_cols if c in not_sold_df.columns]
        display_df = not_sold_df[ordered_cols] if not not_sold_df.empty else not_sold_df

        prod_col = "Producto" if "Producto" in display_df.columns else "SKU"
        TableOrStockPlotPanel(
            tab,
            table_df=display_df,
            pred_full_df=pred_data["full_predictions"],
            pred_no_orders_df=pred_no_orders_data["full_predictions"],
            sales_full_df=sales_full,
            weekly_sku_df=weekly_sku,
            target_date=self.target_date,
            find_latest_monday=self.find_latest_monday,
            product_col=prod_col,
            plot_title="Excess Stock (Zero Predicted Sales)",
        ).pack(fill="both", expand=True)

    def _build_proposals_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Proposals")

        pred_data = self.results["predictions"]["with_special_sales"]
        full_pred = pred_data["full_predictions"].copy()
        not_sold_df = pred_data["not_sold_at_all"].copy()

        reorder_df = full_pred[full_pred["recommended_order_units"] > 0].copy()
        reorder_df = reorder_df.sort_values(by=["recommended_reorder_date", "recommended_order_units"],
                                            ascending=[True, False])

        reorder_cols = [
            c for c in [
                "SKU", "Producto", "Categoría", "current_stock",
                "predicted_8w_sales", "recommended_reorder_date", "recommended_order_units"
            ]
            if c in reorder_df.columns
        ]
        reorder_display = reorder_df[reorder_cols] if not reorder_df.empty else reorder_df

        top_box = ttk.LabelFrame(
            tab,
            text=f"Reorder Proposals (Non-Zero Recommended Units: {len(reorder_display)} SKUs)",
            padding=6,
        )
        top_box.pack(fill="both", expand=True, pady=(0, 8))
        DataFrameTable(top_box, reorder_display).pack(fill="both", expand=True)

        sale_cols = [
            c for c in [
                "SKU", "Producto", "Categoría", "Subcategoría", "Drop",
                "current_stock", "predicted_8w_sales"
            ]
            if c in not_sold_df.columns
        ]
        sale_display = not_sold_df[sale_cols].sort_values(by="current_stock",
                                                          ascending=False) if not not_sold_df.empty else not_sold_df

        bot_box = ttk.LabelFrame(
            tab,
            text=f"Sales — Recommended Products to Put on Sale ({len(sale_display)} SKUs with 0 Predicted Demand)",
            padding=6,
        )
        bot_box.pack(fill="both", expand=True)
        DataFrameTable(bot_box, sale_display).pack(fill="both", expand=True)


# ==============================================================================
# WINDOW 1: INITIAL LAUNCHER WINDOW
# ==============================================================================
class LauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SimpleDataAnalysisSales — Setup")
        self.geometry("700x310")
        self.resizable(False, False)

        self.file_path_var = tk.StringVar(value="")
        self.target_date_var = tk.StringVar(value="09-11-2025")
        self.closest_monday_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Select an Excel dataset and configure analysis parameters.")

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(
            main_frame,
            text="Sales & Inventory Analysis Pipeline",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        ttk.Label(main_frame, text="Excel Data File Path (.xlsx / .xls / .xlsb):").pack(anchor="w")
        file_row = ttk.Frame(main_frame)
        file_row.pack(fill="x", pady=(4, 12))

        self.path_entry = ttk.Entry(file_row, textvariable=self.file_path_var)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(file_row, text="Browse...", command=self._browse_file).pack(side="right")

        param_row = ttk.Frame(main_frame)
        param_row.pack(fill="x", pady=(4, 14))

        ttk.Label(param_row, text="Target Date (DD-MM-YYYY):").pack(side="left")
        ttk.Entry(param_row, textvariable=self.target_date_var, width=16).pack(side="left", padx=(8, 20))

        ttk.Checkbutton(
            param_row,
            text="Use Closest Monday (Full Week starting Monday)",
            variable=self.closest_monday_var,
        ).pack(side="left")

        self.run_btn = ttk.Button(
            main_frame,
            text="Start Cleaning & Analysis",
            command=self._start_pipeline,
        )
        self.run_btn.pack(fill="x", pady=(4, 10))

        self.progress = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 6))

        ttk.Label(main_frame, textvariable=self.status_var, foreground="#444444").pack(anchor="w")

    def _browse_file(self):
        selected = filedialog.askopenfilename(
            title="Select Sales Data Excel File",
            filetypes=[
                ("Excel Files", "*.xlsx *.xls *.xlsb"),
                ("All Files", "*.*"),
            ],
        )
        if selected:
            self.file_path_var.set(selected)

    def _start_pipeline(self):
        path = self.file_path_var.get().strip().strip('"')
        target_date = self.target_date_var.get().strip()
        find_latest_monday = self.closest_monday_var.get()

        if not path or not os.path.isfile(path):
            messagebox.showerror("Invalid File", "Please enter a valid path or select an Excel file via Browse.")
            return

        parsed_date = pd.to_datetime(target_date, format="%d-%m-%Y", errors="coerce")
        if pd.isna(parsed_date):
            messagebox.showerror("Invalid Date", "Please enter a valid date in DD-MM-YYYY format (e.g., 09-11-2025).")
            return

        self.run_btn.config(state="disabled")
        self.progress.start(12)
        self.status_var.set("Reading Excel sheets and running initial data cleaning...")

        thread = threading.Thread(
            target=self._run_initial_cleaning_worker,
            args=(path, target_date, find_latest_monday),
            daemon=True,
        )
        thread.start()

    def _run_initial_cleaning_worker(self, path: str, target_date: str, find_latest_monday: bool):
        try:
            sheets = pd.read_excel(path, sheet_name=None)
            sales_raw = sheets["VENTAS"]
            prod_raw = sheets["PRODUCTO"]
            stocks_raw = sheets["STOCK"]
            purchases_raw = sheets["COMPRAS"]

            merged_outer = pd.merge(sales_raw, prod_raw, on="SKU", how="outer")
            prod_clean = pro_p.clean_prod(prod_raw, merged_outer)
            stocks_clean = stock_p.clean_stocks(stocks_raw)
            purchases_clean = pur_p.clean_purchases(purchases_raw)

            default_country = "ES"
            accepted_countries = ["DE", "ES", "FR", "IT", "NL", "PT", "US"]
            sales_step1, _ = clean_basic_fields(sales_raw, default_country=default_country)

            price_col_sales = "PVP unitario (€)"
            price_col_prod = "PVP (€)"
            prod_pvp_map = prod_clean.set_index("SKU")[price_col_prod].to_dict()
            sales_step1["Prod_PVP"] = sales_step1["SKU"].map(prod_pvp_map)
            sales_step1[price_col_sales] = pd.to_numeric(sales_step1[price_col_sales], errors="coerce")
            sales_step1["Prod_PVP"] = pd.to_numeric(sales_step1["Prod_PVP"], errors="coerce")

            mismatch_mask = (
                    sales_step1[price_col_sales].notna()
                    & sales_step1["Prod_PVP"].notna()
                    & (abs(sales_step1[price_col_sales] - sales_step1["Prod_PVP"]) > 0.01)
            )
            mismatch_records = []
            for idx in sales_step1[mismatch_mask].index:
                row = sales_step1.loc[idx]
                fecha_str = (
                    pd.to_datetime(row["Fecha"]).strftime("%Y-%m-%d")
                    if pd.notna(row["Fecha"])
                    else "Unknown Date"
                )
                mismatch_records.append({
                    "index": idx,
                    "sku": row["SKU"],
                    "fecha": fecha_str,
                    "sales_price": float(row[price_col_sales]),
                    "prod_price": float(row["Prod_PVP"]),
                })

            invalid_mkts_set = sorted(
                set(sales_step1[~sales_step1["Mercado"].isin(accepted_countries)]["Mercado"])
            )
            invalid_markets = [
                {
                    "market": mkt,
                    "rows_affected": int((sales_step1["Mercado"] == mkt).sum()),
                }
                for mkt in invalid_mkts_set
            ]

            context_data = {
                "sales_df": sales_step1,
                "prod_df": prod_clean,
                "stocks_df": stocks_clean,
                "purchases_df": purchases_clean,
                "mismatch_records": mismatch_records,
                "invalid_markets": invalid_markets,
                "default_country": default_country,
                "target_date": target_date,
                "find_latest_monday": find_latest_monday,
            }

            self.after(0, lambda: self._prompt_user_cleaning_decisions(context_data))

        except Exception as exc:
            traceback.print_exc()  # full traceback in the console
            msg = f"Error during cleaning: {type(exc).__name__}: {exc}"
            self.after(0, lambda m=msg: self._handle_error(m))

    def _prompt_user_cleaning_decisions(self, ctx: dict):
        self.progress.stop()
        self.status_var.set("Waiting for cleaning decisions...")

        dialog = CleaningResolutionDialog(
            self,
            mismatch_records=ctx["mismatch_records"],
            invalid_markets=ctx["invalid_markets"],
            default_country=ctx["default_country"],
        )
        self.wait_window(dialog)

        price_map, market_map = dialog.get_decisions()
        self.status_var.set("Applying cleaning choices and running full sales analysis...")
        self.progress.start(12)

        thread = threading.Thread(
            target=self._run_analysis_worker,
            args=(ctx, price_map, market_map),
            daemon=True,
        )
        thread.start()

    def _run_analysis_worker(self, ctx: dict, price_map: dict, market_map: dict):
        try:
            sales = ctx["sales_df"].copy()
            prod = ctx["prod_df"]
            stocks = ctx["stocks_df"]
            purchases = ctx["purchases_df"]
            target_date = ctx["target_date"]
            find_latest_monday = ctx["find_latest_monday"]

            price_col_sales = "PVP unitario (€)"
            for idx, choice in price_map.items():
                if choice == "2" and idx in sales.index:
                    sales.loc[idx, price_col_sales] = sales.loc[idx, "Prod_PVP"]
            sales = sales.drop(columns=["Prod_PVP"], errors="ignore")

            for inv_mkt, replacement in market_map.items():
                sales.loc[sales["Mercado"] == inv_mkt, "Mercado"] = replacement

            sales_non = sales[sales["Etiquetas"].isna()].copy()
            sales_sale = sales[
                sales["Etiquetas"].notna()
                & (~sales["Etiquetas"].str.contains("influencers", na=False))
                ].copy()

            week_comparison = compute_week_comparison(
                sales_non, sales_sale, prod, target_date, find_latest_monday
            )
            distributions = compute_market_distributions(
                sales_non, sales_sale, prod, target_date, find_latest_monday
            )
            models_perf = compute_model_sell_through(
                sales_non, sales_sale, prod, stocks, target_date, find_latest_monday
            )
            weekly_tables = compute_weekly_aggregations_with_derivatives(
                sales_non, sales_sale, prod
            )

            predictions = compute_inventory_predictions_for_both(
                weekly_tables=weekly_tables,
                stock_df=stocks,
                purchases_df=purchases,
                prod_df=prod,
                target_date=target_date,
                find_latest_monday=find_latest_monday,
            )

            predictions_no_orders = compute_inventory_predictions_for_both(
                weekly_tables=weekly_tables,
                stock_df=stocks,
                purchases_df=None,
                prod_df=prod,
                target_date=target_date,
                find_latest_monday=find_latest_monday,
            )

            results = {
                "week_comparison": week_comparison,
                "distributions": distributions,
                "models_perf": models_perf,
                "weekly_tables": weekly_tables,
                "predictions": predictions,
                "predictions_no_orders": predictions_no_orders,
                "sales_full": sales,
            }

            self.after(0, lambda: self._open_dashboard_and_close_launcher(results, target_date, find_latest_monday))

        except Exception as exc:
            traceback.print_exc()  # full traceback in the console
            msg = f"Error during analysis: {type(exc).__name__}: {exc}"
            self.after(0, lambda m=msg: self._handle_error(m))

    def _open_dashboard_and_close_launcher(self, results: dict, target_date: str, find_latest_monday: bool):
        self.progress.stop()
        self.withdraw()
        AnalyticsDashboardWindow(self, results, target_date, find_latest_monday)

    def _handle_error(self, msg: str):
        self.progress.stop()
        self.run_btn.config(state="normal")
        self.status_var.set("An error occurred.")
        messagebox.showerror("Pipeline Error", msg)


if __name__ == "__main__":
    app = LauncherApp()
    app.mainloop()