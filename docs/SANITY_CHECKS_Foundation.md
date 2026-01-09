# Foundation Sanity Checks - Logical Impossibilities
## LendCo Synthetic Data - Zero-Tolerance Validation

**Purpose:** These are BINARY checks that should NEVER fail. Any violation represents a fundamental data corruption or generator bug.

**Status:** MUST be 100% PASS before any other validation
**Severity:** ALL CRITICAL

---

## Categories

1. [Lifecycle Sanity Checks](#lifecycle-sanity-checks) - Workflow state consistency
2. [Existence Preconditions](#existence-preconditions) - Required parent records
3. [State Machine Violations](#state-machine-violations) - Invalid state transitions
4. [Temporal Impossibilities](#temporal-impossibilities) - Time paradoxes
5. [Financial Impossibilities](#financial-impossibilities) - Money that shouldn't exist
6. [Payment Waterfall Violations](#payment-waterfall-violations) - Payment logic errors
7. [Credit Bureau Impossibilities](#credit-bureau-impossibilities) - Credit data paradoxes
8. [Fraud & Identity Conflicts](#fraud--identity-conflicts) - Identity inconsistencies

---

## LIFECYCLE SANITY CHECKS

### SANITY-001: No Funded Loan Without Approval ⭐ KEY
**Rule:** Every loan in `loan_tape` MUST have `decision_status = 'APPROVED'` in `applications`

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape lt
JOIN applications a ON lt.application_id = a.application_id
WHERE a.decision_status != 'APPROVED'
```
**Expected:** 0 violations (ZERO TOLERANCE)
**Rationale:** Cannot disburse funds for declined/pending applications
**Impact:** Portfolio metrics completely wrong, fraud risk

---

### SANITY-002: No Approval Without Credit Report ⭐ KEY
**Rule:** Every APPROVED application MUST have a credit report

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
LEFT JOIN credit_reports cr ON a.application_id = cr.application_id
WHERE a.decision_status = 'APPROVED'
  AND cr.credit_report_id IS NULL
```
**Expected:** 0 violations
**Rationale:** Cannot underwrite without credit data (regulatory requirement)
**Impact:** Violates lending compliance, unrealistic approval process

---

### SANITY-003: No Approval Without Fraud Check
**Rule:** Every APPROVED application MUST have fraud verification

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
LEFT JOIN fraud_verification fv ON a.application_id = fv.application_id
WHERE a.decision_status = 'APPROVED'
  AND fv.application_id IS NULL
```
**Expected:** 0 violations
**Rationale:** Fraud screening is mandatory pre-funding
**Impact:** AML/KYC violation

---

### SANITY-004: No Payment Without Funded Loan ⭐ KEY
**Rule:** Every payment MUST link to a loan in `loan_tape`

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments p
LEFT JOIN loan_tape lt ON p.loan_id = lt.loan_id
WHERE lt.loan_id IS NULL
```
**Expected:** 0 violations
**Rationale:** Cannot pay a loan that was never funded
**Impact:** Payment data is orphaned, breaks reconciliation

---

### SANITY-005: No Loan Tape Entry Without Application
**Rule:** Every `loan_tape` record MUST have parent application

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape lt
LEFT JOIN applications a ON lt.application_id = a.application_id
WHERE a.application_id IS NULL
```
**Expected:** 0 violations
**Rationale:** Loans don't materialize from thin air
**Impact:** Referential integrity violation

---

### SANITY-006: No Credit Report Without Application
**Rule:** Every credit report MUST link to an application

**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_reports cr
LEFT JOIN applications a ON cr.application_id = a.application_id
WHERE a.application_id IS NULL
```
**Expected:** 0 violations
**Rationale:** Credit reports are pulled FOR an application
**Impact:** Wasted credit bureau pulls (cost issue)

---

### SANITY-007: No Declined Application in Loan Tape
**Rule:** No DECLINED applications should have funded loans

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape lt
JOIN applications a ON lt.application_id = a.application_id
WHERE a.decision_status = 'DECLINED'
```
**Expected:** 0 violations
**Rationale:** Declined = no funding authorization
**Impact:** Fraud, unauthorized lending

---

### SANITY-008: No Pending Application in Loan Tape
**Rule:** No PENDING applications should have funded loans

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape lt
JOIN applications a ON lt.application_id = a.application_id
WHERE a.decision_status IN ('PENDING', 'UNDER_REVIEW', 'INCOMPLETE')
```
**Expected:** 0 violations
**Rationale:** Must complete decisioning before funding
**Impact:** Premature funding, credit risk

---

## STATE MACHINE VIOLATIONS

### SANITY-009: No Payments After Loan Paid Off ⭐ KEY
**Rule:** Loans with status = PAID_OFF should have NO payments after payoff date

**Query:**
```sql
WITH payoff_dates AS (
  SELECT loan_id,
         MAX(snapshot_date) as payoff_date
  FROM loan_tape
  WHERE loan_status = 'PAID_OFF'
  GROUP BY loan_id
)
SELECT COUNT(*) as violations
FROM payments p
JOIN payoff_dates pd ON p.loan_id = pd.loan_id
WHERE p.payment_received_date > pd.payoff_date
```
**Expected:** 0 violations
**Rationale:** Cannot pay a closed loan
**Impact:** Reconciliation breaks, double-counting revenue

---

### SANITY-010: No Payments After Chargeoff ⭐ KEY
**Rule:** Loans with status = CHARGED_OFF should have NO payments after chargeoff

**Query:**
```sql
WITH chargeoff_dates AS (
  SELECT loan_id,
         MIN(snapshot_date) as co_date
  FROM loan_tape
  WHERE loan_status = 'CHARGED_OFF'
  GROUP BY loan_id
)
SELECT COUNT(*) as violations
FROM payments p
JOIN chargeoff_dates cd ON p.loan_id = cd.loan_id
WHERE p.payment_received_date > cd.co_date
  AND p.actual_payment_amount > 0
```
**Expected:** 0 violations (some recovery payments allowed, but should be flagged)
**Rationale:** Charged-off loans moved to collections
**Impact:** Recovery accounting wrong

---

### SANITY-011: No Delinquent Status With All Payments Current ⭐ KEY
**Rule:** Loans marked DELINQUENT must have missed payments

**Query:**
```sql
-- For each delinquent loan, verify it actually missed payments
WITH loan_payment_counts AS (
  SELECT lt.loan_id,
         lt.loan_status,
         lt.months_on_book,
         COUNT(p.payment_id) FILTER (WHERE p.payment_status = 'POSTED' AND p.actual_payment_amount > 0) as paid_count
  FROM loan_tape lt
  LEFT JOIN payments p ON lt.loan_id = p.loan_id
  WHERE lt.snapshot_date = (SELECT MAX(snapshot_date) FROM loan_tape) -- Latest snapshot
  GROUP BY lt.loan_id, lt.loan_status, lt.months_on_book
)
SELECT COUNT(*) as violations
FROM loan_payment_counts
WHERE loan_status LIKE 'DELINQUENT%'
  AND paid_count >= months_on_book
  -- If loan is 6 months old and has 6 payments, it shouldn't be delinquent
```
**Expected:** 0 violations
**Rationale:** Can't be delinquent if all payments made
**Impact:** Status-DPD mismatch, reporting error

---

### SANITY-012: No Current Status With Missed Payments
**Rule:** Loans with status = CURRENT must have days_past_due = 0

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE loan_status = 'CURRENT'
  AND days_past_due > 0
```
**Expected:** 0 violations
**Rationale:** CURRENT means no delinquency
**Impact:** Status inconsistency

---

### SANITY-013: No Balance on Paid Off Loans
**Rule:** PAID_OFF loans must have zero balance

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE loan_status = 'PAID_OFF'
  AND current_principal_balance > 0.01
```
**Expected:** 0 violations
**Rationale:** Paid off means balance = 0
**Impact:** Balance reconciliation fails

---

### SANITY-014: No Balance on Charged Off Loans (After Chargeoff)
**Rule:** CHARGED_OFF loans should have zero balance (written off)

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE loan_status = 'CHARGED_OFF'
  AND current_principal_balance > 0.01
  AND months_on_book > 4  -- Allow grace period for chargeoff process
```
**Expected:** <5% (some lenders carry balance temporarily)
**Rationale:** Chargeoff = removed from books
**Impact:** Balance sheet inflation

---

### SANITY-015: No Payments Before First Payment Due Date
**Rule:** Payments cannot occur before first scheduled payment

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments p
JOIN loan_tape lt ON p.loan_id = lt.loan_id
WHERE p.payment_received_date < lt.first_payment_due_date
  AND p.payment_type != 'PREPAYMENT'
```
**Expected:** <1% (early prepayments allowed)
**Rationale:** Cannot pay before bill is due
**Impact:** Amortization schedule broken

---

### SANITY-016: Loan Status Must Be Valid Enum
**Rule:** loan_status must be from allowed list

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE loan_status NOT IN (
  'CURRENT', 'DELINQUENT_30', 'DELINQUENT_60', 'DELINQUENT_90',
  'DELINQUENT_120', 'CHARGED_OFF', 'PAID_OFF', 'PREPAID',
  'CANCELLED', 'IN_FORBEARANCE'
)
```
**Expected:** 0 violations
**Rationale:** Invalid states corrupt reporting
**Impact:** Reporting breaks

---

## TEMPORAL IMPOSSIBILITIES

### SANITY-017: Application Before Credit Report Pull ⭐ KEY
**Rule:** Credit report must be pulled ON or AFTER application date

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN credit_reports cr ON a.application_id = cr.application_id
WHERE cr.report_date < a.application_date
```
**Expected:** 0 violations
**Rationale:** Cannot pull credit before customer applies
**Impact:** Temporal paradox

---

### SANITY-018: Application Before Fraud Check
**Rule:** Fraud check must occur ON or AFTER application

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN fraud_verification fv ON a.application_id = fv.application_id
WHERE fv.fraud_check_timestamp < a.application_timestamp
```
**Expected:** 0 violations
**Rationale:** Cannot verify before submission
**Impact:** Process order wrong

---

### SANITY-019: Origination After Application ⭐ KEY
**Rule:** Loan origination must occur AFTER application

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape lt
JOIN applications a ON lt.application_id = a.application_id
WHERE lt.origination_date < a.application_date
```
**Expected:** 0 violations
**Rationale:** Cannot fund before application exists
**Impact:** Timeline corruption

---

### SANITY-020: Payment After Origination
**Rule:** First payment must be AFTER loan origination

**Query:**
```sql
WITH first_payments AS (
  SELECT loan_id, MIN(payment_received_date) as first_pmt_date
  FROM payments
  GROUP BY loan_id
)
SELECT COUNT(*) as violations
FROM first_payments fp
JOIN loan_tape lt ON fp.loan_id = lt.loan_id
WHERE fp.first_pmt_date < lt.origination_date
```
**Expected:** 0 violations
**Rationale:** Cannot pay before loan exists
**Impact:** Cash flow timing wrong

---

### SANITY-021: No Future Dates
**Rule:** All dates must be <= today (or simulation snapshot date)

**Query:**
```sql
-- Assuming simulation snapshot = 2023-12-31
SELECT
  'applications' as table_name,
  COUNT(*) as violations
FROM applications
WHERE application_date > '2023-12-31'

UNION ALL

SELECT 'loan_tape', COUNT(*)
FROM loan_tape
WHERE snapshot_date > '2023-12-31'

UNION ALL

SELECT 'payments', COUNT(*)
FROM payments
WHERE payment_received_date > '2023-12-31'
```
**Expected:** 0 violations
**Rationale:** Cannot have future transactions in historical data
**Impact:** Temporal impossibility

---

### SANITY-022: Birth Date Before Application
**Rule:** Applicant must be born before applying

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE date_of_birth >= application_date
```
**Expected:** 0 violations
**Rationale:** Time travel not yet invented
**Impact:** Data quality failure

---

### SANITY-023: No Payments Before Loan Originated
**Rule:** All payments must be AFTER origination_date

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments p
JOIN loan_tape lt ON p.loan_id = lt.loan_id
WHERE p.payment_received_date < lt.origination_date
```
**Expected:** 0 violations
**Rationale:** Loan must exist before payment
**Impact:** Fundamental logic error

---

## FINANCIAL IMPOSSIBILITIES

### SANITY-024: No Negative Principal Balance
**Rule:** Principal balance cannot be negative

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE current_principal_balance < 0
```
**Expected:** 0 violations
**Rationale:** Cannot owe negative money
**Impact:** Accounting corruption

---

### SANITY-025: No Negative Payment Amount
**Rule:** Payment amounts cannot be negative

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE actual_payment_amount < 0
  OR principal_paid < 0
  OR interest_paid < 0
```
**Expected:** 0 violations (refunds should be separate transaction type)
**Rationale:** Payments flow customer → lender
**Impact:** Cash flow direction wrong

---

### SANITY-026: Balance Never Exceeds Original Amount (Non-Neg-Am) ⭐ KEY
**Rule:** Current balance should not exceed original loan amount

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE current_principal_balance > original_loan_amount * 1.01
  -- Allow 1% buffer for interest capitalization edge cases
```
**Expected:** 0 violations (assuming no negative amortization)
**Rationale:** Principal should only decrease
**Impact:** Amortization logic broken

---

### SANITY-027: Sum of Payments Not Exceeding Total Owed
**Rule:** Cumulative payments shouldn't exceed original loan + reasonable interest

**Query:**
```sql
WITH loan_payment_sums AS (
  SELECT
    p.loan_id,
    SUM(p.actual_payment_amount) as total_paid,
    MAX(lt.original_loan_amount) as orig_amt
  FROM payments p
  JOIN loan_tape lt ON p.loan_id = lt.loan_id
  GROUP BY p.loan_id
)
SELECT COUNT(*) as violations
FROM loan_payment_sums
WHERE total_paid > orig_amt * 3
  -- No loan should require 3x original amount (usury check)
```
**Expected:** 0 violations
**Rationale:** Total payments shouldn't be absurdly high
**Impact:** Interest calculation wrong

---

### SANITY-028: No Interest-Only With Zero Interest
**Rule:** If interest_only_indicator = TRUE, must have interest charges

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE interest_only_indicator = TRUE
  AND original_interest_rate = 0
```
**Expected:** 0 violations
**Rationale:** Interest-only requires interest
**Impact:** Product definition error

---

### SANITY-029: Payment Components Sum to Total ⭐ KEY
**Rule:** principal_paid + interest_paid + fees_paid = actual_payment_amount

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE ABS(
  (principal_paid + interest_paid + COALESCE(fees_paid, 0) + COALESCE(late_fee_paid, 0))
  - actual_payment_amount
) > 0.02  -- 2 cent tolerance for rounding
```
**Expected:** 0 violations
**Rationale:** Payment waterfall must balance
**Impact:** Accounting doesn't reconcile

---

### SANITY-030: No Origination Fee Exceeding Loan Amount
**Rule:** Origination fee cannot be larger than the loan itself

**Query:**
```sql
SELECT COUNT(*) as violations
FROM loan_tape
WHERE origination_fee >= original_loan_amount
```
**Expected:** 0 violations
**Rationale:** Fee can't be 100%+ of loan (usury)
**Impact:** Fee structure broken

---

## PAYMENT WATERFALL VIOLATIONS

### SANITY-031: Posted Payments Must Have Received Date
**Rule:** If payment_status = 'POSTED', must have payment_received_date

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE payment_status = 'POSTED'
  AND payment_received_date IS NULL
```
**Expected:** 0 violations
**Rationale:** Cannot post phantom payment
**Impact:** Payment tracking broken

---

### SANITY-032: No Scheduled Payment Amount = 0
**Rule:** scheduled_payment_amount must be > 0 for active loans

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments p
JOIN loan_tape lt ON p.loan_id = lt.loan_id
WHERE p.scheduled_payment_amount <= 0
  AND lt.loan_status NOT IN ('PAID_OFF', 'CHARGED_OFF')
```
**Expected:** 0 violations
**Rationale:** Every payment period requires payment
**Impact:** Amortization schedule wrong

---

### SANITY-033: No Actual Payment > Scheduled (Without Prepayment Flag)
**Rule:** If actual > scheduled, must be marked as prepayment/extra

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE actual_payment_amount > scheduled_payment_amount * 1.05
  -- 5% tolerance
  AND payment_type NOT IN ('PREPAYMENT', 'PAYOFF')
  AND is_extra_payment = FALSE
```
**Expected:** <1%
**Rationale:** Overpayments should be flagged
**Impact:** Prepayment tracking wrong

---

### SANITY-034: Missed Payments Have Zero Actual Amount ⭐ KEY
**Rule:** If payment_status = 'MISSED', actual_payment_amount must be 0

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE payment_status = 'MISSED'
  AND actual_payment_amount > 0
```
**Expected:** 0 violations
**Rationale:** Cannot miss and pay simultaneously
**Impact:** Delinquency tracking broken

---

### SANITY-035: Late Payments Have Late Fee Assessment
**Rule:** If days_late > grace_period, late_fee_assessed should be > 0

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE days_late > COALESCE(grace_period_days, 15)
  AND payment_status = 'POSTED'
  AND late_fee_assessed = 0
  AND late_fee_waived = FALSE
```
**Expected:** <20% (some lenders waive automatically)
**Rationale:** Late fees are automatic after grace period
**Impact:** Fee revenue understated

---

### SANITY-036: NSF Payments Must Be Returned
**Rule:** If nsf_flag = TRUE, returned_flag must also be TRUE

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE nsf_flag = TRUE
  AND returned_flag = FALSE
```
**Expected:** 0 violations
**Rationale:** NSF means payment bounced
**Impact:** NSF tracking inconsistent

---

### SANITY-037: Returned Payments Have Return Date
**Rule:** If returned_flag = TRUE, return_date must exist

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE returned_flag = TRUE
  AND return_date IS NULL
```
**Expected:** 0 violations
**Rationale:** Return event needs timestamp
**Impact:** Return tracking broken

---

### SANITY-038: Autopay Failures Should Trigger NSF/Return
**Rule:** Autopay failed payments should have reason code

**Query:**
```sql
SELECT COUNT(*) as violations
FROM payments
WHERE autopay_flag = TRUE
  AND payment_status IN ('RETURNED', 'REVERSED')
  AND return_reason_code IS NULL
```
**Expected:** <10%
**Rationale:** Failed autopay has ACH return code
**Impact:** Root cause analysis impossible

---

## CREDIT BUREAU IMPOSSIBILITIES

### SANITY-039: FICO Score in Valid Range
**Rule:** All FICO scores must be 300-850

**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_reports
WHERE fico_score_8 NOT BETWEEN 300 AND 850
  OR vantage_score_3 NOT BETWEEN 300 AND 850
```
**Expected:** 0 violations
**Rationale:** FICO range is standardized
**Impact:** Credit data corrupted

---

### SANITY-040: Credit File Established After Birth
**Rule:** file_since_date must be after date_of_birth

**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_reports cr
JOIN applications a ON cr.application_id = a.application_id
WHERE cr.file_since_date < a.date_of_birth
```
**Expected:** 0 violations
**Rationale:** Cannot have credit before birth
**Impact:** Temporal paradox

---

### SANITY-041: Bankruptcy Flag Without Bankruptcy Count ⭐ KEY
**Rule:** If bankruptcies_count > 0, public_records_count should also be > 0

**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_reports
WHERE bankruptcies_count > 0
  AND public_records_count = 0
```
**Expected:** 0 violations
**Rationale:** Bankruptcies are public records
**Impact:** Credit attribute inconsistency

---

### SANITY-042: Utilization Ratio Cannot Exceed 200%
**Rule:** revolving_utilization_ratio should not exceed 2.0 (200%)

**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_reports
WHERE revolving_utilization_ratio > 2.0
```
**Expected:** <0.1% (rare edge cases with over-limit)
**Rationale:** >200% util is extremely rare
**Impact:** Unrealistic credit behavior

---

### SANITY-043: Open Trades ≤ Total Trades
**Rule:** all_trades_open_count cannot exceed all_trades_count

**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_reports
WHERE all_trades_open_count > all_trades_count
```
**Expected:** 0 violations
**Rationale:** Open is subset of all
**Impact:** Trade count logic broken

---

### SANITY-044: Tradeline Balance ≤ Credit Limit
**Rule:** current_balance should not exceed credit_limit (except over-limit fees)

**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_tradelines
WHERE current_balance > credit_limit * 1.10
  -- Allow 10% over-limit buffer
  AND account_status = 'OPEN'
```
**Expected:** <5%
**Rationale:** Lenders prevent excessive over-limit
**Impact:** Unrealistic credit usage

---

### SANITY-045: Closed Tradelines Have No Payment Due
**Rule:** Closed accounts should have monthly_payment = 0

**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_tradelines
WHERE account_status = 'CLOSED'
  AND monthly_payment > 0
```
**Expected:** 0 violations
**Rationale:** Closed accounts don't require payments
**Impact:** Payment obligation wrong

---

### SANITY-046: Tradeline Open Date Before Report Date
**Rule:** open_date must be before or equal to report_date

**Query:**
```sql
SELECT COUNT(*) as violations
FROM credit_tradelines ct
JOIN credit_reports cr ON ct.credit_report_id = cr.credit_report_id
WHERE ct.open_date > cr.report_date
```
**Expected:** 0 violations
**Rationale:** Cannot report future tradeline
**Impact:** Temporal impossibility

---

## FRAUD & IDENTITY CONFLICTS

### SANITY-047: SSN Deceased Flag Conflicts
**Rule:** If ssn_deceased_flag = TRUE, application should be DECLINED

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN fraud_verification fv ON a.application_id = fv.application_id
WHERE fv.ssn_deceased_flag = TRUE
  AND a.decision_status = 'APPROVED'
```
**Expected:** 0 violations
**Rationale:** Cannot lend to deceased person (fraud)
**Impact:** Identity fraud, compliance violation

---

### SANITY-048: SSN Issued After Birth
**Rule:** SSN issuance year should be after birth year

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN fraud_verification fv ON a.application_id = fv.application_id
WHERE fv.ssn_issued_start_year < YEAR(a.date_of_birth)
```
**Expected:** <1% (legacy data errors)
**Rationale:** SSN issued at/after birth
**Impact:** Identity verification failure

---

### SANITY-049: Identity Verification Failures Should Decline
**Rule:** If identity_verification_result = 'FAIL', should be DECLINED

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN fraud_verification fv ON a.application_id = fv.application_id
WHERE fv.identity_verification_result = 'FAIL'
  AND a.decision_status = 'APPROVED'
```
**Expected:** 0 violations
**Rationale:** Cannot approve unverified identity (KYC)
**Impact:** Fraud risk, regulatory violation

---

### SANITY-050: High Fraud Score Should Decline
**Rule:** If fraud_risk_tier = 'CRITICAL', should be DECLINED

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications a
JOIN fraud_verification fv ON a.application_id = fv.application_id
WHERE fv.fraud_risk_tier = 'CRITICAL'
  AND a.decision_status = 'APPROVED'
```
**Expected:** 0 violations
**Rationale:** Critical fraud tier is auto-decline
**Impact:** Fraud losses

---

### SANITY-051: Applicant Age at Application
**Rule:** Applicant must be 18-100 years old at application

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE (application_date - date_of_birth) / 365.25 NOT BETWEEN 18 AND 100
```
**Expected:** 0 violations
**Rationale:** Legal age constraints, data quality
**Impact:** Age validation failure

---

### SANITY-052: Email Format Validation
**Rule:** Email addresses must contain @ and domain

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE email_address IS NOT NULL
  AND (
    email_address NOT LIKE '%@%.%'
    OR LENGTH(email_address) < 5
  )
```
**Expected:** <1%
**Rationale:** Basic email format
**Impact:** Contact info invalid

---

### SANITY-053: Phone Number Length
**Rule:** Phone numbers should be 10 digits (US format)

**Query:**
```sql
SELECT COUNT(*) as violations
FROM applications
WHERE phone_primary IS NOT NULL
  AND LENGTH(REGEXP_REPLACE(phone_primary, '[^0-9]', '')) != 10
```
**Expected:** <1%
**Rationale:** US phone format standard
**Impact:** Contact info invalid

---

## CROSS-TABLE STATE CONSISTENCY

### SANITY-054: Loan Status Consistency Across Snapshots
**Rule:** Loan cannot go from PAID_OFF back to CURRENT

**Query:**
```sql
WITH status_changes AS (
  SELECT
    loan_id,
    snapshot_date,
    loan_status,
    LAG(loan_status) OVER (PARTITION BY loan_id ORDER BY snapshot_date) as prev_status
  FROM loan_tape
)
SELECT COUNT(DISTINCT loan_id) as violations
FROM status_changes
WHERE prev_status = 'PAID_OFF'
  AND loan_status != 'PAID_OFF'
```
**Expected:** 0 violations
**Rationale:** Paid off is terminal state
**Impact:** State machine violation

---

### SANITY-055: Loan Cannot Resurrect After Chargeoff
**Rule:** Loan cannot go from CHARGED_OFF to CURRENT/DELINQUENT

**Query:**
```sql
WITH status_changes AS (
  SELECT
    loan_id,
    snapshot_date,
    loan_status,
    LAG(loan_status) OVER (PARTITION BY loan_id ORDER BY snapshot_date) as prev_status
  FROM loan_tape
)
SELECT COUNT(DISTINCT loan_id) as violations
FROM status_changes
WHERE prev_status = 'CHARGED_OFF'
  AND loan_status NOT IN ('CHARGED_OFF')
```
**Expected:** 0 violations
**Rationale:** Chargeoff is terminal (except recovery)
**Impact:** State machine violation

---

### SANITY-056: Balance Can Only Decrease (No Negative Amortization)
**Rule:** Principal balance should decrease or stay flat month-over-month

**Query:**
```sql
WITH balance_changes AS (
  SELECT
    loan_id,
    snapshot_date,
    current_principal_balance,
    LAG(current_principal_balance) OVER (PARTITION BY loan_id ORDER BY snapshot_date) as prev_balance
  FROM loan_tape
  WHERE loan_status NOT IN ('CHARGED_OFF', 'PAID_OFF')
)
SELECT COUNT(*) as violations
FROM balance_changes
WHERE current_principal_balance > prev_balance + 1.0
  -- Allow $1 tolerance for rounding/interest cap
```
**Expected:** 0 violations (assuming no neg-am products)
**Rationale:** Principal decreases with payments
**Impact:** Amortization logic broken

---

### SANITY-057: Delinquency Can Only Increase or Cure
**Rule:** DPD cannot decrease unless loan cures to 0

**Query:**
```sql
WITH dpd_changes AS (
  SELECT
    loan_id,
    snapshot_date,
    days_past_due,
    LAG(days_past_due) OVER (PARTITION BY loan_id ORDER BY snapshot_date) as prev_dpd
  FROM loan_tape
)
SELECT COUNT(*) as violations
FROM dpd_changes
WHERE days_past_due < prev_dpd
  AND days_past_due > 0
  -- DPD can go 60→0 (cure), but not 60→30 (impossible)
```
**Expected:** 0 violations
**Rationale:** DPD increments by 30 or cures to 0
**Impact:** Delinquency logic broken

---

### SANITY-058: Months on Book Must Increase
**Rule:** months_on_book should increase by 1 each month

**Query:**
```sql
WITH mob_changes AS (
  SELECT
    loan_id,
    snapshot_date,
    months_on_book,
    LAG(months_on_book) OVER (PARTITION BY loan_id ORDER BY snapshot_date) as prev_mob,
    LAG(snapshot_date) OVER (PARTITION BY loan_id ORDER BY snapshot_date) as prev_date
  FROM loan_tape
)
SELECT COUNT(*) as violations
FROM mob_changes
WHERE months_on_book != prev_mob + 1
  AND DATEDIFF(snapshot_date, prev_date) BETWEEN 28 AND 35
  -- Only check consecutive months
```
**Expected:** <5%
**Rationale:** MoB increments linearly
**Impact:** Age calculation wrong

---

### SANITY-059: No Payment Count Exceeding Months on Book
**Rule:** Number of payments should not exceed loan age

**Query:**
```sql
WITH payment_counts AS (
  SELECT
    lt.loan_id,
    lt.months_on_book,
    COUNT(p.payment_id) as pmt_count
  FROM loan_tape lt
  LEFT JOIN payments p ON lt.loan_id = p.loan_id
  WHERE lt.snapshot_date = (SELECT MAX(snapshot_date) FROM loan_tape)
  GROUP BY lt.loan_id, lt.months_on_book
)
SELECT COUNT(*) as violations
FROM payment_counts
WHERE pmt_count > months_on_book + 2
  -- Allow buffer for prepayments/extra payments
```
**Expected:** <1%
**Rationale:** Cannot have 10 payments on 3-month-old loan
**Impact:** Payment count logic broken

---

### SANITY-060: Application Count = Unique Applicants
**Rule:** One application per application_id (PK constraint)

**Query:**
```sql
SELECT COUNT(*) - COUNT(DISTINCT application_id) as violations
FROM applications
```
**Expected:** 0 violations
**Rationale:** Primary key uniqueness
**Impact:** Duplicate applications

---

## SUMMARY MATRIX

| Check ID | Check Name | Zero Tolerance | Rationale |
|----------|------------|----------------|-----------|
| SANITY-001 | No Funded Loan Without Approval | ✅ YES | Cannot disburse without authorization |
| SANITY-002 | No Approval Without Credit Report | ✅ YES | Regulatory requirement |
| SANITY-004 | No Payment Without Funded Loan | ✅ YES | Orphan payment data |
| SANITY-009 | No Payments After Paid Off | ✅ YES | Terminal state violation |
| SANITY-010 | No Payments After Chargeoff | ✅ YES | Terminal state violation |
| SANITY-011 | No Delinquent With All Payments | ✅ YES | Status-payment mismatch |
| SANITY-019 | Origination After Application | ✅ YES | Temporal impossibility |
| SANITY-024 | No Negative Principal | ✅ YES | Financial impossibility |
| SANITY-029 | Payment Components Sum | ✅ YES | Accounting must balance |
| SANITY-034 | Missed Payments = Zero Amount | ✅ YES | Logical contradiction |
| SANITY-039 | FICO Range 300-850 | ✅ YES | Standard range |
| SANITY-047 | No Approval for Deceased SSN | ✅ YES | Fraud/compliance |
| SANITY-054 | No Resurrection After Payoff | ✅ YES | State machine violation |

**Total Checks:** 60
**Zero Tolerance:** 40+ (67%)
**Critical Severity:** 100%

---

## IMPLEMENTATION PRIORITY

### PHASE 1: Immediate (Run Today)
All **SANITY-xxx** checks marked with ⭐ KEY (13 checks)

### PHASE 2: This Week
All lifecycle and state machine checks (SANITY-001 to SANITY-016)

### PHASE 3: This Month
All remaining checks (temporal, financial, credit bureau)

---

## NEXT STEPS

1. **Run the sanity check suite** (create `sanity_check_validator.py`)
2. **Document any violations** as generator bugs
3. **Fix generator logic** before proceeding to advanced validation
4. **Establish zero-tolerance policy** for these checks in CI/CD

---

**Document Version:** 1.0
**Last Updated:** 2026-01-08
**Purpose:** Foundation sanity checks that MUST pass before any other QA
