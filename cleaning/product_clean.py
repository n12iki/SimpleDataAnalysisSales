import pandas as pd


def _prepare_product_data(prod, merged_outer, price_col):
    """Prepares copies and standardizes date and numeric columns for analysis."""
    prod = prod.copy()
    df = merged_outer.copy()

    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df["Unidades"] = pd.to_numeric(df["Unidades"], errors="coerce")

    # Handle column naming if both sales and prod had a 'PVP' column
    pvp_sales_col = "PVP_x" if "PVP_x" in df.columns else price_col

    missing_mask = prod[price_col].isna()
    missing_skus = prod.loc[missing_mask, "SKU"].tolist()

    return prod, df, missing_mask, missing_skus, pvp_sales_col


def _get_window_unit_prices(sku_sales, pvp_sales_col):
    """Extracts or calculates unit prices within a specific transaction window."""
    if "PVP unitario" in sku_sales.columns and sku_sales["PVP unitario"].notna().any():
        return pd.to_numeric(sku_sales["PVP unitario"], errors="coerce").dropna()
    else:
        valid_rows = sku_sales.dropna(subset=[pvp_sales_col, "Unidades"])
        if valid_rows.empty:
            return pd.Series(dtype=float)
        return pd.to_numeric(valid_rows[pvp_sales_col], errors="coerce") / valid_rows["Unidades"]


def _process_missing_sku_prices(prod, df, missing_mask, pvp_sales_col, price_col):
    """Iterates through missing SKUs, calculates 1-month window prices, and updates rows."""
    fixed_records = []
    no_sales_skus = []
    unresolved_skus = []

    for idx, row in prod[missing_mask].iterrows():
        sku = row["SKU"]

        # Filter merged sales data for this SKU with valid dates and units > 0
        sku_sales = df[
            (df["SKU"] == sku) &
            (df["Fecha"].notna()) &
            (df["Unidades"] > 0)
            ].copy()

        if sku_sales.empty:
            no_sales_skus.append(sku)
            continue

        # 1. Find the most recent date for this SKU and 1 month prior
        most_recent_date = sku_sales["Fecha"].max()
        one_month_before = most_recent_date - pd.DateOffset(months=1)

        # 2. Filter transactions within the 1-month window leading up to the most recent date
        recent_window = sku_sales[
            (sku_sales["Fecha"] >= one_month_before) &
            (sku_sales["Fecha"] <= most_recent_date)
            ].copy()

        # 3. Calculate unit prices
        unit_prices = _get_window_unit_prices(recent_window, pvp_sales_col)

        # 4. Fill missing PVP using the median unit price
        if not unit_prices.empty:
            fixed_value = round(unit_prices.median(), 2)
            prod.loc[idx, price_col] = fixed_value
            fixed_records.append({
                "SKU": sku,
                "value": fixed_value,
                "window": f"{one_month_before.strftime('%Y-%m-%d')} to {most_recent_date.strftime('%Y-%m-%d')}"
            })
        else:
            unresolved_skus.append(sku)

    return prod, fixed_records, no_sales_skus, unresolved_skus


def _print_product_summary(initial_missing_count, fixed_records, no_sales_skus, unresolved_skus):
    """Prints a clear summary report of the product price imputation results."""
    print("\n" + "=" * 50)
    print("📊 RESUMEN DE CAMBIOS - PRODUCTOS (PVP FALTANTE)")
    print("=" * 50)
    print(f"Total de SKUs con PVP faltante inicialmente: {initial_missing_count}")
    print(f"SKUs reparados con éxito: {len(fixed_records)}")
    print(f"SKUs sin historial de ventas: {len(no_sales_skus)}")
    print(f"SKUs con ventas pero sin precios válidos en la ventana: {len(unresolved_skus)}")

    if fixed_records:
        print("\nDetalle de SKUs reparados:")
        for item in fixed_records:
            print(f"  - SKU {item['SKU']} -> PVP asignado: {item['value']} (Ventana: {item['window']})")
    if no_sales_skus:
        print(f"\nSKUs sin historial de ventas (PVP permanece NaN): {no_sales_skus}")
    if unresolved_skus:
        print(f"\nSKUs sin precios válidos en el periodo: {unresolved_skus}")
    print("=" * 50 + "\n")


def clean_prod(prod, merged_outer, price_col="PVP (€)"):
    """
    Main orchestrator function that cleans product prices using modular sub-steps.
    """
    print("Cleaning products")
    prod, df, missing_mask, missing_skus, pvp_sales_col = _prepare_product_data(prod, merged_outer, price_col)

    print(f"-> Found {len(missing_skus)} product row(s) with missing PVP.")
    if missing_skus:
        print(f"-> Missing SKUs: {missing_skus}")
        print("-> Fixing missing PVPs based on sales history:")

    prod, fixed_records, no_sales_skus, unresolved_skus = _process_missing_sku_prices(
        prod, df, missing_mask, pvp_sales_col, price_col
    )

    _print_product_summary(len(missing_skus), fixed_records, no_sales_skus, unresolved_skus)

    return prod