import pandas as pd


def _validate_essential_columns(purchases):
    """Drops rows missing essential columns and tracks dropped info."""
    essential_cols = ["Pedido proveedor", "SKU", "Proveedor", "Unidades"]
    dropped_info = []

    is_missing_essential = purchases[essential_cols].isna().any(axis=1)
    missing_df = purchases[is_missing_essential]

    for idx, row in missing_df.iterrows():
        missing_fields = [col for col in essential_cols if pd.isna(row[col])]
        dropped_info.append({
            "index": idx,
            "reason": f"Columnas esenciales faltantes: {', '.join(missing_fields)}",
            "data": row.to_dict()
        })

    cleaned_purchases = purchases[~is_missing_essential].copy()
    return cleaned_purchases, dropped_info


def _standardize_and_prepare_dates(purchases):
    """Standardizes date columns to datetime objects and initializes the calculated column."""
    purchases = purchases.copy()
    for date_col in ["Fecha llegada estimada", "Fecha llegada real"]:
        if date_col in purchases.columns:
            purchases[date_col] = pd.to_datetime(purchases[date_col], errors="coerce")

    purchases["calculated"] = 0
    return purchases


def _find_imputed_mode_date(row, purchases):
    """Applies the hierarchical fallback strategy to find a mode date for estimation."""
    sku = row["SKU"]
    prov = row["Proveedor"]

    # Level 1: SKU + Proveedor mode
    match_1 = purchases[
        (purchases["SKU"] == sku) & (purchases["Proveedor"] == prov) & (purchases["Fecha llegada estimada"].notna())]
    if not match_1.empty and not match_1["Fecha llegada estimada"].mode().empty:
        return match_1["Fecha llegada estimada"].mode().iloc[0]

    # Level 2: Proveedor mode
    match_2 = purchases[(purchases["Proveedor"] == prov) & (purchases["Fecha llegada estimada"].notna())]
    if not match_2.empty and not match_2["Fecha llegada estimada"].mode().empty:
        return match_2["Fecha llegada estimada"].mode().iloc[0]

    # Level 3: SKU mode
    match_3 = purchases[(purchases["SKU"] == sku) & (purchases["Fecha llegada estimada"].notna())]
    if not match_3.empty and not match_3["Fecha llegada estimada"].mode().empty:
        return match_3["Fecha llegada estimada"].mode().iloc[0]

    return pd.NaT


def _impute_missing_estimates(purchases):
    """Imputes missing estimated arrival dates using hierarchy and tracks unresolvable rows."""
    purchases = purchases.copy()
    rows_to_drop_indices = []
    dropped_info = []

    missing_est_mask = purchases["Fecha llegada estimada"].isna()

    for idx, row in purchases[missing_est_mask].iterrows():
        imputed_date = _find_imputed_mode_date(row, purchases)

        if pd.notna(imputed_date):
            purchases.loc[idx, "Fecha llegada estimada"] = imputed_date
            purchases.loc[idx, "calculated"] = 1
        else:
            rows_to_drop_indices.append(idx)
            dropped_info.append({
                "index": idx,
                "reason": "Fecha llegada estimada faltante sin historial suficiente para imputar (SKU/Proveedor)",
                "data": row.to_dict()
            })

    if rows_to_drop_indices:
        purchases = purchases.drop(index=rows_to_drop_indices)

    return purchases, dropped_info


def _print_purchases_summary(initial_rows, final_rows, dropped_rows_info):
    """Prints a clear summary report of rows kept and dropped."""
    print("\n" + "=" * 50)
    print("RESUMEN DE CAMBIOS Y ELIMINACIONES - COMPRAS")
    print("=" * 50)
    print(f"Filas iniciales en el dataset: {initial_rows}")
    print(f"Total de filas eliminadas: {len(dropped_rows_info)}")
    print(f"Filas finales procesadas: {final_rows}")
    print("\nDetalle de filas eliminadas:")
    if dropped_rows_info:
        for item in dropped_rows_info:
            print(f"  - Índice {item['index']} | Motivo: {item['reason']}")
            print(f"    Datos disponibles: {item['data']}")
    else:
        print("  - Ninguna fila fue eliminada.")
    print("=" * 50 + "\n")


def clean_purchases(purchases):
    """
    Main orchestrator function that cleans the purchases dataset using modular steps.
    """
    print("Cleaning purchases")
    initial_rows = len(purchases)

    # Step 1: Drop missing essential columns
    purchases, dropped_info_essential = _validate_essential_columns(purchases)

    # Step 2: Standardize date columns & setup flag
    purchases = _standardize_and_prepare_dates(purchases)

    # Step 3: Impute missing estimated dates hierarchically
    purchases, dropped_info_impute = _impute_missing_estimates(purchases)

    # Combine all dropped records for reporting
    all_dropped_info = dropped_info_essential + dropped_info_impute

    # Step 4: Add effective arrival date column (Real if available, else Estimada)
    purchases["Fecha llegada efectiva"] = purchases["Fecha llegada real"].fillna(purchases["Fecha llegada estimada"])

    # Step 5: Print summary report
    _print_purchases_summary(initial_rows, len(purchases), all_dropped_info)

    return purchases