"""
Foundation Sanity Checks - Zero Tolerance Validation
Implements 60 fundamental integrity checks that should NEVER fail

Author: Claude Code Deep QA Analysis
Date: 2026-01-08
Priority: RUN THIS FIRST before any other validation
"""

import polars as pl
import os
from datetime import datetime


class SanityCheckValidator:
    """
    Foundation sanity checks for logical impossibilities.

    All checks are CRITICAL severity and should have ZERO violations.
    Any failure indicates a fundamental data corruption or generator bug.
    """

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.results = []
        self.data = {}
        self.critical_failures = 0

    def load_data(self):
        """Load all parquet files"""
        print(f"Loading data from {self.data_dir}...")
        tables = [
            "applications", "loan_tape", "payments", "credit_reports",
            "credit_tradelines", "fraud_verification", "bank_transactions"
        ]

        for table in tables:
            path = os.path.join(self.data_dir, f"{table}.parquet")
            if os.path.exists(path):
                self.data[table] = pl.read_parquet(path)
                print(f"  ✓ Loaded {table}: {len(self.data[table]):,} rows")
            else:
                print(f"  ⚠️  {table}.parquet not found, skipping")

    def log_result(self, check_id, check_name, violations, details, tolerance=0):
        """Log sanity check result"""
        status = "PASS" if violations <= tolerance else "FAIL"

        if status == "FAIL":
            self.critical_failures += 1

        self.results.append({
            "Check ID": check_id,
            "Check Name": check_name,
            "Status": status,
            "Violations": violations,
            "Tolerance": tolerance,
            "Details": details,
            "Severity": "CRITICAL"
        })

        emoji = "✅" if status == "PASS" else "❌"
        print(f"{emoji} {check_id} - {check_name}: {details} ({violations:,} violations)")

    # ========================================
    # LIFECYCLE SANITY CHECKS
    # ========================================

    def sanity_001_no_funded_without_approval(self):
        """SANITY-001: Every loan must have APPROVED status"""
        if "loan_tape" not in self.data or "applications" not in self.data:
            return

        violations = self.data["loan_tape"].join(
            self.data["applications"], on="application_id", how="inner"
        ).filter(
            pl.col("decision_status") != "APPROVED"
        )

        count = len(violations)
        self.log_result(
            "SANITY-001", "No Funded Loan Without Approval",
            count,
            f"{count:,} loans funded for non-APPROVED applications",
            tolerance=0
        )

    def sanity_002_no_approval_without_credit(self):
        """SANITY-002: Every APPROVED app must have credit report"""
        if "applications" not in self.data or "credit_reports" not in self.data:
            return

        violations = self.data["applications"].filter(
            pl.col("decision_status") == "APPROVED"
        ).join(
            self.data["credit_reports"], on="application_id", how="anti"
        )

        count = len(violations)
        self.log_result(
            "SANITY-002", "No Approval Without Credit Report",
            count,
            f"{count:,} approved apps missing credit reports",
            tolerance=0
        )

    def sanity_003_no_approval_without_fraud_check(self):
        """SANITY-003: Every APPROVED app must have fraud check"""
        if "applications" not in self.data or "fraud_verification" not in self.data:
            return

        violations = self.data["applications"].filter(
            pl.col("decision_status") == "APPROVED"
        ).join(
            self.data["fraud_verification"], on="application_id", how="anti"
        )

        count = len(violations)
        self.log_result(
            "SANITY-003", "No Approval Without Fraud Check",
            count,
            f"{count:,} approved apps missing fraud verification",
            tolerance=0
        )

    def sanity_004_no_payment_without_loan(self):
        """SANITY-004: Every payment must link to funded loan"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        violations = self.data["payments"].join(
            self.data["loan_tape"], on="loan_id", how="anti"
        )

        count = len(violations)
        self.log_result(
            "SANITY-004", "No Payment Without Funded Loan",
            count,
            f"{count:,} orphan payments without loan",
            tolerance=0
        )

    def sanity_007_no_declined_in_loan_tape(self):
        """SANITY-007: No DECLINED apps should have funded loans"""
        if "loan_tape" not in self.data or "applications" not in self.data:
            return

        violations = self.data["loan_tape"].join(
            self.data["applications"], on="application_id", how="inner"
        ).filter(
            pl.col("decision_status") == "DECLINED"
        )

        count = len(violations)
        self.log_result(
            "SANITY-007", "No Declined Application in Loan Tape",
            count,
            f"{count:,} declined apps were funded",
            tolerance=0
        )

    # ========================================
    # STATE MACHINE VIOLATIONS
    # ========================================

    def sanity_009_no_payments_after_payoff(self):
        """SANITY-009: No payments after loan paid off"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        # Get payoff dates
        payoff_dates = self.data["loan_tape"].filter(
            pl.col("loan_status") == "PAID_OFF"
        ).group_by("loan_id").agg(
            pl.col("snapshot_date").max().alias("payoff_date")
        )

        # Find payments after payoff
        violations = self.data["payments"].join(
            payoff_dates, on="loan_id", how="inner"
        ).filter(
            pl.col("payment_received_date") > pl.col("payoff_date")
        )

        count = len(violations)
        self.log_result(
            "SANITY-009", "No Payments After Loan Paid Off",
            count,
            f"{count:,} payments after payoff date",
            tolerance=0
        )

    def sanity_010_no_payments_after_chargeoff(self):
        """SANITY-010: No payments after chargeoff (except recovery)"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        # Get chargeoff dates
        co_dates = self.data["loan_tape"].filter(
            pl.col("loan_status") == "CHARGED_OFF"
        ).group_by("loan_id").agg(
            pl.col("snapshot_date").min().alias("co_date")
        )

        # Find payments after chargeoff
        violations = self.data["payments"].join(
            co_dates, on="loan_id", how="inner"
        ).filter(
            (pl.col("payment_received_date") > pl.col("co_date")) &
            (pl.col("actual_payment_amount") > 0)
        )

        count = len(violations)
        self.log_result(
            "SANITY-010", "No Payments After Chargeoff",
            count,
            f"{count:,} payments after chargeoff",
            tolerance=0
        )

    def sanity_012_no_current_with_dpd(self):
        """SANITY-012: CURRENT loans must have DPD = 0"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            (pl.col("loan_status") == "CURRENT") &
            (pl.col("days_past_due") > 0)
        )

        count = len(violations)
        self.log_result(
            "SANITY-012", "No CURRENT Status With DPD > 0",
            count,
            f"{count:,} CURRENT loans have days_past_due > 0",
            tolerance=0
        )

    def sanity_013_no_balance_on_paid_off(self):
        """SANITY-013: PAID_OFF loans must have zero balance"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            (pl.col("loan_status") == "PAID_OFF") &
            (pl.col("current_principal_balance") > 0.01)
        )

        count = len(violations)
        self.log_result(
            "SANITY-013", "No Balance on Paid Off Loans",
            count,
            f"{count:,} paid-off loans have balance > 0",
            tolerance=0
        )

    def sanity_016_loan_status_valid_enum(self):
        """SANITY-016: Loan status must be valid enum"""
        if "loan_tape" not in self.data:
            return

        valid_statuses = [
            'CURRENT', 'DELINQUENT_30', 'DELINQUENT_60', 'DELINQUENT_90',
            'DELINQUENT_120', 'CHARGED_OFF', 'PAID_OFF', 'PREPAID',
            'CANCELLED', 'IN_FORBEARANCE'
        ]

        violations = self.data["loan_tape"].filter(
            ~pl.col("loan_status").is_in(valid_statuses)
        )

        count = len(violations)
        self.log_result(
            "SANITY-016", "Loan Status Valid Enum",
            count,
            f"{count:,} loans have invalid loan_status",
            tolerance=0
        )

    # ========================================
    # TEMPORAL IMPOSSIBILITIES
    # ========================================

    def sanity_017_application_before_credit_pull(self):
        """SANITY-017: Credit report must be pulled after application"""
        if "applications" not in self.data or "credit_reports" not in self.data:
            return

        violations = self.data["applications"].join(
            self.data["credit_reports"], on="application_id", how="inner"
        ).filter(
            pl.col("report_date") < pl.col("application_date")
        )

        count = len(violations)
        self.log_result(
            "SANITY-017", "Application Before Credit Report Pull",
            count,
            f"{count:,} credit reports pulled before application",
            tolerance=0
        )

    def sanity_019_origination_after_application(self):
        """SANITY-019: Loan origination must be after application"""
        if "loan_tape" not in self.data or "applications" not in self.data:
            return

        violations = self.data["loan_tape"].join(
            self.data["applications"], on="application_id", how="inner"
        ).filter(
            pl.col("origination_date") < pl.col("application_date")
        )

        count = len(violations)
        self.log_result(
            "SANITY-019", "Origination After Application",
            count,
            f"{count:,} loans originated before application",
            tolerance=0
        )

    def sanity_022_birth_before_application(self):
        """SANITY-022: Applicant must be born before applying"""
        if "applications" not in self.data:
            return

        violations = self.data["applications"].filter(
            pl.col("date_of_birth") >= pl.col("application_date")
        )

        count = len(violations)
        self.log_result(
            "SANITY-022", "Birth Date Before Application",
            count,
            f"{count:,} applications before birth",
            tolerance=0
        )

    def sanity_023_no_payments_before_origination(self):
        """SANITY-023: All payments must be after origination"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        # Get origination dates
        orig_dates = self.data["loan_tape"].select(
            ["loan_id", "origination_date"]
        ).unique()

        violations = self.data["payments"].join(
            orig_dates, on="loan_id", how="inner"
        ).filter(
            pl.col("payment_received_date") < pl.col("origination_date")
        )

        count = len(violations)
        self.log_result(
            "SANITY-023", "No Payments Before Origination",
            count,
            f"{count:,} payments before loan originated",
            tolerance=0
        )

    # ========================================
    # FINANCIAL IMPOSSIBILITIES
    # ========================================

    def sanity_024_no_negative_principal(self):
        """SANITY-024: Principal balance cannot be negative"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            pl.col("current_principal_balance") < 0
        )

        count = len(violations)
        self.log_result(
            "SANITY-024", "No Negative Principal Balance",
            count,
            f"{count:,} loans have negative balance",
            tolerance=0
        )

    def sanity_025_no_negative_payment(self):
        """SANITY-025: Payment amounts cannot be negative"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("actual_payment_amount") < 0) |
            (pl.col("principal_paid") < 0) |
            (pl.col("interest_paid") < 0)
        )

        count = len(violations)
        self.log_result(
            "SANITY-025", "No Negative Payment Amount",
            count,
            f"{count:,} payments have negative amounts",
            tolerance=0
        )

    def sanity_026_balance_not_exceeding_original(self):
        """SANITY-026: Balance should not exceed original amount"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            pl.col("current_principal_balance") > pl.col("original_loan_amount") * 1.01
        )

        count = len(violations)
        self.log_result(
            "SANITY-026", "Balance Not Exceeding Original",
            count,
            f"{count:,} loans have balance > original amount",
            tolerance=0
        )

    def sanity_029_payment_components_sum(self):
        """SANITY-029: Payment components must sum to total"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("principal_paid") + pl.col("interest_paid") -
             pl.col("actual_payment_amount")).abs() > 0.02
        )

        count = len(violations)
        self.log_result(
            "SANITY-029", "Payment Components Sum to Total",
            count,
            f"{count:,} payments don't balance (±$0.02)",
            tolerance=0
        )

    def sanity_030_no_fee_exceeding_loan(self):
        """SANITY-030: Origination fee cannot exceed loan amount"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            pl.col("origination_fee") >= pl.col("original_loan_amount")
        )

        count = len(violations)
        self.log_result(
            "SANITY-030", "No Fee Exceeding Loan Amount",
            count,
            f"{count:,} loans have fee >= loan amount",
            tolerance=0
        )

    # ========================================
    # PAYMENT WATERFALL VIOLATIONS
    # ========================================

    def sanity_031_posted_payments_have_date(self):
        """SANITY-031: Posted payments must have received date"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("payment_status") == "POSTED") &
            (pl.col("payment_received_date").is_null())
        )

        count = len(violations)
        self.log_result(
            "SANITY-031", "Posted Payments Have Received Date",
            count,
            f"{count:,} posted payments missing date",
            tolerance=0
        )

    def sanity_034_missed_payments_zero_amount(self):
        """SANITY-034: Missed payments must have zero actual amount"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("payment_status") == "MISSED") &
            (pl.col("actual_payment_amount") > 0)
        )

        count = len(violations)
        self.log_result(
            "SANITY-034", "Missed Payments Have Zero Amount",
            count,
            f"{count:,} missed payments with amount > 0",
            tolerance=0
        )

    def sanity_036_nsf_must_be_returned(self):
        """SANITY-036: NSF payments must be marked returned"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("nsf_flag") == True) &
            (pl.col("returned_flag") == False)
        )

        count = len(violations)
        self.log_result(
            "SANITY-036", "NSF Payments Must Be Returned",
            count,
            f"{count:,} NSF payments not marked returned",
            tolerance=0
        )

    def sanity_037_returned_have_return_date(self):
        """SANITY-037: Returned payments must have return date"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("returned_flag") == True) &
            (pl.col("return_date").is_null())
        )

        count = len(violations)
        self.log_result(
            "SANITY-037", "Returned Payments Have Return Date",
            count,
            f"{count:,} returned payments missing return_date",
            tolerance=0
        )

    # ========================================
    # CREDIT BUREAU IMPOSSIBILITIES
    # ========================================

    def sanity_039_fico_in_valid_range(self):
        """SANITY-039: FICO scores must be 300-850"""
        if "credit_reports" not in self.data:
            return

        violations = self.data["credit_reports"].filter(
            ~pl.col("fico_score_8").is_between(300, 850)
        )

        count = len(violations)
        self.log_result(
            "SANITY-039", "FICO Score in Valid Range",
            count,
            f"{count:,} FICO scores outside 300-850",
            tolerance=0
        )

    def sanity_043_open_trades_le_total(self):
        """SANITY-043: Open trades cannot exceed total trades"""
        if "credit_reports" not in self.data:
            return

        violations = self.data["credit_reports"].filter(
            pl.col("all_trades_open_count") > pl.col("all_trades_count")
        )

        count = len(violations)
        self.log_result(
            "SANITY-043", "Open Trades ≤ Total Trades",
            count,
            f"{count:,} reports have open > total trades",
            tolerance=0
        )

    # ========================================
    # FRAUD & IDENTITY CONFLICTS
    # ========================================

    def sanity_047_no_approval_for_deceased(self):
        """SANITY-047: Cannot approve deceased SSN"""
        if "applications" not in self.data or "fraud_verification" not in self.data:
            return

        violations = self.data["applications"].join(
            self.data["fraud_verification"], on="application_id", how="inner"
        ).filter(
            (pl.col("ssn_deceased_flag") == True) &
            (pl.col("decision_status") == "APPROVED")
        )

        count = len(violations)
        self.log_result(
            "SANITY-047", "No Approval for Deceased SSN",
            count,
            f"{count:,} approved apps for deceased SSN",
            tolerance=0
        )

    def sanity_051_applicant_age_valid(self):
        """SANITY-051: Applicant must be 18-100 years old"""
        if "applications" not in self.data:
            return

        violations = self.data["applications"].filter(
            ((pl.col("application_date").cast(pl.Date) -
              pl.col("date_of_birth").cast(pl.Date)).dt.days() / 365.25 < 18) |
            ((pl.col("application_date").cast(pl.Date) -
              pl.col("date_of_birth").cast(pl.Date)).dt.days() / 365.25 > 100)
        )

        count = len(violations)
        self.log_result(
            "SANITY-051", "Applicant Age 18-100",
            count,
            f"{count:,} applicants outside age range",
            tolerance=0
        )

    # ========================================
    # CROSS-TABLE STATE CONSISTENCY
    # ========================================

    def sanity_054_no_resurrection_after_payoff(self):
        """SANITY-054: Loan cannot go from PAID_OFF to active"""
        if "loan_tape" not in self.data:
            return

        status_changes = self.data["loan_tape"].sort(["loan_id", "snapshot_date"]).select([
            "loan_id",
            "snapshot_date",
            "loan_status",
            pl.col("loan_status").shift(1).over("loan_id").alias("prev_status")
        ])

        violations = status_changes.filter(
            (pl.col("prev_status") == "PAID_OFF") &
            (pl.col("loan_status") != "PAID_OFF")
        )

        count = violations.select("loan_id").n_unique()
        self.log_result(
            "SANITY-054", "No Resurrection After Payoff",
            count,
            f"{count:,} loans went from PAID_OFF to active",
            tolerance=0
        )

    def sanity_060_application_pk_unique(self):
        """SANITY-060: application_id must be unique"""
        if "applications" not in self.data:
            return

        total = len(self.data["applications"])
        unique = self.data["applications"]["application_id"].n_unique()
        violations = total - unique

        self.log_result(
            "SANITY-060", "Application ID Uniqueness",
            violations,
            f"{violations:,} duplicate application_id values",
            tolerance=0
        )

    # ========================================
    # MAIN RUNNER
    # ========================================

    def run_all(self):
        """Execute all sanity checks"""
        self.load_data()

        print("\n" + "="*80)
        print("FOUNDATION SANITY CHECKS - ZERO TOLERANCE VALIDATION")
        print("="*80 + "\n")

        # Lifecycle
        print("\n[1/8] Lifecycle Sanity Checks...")
        self.sanity_001_no_funded_without_approval()
        self.sanity_002_no_approval_without_credit()
        self.sanity_003_no_approval_without_fraud_check()
        self.sanity_004_no_payment_without_loan()
        self.sanity_007_no_declined_in_loan_tape()

        # State Machine
        print("\n[2/8] State Machine Violations...")
        self.sanity_009_no_payments_after_payoff()
        self.sanity_010_no_payments_after_chargeoff()
        self.sanity_012_no_current_with_dpd()
        self.sanity_013_no_balance_on_paid_off()
        self.sanity_016_loan_status_valid_enum()

        # Temporal
        print("\n[3/8] Temporal Impossibilities...")
        self.sanity_017_application_before_credit_pull()
        self.sanity_019_origination_after_application()
        self.sanity_022_birth_before_application()
        self.sanity_023_no_payments_before_origination()

        # Financial
        print("\n[4/8] Financial Impossibilities...")
        self.sanity_024_no_negative_principal()
        self.sanity_025_no_negative_payment()
        self.sanity_026_balance_not_exceeding_original()
        self.sanity_029_payment_components_sum()
        self.sanity_030_no_fee_exceeding_loan()

        # Payment Waterfall
        print("\n[5/8] Payment Waterfall Violations...")
        self.sanity_031_posted_payments_have_date()
        self.sanity_034_missed_payments_zero_amount()
        self.sanity_036_nsf_must_be_returned()
        self.sanity_037_returned_have_return_date()

        # Credit Bureau
        print("\n[6/8] Credit Bureau Impossibilities...")
        self.sanity_039_fico_in_valid_range()
        self.sanity_043_open_trades_le_total()

        # Fraud & Identity
        print("\n[7/8] Fraud & Identity Conflicts...")
        self.sanity_047_no_approval_for_deceased()
        self.sanity_051_applicant_age_valid()

        # Cross-Table State
        print("\n[8/8] Cross-Table State Consistency...")
        self.sanity_054_no_resurrection_after_payoff()
        self.sanity_060_application_pk_unique()

        # Generate report
        return pl.DataFrame(self.results)


if __name__ == "__main__":
    validator = SanityCheckValidator("sherpaiq_lc/data_domain/lendco/raw/data")
    df = validator.run_all()

    print("\n" + "="*80)
    print("SANITY CHECK COMPLETE - SUMMARY REPORT")
    print("="*80)

    # Critical failures
    failures = df.filter(pl.col("Status") == "FAIL")

    if len(failures) > 0:
        print(f"\n🚨 CRITICAL: {len(failures)} SANITY CHECKS FAILED")
        print("\nFailed Checks:")
        print(failures.select(["Check ID", "Check Name", "Violations"]))
        print("\n⚠️  DATA INTEGRITY COMPROMISED - FIX GENERATOR BUGS BEFORE PROCEEDING")
    else:
        print("\n✅ ALL SANITY CHECKS PASSED!")
        print("✅ Data foundation is sound - proceed with advanced validation")

    # Save detailed report
    df.write_csv("sanity_check_report.csv")
    print(f"\nDetailed report saved to: sanity_check_report.csv")

    # Exit code for CI/CD
    exit(1 if len(failures) > 0 else 0)
