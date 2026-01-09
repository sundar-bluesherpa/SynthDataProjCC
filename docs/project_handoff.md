# Project Handoff: Synthetic Data QA & Validation

## 1. Project Overview
**LendCo Synthetic Data Engine**
A high-fidelity simulation generating 1 Million+ credit applications and their associated performance data (Loan Tape, Payments, Credit Reports).
The system uses "Gen 2" dynamic transition matrices and a "Gaussian Copula" for realistic correlation.

## 2. Current State
- **Scale**: Configured for 1,000,000 applications (`src/config.json`).
- **Schema**: Fully hydrated 955 columns across 8 tables (output to `sherpaiq_lc/.../raw/data`).
- **Hydration Logic**: `ExtendedDataGenerator` (in `src/data_generator.py`) dynamically reads CSV schemas and backfills missing columns using smart heuristics (defaults, logical derivations).

## 3. Objective for Next Workspace
**Thoroughly Vet Data & Expand Integrity Checks**
The current validation suite (`src/validation_framework.py`) covers 12 core checks. The goal is to expand this to a comprehensive "Deep QA" suite.

### Areas for Deep Dive:
1.  **Hydration Logic Audit**:
    *   Review the heuristics in `data_generator.py`. Are they realistic?
    *   Example: `delinquency_30day_count` is defaulted to 0. Should it correlate with `status=Delinquent`?
2.  **Cross-Column Consistency**:
    *   Does `months_since_last_delinquency` match the `delinquency_history` string?
    *   Does `current_balance` match the sum of recent payments vs original amount?
3.  **Cross-Table Integrity**:
    *   Does `credit_reports.fico_score` match `applications.fico_score`?
    *   Do `payments.payment_date` align with `loan_tape.snapshot_date` logic?
4.  **Schema Exhaustiveness**:
    *   Confirm mapped data types (polars intrerpretation) match business expectations.

## 4. Key Files & Artifacts
| File | Purpose |
| :--- | :--- |
| `src/reference_generator.py` | **Step 1**: Generates valid, correlated Application data (Seed). |
| `src/data_generator.py` | **Step 2**: Simulates loan performance, hydrates full schema, saves Parquet. |
| `src/validation_framework.py` | **QA Suite**: The current script running 12 integrity checks. **Start Here**. |
| `src/generate_data_dictionary.py` | Generates the Excel Dictionary from schemas. |
| `sherpaiq_lc/.../schemas/*.csv` | **Source of Truth** for the 955 columns. |

## 5. How to Run
1.  **Regenerate Data** (if needed):
    ```bash
    python3 src/reference_generator.py
    python3 src/data_generator.py
    ```
2.  **Run Validation**:
    ```bash
    python3 src/validation_framework.py
    ```

## 6. Known Issues / Context
- **Hydration Heuristics**: Many columns use "Safe Defaults" (e.g. 0 or NULL). These technically satisfy the schema but may lack "Business Depth". The new agent should identify where more complex logic is needed to simulate realistic "dirty data" or secondary attributes.
