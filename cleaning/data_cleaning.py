import pandas as pd
import sys

import cleaning.sales_clean as sales_p
import cleaning.product_clean as pro_p
import cleaning.stock_clean as stock_p
import cleaning.purchase_clean as pur_p


def read_xcel(path):
    # Load all sheets
    sheets = pd.read_excel(path, sheet_name=None)
    # Access each sheet
    sales = sheets["VENTAS"]
    prod = sheets["PRODUCTO"]
    stocks = sheets["STOCK"]
    purchases = sheets["COMPRAS"]
    return sales, prod, stocks, purchases

def merge_prod_sales(sales, prod):
    merged_outer = pd.merge(sales, prod, on="SKU", how="outer")
    return merged_outer

def clean_pandas(sales, prod, stocks, purchases):
    merged = merge_prod_sales(sales, prod)
    prod = pro_p.clean_prod(prod, merged)
    sales, influencers, sales_non, sales_sale = sales_p.clean_sales(sales, prod)
    stocks = stock_p.clean_stocks(stocks)
    purchases = pur_p.clean_purchases(purchases)
    return sales, influencers, sales_non, sales_sale, purchases, stocks, prod

def clean_xcel(path):
    path = "C:/Users/Dome/Downloads/EME_Caso_Practico_Datos_1.xlsx"
    sales, prod, stocks, purchases = read_xcel(path)
    return clean_pandas(sales, prod, stocks, purchases)

if __name__ == "__main__":
    clean_xcel(sys.argv[1:])

