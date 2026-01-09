# Remediation Plan: LendCo Synthetic Data v1.0 → v2.0

**Status:** 🟡 IN PROGRESS
**Target Completion:** TBD
**Responsible:** Claude Code + User Review

---

## Overview

This document outlines the complete remediation strategy to fix all 4 critical failures and 17 missing columns identified in the v1.0 dataset validation.

**Remediation Phases:**
1. ✅ Phase 1: Analysis & Planning (COMPLETE)
2. 🟡 Phase 2: Code Fixes (IN PROGRESS)
3. ⚪ Phase 3: Regeneration & Validation
4. ⚪ Phase 4: Final QA & Release

---

## Phase 2: Code Fixes (IN PROGRESS)

### Fix 1: SANITY-011 - Delinquent Loans Without Missed Payments
**File:** `src/data_generator.py`
**Lines:** ~450-650 (loan state machine)
**Violations:** 169,351 loans

#### Root Cause
The Markov state machine transitions loans to DELINQUENT status but doesn't create corresponding MISSED payment records in the payments table.

#### Current Flawed Logic
```python
# Pseudocode of current behavior
if loan transitions to DELINQUENT_30:
    loan_status = "DELINQUENT_30"
    days_past_due = 30
    # ❌ NO missed payment record created!
```

#### Fix Required
```python
# When transitioning to delinquent:
if loan transitions to DELINQUENT_30:
    loan_status = "DELINQUENT_30"
    days_past_due = 30

    # ✅ Create missed payment record
    missed_payment = {
        "payment_id": generate_payment_id(),
        "loan_id": loan_id,
        "payment_due_date": current_snapshot_date - 30 days,
        "payment_status": "MISSED",
        "actual_payment_amount": 0.0,
        "scheduled_payment_amount": monthly_payment,
        "principal_paid": 0.0,
        "interest_paid": 0.0
    }
    payments_table.append(missed_payment)
```

#### Implementation Steps
1. Locate state transition logic in `generate_loan_tape()` function
2. Add payment record creation for each delinquency transition:
   - CURRENT → DELINQUENT_30: Create 1 missed payment
   - DELINQUENT_30 → DELINQUENT_60: Create 2 consecutive missed payments
   - DELINQUENT_60 → DELINQUENT_90: Create 3 consecutive missed payments
   - DELINQUENT_90+ → CHARGED_OFF: Ensure 4+ missed payments exist
3. Maintain counter: `consecutive_missed_payments` in loan state
4. Ensure DPD aligns with missed payment count

#### Validation
After fix, run: `SANITY-011: No Delinquent Without Missed Payments` → Expected: 0 violations

---

### Fix 2: SANITY-043 - Open Trades > Total Trades
**File:** `src/data_generator.py`
**Lines:** ~200-300 (credit report generation)
**Violations:** 22,948 credit reports

#### Root Cause
`open_trades_count` and `all_trades_count` are generated independently without constraint enforcement.

#### Current Flawed Logic
```python
# ❌ Independent random generation
open_trades_count = random.randint(0, 30)
all_trades_count = random.randint(0, 30)
# No guarantee that open_trades_count <= all_trades_count
```

#### Fix Required
```python
# ✅ Generate total first, then sample open from total
all_trades_count = random.randint(5, 30)  # Generate total first
open_trades_count = random.randint(0, all_trades_count)  # Sample from total

# Also enforce for subcategories:
all_trades_open_count = open_trades_count  # Must match
bankcard_trades_count = random.randint(1, all_trades_count)
bankcard_trades_open_count = random.randint(0, bankcard_trades_count)
installment_trades_count = random.randint(0, all_trades_count - bankcard_trades_count)
# ... etc
```

#### Implementation Steps
1. Locate credit report generation in `generate_credit_reports()` function
2. Establish generation hierarchy:
   ```
   all_trades_count (root)
   ├── open_trades_count (subset)
   ├── bankcard_trades_count (partition)
   │   └── bankcard_trades_open_count (subset)
   ├── installment_trades_count (partition)
   │   └── installment_trades_open_count (subset)
   └── revolving_trades_count (partition)
       └── revolving_trades_open_count (subset)
   ```
3. Ensure sum of partitions ≤ root: `bankcard + installment + revolving + ... ≤ all_trades`
4. Add assertion checks during generation

#### Validation
After fix, run: `SANITY-043: Open Trades ≤ Total Trades` → Expected: 0 violations

