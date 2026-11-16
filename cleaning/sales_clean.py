import pandas as pd


def clean_sales(sales, prod,
                accepted_countries: list[str] = ["DE", "ES", "FR", "IT", "NL", "PT", "US"],
                default_country: str = "ES"):
    """Orchestrates the cleaning pipeline and generates a comprehensive summary report."""
    print("🚀 Starting sales cleaning pipeline...\n")

    # Initialize a dictionary to track metrics and changes across steps
    summary_report = {
        "initial_rows": len(sales),
        "dropped_missing_essentials": 0,
        "imputed_units": 0,
        "missing_markets_filled": 0,
        "price_mismatches_found": 0,
        "prices_updated": 0,
        "markets_corrected": {}
    }

    sales, summary_report = clean_basic_fields(sales, default_country=default_country, summary=summary_report)
    sales, summary_report = clean_pvp_prices(sales, prod, summary=summary_report)
    sales, summary_report = clean_countries(sales, accepted_countries=accepted_countries,
                                            default_country=default_country, summary=summary_report)

    # Segment datasets
    influencers = sales[sales["Etiquetas"].str.contains("influencers", na=False)].copy()
    sales_non = sales[sales["Etiquetas"].isna()].copy()
    sales_sale = sales[
        sales["Etiquetas"].notna()
        & (~sales["Etiquetas"].str.contains("influencers", na=False))
        ].copy()

    summary_report["final_rows"] = len(sales)
    summary_report["influencers_rows"] = len(influencers)
    summary_report["sales_non_rows"] = len(sales_non)
    summary_report["sales_sale_rows"] = len(sales_sale)

    # Print Final Consolidated Summary
    print("\n" + "=" * 50)
    print("📊 RESUMEN GENERAL DEL PROCESO DE LIMPIEZA")
    print("=" * 50)
    print(f"• Filas iniciales en bruto: {summary_report['initial_rows']}")
    print(f"• Filas eliminadas (faltaba Fecha o Pedido): {summary_report['dropped_missing_essentials']}")
    print(f"• Unidades imputadas por moda (SKU/Global): {summary_report['imputed_units']}")
    print(
        f"• Mercados faltantes (NaN) rellenados con '{default_country}': {summary_report['missing_markets_filled']} filas")
    print(
        f"• Discrepancias de PVP gestionadas: {summary_report['price_mismatches_found']} (Actualizadas: {summary_report['prices_updated']})")

    if summary_report["markets_corrected"]:
        print("• Corrección de mercados inválidos:")
        for inv, data in summary_report["markets_corrected"].items():
            print(f"    - '{inv}' -> '{data['replacement']}' ({data['rows_affected']} filas afectadas)")
    else:
        print("• Corrección de mercados inválidos: Ninguno (todos eran válidos)")

    print(f"\n• Filas finales procesadas: {summary_report['final_rows']}")
    print(f"    - Ventas estándar ('sales_sale'): {summary_report['sales_sale_rows']}")
    print(f"    - Influencers ('influencers'): {summary_report['influencers_rows']}")
    print(f"    - Sin etiqueta ('sales_non'): {summary_report['sales_non_rows']}")
    print("=" * 50 + "\n")

    return sales, influencers, sales_non, sales_sale


def clean_basic_fields(sales, default_country: str = "ES", summary: dict = None):
    """Standardizes basic fields, fills missing markets/units, and drops rows missing essential data."""
    sales = sales.copy()

    # 1. Handle missing Mercado (NaN values)
    missing_mercado_count = sales["Mercado"].isna().sum()
    sales["Mercado"] = sales["Mercado"].fillna(default_country).astype(str).str.upper().str.strip()
    if summary is not None:
        summary["missing_markets_filled"] += missing_mercado_count

    # 2. Track rows dropped due to missing Fecha or Pedido
    initial_count = len(sales)
    sales = sales.dropna(subset=["Fecha", "Pedido"])
    dropped_count = initial_count - len(sales)
    if summary is not None:
        summary["dropped_missing_essentials"] += dropped_count

    # 3. Handle Units cleaning & imputation
    sales["Unidades"] = pd.to_numeric(sales["Unidades"], errors="coerce")
    missing_units_count = sales["Unidades"].isna().sum()

    sku_modes = sales.groupby("SKU")["Unidades"].agg(
        lambda x: x.mode().iloc[0] if not x.mode().empty else 1
    )
    global_mode = int(sales["Unidades"].mode().iloc[0]) if not sales["Unidades"].mode().empty else 1
    fallback_value = sku_modes.fillna(global_mode)

    sales["Unidades"] = sales["Unidades"].fillna(sales["SKU"].map(fallback_value)).fillna(1).astype(int)
    if summary is not None:
        summary["imputed_units"] += missing_units_count

    print(
        f"[Basic Fields] Filas eliminadas por Fecha/Pedido nulos: {dropped_count} | Mercados NaN rellenados: {missing_mercado_count} | Unidades imputadas: {missing_units_count}.")
    return sales, summary


