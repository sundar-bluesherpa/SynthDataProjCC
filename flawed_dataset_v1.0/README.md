# Flawed Dataset v1.0 - DO NOT USE FOR PRODUCTION

⚠️ **WARNING: This dataset contains known data quality issues and should NOT be used for:**
- Model training
- Production analytics
- System integration
- Regulatory compliance demonstration

## Purpose
This directory documents the **first attempt** at generating the 1M LendCo synthetic dataset, preserved for:
1. **Learning** - Understanding what went wrong in initial generation
2. **Comparison** - Benchmarking improvements in remediated version
3. **Audit Trail** - Complete project history documentation

## Dataset Information

**Generated:** 2026-01-09
**Version:** 1.0 (Flawed)
**Total Records:** 16,437,510 rows across 8 tables
**Configuration:** 1,000,000 applications, 40% approval rate, 95% funding rate

### Dataset Statistics

| Table | Rows | Columns | Status |
|-------|------|---------|--------|
| applications | 1,000,000 | 182 | ✅ |
| loan_tape | 6,783,779 | 120 | ⚠️ |
| payments | 5,827,988 | 54 | ⚠️ |
| credit_reports | 1,000,000 | 322 | ✅ |
| credit_tradelines | 1,624,643 | 90 | ✅ |
| fraud_verification | 1,000,000 | 104 | ❌ |
| bank_transactions | 100 | 69 | ❌ |
| reference_codes | N/A | 13 | ✅ |

## Known Issues (4 Critical Failures)

### 🚨 FAILURE 1: SANITY-011 - Delinquent Loans Without Missed Payments
**Impact:** 169,351 loans (25% of all delinquent loans)
**Description:** Loans marked as DELINQUENT_30/60/90/120 but have no missed payment records

### 🚨 FAILURE 2: SANITY-043 - Open Trades > Total Trades
**Impact:** 22,948 credit reports (2.3% of all applications)
**Description:** Credit reports showing more open trades than total trades (logical impossibility)

### 🚨 FAILURE 3: SANITY-047 - Invalid Identity Verification Scores
**Impact:** 1,000,000 records (100% of fraud_verification table)
**Description:** All identity_verification_score values outside valid 0-100 range

### 🚨 FAILURE 4: SANITY-057 - Loans Without Payment Records
**Impact:** 6,035 loans (1.7% of funded loans)
**Description:** Funded loans with zero payment records

## Missing/Invalid Columns (17 Skipped Checks)

**loan_tape:** funding_date, interest_rate, original_loan_term, scheduled_payment_amount
**payments:** interest_accrued, snapshot_date
**fraud_verification:** fraud_check_status, fraud_risk_score, income_verification_status, employment_verification_status
**credit_reports:** inquiries_last_6mo_count

## Validation Results

- ✅ **Passed:** 39/43 checks (90.7%)
- ❌ **Failed:** 4/43 checks (9.3%)
- ⚠️ **Skipped:** 17 checks (missing columns)

**Detailed Report:** See `../VALIDATION_REPORT_1M_DATASET.md`
**Raw Results:** See `../validation_results/complete_sanity_check_results.csv`

## Dataset Location

⚠️ **Note:** Due to file size (~15GB total), the actual .parquet files are NOT stored in this Git repository.

**Original Location:**
```
~/Downloads/sherpaiq_lc/data_domain/lendco/raw/data/
```

**To Regenerate This Flawed Version:**
```bash
cd ~/Downloads
git checkout v1.0-flawed  # Tag for original generator code
python3 src/reference_generator.py
python3 src/data_generator.py
```

## What's Next

See `REMEDIATION_PLAN.md` for detailed fix strategy.
The remediated dataset will be versioned as v2.0.

---

**Status:** 🔴 DEPRECATED - Use remediated v2.0 dataset instead
**Preserved:** For historical reference and learning purposes only