---

### Fix 3: SANITY-047 - Invalid Identity Verification Scores
**File:** `src/data_generator.py`
**Lines:** ~750-850 (fraud verification generation)
**Violations:** 1,000,000 records (100%)

#### Root Cause
`identity_verification_score` column is added during schema hydration but populated with NULL or default values outside 0-100 range.

#### Current Flawed Logic
```python
# ❌ Column exists but not populated
fraud_verification_df = pl.DataFrame({
    "application_id": app_ids,
    # ... other columns ...
})
# identity_verification_score added by hydration with NULL/invalid values
```

#### Fix Required
```python
# ✅ Explicitly generate identity verification scores
def generate_identity_verification_score(is_fraudulent, is_approved):
    """
    Generate identity verification score in range [0, 100]
    - Legitimate applicants: 70-100 (high confidence)
    - Fraudulent applicants: 0-40 (low confidence)
    - Edge cases: 40-70 (medium confidence)
    """
    if is_fraudulent:
        return random.normalvariate(25, 10)  # Mean 25, std 10
    elif is_approved:
        return random.normalvariate(85, 8)   # Mean 85, std 8
    else:
        return random.normalvariate(60, 15)  # Mean 60, std 15
    # Clamp to [0, 100]
    return max(0, min(100, score))

fraud_verification_df = pl.DataFrame({
    "application_id": app_ids,
    "identity_verification_score": [
        generate_identity_verification_score(is_fraud, is_approved)
        for is_fraud, is_approved in zip(fraud_flags, approval_flags)
    ],
    # ... other columns ...
})
```

#### Implementation Steps
1. Locate `generate_fraud_verification()` function
2. Add `generate_identity_verification_score()` helper function
3. Generate scores correlated with:
   - `fraud_check_status` (PASSED/FAILED)
   - `decision_status` (APPROVED/DECLINED)
4. Consider bimodal distribution for realism
5. Remove identity_verification_score from hydration (generate explicitly)

#### Validation
After fix, run: `SANITY-047: Identity Verification Score in Valid Range (0-100)` → Expected: 0 violations

---

### Fix 4: SANITY-057 - Loans Without Payment Records
**File:** `src/data_generator.py`
**Lines:** ~550-650 (payment generation)
**Violations:** 6,035 loans

#### Root Cause
Payment generation logic skips certain loans or fails to create initial payment schedules for all funded loans.

#### Current Flawed Logic
```python
# ❌ Payments may not be generated for all loans
for loan in funded_loans:
    if loan.status in ["CURRENT", "DELINQUENT"]:
        generate_payments(loan)
    # ❌ CHARGED_OFF and PAID_OFF loans may be skipped
```

#### Fix Required
```python
# ✅ Generate payments for ALL funded loans
for loan in funded_loans:
    # Every funded loan gets a payment schedule
    payment_schedule = generate_full_payment_schedule(
        loan_id=loan.id,
        funding_date=loan.funding_date,
        loan_term=loan.original_loan_term,
        monthly_payment=loan.scheduled_payment_amount,
        snapshot_date=loan.snapshot_date
    )

    # Then apply state-specific modifications
    if loan.status == "CHARGED_OFF":
        # Truncate payments at chargeoff date
        payment_schedule = truncate_at_chargeoff(payment_schedule, loan)
    elif loan.status == "PAID_OFF":
        # Include all payments through payoff
        payment_schedule = include_through_payoff(payment_schedule, loan)

    payments_table.extend(payment_schedule)
```

#### Implementation Steps
1. Locate payment generation logic in `generate_payments()` function
2. Create `generate_full_payment_schedule()` helper:
   - Input: loan details (term, rate, amount)
   - Output: Complete payment schedule (1 payment per month)
3. Ensure payment count = min(loan_term, months_since_funding)
4. Apply status-specific logic AFTER base schedule creation:
   - CHARGED_OFF: Stop payments at chargeoff date
   - PAID_OFF: Mark final payment as paying off remaining balance
   - PREPAID: Create single large payment
5. Verify: `SELECT COUNT(DISTINCT loan_id) FROM payments` = `SELECT COUNT(DISTINCT loan_id) FROM loan_tape`

#### Validation
After fix, run: `SANITY-057: Payments Match Loan Count` → Expected: < 100 violations (allow small discrepancies)

---

## Phase 2 Additional Fixes: Missing Columns (17 Skipped Checks)

### Fix 5: loan_tape Missing Columns

