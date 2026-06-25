"""Build web replenishment_engine.py from GUI backup (line-safe)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "replenishment_engine_gui_backup.py"
OUT = ROOT / "replenishment_engine.py"

lines = SRC.read_text(encoding="utf-8").splitlines()
start = next(i for i, l in enumerate(lines) if "def process_data(self):" in l)
end = next(i for i, l in enumerate(lines) if "def export_history(self):" in l)
body = "\n".join(lines[start:end])

replacements = [
    ("    def process_data(self):", "def process_replenishment(\n    main_df,\n    branch_targets,\n    rank_data=None,\n    blocked_items=None,\n    blocked_branches=None,\n    similar_df=None,\n    progress_callback=None,\n):"),
    ("self.update_progress(", "_progress(progress_callback, "),
    ("self.hide_progress()", "pass"),
    ('self.process_btn.configure(state="disabled")', "pass"),
    ('self.process_btn.configure(state="normal")', "pass"),
    ("pd.read_excel(self.file_path)", "standardize_columns(main_df.copy())"),
    ("df = self.standardize_columns(df)", "df = standardize_columns(df)"),
    ("if self.blocked_items or self.blocked_branches:", "if blocked_items or blocked_branches:"),
    ("if self.blocked_items:", "if blocked_items:"),
    ("if self.blocked_branches:", "if blocked_branches:"),
    ("self.blocked_items", "blocked_items"),
    ("self.blocked_branches", "blocked_branches"),
    ("if hasattr(self, 'similar_df') and self.similar_df is not None:", "if similar_df is not None:"),
    ("self.similar_df", "similar_df"),
    ("self.rank_data.get", "rank_data.get"),
    ("self.db_name", "DB_NAME"),
]

for old, new in replacements:
    body = body.replace(old, new)

body = body.replace("        try:", "    rank_data = rank_data or {}\n    blocked_items = set(blocked_items or [])\n    blocked_branches = set(blocked_branches or [])\n    try:", 1)

old_targets = """            targets_map = {}
            for b, inputs in self.branch_inputs.items():
                try:
                    p_val = inputs['pharma'].get().strip()
                    np_val = inputs['non_pharma'].get().strip()
                    targets_map[b] = {'pharma': float(p_val) if p_val else 0.0, 'non_pharma': float(np_val) if np_val else 0.0}
                except ValueError:
                    targets_map[b] = {'pharma': 0.0, 'non_pharma': 0.0}"""
body = body.replace(old_targets, "            targets_map = branch_targets")

body = body.replace(
    'messagebox.showinfo("Result Empty", "No items left to process after filtering blocked items.")\n                pass\n                pass\n                return',
    'raise ValueError("No items left to process after filtering blocked items.")',
)
body = body.replace(
    'messagebox.showinfo("Result Empty", "No data available to export.")\n                pass\n                pass\n                return',
    'raise ValueError("No data available to export.")',
)
body = body.replace(
    'messagebox.showwarning("Database Warning", f"Could not save history to database: {e}")',
    "pass",
)

save_start = body.index("            save_path = fd.asksaveasfilename")
except_pos = body.index("        except Exception as e:")
export_new = """            buf = io.BytesIO()
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
                    main_codes = similar_df[m_main_col].astype(str).str.replace(r"\\.0$", "", regex=True).str.strip().unique()
                    sim_codes = similar_df[m_sim_col].astype(str).str.replace(r"\\.0$", "", regex=True).str.strip().unique()
                    all_sim_main_codes = set(main_codes).union(set(sim_codes))
                    df_all_for_similars = df.copy()
                    for col in output_cols:
                        if col not in df_all_for_similars.columns:
                            df_all_for_similars[col] = ""
                    df_all_for_similars = df_all_for_similars[output_cols]
                    clean_materials = df_all_for_similars["Material"].astype(str).str.replace(r"\\.0$", "", regex=True).str.strip()
                    df_sim_detailed = df_all_for_similars[clean_materials.isin(all_sim_main_codes)].copy()
                    df_sim_detailed = df_sim_detailed.sort_values(by=["Material"])
                    update_save_progress("Similars")
                    df_sim_detailed.to_excel(writer, sheet_name="Similars", index=False)
            _progress(progress_callback, 1.0, "Export completed")
            buf.seek(0)
            return buf.getvalue()

"""
body = body[:save_start] + export_new + body[except_pos:]
body = body.replace(
    "        except Exception as e:\n            messagebox.showerror(\"Processing Error\", f\"An error occurred during calculation:\\n{str(e)}\")\n        finally:\n            pass\n            pass",
    "    except Exception as e:\n        raise ValueError(str(e)) from e",
)

header = open(Path(__file__).parent / "_repl_header_snippet.txt", encoding="utf-8").read()

OUT.write_text(header + body, encoding="utf-8")
print(f"OK: {OUT.stat().st_size} bytes, {len(OUT.read_text(encoding='utf-8').splitlines())} lines")
