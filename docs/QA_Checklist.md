# LendCo Synthetic Data - QA Checklist
**Quick Reference for Data Quality Review**

---

## Pre-Flight Checks (Run These First)

- [ ] **Data exists**: Verify all 8 parquet files in `sherpaiq_lc/data_domain/lendco/raw/data/`
  ```bash
  ls -lh sherpaiq_lc/data_domain/lendco/raw/data/*.parquet
  ```

- [ ] **Row counts match expectations**:
  ```python
  import polars as pl
  apps = pl.read_parquet("sherpaiq_lc/data_domain/lendco/raw/data/applications.parquet")
  print(f"Applications: {len(apps):,}")  # Expect 1,000,000
  ```

- [ ] **Run existing validation**:
  ```bash
  python src/validation_framework.py
  ```

- [ ] **Run extended validation**:
  ```bash
  python extended_validation_suite.py
  ```

---

## Critical Validation Checklist (Must Pass)

### Referential Integrity
- [ ] INT-001: All `application_id` are unique in applications table
- [ ] INT-002: All `loan_tape.application_id` exist in `applications`
- [ ] INT-003: All `credit_reports.application_id` exist in `applications`
- [ ] INT-004: All `payments.loan_id` exist in `loan_tape`
- [ ] INT-005: All `credit_tradelines.credit_report_id` exist in `credit_reports`
- [ ] INT-006: Each application has exactly 1 fraud verification record
- [ ] INT-008: `customer_id` is consistent across applications, loan_tape, payments

**Expected Result:** 0 violations for all checks

---

### Temporal Consistency
- [ ] TMP-001: All `loan_tape.origination_date >= applications.application_date`
- [ ] TMP-002: All `loan_tape.note_signature_date <= origination_date`
- [ ] TMP-003: All `loan_tape.first_payment_due_date > origination_date`
- [ ] TMP-007: All `credit_reports.file_since_date >= applications.date_of_birth`
- [ ] TMP-010: All `loan_tape.vintage_month` matches `origination_date` (YYYY-MM)

**Expected Result:** 0 violations for all checks

---

### Financial Mathematics
- [ ] FIN-001: All `loan_tape.current_principal_balance <= original_loan_amount`
- [ ] FIN-002: All `payments.principal_paid + interest_paid = actual_payment_amount` (±$0.01)
- [ ] FIN-003: Scheduled payment matches amortization formula (±$1.00)
- [ ] FIN-005: All `payments.ending_principal_balance = beginning_balance - principal_paid` (±$0.10)
- [ ] FIN-006: All `loan_tape.original_apr >= original_interest_rate` (APR should be higher)
- [ ] FIN-007: All `loan_tape.origination_fee <= original_loan_amount * 0.06` (max 6%)

**Expected Result:** <1% violations for FIN-003, 0 for others

---

### Business Rules
- [ ] POL-001: No APPROVED applications with `fico_score_at_application < 640`
- [ ] POL-002: No APPROVED applications with `debt_to_income_ratio > 0.50`
- [ ] POL-003: Only APPROVED applications appear in `loan_tape`
- [ ] POL-005: All `loan_tape.original_apr` between 0.05 and 0.36
- [ ] POL-009: All applicants are 18+ years old at `application_date`
- [ ] POL-010: All `loan_tape.chargeoff_flag = 1` only when `days_past_due >= 120`

**Expected Result:** 0 violations for all checks

---

