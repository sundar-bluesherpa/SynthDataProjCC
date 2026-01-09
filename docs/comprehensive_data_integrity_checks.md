# Comprehensive Data Integrity & Consistency Checks
## LendCo Synthetic Data - Deep QA Framework

**Generated:** 2026-01-08
**Scope:** 955 columns across 8 tables, 1M rows
**Purpose:** Expand beyond the initial 12 checks to ensure realistic, production-grade synthetic data

---

## Executive Summary

This document provides **75+ comprehensive integrity checks** organized into 8 categories:
1. **Referential Integrity** (Cross-table FK relationships)
2. **Business Rule Validation** (Lending policies & regulations)
3. **Temporal Consistency** (Date/time logic)
4. **Financial Mathematics** (Calculations & amortization)
5. **Cross-Column Logic** (Within-table dependencies)
6. **Statistical Realism** (Distributions & correlations)
7. **Data Quality** (Nulls, ranges, formats)
8. **Hydration Heuristics Audit** (Schema completeness & defaults)

**Current Coverage:** 12 checks
**Recommended Coverage:** 75+ checks
**Critical Gaps:** Temporal logic, credit bureau correlations, payment waterfall, fraud consistency

---

## TABLE OF CONTENTS

1. [Referential Integrity Checks](#1-referential-integrity-checks) (INT-xxx)
2. [Business Rule Validation](#2-business-rule-validation) (POL-xxx)
3. [Temporal Consistency](#3-temporal-consistency) (TMP-xxx)
4. [Financial Mathematics](#4-financial-mathematics) (FIN-xxx)
5. [Cross-Column Logic](#5-cross-column-logic) (LOG-xxx)
6. [Statistical Realism](#6-statistical-realism) (STAT-xxx)
7. [Data Quality](#7-data-quality) (DQ-xxx)
8. [Hydration Heuristics Audit](#8-hydration-heuristics-audit) (HYD-xxx)

---

## 1. REFERENTIAL INTEGRITY CHECKS

### INT-001: Primary Key Uniqueness (EXISTING ✓)
**Status:** Already implemented
**Tables:** applications, loan_tape (composite key check)

### INT-002: Foreign Key Coverage (EXISTING ✓)
**Status:** Already implemented
**Relationship:** loan_tape.application_id → applications.application_id

### INT-003: Credit Reports → Applications
**Query:**
```sql
SELECT COUNT(*) as orphan_count
FROM credit_reports cr
LEFT JOIN applications a ON cr.application_id = a.application_id
WHERE a.application_id IS NULL
```
**Expected:** 0 orphans
**Severity:** CRITICAL

### INT-004: Payments → Loan Tape
**Query:**
```sql
SELECT COUNT(*) as orphan_count
FROM payments p
LEFT JOIN loan_tape lt ON p.loan_id = lt.loan_id
WHERE lt.loan_id IS NULL
```
**Expected:** 0 orphans
**Severity:** CRITICAL

### INT-005: Tradelines → Credit Reports
**Query:**
```sql
SELECT COUNT(*) as orphan_count
FROM credit_tradelines ct
LEFT JOIN credit_reports cr ON ct.credit_report_id = cr.credit_report_id
WHERE cr.credit_report_id IS NULL
```
**Expected:** 0 orphans
**Severity:** CRITICAL

### INT-006: Fraud Verification → Applications (1:1)
**Query:**
```sql
-- Every application should have exactly 1 fraud record
WITH fraud_counts AS (
  SELECT application_id, COUNT(*) as cnt
  FROM fraud_verification
  GROUP BY application_id
)
SELECT COUNT(*) as violations
FROM applications a
LEFT JOIN fraud_counts fc ON a.application_id = fc.application_id
WHERE fc.cnt != 1 OR fc.cnt IS NULL
```
**Expected:** 0 violations
**Severity:** HIGH

### INT-007: Bank Transactions → Applications
**Query:**
```sql
SELECT COUNT(*) as orphan_count
FROM bank_transactions bt
LEFT JOIN applications a ON bt.application_id = a.application_id
WHERE a.application_id IS NULL
```
**Expected:** 0 orphans
**Severity:** MEDIUM

### INT-008: Customer ID Consistency
**Query:**
```sql
-- customer_id should be consistent across applications, loan_tape, payments
SELECT a.application_id,
       a.customer_id as app_cust,
       lt.customer_id as loan_cust,
       p.customer_id as pmt_cust
FROM applications a
JOIN loan_tape lt ON a.application_id = lt.application_id
JOIN payments p ON lt.loan_id = p.loan_id
WHERE a.customer_id != lt.customer_id
   OR a.customer_id != p.customer_id
   OR lt.customer_id != p.customer_id
```
**Expected:** 0 mismatches
**Severity:** HIGH

---

## 2. BUSINESS RULE VALIDATION

### POL-001: FICO Floor Compliance (EXISTING ✓)
**Status:** Already implemented
**Rule:** No APPROVED apps with FICO < 640

### POL-002: DTI Ceiling (NEW)
**Rule:** No APPROVED apps with DTI > 50%
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE decision_status = 'APPROVED'
  AND debt_to_income_ratio > 0.50
```
**Expected:** 0 (or <1% if lender allows exceptions)
**Severity:** HIGH

### POL-003: Funding Policy (EXISTING ✓)
**Status:** Already implemented
**Rule:** Only APPROVED apps in loan_tape

### POL-004: Loan Amount Limits
**Rule:** Personal loans $1K-$50K, Auto loans $5K-$100K
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN loan_tape lt ON a.application_id = lt.application_id
WHERE (a.product_type = 'PERSONAL' AND (lt.original_loan_amount < 1000 OR lt.original_loan_amount > 50000))
   OR (a.product_type = 'AUTO' AND (lt.original_loan_amount < 5000 OR lt.original_loan_amount > 100000))
```
**Expected:** 0 violations
**Severity:** MEDIUM

### POL-005: Interest Rate Ranges
**Rule:** APR between 5% and 36% (state-dependent)
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE original_apr < 0.05 OR original_apr > 0.36
```
**Expected:** 0 violations
**Severity:** HIGH

### POL-006: Term Constraints
**Rule:** Personal loans: 12, 24, 36, 48, 60 months
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape lt
JOIN applications a ON lt.application_id = a.application_id
WHERE a.product_type = 'PERSONAL'
  AND original_term_months NOT IN (12, 24, 36, 48, 60)
```
**Expected:** 0 violations
**Severity:** MEDIUM

### POL-007: Income Verification Threshold
**Rule:** Loans >$25K require stated income >$40K
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN loan_tape lt ON a.application_id = lt.application_id
WHERE lt.original_loan_amount > 25000
  AND a.annual_income < 40000
  AND a.decision_status = 'APPROVED'
```
**Expected:** <5% (allowing some exceptions)
**Severity:** MEDIUM

### POL-008: Credit Report Freshness
**Rule:** Credit reports must be pulled within 30 days of application
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN credit_reports cr ON a.application_id = cr.application_id
WHERE ABS(DATEDIFF(a.application_date, cr.report_date)) > 30
```
**Expected:** <1%
**Severity:** MEDIUM

### POL-009: Minimum Age Requirement
**Rule:** Applicants must be 18+ years old at application
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE DATEDIFF(application_date, date_of_birth) / 365.25 < 18
```
**Expected:** 0 violations
**Severity:** CRITICAL

### POL-010: Chargeoff Timing
**Rule:** Chargeoffs occur at 120+ DPD (4 consecutive missed payments)
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE loan_status = 'CHARGED_OFF'
  AND days_past_due < 120
```
**Expected:** 0 violations
**Severity:** HIGH

---

## 3. TEMPORAL CONSISTENCY

### TMP-001: Application Before Origination
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN loan_tape lt ON a.application_id = lt.application_id
WHERE lt.origination_date < a.application_date
```
**Expected:** 0 violations
**Severity:** CRITICAL

### TMP-002: Note Signature Before Origination
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE note_signature_date > origination_date
```
**Expected:** 0 violations
**Severity:** HIGH

### TMP-003: First Payment After Origination
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE first_payment_due_date <= origination_date
```
**Expected:** 0 violations (typically 30+ days gap)
**Severity:** HIGH

### TMP-004: Maturity Date Logic
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE DATEDIFF(maturity_date, first_payment_due_date) / 30.44 != original_term_months - 1
  -- Allow 5-day tolerance for month-end adjustments
  AND ABS(DATEDIFF(maturity_date, first_payment_due_date) - (original_term_months - 1) * 30.44) > 5
```
**Expected:** <1%
**Severity:** MEDIUM

### TMP-005: Payment Received Before Due Date (Early Payments)
**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE payment_received_date < payment_due_date
  AND DATEDIFF(payment_due_date, payment_received_date) > 30
  -- Flag only if >30 days early (unrealistic)
```
**Expected:** <0.1%
**Severity:** LOW

### TMP-006: Snapshot Date Progression
**Query:**
```sql
WITH snapshot_gaps AS (
  SELECT loan_id,
         snapshot_date,
         LAG(snapshot_date) OVER (PARTITION BY loan_id ORDER BY snapshot_date) as prev_snapshot,
         DATEDIFF(snapshot_date, LAG(snapshot_date) OVER (PARTITION BY loan_id ORDER BY snapshot_date)) as gap_days
  FROM loan_tape
)
SELECT COUNT(*) as violations
FROM snapshot_gaps
WHERE gap_days > 35 OR gap_days < 25
  -- Snapshots should be roughly monthly (28-32 days)
```
**Expected:** <5%
**Severity:** MEDIUM

### TMP-007: Credit File Establishment Before DOB
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN credit_reports cr ON a.application_id = cr.application_id
WHERE cr.file_since_date < a.date_of_birth
```
**Expected:** 0 violations
**Severity:** CRITICAL

### TMP-008: Months Since Last Delinquency vs Current Status
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE months_since_last_delinquency = 0
  AND loan_status = 'CURRENT'
  -- If months_since = 0, loan should be DELINQUENT
```
**Expected:** 0 violations
**Severity:** HIGH

### TMP-009: Tradeline Open Date Realism
**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_tradelines ct
JOIN credit_reports cr ON ct.credit_report_id = cr.credit_report_id
JOIN applications a ON cr.application_id = a.application_id
WHERE ct.open_date > cr.report_date
  OR DATEDIFF(cr.report_date, ct.open_date) / 365.25 > 50
  -- Tradelines shouldn't be future-dated or >50 years old
```
**Expected:** 0 violations
**Severity:** MEDIUM

### TMP-010: Vintage Consistency
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE vintage_month != DATE_FORMAT(origination_date, '%Y-%m')
   OR vintage_year != YEAR(origination_date)
```
**Expected:** 0 violations
**Severity:** MEDIUM

---

## 4. FINANCIAL MATHEMATICS

### FIN-001: Balance Cap (EXISTING ✓)
**Status:** Already implemented
**Rule:** Current balance ≤ Original amount

### FIN-002: Payment Component Sum (EXISTING ✓)
**Status:** Already implemented
**Rule:** Principal + Interest = Total Payment

### FIN-003: Amortization Schedule Accuracy
**Query:**
```sql
-- Check if scheduled payments actually amortize loan over term
-- PMT = P * [r(1+r)^n] / [(1+r)^n - 1]
SELECT COUNT(*) as violations
FROM loan_tape
WHERE ABS(
    original_installment_amount -
    (original_loan_amount * (original_interest_rate/12 * POW(1 + original_interest_rate/12, original_term_months)) /
     (POW(1 + original_interest_rate/12, original_term_months) - 1))
  ) > 1.0
  -- Allow $1 rounding tolerance
```
**Expected:** <1%
**Severity:** MEDIUM

### FIN-004: Interest Accrual Logic
**Query:**
```sql
-- Verify interest_paid ≈ beginning_balance * monthly_rate
SELECT COUNT(*) as violations
FROM payments p
JOIN loan_tape lt ON p.loan_id = lt.loan_id AND DATE_FORMAT(p.payment_due_date, '%Y-%m') = lt.vintage_month
WHERE p.payment_status = 'POSTED'
  AND ABS(p.interest_paid - (p.beginning_principal_balance * lt.original_interest_rate / 12)) > 5.0
```
**Expected:** <5%
**Severity:** MEDIUM

### FIN-005: Principal Paydown Consistency
**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE ending_principal_balance != beginning_principal_balance - principal_paid
  AND ABS(ending_principal_balance - (beginning_principal_balance - principal_paid)) > 0.10
```
**Expected:** 0 violations
**Severity:** HIGH

### FIN-006: APR vs Interest Rate Delta
**Query:**
```sql
-- APR should be slightly higher than interest rate (includes fees)
SELECT COUNT(*) as violations
FROM loan_tape
WHERE original_apr < original_interest_rate
   OR (original_apr - original_interest_rate) > 0.05
   -- APR shouldn't exceed rate by more than 5%
```
**Expected:** <1%
**Severity:** MEDIUM

### FIN-007: Origination Fee Reasonableness
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE origination_fee > original_loan_amount * 0.06
  -- Fees >6% of loan amount are unrealistic/usurious
```
**Expected:** 0 violations
**Severity:** HIGH

### FIN-008: Disbursed Amount Logic
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE ABS(disbursed_amount - (original_loan_amount - origination_fee)) > 1.0
  -- Disbursed = Loan Amount - Fees (if fees deducted upfront)
```
**Expected:** <10% (some lenders capitalize fees)
**Severity:** LOW

### FIN-009: Payoff Amount Calculation
**Query:**
```sql
-- Payoff ≈ Current Principal + Accrued Interest + Fees
SELECT COUNT(*) as violations
FROM loan_tape
WHERE payoff_amount > 0
  AND ABS(payoff_amount - (current_principal_balance + current_interest_balance + current_fees_balance)) > 10.0
```
**Expected:** <5%
**Severity:** MEDIUM

### FIN-010: Balance Progression (Non-Negative)
**Query:**
```sql
WITH balance_changes AS (
  SELECT loan_id,
         snapshot_date,
         current_principal_balance,
         LAG(current_principal_balance) OVER (PARTITION BY loan_id ORDER BY snapshot_date) as prev_balance
  FROM loan_tape
)
SELECT COUNT(*) as violations
FROM balance_changes
WHERE loan_status NOT IN ('CHARGED_OFF', 'PAID_OFF')
  AND current_principal_balance > prev_balance
  -- Balance should decrease or stay flat, never increase (no neg-am)
```
**Expected:** <1%
**Severity:** HIGH

---

## 5. CROSS-COLUMN LOGIC

### LOG-001: Status/DPD Alignment (EXISTING ✓)
**Status:** Already implemented
**Rules:**
- CURRENT → DPD = 0
- DELINQUENT_30 → DPD ≥ 30

### LOG-002: Delinquency Flag Consistency
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE (delinquent_flag = TRUE AND days_past_due = 0)
   OR (delinquent_flag = FALSE AND days_past_due > 0)
```
**Expected:** 0 violations
**Severity:** HIGH

### LOG-003: Trade Count Consistency (EXISTING ✓)
**Status:** Already implemented
**Rule:** Revolving trades ≤ Total trades

### LOG-004: Delinquency Bucket Flags
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE (delinquent_0_30_flag = TRUE AND (days_past_due < 1 OR days_past_due > 30))
   OR (delinquent_31_60_flag = TRUE AND (days_past_due < 31 OR days_past_due > 60))
   OR (delinquent_61_90_flag = TRUE AND (days_past_due < 61 OR days_past_due > 90))
   OR (delinquent_91_120_flag = TRUE AND (days_past_due < 91 OR days_past_due > 120))
```
**Expected:** 0 violations
**Severity:** HIGH

### LOG-005: Worst Delinquency Logic
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE worst_days_past_due < days_past_due
  -- Worst DPD should always be >= current DPD
```
**Expected:** 0 violations
**Severity:** HIGH

### LOG-006: Times 30/60/90 DPD Progression
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE times_60_dpd > times_30_dpd
   OR times_90_dpd > times_60_dpd
   OR times_120_dpd > times_90_dpd
  -- Can't be 60 DPD without first being 30 DPD
```
**Expected:** 0 violations
**Severity:** HIGH

### LOG-007: Payment History String Consistency
**Query:**
```sql
-- loan_payment_history should reflect times_30_dpd count
SELECT COUNT(*) as violations
FROM loan_tape
WHERE LENGTH(loan_payment_history) > 0
  AND times_30_dpd != (LENGTH(loan_payment_history) - LENGTH(REPLACE(loan_payment_history, '01', ''))) / 2
  -- Count '01' occurrences in payment string
```
**Expected:** <10% (simplified check)
**Severity:** MEDIUM

### LOG-008: FICO Score Alignment
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN credit_reports cr ON a.application_id = cr.application_id
WHERE ABS(a.fico_score_at_application - cr.fico_score_8) > 20
  -- Scores should match within 20 points (same pull)
```
**Expected:** <5%
**Severity:** MEDIUM

### LOG-009: Credit Utilization Logic
**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_reports
WHERE revolving_utilization_ratio > 1.5
   OR revolving_utilization_ratio < 0
  -- Utilization >150% or negative is unrealistic
```
**Expected:** <1%
**Severity:** MEDIUM

### LOG-010: Trade Type vs Count
**Query:**
```sql
-- Sum of specific trade types should ≈ all_trades_count
SELECT COUNT(*) as violations
FROM credit_reports
WHERE ABS(all_trades_count - (revolving_trades_count + installment_trades_count + mortgage_trades_count)) > 3
  -- Allow small variance for "other" trade types
```
**Expected:** <10%
**Severity:** LOW

### LOG-011: Public Records & FICO Correlation
**Query:**
```sql
-- Applicants with bankruptcies should have lower FICO scores
SELECT COUNT(*) as violations
FROM credit_reports
WHERE bankruptcies_count > 0
  AND fico_score_8 > 650
  -- Bankruptcy typically drops FICO below 650
```
**Expected:** <5%
**Severity:** MEDIUM

### LOG-012: Months on Book Calculation
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE months_on_book != PERIOD_DIFF(
    DATE_FORMAT(snapshot_date, '%Y%m'),
    DATE_FORMAT(origination_date, '%Y%m')
  )
```
**Expected:** 0 violations
**Severity:** MEDIUM

### LOG-013: Never Paid Flag Logic
**Query:**
```sql
-- never_paid_flag should only be TRUE if no successful payments exist
SELECT COUNT(*) as violations
FROM loan_tape lt
WHERE lt.never_paid_flag = TRUE
  AND EXISTS (
    SELECT 1 FROM payments p
    WHERE p.loan_id = lt.loan_id
      AND p.payment_status = 'POSTED'
      AND p.actual_payment_amount > 0
  )
```
**Expected:** 0 violations
**Severity:** HIGH

### LOG-014: Address Consistency (Applications vs Fraud)
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN fraud_verification fv ON a.application_id = fv.application_id
WHERE (a.address_zip != fv.address_verified AND fv.address_verified = FALSE)
  -- If address failed verification, flag it
```
**Expected:** Informational (depends on fraud rules)
**Severity:** LOW

### LOG-015: SSN Issuance vs DOB
**Query:**
```sql
-- SSN should be issued after birth (or within reasonable newborn window)
SELECT COUNT(*) as violations
FROM applications a
JOIN fraud_verification fv ON a.application_id = fv.application_id
WHERE fv.ssn_issued_start_year < YEAR(a.date_of_birth)
```
**Expected:** <1% (some legacy SSN data may predate DOB due to errors)
**Severity:** MEDIUM

---

## 6. STATISTICAL REALISM

### STAT-001: FICO Distribution Shape
**Query:**
```sql
-- Check if FICO follows realistic distribution (not uniform)
SELECT
  FLOOR(fico_score_at_application / 50) * 50 as bucket,
  COUNT(*) as count
FROM applications
GROUP BY bucket
ORDER BY bucket
-- Manual review: Should show bell curve peaking at 680-720
```
**Expected:** Bell curve, mean ≈ 680-720
**Severity:** LOW (visual check)

### STAT-002: Approval Rate Realism
**Query:**
```sql
SELECT
  decision_status,
  COUNT(*) * 100.0 / (SELECT COUNT(*) FROM applications) as pct
FROM applications
GROUP BY decision_status
```
**Expected:** 60-80% approval rate for consumer lending
**Severity:** LOW

### STAT-003: Delinquency Rate Progression
**Query:**
```sql
-- Check roll rates: 30→60 should be 30-50%, 60→90 should be 50-70%
WITH status_counts AS (
  SELECT
    vintage_month,
    COUNT(*) FILTER (WHERE loan_status = 'DELINQUENT_30') as count_30,
    COUNT(*) FILTER (WHERE loan_status = 'DELINQUENT_60') as count_60,
    COUNT(*) FILTER (WHERE loan_status = 'DELINQUENT_90') as count_90
  FROM loan_tape
  GROUP BY vintage_month
)
SELECT vintage_month,
       count_60 * 100.0 / NULLIF(count_30, 0) as roll_30_to_60
FROM status_counts
WHERE count_30 > 100
-- Expect roll rate between 20-50%
```
**Expected:** 20-50% roll rate
**Severity:** MEDIUM

### STAT-004: Chargeoff Rate by Vintage
**Query:**
```sql
SELECT
  vintage_year,
  SUM(chargeoff_flag) * 100.0 / COUNT(*) as chargeoff_rate
FROM loan_tape
WHERE months_on_book >= 12
GROUP BY vintage_year
```
**Expected:** 3-10% cumulative chargeoff rate for personal loans
**Severity:** MEDIUM

### STAT-005: DTI Distribution
**Query:**
```sql
SELECT
  FLOOR(debt_to_income_ratio * 10) * 10 as dti_bucket,
  COUNT(*) as count
FROM applications
WHERE decision_status = 'APPROVED'
GROUP BY dti_bucket
ORDER BY dti_bucket
```
**Expected:** Mean DTI ≈ 20-35%, few outliers >45%
**Severity:** LOW

### STAT-006: Income Distribution by State
**Query:**
```sql
SELECT
  address_state,
  AVG(annual_income) as avg_income,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY annual_income) as median_income
FROM applications
GROUP BY address_state
-- Compare to US Census data: CA/NY should have higher median than MS/AR
```
**Expected:** State-level variance aligns with real demographics
**Severity:** LOW

### STAT-007: Inquiries vs FICO Correlation
**Query:**
```sql
SELECT
  CASE
    WHEN inquiries_6mo_count = 0 THEN '0'
    WHEN inquiries_6mo_count BETWEEN 1 AND 2 THEN '1-2'
    WHEN inquiries_6mo_count BETWEEN 3 AND 5 THEN '3-5'
    ELSE '6+'
  END as inq_bucket,
  AVG(fico_score_8) as avg_fico
FROM credit_reports
GROUP BY inq_bucket
ORDER BY inq_bucket
```
**Expected:** Negative correlation (more inquiries → lower FICO)
**Severity:** MEDIUM

### STAT-008: Utilization vs FICO Correlation
**Query:**
```sql
SELECT
  FLOOR(revolving_utilization_ratio * 10) * 10 as util_bucket,
  AVG(fico_score_8) as avg_fico
FROM credit_reports
GROUP BY util_bucket
ORDER BY util_bucket
```
**Expected:** Negative correlation (higher util → lower FICO)
**Severity:** MEDIUM

### STAT-009: Prepayment Rate Curve
**Query:**
```sql
-- CPR (Conditional Prepayment Rate) should show S-curve
SELECT
  months_on_book,
  COUNT(*) FILTER (WHERE loan_status = 'PAID_OFF') * 100.0 / COUNT(*) as prepay_rate
FROM loan_tape
WHERE loan_status IN ('CURRENT', 'PAID_OFF')
GROUP BY months_on_book
ORDER BY months_on_book
```
**Expected:** CPR increases over time, peaks at 12-24 months
**Severity:** LOW

### STAT-010: Grade Distribution
**Query:**
```sql
SELECT grade, COUNT(*) * 100.0 / (SELECT COUNT(*) FROM loan_tape) as pct
FROM loan_tape
GROUP BY grade
ORDER BY grade
```
**Expected:** Bell curve centered on B-C grades
**Severity:** LOW

---

## 7. DATA QUALITY

### DQ-001: FICO Validity (EXISTING ✓)
**Status:** Already implemented
**Range:** 300-850

### DQ-002: Income Validity (EXISTING ✓)
**Status:** Already implemented
**Range:** >0

### DQ-003: Schema Exhaustiveness (EXISTING ✓)
**Status:** Already implemented
**Coverage:** All 955 columns present

### DQ-004: Null Rate Analysis
**Query (per table):**
```sql
-- Example for applications table
SELECT
  COUNT(*) FILTER (WHERE email_address IS NULL) * 100.0 / COUNT(*) as email_null_pct,
  COUNT(*) FILTER (WHERE phone_primary IS NULL) * 100.0 / COUNT(*) as phone_null_pct,
  COUNT(*) FILTER (WHERE ssn_hash IS NULL) * 100.0 / COUNT(*) as ssn_null_pct
FROM applications
```
**Expected:**
- Critical fields (PK, FK, dates) → 0% null
- Optional fields (middle_name, phone_secondary) → <90% null
**Severity:** MEDIUM

### DQ-005: SSN Last 4 Format
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE ssn_last4 NOT REGEXP '^[0-9]{4}$'
  OR ssn_last4 = '0000'
```
**Expected:** 0 violations
**Severity:** HIGH

### DQ-006: Email Format Validation
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE email_address IS NOT NULL
  AND email_address NOT REGEXP '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
```
**Expected:** <1%
**Severity:** LOW

### DQ-007: Phone Number Format
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE phone_primary IS NOT NULL
  AND phone_primary NOT REGEXP '^[0-9]{3}-[0-9]{3}-[0-9]{4}$'
```
**Expected:** 0 violations (if standardized)
**Severity:** LOW

### DQ-008: ZIP Code Validity
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE address_zip NOT REGEXP '^[0-9]{5}$'
   OR address_zip = '00000'
```
**Expected:** 0 violations
**Severity:** MEDIUM

### DQ-009: State Code Validity
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE address_state NOT IN (
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS',
  'KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY',
  'NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'
)
```
**Expected:** 0 violations
**Severity:** MEDIUM

### DQ-010: Date Range Reasonableness
**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE application_date < '2020-01-01'
   OR application_date > CURRENT_DATE
   OR date_of_birth < '1920-01-01'
   OR date_of_birth > CURRENT_DATE - INTERVAL '18 years'
```
**Expected:** 0 violations
**Severity:** HIGH

### DQ-011: Negative Balance Check
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE current_principal_balance < 0
   OR current_interest_balance < 0
   OR current_fees_balance < 0
```
**Expected:** 0 violations
**Severity:** CRITICAL

### DQ-012: Duplicate Detection
**Query:**
```sql
-- Check for duplicate SSN+DOB combinations (potential fraud or data error)
SELECT ssn_last4, date_of_birth, COUNT(*) as dup_count
FROM applications
GROUP BY ssn_last4, date_of_birth
HAVING COUNT(*) > 1
```
**Expected:** <0.1% (some twins/family members may legitimately match)
**Severity:** MEDIUM

---

## 8. HYDRATION HEURISTICS AUDIT

### HYD-001: Delinquency Count Defaults
**Issue:** `delinquency_30_day_count` defaulted to 0
**Query:**
```sql
-- Check if delinquent loans have delinquency_count = 0 (unrealistic)
SELECT COUNT(*) as violations
FROM credit_reports cr
JOIN loan_tape lt ON cr.application_id = lt.application_id
WHERE lt.loan_status LIKE 'DELINQUENT%'
  AND cr.delinquency_30_day_count = 0
```
**Recommendation:** Derive from loan_tape.times_30_dpd
**Severity:** MEDIUM

### HYD-002: Months Since Last Delinquency
**Issue:** Field may be NULL or 999 by default
**Query:**
```sql
-- If loan is CURRENT but has delinquency history, months_since should be populated
SELECT COUNT(*) as violations
FROM loan_tape
WHERE loan_status = 'CURRENT'
  AND times_30_dpd > 0
  AND (months_since_last_delinquency IS NULL OR months_since_last_delinquency = 999)
```
**Recommendation:** Calculate based on payment history
**Severity:** HIGH

### HYD-003: Credit Tradeline Defaults
**Issue:** Many tradeline fields use placeholder values
**Query:**
```sql
-- Check if all tradelines have times_30_dpd = 0 (too clean)
SELECT COUNT(*) * 100.0 / (SELECT COUNT(*) FROM credit_tradelines) as pct_clean
FROM credit_tradelines
WHERE times_30dpd = 0 AND times_60dpd = 0 AND times_90dpd = 0
```
**Expected:** <90% (some tradelines should show delinquency)
**Severity:** MEDIUM

### HYD-004: Fraud Score Realism
**Issue:** Fraud scores may be uniformly distributed
**Query:**
```sql
-- Check variance in fraud scores
SELECT
  STDDEV(overall_fraud_score) as stddev,
  AVG(overall_fraud_score) as avg
FROM fraud_verification
```
**Expected:** Stddev >100, mean ≈ 600-800
**Severity:** LOW

### HYD-005: Bank Transaction Volume
**Issue:** Only 100 transactions generated (minimal)
**Query:**
```sql
SELECT COUNT(*) as total_txns,
       COUNT(DISTINCT application_id) as unique_apps
FROM bank_transactions
```
**Expected:** >1000 transactions across applications
**Severity:** LOW

### HYD-006: Customer ID Generation
**Issue:** customer_id may not be consistent across tables
**Status:** Covered by INT-008

### HYD-007: Missing Payment Details
**Issue:** Fields like `suspense_amount`, `unapplied_amount` may be hardcoded to 0
**Query:**
```sql
-- Check if ALL payments have 0 suspense/unapplied (too clean)
SELECT COUNT(*) as total,
       COUNT(*) FILTER (WHERE suspense_amount = 0 AND unapplied_amount = 0) as all_zero
FROM payments
```
**Expected:** <99% (some partial payments should create suspense)
**Severity:** LOW

### HYD-008: Autopay Enrollment Rate
**Issue:** autopay_flag may be TRUE for all records
**Query:**
```sql
SELECT
  autopay_flag,
  COUNT(*) * 100.0 / (SELECT COUNT(*) FROM payments) as pct
FROM payments
GROUP BY autopay_flag
```
**Expected:** 60-80% autopay, 20-40% manual
**Severity:** MEDIUM

### HYD-009: Payment Channel Distribution
**Issue:** All payments may be "WEB"
**Query:**
```sql
SELECT payment_channel, COUNT(*) as cnt
FROM payments
GROUP BY payment_channel
```
**Expected:** Mix of WEB, MOBILE, PHONE, AUTOPAY
**Severity:** LOW

### HYD-010: NSF/Returned Payment Rate
**Issue:** nsf_flag may be FALSE for all records
**Query:**
```sql
SELECT COUNT(*) * 100.0 / (SELECT COUNT(*) FROM payments) as nsf_pct
FROM payments
WHERE nsf_flag = TRUE OR returned_flag = TRUE
```
**Expected:** 1-3% NSF rate
**Severity:** MEDIUM

### HYD-011: Grade/Subgrade Consistency
**Issue:** Subgrade may not align with grade (e.g., grade=B, subgrade=C3)
**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE LEFT(subgrade, 1) != grade
```
**Expected:** 0 violations
**Severity:** MEDIUM

### HYD-012: Credit Bureau Code Distribution
**Issue:** All credit reports may be from single bureau (TU)
**Query:**
```sql
SELECT bureau_code, COUNT(*) as cnt
FROM credit_reports
GROUP BY bureau_code
```
**Expected:** Mix of EXP, EFX, TU
**Severity:** LOW

---

## IMPLEMENTATION PRIORITY

### CRITICAL (Immediate)
1. All Referential Integrity checks (INT-003 to INT-008)
2. Temporal violations (TMP-001 to TMP-004)
3. Negative balances (DQ-011)
4. POL-009 (Age requirement)
5. POL-010 (Chargeoff timing)

### HIGH (Short-term)
1. Financial math (FIN-003 to FIN-007)
2. Cross-column logic (LOG-002, LOG-004 to LOG-006)
3. Delinquency heuristics (HYD-001, HYD-002)
4. Payment waterfall (FIN-005)

### MEDIUM (Medium-term)
1. Statistical realism (STAT-003, STAT-004, STAT-007, STAT-008)
2. Hydration defaults (HYD-003, HYD-008, HYD-010)
3. Temporal gaps (TMP-006)
4. Business rules (POL-004 to POL-008)

### LOW (Long-term)
1. Distribution shape checks (STAT-001, STAT-009)
2. Data format validation (DQ-006, DQ-007)
3. Edge case handling (HYD-005, HYD-009)

---

## RECOMMENDED NEXT STEPS

1. **Extend `validation_framework.py`** with the checks above
2. **Create parameterized test suite** using pytest for regression testing
3. **Generate QA dashboard** showing pass/fail rates by category
4. **Document edge cases** where violations are expected (e.g., state-specific regulations)
5. **Integrate with CI/CD** to prevent data quality regression
6. **Add sampling logic** for 1M row datasets (validate on 10% sample for speed)

---

## APPENDIX: Quick Reference

| Category | Check Count | Current Coverage | Gap |
|----------|-------------|------------------|-----|
| Referential Integrity | 8 | 2 | 6 |
| Business Rules | 10 | 3 | 7 |
| Temporal Consistency | 10 | 0 | 10 |
| Financial Math | 10 | 2 | 8 |
| Cross-Column Logic | 15 | 3 | 12 |
| Statistical Realism | 10 | 0 | 10 |
| Data Quality | 12 | 3 | 9 |
| Hydration Heuristics | 12 | 1 | 11 |
| **TOTAL** | **87** | **14** | **73** |

---

**Document Version:** 1.0
**Last Updated:** 2026-01-08
**Prepared by:** Claude Code QA Analysis
**Status:** Ready for Implementation
