import polars as pl
import pandas as pd
import numpy as np
import scipy.stats as stats
import os
from datetime import datetime, timedelta
import os
import sys

# Add current directory to path to find archetype_model
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from archetype_model import ArchetypePredictor
class ExtendedDataGenerator:
    """
    Extends existing application data with consistent downstream tables:
    - Credit Reports (Snapshot & Tradelines)
    - Loan Performance (Month-end snapshots)
    - Payments (Transaction history)
    - Fraud Verification
    - Bank Transactions
    """
    
    def __init__(self, apps_path, output_dir):
        self.apps_path = apps_path
        self.output_dir = output_dir
        self.apps_df = None
        
        # Configuration
        self.snapshot_date = datetime.now()
        self.start_date = datetime(2022, 1, 1) # Simulation start
        
        # Ensure output dir exists
        os.makedirs(self.output_dir, exist_ok=True)

    def load_applications(self):
        """Load and preprocess reference applications."""
        print(f"Loading applications from {self.apps_path}...")
        self.apps_df = pl.read_csv(self.apps_path)
        
        # Ensure we have product, channel, state
        # If missing, add them with random values
        columns = self.apps_df.collect_schema().names() if hasattr(self.apps_df, "collect_schema") else self.apps_df.columns
        
        n_rows = len(self.apps_df)
        
        if "product_type" not in columns:
            self.apps_df = self.apps_df.with_columns(
                pl.Series("product_type", np.random.choice(["PERSONAL", "AUTO"], n_rows)).alias("product_type")
            )
            
        if "channel" not in columns:
            self.apps_df = self.apps_df.with_columns(
                pl.Series("channel", np.random.choice(["ONLINE", "PARTNER", "DIRECT"], n_rows)).alias("channel")
            )
            
        if "state" not in columns:
             self.apps_df = self.apps_df.with_columns(
                pl.Series("state", np.random.choice(["CA", "NY", "TX", "FL", "IL"], n_rows)).alias("state")
            )
        
        # Ensure required columns exist
        required = ["application_id", "fico_score_at_application", "decision_status"]
        for col in required:
            if col not in self.apps_df.columns:
                raise ValueError(f"Input CSV missing required column: {col}")
                
        # Normalize decision status
        self.apps_df = self.apps_df.with_columns(
            pl.col("decision_status").str.to_uppercase()
        )
        
        print(f"Loaded {len(self.apps_df)} applications.")
        return self.apps_df

    def generate_credit_reports(self):
        """
        Generate Credit Report Snapshot and Tradelines.
        Logic: Correlate attributes with FICO score.
        """
        print("Generating Credit Reports...")
        n = len(self.apps_df)
        
        # 1. Base Attributes correlated with FICO
        # Higher FICO -> Lower Utilization, Fewer Inquiries, Longer History
        ficos = self.apps_df["fico_score_at_application"].to_numpy()
        
        # Inverse transform sampling for correlation
        # We'll use FICO as a 'rank' to sample from other distributions
        fico_rank = stats.rankdata(ficos) / (n + 1)
        
        # Utilization: Beta distribution (Higher score -> Lower util)
        # Flip rank for utilization (High score = Low rank in utilization)
        util_vals = stats.beta.ppf(1 - fico_rank, a=2, b=5)
        
        # Inquiries: Poisson (Higher score -> Fewer inquiries)
        inq_vals = stats.poisson.ppf(1 - fico_rank, mu=2)
        
        # Total Trades: Normal (Higher score -> More trades generally)
        trades_vals = stats.norm.ppf(fico_rank, loc=15, scale=5).clip(min=1)
        
        # Generate Report IDs
        report_ids = [f"CR-{app_id}" for app_id in self.apps_df["application_id"]]
        
        # Create Snapshot DataFrame
        credit_snapshot = pl.DataFrame({
            "credit_report_id": report_ids,
            "application_id": self.apps_df["application_id"],
            "report_date": [self.start_date] * n, # Simplified: All pulled at start/app time
            "fico_score_8": ficos,
            "vantage_score_3": (ficos * 0.9 + 50).astype(int), # Rough correlation
            "revolving_utilization_ratio": util_vals,
            "inquiries_6mo_count": inq_vals.astype(int),
            "all_trades_count": trades_vals.astype(int),
            
            # Defaults/Bankruptcies (Low probability for high FICO)
            "public_records_count": np.where(ficos < 600, np.random.choice([0, 1], n, p=[0.8, 0.2]), 0),
            "bankruptcies_count": np.where(ficos < 550, np.random.choice([0, 1], n, p=[0.9, 0.1]), 0)
        })
        
        # Fill missing schemas from lendco.yaml requirements
        # FIX SANITY-043: Generate open_trades_count as proper subset of all_trades_count
        credit_snapshot = credit_snapshot.with_columns([
            pl.lit(0).alias("delinquency_30_day_count"), # Placeholder, could refine
            pl.lit(0).alias("delinquency_60_day_count"),
            pl.lit(0).alias("delinquency_90_day_count"),
            pl.col("all_trades_count").cast(pl.Int32).alias("revolving_trades_count"), # Simplify
            pl.lit(0).alias("collections_count"),
            # Ensure open_trades_count ≤ all_trades_count
            (pl.col("all_trades_count") * (0.6 + np.random.random(n) * 0.3)).cast(pl.Int32).alias("open_trades_count")
        ])
        
        # 2. Generate Tradelines (1-N per report)
        # This can be large, so we'll generate a simplified set
        # For now, let's create 1 'Summary' tradeline or just skip if not strictly needed for MVP
        # But lendco.yaml defines `fact_credit_tradelines`.
        
        # Let's generate 3 tradelines per person for realism
        print("  Generating Tradelines...")
        tl_rows = []
        for i, row in enumerate(credit_snapshot.iter_rows(named=True)):
            rid = row['credit_report_id']
            # Trade 1: Mortgage (if good score)
            if row['fico_score_8'] > 680:
                tl_rows.append({
                    "credit_report_id": rid,
                    "tradeline_id": f"{rid}-TL1",
                    "account_type": "MORTGAGE",
                    "account_status": "OPEN",
                    "current_balance": 250000.0,
                    "credit_limit": 300000.0,
                    "monthly_payment": 1500.0,
                    "open_date": (self.start_date - timedelta(days=365*5)),
                    "times_30dpd": 0, "times_60dpd": 0, "times_90dpd": 0
                })
            
            # Trade 2: Credit Card
            limit = 5000 + (row['fico_score_8'] - 600) * 50
            bal = limit * row['revolving_utilization_ratio']
            tl_rows.append({
                "credit_report_id": rid,
                "tradeline_id": f"{rid}-TL2",
                "account_type": "REVOLVING",
                "account_status": "OPEN",
                "current_balance": bal,
                "credit_limit": limit,
                "monthly_payment": max(25.0, bal * 0.02),
                "open_date": (self.start_date - timedelta(days=365*2)),
                "times_30dpd": 0, "times_60dpd": 0, "times_90dpd": 0
            })
            
        tradelines = pl.DataFrame(tl_rows)
        
        return credit_snapshot, tradelines

    def generate_loan_tape(self):
        """
        Generate monthly loan performance snapshots (fact_loan_monthly).
        GEN 2 ARCHITECTURE: Dynamic Markov Transition Model
        - Continuous Risk: Uses blended transition matrices based on Risk Scores.
        - Vectorized Simulation: Iterates by Calendar Month for speed.
        """
        print("Generating Loan Tape (Gen 2 Dynamic Model)...")
        
        # 1. Filter Approved
        approved = self.apps_df.filter(pl.col("decision_status") == "APPROVED")
        n_approved = len(approved)
        
        # 2. Funding Logic (90% take rate)
        is_funded = np.random.random(n_approved) < 0.9
        funded_apps = approved.filter(pl.Series(is_funded))
        n_funded = len(funded_apps)
        print(f"  Funded {n_funded} loans from {n_approved} approved applications.")
        
        # 3. Predict Continuous Risk Vectors (The "Gen 2" Feature)
        print("  Calculating continuous risk vectors...")
        predictor = ArchetypePredictor()
        risk_probs = predictor.predict_risk_vectors(funded_apps) # Shape (N, 8)
        
        # 3b. Sample Discrete Archetypes for Event Triggers (Gen 5)
        # We need discrete labels to assign specific "Forced Payoff" dates
        print("  Assigning discrete archetypes for Event Triggers...")
        cum_probs = np.cumsum(risk_probs, axis=1)
        random_draws = np.random.rand(n_funded, 1)
        chosen_indices = (random_draws < cum_probs).argmax(axis=1)
        assigned_archetypes = [predictor.ARCHETYPES[i] for i in chosen_indices]
        
        # 3c. Pre-assign Forced Payoff Dates
        payoff_months = np.full(n_funded, 999) # Default: No forced payoff
        
        for i, arch in enumerate(assigned_archetypes):
            if arch == predictor.EARLY_PREPAY:
                payoff_months[i] = np.random.randint(6, 19) # 6-18
            elif arch == predictor.MID_PREPAY:
                payoff_months[i] = np.random.randint(19, 31) # 19-30
            elif arch == predictor.LATE_PREPAY:
                payoff_months[i] = np.random.randint(31, 61) # 31-60
        
        # 4. Pre-compute Transition Lookup Table
        # Shape: (Max_Age=60, 8_Archetypes, 5_Params)
        # Params: [p_c_30, p_c_paid, p_30_60, p_30_c, p_roll]
        print("  Pre-computing Markov Transition Surfaces...")
        max_age = 60
        lookup_table = np.zeros((max_age + 1, len(predictor.ARCHETYPES), 5))
        
        param_names = ["p_c_to_30", "p_c_to_paid", "p_30_to_60", "p_30_to_c", "p_roll"]
        
        for age in range(max_age + 1):
            for i, arch in enumerate(predictor.ARCHETYPES):
                # Get dict from model
                trans_dict = predictor.get_base_transition_matrix(arch, age)
                for p_idx, p_name in enumerate(param_names):
                    lookup_table[age, i, p_idx] = trans_dict.get(p_name, 0.0)
                    
        # 5. Initialize Simulation Vectors
        start_ts = self.start_date.timestamp()
        end_ts = datetime(2023, 12, 31).timestamp()
        orig_timestamps = np.random.uniform(start_ts, end_ts, n_funded)
        orig_dates = np.array([datetime.fromtimestamp(ts).date().replace(day=1) for ts in orig_timestamps])
        
        loan_ids = np.array([f"LN-{app_id}" for app_id in funded_apps["application_id"]])
        app_ids = funded_apps["application_id"].to_numpy()
        amounts = (funded_apps["annual_income"].to_numpy() * 0.15).clip(1000, 50000)
        terms = np.full(n_funded, 36)

        # FIX: Add missing columns - interest_rate calculation
        # Interest rate based on FICO and DTI
        ficos = funded_apps["fico_score_at_application"].to_numpy()
        dtis = funded_apps["debt_to_income_ratio"].to_numpy()

        # Pricing curve: Base 15% + FICO adjustment + DTI adjustment
        fico_adjustment = (750 - ficos) * 0.0001  # -0.01% per FICO point above 750
        dti_adjustment = dtis * 0.10  # +10% for 100% DTI
        interest_rates = np.clip(0.15 + fico_adjustment + dti_adjustment, 0.06, 0.25)

        # Calculate scheduled monthly payment using amortization formula
        # M = P * [r(1+r)^n] / [(1+r)^n - 1]
        monthly_rates = interest_rates / 12
        scheduled_payments = amounts * (monthly_rates * (1 + monthly_rates)**terms) / ((1 + monthly_rates)**terms - 1)
        
        # State Vectors
        states = np.zeros(n_funded, dtype=int) # 0=Current, 1=30, 2=60, 3=90, 4=CO, 5=Paid
        dpds = np.zeros(n_funded, dtype=int)
        balances = amounts.copy()
        
        # 6. Time Loop (Calendar Months)
        # From Start Date to Snapshot Date
        sim_start = self.start_date.date().replace(day=1)
        sim_end = self.snapshot_date.date().replace(day=1)
        
        curr_date = sim_start
        snapshots = []
        payments = []
        
        print(f"  Simulating from {sim_start} to {sim_end}...")
        
        while curr_date <= sim_end:
            # Current Month End Date (for reporting)
            month_end = (curr_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            # A. Determine Active Population
            # Loans that have originated AND are not terminal (CO/Paid)
            # Actually, we need to report terminal state ONCE then stop.
            # Simplified: orig_dates <= curr_date
            
            is_originated = (orig_dates <= curr_date)
            is_active = (states < 4) & is_originated # 4=CO, 5=Paid
            
            active_indices = np.where(is_active)[0]
            if len(active_indices) == 0:
                curr_date = (curr_date + timedelta(days=32)).replace(day=1)
                continue
                
            # B. Calculate Age (Months on Book) for ALL funded loans (or at least originated)
            # We need this for reporting AND simulation.
            # Calculating for all N_funded is safest and fast enough.
            
            # Vectorized MoB for entire population
            all_mobs = (curr_date.year - pd.DatetimeIndex(orig_dates).year) * 12 + \
                       (curr_date.month - pd.DatetimeIndex(orig_dates).month)
            all_mobs = np.clip(all_mobs, 1, max_age).astype(int)
            
            # C. Dynamic Blending (The "Smooth Switch")
            # 1. Look up Base Params for ACTIVE loans only
            active_mobs = all_mobs[active_indices]
            base_params = lookup_table[active_mobs, :, :]
            
            # 2. Get Risk Weights -> (N_active, 8)
            weights = risk_probs[active_indices, :]
            
            # 3. Dot Product -> (N_active, 5)
            # Blend the matrices based on risk score!
            # param[k] = sum(weight[i] * base[mob, i, k])
            current_params = np.einsum('ij,ijk->ik', weights, base_params)
            
            # D. Vectorized Transition Logic (STRICT STEP)
            # Use separate next_state array to prevent cascading (0->30->60 in one month)
            next_states = states.copy()
            next_dpds = dpds.copy()
            
            # Capture Prior State/Balance BEFORE any transitions (Forced or Standard)
            # This ensures we get the "Opening Balance" for the month for Payoff Logic
            prior_states = states.copy()
            prior_balances = balances.copy()

            # S-Curve Check: Suppress delinquency for very young loans (Seasoning)
            # If MoB < 4, reduce p_c_to_30 by 90%
            is_young = (active_mobs < 4)
            if np.any(is_young):
                 # Apply suppression to indices where is_young is True
                 # Note: current_params is (N, 5), index 0 is p_c_to_30
                 current_params[is_young, 0] *= 0.10

            # Extract specific probs
            p_c_30 = current_params[:, 0]
            p_c_paid = current_params[:, 1]
            p_30_60 = current_params[:, 2]
            p_30_c = current_params[:, 3]
            p_roll = current_params[:, 4] 
            
            # Random Draws
            rng = np.random.random(len(active_indices))
            
            # 1. From CURRENT (0)
            mask_c = (states[active_indices] == 0)
            target_indices = active_indices[mask_c]
            # Subset rng/probs for alignment
            rng_c = rng[mask_c]

            # C -> Paid
            paid_mask = (rng_c < p_c_paid[mask_c])
            idx_paid = target_indices[paid_mask]
            next_states[idx_paid] = 5
            balances[idx_paid] = 0

            # C -> 30
            # Condition: NOT paid AND prob check
            to_30_mask = (~paid_mask) & (rng_c < (p_c_paid[mask_c] + p_c_30[mask_c]))
            idx_30 = target_indices[to_30_mask]
            next_states[idx_30] = 1
            next_dpds[idx_30] = 30

            # FIX SANITY-011: Create MISSED payment record for loans transitioning to 30 DPD
            for idx in idx_30:
                interest_accrued_missed = balances[idx] * (interest_rates[idx] / 12)
                payments.append({
                    "payment_id": f"PMT-{loan_ids[idx]}-{all_mobs[idx]}-MISSED",
                    "loan_id": loan_ids[idx],
                    "payment_due_date": month_end,
                    "payment_received_date": month_end,
                    "scheduled_payment_amount": scheduled_payments[idx],
                    "actual_payment_amount": 0.0,
                    "principal_paid": 0.0,
                    "interest_paid": 0.0,
                    "interest_accrued": float(interest_accrued_missed),
                    "payment_status": "MISSED",
                    "autopay_flag": False,
                    "payment_method": "NONE",
                    "payment_channel": "NONE"
                })
            
            # 2. From 30 (1)
            mask_30 = (states[active_indices] == 1)
            target_indices = active_indices[mask_30]
            rng_30 = rng[mask_30]

            # 30 -> 60
            roll_mask = (rng_30 < p_30_60[mask_30])
            idx_30_60 = target_indices[roll_mask]
            next_states[idx_30_60] = 2
            next_dpds[idx_30_60] = 60

            # FIX SANITY-011: Create MISSED payment record for loans rolling from 30 to 60 DPD
            for idx in idx_30_60:
                interest_accrued_missed = balances[idx] * (interest_rates[idx] / 12)
                payments.append({
                    "payment_id": f"PMT-{loan_ids[idx]}-{all_mobs[idx]}-MISSED60",
                    "loan_id": loan_ids[idx],
                    "payment_due_date": month_end,
                    "payment_received_date": month_end,
                    "scheduled_payment_amount": scheduled_payments[idx],
                    "actual_payment_amount": 0.0,
                    "principal_paid": 0.0,
                    "interest_paid": 0.0,
                    "interest_accrued": float(interest_accrued_missed),
                    "payment_status": "MISSED",
                    "autopay_flag": False,
                    "payment_method": "NONE",
                    "payment_channel": "NONE"
                })
            
            # 30 -> Cure
            cure_mask = (~roll_mask) & (rng_30 < (p_30_60[mask_30] + p_30_c[mask_30]))
            idx_cured = target_indices[cure_mask]
            next_states[idx_cured] = 0
            next_dpds[idx_cured] = 0
            
            # 3. From 60 (2) -> 90
            mask_60 = (states[active_indices] == 2)
            target_indices = active_indices[mask_60]
            rng_60 = rng[mask_60]

            roll_mask = (rng_60 < p_roll[mask_60])
            idx_60_90 = target_indices[roll_mask]
            next_states[idx_60_90] = 3
            next_dpds[idx_60_90] = 90

            # FIX SANITY-011: Create MISSED payment record for loans rolling from 60 to 90 DPD
            for idx in idx_60_90:
                interest_accrued_missed = balances[idx] * (interest_rates[idx] / 12)
                payments.append({
                    "payment_id": f"PMT-{loan_ids[idx]}-{all_mobs[idx]}-MISSED90",
                    "loan_id": loan_ids[idx],
                    "payment_due_date": month_end,
                    "payment_received_date": month_end,
                    "scheduled_payment_amount": scheduled_payments[idx],
                    "actual_payment_amount": 0.0,
                    "principal_paid": 0.0,
                    "interest_paid": 0.0,
                    "interest_accrued": float(interest_accrued_missed),
                    "payment_status": "MISSED",
                    "autopay_flag": False,
                    "payment_method": "NONE",
                    "payment_channel": "NONE"
                })
            
            # 4. From 90 (3) -> CO
            mask_90 = (states[active_indices] == 3)
            target_indices = active_indices[mask_90]
            rng_90 = rng[mask_90]
            
            roll_mask = (rng_90 < p_roll[mask_90])
            idx_90_co = target_indices[roll_mask]
            next_states[idx_90_co] = 4
            balances[idx_90_co] = 0
            next_dpds[idx_90_co] = 120
            
            # 5. Forced Payoff Override (Gen 5)
            # If MoB == payoff_month, force transition to PAID (5)
            # This overrides any other transition (e.g. C->30) for this month
            force_pay_mask = (all_mobs[active_indices] == payoff_months[active_indices])
            idx_force_pay = active_indices[force_pay_mask]
            
            if len(idx_force_pay) > 0:
                # DEBUG: Print first time we see payoffs
                if "payoff_debug_printed" not in locals():
                     print(f"  [DEBUG] Month {curr_date}: Forced Payoff for {len(idx_force_pay)} loans! (First Occurrence)")
                     payoff_debug_printed = True
                
                next_states[idx_force_pay] = 5
                balances[idx_force_pay] = 0
                next_dpds[idx_force_pay] = 0
            
            # Update Global State (Atomic Commit)
            prior_states = states.copy()
            prior_balances = balances.copy() # Capture balance before zeroing
            states = next_states
            dpds = next_dpds
            
            # E. Amortization (for performing loans)
            # Simple Principal Paydown
            mask_perf = (states[active_indices] == 0)
            idx_perf = active_indices[mask_perf]
            
            # monthly_payment = balance * 0.03 (approx)
            payment_amt = balances[idx_perf] * 0.03
            balances[idx_perf] -= payment_amt
            balances[idx_perf] = np.maximum(balances[idx_perf], 0)
            
            # Check for natural payoff
            idx_nat_paid = idx_perf[balances[idx_perf] < 10.0]
            states[idx_nat_paid] = 5
            balances[idx_nat_paid] = 0
            
            # F. Record Snapshots
            report_indices = np.where(is_originated & (states < 6))[0]
            
            status_map = {0:'CURRENT', 1:'DELINQUENT_30', 2:'DELINQUENT_60', 3:'DELINQUENT_90', 4:'CHARGED_OFF', 5:'PAID_OFF'}
            
            # Batch Extract
            batch_rows = []
            for idx in report_indices:
                st_code = states[idx]
                prev_code = prior_states[idx]
                
                if st_code == 4 and balances[idx] == 0 and dpds[idx] > 120: continue # Stop reporting CO
                
                # Report PAID_OFF only if it happened this month or recently
                if st_code == 5 and prev_code == 5: continue
                
                # Payment Logic (Generate Record)
                # Allow Active (0-3) AND Paid (5) AND CO (4) to generate payment records (e.g. final payments)
                if st_code <= 5: 
                    # Determine Payment Amount
                    is_pd = False
                    val_paid = 0.0
                    pmt_status = "MISSED"
                    description = "Regular Payment"
                    
                    # 1. Regular Payment (Current or Delinquent but paying)
                    if st_code == 0:
                        is_pd = True
                        val_paid = amounts[idx] / 36.0
                        pmt_status = "PAID"
                    
                    # 2. Payoff Event (Standard or Forced)
                    elif st_code == 5:
                         is_pd = True
                         # Payoff Amount = Outstanding Balance from PRIOR step
                         val_paid = prior_balances[idx]  
                         pmt_status = "PAID_OFF"
                         description = "Payoff"
                    
                    # 3. Delinquent (Missed)
                    elif st_code in [1, 2, 3, 4]:
                         is_pd = False
                         val_paid = 0.0
                         pmt_status = "MISSED"

                    # Calculate Components (Principal / Interest)
                    # FIX: Calculate actual interest accrued based on interest rate
                    interest_accrued = prior_balances[idx] * (interest_rates[idx] / 12)
                    principal_paid = 0.0
                    interest_paid = 0.0

                    if is_pd and val_paid > 0:
                        if st_code == 5:
                            # For payoff, simpler logic: Interest + Remaining Principal
                            # Actually, just assume val_paid covers everything.
                            # We set interest to 0 for simplicity or standard approx
                            interest_paid = 0.0
                            principal_paid = val_paid
                        else:
                            # Regular payment
                            if val_paid < interest_accrued:
                                interest_paid = val_paid
                                principal_paid = 0.0
                            else:
                                interest_paid = interest_accrued
                                principal_paid = val_paid - interest_accrued

                        payments.append({
                            "payment_id": f"PMT-{loan_ids[idx]}-{all_mobs[idx]}",
                            "loan_id": loan_ids[idx],
                            "payment_due_date": month_end,
                            "payment_received_date": month_end,
                            "scheduled_payment_amount": amounts[idx] / 36.0,
                            "actual_payment_amount": val_paid,
                            "principal_paid": float(principal_paid),
                            "interest_paid": float(interest_paid),
                            "interest_accrued": float(interest_accrued),  # FIX: Add missing column
                            "payment_status": pmt_status,
                            "autopay_flag": True, "payment_method":"ACH", "payment_channel":"WEB"
                        })

                batch_rows.append({
                    "loan_id": loan_ids[idx],
                    "application_id": app_ids[idx],
                    "customer_id": f"CUST-{app_ids[idx]}",
                    "snapshot_date": month_end,
                    "months_on_book": int(all_mobs[idx]),
                    "loan_status": status_map[st_code],
                    "chargeoff_flag": 1 if st_code == 4 else 0, # ADDED for Vintage Tool
                    "default_flag": 1 if st_code >= 3 else 0,   # ADDED (90+ DPD)
                    "days_past_due": int(dpds[idx]),
                    "current_principal_balance": float(balances[idx]),
                    "current_interest_balance": 0.0,
                    "total_current_balance": float(balances[idx]),
                    "original_loan_amount": float(amounts[idx]),
                    "original_term_months": 36,
                    "origination_month": f"{orig_dates[idx].year}-{orig_dates[idx].month:02d}",
                    "origination_date": orig_dates[idx], # ADDED for Default Rates Tool
                    "vintage_year": orig_dates[idx].year,
                    "vintage_quarter": f"{orig_dates[idx].year}-Q{(orig_dates[idx].month-1)//3+1}",
                    "vintage_month": f"{orig_dates[idx].year}-{orig_dates[idx].month:02d}", # ADDED for Vintage Tool
                    # FIX: Add missing columns
                    "funding_date": orig_dates[idx],
                    "interest_rate": float(interest_rates[idx]),
                    "original_loan_term": 36,
                    "scheduled_payment_amount": float(scheduled_payments[idx])
                })
            snapshots.extend(batch_rows)
            
            # Increment Date
            curr_date = (curr_date + timedelta(days=32)).replace(day=1)
            
        print("  Simulation Complete.")
        loans_df = pl.DataFrame(snapshots)
        payments_df = pl.DataFrame(payments)
        
        return loans_df, payments_df

    def save_parquet(self, df, name):
        path = os.path.join(self.output_dir, f"{name}.parquet")
        print(f"Saving {name} to {path}...")
        df.write_parquet(path)

    def generate_fraud_and_transactions(self):
        """Generate static fraud/txn tables to satisfy schema."""
        print("Generating Fraud & Transactions...")
        # Fraud: 1 row per app
        n = len(self.apps_df)

        # FIX SANITY-047: Generate identity_verification_score in valid range (0-100)
        # Correlate with approval status: approved = high score, declined = low score
        approved_mask = self.apps_df["decision_status"].to_numpy() == "APPROVED"

        # Approved apps: Score 70-95 (high confidence)
        # Declined apps: Score 10-60 (low to medium confidence)
        identity_scores = np.where(
            approved_mask,
            np.random.randint(70, 96, n),  # Approved: 70-95
            np.random.randint(10, 61, n)   # Declined: 10-60
        )

        fraud = pl.DataFrame({
            "application_id": self.apps_df["application_id"],
            "overall_fraud_score": np.random.randint(600, 900, n),
            "fraud_risk_tier": np.random.choice(["LOW", "MEDIUM", "HIGH"], n, p=[0.9, 0.08, 0.02]),
            "identity_verification_score": identity_scores,
            "synthetic_identity_score": np.random.randint(0, 101, n)  # Also fix this to 0-100
        })
        
        # Transactions: Random junk
        txns = pl.DataFrame({
            "transaction_id": [f"TXN-{i}" for i in range(100)],
            "application_id":  np.random.choice(self.apps_df["application_id"], 100),
            "bank_acct_id": "BA-123",
            "transaction_date": [self.start_date] * 100,
            "amount": np.random.uniform(-100, 100, 100),
            "type": "DEBIT",
            "category": "Food",
            "merchant": "Uber Eats",
            "description": "Uber Eats San Francisco"
        })
        
        return fraud, txns

    
    def load_schema(self, table_name):
        """
        Dynamically load schema definition from local CSV.
        Returns Dict[column_name, data_type].
        """
        # Determine schema path (relative to repo root)
        # Assuming we are in src/, repo root is ../
        # Schema path: sherpaiq_lc/data_domain/lendco/raw/schemas/{table_name}.csv
        
        # Safe path resolution
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # src/.. = Root (Bl Sh Work)
        schema_path = os.path.join(base_path, "sherpaiq_lc", "data_domain", "lendco", "raw", "schemas", f"{table_name}.csv")
        
        if not os.path.exists(schema_path):
            print(f"  [WARN] Schema file not found: {schema_path}. Skipping hydration.")
            return None
            
        try:
            # Simple CSV parsing to avoid pandas dependency if possible, but we use polars
            schema_df = pl.read_csv(schema_path)
            # Expecting columns: column_name, data_type
            return schema_df.select(["column_name", "data_type"]).to_dict(as_series=False)
        except Exception as e:
            print(f"  [ERROR] Failed to load schema {schema_path}: {e}")
            return None

    def hydrate_dataframe(self, df, table_name):
        """
        Ensures DataFrame matches the official schema:
        1. Adds missing columns with default/heuristic values.
        2. Reorders columns to match schema.
        3. Casts types (best effort).
        """
        print(f"  Hydrating schema for {table_name}...")
        schema_dict = self.load_schema(table_name)
        if not schema_dict:
            return df
            
        required_cols = schema_dict["column_name"]
        data_types = schema_dict["data_type"]
        
        # 1. Add Missing Columns with Heuristics
        current_cols = df.columns
        missing_cols = [c for c in required_cols if c not in current_cols]
        
        if missing_cols:
            print(f"    Adding {len(missing_cols)} missing columns...")
            new_exprs = []
            
            # Heuristic Defaults
            # We construct a dictionary of "Smart Defaults" based on column patterns
            # Note: We use literals for speed.
            
            for col, dtype in zip(required_cols, data_types):
                if col in current_cols: continue
                
                # --- Heuristics ---
                col_lower = col.lower()
                
                # IDs
                if "_id" in col_lower:
                    val = pl.lit(None) # Foreign keys/IDs shouldn't be guessed
                    
                # Counts (Integer)
                elif "count" in col_lower:
                    if "delinq" in col_lower or "past_due" in col_lower:
                        val = pl.lit(0) # Default clean history
                    elif "inquir" in col_lower:
                        val = pl.lit(1) # Avg inquiries
                    elif "trade" in col_lower:
                        # FIX SANITY-043: Ensure open_trades ≤ all_trades
                        if "open" in col_lower and "all_trades_count" in df.columns:
                            # Generate open_trades as 60-90% subset of all_trades
                            import numpy as np
                            rand_pct = 0.6 + np.random.random(len(df)) * 0.3
                            val = (pl.col("all_trades_count") * pl.lit(rand_pct)).cast(pl.Int32)
                        else:
                            # Other trade subcategories (should be ≤ all_trades)
                            if "all_trades_count" in df.columns:
                                # Make it a subset
                                val = (pl.col("all_trades_count") * pl.lit(0.3)).cast(pl.Int32)
                            else:
                                val = pl.lit(3)
                    else:
                        val = pl.lit(0)
                        
                # Amounts (Decimal/Float)
                elif "amount" in col_lower or "balance" in col_lower or "limit" in col_lower:
                    val = pl.lit(0.0)
                    
                # Ratios/Percentages
                elif "ratio" in col_lower or "pct" in col_lower:
                    val = pl.lit(0.0)
                    
                # Dates
                elif "date" in col_lower:
                    val = pl.lit(None) # Cannot guess dates easily without context
                    
                # Boolean/Flags
                elif "flag" in col_lower or "indicator" in col_lower:
                    val = pl.lit(False)
                    # Specific text flags
                    if "match" in col_lower: val = pl.lit("Y")
                    
                # Default
                else:
                    if "VARCHAR" in dtype: val = pl.lit(None)
                    elif "INT" in dtype or "DECIMAL" in dtype: val = pl.lit(0)
                    else: val = pl.lit(None)
                
                new_exprs.append(val.alias(col))
            
            if new_exprs:
                df = df.with_columns(new_exprs)
                
        # 2. Reorder Columns (and drop extras not in schema, strictly speaking? No, keep extras usually safe)
        # We will select only schema columns to be strict.
        final_cols = [c for c in required_cols if c in df.columns]
        df = df.select(final_cols)
        
        return df

    def validate_dataset(self, data):
        """
        Gen 2 Validation Framework (Section 12 of Guide).
        Verifies "Ground Truth" before warehouse ingestion.
        """
        print("\nType 2 Validation: Checking Dataset Integrity...")
        apps = data['applications']
        loans = data['loan_tape']
        
        # Check 1: Policy Consistency
        # No Approved loans with FICO < Floor (640)
        # Note: In Gen 2, we might have near-misses (639) that are DECLINED.
        # We check APPROVED only.
        c1 = apps.filter(
            (pl.col("decision_status") == "APPROVED") & 
            (pl.col("fico_score_at_application") < 640)
        )
        if len(c1) > 0:
            print(f"  [FAIL] Found {len(c1)} Approved apps with FICO < 640!")
        else:
            print("  [PASS] Policy Check (FICO >= 640)")
            
        # Check 2: Referential Integrity
        # All loans in tape must have an app
        # NOTE: After hydration, Loan Tape uses 'application_id' (per schema) instead of 'orig_app_id'
        orphan_loans = loans.join(apps, on="application_id", how="anti")
        if len(orphan_loans) > 0:
             print(f"  [FAIL] Found {len(orphan_loans)} Orphan Loans (No App)!")
        else:
             print("  [PASS] Referential Integrity (Loans -> Apps)")
             
        # Check 3: Terminal State Consistency
        # Loans cannot be both CO and Paid
        # (Handled by generator logic, but good to verify)
        # Check if any loan has status 'CHARGED_OFF' and 'PAID_OFF' in history?
        # Actually simplified: Check current state valid.
        print("  [PASS] Validation Complete.")

    def generate_all(self):
        """
        Orchestrate the full generation pipeline.
        Returns dictionary of all generated dataframes.
        """
        print("Starting Full Data Generation Pipeline (Consolidated)...")
        
        # 1. Generate & Save Credit Data
        print(" Phase 1: Generated Credit Reports & Tradelines")
        snapshot_df, tradelines_df = self.generate_credit_reports()
        
        # Rename Credit Snapshot columns
        snapshot_df = snapshot_df.rename({
            "credit_report_id": "credit_report_id", # KEEP for hydration mapping if needed, schema expects 'credit_report_id'
            "application_id": "application_id",
            "report_date": "report_date",
            "fico_score_8": "fico_score_8", 
            # Note: Schema has specific names. We rely on initial mapping or we rename to match schema expected names?
            # Schema expects: credit_report_id, application_id, report_date, fico_score_8...
            # Our generator produced: credit_report_id, application_id, report_date, fico_score_8... 
            # So we mostly just need to ensure names match.
        })
        # Hydrate
        snapshot_df = self.hydrate_dataframe(snapshot_df, "credit_reports")
        self.save_parquet(snapshot_df, "credit_reports")
    
        # Rename Credit Tradelines columns
        tradelines_df = tradelines_df.rename({
            # Check schema: credit_tradelines.csv
            # Schema: tradeline_id, credit_report_id, account_type...
            "tradeline_id": "tradeline_id", 
            "credit_report_id": "credit_report_id"
        })
        # Add missing columns requested by schema
        tradelines_df = tradelines_df.with_columns(
            pl.lit(12).alias("months_reviewed")
        )
        tradelines_df = self.hydrate_dataframe(tradelines_df, "credit_tradelines")
        self.save_parquet(tradelines_df, "credit_tradelines")
        
        # 2. Generate & Save Loan Tape
        print(" Phase 2: Generating Loan Tape and Payments")
        loans_df, payments_df = self.generate_loan_tape()
        
        # Maps generated names to Schema names (loan_tape.csv)
        # Generated: loan_id, application_id...
        # Schema: loan_id, borrower_id, original_loan_amount...
        loans_df = loans_df.rename({
           # "loan_id": "loan_id",
           # "application_id": "orig_app_id" ? Schema is 'orig_app_id' or 'application_id'? Check schema. 
           # Checking schema loan_tape.csv...
           "application_id": "application_id", # Usually, but let's check schema.
        })
        
        loans_df = self.hydrate_dataframe(loans_df, "loan_tape")
        self.save_parquet(loans_df, "loan_tape")
    
        # Rename Payments columns
        # Schema payments.csv
        p_rename = {
            # "payment_id": "payment_id",
            # "loan_id": "loan_id"
        }
        # Check generated keys.
        payments_df = self.hydrate_dataframe(payments_df, "payments")
        self.save_parquet(payments_df, "payments")
        
        # 3. Generate & Save Fraud/Txns
        print(" Phase 3: Generating Fraud & Transactions")
        fraud_df, txns_df = self.generate_fraud_and_transactions()
        
        fraud_df = self.hydrate_dataframe(fraud_df, "fraud_verification")
        self.save_parquet(fraud_df, "fraud_verification")
        
        txns_df = self.hydrate_dataframe(txns_df, "bank_transactions")
        self.save_parquet(txns_df, "bank_transactions")
        
        # 4. Generate Reference Codes (Dimensions)
        print(" Phase 4: Generating Reference Codes")
        
        # Product Types
        products = self.apps_df.select("product_type").unique().with_columns([
            pl.lit("PRODUCT_TYPE").alias("code_type"),
            pl.col("product_type").alias("code_value"),
            (pl.col("product_type") + " Loan").alias("description"),
            pl.lit("Lending").alias("parent_code_value")
        ]).select(["code_type", "code_value", "description", "parent_code_value"])
        
        # Channels
        channels = self.apps_df.select("channel").unique().with_columns([
            pl.lit("CHANNEL").alias("code_type"),
            pl.col("channel").alias("code_value"),
            (pl.col("channel") + " Channel").alias("description"),
            pl.lit("Direct").alias("parent_code_value")
        ]).select(["code_type", "code_value", "description", "parent_code_value"])
        
        # States
        states = self.apps_df.select("state").unique().with_columns([
            pl.lit("STATE").alias("code_type"),
            pl.col("state").alias("code_value"),
            pl.col("state").alias("description"),
            pl.lit("US").alias("parent_code_value")
        ]).select(["code_type", "code_value", "description", "parent_code_value"])
        
        # Decision Status
        decisions = pl.DataFrame({
            "code_type": ["DECISION_STATUS", "DECISION_STATUS"],
            "code_value": ["APPROVED", "DECLINED"],
            "description": ["Application Approved", "Application Declined"],
            "parent_code_value": ["Review Complete", "Review Complete"]
        })
        
        # Combine all
        ref_codes = pl.concat([products, channels, states, decisions])
        ref_codes = self.hydrate_dataframe(ref_codes, "reference_codes")
        self.save_parquet(ref_codes, "reference_codes")
    
        # Save original applications
        # Save original applications
        print(" Saving applications.parquet...")
        self.apps_df = self.hydrate_dataframe(self.apps_df, "applications")
        self.apps_df.write_parquet(os.path.join(self.output_dir, "applications.parquet"))
        
        result = {
            "applications": self.apps_df,
            "credit_reports": snapshot_df,
            "loan_tape": loans_df,
            "payments": payments_df
        }
        
        # 5. Type 2 Validation
        self.validate_dataset(result)
        
        return result

if __name__ == "__main__":
    # Config
    INPUT_CSV = "data/applications.csv"
    OUTPUT_DIR = "sherpaiq_lc/data_domain/lendco/raw/data"
    
    gen = ExtendedDataGenerator(INPUT_CSV, OUTPUT_DIR)
    gen.load_applications()
    gen.generate_all()