#### 5a. funding_date
**Current:** Column missing or NULL
**Fix:** Set `funding_date = decision_date + random(1-7 days)` for approved loans

```python
loan_tape_df = loan_tape_df.with_columns([
    (pl.col("decision_date") + pl.duration(days=pl.col("funding_delay_days"))).alias("funding_date")
])
```

#### 5b. interest_rate
**Current:** Column missing or NULL
**Fix:** Generate interest rate based on FICO score and DTI

```python
def calculate_interest_rate(fico_score, dti_ratio):
    """
    Interest rate pricing curve:
    - Excellent (750+): 6-8%
    - Good (700-749): 8-12%
    - Fair (650-699): 12-18%
    - Poor (640-649): 18-25%
    """
    base_rate = 0.15  # 15% baseline
    fico_adjustment = (750 - fico_score) * 0.001  # -0.1% per FICO point above 750
    dti_adjustment = dti_ratio * 0.10  # +10% for 100% DTI
    rate = base_rate + fico_adjustment + dti_adjustment
    return max(0.06, min(0.25, rate))  # Clamp to [6%, 25%]
```

#### 5c. original_loan_term
**Current:** Column missing or NULL
**Fix:** Generate realistic loan terms (24, 36, 48, 60 months)

```python
loan_term_distribution = {
    24: 0.10,
    36: 0.30,
    48: 0.35,
    60: 0.25
}
loan_tape_df = loan_tape_df.with_columns([
    pl.Series("original_loan_term", random.choices(
        population=[24, 36, 48, 60],
        weights=[0.10, 0.30, 0.35, 0.25],
        k=len(loan_tape_df)
    ))
])
```

#### 5d. scheduled_payment_amount
**Current:** Column missing or NULL
**Fix:** Calculate using proper amortization formula

```python
def calculate_monthly_payment(principal, annual_rate, term_months):
    """
    Standard amortization formula:
    M = P * [r(1+r)^n] / [(1+r)^n - 1]
    """
    monthly_rate = annual_rate / 12
    payment = principal * (monthly_rate * (1 + monthly_rate)**term_months) / \
              ((1 + monthly_rate)**term_months - 1)
    return round(payment, 2)

loan_tape_df = loan_tape_df.with_columns([
    pl.struct(["original_loan_amount", "interest_rate", "original_loan_term"])
      .map_elements(lambda x: calculate_monthly_payment(
          x["original_loan_amount"],
          x["interest_rate"],
          x["original_loan_term"]
      )).alias("scheduled_payment_amount")
])
```

### Fix 6: payments Missing Columns

#### 6a. interest_accrued
**Current:** Column missing or NULL
**Fix:** Calculate based on principal balance and interest rate

```python
def calculate_interest_accrued(principal_balance, annual_rate, days=30):
    """
    Simple interest: I = P * r * t
    """
    daily_rate = annual_rate / 365
    interest = principal_balance * daily_rate * days
    return round(interest, 2)

# Join with loan_tape to get balance and rate
payments_df = payments_df.join(
    loan_tape_df.select(["loan_id", "snapshot_date", "current_principal_balance", "interest_rate"]),
    on=["loan_id", "snapshot_date"],
    how="left"
).with_columns([
    pl.struct(["current_principal_balance", "interest_rate"])
      .map_elements(lambda x: calculate_interest_accrued(
          x["current_principal_balance"],
          x["interest_rate"]
      )).alias("interest_accrued")
])
```

#### 6b. snapshot_date in payments
**Current:** Column missing
**Fix:** Set to payment_due_date for temporal joins

```python
payments_df = payments_df.with_columns([
    pl.col("payment_due_date").alias("snapshot_date")
])
```

### Fix 7: fraud_verification Missing Columns

#### 7a. fraud_check_status
**Current:** Column missing or NULL
**Fix:** Set based on fraud_risk_score and decision

```python
def determine_fraud_check_status(fraud_risk_score, is_approved):
    """
    PASSED: Low risk (< 400) and approved
    FLAGGED: Medium risk (400-600)
    FAILED: High risk (> 600) or declined for fraud
    """
    if fraud_risk_score < 400 and is_approved:
        return "PASSED"
    elif fraud_risk_score > 600:
        return "FAILED"
    else:
        return "FLAGGED"

fraud_df = fraud_df.with_columns([
    pl.struct(["fraud_risk_score", "decision_status"])
      .map_elements(lambda x: determine_fraud_check_status(
          x["fraud_risk_score"],
          x["decision_status"] == "APPROVED"
      )).alias("fraud_check_status")
])
```

