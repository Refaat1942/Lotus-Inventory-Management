"""Lotus inventory processing engine for web."""
import datetime
import io
import logging
import math
import os
import sqlite3
from typing import Callable, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

APP_VERSION = "v9.8.5 (Web)"
DB_NAME = os.path.join(os.path.dirname(__file__), "lotus_inventory_history.db")

TEMPLATES = {
    "main": ["Plnt","Plant","Material","Material Group","Material Description","Branch Stock","Pending to Branch","Open PO Quantity","Display","Dc Stock","Pending from DC","Consumption 180Day","Consumption90D","Ref.Cons 30D","Ref.Cons First 5D","Sales Price","Max Receipt","Main Category","SubCategory 1","Storage Condition","Manufacturer Name","Created On","Days Since Last STO","Days from last sell"],
    "targets": ["Plnt","Plant","Main Category","Target Days","Overstock Target Days","Target Distribution Target Days"],
    "purchase_targets": ["Plnt","Plant","Main Category","Target Days"],
    "rank": ["Plnt","Plant","Rank"],
    "blocked": ["Plnt","Plant","Material","Material Description"],
    "blocked_os": ["Plnt","Plant","Material","Material Description"],
    "avoid_zero": ["Plnt","Branch Name","Material","Category"],
    "similar": ["Material ( Main)","Material description (Main)","Material (Similar)","Material description (Similar)"],
}

def template_excel_bytes(name: str) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(columns=TEMPLATES[name]).to_excel(buf, index=False)
    buf.seek(0)
    return buf.getvalue()


