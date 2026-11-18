import numpy as np
import pandas as pd


# ---------------------------------------------------------
# 1. Data Preparation & Merging (with dd-mm-yyyy date parsing)
# ---------------------------------------------------------
def prepare_sales_and_products(
        sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        is_special_price: bool = False,
        date_format: str = '%d-%m-%Y'
):
    """Merges a sales table (normal or special) with the product table,
    tagging transactions with is_special_price, calculating net_revenue, margin,
    and enforcing dd-mm-yyyy date parsing.
    """
    sales = sales_df.copy()
    sales["is_special_price"] = is_special_price

    if "unidades" in sales.columns and "Unidades" not in sales.columns:
        sales["Unidades"] = sales["unidades"]

    prod = prod_df.copy()

    # Merge sales with product data on SKU
    full_df = pd.merge(sales, prod, on="SKU", how="left")

    # Calculate net revenue per item and total net revenue using PVP (€) and Coste unitario (€)
    if "PVP (€)" in full_df.columns and "Coste unitario (€)" in full_df.columns:
        full_df["net_revenue_per_item"] = (
                full_df["PVP (€)"] - full_df["Coste unitario (€)"]
        )
        full_df["net_revenue"] = (
                full_df["net_revenue_per_item"] * full_df["Unidades"]
        )
        if "margin" not in full_df.columns:
            full_df["margin"] = full_df["net_revenue"] * 0.3  # placeholder formula
    else:
        full_df["net_revenue"] = full_df["Unidades"] * 10.0  # fallback

    # Handle date column mapping with dd-mm-yyyy format and safe fallback
    date_col = next(
        (c for c in ["Fecha", "date", "created_at"] if c in full_df.columns),
        None,
    )
    if date_col:
        parsed = pd.to_datetime(full_df[date_col], format=date_format, errors="coerce")
        if parsed.isna().all() or parsed.isna().mean() > 0.5:
            parsed = pd.to_datetime(full_df[date_col], errors="coerce", dayfirst=True)
        full_df["Fecha"] = parsed

    return full_df