#### 7b. fraud_risk_score
**Current:** Column missing or NULL
**Fix:** Generate score in [0, 999] correlated with approval

```python
def generate_fraud_risk_score(is_approved):
    """
    Approved apps: Low risk (50-300, mean 150)
    Declined apps: Mixed risk (200-800, mean 500)
    """
    if is_approved:
        score = random.normalvariate(150, 80)
    else:
        score = random.normalvariate(500, 200)
    return int(max(0, min(999, score)))
```

#### 7c. income_verification_status
**Current:** Column missing or NULL
**Fix:** Set to VERIFIED/UNVERIFIED/PENDING

```python
income_verification_distribution = {
    "VERIFIED": 0.70,      # 70% verified
    "UNVERIFIED": 0.20,    # 20% unverified
    "PENDING": 0.10        # 10% pending
}
```

#### 7d. employment_verification_status
**Current:** Column missing or NULL
**Fix:** Set to VERIFIED/UNVERIFIED/PENDING

```python
employment_verification_distribution = {
    "VERIFIED": 0.65,      # 65% verified
    "UNVERIFIED": 0.25,    # 25% unverified
    "PENDING": 0.10        # 10% pending
}
```

### Fix 8: credit_reports Missing Columns

#### 8a. inquiries_last_6mo_count
**Current:** Column missing or NULL
**Fix:** Generate realistic inquiry counts

```python
def generate_inquiry_count(is_approved, fico_score):
    """
    Approved + High FICO: 1-3 inquiries (careful shoppers)
    Declined + Low FICO: 5-15 inquiries (credit seeking behavior)
    """
    if is_approved and fico_score > 700:
        return random.randint(1, 3)
    elif not is_approved and fico_score < 650:
        return random.randint(5, 15)
    else:
        return random.randint(2, 7)
```

---

## Phase 3: Regeneration & Validation

### Step 1: Backup Current Flawed Dataset
```bash
cd ~/Downloads/sherpaiq_lc/data_domain/lendco/raw/data
tar -czf ~/Downloads/flawed_dataset_v1.0_backup.tar.gz *.parquet
```

### Step 2: Regenerate with Fixed Code
```bash
cd ~/Downloads
python3 src/reference_generator.py
python3 src/data_generator.py
```

### Step 3: Run Complete Validation Suite
```bash
python3 complete_sanity_validator_1M.py sherpaiq_lc/data_domain/lendco/raw/data
```

### Step 4: Expected Results
- ✅ All 60 checks executable (0 skipped due to missing columns)
- ✅ All 60 checks pass (0 failures)
- ✅ 100% validation success rate

---

## Phase 4: Final QA & Release

### Checklist
- [ ] All 4 critical failures resolved
- [ ] All 17 missing columns populated
- [ ] All 60 sanity checks passing
- [ ] Extended validation suite (75+ checks) passing
- [ ] Statistical realism checks passing
- [ ] Documentation updated
- [ ] Dataset versioned as v2.0
- [ ] GitHub release created with:
  - Validation report
  - Generation statistics
  - Comparison vs v1.0
  - Download instructions

### Success Criteria
✅ **Dataset v2.0 is production-ready when:**
1. Zero sanity check failures
2. Zero missing/invalid columns
3. Statistical distributions match real-world lending data
4. Passes regulatory compliance checks
5. User acceptance testing complete

---

## Timeline Estimate

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| Phase 1 | Analysis & Planning | ✅ Complete (2 hours) |
| Phase 2 | Code Fixes | 🟡 4-6 hours |
| Phase 3 | Regeneration & Validation | ⚪ 1-2 hours |
| Phase 4 | Final QA & Release | ⚪ 1 hour |
| **Total** | **End-to-End** | **8-11 hours** |

---

## Contact & Support

**Questions?** Refer to:
- `VALIDATION_REPORT_1M_DATASET.md` - Detailed findings
- `docs/comprehensive_data_integrity_checks.md` - All 75+ checks explained
- `docs/SANITY_CHECKS_Foundation.md` - 60 sanity checks specification

**Updates:** This document will be updated as remediation progresses.

---

**Status:** 🟡 Phase 2 Ready to Start
**Last Updated:** 2026-01-09
**Next Action:** Begin code fixes in `src/data_generator.py`
