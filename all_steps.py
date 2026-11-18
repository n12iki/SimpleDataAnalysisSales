import sys
from cleaning.data_cleaning import clean_xcel
from analysis.sales_analysis import (
    compute_week_comparison,
    compute_market_distributions,
    compute_model_sell_through,
    compute_weekly_aggregations_with_derivatives,
    compute_influencer_metrics,
    compute_purchase_metrics,
    compute_inventory_predictions_for_both,
)


def main(path):
    sales, influencers, sales_non, sales_sale, purchases, stocks, prod = clean_xcel(path)

    target_date = "09-11-2025"
    find_latest_monday = True

    # 1. Week Comparison (With & Without Special Sales)
    print("Computing week comparisons...")
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

    # 3. Top 10 Best/Worst Models & Sell-Through
    print("Computing model sell-through performance...")
    models_perf = compute_model_sell_through(
        sales_non, sales_sale, prod, stocks, target_date, find_latest_monday
    )
    print("Top Best Model Sample (With Sales):\n", models_perf["with_special_sales"]["top_10_best"].head(2))

    # 4. Granular Weekly Tables & Derivatives
    print("Building granular weekly tables and derivatives...")
    weekly_tables = compute_weekly_aggregations_with_derivatives(
        sales_non, sales_sale, prod
    )

    # 5. Week-by-Week 8-Week Inventory & Sales Predictions (With & Without Special Sales)
    print("Computing week-by-week 8-week inventory predictions...")
    prediction_inventory = compute_inventory_predictions_for_both(
        weekly_tables=weekly_tables,
        stock_df=stocks,
        purchases_df=purchases,
        prod_df=prod,
        target_date=target_date,
        find_latest_monday=find_latest_monday,
    )

    print("Sold Out Products Count (With Sales):", len(prediction_inventory["with_special_sales"]["sold_out"]))
    print("Sold Out Products Count (Without Sales):", len(prediction_inventory["without_special_sales"]["sold_out"]))

    # 6. Influencer Metrics
    print("Computing influencer tracking metrics...")
    influencer_metrics = compute_influencer_metrics(
        influencers, target_date, find_latest_monday
    )
    if influencer_metrics:
        print("Influencer Specific Weekly Shape:", influencer_metrics["specific_weekly"].shape)

    # 7. Purchase Metrics
    print("Computing purchase lead times and delivery variance...")
    purchases_metrics = compute_purchase_metrics(purchases)
    if purchases_metrics is not None:
        print("Purchases Summary Sample:\n", purchases_metrics.head(2))

    print("Pipeline execution completed successfully!")


if __name__ == "__main__":
    main(sys.argv[1:])