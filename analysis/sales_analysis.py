import numpy as np
import pandas as pd


# ---------------------------------------------------------
# Helper: Warning-Free Date Parser (dd-mm-yyyy & ISO safe)
# ---------------------------------------------------------
def _safe_parse_date_series(series: pd.Series) -> pd.Series:
    """Parses a Series of dates supporting dd-mm-yyyy and yyyy-mm-dd without warnings."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    s = series.astype(str).str.strip()
    res = pd.to_datetime(s, format="%d-%m-%Y", errors="coerce")

    mask_iso = res.isna() & s.notna() & ~s.isin(["nan", "NaT", "None", ""])
    if mask_iso.any():
        res.loc[mask_iso] = pd.to_datetime(s.loc[mask_iso], format="%Y-%m-%d", errors="coerce")

    mask_fallback = res.isna() & s.notna() & ~s.isin(["nan", "NaT", "None", ""])
    if mask_fallback.any():
        res.loc[mask_fallback] = pd.to_datetime(s.loc[mask_fallback], dayfirst=True, errors="coerce")

    return res


# ---------------------------------------------------------
# 1. Data Preparation & Merging (Excludes Influencers)
# ---------------------------------------------------------
def prepare_sales_and_products(
        sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        is_special_price: bool = False,
):
    """Merges a sales table with the product catalog on SKU, excludes influencer gifts[cite: 1],
    tags special pricing, computes net revenue & margin, and parses dates cleanly.
    """
    sales = sales_df.copy()

    # Strictly filter out influencer gifts per business rules[cite: 1]
    tag_col = next((c for c in ["Etiquetas", "etiquetas", "tags"] if c in sales.columns), None)
    if tag_col:
        sales = sales[~sales[tag_col].astype(str).str.contains("influencer", case=False, na=False)].copy()

    sales["is_special_price"] = is_special_price

    if "unidades" in sales.columns and "Unidades" not in sales.columns:
        sales["Unidades"] = sales["unidades"]

    prod = prod_df.copy()

    # Merge sales with product catalog on SKU
    full_df = pd.merge(sales, prod, on="SKU", how="left")

    # Calculate net revenue and margin using effective price after discount
    price_col = next((c for c in ["PVP unitario (€)", "PVP (€)"] if c in full_df.columns), None)
    discount_col = next((c for c in ["Descuento (€)", "descuento"] if c in full_df.columns), None)
    cost_col = next((c for c in ["Coste unitario (€)", "Coste"] if c in full_df.columns), None)

    if price_col:
        unit_price = full_df[price_col].fillna(0)
        discount = full_df[discount_col].fillna(0) if discount_col else 0.0
        effective_price = np.maximum(0, unit_price - discount)
        full_df["net_revenue"] = effective_price * full_df["Unidades"]

        if cost_col:
            unit_cost = full_df[cost_col].fillna(0)
            full_df["margin"] = (effective_price - unit_cost) * full_df["Unidades"]
        else:
            full_df["margin"] = full_df["net_revenue"] * 0.3
    else:
        full_df["net_revenue"] = full_df["Unidades"] * 10.0
        full_df["margin"] = full_df["net_revenue"] * 0.3

    # Parse date column cleanly
    date_col = next((c for c in ["Fecha", "date", "created_at"] if c in full_df.columns), None)
    if date_col:
        full_df["Fecha"] = _safe_parse_date_series(full_df[date_col])

    return full_df


# ---------------------------------------------------------
# 2. Date Processing & Week Boundaries (Bulletproof & DataFrame-Safe)
# ---------------------------------------------------------
def get_week_boundaries(
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
):
    """Calculates current, previous, and last-year week start/end dates safely."""
    if isinstance(target_date, (pd.DataFrame, pd.Series)):
        target_date = target_date.iloc[0, 0] if isinstance(target_date, pd.DataFrame) else target_date.iloc[0]

    if isinstance(target_date, (pd.Timestamp, np.datetime64)):
        ref_date = pd.Timestamp(target_date)
    else:
        target_str = str(target_date).strip()
        ref_date = pd.to_datetime(target_str, format="%d-%m-%Y", errors="coerce")
        if pd.isna(ref_date):
            ref_date = pd.to_datetime(target_str, format="%Y-%m-%d", errors="coerce")
        if pd.isna(ref_date):
            ref_date = pd.to_datetime(target_str, dayfirst=True, errors="coerce")
        if pd.isna(ref_date):
            raise ValueError(f"Unable to parse target_date '{target_date}'.")

    if find_latest_monday:
        days_to_monday = ref_date.dayofweek  # Monday is 0
        current_monday = ref_date - pd.Timedelta(days=days_to_monday)
    else:
        current_monday = ref_date

    cur_start = current_monday
    cur_end = current_monday + pd.Timedelta(days=6)

    prv_start = cur_start - pd.Timedelta(weeks=1)
    prv_end = cur_end - pd.Timedelta(weeks=1)

    ly_start = cur_start - pd.Timedelta(weeks=52)
    ly_end = cur_end - pd.Timedelta(weeks=52)

    return {
        "current_start": cur_start,
        "current_end": cur_end,
        "prev_start": prv_start,
        "prev_end": prv_end,
        "ly_start": ly_start,
        "ly_end": ly_end,
    }


# ---------------------------------------------------------
# 3. Period Comparison Engine (Supports Optional Market Filter)
# ---------------------------------------------------------
def compute_week_comparison(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        market: str = None,
):
    """Computes units, net revenue, and margin for target week, previous week,
    and last year for both with and without special sales (optionally filtered by market).
    """
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True)
    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    if market and "Mercado" in combined_full.columns:
        combined_full = combined_full[combined_full["Mercado"] == market]
        norm_full = norm_full[norm_full["Mercado"] == market]

    def _calculate(full_sales):
        weeks = get_week_boundaries(target_date, find_latest_monday)

        def filter_week(df, start, end):
            return df[(df["Fecha"] >= start) & (df["Fecha"] <= end)]

        cur_sales = filter_week(full_sales, weeks["current_start"], weeks["current_end"])
        prv_sales = filter_week(full_sales, weeks["prev_start"], weeks["prev_end"])
        ly_sales = filter_week(full_sales, weeks["ly_start"], weeks["ly_end"])

        def summarize(df):
            return {
                "Unidades": df["Unidades"].sum() if not df.empty else 0,
                "net_revenue": df["net_revenue"].sum() if not df.empty else 0,
                "margin": df["margin"].sum() if "margin" in df.columns and not df.empty else 0,
            }

        cur_summary = summarize(cur_sales)
        prv_summary = summarize(prv_sales)
        ly_summary = summarize(ly_sales)

        cur_month_days = weeks["current_start"].days_in_month
        ly_month_days = weeks["ly_start"].days_in_month
        norm_factor = cur_month_days / ly_month_days if ly_month_days > 0 else 1.0

        ly_normalized = {
            "Unidades": ly_summary["Unidades"] * norm_factor,
            "net_revenue": ly_summary["net_revenue"] * norm_factor,
            "margin": ly_summary["margin"] * norm_factor,
        }

        return {
            "Current Week": cur_summary,
            "Previous Week": prv_summary,
            "Last Year Same Week (Actual)": ly_summary,
            "Last Year Same Week (Month-Normalized)": ly_normalized,
        }

    return {
        "with_special_sales": _calculate(combined_full),
        "without_special_sales": _calculate(norm_full),
    }


# ---------------------------------------------------------
# 4. Multi-Dimensional Distribution & Special Pricing Share
# ---------------------------------------------------------
def compute_market_distributions(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        market: str = None,
):
    """Computes distribution by market, section, category, and special price share."""
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True)
    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    weeks = get_week_boundaries(target_date, find_latest_monday)
    cur_sales = combined_full[
        (combined_full["Fecha"] >= weeks["current_start"])
        & (combined_full["Fecha"] <= weeks["current_end"])
    ]

    if market and "Mercado" in cur_sales.columns:
        cur_sales = cur_sales[cur_sales["Mercado"] == market]

    dist_market = cur_sales.groupby("Mercado")[["Unidades", "net_revenue", "margin"]].sum().reset_index() if "Mercado" in cur_sales.columns else pd.DataFrame()
    dist_section = cur_sales.groupby("Sección")[["Unidades", "net_revenue", "margin"]].sum().reset_index() if "Sección" in cur_sales.columns else pd.DataFrame()
    dist_category = cur_sales.groupby("Categoría")[["Unidades", "net_revenue", "margin"]].sum().reset_index() if "Categoría" in cur_sales.columns else pd.DataFrame()

    special_units = cur_sales[cur_sales["is_special_price"] == True]["Unidades"].sum() if "is_special_price" in cur_sales.columns else 0
    total_units = cur_sales["Unidades"].sum()
    special_share = (special_units / total_units) if total_units > 0 else 0

    return {
        "by_market": dist_market,
        "by_section": dist_section,
        "by_category": dist_category,
        "special_price_unit_share": special_share,
    }


# ---------------------------------------------------------
# 5. Model Performance & Sell-Through
# ---------------------------------------------------------
def compute_model_sell_through(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        stock_df: pd.DataFrame,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        market: str = None,
):
    """Computes top 10 best and worst models with inventory sell-through."""
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True)
    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    weeks = get_week_boundaries(target_date, find_latest_monday)

    def _calc_sell_through(full_sales):
        cur_sales = full_sales[
            (full_sales["Fecha"] >= weeks["current_start"])
            & (full_sales["Fecha"] <= weeks["current_end"])
        ]

        if market and "Mercado" in cur_sales.columns:
            cur_sales = cur_sales[cur_sales["Mercado"] == market]

        model_perf = (
            cur_sales.groupby("Producto")
            .agg(
                total_units=("Unidades", "sum"),
                special_units=("Unidades", lambda x: x[cur_sales.loc[x.index, "is_special_price"] == True].sum()),
                total_revenue=("net_revenue", "sum"),
                sold_stock=("Unidades", "sum"),
            )
            .reset_index()
        )

        model_perf["pct_sold_at_sale"] = np.where(
            model_perf["total_units"] > 0,
            (model_perf["special_units"] / model_perf["total_units"]) * 100,
            0.0
        )

        if stock_df is not None and not stock_df.empty:
            stock_with_prod = pd.merge(stock_df, prod_df[["SKU", "Producto"]], on="SKU", how="left")
            stock_col = next((c for c in ["Stock disponible (uds)", "ending_stock", "stock"] if c in stock_with_prod.columns), "Stock disponible (uds)")

            stock_agg = stock_with_prod.groupby("Producto")[stock_col].sum().reset_index()
            stock_agg.rename(columns={stock_col: "Stock disponible (uds)"}, inplace=True)

            model_perf = pd.merge(model_perf, stock_agg, on="Producto", how="left")
            model_perf["Stock disponible (uds)"] = model_perf["Stock disponible (uds)"].fillna(0)
            model_perf["initial_stock"] = model_perf["Stock disponible (uds)"] + model_perf["sold_stock"]
        else:
            model_perf["initial_stock"] = model_perf["sold_stock"]

        model_perf["sell_through"] = np.where(
            model_perf["initial_stock"] > 0,
            model_perf["sold_stock"] / model_perf["initial_stock"],
            0,
        )

        top_best = model_perf.sort_values(by="total_units", ascending=False).head(10)
        top_worst = model_perf.sort_values(by="total_units", ascending=True).head(10)
        return {"top_10_best": top_best, "top_10_worst": top_worst}

    return {
        "with_special_sales": _calc_sell_through(combined_full),
        "without_special_sales": _calc_sell_through(norm_full),
    }


# ---------------------------------------------------------
# 6. Granular Weekly Hierarchies & Derivatives (Includes Market)
# ---------------------------------------------------------
def compute_weekly_aggregations_with_derivatives(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
):
    """Builds granular weekly tables with 1st and 2nd derivatives of units sold,
    including Market-level and SKU-Market breakdowns.
    """
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True)
    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    def _build_pipeline(full_sales):
        df = full_sales.copy()
        df["week_start"] = df["Fecha"] - pd.to_timedelta(df["Fecha"].dt.dayofweek, unit="d")

        def build_agg(group_cols):
            valid_cols = [c for c in group_cols if c in df.columns]
            cols = ["week_start"] + valid_cols
            agg_df = (
                df.groupby(cols)
                .agg(
                    units=("Unidades", "sum"),
                    special_units=("Unidades", lambda x: x[df.loc[x.index, "is_special_price"] == True].sum()),
                    net_revenue=("net_revenue", "sum"),
                    margin=("margin", "sum"),
                )
                .reset_index()
                .sort_values(by=cols)
            )

            agg_df["pct_sold_at_sale"] = np.where(
                agg_df["units"] > 0,
                (agg_df["special_units"] / agg_df["units"]) * 100,
                0.0
            )
            agg_df.drop(columns=["special_units"], inplace=True)

            if valid_cols:
                agg_df["first_derivative"] = agg_df.groupby(valid_cols)["units"].diff()
                agg_df["second_derivative"] = agg_df.groupby(valid_cols)["first_derivative"].diff()
            else:
                agg_df["first_derivative"] = agg_df["units"].diff()
                agg_df["second_derivative"] = agg_df["first_derivative"].diff()

            return agg_df

        return {
            "total": build_agg([]),
            "Mercado": build_agg(["Mercado"]),
            "Categoría": build_agg(["Categoría"]),
            "Subcategoría": build_agg(["Subcategoría"]),
            "Producto": build_agg(["Producto"]),
            "SKU": build_agg(["SKU"]),
            "SKU_Mercado": build_agg(["SKU", "Mercado"]),
            "Drop": build_agg(["Drop"]),
        }

    return {
        "with_special_sales": _build_pipeline(combined_full),
        "without_special_sales": _build_pipeline(norm_full),
    }


# ---------------------------------------------------------
# 7. Influencer Tracking
# ---------------------------------------------------------
def compute_influencer_metrics(
        influencer_df: pd.DataFrame,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
):
    """Computes total influencer mentions per SKU for specific weeks and rolling windows."""
    if influencer_df is None or influencer_df.empty:
        return None

    influencer_df = influencer_df.copy()
    date_col = next((c for c in ["Fecha", "date", "created_at"] if c in influencer_df.columns), "Fecha")
    influencer_df[date_col] = _safe_parse_date_series(influencer_df[date_col])

    weeks = get_week_boundaries(target_date, find_latest_monday)
    ref_end = weeks["current_end"]

    influencer_df["week_start"] = influencer_df[date_col] - pd.to_timedelta(
        influencer_df[date_col].dt.dayofweek, unit="d"
    )

    inf_specific = (
        influencer_df.groupby(["SKU", "week_start"])
        .size()
        .reset_index(name="influencer_mentions_specific_week")
    )

    rolling_results = []
    for w in range(1, 6):
        window_start = ref_end - pd.Timedelta(weeks=w) + pd.Timedelta(days=1)
        mask = (influencer_df[date_col] >= window_start) & (influencer_df[date_col] <= ref_end)
        sub = (
            influencer_df[mask]
            .groupby("SKU")
            .size()
            .reset_index(name=f"influencer_mentions_past_{w}_weeks_total")
        )
        rolling_results.append(sub)

    return {
        "specific_weekly": inf_specific,
        "rolling_totals": rolling_results,
    }


# ---------------------------------------------------------
# 8. Purchases Analytics Table
# ---------------------------------------------------------
def compute_purchase_metrics(purchases_df: pd.DataFrame):
    """Computes average lead time and delivery variance (actual vs estimated)."""
    if purchases_df is None or purchases_df.empty:
        return None

    purchases = purchases_df.copy()

    date_col = next((c for c in ["Fecha", "created_at", "date", "order_date"] if c in purchases.columns), None)
    est_col = next((c for c in ["Fecha llegada estimada", "estimated_delivery_date", "estimated_date"] if c in purchases.columns), None)
    act_col = next((c for c in ["Fecha llegada real", "Fecha llegada efectiva", "delivery_date", "actual_date"] if c in purchases.columns), None)

    for col in [date_col, act_col, est_col]:
        if col and col in purchases.columns:
            purchases[col] = _safe_parse_date_series(purchases[col])

    if date_col and act_col:
        purchases["actual_lead_time"] = (purchases[act_col] - purchases[date_col]).dt.days
    else:
        purchases["actual_lead_time"] = np.nan

    if act_col and est_col:
        purchases["delivery_variance"] = (purchases[act_col] - purchases[est_col]).dt.days
    else:
        purchases["delivery_variance"] = np.nan

    return (
        purchases.groupby("SKU")
        .agg(
            avg_lead_time_days=("actual_lead_time", "mean"),
            avg_delivery_variance_days=("delivery_variance", "mean"),
            total_purchases=("SKU", "count"),
        )
        .reset_index()
    )


# ---------------------------------------------------------
# 9. 4-Week Mutually Exclusive Inventory & Sales Prediction Engine
# ---------------------------------------------------------
def predict_inventory_status_4_weeks_sku(
        weekly_sku_df: pd.DataFrame,
        stock_df: pd.DataFrame,
        prod_df: pd.DataFrame = None,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        weeks_horizon: int = 4,
        excess_stock_threshold: int = 60,
        market: str = None,
):
    """Predicts SKU-level inventory status over 4 weeks with mutually exclusive buckets
    (no overlap between running low and excess stock) and optional market filtering.
    """
    if weekly_sku_df is None or weekly_sku_df.empty or stock_df is None or stock_df.empty:
        return None

    df_to_use = weekly_sku_df.copy()
    if market and "Mercado" in df_to_use.columns:
        df_to_use = df_to_use[df_to_use["Mercado"] == market]

    # Get latest weekly record per SKU
    latest_weeks = (
        df_to_use.sort_values("week_start")
        .groupby("SKU")
        .last()
        .reset_index()
    )

    stock_col = next((c for c in ["Stock disponible (uds)", "ending_stock", "stock"] if c in stock_df.columns), "Stock disponible (uds)")
    stock_subset = stock_df[["SKU", stock_col]].copy()
    stock_subset.rename(columns={stock_col: "current_stock"}, inplace=True)

    # Merge stock and sales derivative data on SKU
    pred_df = pd.merge(latest_weeks, stock_subset, on="SKU", how="right")
    pred_df["current_stock"] = pred_df["current_stock"].fillna(0)
    pred_df["units"] = pred_df["units"].fillna(0)
    pred_df["first_derivative"] = pred_df["first_derivative"].fillna(0)
    pred_df["second_derivative"] = pred_df["second_derivative"].fillna(0)

    # Sales velocity (units/week)
    pred_df["sales_velocity"] = np.maximum(0, pred_df["units"] + pred_df["first_derivative"])
    pred_df["has_sales_history"] = pred_df["units"] > 0

    # Project over the 4-week horizon
    pred_df["projected_sales_4w"] = pred_df["sales_velocity"] * weeks_horizon
    pred_df["projected_stock_4w"] = pred_df["current_stock"] - pred_df["projected_sales_4w"]

    # Mutually Exclusive Categorization Logic (Prevents overlap between Low Stock & Excess Stock)
    # 1. Critical Stockouts: Projected stock <= 0 within 4 weeks
    critical_stockouts = pred_df[pred_df["projected_stock_4w"] <= 0].copy()
    critical_stockouts["inventory_status"] = "Critical Stockout (<=0)"

    # Remaining items with positive stock after 4 weeks
    positive_remaining = pred_df[pred_df["projected_stock_4w"] > 0].copy()

    # 2. Active Stock with Zero Sales Velocity (Dead Stock Risk)
    dead_stock = positive_remaining[
        (positive_remaining["current_stock"] > 0) & (positive_remaining["sales_velocity"] == 0)
    ].copy()
    dead_stock["inventory_status"] = "Dead Stock (Active Inventory, Zero Velocity)"

    # Active moving items (positive stock & positive sales velocity)
    moving_items = positive_remaining[positive_remaining["sales_velocity"] > 0].copy()

    # 3. Excess Stock: Moving items with high leftover buffer (>= excess_stock_threshold)
    excess_stock = moving_items[moving_items["projected_stock_4w"] >= excess_stock_threshold].copy()
    excess_stock["inventory_status"] = f"Excess Stock (>={excess_stock_threshold} units)"

    # 4. Mutually Exclusive Low Stock Tiers (strictly below excess threshold)
    non_excess_moving = moving_items[moving_items["projected_stock_4w"] < excess_stock_threshold].copy()

    low_under_5 = non_excess_moving[non_excess_moving["projected_stock_4w"] < 5].copy()
    low_under_5["inventory_status"] = "Low Stock (<5 units)"

    low_5_to_9 = non_excess_moving[
        (non_excess_moving["projected_stock_4w"] >= 5) & (non_excess_moving["projected_stock_4w"] < 10)
    ].copy()
    low_5_to_9["inventory_status"] = "Low Stock (5-9 units)"

    low_10_to_29 = non_excess_moving[
        (non_excess_moving["projected_stock_4w"] >= 10) & (non_excess_moving["projected_stock_4w"] < 30)
    ].copy()
    low_10_to_29["inventory_status"] = "Low Stock (10-29 units)"

    healthy_stock = non_excess_moving[non_excess_moving["projected_stock_4w"] >= 30].copy()
    healthy_stock["inventory_status"] = "Healthy Stock (30-59 units)"

    # Combine labeled status back into full_predictions
    categorized_all = pd.concat(
        [critical_stockouts, dead_stock, excess_stock, low_under_5, low_5_to_9, low_10_to_29, healthy_stock],
        ignore_index=True
    )

    # Separate datasets for items WITH vs WITHOUT sales history
    catalog_with_sales = categorized_all[categorized_all["has_sales_history"]].copy()
    catalog_without_sales = categorized_all[~categorized_all["has_sales_history"]].copy()

    # Merge product metadata
    if prod_df is not None and not prod_df.empty:
        meta_cols = [c for c in ["SKU", "Producto", "Color", "Talla", "Categoría", "Subcategoría", "Drop", "Sección"] if c in prod_df.columns]
        if meta_cols:
            meta_dedup = prod_df[meta_cols].drop_duplicates("SKU")
            critical_stockouts = pd.merge(critical_stockouts, meta_dedup, on="SKU", how="left")
            dead_stock = pd.merge(dead_stock, meta_dedup, on="SKU", how="left")
            excess_stock = pd.merge(excess_stock, meta_dedup, on="SKU", how="left")
            low_under_5 = pd.merge(low_under_5, meta_dedup, on="SKU", how="left")
            low_5_to_9 = pd.merge(low_5_to_9, meta_dedup, on="SKU", how="left")
            low_10_to_29 = pd.merge(low_10_to_29, meta_dedup, on="SKU", how="left")
            healthy_stock = pd.merge(healthy_stock, meta_dedup, on="SKU", how="left")
            catalog_with_sales = pd.merge(catalog_with_sales, meta_dedup, on="SKU", how="left")
            catalog_without_sales = pd.merge(catalog_without_sales, meta_dedup, on="SKU", how="left")
            categorized_all = pd.merge(categorized_all, meta_dedup, on="SKU", how="left")

    return {
        "critical_stockouts": critical_stockouts,
        "dead_stock_zero_velocity": dead_stock,
        "excess_stock": excess_stock,
        "low_stock_under_5": low_under_5,
        "low_stock_5_to_9": low_5_to_9,
        "low_stock_10_to_29": low_10_to_29,
        "healthy_stock": healthy_stock,
        "catalog_items_with_sales": catalog_with_sales,
        "catalog_items_without_sales": catalog_without_sales,
        "full_predictions": categorized_all,
    }


# ---------------------------------------------------------
# 10. 8-Week Purchase-Aware Inventory Forecast (feeds the dashboard)
# ---------------------------------------------------------
# NOTE: the dashboard hard-codes 8 weeks (ending_stock_week_1..8), so keep weeks_horizon=8.
DEFAULT_LEAD_TIME_DAYS = 30   # used when the purchases sheet has no usable order->arrival history
LOOKBACK_WEEKS = 4            # weekly demand = average units/week over the last N weeks


def _latest_stock_per_sku(stock_df: pd.DataFrame) -> pd.DataFrame:
    """One row per SKU with the most recent stock snapshot as `current_stock`."""
    stock_col = next(
        (c for c in ["Stock disponible (uds)", "ending_stock", "stock"] if c in stock_df.columns),
        "Stock disponible (uds)",
    )
    s = stock_df.copy()
    if "Fecha stock" in s.columns:
        s["Fecha stock"] = _safe_parse_date_series(s["Fecha stock"])
        s = s.sort_values("Fecha stock", kind="stable")
    s = s.drop_duplicates("SKU", keep="last")
    s["current_stock"] = pd.to_numeric(s[stock_col], errors="coerce").fillna(0).clip(lower=0)
    return s[["SKU", "current_stock"]]


def _purchase_arrival_dates(purchases: pd.DataFrame) -> pd.Series:
    """Effective arrival date (real if known, otherwise estimated), normalized to midnight."""
    arrival_col = next(
        (c for c in ["Fecha llegada efectiva", "Fecha llegada real", "Fecha llegada estimada"]
         if c in purchases.columns),
        None,
    )
    if arrival_col is None:
        return pd.Series(pd.NaT, index=purchases.index, dtype="datetime64[ns]")
    return _safe_parse_date_series(purchases[arrival_col]).dt.normalize()


def _incoming_units_by_week(purchases_df, forecast_start: pd.Timestamp, horizon: int) -> pd.DataFrame:
    """Units arriving per SKU in each forecast week (week 1 = the 7 days after `forecast_start`).

    Only orders whose arrival date falls inside the horizon are counted. Orders that already
    arrived are assumed to be in the stock snapshot; open orders with a past estimated date
    are ignored because we cannot tell whether they are late or cancelled.
    """
    cols = [f"incoming_week_{k}" for k in range(1, horizon + 1)]
    empty = pd.DataFrame(columns=cols, dtype=float)
    empty.index.name = "SKU"
    if purchases_df is None or purchases_df.empty or "SKU" not in purchases_df.columns:
        return empty

    p = purchases_df.copy()
    p["_arrival"] = _purchase_arrival_dates(p)
    p["_units"] = pd.to_numeric(p["Unidades"], errors="coerce").fillna(0)
    p = p[p["_arrival"].notna() & (p["_arrival"] > forecast_start)]
    if p.empty:
        return empty

    p["_week"] = np.ceil((p["_arrival"] - forecast_start) / pd.Timedelta(days=7)).astype(int)
    p = p[(p["_week"] >= 1) & (p["_week"] <= horizon)]
    if p.empty:
        return empty

    table = p.pivot_table(index="SKU", columns="_week", values="_units", aggfunc="sum", fill_value=0)
    table = table.reindex(columns=range(1, horizon + 1), fill_value=0)
    table.columns = cols
    return table.astype(float)


def _lead_times_by_sku(purchases_df):
    """Average order->arrival lead time (days) per SKU, plus a global median fallback."""
    if purchases_df is None or purchases_df.empty or "SKU" not in purchases_df.columns:
        return pd.Series(dtype=float), float(DEFAULT_LEAD_TIME_DAYS)

    p = purchases_df.copy()
    order_col = next((c for c in ["Fecha pedido", "Fecha de pedido", "Fecha compra", "Fecha"] if c in p.columns), None)
    arrival_col = next(
        (c for c in ["Fecha llegada real", "Fecha llegada efectiva", "Fecha llegada estimada"] if c in p.columns),
        None,
    )
    if order_col is None or arrival_col is None:
        return pd.Series(dtype=float), float(DEFAULT_LEAD_TIME_DAYS)

    p["_lt"] = (_safe_parse_date_series(p[arrival_col]) - _safe_parse_date_series(p[order_col])).dt.days
    p = p[p["_lt"] > 0]
    if p.empty:
        return pd.Series(dtype=float), float(DEFAULT_LEAD_TIME_DAYS)
    return p.groupby("SKU")["_lt"].mean(), float(p["_lt"].median())


def predict_inventory_8_weeks_sku(
        weekly_sku_df: pd.DataFrame,
        stock_df: pd.DataFrame,
        purchases_df: pd.DataFrame = None,
        prod_df: pd.DataFrame = None,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        weeks_horizon: int = 8,
        lookback_weeks: int = LOOKBACK_WEEKS,
        market: str = None,
):
    """SKU-level 8-week stock projection that adds incoming purchase orders to stock.

    Method
      * Forecast starts at the end of the target week (`current_end`).
      * Weekly demand per SKU = average units/week over the last `lookback_weeks` weeks (flat).
      * Ending stock week k = max(0, ending stock week k-1 + incoming_k - sales_k).
      * A SKU is at risk when demand > 0 and its cumulative balance (stock + incoming - sales,
        not floored at zero) reaches <= 0 inside the horizon. Recommended order units cover the
        worst deficit; the reorder date is the projected stock-out date minus the SKU's average
        lead time (global median, or DEFAULT_LEAD_TIME_DAYS if there is no history), never earlier
        than the day after the forecast starts.

    Pass purchases_df=None for the "without incoming orders" scenario.
    """
    if weekly_sku_df is None or weekly_sku_df.empty or stock_df is None or stock_df.empty:
        return None

    H = weeks_horizon
    weeks = get_week_boundaries(target_date, find_latest_monday)
    forecast_start = weeks["current_end"]

    # ---- demand: average weekly units over the lookback window ----
    sales = weekly_sku_df.copy()
    if market and "Mercado" in sales.columns:
        sales = sales[sales["Mercado"] == market]
    sales["week_start"] = pd.to_datetime(sales["week_start"])
    window_start = forecast_start - pd.Timedelta(days=7 * lookback_weeks)
    recent = sales[(sales["week_start"] > window_start) & (sales["week_start"] <= forecast_start)]
    velocity = recent.groupby("SKU")["units"].sum() / lookback_weeks

    # ---- supply: stock snapshot + incoming purchase orders ----
    stock = _latest_stock_per_sku(stock_df)
    incoming = _incoming_units_by_week(purchases_df, forecast_start, H)

    skus = pd.Index(stock["SKU"]).union(velocity.index).union(incoming.index)
    pred = pd.DataFrame({"SKU": skus}).merge(stock, on="SKU", how="left")
    pred["current_stock"] = pred["current_stock"].fillna(0.0)
    pred["weekly_velocity"] = pred["SKU"].map(velocity).fillna(0.0)
    pred["has_recent_sales"] = pred["weekly_velocity"] > 0

    n = len(pred)
    stock0 = pred["current_stock"].to_numpy(dtype=float)
    vel = pred["weekly_velocity"].to_numpy(dtype=float)
    inc_matrix = incoming.reindex(pred["SKU"]).fillna(0.0).to_numpy(dtype=float)
    if inc_matrix.shape[1] != H:  # no purchases -> empty frame has the right columns, but be safe
        inc_matrix = np.zeros((n, H))
    sales_matrix = np.tile(vel.reshape(-1, 1), (1, H))

    # ---- week-by-week stock (floored at zero) and cumulative balance (not floored) ----
    ending = np.zeros((n, H))
    running = stock0.copy()
    for k in range(H):
        running = np.maximum(0.0, running + inc_matrix[:, k] - sales_matrix[:, k])
        ending[:, k] = running
    balance = stock0.reshape(-1, 1) + np.cumsum(inc_matrix - sales_matrix, axis=1)

    # ---- stock-out risk, order size and reorder date ----
    at_risk = (vel > 0) & (balance <= 0).any(axis=1)
    shortfall = np.maximum(0.0, -balance.min(axis=1))
    order_units = np.where(at_risk, np.ceil(shortfall), 0).astype(int)

    k0 = np.argmax(balance <= 0, axis=1)  # 0-based week in which the balance first hits <= 0
    prev_balance = np.where(k0 == 0, stock0, balance[np.arange(n), np.maximum(k0 - 1, 0)])
    frac = np.where(vel > 0, np.clip(prev_balance / np.where(vel > 0, vel, 1.0), 0.0, 1.0), 0.0)
    days_to_stockout = k0 * 7 + frac * 7

    lead_by_sku, lead_default = _lead_times_by_sku(purchases_df)
    lead_days = pred["SKU"].map(lead_by_sku).fillna(lead_default).to_numpy(dtype=float)
    offset_days = np.maximum(1.0, np.floor(days_to_stockout - lead_days))
    reorder_dates = pd.Series(
        (forecast_start + pd.to_timedelta(offset_days, unit="D")).to_numpy(), index=pred.index
    ).where(order_units > 0)

    # ---- assemble output ----
    weekly_cols = pd.concat(
        [
            pd.DataFrame(sales_matrix, columns=[f"sales_week_{k}" for k in range(1, H + 1)], index=pred.index),
            pd.DataFrame(inc_matrix, columns=[f"incoming_week_{k}" for k in range(1, H + 1)], index=pred.index),
            pd.DataFrame(ending, columns=[f"ending_stock_week_{k}" for k in range(1, H + 1)], index=pred.index),
        ],
        axis=1,
    ).round(1)
    pred = pd.concat([pred, weekly_cols], axis=1)

    pred["predicted_8w_sales"] = sales_matrix.sum(axis=1).round(1)
    pred["total_incoming_8w"] = inc_matrix.sum(axis=1).round(1)
    pred["projected_ending_stock"] = ending[:, -1].round(1)
    pred["recommended_order_units"] = order_units
    pred["recommended_reorder_date"] = reorder_dates
    pred["weekly_velocity"] = pred["weekly_velocity"].round(2)

    if prod_df is not None and not prod_df.empty:
        meta_cols = [c for c in ["SKU", "Producto", "Color", "Talla", "Categoría", "Subcategoría", "Drop", "Sección"]
                     if c in prod_df.columns]
        if len(meta_cols) > 1:
            pred = pred.merge(prod_df[meta_cols].drop_duplicates("SKU"), on="SKU", how="left")

    stock_cols = [f"ending_stock_week_{k}" for k in range(1, H + 1)]
    sold_out_mask = (pred[stock_cols] <= 0).any(axis=1) & (pred["predicted_8w_sales"] > 0)
    not_sold_mask = (pred["current_stock"] > 0) & (pred["predicted_8w_sales"] == 0)

    return {
        "full_predictions": pred,
        "sold_out": pred[sold_out_mask].copy(),
        "not_sold_at_all": pred[not_sold_mask].copy(),
    }


def compute_inventory_predictions_for_both(
        weekly_tables: dict,
        stock_df: pd.DataFrame,
        purchases_df: pd.DataFrame = None,
        prod_df: pd.DataFrame = None,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        weeks_horizon: int = 8,
        market: str = None,
):
    """8-week predictions for both with_special_sales and without_special_sales.

    purchases_df=None gives the 'without incoming orders' scenario used by the dashboard toggle.
    """
    key = "SKU_Mercado" if market else "SKU"
    return {
        scenario: predict_inventory_8_weeks_sku(
            weekly_tables[scenario][key], stock_df, purchases_df, prod_df,
            target_date, find_latest_monday, weeks_horizon, LOOKBACK_WEEKS, market,
        )
        for scenario in ("with_special_sales", "without_special_sales")
    }
