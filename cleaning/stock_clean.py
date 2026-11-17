import pandas as pd


def clean_stocks(stocks):
    print("Cleaning stocks")
    stocks = stocks.copy()

    initial_rows = len(stocks)

    # 1. Track and drop rows where essential columns ('SKU' or 'Fecha stock') are missing
    stocks = stocks.dropna(subset=["SKU", "Fecha stock"])
    rows_dropped_due_to_nulls = initial_rows - len(stocks)

    # 2. Track missing available stock values before filling with 0
    missing_stock_mask = stocks["Stock disponible (uds)"].isna()
    missing_stock_count = missing_stock_mask.sum()

    # Fill missing stock values with 0
    stocks["Stock disponible (uds)"] = stocks["Stock disponible (uds)"].fillna(0)

    # Ensure stock count is numeric and formatted as an integer (if applicable)
    stocks["Stock disponible (uds)"] = pd.to_numeric(stocks["Stock disponible (uds)"], errors="coerce").fillna(
        0).astype(int)

    # --- PRINT SUMMARY OF CHANGES ---
    print("\n" + "=" * 40)
    print("RESUMEN DE CAMBIOS - STOCK")
    print("=" * 40)
    print(f"Filas iniciales en el dataset: {initial_rows}")
    print(f"Filas eliminadas (SKU o Fecha stock vacíos): {rows_dropped_due_to_nulls}")
    print(f"Valores de stock nulos rellenados con 0: {missing_stock_count}")
    print(f"Filas finales procesadas: {len(stocks)}")
    print("=" * 40 + "\n")

    return stocks