def clean_countries(sales, accepted_countries: list[str] = ["DE", "ES", "FR", "IT", "NL", "PT", "US"],
                    default_country: str = "ES", summary: dict = None):
    """Detects invalid markets, prompts for corrections, tracks affected rows, and prints a summary."""
    sales = sales.copy()

    # Ensure accepted countries are uppercase for robust comparison
    accepted_countries = [c.upper() for c in accepted_countries]

    # Find markets that are not in the accepted list
    invalid_markets = set(sales[~sales["Mercado"].isin(accepted_countries)]["Mercado"])
    market_fixes = {}

    for invalid_market in invalid_markets:
        # Count how many rows have this invalid market before replacing
        rows_affected = (sales["Mercado"] == invalid_market).sum()

        fix_value = input(
            f"Mercado inválido '{invalid_market}' ({rows_affected} filas). Cambiar a [{default_country}]: ").strip()
        replacement = (fix_value or default_country).upper()

        sales.loc[sales["Mercado"] == invalid_market, "Mercado"] = replacement
        market_fixes[invalid_market] = {
            "replacement": replacement,
            "rows_affected": rows_affected
        }

    if summary is not None:
        summary["markets_corrected"].update(market_fixes)

    # Summary for Country step
    print("\n" + "=" * 40)
    print("RESUMEN DE MERCADOS / PAÍSES")
    print("=" * 40)
    if market_fixes:
        print(f"Total de mercados inválidos detectados: {len(market_fixes)}")
        for inv, data in market_fixes.items():
            print(f"  - '{inv}' -> cambiado a '{data['replacement']}' ({data['rows_affected']} filas)")
    else:
        print("  - Todos los mercados son válidos.")
    print("=" * 40 + "\n")

    return sales, summary


def clean_pvp_prices(sales, prod,
                     price_col_sales="PVP unitario (€)",
                     price_col_prod="PVP (€)",
                     summary: dict = None):
    """Cross-references unit prices with product master, handles mismatches, and prints a summary."""
    sales = sales.copy()
    prod = prod.copy()

    total_mismatches = 0
    prices_updated = 0
    mismatches_per_sku = {}

    prod_pvp_map = prod.set_index("SKU")[price_col_prod].to_dict()
    sales["Prod_PVP"] = sales["SKU"].map(prod_pvp_map)
    sales[price_col_sales] = pd.to_numeric(sales[price_col_sales], errors="coerce")
    sales["Prod_PVP"] = pd.to_numeric(sales["Prod_PVP"], errors="coerce")

    mismatch_mask = (
            sales[price_col_sales].notna() &
            sales["Prod_PVP"].notna() &
            (abs(sales[price_col_sales] - sales["Prod_PVP"]) > 0.01)
    )

    mismatch_indices = sales[mismatch_mask].index

    if len(mismatch_indices) > 0:
        print(
            f"\n-> Se encontraron {len(mismatch_indices)} discrepancia(s) de precios entre ventas y el maestro de productos.")

    for idx in mismatch_indices:
        row = sales.loc[idx]
        sku = row["SKU"]
        fecha = pd.to_datetime(row["Fecha"]).strftime("%Y-%m-%d") if pd.notna(row["Fecha"]) else "Fecha desconocida"
        sales_price = row[price_col_sales]
        prod_price = row["Prod_PVP"]

        total_mismatches += 1
        mismatches_per_sku[sku] = mismatches_per_sku.get(sku, 0) + 1

        print(f"\n[Mismatch] SKU: {sku} | Fecha: {fecha}")
        print(f"  - Precio en Ventas ({price_col_sales}): {sales_price}")
        print(f"  - PVP Maestro de Productos: {prod_price}")

        choice = input(
            f"  ¿Qué precio deseas usar? ([1] Mantener Ventas: {sales_price} / [2] Usar Producto: {prod_price}): "
        ).strip()

        if choice == "2":
            sales.loc[idx, price_col_sales] = prod_price
            prices_updated += 1
            print(f"  -> Actualizado al precio de Producto: {prod_price}")
        else:
            print(f"  -> Se mantiene el precio de Ventas: {sales_price}")

    sales = sales.drop(columns=["Prod_PVP"], errors="ignore")

    if summary is not None:
        summary["price_mismatches_found"] += total_mismatches
        summary["prices_updated"] += prices_updated

    print("\n" + "=" * 40)
    print("RESUMEN DE DISCREPANCIAS DE PRECIOS (PVP)")
    print("=" * 40)
    print(f"Total de discrepancias encontradas: {total_mismatches}")
    print(f"Precios actualizados al maestro: {prices_updated}")
    print(f"Precios mantenidos: {total_mismatches - prices_updated}")

    if mismatches_per_sku:
        print("Discrepancias por SKU:")
        for sku, count in mismatches_per_sku.items():
            print(f"  - SKU {sku}: {count} vez/veces")
    else:
        print("  - Ninguna discrepancia por SKU.")
    print("=" * 40 + "\n")

    return sales, summary