### Cross-Column Logic
- [ ] LOG-002: `loan_tape.delinquent_flag = TRUE` ↔ `days_past_due > 0`
- [ ] LOG-003: `credit_reports.revolving_trades_count <= total_trades`
- [ ] LOG-005: `loan_tape.worst_days_past_due >= days_past_due` for all loans
- [ ] LOG-006: `loan_tape.times_60_dpd <= times_30_dpd` (can't skip 30 DPD)
- [ ] LOG-008: `|applications.fico - credit_reports.fico_score_8| <= 20` points

**Expected Result:** 0 violations for all checks

---

### Data Quality
- [ ] DQ-001: All `fico_score_at_application` between 300 and 850
- [ ] DQ-002: All `annual_income > 0`
- [ ] DQ-003: All 955 schema columns exist in parquet files
- [ ] DQ-005: All `ssn_last4` are 4 digits and != "0000"
- [ ] DQ-008: All `address_zip` are 5 digits and != "00000"
- [ ] DQ-011: No negative balances in `loan_tape` (principal, interest, fees)

**Expected Result:** 0 violations for all checks

---

## Statistical Realism Checklist (Informational)

### Portfolio-Level Metrics
- [ ] **Approval Rate**: 60-80%
  ```python
  apps["decision_status"].value_counts(normalize=True)
  # APPROVED should be 60-80%
  ```

- [ ] **Chargeoff Rate** (for loans 12+ months old): 3-10%
  ```python
  mature = loan_tape.filter(pl.col("months_on_book") >= 12)
  co_rate = mature["chargeoff_flag"].sum() / len(mature)
  # Should be 3-10%
  ```

- [ ] **Delinquency Rate** (current 30+ DPD): 2-8%
  ```python
  loan_tape.filter(pl.col("days_past_due") >= 30).height / loan_tape.height
  # Should be 2-8%
  ```

### Distribution Checks
- [ ] **FICO Distribution**: Bell curve peaking at 680-720
  ```python
  apps["fico_score_at_application"].hist()
  # Should NOT be uniform
  ```

- [ ] **DTI Distribution**: Mean 25-35%, few outliers >45%
  ```python
  apps.filter(pl.col("decision_status") == "APPROVED")["debt_to_income_ratio"].describe()
  ```

- [ ] **Income Distribution**: Median $40K-$70K, varies by state
  ```python
  apps.group_by("address_state").agg(pl.median("annual_income"))
  ```

### Correlation Checks
- [ ] **FICO vs Inquiries**: Negative correlation (more inq → lower FICO)
  ```python
  credit_reports.group_by("inquiries_6mo_count").agg(pl.mean("fico_score_8"))
  # Should decrease as inquiries increase
  ```

- [ ] **FICO vs Utilization**: Negative correlation (higher util → lower FICO)
  ```python
  credit_reports.group_by(pl.col("revolving_utilization_ratio").cut([0, 0.3, 0.5, 0.7, 1.0]))
      .agg(pl.mean("fico_score_8"))
  ```

---

## Hydration Quality Checklist

### Realistic Variability
- [ ] **Autopay Rate**: 60-80% (not 100%)
  ```python
  payments["autopay_flag"].value_counts(normalize=True)
  ```

- [ ] **NSF Rate**: 1-3% (not 0%)
  ```python
  (payments["nsf_flag"] | payments["returned_flag"]).sum() / len(payments)
  ```

- [ ] **Payment Channel Mix**: Not all "WEB"
  ```python
  payments["payment_channel"].value_counts()
  # Should have WEB, MOBILE, PHONE, AUTOPAY
  ```

- [ ] **Credit Bureau Mix**: Not all "TU"
  ```python
  credit_reports["bureau_code"].value_counts()
  # Should have EXP, EFX, TU
  ```

### Correlation with Performance
- [ ] **Delinquency Counts**: Correlated with `loan_status`
  ```python
  # Delinquent loans should have non-zero delinquency_30_day_count
  loan_tape.filter(pl.col("loan_status").str.contains("DELINQUENT"))
      .filter(pl.col("delinquency_30_day_count") == 0)
  # Should be <10% of delinquent loans
  ```

- [ ] **Months Since Delinquency**: Populated for cured loans
  ```python
  # CURRENT loans with delinquency history should have months_since populated
  loan_tape.filter(
      (pl.col("loan_status") == "CURRENT") &
      (pl.col("times_30_dpd") > 0) &
      (pl.col("months_since_last_delinquency").is_null())
  )
  # Should be 0 or very few
  ```

---

## Edge Case Validation

### Boundary Conditions
- [ ] **Date Ranges**: No future dates, no dates before 1900
- [ ] **FICO Extremes**: Very few scores <500 or >800
- [ ] **Age Extremes**: No applicants >100 years old
- [ ] **Income Extremes**: Few incomes >$500K
- [ ] **Loan Amount Extremes**: Check min/max by product type

### Null Patterns
- [ ] **Critical Fields**: 0% null
  - `application_id`, `loan_id`, `payment_id`
  - `origination_date`, `application_date`
  - `fico_score_at_application`

- [ ] **Optional Fields**: <90% null (else why include?)
  - `middle_name`, `name_suffix` (expect 50-70% null)
  - `previous_address_*` (expect 60-70% null)
  - `phone_secondary` (expect 80-90% null)

- [ ] **Derived Fields**: Should never be null if source exists
  - `vintage_month` (derived from `origination_date`)
  - `months_on_book` (derived from dates)

---

## Performance Benchmarks

- [ ] **Validation Runtime**: <5 minutes for 1M rows
- [ ] **Data Load Time**: <30 seconds for all tables
- [ ] **Query Performance**: Simple aggregations <1 second

---

## Sign-Off Criteria

### Minimum Requirements (MUST PASS)
- ✅ All CRITICAL severity checks pass (0 violations)
- ✅ <1% violations on HIGH severity checks
- ✅ No orphan records (referential integrity)
- ✅ No temporal logic violations
- ✅ No negative balances

### Quality Requirements (SHOULD PASS)
- ✅ Statistical distributions match industry norms (±10%)
- ✅ Correlations align with real-world patterns
- ✅ Hydration defaults show realistic variability
- ✅ <5% violations on MEDIUM severity checks

### Documentation Requirements
- ✅ All validation results saved to CSV
- ✅ Summary report generated
- ✅ Known issues documented with severity/risk
- ✅ Edge cases explained (if intentional)

---

## Quick Commands Reference

### Run Full Validation
```bash
# Original validation (12 checks)
python src/validation_framework.py

# Extended validation (35+ checks)
python extended_validation_suite.py

# View results
cat extended_validation_report.csv | grep "FAIL"
```

### Spot Check Specific Tables
```python
import polars as pl

# Check applications
apps = pl.read_parquet("sherpaiq_lc/data_domain/lendco/raw/data/applications.parquet")
print(f"Apps: {len(apps):,} rows, {len(apps.columns)} columns")
print(apps["decision_status"].value_counts())

# Check loan_tape
loans = pl.read_parquet("sherpaiq_lc/data_domain/lendco/raw/data/loan_tape.parquet")
print(f"Loans: {len(loans):,} rows")
print(loans["loan_status"].value_counts())

# Check payments
pmts = pl.read_parquet("sherpaiq_lc/data_domain/lendco/raw/data/payments.parquet")
print(f"Payments: {len(pmts):,} rows")
print(f"Autopay %: {pmts['autopay_flag'].sum() / len(pmts) * 100:.1f}%")
```

### Generate Quick Stats
```python
# FICO distribution
apps["fico_score_at_application"].describe()

# Loan status distribution
loans["loan_status"].value_counts()

# Delinquency rate by vintage
loans.filter(pl.col("months_on_book") >= 12).group_by("vintage_year").agg([
    (pl.col("chargeoff_flag").sum() / pl.count()).alias("co_rate")
])
```

---

## Troubleshooting Common Issues

### "Column not found" errors
- **Cause**: Hydration didn't add all expected columns
- **Fix**: Check `data_generator.py` line 593-676, ensure schema CSV exists

### High violation counts on FK checks
- **Cause**: Tables generated in different runs with different seeds
- **Fix**: Regenerate all tables in single pipeline run

### Unrealistic distributions (e.g., all FICO=720)
- **Cause**: Random seed not set or correlation logic broken
- **Fix**: Check `reference_generator.py` for seed setting

### Validation script crashes on large dataset
- **Cause**: Memory exhaustion with 1M rows
- **Fix**: Use `scan_parquet()` for lazy evaluation or sample 10%

---

**Last Updated:** 2026-01-08
**Version:** 1.0
**Purpose:** Quick reference for QA review process
