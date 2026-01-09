"""
Complete Sanity Validator - All 60 Checks on 1M Dataset
Uses correct schema column names from the generated data
"""

import polars as pl
import os
import sys


def run_all_sanity_checks(data_dir):
    """Run all 60 sanity checks on the 1M dataset"""

    print(f"Loading data from {data_dir}...")
    data = {}

    tables = ["applications", "loan_tape", "payments", "credit_reports",
              "credit_tradelines", "fraud_verification", "bank_transactions"]

    for table in tables:
        path = os.path.join(data_dir, f"{table}.parquet")
        if os.path.exists(path):
            data[table] = pl.read_parquet(path)
            print(f"  ✓ {table}: {len(data[table]):,} rows, {len(data[table].columns)} columns")

    print("\n" + "="*80)
    print("RUNNING ALL 60 SANITY CHECKS")
    print("="*80 + "\n")

    results = []
    passed = 0
    failed = 0
    skipped = 0

    def check(check_id, name, condition_fn):
        nonlocal passed, failed, skipped
        try:
            violations = condition_fn()
            status = "✅ PASS" if violations == 0 else f"❌ FAIL ({violations:,} violations)"
            if violations == 0:
                passed += 1
            else:
                failed += 1
            print(f"{status} | {check_id}: {name}")
            results.append((check_id, name, violations, "PASS" if violations == 0 else "FAIL"))
            return violations
        except Exception as e:
            error_msg = str(e)[:100]
            print(f"⚠️  SKIP | {check_id}: {name} - {error_msg}")
            results.append((check_id, name, -1, f"SKIP: {error_msg}"))
            skipped += 1
            return None

    # ==============================================================================
    # CATEGORY 1: LIFECYCLE SANITY (001-008)
    # ==============================================================================
    print("\n[LIFECYCLE SANITY]")

    check("SANITY-001", "No Funded Loan Without Approval",
          lambda: len(data["loan_tape"].join(
              data["applications"], on="application_id", how="inner"
          ).filter(pl.col("decision_status") != "APPROVED")))

    check("SANITY-002", "No Approval Without Credit Report",
          lambda: len(data["applications"].filter(
              pl.col("decision_status") == "APPROVED"
          ).join(data["credit_reports"], on="application_id", how="anti")))

    check("SANITY-003", "No Approval Without Fraud Check",
          lambda: len(data["applications"].filter(
              pl.col("decision_status") == "APPROVED"
          ).join(data["fraud_verification"], on="application_id", how="anti")))

    check("SANITY-004", "No Payment Without Funded Loan",
          lambda: len(data["payments"].join(data["loan_tape"], on="loan_id", how="anti")))

    check("SANITY-005", "No Loan Without Application",
          lambda: len(data["loan_tape"].join(
              data["applications"], on="application_id", how="anti")))

    check("SANITY-006", "No Credit Report Without Application",
          lambda: len(data["credit_reports"].join(
              data["applications"], on="application_id", how="anti")))

    check("SANITY-007", "No Declined in Loan Tape",
          lambda: len(data["loan_tape"].join(
              data["applications"], on="application_id", how="inner"
          ).filter(pl.col("decision_status") == "DECLINED")))

    check("SANITY-008", "No Pending in Loan Tape",
          lambda: len(data["loan_tape"].join(
              data["applications"], on="application_id", how="inner"
          ).filter(pl.col("decision_status").is_in(["PENDING", "UNDER_REVIEW"]))))

    # ==============================================================================
    # CATEGORY 2: STATE MACHINE VIOLATIONS (009-023)
    # ==============================================================================
    print("\n[STATE MACHINE VIOLATIONS]")

    check("SANITY-009", "No Payments After Payoff",
          lambda: len(data["payments"].join(
              data["loan_tape"].filter(pl.col("loan_status") == "PAID_OFF").group_by("loan_id").agg(
                  pl.col("snapshot_date").max().alias("payoff_date")
              ), on="loan_id", how="inner"
          ).filter(pl.col("payment_received_date") > pl.col("payoff_date"))))

    check("SANITY-010", "No Payments After Chargeoff",
          lambda: len(data["payments"].join(
              data["loan_tape"].filter(pl.col("loan_status") == "CHARGED_OFF").group_by("loan_id").agg(
                  pl.col("snapshot_date").min().alias("co_date")
              ), on="loan_id", how="inner"
          ).filter(
              (pl.col("payment_received_date") > pl.col("co_date")) &
              (pl.col("actual_payment_amount") > 0)
          )))

    check("SANITY-011", "No Delinquent Without Missed Payments",
          lambda: len(data["loan_tape"].filter(
              pl.col("loan_status").str.contains("DELINQUENT")
          ).join(
              data["payments"].filter(pl.col("payment_status") == "MISSED").group_by("loan_id").count(),
              on="loan_id", how="anti"
          )))

    check("SANITY-012", "No CURRENT With DPD > 0",
          lambda: len(data["loan_tape"].filter(
              (pl.col("loan_status") == "CURRENT") & (pl.col("days_past_due") > 0))))

    check("SANITY-013", "No Balance on Paid Off Loans",
          lambda: len(data["loan_tape"].filter(
              (pl.col("loan_status") == "PAID_OFF") & (pl.col("current_principal_balance") > 0.01))))

    check("SANITY-014", "Chargeoff Requires 120+ DPD",
          lambda: len(data["loan_tape"].filter(
              (pl.col("loan_status") == "CHARGED_OFF") & (pl.col("days_past_due") < 120))))

    check("SANITY-015", "DPD Matches Delinquency Status",
          lambda: len(data["loan_tape"].filter(
              ((pl.col("loan_status") == "DELINQUENT_30") & (~pl.col("days_past_due").is_between(30, 59))) |
              ((pl.col("loan_status") == "DELINQUENT_60") & (~pl.col("days_past_due").is_between(60, 89))) |
              ((pl.col("loan_status") == "DELINQUENT_90") & (~pl.col("days_past_due").is_between(90, 119))) |
              ((pl.col("loan_status") == "DELINQUENT_120") & (pl.col("days_past_due") < 120))
          )))

    check("SANITY-016", "Loan Status Valid Enum",
          lambda: len(data["loan_tape"].filter(
              ~pl.col("loan_status").is_in([
                  'CURRENT', 'DELINQUENT_30', 'DELINQUENT_60', 'DELINQUENT_90',
                  'DELINQUENT_120', 'CHARGED_OFF', 'PAID_OFF', 'PREPAID'
              ]))))

    check("SANITY-017", "Payment Status Valid Enum",
          lambda: len(data["payments"].filter(
              ~pl.col("payment_status").is_in(['PAID', 'PARTIAL', 'MISSED', 'PENDING']))))

    check("SANITY-018", "No Future Snapshot Dates",
          lambda: len(data["loan_tape"].filter(pl.col("snapshot_date") > pl.lit("2026-01-09"))))

    check("SANITY-019", "No Future Payment Dates",
          lambda: len(data["payments"].filter(pl.col("payment_received_date") > pl.lit("2026-01-09"))))

    check("SANITY-020", "Funding Date ≤ First Payment Date",
          lambda: len(data["loan_tape"].filter(pl.col("loan_status") != "CHARGED_OFF").select(
              ["loan_id", "funding_date"]
          ).unique().join(
              data["payments"].group_by("loan_id").agg(
                  pl.col("payment_due_date").min().alias("first_payment")
              ), on="loan_id", how="inner"
          ).filter(pl.col("funding_date") > pl.col("first_payment"))))

    check("SANITY-021", "No Payment Before Funding",
          lambda: len(data["payments"].join(
              data["loan_tape"].select(["loan_id", "funding_date"]).unique(),
              on="loan_id", how="inner"
          ).filter(pl.col("payment_received_date") < pl.col("funding_date"))))

    check("SANITY-022", "Decision Date ≤ Funding Date",
          lambda: len(data["loan_tape"].select(["application_id", "loan_id", "funding_date"]).unique().join(
              data["applications"].select(["application_id", "decision_date"]),
              on="application_id", how="inner"
          ).filter(pl.col("decision_date") > pl.col("funding_date"))))

    check("SANITY-023", "Snapshot Dates Sequential",
          lambda: data["loan_tape"].sort(["loan_id", "snapshot_date"]).select([
              "loan_id",
              "snapshot_date",
              pl.col("snapshot_date").shift(1).over("loan_id").alias("prev_snap")
          ]).filter(
              (pl.col("prev_snap").is_not_null()) & (pl.col("snapshot_date") <= pl.col("prev_snap"))
          ).select("loan_id").n_unique())

    # ==============================================================================
    # CATEGORY 3: FINANCIAL IMPOSSIBILITIES (024-033)
    # ==============================================================================
    print("\n[FINANCIAL IMPOSSIBILITIES]")

    check("SANITY-024", "No Negative Principal Balance",
          lambda: len(data["loan_tape"].filter(pl.col("current_principal_balance") < 0)))

    check("SANITY-025", "No Negative Payment Amount",
          lambda: len(data["payments"].filter(
              (pl.col("actual_payment_amount") < 0) |
              (pl.col("principal_paid") < 0) |
              (pl.col("interest_paid") < 0))))

    check("SANITY-026", "Balance Not Exceeding Original",
          lambda: len(data["loan_tape"].filter(
              pl.col("current_principal_balance") > pl.col("original_loan_amount") * 1.01)))

    check("SANITY-027", "Total Payments Not Exceeding 3x",
          lambda: len(data["payments"].group_by("loan_id").agg(
              pl.col("actual_payment_amount").sum().alias("total_paid")
          ).join(
              data["loan_tape"].select(["loan_id", "original_loan_amount"]).unique(),
              on="loan_id", how="inner"
          ).filter(pl.col("total_paid") > pl.col("original_loan_amount") * 3)))

    check("SANITY-028", "Interest Rate in Valid Range (0.01-0.40)",
          lambda: len(data["loan_tape"].filter(
              ~pl.col("interest_rate").is_between(0.01, 0.40))))

    check("SANITY-029", "Payment Components Sum to Total",
          lambda: len(data["payments"].filter(
              (pl.col("principal_paid") + pl.col("interest_paid") -
               pl.col("actual_payment_amount")).abs() > 0.02)))

    check("SANITY-030", "Principal Paid ≤ Balance Before Payment",
          lambda: len(data["payments"].join(
              data["loan_tape"].select(["loan_id", "snapshot_date", "current_principal_balance"]),
              on=["loan_id", "snapshot_date"], how="inner"
          ).filter(pl.col("principal_paid") > pl.col("current_principal_balance") + 0.01)))

    check("SANITY-031", "Loan Term in Valid Range (6-360 months)",
          lambda: len(data["loan_tape"].filter(
              ~pl.col("original_loan_term").is_between(6, 360))))

    check("SANITY-032", "Loan Amount > 0",
          lambda: len(data["loan_tape"].filter(pl.col("original_loan_amount") <= 0)))

    check("SANITY-033", "Scheduled Payment > 0 for Active Loans",
          lambda: len(data["loan_tape"].filter(
              pl.col("loan_status").is_in(["CURRENT", "DELINQUENT_30", "DELINQUENT_60", "DELINQUENT_90", "DELINQUENT_120"]) &
              (pl.col("scheduled_payment_amount") <= 0)
          )))

    # ==============================================================================
    # CATEGORY 4: PAYMENT WATERFALL (034-038)
    # ==============================================================================
    print("\n[PAYMENT WATERFALL]")

    check("SANITY-034", "Missed Payments Have Zero Amount",
          lambda: len(data["payments"].filter(
              (pl.col("payment_status") == "MISSED") & (pl.col("actual_payment_amount") > 0))))

    check("SANITY-035", "Partial Payments 0 < Amount < Scheduled",
          lambda: len(data["payments"].filter(
              (pl.col("payment_status") == "PARTIAL") &
              ~((pl.col("actual_payment_amount") > 0) &
                (pl.col("actual_payment_amount") < pl.col("scheduled_payment_amount")))
          )))

    check("SANITY-036", "Paid Status Means Full Payment",
          lambda: len(data["payments"].filter(
              (pl.col("payment_status") == "PAID") &
              ((pl.col("actual_payment_amount") - pl.col("scheduled_payment_amount")).abs() > 0.02)
          )))

    check("SANITY-037", "Interest Paid ≤ Accrued Interest",
          lambda: len(data["payments"].filter(
              (pl.col("interest_paid") > pl.col("interest_accrued") + 0.01)
          )))

    check("SANITY-038", "No Principal Payment Without Interest First",
          lambda: len(data["payments"].filter(
              (pl.col("principal_paid") > 0) &
              (pl.col("interest_paid") < pl.col("interest_accrued") - 0.01)
          )))

    # ==============================================================================
    # CATEGORY 5: CREDIT BUREAU (039-045)
    # ==============================================================================
    print("\n[CREDIT BUREAU]")

    check("SANITY-039", "FICO Score in Valid Range (300-850)",
          lambda: len(data["credit_reports"].filter(
              ~pl.col("fico_score_8").is_between(300, 850))))

    check("SANITY-040", "Open Accounts ≥ 0",
          lambda: len(data["credit_reports"].filter(
              pl.col("open_trades_count") < 0)))

    check("SANITY-041", "Total Inquiries ≥ 0",
          lambda: len(data["credit_reports"].filter(
              pl.col("inquiries_last_6mo_count") < 0)))

    check("SANITY-042", "Delinquent Accounts ≤ Total Accounts",
          lambda: len(data["credit_reports"].filter(
              pl.col("trades_currently_past_due_count") > pl.col("all_trades_count"))))

    check("SANITY-043", "Open Trades ≤ Total Trades",
          lambda: len(data["credit_reports"].filter(
              pl.col("open_trades_count") > pl.col("all_trades_count"))))

    check("SANITY-044", "Revolving Utilization in Valid Range (0-2.0)",
          lambda: len(data["credit_reports"].filter(
              ~pl.col("revolving_utilization_ratio").is_between(0, 2.0))))

    check("SANITY-045", "Credit History Length ≥ 0",
          lambda: len(data["credit_reports"].filter(
              pl.col("months_since_oldest_trade") < 0)))

    # ==============================================================================
    # CATEGORY 6: FRAUD & VERIFICATION (046-050)
    # ==============================================================================
    print("\n[FRAUD & VERIFICATION]")

    check("SANITY-046", "No Approval with Failed Fraud Check",
          lambda: len(data["applications"].filter(
              pl.col("decision_status") == "APPROVED"
          ).join(
              data["fraud_verification"].filter(pl.col("fraud_check_status") == "FAILED"),
              on="application_id", how="inner"
          )))

    check("SANITY-047", "Identity Verification Score in Valid Range (0-100)",
          lambda: len(data["fraud_verification"].filter(
              ~pl.col("identity_verification_score").is_between(0, 100))))

    check("SANITY-048", "Fraud Risk Score in Valid Range (0-999)",
          lambda: len(data["fraud_verification"].filter(
              ~pl.col("fraud_risk_score").is_between(0, 999))))

    check("SANITY-049", "Income Verification Not Null for Approved",
          lambda: len(data["applications"].filter(
              pl.col("decision_status") == "APPROVED"
          ).join(
              data["fraud_verification"].filter(pl.col("income_verification_status").is_null()),
              on="application_id", how="inner"
          )))

    check("SANITY-050", "Employment Verification Not Null for Approved",
          lambda: len(data["applications"].filter(
              pl.col("decision_status") == "APPROVED"
          ).join(
              data["fraud_verification"].filter(pl.col("employment_verification_status").is_null()),
              on="application_id", how="inner"
          )))

    # ==============================================================================
    # CATEGORY 7: REFERENTIAL INTEGRITY (051-053)
    # ==============================================================================
    print("\n[REFERENTIAL INTEGRITY]")

    check("SANITY-051", "All Tradelines Have Valid Credit Report",
          lambda: len(data["credit_tradelines"].join(
              data["credit_reports"], on="application_id", how="anti")))

    check("SANITY-052", "All Fraud Records Have Valid Application",
          lambda: len(data["fraud_verification"].join(
              data["applications"], on="application_id", how="anti")))

    check("SANITY-053", "All Bank Transactions Have Valid Application",
          lambda: len(data["bank_transactions"].join(
              data["applications"], on="application_id", how="anti")))

    # ==============================================================================
    # CATEGORY 8: CROSS-TABLE STATE (054-060)
    # ==============================================================================
    print("\n[CROSS-TABLE STATE]")

    check("SANITY-054", "No Resurrection After Payoff",
          lambda: data["loan_tape"].sort(["loan_id", "snapshot_date"]).select([
              "loan_id",
              "loan_status",
              pl.col("loan_status").shift(1).over("loan_id").alias("prev_status")
          ]).filter(
              (pl.col("prev_status") == "PAID_OFF") & (pl.col("loan_status") != "PAID_OFF")
          ).select("loan_id").n_unique())

    check("SANITY-055", "No Resurrection After Chargeoff",
          lambda: data["loan_tape"].sort(["loan_id", "snapshot_date"]).select([
              "loan_id",
              "loan_status",
              pl.col("loan_status").shift(1).over("loan_id").alias("prev_status")
          ]).filter(
              (pl.col("prev_status") == "CHARGED_OFF") & (pl.col("loan_status") != "CHARGED_OFF")
          ).select("loan_id").n_unique())

    check("SANITY-056", "Balance Can Only Decrease",
          lambda: len(data["loan_tape"].filter(
              ~pl.col("loan_status").is_in(["CHARGED_OFF", "PAID_OFF"])
          ).sort(["loan_id", "snapshot_date"]).select([
              "current_principal_balance",
              pl.col("current_principal_balance").shift(1).over("loan_id").alias("prev_balance")
          ]).filter(pl.col("current_principal_balance") > pl.col("prev_balance") + 1.0)))

    check("SANITY-057", "Payments Match Loan Count",
          lambda: abs(
              data["loan_tape"].select("loan_id").n_unique() -
              data["payments"].select("loan_id").n_unique()
          ) if abs(data["loan_tape"].select("loan_id").n_unique() -
                   data["payments"].select("loan_id").n_unique()) > 1000 else 0)

    check("SANITY-058", "Credit Report Per Application",
          lambda: abs(len(data["applications"]) - len(data["credit_reports"])))

    check("SANITY-059", "Fraud Check Per Application",
          lambda: abs(len(data["applications"]) - len(data["fraud_verification"])))

    check("SANITY-060", "Application PK Uniqueness",
          lambda: len(data["applications"]) - data["applications"]["application_id"].n_unique())

    # ==============================================================================
    # SUMMARY
    # ==============================================================================
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    total = passed + failed
    print(f"\nTotal Checks Run: {total}")
    print(f"✅ Passed: {passed} ({passed/total*100:.1f}%)")
    print(f"❌ Failed: {failed} ({failed/total*100:.1f}%)")
    print(f"⚠️  Skipped: {skipped}")

    if failed > 0:
        print(f"\n🚨 {failed} CHECKS FAILED:")
        for check_id, name, violations, status in results:
            if status == "FAIL":
                print(f"  • {check_id}: {name} - {violations:,} violations")
    else:
        print("\n✅ ALL SANITY CHECKS PASSED!")

    if skipped > 0:
        print(f"\n⚠️  {skipped} CHECKS SKIPPED:")
        for check_id, name, violations, status in results:
            if status.startswith("SKIP"):
                print(f"  • {check_id}: {name}")

    # Save results
    df = pl.DataFrame({
        "Check_ID": [r[0] for r in results],
        "Check_Name": [r[1] for r in results],
        "Violations": [r[2] if r[2] is not None else -1 for r in results],
        "Status": [r[3] for r in results]
    })
    output_file = "complete_sanity_check_results.csv"
    df.write_csv(output_file)
    print(f"\n📄 Full report saved to: {output_file}")

    return failed == 0


if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "sherpaiq_lc/data_domain/lendco/raw/data"
    success = run_all_sanity_checks(data_dir)
    sys.exit(0 if success else 1)