def safe_int_series(s) -> pd.Series:
    """Ceiling float values to int — avoids pandas 'Invalid value for dtype int64' errors."""
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    nums = pd.to_numeric(s, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    return pd.Series(np.ceil(nums).astype(np.int64), index=s.index)


def display_branch_qty(stock, display, pending=None) -> pd.Series:
    """Branch qty needed to reach Display minimum (matches POS/Purchase display rules)."""
    stock = pd.to_numeric(stock, errors="coerce").fillna(0)
    display = pd.to_numeric(display, errors="coerce").fillna(0)
    if pending is not None:
        pending = pd.to_numeric(pending, errors="coerce").fillna(0)
        on_hand = stock + pending
        gap = np.maximum(0, np.ceil(display - on_hand))
    else:
        gap = np.maximum(0, np.ceil(display - stock))
    return safe_int_series(np.where(display > 0, gap, 0))


def apply_blocked_with_display(df, mask, stock, pending=None):
    """Blocked rows: zero REQ/purchase unless Display requires shelf quantity."""
    mask = pd.Series(mask, index=df.index) if not isinstance(mask, pd.Series) else mask.reindex(df.index, fill_value=False)
    display = pd.to_numeric(df["Display"], errors="coerce").fillna(0)
    qty = display_branch_qty(stock, display, pending=pending).reindex(df.index, fill_value=0)
    has_display = mask & (display > 0)
    df.loc[has_display, "Final Positive REQ"] = qty.loc[has_display]
    df.loc[has_display, "Purchase Quantity"] = qty.loc[has_display]
    no_display = mask & ~has_display
    df.loc[no_display, "Final Positive REQ"] = 0
    df.loc[no_display, "Purchase Quantity"] = 0


def floatify_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if pd.api.types.is_bool_dtype(df[col]):
            continue
        if pd.api.types.is_integer_dtype(df[col]):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    return df

def parse_rank_df(df_rank: pd.DataFrame) -> dict:
    rank_data = {}
    p_col = next((c for c in df_rank.columns if c.strip().lower() in ["plnt","plant","branch"]), None)
    rank_col = next((c for c in df_rank.columns if c.strip().lower() == "rank"), None)
    if not p_col: return rank_data
    current_rank = 1
    for _, row in df_rank.iterrows():
        b = str(row[p_col]).strip()
        if b and b != "nan" and b not in rank_data:
            if rank_col:
                try: rank_data[b] = int(row[rank_col])
                except Exception: rank_data[b] = 999
            else:
                rank_data[b] = current_rank; current_rank += 1
    return rank_data

def parse_blocked_df(df_b: pd.DataFrame):
    blocked_items, blocked_branches = set(), set()
    p_cols = [c for c in df_b.columns if c.strip().lower() in ["plnt","plant","branch"]]
    m_col = next((c for c in df_b.columns if c.strip().lower() in ["material","item code"]), None)
    if not p_cols: return blocked_items, blocked_branches
    for _, row in df_b.iterrows():
        for p_col in p_cols:
            b = str(row[p_col]).strip()
            if b and b != "nan":
                if m_col:
                    m = str(row[m_col]).replace(".0","").strip()
                    if m and m != "nan" and m != "": blocked_items.add((b,m))
                    else: blocked_branches.add(b)
                else: blocked_branches.add(b)
    return blocked_items, blocked_branches

def export_history_bytes() -> Optional[bytes]:
    if not os.path.exists(DB_NAME): return None
    conn = sqlite3.connect(DB_NAME)
    history_df = pd.read_sql("SELECT * FROM inventory_history", conn)
    conn.close()
    if history_df.empty: return None
    buf = io.BytesIO(); history_df.to_excel(buf, index=False); buf.seek(0)
    return buf.getvalue()

def standardize_columns(df):
    df.columns = df.columns.astype(str).str.strip()
    df.rename(columns={"Branch Stock":"Stock","Pending to Branch":"Pending preparation to branch","Pending from DC":"Pending preparation from DC","Consumption90D":"Consumption 90Day","Ref.Cons 30D":"Consumption last 30 days","Ref.Cons First 5D":"Consumption first 5 days of last month"}, inplace=True)
    return df


def process_inventory(main_df, targets_df=None, purchase_targets_df=None, rank_data=None, avoid_zero_df=None, similar_df=None, blocked_items=None, blocked_branches=None, blocked_os_items=None, blocked_os_branches=None, zero_overstock=True, sto_threshold=180, progress_callback=None):
    rank_data = rank_data or {}
    blocked_items = set(blocked_items or [])
    blocked_branches = set(blocked_branches or [])
    blocked_os_items = set(blocked_os_items or [])
    blocked_os_branches = set(blocked_os_branches or [])

    def update_progress(val, text):
        if progress_callback:
            progress_callback(val, text)

    missing_files = []
    if main_df is None: missing_files.append("- Main ERP Sheet")
    if targets_df is None: missing_files.append("- Targets")
    if not rank_data: missing_files.append("- Rank")
    if avoid_zero_df is None: missing_files.append("- Avoid Zero")

    try:
        sto_threshold = int(sto_threshold)
        if sto_threshold < 0:
            raise ValueError
    except (TypeError, ValueError):
        missing_files.append("- High STO Threshold (Days)")

    if missing_files:
        error_msg = "Please upload the following missing requirements:\n\n" + "\n".join(missing_files)
        raise ValueError(error_msg)

    try:
        update_progress(0.1, "Phase 2: Loading & Standardizing Dataset...")
        df = floatify_numeric_columns(main_df.copy())
        df = standardize_columns(df)
        plant_col = 'Plnt' if 'Plnt' in df.columns else 'Plant'
        if 'Plnt' not in df.columns and 'Plant' in df.columns:
            df['Plnt'] = df['Plant']
        if 'Plant' not in df.columns and 'Plnt' in df.columns:
            df['Plant'] = df['Plnt']
        if 'Display' not in df.columns: df['Display'] = 0
        if 'Storage Condition' not in df.columns: df['Storage Condition'] = ""
        if 'Manufacturer Name' not in df.columns: df['Manufacturer Name'] = ""
            
        df['temp_mat'] = df['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        df['temp_p'] = df[plant_col].astype(str).str.strip()
            
        df['Action Status'] = 'Pending'
        if 'Days Since Last STO' not in df.columns: df['Days Since Last STO'] = 0

        df['is_main_item'] = False
        if similar_df is not None:
            update_progress(0.15, "Merging Similar Items Data...")
            sim_df = similar_df.copy()
            m_main_col = next((c for c in sim_df.columns if 'main' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), sim_df.columns[0])
            m_sim_col = next((c for c in sim_df.columns if 'similar' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), sim_df.columns[2])
            agg_columns = [
                'Stock', 'Pending preparation to branch', 'Display',
                'Consumption 180Day', 'Consumption 90Day',
                'Consumption last 30 days', 'Consumption first 5 days of last month',
            ]
            pairs = sim_df[[m_main_col, m_sim_col]].copy()
            pairs[m_main_col] = pairs[m_main_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            pairs[m_sim_col] = pairs[m_sim_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            pairs = pairs.drop_duplicates()
            for _, row in pairs.iterrows():
                main_mat = row[m_main_col]
                sim_mat = row[m_sim_col]
                if not main_mat or main_mat == 'nan' or not sim_mat or sim_mat == 'nan':
                    continue
                sim_mask = df['temp_mat'] == sim_mat
                if not sim_mask.any():
                    continue
                for b in df.loc[sim_mask, 'temp_p'].unique():
                    s_b_mask = (df['temp_p'] == b) & (df['temp_mat'] == sim_mat)
                    m_b_mask = (df['temp_p'] == b) & (df['temp_mat'] == main_mat)
                    if m_b_mask.any():
                        for col in agg_columns:
                            if col in df.columns:
                                s_val = pd.to_numeric(df.loc[s_b_mask, col], errors='coerce').fillna(0).sum()
                                m_val = pd.to_numeric(df.loc[m_b_mask, col], errors='coerce').fillna(0).iloc[0]
                                df.loc[m_b_mask, col] = m_val + s_val
                        df.loc[m_b_mask, 'is_main_item'] = True
                    blocked_items.add((b, sim_mat))
                    blocked_os_items.add((b, sim_mat))
                    if s_b_mask.any():
                        df.loc[s_b_mask, 'Action Status'] = 'Merged as Similar & Blocked'

        update_progress(0.2, "Phase 3.1: Applying Targets & Purchase Targets...")
        df['Target Days'] = 35 
        df['Overstock Target Days'] = 45 
        df['Target Distribution Target Days'] = 30 
        df['Purchase Target Days'] = 0 
            
        # --- MODIFIED: Flexible Targets logic ---
        if targets_df is not None:
            t_df = targets_df.copy()
            t_df.columns = t_df.columns.astype(str).str.strip().str.lower()
            t_plant_cols = [c for c in t_df.columns if c in ['plnt', 'plant', 'branch']]
            t_cat_col = next((c for c in t_df.columns if 'category' in c), None)
            t_target_col = next((c for c in t_df.columns if 'target days' in c and 'overstock' not in c and 'distribution' not in c), None)
            t_os_target_col = next((c for c in t_df.columns if 'overstock' in c), None)
            t_dist_col = next((c for c in t_df.columns if 'distribution target' in c), None)

            if t_plant_cols:
                t_plant_col = t_plant_cols[0]
                for _, row in t_df.iterrows():
                    b = str(row[t_plant_col]).strip()
                    target_val = pd.to_numeric(row[t_target_col], errors='coerce') if t_target_col else np.nan
                    os_target_val = pd.to_numeric(row[t_os_target_col], errors='coerce') if t_os_target_col else np.nan
                    dist_target_val = pd.to_numeric(row[t_dist_col], errors='coerce') if t_dist_col else np.nan

                    mask = pd.Series(False, index=df.index)
                        
                    if t_cat_col:
                        cat = str(row[t_cat_col]).strip().lower()
                        if 'non' in cat: mask = (df['temp_p'] == b) & (df['Main Category'].astype(str).str.lower().str.contains('non'))
                        else: mask = (df['temp_p'] == b) & (~df['Main Category'].astype(str).str.lower().str.contains('non')) & (df['Main Category'].astype(str).str.lower().str.contains('pharma'))
                    else:
                        # Apply to all items in the branch if category column is missing
                        mask = (df['temp_p'] == b)

                    if not pd.isna(target_val): df.loc[mask, 'Target Days'] = target_val
                    if not pd.isna(os_target_val): df.loc[mask, 'Overstock Target Days'] = os_target_val
                    if not pd.isna(dist_target_val): df.loc[mask, 'Target Distribution Target Days'] = dist_target_val

        if purchase_targets_df is not None:
            pt_df = purchase_targets_df.copy()
            pt_df.columns = pt_df.columns.astype(str).str.strip().str.lower()
            pt_plant_cols = [c for c in pt_df.columns if c in ['plnt', 'plant', 'branch']]
            pt_cat_col = next((c for c in pt_df.columns if 'category' in c), None)
            pt_target_col = next((c for c in pt_df.columns if 'target days' in c), None)

            if pt_plant_cols and pt_target_col:
                pt_plant_col = pt_plant_cols[0]
                for _, row in pt_df.iterrows():
                    b = str(row[pt_plant_col]).strip()
                    target_val = pd.to_numeric(row[pt_target_col], errors='coerce')

                    if not pd.isna(target_val):
                        mask = pd.Series(False, index=df.index)
                        if pt_cat_col:
                            cat = str(row[pt_cat_col]).strip().lower()
                            if 'non' in cat: mask = (df['temp_p'] == b) & (df['Main Category'].astype(str).str.lower().str.contains('non'))
                            else: mask = (df['temp_p'] == b) & (~df['Main Category'].astype(str).str.lower().str.contains('non')) & (df['Main Category'].astype(str).str.lower().str.contains('pharma'))
                        else:
                            # Apply to all items in the branch if category column is missing
                            mask = (df['temp_p'] == b)
                            
                        df.loc[mask, 'Purchase Target Days'] = target_val

        df['Target Days'] = pd.to_numeric(df['Target Days'], errors='coerce').fillna(35)
        df.loc[df['Target Days'] <= 0, 'Target Days'] = 35
        df['Overstock Target Days'] = pd.to_numeric(df['Overstock Target Days'], errors='coerce').fillna(45)
        df.loc[df['Overstock Target Days'] <= 0, 'Overstock Target Days'] = 45
        df['Target Distribution Target Days'] = pd.to_numeric(df['Target Distribution Target Days'], errors='coerce').fillna(30)
        df.loc[df['Target Distribution Target Days'] <= 0, 'Target Distribution Target Days'] = 30
        df['Purchase Target Days'] = pd.to_numeric(df['Purchase Target Days'], errors='coerce').fillna(0)

        update_progress(0.3, "Phase 3.2: Applying Avoid Zero Stock Logic...")
            
        df['Is_Avoid_Zero'] = False 
            
        if avoid_zero_df is not None:
            az_df = avoid_zero_df.copy()
            az_p_cols = [c for c in az_df.columns if c.strip().lower() in ['plnt', 'plant', 'branch name']]
            az_m_col = next((c for c in az_df.columns if c.strip().lower() in ['material', 'item code']), None)
            az_cat_col = next((c for c in az_df.columns if 'category' in c.lower()), None)
                
            if az_p_cols:
                az_p_col = az_p_cols[0]
                for _, row in az_df.iterrows():
                    b = str(row[az_p_col]).strip()
                    if not b or b == 'nan': continue
                        
                    m_val = str(row[az_m_col]).replace('.0', '').strip() if az_m_col else 'nan'
                    cat_val = str(row[az_cat_col]).strip().lower() if az_cat_col else 'nan'
                        
                    if m_val != 'nan':
                        mask = (df['temp_p'] == b) & (df['temp_mat'] == m_val)
                        df.loc[mask, 'Is_Avoid_Zero'] = True
                    elif cat_val != 'nan' and cat_val != '':
                        is_pharma = ('pharma' in cat_val and 'non' not in cat_val) or ('all' in cat_val)
                        is_non_pharma = ('non' in cat_val) or ('all' in cat_val)
                        if is_pharma:
                            mask = (df['temp_p'] == b) & (~df['Main Category'].astype(str).str.lower().str.contains('non')) & (df['Main Category'].astype(str).str.lower().str.contains('pharma'))
                            df.loc[mask, 'Is_Avoid_Zero'] = True
                        if is_non_pharma:
                            mask = (df['temp_p'] == b) & (df['Main Category'].astype(str).str.lower().str.contains('non'))
                            df.loc[mask, 'Is_Avoid_Zero'] = True
                    else:
                        mask = (df['temp_p'] == b)
                        df.loc[mask, 'Is_Avoid_Zero'] = True

        update_progress(0.4, "Phase 3.3 & 3.4: Dynamic Consumption & REQ Calculation...")
            
        df['Consumption 180Day'] = pd.to_numeric(df.get('Consumption 180Day', 0), errors='coerce').fillna(0)
        df['Consumption 90Day'] = pd.to_numeric(df.get('Consumption 90Day', 0), errors='coerce').fillna(0)
        df['Consumption last 30 days'] = pd.to_numeric(df.get('Consumption last 30 days', 0), errors='coerce').fillna(0)
            
        ratio_30_90 = df['Consumption last 30 days'] / df['Consumption 90Day'].replace(0, np.nan)
            
        df['R_analysis'] = 90
        df.loc[ratio_30_90 >= 1.0, 'R_analysis'] = 30
        df.loc[(ratio_30_90 >= 0.8) & (ratio_30_90 < 1.0), 'R_analysis'] = 45
            
        df['Daily Consumption'] = df['Consumption 90Day'] / df['R_analysis']
            
        F_stock = pd.to_numeric(df.get('Stock', 0), errors='coerce').fillna(0)
        Pending_branch = pd.to_numeric(df.get('Pending preparation to branch', 0), errors='coerce').fillna(0)
        Total_Stock = F_stock + Pending_branch 
            
        S_target = df['Target Days']
        df['Calculated POS REQ'] = (df['Daily Consumption'] * S_target) - Total_Stock
        df['Final Positive REQ'] = safe_int_series(
            np.where(df['Calculated POS REQ'] > 0, np.ceil(df['Calculated POS REQ']), 0)
        )

        # Ø§Ù„Ù€ Positive REQ Ø¨ÙŠØ¨Øµ Ø¹Ù„Ù‰ Ø§Ù„Ù€ Display
        mask_pos_display = (F_stock + df['Final Positive REQ']) < df['Display']
        df.loc[mask_pos_display, 'Final Positive REQ'] = np.ceil(df['Display'] - F_stock)
        df['Final Positive REQ'] = safe_int_series(df['Final Positive REQ'])

        OS_target = df['Overstock Target Days']
        df['Required Safe Stock'] = df['Daily Consumption'] * OS_target
        df['Calculated NEG REQ'] = df['Required Safe Stock'] - Total_Stock
            
        df['Final Negative REQ'] = np.where(df['Calculated NEG REQ'] < 0, np.trunc(df['Calculated NEG REQ']), 0)
        df['Overstock QTY'] = abs(df['Final Negative REQ'])

        # -- Purchase Calculation (Branch Level) --
        df['Purchase Quantity'] = safe_int_series(
            np.where(
                (df['Daily Consumption'] * df['Purchase Target Days']) - Total_Stock > 0,
                np.ceil((df['Daily Consumption'] * df['Purchase Target Days']) - Total_Stock),
                0,
            )
        )
            
        # --- ØªØ¹Ø¯ÙŠÙ„ Ø§Ù„Ù€ Purchase Ù„Ù„Ù€ Display Ø§Ù„Ø¥Ø¬Ø¨Ø§Ø±ÙŠ ---
        mask_purch_display = (F_stock + df['Purchase Quantity']) < df['Display']
        df.loc[mask_purch_display, 'Purchase Quantity'] = np.ceil(df['Display'] - F_stock)
        df['Purchase Quantity'] = safe_int_series(df['Purchase Quantity'])

        update_progress(0.5, "Phase 3.5: Filtering Blocked Lists & Protecting Display...")
        if blocked_items:
            mask_bi = pd.Series(
                df.set_index(["temp_p", "temp_mat"]).index.isin(blocked_items),
                index=df.index,
            )
            apply_blocked_with_display(df, mask_bi, F_stock)
            df.loc[mask_bi & (df["Action Status"] != "Merged as Similar & Blocked"), "Action Status"] = "Blocked Item (User List)"

        if blocked_branches:
            mask_bb = df["temp_p"].isin(blocked_branches)
            apply_blocked_with_display(df, mask_bb, F_stock)
            df.loc[mask_bb, "Action Status"] = "Blocked Branch (User List)"
                
        df_blocked_os_output = pd.DataFrame()
            
        if blocked_os_branches:
            mask_bos_b = df['temp_p'].isin(blocked_os_branches)
            df_blocked_os_output = pd.concat([df_blocked_os_output, df[mask_bos_b]])
            df.loc[mask_bos_b, 'Overstock QTY'] = 0
            df.loc[mask_bos_b, 'Action Status'] = 'Blocked OS Branch (User List)'
                
        if blocked_os_items:
            mask_bos_i = df.set_index(['temp_p', 'temp_mat']).index.isin(blocked_os_items)
            df_blocked_os_output = pd.concat([df_blocked_os_output, df[mask_bos_i]])
            df.loc[mask_bos_i, 'Overstock QTY'] = 0
            df.loc[mask_bos_i & (df['Action Status'] != 'Merged as Similar & Blocked'), 'Action Status'] = 'Blocked OS Item (User List)'

        if not df_blocked_os_output.empty:
            df_blocked_os_output = df_blocked_os_output.drop_duplicates(subset=['temp_p', 'temp_mat'])

        mask_display = (F_stock - df['Overstock QTY']) < df['Display']
        df.loc[mask_display & (df['Overstock QTY'] > 0) & (df['Action Status'] == 'Pending'), 'Action Status'] = 'Protected by Display Qty'
        df.loc[mask_display, 'Overstock QTY'] = F_stock - df['Display']
        df['Overstock QTY'] = safe_int_series(df['Overstock QTY'])

        update_progress(0.6, "Calculating Company Totals & Applying Pos/Neg Rules...")
            
        df['Pending preparation from DC'] = pd.to_numeric(df.get('Pending preparation from DC', 0), errors='coerce').fillna(0)
        df['Open PO Quantity'] = pd.to_numeric(df.get('Open PO Quantity', 0), errors='coerce').fillna(0)
            
        num_cols_to_fill = ['Dc Stock']
        for c in num_cols_to_fill:
            if c not in df.columns: df[c] = 0
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
        company_totals = df.groupby(["temp_mat"], as_index=False).agg(
            Material=("Material", "first"),
            Material_Group=("Material Group", "first"),
            Material_Description=("Material Description", "first"),
            Total_Dc=("Dc Stock", "first"),
            Total_Pending_From_DC=("Pending preparation from DC", "first"),
            Total_Open_PO=("Open PO Quantity", "first"),
            Main_Category=("Main Category", "first"),
            SubCategory_1=("SubCategory 1", "first"),
            Storage_Condition=("Storage Condition", "first"),
            Manufacturer_Name=("Manufacturer Name", "first"),
            Created_On=("Created On", "first"),
            Total_Stock=("Stock", "sum"),
            Store_Outbound=("Pending preparation to branch", "sum"),
            Consumption_90Day=("Consumption 90Day", "sum"),
            Cons_30_Day=("Consumption last 30 days", "sum"),
            Cons_180Day=("Consumption 180Day", "sum"),
            Final_Positive_REQ_Internal=("Final Positive REQ", "sum"),
            Final_Negative_REQ_Internal=("Overstock QTY", "sum"),
            Total_Purchase_REQ=("Purchase Quantity", "sum"),
            Sales_Price=("Sales Price", "first"),
        )
        company_totals["Material"] = company_totals["temp_mat"]
        company_totals.drop(columns=["temp_mat"], inplace=True)

        # Keep every material that appears in All Items (no aggressive filter).
        # Company Totals = one row per material; All Items = branch rows for the same materials.
        company_totals['Pos/Neg'] = np.where(
            company_totals['Final_Negative_REQ_Internal'] == 0, 
            np.nan, 
            company_totals['Final_Positive_REQ_Internal'] / company_totals['Final_Negative_REQ_Internal']
        )

        def get_company_decision(row):
            if row['Final_Negative_REQ_Internal'] > row['Final_Positive_REQ_Internal'] and row['Final_Negative_REQ_Internal'] > 0: 
                return "DO NOT BUY - Pullback/Transfer"
            elif row['Final_Positive_REQ_Internal'] > row['Final_Negative_REQ_Internal']: 
                return "BUY - Shortage Exceeds Available Overstock"
            else: 
                return "BALANCED / HOLD"
        company_totals['Order Decision'] = company_totals.apply(get_company_decision, axis=1)

        def calculate_overstock_and_exclusion(row):
            pos = row['Final_Positive_REQ_Internal']
            neg = row['Final_Negative_REQ_Internal']
            wh_stock = max(0, row['Total_Dc'] - row['Total_Pending_From_DC']) 
                
            if neg == 0: return 0, "No Negative Target"
                
            ratio = pos / neg
            target = 0
            condition = 0
                
            if ratio < 0.01: target = pos * 20
            elif ratio == 1 and pos == 1:
                condition = 7
                target = pos
            elif ratio == 1 and pos != 1:
                condition = 14
                target = pos
            elif ratio > 1:
                condition = 15
                target = abs(neg)
            else:
                if pos == 1:
                    if 0.01 <= ratio < 0.05: target = pos * 6
                    elif 0.05 <= ratio < 0.07: target = pos * 4
                    elif 0.07 <= ratio < 0.12: target = pos * 3
                    elif 0.12 <= ratio <= 0.5: target = pos * 2
                    elif 0.5 < ratio < 1: target = pos
                else:
                    if 0.01 <= ratio < 0.05: target = pos * 5
                    elif 0.05 <= ratio < 0.09: target = pos * 3
                    elif 0.09 <= ratio < 0.20: target = pos * 2
                    elif 0.20 <= ratio <= 0.5: target = math.ceil(pos * 1.5)
                    elif 0.5 < ratio <= 0.7: target = math.ceil(pos * 1.2)
                    elif 0.7 < ratio < 1: target = pos
                
            is_checked = bool(zero_overstock)
                
            if condition in [14, 15]:
                if is_checked:
                    res = target - wh_stock
                    return max(0, int(res)), f"Included in Target (Rule {condition})"
                else:
                    return 0, f"Excluded by Checkbox (Rule {condition})"
            else:
                res = target - wh_stock
                if condition > 0: return max(0, int(res)), f"Included in Target (Rule {condition})"
                return max(0, int(res)), "Included in Target"

        if company_totals.empty:
            company_totals['Overstock'] = 0
            company_totals['Exclusion_Status'] = ""
        else:
            company_totals[['Overstock', 'Exclusion_Status']] = company_totals.apply(
                lambda row: pd.Series(calculate_overstock_and_exclusion(row)), axis=1
            )

        company_totals.rename(columns={
            'Material_Group': 'Material Group', 'Material_Description': 'Material Description',
            'Total_Dc': 'Total Dc', 'Total_Pending_From_DC': 'Pending from DC',
            'Main_Category': 'Main Category', 'SubCategory_1': 'SubCategory 1',
            'Storage_Condition': 'Storage Condition', 'Manufacturer_Name': 'Manufacturer Name',
            'Created_On': 'Created On', 'Total_Stock': 'Stock', 'Store_Outbound': 'Store_Outbound',
            'Consumption_90Day': 'Consumption 90Day', 'Cons_30_Day': 'Cons 30 Day',
            'Cons_180Day': 'Cons 180Day', 'Final_Positive_REQ_Internal': 'Final PositiveREQ', 
            'Final_Negative_REQ_Internal': 'Final Negative REQ', 'Sales_Price': 'Sales Price'
        }, inplace=True)

        update_progress(0.7, "Running 5-Phase Dynamic Smart Pullback Algorithm...")
        df['Branch Rank'] = df['temp_p'].map(lambda x: rank_data.get(str(x), 999))
        df['Days Since Last STO'] = pd.to_numeric(df.get('Days Since Last STO', 0), errors='coerce').fillna(0)
            
        df['Final Pullback QTY'] = 0
            
        if not company_totals.empty:
            needed_pullbacks = company_totals.set_index('Material')['Overstock'].to_dict()
        else:
            needed_pullbacks = {}
            
        stock_dict = df['Stock'].to_dict()
        os_qty_dict = df['Overstock QTY'].to_dict()
        dc_dict = df['Daily Consumption'].to_dict()
        sto_dict = df['Days Since Last STO'].to_dict()
        rank_dict = df['Branch Rank'].to_dict()
        is_az_dict = df['Is_Avoid_Zero'].to_dict()
            
        for mat, gross_pull in needed_pullbacks.items():
            if gross_pull <= 0: continue
            target_pull = gross_pull 

            mat_key = str(mat).replace(".0", "").strip()
            mat_mask = (df["temp_mat"] == mat_key) & (df["Overstock QTY"] > 0)
            if not mat_mask.any(): continue

            mat_indices = df[mat_mask].index.tolist()
            pullbacks = {i: 0 for i in mat_indices}
                
            max_pull_allowed = {}
            for i in mat_indices:
                if is_az_dict[i]:
                    max_pull_allowed[i] = max(0, min(os_qty_dict[i], int(stock_dict[i]) - 1))
                else:
                    max_pull_allowed[i] = os_qty_dict[i]

            active_idx = [i for i in mat_indices if dc_dict[i] > 0]
            zero_cons_HighSTO = [i for i in mat_indices if dc_dict[i] <= 0 and sto_dict[i] >= sto_threshold]
            zero_cons_LowSTO = [i for i in mat_indices if dc_dict[i] <= 0 and sto_dict[i] < sto_threshold]
                
            def pull_percentage_group(group, needed, max_pct=0.8):
                if needed <= 0 or not group: return needed
                    
                def get_max_pull(i, pct):
                    desired_pull = round(stock_dict[i] * pct)
                    available_os = max_pull_allowed[i] - pullbacks[i]
                    safe_stock_limit = max(0, int(stock_dict[i] - pullbacks[i] - 1))
                    return min(desired_pull, available_os, safe_stock_limit)
                        
                max_pulls = {i: get_max_pull(i, max_pct) for i in group}
                total_max = sum(max_pulls.values())

                if total_max <= needed:
                    for i in group: pullbacks[i] += max_pulls[i]
                    return needed - total_max

                for pct_int in range(int(max_pct*100), -1, -1):
                    pct = pct_int / 100.0
                    current_pulls = {i: get_max_pull(i, pct) for i in group}
                    if sum(current_pulls.values()) <= needed:
                        for i in group: pullbacks[i] += current_pulls[i]
                        rem = needed - sum(current_pulls.values())
                        if rem > 0:
                            sorted_group = sorted(group, key=lambda x: (sto_dict[x], rank_dict[x]), reverse=True)
                            for idx in sorted_group:
                                if rem <= 0: break
                                if pullbacks[idx] < max_pulls[idx]:
                                    pullbacks[idx] += 1
                                    rem -= 1
                        return 0
                return needed

            def pull_active_group(group, needed):
                if needed <= 0 or not group: return needed
                max_pulls = {i: max_pull_allowed[i] - pullbacks[i] for i in group}
                total_max = sum(max_pulls.values())

                if total_max <= needed:
                    for i in group: pullbacks[i] += max_pulls[i]
                    return needed - total_max

                max_days = int(max((stock_dict[i] / dc_dict[i]) for i in group if dc_dict[i] > 0)) + 1
                    
                for d in range(max_days, -1, -1):
                    current_pulls = {i: min(max_pulls[i], max(0, int(stock_dict[i] - max(d, df.at[i, 'Overstock Target Days']) * dc_dict[i]))) for i in group}
                    if sum(current_pulls.values()) >= needed:
                        safe_d = d + 1
                        safe_pulls = {i: min(max_pulls[i], max(0, int(stock_dict[i] - max(safe_d, df.at[i, 'Overstock Target Days']) * dc_dict[i]))) for i in group}
                        for i in group: pullbacks[i] += safe_pulls[i]
                        rem = needed - sum(safe_pulls.values())
                        if rem > 0:
                            sorted_group = sorted(group, key=lambda x: ((os_qty_dict[x]-pullbacks[x])/dc_dict[x], rank_dict[x]), reverse=True)
                            for idx in sorted_group:
                                if rem <= 0: break
                                if pullbacks[idx] < max_pulls[idx]:
                                    pullbacks[idx] += 1
                                    rem -= 1
                        return 0
                return needed

            def pull_phase_4(group, needed):
                if needed <= 0 or not group: return needed
                sorted_group = sorted(group, key=lambda x: (sto_dict[x], rank_dict[x]), reverse=True)
                for idx in sorted_group:
                    rem_os = max_pull_allowed[idx] - pullbacks[idx]
                    if rem_os > 0:
                        take = min(needed, rem_os)
                        pullbacks[idx] += take
                        needed -= take
                    if needed <= 0: break
                return needed

            def pull_phase_5(group, needed):
                if needed <= 0 or not group: return needed
                sorted_group = sorted(group, key=lambda x: (sto_dict[x], rank_dict[x]), reverse=True)
                for idx in sorted_group:
                    rem_os = max_pull_allowed[idx] - pullbacks[idx]
                    max_take = min(rem_os, max(0, int(stock_dict[idx] - pullbacks[idx] - 1)))
                    if max_take > 0:
                        take = min(needed, max_take)
                        pullbacks[idx] += take
                        needed -= take
                    if needed <= 0: break
                return needed

            target_pull = pull_percentage_group(zero_cons_HighSTO, target_pull, max_pct=0.8)
            target_pull = pull_active_group(active_idx, target_pull)
            target_pull = pull_percentage_group(zero_cons_LowSTO, target_pull, max_pct=0.8)
            target_pull = pull_phase_4(zero_cons_HighSTO, target_pull)
            target_pull = pull_phase_5(zero_cons_LowSTO, target_pull)

            for i, val in pullbacks.items():
                if val > 0:
                    df.at[i, 'Final Pullback QTY'] = val

        def finalize_action_status(row):
            if 'Blocked' in str(row['Action Status']): 
                return row['Action Status']
                    
            if row['Final Pullback QTY'] > 0: 
                base_status = 'Action Taken: Pulled to DC'
                if row['Is_Avoid_Zero'] and row['Overstock QTY'] > row['Final Pullback QTY'] and (row['Stock'] - row['Final Pullback QTY'] <= 1):
                    base_status += ' (Avoid Zero Applied)'
                return base_status
                    
            if row['Final Positive REQ'] > 0: 
                return 'Action Taken: Shortage Logged'
                    
            if row['Overstock QTY'] > 0 and row['Final Pullback QTY'] == 0: 
                if row['Is_Avoid_Zero'] and row['Stock'] <= 1:
                    return 'Protected by Avoid Zero'
                if 'Protected' in str(row['Action Status']):
                    return row['Action Status']
                return 'Overstock Exists but DC Target Met'
                    
            return 'Balanced / No Action Needed'
                
        df['Action Status'] = df.apply(finalize_action_status, axis=1)

            # Ø§Ù„Ø³Ø·ÙˆØ± Ø¯ÙŠ Ù‡ØªØ¬Ø¨Ø± Ø§Ù„ÙƒÙˆØ¯ ÙŠÙƒØªØ¨ Ø¥Ù† Ø¯Ù‡ ØµÙ†Ù Ù…ÙŠÙ† Ù…Ù‡Ù…Ø§ ÙƒØ§Ù†Øª Ø­Ø§Ù„ØªÙ‡
        if 'is_main_item' in df.columns:
            mask_main = df['is_main_item'] == True
            df.loc[mask_main, 'Action Status'] = df.loc[mask_main, 'Action Status'].astype(str) + ' (Main Item - Merged)'

        def get_final_decision(row):
            decisions = []
            if row['Final Pullback QTY'] > 0: decisions.append("PULLBACK TO DC")
            if row['Final Positive REQ'] > 0: decisions.append("ORDER SHORTAGE")
                
            if not decisions: return "HOLD"
            return " + ".join(decisions)
                
        df['System Decision'] = df.apply(get_final_decision, axis=1)

        # =========================================================================
        # Stock Reallocation Engine (Inter-Branch Transfers)
        # =========================================================================
        update_progress(0.85, "Calculating Stock Reallocation (Branch Transfers)...")
            
        NEIGHBOR_MAP = {
            'CA21': ['CA27'], 'CA27': ['CA21'],
            'GZ03': ['GZ05'], 'GZ05': ['GZ03'],
            'GZ04': ['GZ06'], 'GZ06': ['GZ04'],
            'CA23': ['CA28'], 'CA28': ['CA23']
        }
        NEIGHBORS_MAP_UPPER = {k.upper(): [v.upper() for v in vals] for k, vals in NEIGHBOR_MAP.items()}
            
        reallocation_records = []
            
        df['Realloc_Available'] = df['Final Pullback QTY']
            
        df['Final Positive REQ (Distribution)'] = np.where(
            df['Final Positive REQ'] > 0,
            np.ceil(df['Daily Consumption'] * df['Target Distribution Target Days']) - F_stock,
            0
        )
            
        # --- ØªØ¹Ø¯ÙŠÙ„ Ø§Ù„Ù€ Distribution Ù„Ù„Ù€ Display Ø§Ù„Ø¥Ø¬Ø¨Ø§Ø±ÙŠ ---
        mask_dist_display = (df['Final Positive REQ'] > 0) & ((F_stock + df['Final Positive REQ (Distribution)']) < df['Display'])
        df.loc[mask_dist_display, 'Final Positive REQ (Distribution)'] = np.ceil(df['Display'] - F_stock)
            
        df['Final Positive REQ (Distribution)'] = safe_int_series(
            df['Final Positive REQ (Distribution)'].clip(lower=0, upper=df['Final Positive REQ'])
        )

        materials_to_reallocate = df.loc[df["Realloc_Available"] > 0, "temp_mat"].unique()

        for mat in materials_to_reallocate:
            donors = df[(df["temp_mat"] == mat) & (df["Realloc_Available"] > 0)].sort_values("Realloc_Available", ascending=False).to_dict("records")
            receivers = df[(df["temp_mat"] == mat) & (df["Final Positive REQ (Distribution)"] > 0)].sort_values("Final Positive REQ (Distribution)", ascending=False).to_dict("records")

            for d in donors:
                if d['Realloc_Available'] <= 0: continue
                d_code = str(d['temp_p']).strip().upper()
                    
                if d_code in NEIGHBORS_MAP_UPPER:
                    for r in receivers:
                        if r['Final Positive REQ (Distribution)'] <= 0: continue
                        r_code = str(r['temp_p']).strip().upper()
                            
                        if r_code in NEIGHBORS_MAP_UPPER[d_code]:
                            qty_to_move = min(d['Realloc_Available'], r['Final Positive REQ (Distribution)'])
                            if qty_to_move > 0:
                                reallocation_records.append({
                                    'Material': mat,
                                    'Material Description': d['Material Description'],
                                    'From Branch Code': str(d['temp_p']),
                                    'From Branch Name': str(d.get('Plant', '')),
                                    'From Branch Stock': int(d.get('Stock', 0)),
                                    'To Branch Code': str(r['temp_p']),
                                    'To Branch Name': str(r.get('Plant', '')),
                                    'Distribution Target REQ': int(r.get('Final Positive REQ (Distribution)', 0)),
                                    'Transfer QTY': int(qty_to_move),
                                    'Action Status': f"Priority Neighbor Transfer ({r['Target Distribution Target Days']} Days)"
                                })
                                d['Realloc_Available'] -= qty_to_move
                                r['Final Positive REQ (Distribution)'] -= qty_to_move
                                    
                            if d['Realloc_Available'] <= 0: break

            donors = [d for d in donors if d['Realloc_Available'] > 0]
            receivers = [r for r in receivers if r['Final Positive REQ (Distribution)'] > 0]

            donor_idx = 0
            receiver_idx = 0

            while donor_idx < len(donors) and receiver_idx < len(receivers):
                donor = donors[donor_idx]
                receiver = receivers[receiver_idx]

                qty_to_move = min(donor['Realloc_Available'], receiver['Final Positive REQ (Distribution)'])

                if qty_to_move > 0:
                    reallocation_records.append({
                        'Material': mat,
                        'Material Description': donor['Material Description'],
                        'From Branch Code': str(donor['temp_p']),
                        'From Branch Name': str(donor.get('Plant', '')),
                        'From Branch Stock': int(donor.get('Stock', 0)), 
                        'To Branch Code': str(receiver['temp_p']),
                        'To Branch Name': str(receiver.get('Plant', '')),
                        'Distribution Target REQ': int(receiver.get('Final Positive REQ (Distribution)', 0)), 
                        'Transfer QTY': int(qty_to_move),
                        'Action Status': f"Transfer based on Target Distribution ({receiver['Target Distribution Target Days']} Days)"
                    })

                    donor['Realloc_Available'] -= qty_to_move
                    receiver['Final Positive REQ (Distribution)'] -= qty_to_move

                if donor['Realloc_Available'] <= 0:
                    donor_idx += 1
                if receiver['Final Positive REQ (Distribution)'] <= 0:
                    receiver_idx += 1

            while donor_idx < len(donors):
                donor = donors[donor_idx]
                if donor['Realloc_Available'] > 0:
                    reallocation_records.append({
                        'Material': mat,
                        'Material Description': donor['Material Description'],
                        'From Branch Code': str(donor['temp_p']),
                        'From Branch Name': str(donor.get('Plant', '')),
                        'From Branch Stock': int(donor.get('Stock', 0)), 
                        'To Branch Code': 'DC',
                        'To Branch Name': 'Main Warehouse',
                        'Distribution Target REQ': 0,
                        'Transfer QTY': int(donor['Realloc_Available']),
                        'Action Status': 'Remainder Pulled to DC'
                    })
                donor_idx += 1

        df_reallocation = pd.DataFrame(reallocation_records)
        # =========================================================================

        update_progress(0.9, "Preparing export sheets...")
            
        df_purchase = pd.DataFrame()
        if not company_totals.empty:
            pulled_totals = df.groupby("temp_mat", as_index=False).agg(
                Total_Pulled_Overstock=("Final Pullback QTY", "sum")
            )
            pulled_totals.rename(columns={"temp_mat": "Material"}, inplace=True)
            company_totals = pd.merge(company_totals, pulled_totals, on="Material", how="left")
            if "Total_Pulled_Overstock" in company_totals.columns:
                company_totals["Total Pulled Overstock"] = safe_int_series(
                    company_totals["Total_Pulled_Overstock"].fillna(0)
                )
                company_totals.drop(columns=["Total_Pulled_Overstock"], inplace=True, errors="ignore")
            else:
                company_totals["Total Pulled Overstock"] = 0

            purchase_req_col = "Total_Purchase_REQ" if "Total_Purchase_REQ" in company_totals.columns else "Total Purchase Quantity"
            open_po_col = "Total_Open_PO" if "Total_Open_PO" in company_totals.columns else "Open PO Quantity"
            dc_col = "Total Dc" if "Total Dc" in company_totals.columns else "Total_Dc"
            pending_dc_col = "Pending from DC" if "Pending from DC" in company_totals.columns else "Pending from DC"

            company_totals["Company Purchase Quantity"] = (
                pd.to_numeric(company_totals[purchase_req_col], errors="coerce").fillna(0)
                - company_totals["Total Pulled Overstock"]
                - pd.to_numeric(company_totals[open_po_col], errors="coerce").fillna(0)
                - (
                    pd.to_numeric(company_totals[dc_col], errors="coerce").fillna(0)
                    - pd.to_numeric(company_totals[pending_dc_col], errors="coerce").fillna(0)
                )
            )
            company_totals["Company Purchase Quantity"] = safe_int_series(company_totals["Company Purchase Quantity"])

            company_totals = company_totals.sort_values(
                by=["Order Decision", "Material"],
                ascending=[True, True],
            )

            df_purchase = company_totals[company_totals['Company Purchase Quantity'] > 0].copy()
            df_purchase['Total Branch stock'] = df_purchase['Stock'] + df_purchase['Store_Outbound']
                
            df_purchase.rename(columns={
                'Company Purchase Quantity': 'Net Purchase Quantity', 
                'Total_Purchase_REQ': 'Total Purchase Quantity',      
                'Total_Open_PO': 'Open PO Quantity'                   
            }, inplace=True)
                
            purchase_cols = [
                'Material', 'Material Group', 'Material Description', 'Total Dc',
                'Pending from DC', 'Open PO Quantity', 'Main Category', 'SubCategory 1', 
                'Storage Condition', 'Manufacturer Name', 'Created On',
                'Total Branch stock', 'Consumption 90Day', 'Cons 30 Day', 'Cons 180Day',
                'Sales Price', 'Total Pulled Overstock', 'Total Purchase Quantity', 'Net Purchase Quantity'
            ]
            df_purchase = df_purchase[[c for c in purchase_cols if c in df_purchase.columns]]

        df_actionable_db = df[(df['Final Pullback QTY'] > 0) | (df['Final Positive REQ'] > 0)].copy()

        df_all = df.copy()
        if "temp_mat" in df_all.columns:
            df_all["Material"] = df_all["temp_mat"]
        sort_branch = "Plnt" if "Plnt" in df_all.columns else "Plant"
        sort_by = [c for c in ["Material", sort_branch, "Final Positive REQ", "Final Pullback QTY"] if c in df_all.columns]
        sort_asc = [True, True, False, False][: len(sort_by)]
        df_all = df_all.sort_values(by=sort_by, ascending=sort_asc)

        output_cols = [
            'Plnt', 'Plant', 'Material', 'Material Description', 'System Decision', 'Action Status',
            'Stock', 'Pending preparation to branch', 'Open PO Quantity', 'Display', 
            'Dc Stock', 'Pending preparation from DC',
            'Consumption 180Day', 'Consumption 90Day', 'Consumption last 30 days', 'Consumption first 5 days of last month',
            'Target Days', 'Overstock Target Days', 'Target Distribution Target Days', 'Purchase Target Days',
            'Calculated NEG REQ', 'Final Negative REQ', 'Overstock QTY', 'Final Pullback QTY', 
            'Final Positive REQ', 'Final Positive REQ (Distribution)', 'Purchase Quantity',
            'Branch Rank', 'Main Category', 'SubCategory 1', 'Storage Condition', 'Manufacturer Name', 
            'Sales Price', 'Created On', 'Days Since Last STO', 'Days from last sell'
        ]
            
        for col in output_cols:
            if col not in df_all.columns: df_all[col] = ""
        df_all = df_all[output_cols]

        df_blocked_final = df[df['Action Status'].str.contains('Blocked', na=False)].copy()
        if not df_blocked_final.empty:
            for col in output_cols:
                if col not in df_blocked_final.columns: df_blocked_final[col] = ""
            df_blocked_final = df_blocked_final[output_cols]
                
        run_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not df_actionable_db.empty:
            db_data = df_actionable_db.copy()
            db_cols = [c for c in output_cols if c in db_data.columns]
            db_data = db_data[db_cols]
            db_data.insert(0, 'Run_Date', run_timestamp) 
            try:
                conn = sqlite3.connect(DB_NAME)
                db_data.to_sql('inventory_history', conn, if_exists='append', index=False)
                conn.close()
            except Exception: pass

        # --- MODIFIED: Export with Progress Updates ---
        update_progress(0.92, "Initializing Excel Export...")
        output_buffer = io.BytesIO()
            
        def _write_sheet(frame, sheet_name):
            if frame is not None and not frame.empty:
                frame.to_excel(writer, sheet_name=sheet_name, index=False)

        try:
            import xlsxwriter  # noqa: F401
            excel_engine = "xlsxwriter"
        except ImportError:
            excel_engine = "openpyxl"
        with pd.ExcelWriter(output_buffer, engine=excel_engine) as writer:
            update_progress(0.93, "Exporting Company Totals Sheet...")
            if not company_totals.empty:
                company_totals.to_excel(writer, sheet_name='Company Totals', index=False)
                df_rules_14_15 = company_totals[
                    company_totals['Exclusion_Status'].str.contains('Rule 14|Rule 15', na=False)
                ].copy()
            else:
                pd.DataFrame(columns=['Message']).append(
                    {'Message': 'No Targets Available'}, ignore_index=True
                ).to_excel(writer, sheet_name='Company Totals', index=False)
                df_rules_14_15 = pd.DataFrame()

            update_progress(0.95, "Exporting Purchase & All Items Sheets...")
            _write_sheet(df_purchase, 'Purchase')
            update_progress(0.97, "Exporting All Items Sheet (May take a moment)...")
            df_all.to_excel(writer, sheet_name='All Items (With Status)', index=False)
            _write_sheet(df_blocked_final, 'Blocked Items')
            _write_sheet(df_reallocation, 'Stock Reallocation')

            update_progress(0.99, "Exporting Rules & Similar Sheets...")
            _write_sheet(df_rules_14_15, 'Rules 14 & 15 Items')
            if similar_df is not None:
                update_progress(0.99, "Exporting Detailed Similars Sheet...")
                m_main_col = next((c for c in similar_df.columns if 'main' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), similar_df.columns[0])
                m_sim_col = next((c for c in similar_df.columns if 'similar' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), similar_df.columns[2])
                main_codes = similar_df[m_main_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique()
                sim_codes = similar_df[m_sim_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique()
                all_sim_main_codes = set(main_codes).union(set(sim_codes))
                clean_materials = df_all['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                df_sim_detailed = df_all[clean_materials.isin(all_sim_main_codes)].copy()
                df_sim_detailed = df_sim_detailed.sort_values(by=['Material'])
                df_sim_detailed.to_excel(writer, sheet_name='Similars', index=False)
        update_progress(1.0, "Done!")

        output_buffer.seek(0)
        return output_buffer.getvalue()

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise