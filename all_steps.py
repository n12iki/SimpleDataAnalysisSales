from cleaning.data_cleaning import clean_xcel
import pandas as pd
import sys

def main(path):
    sales, influencers, sales_non, sales_sale, purchases, stocks, prod = clean_xcel(path)
    sales.to_csv('./data/sales.csv', index=False)
    influencers.to_csv('./data/influencers.csv', index=False)
    sales_non.to_csv('./data/sales_non.csv', index=False)
    sales_sale.to_csv('./data/sales_sale.csv', index=False)
    purchases.to_csv('./data/purchases.csv', index=False)
    stocks.to_csv('./data/stocks.csv', index=False)
    prod.to_csv('./data/prod.csv', index=False)

if __name__ == "__main__":
    main(sys.argv[1:])