# ---------------------------------------------------------
# 2. Date Processing & Week Boundaries (Bulletproof)
# ---------------------------------------------------------
def get_week_boundaries(
        target_date: str = "09-11-2025", find_latest_monday: bool = True, date_format: str = '%d-%m-%Y'
):
    """Calculates current, previous, and last-year week start/end dates safely without any mapping errors."""
    if isinstance(target_date, (pd.Timestamp, np.datetime64)):
        ref_date = pd.Timestamp(target_date)
    else:
        ref_date = pd.to_datetime(target_date, format=date_format, errors="coerce")
        if pd.isna(ref_date):
            ref_date = pd.to_datetime(target_date, dayfirst=True, errors="coerce")
        if pd.isna(ref_date):
            ref_date = pd.to_datetime(target_date, errors="coerce")
        if pd.isna(ref_date):
            raise ValueError(f"Unable to parse target_date '{target_date}'.")

    if find_latest_monday:
        days_to_monday = ref_date.dayofweek  # Lunes es 0
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
# 3. Period Comparison Engine
# ---------------------------------------------------------
def compute_week_comparison(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        date_format: str = '%d-%m-%Y',
):
    """Computes units, net revenue, and margin for target week, previous week,
    and last year for both with and without special sales.
    """
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False, date_format=date_format)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True, date_format=date_format)
    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    def _calculate(full_sales):
        weeks = get_week_boundaries(target_date, find_latest_monday, date_format=date_format)

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
        date_format: str = '%d-%m-%Y',
):
    """Computes distribution by market, section, category, and special price share."""
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False, date_format=date_format)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True, date_format=date_format)
    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    weeks = get_week_boundaries(target_date, find_latest_monday, date_format=date_format)
    cur_sales = combined_full[
        (combined_full["Fecha"] >= weeks["current_start"])
        & (combined_full["Fecha"] <= weeks["current_end"])
        ]

    dist_market = cur_sales.groupby("Mercado")[
        ["Unidades", "net_revenue"]].sum().reset_index() if "Mercado" in cur_sales.columns else pd.DataFrame()
    dist_section = cur_sales.groupby("Sección")[
        ["Unidades", "net_revenue"]].sum().reset_index() if "Sección" in cur_sales.columns else pd.DataFrame()
    dist_category = cur_sales.groupby("Categoría")[
        ["Unidades", "net_revenue"]].sum().reset_index() if "Categoría" in cur_sales.columns else pd.DataFrame()

    special_units = cur_sales[cur_sales["is_special_price"] == True][
        "Unidades"].sum() if "is_special_price" in cur_sales.columns else 0
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
        date_format: str = '%d-%m-%Y',
):
    """Computes top 10 best and worst models with inventory sell-through."""
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False, date_format=date_format)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True, date_format=date_format)
    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    weeks = get_week_boundaries(target_date, find_latest_monday, date_format=date_format)

    def _calc_sell_through(full_sales):
        cur_sales = full_sales[
            (full_sales["Fecha"] >= weeks["current_start"])
            & (full_sales["Fecha"] <= weeks["current_end"])
            ]

        model_perf = (
            cur_sales.groupby("Producto")
            .agg(
                total_units=("Unidades", "sum"),
                special_units=("Unidades", lambda x: x[
                    cur_sales.loc[
                        x.index, "is_special_price"] == True].sum() if "is_special_price" in cur_sales.columns else 0),
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
            stock_col = next(
                (c for c in ["Stock disponible (uds)", "ending_stock", "stock"] if c in stock_with_prod.columns),
                "Stock disponible (uds)")

            stock_agg = (
                stock_with_prod.groupby("Producto")[stock_col].sum().reset_index()
            )
            stock_agg.rename(columns={stock_col: "Stock disponible (uds)"}, inplace=True)

            model_perf = pd.merge(model_perf, stock_agg, on="Producto", how="left")
            model_perf["Stock disponible (uds)"] = model_perf["Stock disponible (uds)"].fillna(0)
            model_perf["initial_stock"] = (
                    model_perf["Stock disponible (uds)"] + model_perf["sold_stock"]
            )
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
# 6. Granular Weekly Hierarchies & Derivatives
# ---------------------------------------------------------
def compute_weekly_aggregations_with_derivatives(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        date_format: str = '%d-%m-%Y',
):
    """Builds granular weekly tables with 1st and 2nd derivatives of units sold,
    including the percentage of units sold at special price (`pct_sold_at_sale`).
    """
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False, date_format=date_format)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True, date_format=date_format)
    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    def _build_pipeline(full_sales):
        df = full_sales.copy()
        df["week_start"] = df["Fecha"] - pd.to_timedelta(df["Fecha"].dt.dayofweek, unit="d")

        def build_agg(group_cols):
            cols = ["week_start"] + group_cols
            agg_df = (
                df.groupby(cols)
                .agg(
                    units=("Unidades", "sum"),
                    special_units=("Unidades", lambda x: x[
                        df.loc[x.index, "is_special_price"] == True].sum() if "is_special_price" in df.columns else 0),
                    net_revenue=("net_revenue", "sum"),
                    margin=("margin", "sum"),
                )
                .reset_index()
                .sort_values(by=["week_start"] + group_cols)
            )

            agg_df["pct_sold_at_sale"] = np.where(
                agg_df["units"] > 0,
                (agg_df["special_units"] / agg_df["units"]) * 100,
                0.0
            )
            agg_df.drop(columns=["special_units"], inplace=True)

            if group_cols:
                agg_df["first_derivative"] = agg_df.groupby(group_cols)["units"].diff()
                agg_df["second_derivative"] = agg_df.groupby(group_cols)["first_derivative"].diff()
            else:
                agg_df["first_derivative"] = agg_df["units"].diff()
                agg_df["second_derivative"] = agg_df["first_derivative"].diff()

            return agg_df

        return {
            "total": build_agg([]),
            "Categoría": build_agg(["Categoría"]),
            "Subcategoría": build_agg(["Subcategoría"]),
            "Producto": build_agg(["Producto"]),
            "SKU": build_agg(["SKU"]),
            "Drop": build_agg(["Drop"]),
        }

    return {
        "with_special_sales": _build_pipeline(combined_full),
        "without_special_sales": _build_pipeline(norm_full),
    }


