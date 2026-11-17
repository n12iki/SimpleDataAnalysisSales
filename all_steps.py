from cleaning.data_cleaning import clean_xcel
from analysis.sales_analysis import (
    compute_week_comparison,
    compute_market_distributions,
    compute_model_sell_through,
    compute_weekly_aggregations_with_derivatives,
    compute_influencer_metrics,
    compute_purchase_metrics,
)
import pandas as pd
import sys

def main(path):
    sales, influencers, sales_non, sales_sale, purchases, stocks, prod = clean_xcel(path)
    #sales.to_csv('./data/sales.csv', index=False)
    #influencers.to_csv('./data/influencers.csv', index=False)
    #sales_non.to_csv('./data/sales_non.csv', index=False)
    #sales_sale.to_csv('./data/sales_sale.csv', index=False)
    #purchases.to_csv('./data/purchases.csv', index=False)
    #stocks.to_csv('./data/stocks.csv', index=False)
    #prod.to_csv('./data/prod.csv', index=False)

    target_date = "2025-11-09"
    find_latest_monday = True

    # 1. Week Comparison (With & Without Special Sales)
    print("Computing week comparisons (with & without sales)...")
    week_comparison = compute_week_comparison(
        sales_non, sales_sale, prod, target_date, find_latest_monday
    )
    print("Week Comparison (With Special Sales):", week_comparison["with_special_sales"])
    print("Week Comparison (Without Special Sales):", week_comparison["without_special_sales"])

    # 2. Distributions & Special Price Share
    print("Computing market/section/category distributions...")
    distributions = compute_market_distributions(
        sales_non, sales_sale, prod, target_date, find_latest_monday
    )
    print("Special Price Unit Share:", distributions["special_price_unit_share"])

    # 3. Top 10 Best/Worst Models & Sell-Through (With & Without Special Sales)
    print("Computing model sell-through performance...")
    models_perf = compute_model_sell_through(
        sales_non, sales_sale, prod, stocks, target_date, find_latest_monday
    )
    print("Top Best Model Sample (With Sales):\n", models_perf["with_special_sales"]["top_10_best"].head(2))
    print("Top Best Model Sample (Without Sales):\n", models_perf["without_special_sales"]["top_10_best"].head(2))

    # 4. Granular Weekly Tables & Derivatives (With & Without Special Sales)
    print("Building granular weekly tables and derivatives...")
    weekly_tables = compute_weekly_aggregations_with_derivatives(
        sales_non, sales_sale, prod
    )
    print("Weekly Total Shape (With Sales):", weekly_tables["with_special_sales"]["total"].shape)
    print("Weekly Total Shape (Without Sales):", weekly_tables["without_special_sales"]["total"].shape)

    # 5. Influencer Metrics
    print("Computing influencer tracking metrics...")
    influencer_metrics = compute_influencer_metrics(
        influencers, target_date, find_latest_monday
    )
    if influencer_metrics:
        print("Influencer Specific Weekly Shape:", influencer_metrics["specific_weekly"].shape)

    # 6. Purchase Metrics
    print("Computing purchase lead times and delivery variance...")
    purchases_metrics = compute_purchase_metrics(purchases)
    if purchases_metrics is not None:
        print("Purchases Summary Sample:\n", purchases_metrics.head(2))

    print("Pipeline execution completed successfully!")

if __name__ == "__main__":
    main(sys.argv[1:])




