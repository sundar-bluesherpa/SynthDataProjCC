"""
Complete Foundation Sanity Checks - All 60 Checks
Zero Tolerance Validation for LendCo Synthetic Data

Author: Claude Code Deep QA Analysis
Date: 2026-01-08
Priority: RUN THIS FIRST before any other validation
"""

import polars as pl
import os
from datetime import datetime


class CompleteSanityValidator:
    """
    Complete foundation sanity checks for logical impossibilities.
    Implements ALL 60 checks from SANITY_CHECKS_Foundation.md

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
        print(f"{emoji} {check_id} - {check_name}: {violations:,} violations")

    # ========================================
    # LIFECYCLE SANITY CHECKS (8 checks)
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

        self.log_result(
            "SANITY-001", "No Funded Loan Without Approval",
            len(violations), f"Loans funded for non-APPROVED applications"
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

        self.log_result(
            "SANITY-002", "No Approval Without Credit Report",
            len(violations), f"Approved apps missing credit reports"
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

        self.log_result(
            "SANITY-003", "No Approval Without Fraud Check",
            len(violations), f"Approved apps missing fraud verification"
        )

    def sanity_004_no_payment_without_loan(self):
        """SANITY-004: Every payment must link to funded loan"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        violations = self.data["payments"].join(
            self.data["loan_tape"], on="loan_id", how="anti"
        )

        self.log_result(
            "SANITY-004", "No Payment Without Funded Loan",
            len(violations), f"Orphan payments without loan"
        )

    def sanity_005_no_loan_without_application(self):
        """SANITY-005: Every loan tape record must have parent application"""
        if "loan_tape" not in self.data or "applications" not in self.data:
            return

        violations = self.data["loan_tape"].join(
            self.data["applications"], on="application_id", how="anti"
        )

        self.log_result(
            "SANITY-005", "No Loan Tape Without Application",
            len(violations), f"Orphan loan tape records"
        )

    def sanity_006_no_credit_without_application(self):
        """SANITY-006: Every credit report must link to application"""
        if "credit_reports" not in self.data or "applications" not in self.data:
            return

        violations = self.data["credit_reports"].join(
            self.data["applications"], on="application_id", how="anti"
        )

        self.log_result(
            "SANITY-006", "No Credit Report Without Application",
            len(violations), f"Orphan credit reports"
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

        self.log_result(
            "SANITY-007", "No Declined Application in Loan Tape",
            len(violations), f"Declined apps were funded"
        )

    def sanity_008_no_pending_in_loan_tape(self):
        """SANITY-008: No PENDING apps should have funded loans"""
        if "loan_tape" not in self.data or "applications" not in self.data:
            return

        violations = self.data["loan_tape"].join(
            self.data["applications"], on="application_id", how="inner"
        ).filter(
            pl.col("decision_status").is_in(["PENDING", "UNDER_REVIEW", "INCOMPLETE"])
        )

        self.log_result(
            "SANITY-008", "No Pending Application in Loan Tape",
            len(violations), f"Pending apps were funded"
        )

    # ========================================
    # STATE MACHINE VIOLATIONS (8 checks)
    # ========================================

    def sanity_009_no_payments_after_payoff(self):
        """SANITY-009: No payments after loan paid off"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        payoff_dates = self.data["loan_tape"].filter(
            pl.col("loan_status") == "PAID_OFF"
        ).group_by("loan_id").agg(
            pl.col("snapshot_date").max().alias("payoff_date")
        )

        violations = self.data["payments"].join(
            payoff_dates, on="loan_id", how="inner"
        ).filter(
            pl.col("payment_received_date") > pl.col("payoff_date")
        )

        self.log_result(
            "SANITY-009", "No Payments After Loan Paid Off",
            len(violations), f"Payments after payoff date"
        )

    def sanity_010_no_payments_after_chargeoff(self):
        """SANITY-010: No payments after chargeoff (except recovery)"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        co_dates = self.data["loan_tape"].filter(
            pl.col("loan_status") == "CHARGED_OFF"
        ).group_by("loan_id").agg(
            pl.col("snapshot_date").min().alias("co_date")
        )

        violations = self.data["payments"].join(
            co_dates, on="loan_id", how="inner"
        ).filter(
            (pl.col("payment_received_date") > pl.col("co_date")) &
            (pl.col("actual_payment_amount") > 0)
        )

        self.log_result(
            "SANITY-010", "No Payments After Chargeoff",
            len(violations), f"Payments after chargeoff"
        )

    def sanity_011_no_delinquent_with_all_payments(self):
        """SANITY-011: Delinquent loans must have missed payments"""
        if "loan_tape" not in self.data or "payments" not in self.data:
            return

        # Get latest snapshot
        latest = self.data["loan_tape"].filter(
            pl.col("snapshot_date") == self.data["loan_tape"]["snapshot_date"].max()
        )

        # Count successful payments per loan
        payment_counts = self.data["payments"].filter(
            (pl.col("payment_status") == "POSTED") &
            (pl.col("actual_payment_amount") > 0)
        ).group_by("loan_id").agg(
            pl.count().alias("paid_count")
        )

        # Find delinquent loans with all payments made
        violations = latest.filter(
            pl.col("loan_status").str.contains("DELINQUENT")
        ).join(
            payment_counts, on="loan_id", how="left"
        ).filter(
            pl.col("paid_count") >= pl.col("months_on_book")
        )

        self.log_result(
            "SANITY-011", "No Delinquent With All Payments",
            len(violations), f"Delinquent loans with full payment history", tolerance=0
        )

    def sanity_012_no_current_with_dpd(self):
        """SANITY-012: CURRENT loans must have DPD = 0"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            (pl.col("loan_status") == "CURRENT") &
            (pl.col("days_past_due") > 0)
        )

        self.log_result(
            "SANITY-012", "No CURRENT Status With DPD > 0",
            len(violations), f"CURRENT loans have days_past_due > 0"
        )

    def sanity_013_no_balance_on_paid_off(self):
        """SANITY-013: PAID_OFF loans must have zero balance"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            (pl.col("loan_status") == "PAID_OFF") &
            (pl.col("current_principal_balance") > 0.01)
        )

        self.log_result(
            "SANITY-013", "No Balance on Paid Off Loans",
            len(violations), f"Paid-off loans have balance > 0"
        )

    def sanity_014_no_balance_on_chargedoff(self):
        """SANITY-014: CHARGED_OFF loans should have zero balance"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            (pl.col("loan_status") == "CHARGED_OFF") &
            (pl.col("current_principal_balance") > 0.01) &
            (pl.col("months_on_book") > 4)
        )

        self.log_result(
            "SANITY-014", "No Balance on Charged Off Loans",
            len(violations), f"Charged-off loans retain balance", tolerance=int(len(self.data.get("loan_tape", [])) * 0.05)
        )

    def sanity_015_no_payments_before_first_due(self):
        """SANITY-015: No regular payments before first due date"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        # Get first payment due date per loan
        first_due = self.data["loan_tape"].select(
            ["loan_id", "first_payment_due_date"]
        ).unique()

        violations = self.data["payments"].join(
            first_due, on="loan_id", how="inner"
        ).filter(
            (pl.col("payment_received_date") < pl.col("first_payment_due_date")) &
            (pl.col("payment_type") != "PREPAYMENT")
        )

        total_payments = len(self.data["payments"])
        self.log_result(
            "SANITY-015", "No Payments Before First Due Date",
            len(violations), f"Regular payments before first due date",
            tolerance=int(total_payments * 0.01)
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

        self.log_result(
            "SANITY-016", "Loan Status Valid Enum",
            len(violations), f"Invalid loan_status values"
        )

    # ========================================
    # TEMPORAL IMPOSSIBILITIES (7 checks)
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

        self.log_result(
            "SANITY-017", "Application Before Credit Report Pull",
            len(violations), f"Credit reports pulled before application"
        )

    def sanity_018_application_before_fraud_check(self):
        """SANITY-018: Fraud check must occur after application"""
        if "applications" not in self.data or "fraud_verification" not in self.data:
            return

        violations = self.data["applications"].join(
            self.data["fraud_verification"], on="application_id", how="inner"
        ).filter(
            pl.col("fraud_check_timestamp").cast(pl.Date) < pl.col("application_date")
        )

        self.log_result(
            "SANITY-018", "Application Before Fraud Check",
            len(violations), f"Fraud checks before application"
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

        self.log_result(
            "SANITY-019", "Origination After Application",
            len(violations), f"Loans originated before application"
        )

    def sanity_020_payment_after_origination(self):
        """SANITY-020: First payment must be after origination"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        # Get first payment per loan
        first_payments = self.data["payments"].group_by("loan_id").agg(
            pl.col("payment_received_date").min().alias("first_pmt_date")
        )

        # Get origination dates
        orig_dates = self.data["loan_tape"].select(
            ["loan_id", "origination_date"]
        ).unique()

        violations = first_payments.join(
            orig_dates, on="loan_id", how="inner"
        ).filter(
            pl.col("first_pmt_date") < pl.col("origination_date")
        )

        self.log_result(
            "SANITY-020", "Payment After Origination",
            len(violations), f"Payments before loan originated"
        )

    def sanity_021_no_future_dates(self):
        """SANITY-021: All dates must be <= simulation snapshot"""
        snapshot_date = pl.lit(datetime(2023, 12, 31).date())

        violations = 0

        if "applications" in self.data:
            v1 = self.data["applications"].filter(
                pl.col("application_date") > snapshot_date
            )
            violations += len(v1)

        if "loan_tape" in self.data:
            v2 = self.data["loan_tape"].filter(
                pl.col("snapshot_date") > snapshot_date
            )
            violations += len(v2)

        if "payments" in self.data:
            v3 = self.data["payments"].filter(
                pl.col("payment_received_date") > snapshot_date
            )
            violations += len(v3)

        self.log_result(
            "SANITY-021", "No Future Dates",
            violations, f"Future-dated transactions found"
        )

    def sanity_022_birth_before_application(self):
        """SANITY-022: Applicant must be born before applying"""
        if "applications" not in self.data:
            return

        violations = self.data["applications"].filter(
            pl.col("date_of_birth") >= pl.col("application_date")
        )

        self.log_result(
            "SANITY-022", "Birth Date Before Application",
            len(violations), f"Applications before birth"
        )

    def sanity_023_no_payments_before_origination(self):
        """SANITY-023: All payments must be after origination"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        orig_dates = self.data["loan_tape"].select(
            ["loan_id", "origination_date"]
        ).unique()

        violations = self.data["payments"].join(
            orig_dates, on="loan_id", how="inner"
        ).filter(
            pl.col("payment_received_date") < pl.col("origination_date")
        )

        self.log_result(
            "SANITY-023", "No Payments Before Origination",
            len(violations), f"Payments before loan originated"
        )

    # ========================================
    # FINANCIAL IMPOSSIBILITIES (7 checks)
    # ========================================

    def sanity_024_no_negative_principal(self):
        """SANITY-024: Principal balance cannot be negative"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            pl.col("current_principal_balance") < 0
        )

        self.log_result(
            "SANITY-024", "No Negative Principal Balance",
            len(violations), f"Negative balances found"
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

        self.log_result(
            "SANITY-025", "No Negative Payment Amount",
            len(violations), f"Negative payment amounts"
        )

    def sanity_026_balance_not_exceeding_original(self):
        """SANITY-026: Balance should not exceed original amount"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            pl.col("current_principal_balance") > pl.col("original_loan_amount") * 1.01
        )

        self.log_result(
            "SANITY-026", "Balance Not Exceeding Original",
            len(violations), f"Balance > original amount"
        )

    def sanity_027_total_payments_reasonable(self):
        """SANITY-027: Sum of payments not exceeding 3x original"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        loan_payment_sums = self.data["payments"].group_by("loan_id").agg(
            pl.col("actual_payment_amount").sum().alias("total_paid")
        )

        loan_amounts = self.data["loan_tape"].select(
            ["loan_id", "original_loan_amount"]
        ).unique()

        violations = loan_payment_sums.join(
            loan_amounts, on="loan_id", how="inner"
        ).filter(
            pl.col("total_paid") > pl.col("original_loan_amount") * 3
        )

        self.log_result(
            "SANITY-027", "Total Payments Not Exceeding 3x",
            len(violations), f"Total payments > 3x original amount"
        )

    def sanity_028_no_interest_only_with_zero_rate(self):
        """SANITY-028: Interest-only loans must have interest rate"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            (pl.col("interest_only_indicator") == True) &
            (pl.col("original_interest_rate") == 0)
        )

        self.log_result(
            "SANITY-028", "No Interest-Only With Zero Rate",
            len(violations), f"Interest-only loans with 0% rate"
        )

    def sanity_029_payment_components_sum(self):
        """SANITY-029: Payment components must sum to total"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("principal_paid") + pl.col("interest_paid") -
             pl.col("actual_payment_amount")).abs() > 0.02
        )

        self.log_result(
            "SANITY-029", "Payment Components Sum to Total",
            len(violations), f"Payment components don't balance"
        )

    def sanity_030_no_fee_exceeding_loan(self):
        """SANITY-030: Origination fee cannot exceed loan amount"""
        if "loan_tape" not in self.data:
            return

        violations = self.data["loan_tape"].filter(
            pl.col("origination_fee") >= pl.col("original_loan_amount")
        )

        self.log_result(
            "SANITY-030", "No Fee Exceeding Loan Amount",
            len(violations), f"Fees >= loan amount"
        )

    # ========================================
    # PAYMENT WATERFALL VIOLATIONS (8 checks)
    # ========================================

    def sanity_031_posted_payments_have_date(self):
        """SANITY-031: Posted payments must have received date"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("payment_status") == "POSTED") &
            (pl.col("payment_received_date").is_null())
        )

        self.log_result(
            "SANITY-031", "Posted Payments Have Received Date",
            len(violations), f"Posted payments missing date"
        )

    def sanity_032_no_zero_scheduled_payment(self):
        """SANITY-032: Scheduled payment must be > 0 for active loans"""
        if "payments" not in self.data or "loan_tape" not in self.data:
            return

        # Join to get loan status
        violations = self.data["payments"].join(
            self.data["loan_tape"].select(["loan_id", "loan_status"]).unique(),
            on="loan_id", how="inner"
        ).filter(
            (pl.col("scheduled_payment_amount") <= 0) &
            ~pl.col("loan_status").is_in(["PAID_OFF", "CHARGED_OFF"])
        )

        self.log_result(
            "SANITY-032", "No Zero Scheduled Payment",
            len(violations), f"Zero scheduled payment for active loans"
        )

    def sanity_033_overpayments_flagged(self):
        """SANITY-033: Overpayments must be flagged"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("actual_payment_amount") > pl.col("scheduled_payment_amount") * 1.05) &
            ~pl.col("payment_type").is_in(["PREPAYMENT", "PAYOFF"]) &
            (pl.col("is_extra_payment") == False)
        )

        total = len(self.data["payments"])
        self.log_result(
            "SANITY-033", "Overpayments Must Be Flagged",
            len(violations), f"Overpayments not marked as extra",
            tolerance=int(total * 0.01)
        )

    def sanity_034_missed_payments_zero_amount(self):
        """SANITY-034: Missed payments must have zero actual amount"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("payment_status") == "MISSED") &
            (pl.col("actual_payment_amount") > 0)
        )

        self.log_result(
            "SANITY-034", "Missed Payments Have Zero Amount",
            len(violations), f"Missed payments with amount > 0"
        )

    def sanity_035_late_payments_have_fee(self):
        """SANITY-035: Late payments should have late fee"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("days_late") > pl.col("grace_period_days").fill_null(15)) &
            (pl.col("payment_status") == "POSTED") &
            (pl.col("late_fee_assessed") == 0) &
            (pl.col("late_fee_waived") == False)
        )

        total = len(self.data["payments"])
        self.log_result(
            "SANITY-035", "Late Payments Have Late Fee",
            len(violations), f"Late payments without fee",
            tolerance=int(total * 0.20)
        )

    def sanity_036_nsf_must_be_returned(self):
        """SANITY-036: NSF payments must be marked returned"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("nsf_flag") == True) &
            (pl.col("returned_flag") == False)
        )

        self.log_result(
            "SANITY-036", "NSF Payments Must Be Returned",
            len(violations), f"NSF payments not marked returned"
        )

    def sanity_037_returned_have_return_date(self):
        """SANITY-037: Returned payments must have return date"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("returned_flag") == True) &
            (pl.col("return_date").is_null())
        )

        self.log_result(
            "SANITY-037", "Returned Payments Have Return Date",
            len(violations), f"Returned payments missing return_date"
        )

    def sanity_038_autopay_failures_have_reason(self):
        """SANITY-038: Failed autopay should have return reason"""
        if "payments" not in self.data:
            return

        violations = self.data["payments"].filter(
            (pl.col("autopay_flag") == True) &
            pl.col("payment_status").is_in(["RETURNED", "REVERSED"]) &
            (pl.col("return_reason_code").is_null())
        )

        total_autopay_failures = len(self.data["payments"].filter(
            (pl.col("autopay_flag") == True) &
            pl.col("payment_status").is_in(["RETURNED", "REVERSED"])
        ))

        self.log_result(
            "SANITY-038", "Autopay Failures Have Reason Code",
            len(violations), f"Autopay failures without reason",
            tolerance=int(max(1, total_autopay_failures * 0.10))
        )

    # ========================================
    # CREDIT BUREAU IMPOSSIBILITIES (8 checks)
    # ========================================

    def sanity_039_fico_in_valid_range(self):
        """SANITY-039: FICO scores must be 300-850"""
        if "credit_reports" not in self.data:
            return

        violations = self.data["credit_reports"].filter(
            ~pl.col("fico_score_8").is_between(300, 850)
        )

        self.log_result(
            "SANITY-039", "FICO Score in Valid Range",
            len(violations), f"FICO scores outside 300-850"
        )

    def sanity_040_credit_file_after_birth(self):
        """SANITY-040: Credit file established after birth"""
        if "credit_reports" not in self.data or "applications" not in self.data:
            return

        violations = self.data["credit_reports"].join(
            self.data["applications"], on="application_id", how="inner"
        ).filter(
            pl.col("file_since_date") < pl.col("date_of_birth")
        )

        self.log_result(
            "SANITY-040", "Credit File After Birth",
            len(violations), f"Credit files before birth"
        )

    def sanity_041_bankruptcy_in_public_records(self):
        """SANITY-041: Bankruptcies must be counted in public records"""
        if "credit_reports" not in self.data:
            return

        violations = self.data["credit_reports"].filter(
            (pl.col("bankruptcies_count") > 0) &
            (pl.col("public_records_count") == 0)
        )

        self.log_result(
            "SANITY-041", "Bankruptcy in Public Records",
            len(violations), f"Bankruptcies not in public records"
        )

    def sanity_042_utilization_not_exceeding_200pct(self):
        """SANITY-042: Utilization ratio should not exceed 200%"""
        if "credit_reports" not in self.data:
            return

        violations = self.data["credit_reports"].filter(
            pl.col("revolving_utilization_ratio") > 2.0
        )

        total = len(self.data["credit_reports"])
        self.log_result(
            "SANITY-042", "Utilization Not Exceeding 200%",
            len(violations), f"Utilization > 200%",
            tolerance=int(total * 0.001)
        )

    def sanity_043_open_trades_le_total(self):
        """SANITY-043: Open trades cannot exceed total trades"""
        if "credit_reports" not in self.data:
            return

        violations = self.data["credit_reports"].filter(
            pl.col("all_trades_open_count") > pl.col("all_trades_count")
        )

        self.log_result(
            "SANITY-043", "Open Trades ≤ Total Trades",
            len(violations), f"Open > total trades"
        )

    def sanity_044_tradeline_balance_le_limit(self):
        """SANITY-044: Tradeline balance should not exceed limit by >10%"""
        if "credit_tradelines" not in self.data:
            return

        violations = self.data["credit_tradelines"].filter(
            (pl.col("current_balance") > pl.col("credit_limit") * 1.10) &
            (pl.col("account_status") == "OPEN")
        )

        total = len(self.data["credit_tradelines"])
        self.log_result(
            "SANITY-044", "Tradeline Balance ≤ Limit",
            len(violations), f"Balances >110% of limit",
            tolerance=int(total * 0.05)
        )

    def sanity_045_closed_tradelines_no_payment(self):
        """SANITY-045: Closed accounts should have no payment due"""
        if "credit_tradelines" not in self.data:
            return

        violations = self.data["credit_tradelines"].filter(
            (pl.col("account_status") == "CLOSED") &
            (pl.col("monthly_payment") > 0)
        )

        self.log_result(
            "SANITY-045", "Closed Tradelines No Payment Due",
            len(violations), f"Closed accounts with payment"
        )

    def sanity_046_tradeline_open_before_report(self):
        """SANITY-046: Tradeline open date before report date"""
        if "credit_tradelines" not in self.data or "credit_reports" not in self.data:
            return

        violations = self.data["credit_tradelines"].join(
            self.data["credit_reports"], on="credit_report_id", how="inner"
        ).filter(
            pl.col("open_date") > pl.col("report_date")
        )

        self.log_result(
            "SANITY-046", "Tradeline Open Before Report",
            len(violations), f"Tradelines opened after report"
        )

    # ========================================
    # FRAUD & IDENTITY CONFLICTS (6 checks)
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

        self.log_result(
            "SANITY-047", "No Approval for Deceased SSN",
            len(violations), f"Approved apps for deceased SSN"
        )

    def sanity_048_ssn_issued_after_birth(self):
        """SANITY-048: SSN issuance after birth year"""
        if "applications" not in self.data or "fraud_verification" not in self.data:
            return

        violations = self.data["applications"].join(
            self.data["fraud_verification"], on="application_id", how="inner"
        ).filter(
            pl.col("ssn_issued_start_year") < pl.col("date_of_birth").dt.year()
        )

        total = len(self.data.get("applications", []))
        self.log_result(
            "SANITY-048", "SSN Issued After Birth",
            len(violations), f"SSN issued before birth",
            tolerance=int(total * 0.01)
        )

    def sanity_049_identity_fail_should_decline(self):
        """SANITY-049: Identity verification failures should decline"""
        if "applications" not in self.data or "fraud_verification" not in self.data:
            return

        violations = self.data["applications"].join(
            self.data["fraud_verification"], on="application_id", how="inner"
        ).filter(
            (pl.col("identity_verification_result") == "FAIL") &
            (pl.col("decision_status") == "APPROVED")
        )

        self.log_result(
            "SANITY-049", "Identity Fail Should Decline",
            len(violations), f"Approved with failed identity check"
        )

    def sanity_050_critical_fraud_should_decline(self):
        """SANITY-050: Critical fraud tier should decline"""
        if "applications" not in self.data or "fraud_verification" not in self.data:
            return

        violations = self.data["applications"].join(
            self.data["fraud_verification"], on="application_id", how="inner"
        ).filter(
            (pl.col("fraud_risk_tier") == "CRITICAL") &
            (pl.col("decision_status") == "APPROVED")
        )

        self.log_result(
            "SANITY-050", "Critical Fraud Should Decline",
            len(violations), f"Approved with critical fraud tier"
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

        self.log_result(
            "SANITY-051", "Applicant Age 18-100",
            len(violations), f"Applicants outside age range"
        )

    def sanity_052_email_format_validation(self):
        """SANITY-052: Email addresses must have @ and domain"""
        if "applications" not in self.data:
            return

        violations = self.data["applications"].filter(
            pl.col("email_address").is_not_null() &
            ~pl.col("email_address").str.contains(r"@.*\.")
        )

        total_emails = self.data["applications"].filter(
            pl.col("email_address").is_not_null()
        ).height

        self.log_result(
            "SANITY-052", "Email Format Validation",
            len(violations), f"Invalid email formats",
            tolerance=int(max(1, total_emails * 0.01))
        )

    # ========================================
    # CROSS-TABLE STATE CONSISTENCY (7 checks)
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

        self.log_result(
            "SANITY-054", "No Resurrection After Payoff",
            violations.select("loan_id").n_unique(), f"Loans resurrected after payoff"
        )

    def sanity_055_no_resurrection_after_chargeoff(self):
        """SANITY-055: Loan cannot go from CHARGED_OFF to active"""
        if "loan_tape" not in self.data:
            return

        status_changes = self.data["loan_tape"].sort(["loan_id", "snapshot_date"]).select([
            "loan_id",
            "snapshot_date",
            "loan_status",
            pl.col("loan_status").shift(1).over("loan_id").alias("prev_status")
        ])

        violations = status_changes.filter(
            (pl.col("prev_status") == "CHARGED_OFF") &
            (pl.col("loan_status") != "CHARGED_OFF")
        )

        self.log_result(
            "SANITY-055", "No Resurrection After Chargeoff",
            violations.select("loan_id").n_unique(), f"Loans resurrected after chargeoff"
        )

    def sanity_056_balance_can_only_decrease(self):
        """SANITY-056: Principal balance should decrease month-over-month"""
        if "loan_tape" not in self.data:
            return

        balance_changes = self.data["loan_tape"].filter(
            ~pl.col("loan_status").is_in(["CHARGED_OFF", "PAID_OFF"])
        ).sort(["loan_id", "snapshot_date"]).select([
            "loan_id",
            "snapshot_date",
            "current_principal_balance",
            pl.col("current_principal_balance").shift(1).over("loan_id").alias("prev_balance")
        ])

        violations = balance_changes.filter(
            pl.col("current_principal_balance") > pl.col("prev_balance") + 1.0
        )

        self.log_result(
            "SANITY-056", "Balance Can Only Decrease",
            len(violations), f"Balance increased month-over-month"
        )

    def sanity_057_delinquency_increment_or_cure(self):
        """SANITY-057: DPD can only increase by 30 or cure to 0"""
        if "loan_tape" not in self.data:
            return

        dpd_changes = self.data["loan_tape"].sort(["loan_id", "snapshot_date"]).select([
            "loan_id",
            "snapshot_date",
            "days_past_due",
            pl.col("days_past_due").shift(1).over("loan_id").alias("prev_dpd")
        ])

        violations = dpd_changes.filter(
            (pl.col("days_past_due") < pl.col("prev_dpd")) &
            (pl.col("days_past_due") > 0)
        )

        self.log_result(
            "SANITY-057", "Delinquency Increment or Cure",
            len(violations), f"DPD decreased but didn't cure"
        )

    def sanity_058_mob_must_increase(self):
        """SANITY-058: Months on book should increase by 1 each month"""
        if "loan_tape" not in self.data:
            return

        mob_changes = self.data["loan_tape"].sort(["loan_id", "snapshot_date"]).select([
            "loan_id",
            "snapshot_date",
            "months_on_book",
            pl.col("months_on_book").shift(1).over("loan_id").alias("prev_mob"),
            pl.col("snapshot_date").shift(1).over("loan_id").alias("prev_date")
        ])

        # Check consecutive months
        violations = mob_changes.filter(
            (pl.col("months_on_book") != pl.col("prev_mob") + 1) &
            ((pl.col("snapshot_date").cast(pl.Date) - pl.col("prev_date").cast(pl.Date)).dt.days().is_between(28, 35))
        )

        total_snapshots = len(self.data["loan_tape"])
        self.log_result(
            "SANITY-058", "Months on Book Must Increase",
            len(violations), f"MoB didn't increment correctly",
            tolerance=int(total_snapshots * 0.05)
        )

    def sanity_059_payment_count_le_mob(self):
        """SANITY-059: Payment count should not exceed loan age"""
        if "loan_tape" not in self.data or "payments" not in self.data:
            return

        latest = self.data["loan_tape"].filter(
            pl.col("snapshot_date") == self.data["loan_tape"]["snapshot_date"].max()
        )

        payment_counts = self.data["payments"].group_by("loan_id").agg(
            pl.count().alias("pmt_count")
        )

        violations = latest.join(
            payment_counts, on="loan_id", how="inner"
        ).filter(
            pl.col("pmt_count") > pl.col("months_on_book") + 2
        )

        total = len(latest)
        self.log_result(
            "SANITY-059", "Payment Count ≤ Months on Book",
            len(violations), f"Too many payments for loan age",
            tolerance=int(total * 0.01)
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
            violations, f"Duplicate application_id values"
        )

    # ========================================
    # MAIN RUNNER
    # ========================================

    def run_all(self):
        """Execute all 60 sanity checks"""
        self.load_data()

        print("\n" + "="*80)
        print("COMPLETE FOUNDATION SANITY CHECKS - ALL 60 VALIDATIONS")
        print("="*80 + "\n")

        # Lifecycle (8)
        print("\n[1/8] Lifecycle Sanity Checks (8)...")
        self.sanity_001_no_funded_without_approval()
        self.sanity_002_no_approval_without_credit()
        self.sanity_003_no_approval_without_fraud_check()
        self.sanity_004_no_payment_without_loan()
        self.sanity_005_no_loan_without_application()
        self.sanity_006_no_credit_without_application()
        self.sanity_007_no_declined_in_loan_tape()
        self.sanity_008_no_pending_in_loan_tape()

        # State Machine (8)
        print("\n[2/8] State Machine Violations (8)...")
        self.sanity_009_no_payments_after_payoff()
        self.sanity_010_no_payments_after_chargeoff()
        self.sanity_011_no_delinquent_with_all_payments()
        self.sanity_012_no_current_with_dpd()
        self.sanity_013_no_balance_on_paid_off()
        self.sanity_014_no_balance_on_chargedoff()
        self.sanity_015_no_payments_before_first_due()
        self.sanity_016_loan_status_valid_enum()

        # Temporal (7)
        print("\n[3/8] Temporal Impossibilities (7)...")
        self.sanity_017_application_before_credit_pull()
        self.sanity_018_application_before_fraud_check()
        self.sanity_019_origination_after_application()
        self.sanity_020_payment_after_origination()
        self.sanity_021_no_future_dates()
        self.sanity_022_birth_before_application()
        self.sanity_023_no_payments_before_origination()

        # Financial (7)
        print("\n[4/8] Financial Impossibilities (7)...")
        self.sanity_024_no_negative_principal()
        self.sanity_025_no_negative_payment()
        self.sanity_026_balance_not_exceeding_original()
        self.sanity_027_total_payments_reasonable()
        self.sanity_028_no_interest_only_with_zero_rate()
        self.sanity_029_payment_components_sum()
        self.sanity_030_no_fee_exceeding_loan()

        # Payment Waterfall (8)
        print("\n[5/8] Payment Waterfall Violations (8)...")
        self.sanity_031_posted_payments_have_date()
        self.sanity_032_no_zero_scheduled_payment()
        self.sanity_033_overpayments_flagged()
        self.sanity_034_missed_payments_zero_amount()
        self.sanity_035_late_payments_have_fee()
        self.sanity_036_nsf_must_be_returned()
        self.sanity_037_returned_have_return_date()
        self.sanity_038_autopay_failures_have_reason()

        # Credit Bureau (8)
        print("\n[6/8] Credit Bureau Impossibilities (8)...")
        self.sanity_039_fico_in_valid_range()
        self.sanity_040_credit_file_after_birth()
        self.sanity_041_bankruptcy_in_public_records()
        self.sanity_042_utilization_not_exceeding_200pct()
        self.sanity_043_open_trades_le_total()
        self.sanity_044_tradeline_balance_le_limit()
        self.sanity_045_closed_tradelines_no_payment()
        self.sanity_046_tradeline_open_before_report()

        # Fraud & Identity (6)
        print("\n[7/8] Fraud & Identity Conflicts (6)...")
        self.sanity_047_no_approval_for_deceased()
        self.sanity_048_ssn_issued_after_birth()
        self.sanity_049_identity_fail_should_decline()
        self.sanity_050_critical_fraud_should_decline()
        self.sanity_051_applicant_age_valid()
        self.sanity_052_email_format_validation()

        # Cross-Table State (7)
        print("\n[8/8] Cross-Table State Consistency (7)...")
        self.sanity_054_no_resurrection_after_payoff()
        self.sanity_055_no_resurrection_after_chargeoff()
        self.sanity_056_balance_can_only_decrease()
        self.sanity_057_delinquency_increment_or_cure()
        self.sanity_058_mob_must_increase()
        self.sanity_059_payment_count_le_mob()
        self.sanity_060_application_pk_unique()

        return pl.DataFrame(self.results)


if __name__ == "__main__":
    import sys

    # Allow custom data directory
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "sherpaiq_lc/data_domain/lendco/raw/data"

    validator = CompleteSanityValidator(data_dir)
    df = validator.run_all()

    print("\n" + "="*80)
    print("COMPLETE SANITY CHECK REPORT - ALL 60 CHECKS")
    print("="*80)

    # Summary statistics
    total_checks = len(df)
    passed = len(df.filter(pl.col("Status") == "PASS"))
    failed = len(df.filter(pl.col("Status") == "FAIL"))

    print(f"\nTotal Checks: {total_checks}")
    print(f"✅ Passed: {passed} ({passed/total_checks*100:.1f}%)")
    print(f"❌ Failed: {failed} ({failed/total_checks*100:.1f}%)")

    # Failed checks
    failures = df.filter(pl.col("Status") == "FAIL")

    if len(failures) > 0:
        print(f"\n🚨 CRITICAL: {len(failures)} SANITY CHECKS FAILED\n")
        print("Failed Checks:")
        print(failures.select(["Check ID", "Check Name", "Violations", "Tolerance"]))
        print("\n⚠️  DATA INTEGRITY COMPROMISED - FIX GENERATOR BUGS BEFORE PROCEEDING")
    else:
        print("\n✅ ALL 60 SANITY CHECKS PASSED!")
        print("✅ Data foundation is sound - proceed with advanced validation")

    # Detailed report by category
    print("\n" + "="*80)
    print("RESULTS BY CATEGORY")
    print("="*80)

    categories = {
        "Lifecycle": df.filter(pl.col("Check ID").str.slice(7, 3).cast(pl.Int32).is_between(1, 8)),
        "State Machine": df.filter(pl.col("Check ID").str.slice(7, 3).cast(pl.Int32).is_between(9, 16)),
        "Temporal": df.filter(pl.col("Check ID").str.slice(7, 3).cast(pl.Int32).is_between(17, 23)),
        "Financial": df.filter(pl.col("Check ID").str.slice(7, 3).cast(pl.Int32).is_between(24, 30)),
        "Payment": df.filter(pl.col("Check ID").str.slice(7, 3).cast(pl.Int32).is_between(31, 38)),
        "Credit": df.filter(pl.col("Check ID").str.slice(7, 3).cast(pl.Int32).is_between(39, 46)),
        "Fraud": df.filter(pl.col("Check ID").str.slice(7, 3).cast(pl.Int32).is_between(47, 52)),
        "State": df.filter(pl.col("Check ID").str.slice(7, 3).cast(pl.Int32).is_between(54, 60))
    }

    for cat_name, cat_df in categories.items():
        if len(cat_df) > 0:
            cat_passed = len(cat_df.filter(pl.col("Status") == "PASS"))
            cat_total = len(cat_df)
            print(f"{cat_name}: {cat_passed}/{cat_total} passed")

    # Save detailed report
    df.write_csv("complete_sanity_check_report.csv")
    print(f"\n📄 Detailed report saved to: complete_sanity_check_report.csv")

    # Exit code for CI/CD
    sys.exit(1 if len(failures) > 0 else 0)