# ---------------------------------------------------------
# 7. Influencer Tracking (with dd-mm-yyyy date parsing)
# ---------------------------------------------------------
def compute_influencer_metrics(
        influencer_df: pd.DataFrame,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        date_format: str = '%d-%m-%Y',
):
    """Computes total influencer mentions per SKU for specific weeks and rolling windows."""
    if influencer_df is None or influencer_df.empty:
        return None

    influencer_df = influencer_df.copy()
    date_col = next((c for c in ["Fecha", "date", "created_at"] if c in influencer_df.columns), "Fecha")

    parsed = pd.to_datetime(influencer_df[date_col], format=date_format, errors="coerce")
    if parsed.isna().all() or parsed.isna().mean() > 0.5:
        parsed = pd.to_datetime(influencer_df[date_col], errors="coerce", dayfirst=True)
    influencer_df[date_col] = parsed

    weeks = get_week_boundaries(target_date, find_latest_monday, date_format=date_format)
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
# 8. Purchases Analytics Table (with dd-mm-yyyy date parsing)
# ---------------------------------------------------------
def compute_purchase_metrics(purchases_df: pd.DataFrame, date_format: str = '%d-%m-%Y'):
    """Computes average lead time and delivery variance (actual vs estimated) with dd-mm-yyyy parsing."""
    if purchases_df is None or purchases_df.empty:
        return None

    purchases = purchases_df.copy()

    date_col = next((c for c in ["Fecha", "created_at", "date", "order_date"] if c in purchases.columns), None)
    est_col = next(
        (c for c in ["Fecha llegada estimada", "estimated_delivery_date", "estimated_date"] if c in purchases.columns),
        None)
    act_col = next((c for c in ["Fecha llegada real", "Fecha llegada efectiva", "delivery_date", "actual_date"] if
                    c in purchases.columns), None)

    for col in [date_col, act_col, est_col]:
        if col and col in purchases.columns:
            parsed = pd.to_datetime(purchases[col], format=date_format, errors="coerce")
            if parsed.isna().all() or parsed.isna().mean() > 0.5:
                parsed = pd.to_datetime(purchases[col], errors="coerce", dayfirst=True)
            purchases[col] = parsed

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
# 9. Week-by-Week 8-Week SKU-Level Inventory & Sales Prediction Engine (with Purchases)
# ---------------------------------------------------------
def predict_inventory_status_8_weeks_weekly(
        weekly_sku_df: pd.DataFrame,
        stock_df: pd.DataFrame,
        purchases_df: pd.DataFrame = None,
        prod_df: pd.DataFrame = None,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        date_format: str = '%d-%m-%Y',
):
    """Predicts SKU-level inventory and sales status week-by-week over an 8-week horizon,
    incorporating incoming purchase orders, a 6-week lead time, and calculating:
    - recommended_reorder_date (defaults to target_date if running out with no incoming order or within lead time)
    - recommended_order_units (units required to cover 8 weeks of demand from when the order arrives)
    """
    if weekly_sku_df is None or weekly_sku_df.empty or stock_df is None or stock_df.empty:
        return None

    weeks = get_week_boundaries(target_date, find_latest_monday, date_format=date_format)
    current_end = weeks["current_end"]

    # Parse target_date cleanly as the fallback/comparison reference date
    ref_date = pd.to_datetime(target_date, format=date_format, errors="coerce")
    if pd.isna(ref_date):
        ref_date = pd.to_datetime(target_date, dayfirst=True, errors="coerce")
    if pd.isna(ref_date):
        ref_date = pd.to_datetime(target_date, errors="coerce")

    # Define 8 forecast weeks (Weeks 1 to 8)
    week_ranges = []
    for k in range(1, 9):
        w_start = current_end + pd.Timedelta(days=(k - 1) * 7 + 1)
        w_end = current_end + pd.Timedelta(days=k * 7)
        week_ranges.append((k, w_start, w_end))

    # Process purchases for incoming stock (actual arrival date, fallback to estimated)
    incoming_purchases_per_week = {k: pd.DataFrame(columns=["SKU", "incoming_stock"]) for k in range(1, 9)}
    if purchases_df is not None and not purchases_df.empty:
        p_df = purchases_df.copy()
        sku_col = next((c for c in ["SKU", "product_id"] if c in p_df.columns), "SKU")
        qty_col = next((c for c in ["Unidades", "unidades", "quantity", "qty"] if c in p_df.columns), "Unidades")

        act_date_col = next(
            (c for c in ["Fecha llegada real", "Fecha llegada efectiva", "delivery_date", "actual_date"] if
             c in p_df.columns), None)
        est_date_col = next(
            (c for c in ["Fecha llegada estimada", "estimated_delivery_date", "estimated_date"] if c in p_df.columns),
            None)

        for col in [act_date_col, est_date_col]:
            if col and col in p_df.columns:
                parsed = pd.to_datetime(p_df[col], format=date_format, errors="coerce")
                if parsed.isna().all() or parsed.isna().mean() > 0.5:
                    parsed = pd.to_datetime(p_df[col], errors="coerce", dayfirst=True)
                p_df[col] = parsed

        if act_date_col and est_date_col:
            p_df["effective_arrival_date"] = p_df[act_date_col].fillna(p_df[est_date_col])
        elif act_date_col:
            p_df["effective_arrival_date"] = p_df[act_date_col]
        elif est_date_col:
            p_df["effective_arrival_date"] = p_df[est_date_col]
        else:
            p_df["effective_arrival_date"] = pd.NaT

        p_df = p_df.dropna(subset=["effective_arrival_date"])

        for k, w_start, w_end in week_ranges:
            mask = (p_df["effective_arrival_date"] >= w_start) & (p_df["effective_arrival_date"] <= w_end)
            w_purchases = p_df[mask].groupby(sku_col)[qty_col].sum().reset_index()
            w_purchases.rename(columns={sku_col: "SKU", qty_col: "incoming_stock"}, inplace=True)
            incoming_purchases_per_week[k] = w_purchases

    # Latest week record per SKU
    latest_weeks = (
        weekly_sku_df.sort_values("week_start")
        .groupby("SKU")
        .last()
        .reset_index()
    )

    stock_col = next(
        (c for c in ["Stock disponible (uds)", "ending_stock", "stock"] if c in stock_df.columns),
        "Stock disponible (uds)",
    )
    stock_subset = stock_df[["SKU", stock_col]].copy()
    stock_subset.rename(columns={stock_col: "current_stock"}, inplace=True)

    pred_df = pd.merge(latest_weeks, stock_subset, on="SKU", how="right")
    pred_df["current_stock"] = pred_df["current_stock"].fillna(0)
    pred_df["units"] = pred_df["units"].fillna(0)
    pred_df["first_derivative"] = pred_df["first_derivative"].fillna(0)
    pred_df["second_derivative"] = pred_df["second_derivative"].fillna(0)

    current_stock_tracker = pred_df["current_stock"].copy()
    total_predicted_sales = np.zeros(len(pred_df))
    total_incoming_8w = np.zeros(len(pred_df))
    run_out_skus = set()

    for k, w_start, w_end in week_ranges:
        weekly_sales = (
            pred_df["units"]
            + k * pred_df["first_derivative"]
            + 0.5 * k * (k - 1) * pred_df["second_derivative"]
        )
        weekly_sales = np.maximum(0, weekly_sales)

        pred_df[f"sales_week_{k}"] = weekly_sales
        total_predicted_sales += weekly_sales

        inc_df = incoming_purchases_per_week[k]
        if not inc_df.empty:
            inc_series = pred_df["SKU"].map(inc_df.set_index("SKU")["incoming_stock"]).fillna(0)
        else:
            inc_series = np.zeros(len(pred_df))

        pred_df[f"incoming_week_{k}"] = inc_series
        total_incoming_8w += inc_series

        beginning_stock = current_stock_tracker + inc_series
        ending_stock = beginning_stock - weekly_sales

        run_out_mask = (beginning_stock < weekly_sales) | (ending_stock <= 0)
        run_out_skus.update(pred_df[run_out_mask]["SKU"].tolist())

        current_stock_tracker = np.maximum(0, ending_stock)
        pred_df[f"ending_stock_week_{k}"] = current_stock_tracker

    pred_df["predicted_8w_sales"] = total_predicted_sales
    pred_df["total_incoming_8w"] = total_incoming_8w
    pred_df["projected_ending_stock"] = current_stock_tracker

    # Calculate Recommended Reorder Date & Units to Cover 8 Weeks from Arrival
    lead_time_weeks = 6
    coverage_weeks = 8
    reorder_dates = []
    order_quantities = []

    for idx, row in pred_df.iterrows():
        first_deficit_week = None
        for k in range(1, 9):
            if row[f"ending_stock_week_{k}"] <= 0:
                first_deficit_week = k
                break

        has_incoming_order = row["total_incoming_8w"] > 0

        if first_deficit_week is not None:
            if not has_incoming_order or first_deficit_week <= lead_time_weeks:
                calculated_date = ref_date
                arrival_week = 1 + lead_time_weeks
            else:
                order_week_offset = first_deficit_week - lead_time_weeks
                calculated_date = ref_date + pd.Timedelta(weeks=order_week_offset)
                if calculated_date < ref_date:
                    calculated_date = ref_date
                    arrival_week = 1 + lead_time_weeks
                else:
                    arrival_week = first_deficit_week

            units_needed_8w = 0.0
            for j in range(arrival_week, arrival_week + coverage_weeks):
                proj_week_demand = (
                    row["units"]
                    + j * row["first_derivative"]
                    + 0.5 * j * (j - 1) * row["second_derivative"]
                )
                units_needed_8w += max(0.0, proj_week_demand)

            stock_at_arrival = row[f"ending_stock_week_{arrival_week - 1}"] if arrival_week <= 9 else 0.0
            net_order_qty = max(0.0, units_needed_8w - stock_at_arrival)
        else:
            calculated_date = ref_date + pd.Timedelta(weeks=8)
            net_order_qty = 0.0

        reorder_dates.append(calculated_date)
        order_quantities.append(int(np.ceil(net_order_qty)))

    pred_df["recommended_reorder_date"] = pd.to_datetime(reorder_dates)
    pred_df["recommended_order_units"] = order_quantities

    # Categorizations
    sold_out_df = pred_df[pred_df["SKU"].isin(run_out_skus)].copy()
    not_sold_df = pred_df[
        (pred_df["predicted_8w_sales"] == 0)
        & (pred_df["current_stock"] > 0)
        & (~pred_df["SKU"].isin(run_out_skus))
    ].copy()

    less_than_5 = pred_df[
        (pred_df["predicted_8w_sales"] > 0)
        & (pred_df["predicted_8w_sales"] < 5)
    ].copy()
    less_than_10 = pred_df[
        (pred_df["predicted_8w_sales"] >= 5)
        & (pred_df["predicted_8w_sales"] < 10)
    ].copy()
    less_than_30 = pred_df[
        (pred_df["predicted_8w_sales"] >= 10)
        & (pred_df["predicted_8w_sales"] < 30)
    ].copy()

    if prod_df is not None and not prod_df.empty:
        meta_cols = [c for c in ["SKU", "Producto", "model", "Categoría", "Subcategoría", "Drop", "Sección", "Mercado"]
                     if c in prod_df.columns]
        if meta_cols:
            meta_dedup = prod_df[meta_cols].drop_duplicates("SKU")
            sold_out_df = pd.merge(sold_out_df, meta_dedup, on="SKU", how="left")
            not_sold_df = pd.merge(not_sold_df, meta_dedup, on="SKU", how="left")
            less_than_5 = pd.merge(less_than_5, meta_dedup, on="SKU", how="left")
            less_than_10 = pd.merge(less_than_10, meta_dedup, on="SKU", how="left")
            less_than_30 = pd.merge(less_than_30, meta_dedup, on="SKU", how="left")
            pred_df = pd.merge(pred_df, meta_dedup, on="SKU", how="left")

    return {
        "sold_out": sold_out_df,
        "not_sold_at_all": not_sold_df,
        "sales_less_than_5": less_than_5,
        "sales_less_than_10": less_than_10,
        "sales_less_than_30": less_than_30,
        "full_predictions": pred_df,
    }


def compute_inventory_predictions_for_both(
        weekly_tables: dict,
        stock_df: pd.DataFrame,
        purchases_df: pd.DataFrame = None,
        prod_df: pd.DataFrame = None,
        target_date: str = "09-11-2025",
        find_latest_monday: bool = True,
        date_format: str = '%d-%m-%Y',
):
    """Computes 8-week inventory predictions for both with_special_sales and without_special_sales, incorporating purchases."""
    return {
        "with_special_sales": predict_inventory_status_8_weeks_weekly(
            weekly_sku_df=weekly_tables["with_special_sales"]["SKU"],
            stock_df=stock_df,
            purchases_df=purchases_df,
            prod_df=prod_df,
            target_date=target_date,
            find_latest_monday=find_latest_monday,
            date_format=date_format,
        ),
        "without_special_sales": predict_inventory_status_8_weeks_weekly(
            weekly_sku_df=weekly_tables["without_special_sales"]["SKU"],
            stock_df=stock_df,
            purchases_df=purchases_df,
            prod_df=prod_df,
            target_date=target_date,
            find_latest_monday=find_latest_monday,
            date_format=date_format,
        ),
    }