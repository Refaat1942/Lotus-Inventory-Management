"""Lotus replenishment processing engine for web."""
import datetime
import io
import os
import sqlite3
from typing import Callable, Optional

import numpy as np
import pandas as pd

APP_VERSION = "v2.1.5 (Web)"
DB_NAME = os.path.join(os.path.dirname(__file__), "lotus_replenishment_history.db")

TEMPLATES = {
    "main": ["Plnt", "Plant", "Material", "Material Group", "Material Description", "Branch Stock", "Pending to Branch", "Display", "Dc Stock", "Pending from DC", "Consumption90D", "Ref.Cons 30D", "Ref.Cons First 5D", "Sales Price", "Max Receipt", "Main Category", "SubCategory 1", "Storage Condition", "Manufacturer Name"],
    "targets": ["Plnt", "Plant", "Main Category", "Target Days"],
    "rank": ["Plnt", "Plant", "Rank"],
    "blocked": ["Plnt", "Plant", "Material", "Material Description"],
    "similar": ["Material ( Main)", "Material description (Main)", "Material (Similar)", "Material description (Similar)"],
}


def _normalize_material_column(frame: pd.DataFrame) -> pd.DataFrame:
    """Align Material codes across export sheets (matches purchase engine temp_mat logic)."""
    if frame.empty or "Material" not in frame.columns:
        return frame
    if "temp_mat" in frame.columns:
        frame["Material"] = frame["temp_mat"]
    elif "Main_Group_Mat" in frame.columns:
        frame["Material"] = frame["Main_Group_Mat"]
    else:
        frame["Material"] = (
            frame["Material"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
        )
    return frame


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


def display_branch_qty(stock, pending, display) -> pd.Series:
    """Qty needed at branch to reach Display (matches replenishment display rules)."""
    stock = pd.to_numeric(stock, errors="coerce").fillna(0)
    pending = pd.to_numeric(pending, errors="coerce").fillna(0)
    display = pd.to_numeric(display, errors="coerce").fillna(0)
    return safe_int_series(np.where(display > 0, np.maximum(0, np.ceil(display - stock - pending)), 0))


def build_blocked_display_req(df_blocked: pd.DataFrame) -> pd.DataFrame:
    """Blocked rows that still need Display shelf quantity in Final Required."""
    if df_blocked.empty:
        return df_blocked.copy()
    out = df_blocked.copy()
    idx = out.index
    stock = out["Stock"] if "Stock" in out.columns else pd.Series(0.0, index=idx)
    pending = (
        out["Pending preparation to branch"]
        if "Pending preparation to branch" in out.columns
        else pd.Series(0.0, index=idx)
    )
    display = out["Display"] if "Display" in out.columns else pd.Series(0.0, index=idx)
    qty = display_branch_qty(stock, pending, display).reindex(idx, fill_value=0)
    out["Final Required"] = qty
    out["rounded up required"] = qty
    out["required"] = qty.astype(float)
    if "Item_Role" not in out.columns:
        out["Item_Role"] = "Main"
    out["_skip_dc"] = True
    return out.loc[qty > 0].copy()


def floatify_integer_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Excel nullable Int64 columns reject fractional assignments — cast to float64."""
    for col in df.columns:
        if pd.api.types.is_bool_dtype(df[col]):
            continue
        if pd.api.types.is_integer_dtype(df[col]):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    return df


def standardize_columns(df):
    df.columns = df.columns.astype(str).str.strip()
    rename_map = {
        "Branch Stock": "Stock",
        "Pending to Branch": "Pending preparation to branch",
        "Pending from DC": "Pending preparation from DC",
        "Consumption90D": "Consumption last 90 days",
        "Ref.Cons 30D": "Consumption last 30 days",
        "Ref.Cons First 5D": "Consumption first 5 days of last month",
        "Min PR Date": "first receiving date",
        "MAX PR Date": "last receiving date",
    }
    df.rename(columns=rename_map, inplace=True)
    return df


def parse_rank_df(df_rank: pd.DataFrame) -> dict:
    rank_data = {}
    plant_cols = [c for c in df_rank.columns if c.strip().lower() in ["plnt", "plant", "branch"]]
    if not plant_cols:
        return rank_data
    rank_col = next((c for c in df_rank.columns if c.strip().lower() == "rank"), None)
    current_rank = 1
    for _, row in df_rank.iterrows():
        r_val = 999
        if rank_col:
            try:
                r_val = int(row[rank_col])
            except Exception:
                r_val = 999
        else:
            r_val = current_rank
            current_rank += 1
        for p_col in plant_cols:
            b_val = str(row[p_col]).strip()
            if b_val and b_val != "nan":
                rank_data[b_val] = r_val
    return rank_data


def parse_blocked_df(df_b: pd.DataFrame):
    blocked_items, blocked_branches = set(), set()
    plant_cols = [c for c in df_b.columns if c.strip().lower() in ["plnt", "plant", "branch"]]
    m_col = next((c for c in df_b.columns if c.strip().lower() in ["material", "item code"]), None)
    if not plant_cols:
        return blocked_items, blocked_branches
    for _, row in df_b.iterrows():
        for p_col in plant_cols:
            b = str(row[p_col]).strip().upper()
            if b and b != "nan":
                if m_col:
                    m = str(row[m_col]).strip()
                    if m.endswith(".0"):
                        m = m[:-2]
                    m = m.strip()
                    if m and m != "nan" and m != "":
                        blocked_items.add((b, m))
                    else:
                        blocked_branches.add(b)
                else:
                    blocked_branches.add(b)
    return blocked_items, blocked_branches


def extract_branches(main_df: pd.DataFrame) -> list[str]:
    df = standardize_columns(main_df.copy())
    plant_col = "Plant" if "Plant" in df.columns else "Plnt"
    if plant_col not in df.columns:
        raise ValueError(f"Column '{plant_col}' not found in the dataset.")
    return sorted(str(b) for b in df[plant_col].dropna().unique())


def apply_targets_excel(df_targets: pd.DataFrame, branches: list[str]) -> dict[str, dict[str, float]]:
    target_col = next((col for col in df_targets.columns if "target" in str(col).lower() or "days" in str(col).lower()), None)
    cat_col = next((col for col in df_targets.columns if "category" in str(col).lower()), None)
    if not cat_col or not target_col:
        raise ValueError("Targets Excel must contain 'Main Category' and 'Target Days'.")
    targets_map = {b: {"pharma": 0.0, "non_pharma": 0.0} for b in branches}
    for _, row in df_targets.iterrows():
        possible_plants = []
        if "Plnt" in df_targets.columns:
            possible_plants.append(str(row["Plnt"]).strip())
        if "Plant" in df_targets.columns:
            possible_plants.append(str(row["Plant"]).strip())
        cat = str(row[cat_col]).strip().lower()
        try:
            target_val = float(row[target_col])
        except Exception:
            continue
        matched_branch = next((p for p in possible_plants if p in targets_map), None)
        if matched_branch:
            if "non-pharma" in cat or "non_pharma" in cat or cat == "non pharma":
                targets_map[matched_branch]["non_pharma"] = target_val
            elif "pharma" in cat:
                targets_map[matched_branch]["pharma"] = target_val
    return targets_map


def export_history_bytes() -> Optional[bytes]:
    if not os.path.exists(DB_NAME):
        return None
    conn = sqlite3.connect(DB_NAME)
    history_df = pd.read_sql("SELECT * FROM orders_history", conn)
    conn.close()
    if history_df.empty:
        return None
    buf = io.BytesIO()
    history_df.to_excel(buf, index=False)
    buf.seek(0)
    return buf.getvalue()


def _progress(cb, val, text):
    if cb:
        cb(val, text)

def process_replenishment(
    main_df,
    branch_targets,
    rank_data=None,
    blocked_items=None,
    blocked_branches=None,
    similar_df=None,
    progress_callback=None,
):
    rank_data = rank_data or {}
    blocked_items = set(blocked_items or [])
    blocked_branches = set(blocked_branches or [])
    try:
            pass
            
            _progress(progress_callback, 0.1, "Loading main dataset...")
            df = floatify_integer_columns(standardize_columns(main_df.copy()))
            df = standardize_columns(df)
            plant_col = 'Plant' if 'Plant' in df.columns else 'Plnt'
            blocked_display_in_df = False
            
            _progress(progress_callback, 0.2, "Filtering blocked items & branches...")
            df_blocked_output = pd.DataFrame(columns=df.columns) 
            
            if blocked_items or blocked_branches:
                df['temp_mat'] = df['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                mask = pd.Series(False, index=df.index)
                
                for p_col in ['Plnt', 'Plant']:
                    if p_col in df.columns:
                        df['temp_p'] = df[p_col].astype(str).str.strip().str.upper()
                        if blocked_items:
                            item_mask = df.set_index(["temp_p", "temp_mat"]).index.isin(blocked_items)
                            mask = mask | pd.Series(item_mask, index=df.index)
                        if blocked_branches:
                            mask = mask | df["temp_p"].isin(blocked_branches)
                        df.drop(columns=['temp_p'], inplace=True)
                
                df_blocked_output = df[mask].drop(columns=['temp_mat']).copy()
                df = df[~mask].drop(columns=['temp_mat']).copy()

            df_blocked_display = build_blocked_display_req(df_blocked_output)
            if not df_blocked_output.empty:
                idx = df_blocked_output.index
                df_blocked_output = df_blocked_output.copy()
                df_blocked_output["Final Required"] = display_branch_qty(
                    df_blocked_output["Stock"] if "Stock" in df_blocked_output.columns else pd.Series(0.0, index=idx),
                    df_blocked_output["Pending preparation to branch"]
                    if "Pending preparation to branch" in df_blocked_output.columns
                    else pd.Series(0.0, index=idx),
                    df_blocked_output["Display"] if "Display" in df_blocked_output.columns else pd.Series(0.0, index=idx),
                ).reindex(idx, fill_value=0)

            if df.empty and df_blocked_display.empty:
                raise ValueError("No items left to process after filtering blocked items.")
            if df.empty:
                df = df_blocked_display.copy()
                blocked_display_in_df = True

            _progress(progress_callback, 0.25, "Processing Similar Items...")
            if 'temp_mat' not in df.columns:
                df['temp_mat'] = df['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                
            df['Main_Group_Mat'] = df['temp_mat']
            df['Item_Role'] = 'Main' 

            if similar_df is not None:
                sim_df = similar_df.copy()
                m_main_col = next((c for c in sim_df.columns if 'main' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), sim_df.columns[0])
                m_sim_col = next((c for c in sim_df.columns if 'similar' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), sim_df.columns[2])
                
                sim_dict = dict(zip(sim_df[m_sim_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip(), 
                                    sim_df[m_main_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()))
                
                df['Main_Group_Mat'] = df['temp_mat'].map(lambda x: sim_dict.get(x, x))
                df.loc[df['temp_mat'].isin(sim_dict.keys()), 'Item_Role'] = 'Similar'

                sim_keys = set(sim_dict.keys())
                sim_vals = set(sim_dict.values())
                pair_codes = sim_keys.union(sim_vals)
                df['Is_Sim_Main_Pair'] = df['temp_mat'].isin(pair_codes)
            else:
                df['Is_Sim_Main_Pair'] = False

            df['_Main_Stock'] = np.where(df['Item_Role'] == 'Main', df['Stock'], 0)
            df['_Sim_Stock'] = np.where(df['Item_Role'] == 'Similar', df['Stock'], 0)
            df['_Main_Cons'] = np.where(df['Item_Role'] == 'Main', df['Consumption last 90 days'], 0)
            df['_Sim_Cons'] = np.where(df['Item_Role'] == 'Similar', df['Consumption last 90 days'], 0)

            branch_agg = df.groupby([plant_col, 'Main_Group_Mat']).agg(
                Total_Stock_Group=('Stock', 'sum'),
                Total_Cons_Group=('Consumption last 90 days', 'sum'),
                Total_Cons30_Group=('Consumption last 30 days', 'sum'),
                Total_Cons5_Group=('Consumption first 5 days of last month', 'sum'),
                Main_Item_Stock=('_Main_Stock', 'sum'),
                Similar_Item_Stock=('_Sim_Stock', 'sum'),
                Main_Item_Cons=('_Main_Cons', 'sum'), 
                Similar_Item_Cons=('_Sim_Cons', 'sum')
            ).reset_index()

            df.drop(columns=['_Main_Stock', '_Sim_Stock', '_Main_Cons', '_Sim_Cons'], inplace=True)

            df = df.merge(branch_agg, on=[plant_col, 'Main_Group_Mat'], how='left')
            df['Stock'] = df['Total_Stock_Group']
            df['Consumption last 90 days'] = df['Total_Cons_Group']
            df['Consumption last 30 days'] = df['Total_Cons30_Group']
            df['Consumption first 5 days of last month'] = df['Total_Cons5_Group']

            _progress(progress_callback, 0.3, "Applying targets & configuring rules...")
            if 'Material Description' not in df.columns: df['Material Description'] = "Unknown"
            if 'Display' not in df.columns: df['Display'] = 0

            targets_map = branch_targets

            def get_initial_target(row):
                branch_name = row.get(plant_col)
                category = str(row.get('Main Category', '')).lower().strip()
                branch_targets = targets_map.get(branch_name, {'pharma': 0.0, 'non_pharma': 0.0})
                
                if 'non' in category:
                    return branch_targets['non_pharma']
                elif 'pharma' in category:
                    return branch_targets['pharma']
                else:
                    return branch_targets['non_pharma']

            df['target stock days chosen'] = df.apply(get_initial_target, axis=1)

            num_cols = ['Consumption last 30 days', 'Consumption last 90 days', 'Consumption first 5 days of last month', 
                        'Stock', 'Pending preparation to branch', 'Display', 'Dc Stock', 'Pending preparation from DC']
            for col in num_cols:
                if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                else: df[col] = 0.0

            ratio_first_5 = df['Consumption first 5 days of last month'] / (df['Consumption last 90 days'] / 3).replace(0, np.nan)
            df.loc[ratio_first_5 > 0.8, 'target stock days chosen'] = 30

            ratio_30_90 = df['Consumption last 30 days'] / df['Consumption last 90 days'].replace(0, np.nan)
            df['consumption days chosen'] = 90
            df.loc[ratio_30_90 >= 1.0, 'consumption days chosen'] = 30
            df.loc[(ratio_30_90 >= 0.8) & (ratio_30_90 < 1.0), 'consumption days chosen'] = 45
            
            df['daily_consumption'] = df['Consumption last 90 days'] / df['consumption days chosen']

            _progress(progress_callback, 0.5, "Running base distribution engine (Push & Pull)...")
            
            def process_material_group(group):
                group = floatify_integer_columns(group.copy())
                if "_skip_dc" in group.columns and group["_skip_dc"].all():
                    qty = safe_int_series(group["Final Required"])
                    group["rounded up required"] = qty
                    group["original_required"] = qty
                    group["original_raw_required"] = group["required"]
                    return group
                branch_group = group.drop_duplicates(subset=[plant_col]).copy()
                
                def evaluate_requirements(current_targets, use_display=True):
                    req = (branch_group['daily_consumption'] * current_targets) - (branch_group['Stock'] + branch_group['Pending preparation to branch'])
                    req_updated = req.copy()
                    req_updated[req_updated < 0] = 0
                    
                    if use_display:
                        curr_tot = branch_group['Stock'] + req_updated + branch_group['Pending preparation to branch']
                        mask_disp = (branch_group['Display'] > 0) & (curr_tot < branch_group['Display'])
                        display_gap = (
                            branch_group['Display'][mask_disp]
                            - branch_group['Stock'][mask_disp]
                            - branch_group['Pending preparation to branch'][mask_disp]
                        )
                        req_updated[mask_disp] = np.ceil(display_gap).clip(lower=0)
                    
                    req_updated[(branch_group['daily_consumption'] == 0) & (branch_group['Display'] == 0)] = 0
                    return req_updated, np.ceil(req_updated)

                initial_targets = branch_group['target stock days chosen'].copy()
                raw_req, rounded_req = evaluate_requirements(initial_targets, use_display=True)
                _, absolute_full_req = evaluate_requirements(initial_targets, use_display=True)
                
                branch_group['original_raw_required'] = raw_req
                branch_group['original_required'] = rounded_req
                
                group['original_raw_required'] = 0.0
                group['original_required'] = 0.0
                for b_name in branch_group[plant_col]:
                    b_mask = group[plant_col] == b_name
                    orig_raw = branch_group.loc[branch_group[plant_col] == b_name, 'original_raw_required'].iloc[0]
                    orig_round = branch_group.loc[branch_group[plant_col] == b_name, 'original_required'].iloc[0]
                    
                    main_idx = group[b_mask & (group['Item_Role'] == 'Main')].index
                    if not main_idx.empty:
                        group.loc[main_idx[0], 'original_raw_required'] = orig_raw
                        group.loc[main_idx[0], 'original_required'] = orig_round
                    else:
                        first_idx = group[b_mask].index[0]
                        group.loc[first_idx, 'original_raw_required'] = orig_raw
                        group.loc[first_idx, 'original_required'] = orig_round

                total_dc_stock = group.groupby('temp_mat')['Dc Stock'].first().sum()
                pending_dc = group.groupby('temp_mat')['Pending preparation from DC'].first().sum() if 'Pending preparation from DC' in group.columns else 0
                dc_stock = max(0, total_dc_stock - pending_dc)
                
                group['required'] = 0.0
                group['rounded up required'] = 0.0
                group['Final Allocated Target Days'] = group['target stock days chosen'].astype(float)
                
                if dc_stock <= 0:
                    return group
                    
                _, display_only_req = evaluate_requirements(initial_targets * 0, use_display=True)
                can_afford_display = display_only_req.sum() <= dc_stock
                raw_req, rounded_req = evaluate_requirements(initial_targets, use_display=can_afford_display)
                total_required = rounded_req.sum()

                # --- التعديل الجوهري: إلغاء الفورس درين لو الصنف من عائلة (Main/Similar) ---
                is_pair_group = group['Is_Sim_Main_Pair'].iloc[0] if 'Is_Sim_Main_Pair' in group.columns else False
                force_drain_allowed = (total_required > dc_stock) and not is_pair_group

                rank_lookup_col = plant_col
                
                if total_required > dc_stock:
                    low = 0.0
                    high = float(initial_targets.max())
                    
                    best_targets = initial_targets * 0
                    raw_allocation, best_rounded = evaluate_requirements(best_targets, use_display=can_afford_display)
                    
                    for _ in range(12):
                        mid = (low + high) / 2.0
                        test_targets = np.minimum(initial_targets, mid)
                        test_raw, test_rounded = evaluate_requirements(test_targets, use_display=can_afford_display)
                        
                        if test_rounded.sum() <= dc_stock:
                            best_targets = test_targets
                            best_rounded = test_rounded
                            raw_allocation = test_raw
                            low = mid
                        else:
                            high = mid
                            
                    remainder = int(dc_stock - best_rounded.sum())
                else:
                    best_rounded = rounded_req.copy()
                    best_targets = initial_targets.copy()
                    raw_allocation = raw_req.copy()
                    remainder = int(dc_stock - best_rounded.sum())

                temp_group = branch_group.copy()
                temp_group['Rank'] = temp_group[rank_lookup_col].map(lambda x: rank_data.get(str(x).strip(), 999))
                
                # الدورة الأولى: سد العجز الفعلي في المطلوب المطلق
                unfulfilled = absolute_full_req - best_rounded
                unfulfilled[unfulfilled < 0] = 0

                if remainder > 0 and unfulfilled.sum() > 0:
                    temp_group['Unfulfilled'] = unfulfilled
                    sorted_idx = temp_group[temp_group['Unfulfilled'] > 0].sort_values(by=['daily_consumption', 'Rank'], ascending=[False, True]).index
                    for current_idx in sorted_idx:
                        if remainder <= 0: break
                        needed = float(temp_group.loc[current_idx, 'Unfulfilled'])
                        taken = int(min(needed, remainder))
                        best_rounded.loc[current_idx] += taken
                        remainder -= taken

                # الدورة الثانية: التفريغ الإجباري (ملغية لعائلة الـ Similar بالكامل بفضل الشرط اللي فوق)
                if remainder > 0 and force_drain_allowed:
                    temp_group['Has_Need'] = absolute_full_req > 0
                    sorted_idx = temp_group[temp_group['Has_Need']].sort_values(by=['daily_consumption', 'Rank'], ascending=[False, True]).index
                    if len(sorted_idx) > 0:
                        while remainder > 0:
                            for current_idx in sorted_idx:
                                if remainder <= 0: break
                                best_rounded.loc[current_idx] += 1
                                remainder -= 1

                branch_group['Final Allocated Target Days'] = best_targets
                branch_group['rounded up required'] = best_rounded
                branch_group['required'] = raw_allocation

                group['required'] = 0.0
                group['rounded up required'] = 0.0

                dc_stock_dict = {}
                for m in group['temp_mat'].unique():
                    m_rows = group[group['temp_mat'] == m]
                    m_raw = m_rows['Dc Stock'].iloc[0]
                    m_pend = m_rows['Pending preparation from DC'].iloc[0] if 'Pending preparation from DC' in m_rows.columns else 0
                    dc_stock_dict[m] = max(0, m_raw - m_pend)

                # أولوية توزيع الأصناف: الـ Similar الأول ثم الـ Main
                sorted_mats = group.sort_values(by='Item_Role', ascending=False)['temp_mat'].unique()

                # التوزيع حسب الأكثر استهلاكاً
                sorted_bg = branch_group.sort_values(by='daily_consumption', ascending=False)
                
                alloc_dict = dict(zip(sorted_bg[plant_col], sorted_bg['rounded up required']))
                targets_dict = dict(zip(sorted_bg[plant_col], sorted_bg['Final Allocated Target Days']))
                
                for b_name, total_rounded_need in alloc_dict.items():
                    group_mask = group[plant_col] == b_name
                    group.loc[group_mask, 'Final Allocated Target Days'] = float(targets_dict.get(b_name, 0))

                    if total_rounded_need <= 0:
                        continue

                    remaining_to_fulfill = int(total_rounded_need)
                    for m_code in sorted_mats:
                        if remaining_to_fulfill <= 0:
                            break
                        m_avail = int(dc_stock_dict.get(m_code, 0))
                        if m_avail <= 0:
                            continue

                        take = int(min(remaining_to_fulfill, m_avail))
                        idx = group[(group[plant_col] == b_name) & (group['temp_mat'] == m_code)].index

                        group.loc[idx, 'rounded up required'] += take
                        raw_need = branch_group.loc[branch_group[plant_col] == b_name, 'required'].iloc[0]
                        if total_rounded_need > 0:
                            group.loc[idx, 'required'] += (take / total_rounded_need) * raw_need

                        dc_stock_dict[m_code] -= take
                        remaining_to_fulfill -= take
                        
                return group

            if 'Material' in df.columns:
                df = df.groupby('Main_Group_Mat', group_keys=False).apply(process_material_group)

            for qty_col in ('rounded up required', 'original_required', 'original_raw_required', 'required'):
                if qty_col in df.columns:
                    df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0.0)
            
            _progress(progress_callback, 0.8, "Finalizing calculations & coverage...")
            
            df['DC Capped Required'] = safe_int_series(df['rounded up required'])
            df['rounded up required'] = safe_int_series(df['original_required'])
            df['required'] = df['original_raw_required']
            
            df['Final Required'] = df['DC Capped Required']
            
            df['%req (final requirement /branch stock)'] = np.where(df['Stock'] == 0, 0.0, df['Final Required'] / df['Stock'])
            
                # 1. نحسب إجمالي المطلوب الأصلي وإجمالي المتوزع الفعلي للصنف ككل
            mat_orig_req = df.groupby('temp_mat')['rounded up required'].transform('sum')
            mat_final_req = df.groupby('temp_mat')['Final Required'].transform('sum')

            # 2. نعتبر إن حصل Adjustment لو الإجمالي اللي اتوزع أقل من الإجمالي المطلوب 
            is_material_adjusted = mat_final_req < mat_orig_req

            # 3. تطبيق قاعدة الـ 20%
            mask_20pct = (
                (df['%req (final requirement /branch stock)'] > 0) & 
                (df['%req (final requirement /branch stock)'] <= 0.2) & 
                (~df['Is_Sim_Main_Pair']) & 
                (~is_material_adjusted)
            )
            if "_skip_dc" in df.columns:
                mask_20pct = mask_20pct & ~df["_skip_dc"].fillna(False)
            df.loc[mask_20pct, 'Final Required'] = 0
            
            def calc_expected_coverage(row):
                if row['daily_consumption'] > 0:
                    total_stock_after = row['Stock'] + row['Pending preparation to branch'] + row['Final Required']
                    coverage = total_stock_after / row['daily_consumption']
                    return round(coverage, 1)
                else:
                    return ">999 (No Cons)"
            
            df['Expected Coverage Days'] = df.apply(calc_expected_coverage, axis=1)

            df_final = df.copy()

            if not df_blocked_display.empty:
                if "temp_mat" not in df_blocked_display.columns and "Material" in df_blocked_display.columns:
                    df_blocked_display["temp_mat"] = (
                        df_blocked_display["Material"]
                        .astype(str)
                        .str.replace(r"\.0$", "", regex=True)
                        .str.strip()
                    )
                if not blocked_display_in_df:
                    df_final = pd.concat([df_final, df_blocked_display], ignore_index=True)

            if df_final.empty:
                raise ValueError("No data available to export.")

            df_final = _normalize_material_column(df_final)

            _progress(progress_callback, 0.9, "Preparing export sheets...")
            
            # --- FIX 1: Rename columns back to their expected names ---
            df_final.rename(columns={
                'Pending preparation from DC': 'Pending from DC',
                'Pending preparation to branch': 'Pending to Branch'
            }, inplace=True)

            output_cols = [
                'Plnt', 'Plant', 'Material', 'Material Description', 'Item_Role', 'Stock', 
                'Main_Item_Stock', 'Main_Item_Cons', 'Similar_Item_Stock', 'Similar_Item_Cons', 'Display', 
                '%req (final requirement /branch stock)', 'Dc Stock', 'Consumption last 90 days', 
                'Consumption last 30 days', 'required', 'rounded up required', 'Final Required', 
                'target stock days chosen', 'Final Allocated Target Days', 'Expected Coverage Days', 
                'consumption days chosen', 'Consumption first 5 days of last month', 
                'Pending from DC', 'Pending to Branch', 'Sales Price', 
                'Max Receipt', 'last receiving date', 'first receiving date', 'Created On', 
                'Main Category', 'SubCategory 1', 'Storage Condition', 'Manufacturer Name'
            ]
            
            for col in output_cols:
                if col not in df_final.columns: df_final[col] = ""

            for qty_col in ('rounded up required', 'Final Required'):
                if qty_col in df_final.columns:
                    df_final[qty_col] = safe_int_series(df_final[qty_col])
                    
            main_output = df_final[output_cols]

            df_action_only = df_final[df_final['Final Required'] > 0].copy()
            
            # Branch Summary relies only on items that actually got allocated
            summary_data = df_action_only.groupby(plant_col).agg(
                Total_Items_Prepared=('Material', 'count'),
                Sum_of_Quantities=('Final Required', 'sum')
            ).reset_index() if plant_col in df_action_only.columns else pd.DataFrame()
            
            # DC Stock Summary: every material in Final Requirement (including zero-allocation rows).
            dc_summary = df_final.groupby("Material", as_index=False).agg(
                Material_Description=("Material Description", "first"),
                Initial_DC_Stock=("Dc Stock", "first"),
                Total_Allocated=("Final Required", "sum"),
            ) if "Material" in df_final.columns else pd.DataFrame()
            
            if not dc_summary.empty:
                dc_summary['Remaining_DC_Stock'] = dc_summary['Initial_DC_Stock'] - dc_summary['Total_Allocated']
            
            df_adjusted_base = df_final.copy()
            df_adjusted_base['Original Required'] = safe_int_series(df_adjusted_base['rounded up required'])
            df_adjusted_base['Adjusted Required'] = safe_int_series(df_adjusted_base['Final Required'])
            df_adjusted_base['Difference'] = df_adjusted_base['Adjusted Required'] - df_adjusted_base['Original Required']
            
            adjusted_df = df_adjusted_base[df_adjusted_base['Difference'] < 0].copy()
            
            if not adjusted_df.empty:
                adj_cols = ['Material', 'Material Description', plant_col, 'Original Required', 'Adjusted Required', 'Difference']
                adjusted_df = adjusted_df[[c for c in adj_cols if c in adjusted_df.columns]]
                if plant_col in adjusted_df.columns:
                    adjusted_df.rename(columns={plant_col: 'Plant'}, inplace=True)
                adjusted_df = adjusted_df.sort_values(by='Difference', ascending=True)

            run_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db_data = main_output.copy()
            db_data.insert(0, 'Run_Date', run_timestamp) 
            
            try:
                conn = sqlite3.connect(DB_NAME)
                db_data.to_sql('orders_history', conn, if_exists='append', index=False)
                conn.close()
            except Exception as e:
                pass

            _progress(progress_callback, 0.9, "Preparing export...")
            buf = io.BytesIO()
            total_sheets = 3
            if not adjusted_df.empty:
                total_sheets += 1
            if not df_blocked_output.empty:
                total_sheets += 1
            if similar_df is not None:
                total_sheets += 1
            current_sheet = 0

            def update_save_progress(sheet_name):
                nonlocal current_sheet
                current_sheet += 1
                _progress(progress_callback, 0.9 + (0.1 * (current_sheet / total_sheets)), f"Saving Sheet: {sheet_name} ({current_sheet}/{total_sheets})...")

            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                update_save_progress("Final Requirement")
                main_output.to_excel(writer, sheet_name="Final Requirement", index=False)
                update_save_progress("Branch Summary")
                summary_data.to_excel(writer, sheet_name="Branch Summary", index=False)
                update_save_progress("DC Stock Summary")
                dc_summary.to_excel(writer, sheet_name="DC Stock Summary", index=False)
                if not adjusted_df.empty:
                    update_save_progress("Adjusted Items")
                    adjusted_df.to_excel(writer, sheet_name="Adjusted Items", index=False)
                if not df_blocked_output.empty:
                    update_save_progress("Blocked Items")
                    df_blocked_output.to_excel(writer, sheet_name="Blocked Items", index=False)
                if similar_df is not None:
                    _progress(progress_callback, 0.98, "Preparing Similars Sheet data...")
                    m_main_col = next((c for c in similar_df.columns if "main" in c.lower() and "material" in c.lower() and "desc" not in c.lower()), similar_df.columns[0])
                    m_sim_col = next((c for c in similar_df.columns if "similar" in c.lower() and "material" in c.lower() and "desc" not in c.lower()), similar_df.columns[2])
                    main_codes = similar_df[m_main_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip().unique()
                    sim_codes = similar_df[m_sim_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip().unique()
                    all_sim_main_codes = set(main_codes).union(set(sim_codes))
                    df_all_for_similars = _normalize_material_column(df.copy())
                    for col in output_cols:
                        if col not in df_all_for_similars.columns:
                            df_all_for_similars[col] = ""
                    df_all_for_similars = df_all_for_similars[output_cols]
                    clean_materials = df_all_for_similars["Material"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
                    df_sim_detailed = df_all_for_similars[clean_materials.isin(all_sim_main_codes)].copy()
                    df_sim_detailed = df_sim_detailed.sort_values(by=["Material"])
                    update_save_progress("Similars")
                    df_sim_detailed.to_excel(writer, sheet_name="Similars", index=False)
            _progress(progress_callback, 1.0, "Export completed")
            buf.seek(0)
            return buf.getvalue()

    except Exception as e:
        raise ValueError(str(e)) from e
