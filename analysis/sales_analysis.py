import numpy as np
import pandas as pd


def prepare_sales_and_products(
        sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        is_special_price: bool = False,
):
    """Merges a sales table (normal or special) with the product table,

    tagging transactions with is_special_price and calculating net_revenue and margin.
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

    # Handle date column mapping
    date_col = (
        "Fecha"
        if "Fecha" in full_df.columns
        else ("date" if "date" in full_df.columns else "created_at")
    )
    full_df["Fecha"] = pd.to_datetime(full_df[date_col])

    return full_df


def get_week_boundaries(
        target_date: str = "2025-11-09", find_latest_monday: bool = True
):
    """Calculates current, previous, and last-year week start/end dates."""
    ref_date = pd.to_datetime(target_date)

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


def compute_week_comparison(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        target_date: str = "2025-11-09",
        find_latest_monday: bool = True,
):
    """Computes units, net revenue, and margin for target week, previous week,

    and last year (actual & month-normalized) for BOTH with sales and without sales.
    """
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True)

    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    def _calculate(full_sales):
        weeks = get_week_boundaries(target_date, find_latest_monday)

        def filter_week(df, start, end):
            return df[(df["Fecha"] >= start) & (df["Fecha"] <= end)]

        cur_sales = filter_week(full_sales, weeks["current_start"], weeks["current_end"])
        prv_sales = filter_week(full_sales, weeks["prev_start"], weeks["prev_end"])
        ly_sales = filter_week(full_sales, weeks["ly_start"], weeks["ly_end"])

        def summarize(df):
            return {
                "Unidades": df["Unidades"].sum(),
                "net_revenue": df["net_revenue"].sum(),
                "margin": df["margin"].sum() if "margin" in df.columns else np.nan,
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


def compute_market_distributions(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        target_date: str = "2025-11-09",
        find_latest_monday: bool = True,
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

    dist_market = cur_sales.groupby("Mercado")[["Unidades", "net_revenue"]].sum().reset_index()
    dist_section = cur_sales.groupby("Sección")[["Unidades", "net_revenue"]].sum().reset_index()
    dist_category = cur_sales.groupby("Categoría")[["Unidades", "net_revenue"]].sum().reset_index()

    special_units = cur_sales[cur_sales["is_special_price"] == True]["Unidades"].sum()
    total_units = cur_sales["Unidades"].sum()
    special_share = (special_units / total_units) if total_units > 0 else 0

    return {
        "by_market": dist_market,
        "by_section": dist_section,
        "by_category": dist_category,
        "special_price_unit_share": special_share,
    }


def compute_model_sell_through(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
        stock_df: pd.DataFrame,
        target_date: str = "2025-11-09",
        find_latest_monday: bool = True,
):
    """Computes top 10 best and worst products/models with inventory sell-through,

    returned for both with sales and without sales.
    """
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True)
    combined_full = pd.concat([norm_full, spec_full], ignore_index=True)

    weeks = get_week_boundaries(target_date, find_latest_monday)

    def _calc_sell_through(full_sales):
        cur_sales = full_sales[
            (full_sales["Fecha"] >= weeks["current_start"])
            & (full_sales["Fecha"] <= weeks["current_end"])
            ]

        model_perf = (
            cur_sales.groupby("Producto")
            .agg(
                total_units=("Unidades", "sum"),
                total_revenue=("net_revenue", "sum"),
                sold_stock=("Unidades", "sum"),
            )
            .reset_index()
        )

        if stock_df is not None and not stock_df.empty:
            stock_with_prod = pd.merge(stock_df, prod_df[["SKU", "Producto"]], on="SKU", how="left")
            stock_agg = stock_with_prod.groupby("Producto")["Stock disponible (uds)"].sum().reset_index()

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


def compute_weekly_aggregations_with_derivatives(
        normal_sales_df: pd.DataFrame,
        special_sales_df: pd.DataFrame,
        prod_df: pd.DataFrame,
):
    """Builds granular weekly tables (Total, Category, Sub-Category, Product, Drop)

    with 1st and 2nd derivatives, returning dictionaries for both with sales and without sales.
    """
    norm_full = prepare_sales_and_products(normal_sales_df, prod_df, is_special_price=False)
    spec_full = prepare_sales_and_products(special_sales_df, prod_df, is_special_price=True)
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
                    net_revenue=("net_revenue", "sum"),
                    margin=("margin", "sum"),
                )
                .reset_index()
                .sort_values(by=["week_start"] + group_cols)
            )

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


def compute_influencer_metrics(
        influencer_df: pd.DataFrame,
        target_date: str = "2025-11-09",
        find_latest_monday: bool = True,
):
    """Computes total influencer mentions per SKU for specific weeks

    and rolling windows (1-5 weeks).
    """
    if influencer_df is None or influencer_df.empty:
        return None

    influencer_df = influencer_df.copy()
    influencer_df["Fecha"] = pd.to_datetime(influencer_df["Fecha"])
    weeks = get_week_boundaries(target_date, find_latest_monday)
    ref_end = weeks["current_end"]

    influencer_df["week_start"] = influencer_df["Fecha"] - pd.to_timedelta(
        influencer_df["Fecha"].dt.dayofweek, unit="d"
    )

    inf_specific = (
        influencer_df.groupby(["SKU", "week_start"])
        .size()
        .reset_index(name="influencer_mentions_specific_week")
    )

    rolling_results = []
    for w in range(1, 6):
        window_start = ref_end - pd.Timedelta(weeks=w) + pd.Timedelta(days=1)
        mask = (influencer_df["Fecha"] >= window_start) & (influencer_df["Fecha"] <= ref_end)
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


def compute_purchase_metrics(purchases_df: pd.DataFrame):
    """Computes average lead time and delivery variance (actual vs estimated)

    checking flexible procurement date column naming variants.
    """
    if purchases_df is None or purchases_df.empty:
        return None

    purchases = purchases_df.copy()

    date_col = next(
        (c for c in ["Fecha", "created_at", "date", "order_date"] if c in purchases.columns),
        None,
    )
    est_col = next(
        (c for c in ["estimated_delivery_date", "estimated_date", "fecha_estimada"] if c in purchases.columns),
        None,
    )
    act_col = next(
        (c for c in ["delivery_date", "actual_date", "Fecha_entrega"] if c in purchases.columns),
        None,
    )

    if date_col:
        purchases[date_col] = pd.to_datetime(purchases[date_col])
    if act_col:
        purchases[act_col] = pd.to_datetime(purchases[act_col])
    if est_col:
        purchases[est_col] = pd.to_datetime(purchases[est_col])

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