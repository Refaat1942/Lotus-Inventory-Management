import customtkinter as ctk
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog
import pandas as pd
import numpy as np
from PIL import Image
import subprocess
import platform
import socket
import base64
import os
import sys
import sqlite3
import datetime
import hashlib
import uuid

# ==========================================
# نظام الحماية والتفعيل المطور (Offline License)
# ==========================================
SECRET_SALT = "LOTUS_PHARMA_2026_SUPER_SECRET_KEY"

def get_machine_id():
    try:
        output = subprocess.check_output('wmic baseboard get serialnumber', shell=True).decode()
        hw_id = output.replace('SerialNumber', '').strip()
        if not hw_id or hw_id.lower() in ["none", "default string", "to be filled by o.e.m."]:
            output = subprocess.check_output('wmic csproduct get uuid', shell=True).decode()
            hw_id = output.replace('UUID', '').strip()
        if hw_id:
            return hashlib.md5(hw_id.encode()).hexdigest()[:10].upper()
    except Exception:
        pass
    mac = uuid.getnode()
    return hashlib.md5(str(mac).encode()).hexdigest()[:10].upper()

def generate_expected_key(machine_id):
    raw_string = f"{machine_id}_{SECRET_SALT}"
    return hashlib.sha256(raw_string.encode()).hexdigest()[:16].upper()

def xor_crypt(text, key):
    return "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(text))

class ActivationDialog(ctk.CTkToplevel):
    def __init__(self, parent, msg):
        super().__init__(parent)
        self.title("تفعيل ترخيص لوتس")
        self.geometry("600x350")
        self.user_key = None
        
        self.attributes('-topmost', True)
        self.resizable(False, False)

        lbl = ctk.CTkLabel(self, text=msg, justify="center", font=("Segoe UI", 16))
        lbl.pack(pady=(30, 20), padx=20)
        
        self.entry = ctk.CTkEntry(self, width=400, height=45, justify="center", font=("Segoe UI", 18, "bold"), placeholder_text="أدخل كود التفعيل هنا")
        self.entry.pack(pady=15)
        self._enable_copy_paste(self.entry) 
        
        btn = ctk.CTkButton(self, text="تفعيل النظام", font=("Segoe UI", 16, "bold"), height=40, command=self.submit)
        btn.pack(pady=10)
        
    def _enable_copy_paste(self, widget):
        menu = tk.Menu(self, tearoff=0, bg="#2c3e50", fg="white", font=("Segoe UI", 11))
        def paste_action():
            try: widget.insert("insert", widget.clipboard_get())
            except: pass
        def copy_action():
            try: text = widget.selection_get()
            except: text = widget.get()
            if text:
                widget.clipboard_clear()
                widget.clipboard_append(text)
        menu.add_command(label="Copy (نسخ)", command=copy_action)
        menu.add_command(label="Paste (لصق)", command=paste_action)

        widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        widget.bind("<Control-v>", lambda e: paste_action() or "break")
        widget.bind("<Control-c>", lambda e: copy_action() or "break")

    def submit(self):
        self.user_key = self.entry.get()
        self.destroy()

def check_license():
    machine_id = get_machine_id()
    expected_key = generate_expected_key(machine_id)
    license_file = "lotus.lic"

    if os.path.exists(license_file):
        with open(license_file, "r") as f:
            if f.read().strip() == expected_key:
                return True 

    hostname = socket.gethostname()
    os_info = f"{platform.system()} {platform.release()}"
    raw_data = f"{machine_id}|{hostname}|{os_info}"
    
    encrypted_data = base64.b64encode(xor_crypt(raw_data, SECRET_SALT).encode('utf-8')).decode('utf-8')
    info_file = "Device_Request.lotus"
    
    with open(info_file, "w") as f:
        f.write(encrypted_data)

    root = ctk.CTk()
    root.withdraw()
    
    msg = f"هذا الجهاز غير مصرح له باستخدام النظام.\n\nتم إنشاء ملف مشفر باسم ({info_file}) بجوار البرنامج.\nبرجاء إرسال هذا الملف للإدارة للحصول على كود التفعيل."
    
    dialog = ActivationDialog(root, msg)
    root.wait_window(dialog)
    
    user_key = dialog.user_key

    if user_key and user_key.strip().upper() == expected_key:
        with open(license_file, "w") as f:
            f.write(user_key.strip().upper())
        messagebox.showinfo("نجاح", "تم تفعيل النظام بنجاح!")
        root.destroy()
        return True
    else:
        messagebox.showerror("خطأ", "كود التفعيل غير صحيح. سيتم إغلاق النظام.")
        sys.exit()

check_license()
# ==========================================

# --- App Version ---
APP_VERSION = "v2.0.8 (Pairs Excluded from Force Drain)"

# --- Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class LotusApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.withdraw()  
        self.file_path = None
        self.branch_inputs = {}
        self.db_name = "lotus_history.db" 
        self.rank_data = {} 
        self.blocked_items = set() 
        self.blocked_branches = set()
        self.similar_df = None

        # --- Splash Screen Setup ---
        self.splash = ctk.CTkToplevel(self)
        self.splash.overrideredirect(True) 
        
        width, height = 700, 450 
        screen_width = self.splash.winfo_screenwidth()
        screen_height = self.splash.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.splash.geometry(f'{width}x{height}+{x}+{y}')
        
        self.splash.configure(fg_color="#FFFFFF")
        self.splash.attributes('-topmost', True)

        try:
            logo_path = resource_path("logo.png")
            logo_img = ctk.CTkImage(light_image=Image.open(logo_path), 
                                    dark_image=Image.open(logo_path), 
                                    size=(160, 160))
            ctk.CTkLabel(self.splash, image=logo_img, text="").pack(pady=(50, 10))
        except:
            ctk.CTkLabel(self.splash, text="LOTUS", font=("Segoe UI", 65, "bold"), text_color="#2980b9").pack(pady=(60, 10))

        ctk.CTkLabel(self.splash, text=f"Lotus Replenishment Platform", 
                     font=("Segoe UI", 20, "bold"), text_color="#2c3e50").pack(pady=5)
        ctk.CTkLabel(self.splash, text=APP_VERSION, 
                     font=("Segoe UI", 12), text_color="#7f8c8d").pack(pady=0)
        
        self.progress_bar = ctk.CTkProgressBar(self.splash, width=300, height=8, 
                                               fg_color="#ecf0f1", progress_color="#3498db")
        self.progress_bar.pack(pady=25)
        self.progress_bar.set(0)

        ctk.CTkLabel(self.splash, text="Copyright © Lotus Pharmacies 2026", 
                     font=("Segoe UI", 13, "bold"), text_color="#2c3e50").pack(side="bottom", pady=20)

        self.animation_step = 0
        self.animate_splash()

    def download_similar_template(self):
        cols = ['Material ( Main)', 'Material description (Main)', 'Material (Similar)', 'Material description (Similar)']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", initialfile="Similar_Items_Template.xlsx", title="Save Similar Template")
        if path: df.to_excel(path, index=False)

    def load_similar_from_excel(self):
        path = fd.askopenfilename(filetypes=[('Excel files', '*.xlsx *.xls')])
        if path:
            try:
                self.similar_df = pd.read_excel(path)
                self.load_similar_btn.configure(text="Similar Loaded ✔", fg_color="#27ae60")
            except Exception: pass    

    def animate_splash(self):
        self.animation_step += 0.01
        self.progress_bar.set(self.animation_step)
        
        if self.animation_step < 1.0:
            self.after(50, self.animate_splash) 
        else:
            self.start_main_app()

    def start_main_app(self):
        self.splash.destroy()
        self.title(f"Lotus Replenishment Platform - {APP_VERSION}")
        self.geometry("1000x850")
        
        try:
            self.iconbitmap(resource_path("inventory.ico"))
        except:
            pass

        self.deiconify()
        self.setup_ui()

    def setup_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(header, text=f"Lotus Replenishment Platform", font=("Segoe UI", 28, "bold")).pack(side="left")
        
        self.theme_switch = ctk.CTkSwitch(header, text="Light Mode", command=self.toggle_theme, 
                                          font=("Segoe UI", 12, "bold"))
        self.theme_switch.pack(side="right", pady=10)

        templates_frame = ctk.CTkFrame(self, fg_color="transparent")
        templates_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(templates_frame, text="Download Templates:", font=("Segoe UI", 14, "bold")).pack(side="left", padx=(0, 10))
        ctk.CTkButton(templates_frame, text="Main Dataset", width=110, height=28, fg_color="#34495e", command=self.download_main_template).pack(side="left", padx=5)
        ctk.CTkButton(templates_frame, text="Targets", width=110, height=28, fg_color="#34495e", command=self.download_targets_template).pack(side="left", padx=5)
        ctk.CTkButton(templates_frame, text="Ranks", width=110, height=28, fg_color="#34495e", command=self.download_rank_template).pack(side="left", padx=5)
        ctk.CTkButton(templates_frame, text="Blocked Items", width=110, height=28, fg_color="#34495e", command=self.download_blocked_template).pack(side="left", padx=5)
        ctk.CTkButton(templates_frame, text="Similar Items", width=110, height=28, fg_color="#34495e", command=self.download_similar_template).pack(side="left", padx=5)
        
        upload_frame = ctk.CTkFrame(self)
        upload_frame.pack(fill="x", padx=20, pady=5)
        
        self.file_label = ctk.CTkLabel(upload_frame, text="Please upload an Excel sheet to begin configuration.", font=("Segoe UI", 14))
        self.file_label.pack(side="left", padx=20, pady=15)

        ctk.CTkButton(upload_frame, text="Upload Excel Sheet", font=("Segoe UI", 14, "bold"), 
                      command=self.upload_and_load_branches).pack(side="right", padx=20, pady=15)

        self.settings_label = ctk.CTkLabel(self, text="Branch Configuration & Rules:", font=("Segoe UI", 16, "bold"))
        self.settings_label.pack(pady=(15, 5), anchor="w", padx=30)
        
        targets_tools_frame = ctk.CTkFrame(self, fg_color="transparent")
        targets_tools_frame.pack(fill="x", padx=30, pady=(0, 10))
        
        self.load_targets_btn = ctk.CTkButton(targets_tools_frame, text="Upload Targets Excel", 
                                              command=self.load_targets_from_excel, 
                                              font=("Segoe UI", 12, "bold"), width=140, fg_color="#8e44ad", hover_color="#9b59b6")
        self.load_targets_btn.pack(side="left", padx=(0, 10))
        
        self.load_rank_btn = ctk.CTkButton(targets_tools_frame, text="Upload Rank Excel", 
                                              command=self.load_rank_from_excel, 
                                              font=("Segoe UI", 12, "bold"), width=140, fg_color="#e67e22", hover_color="#d35400")
        self.load_rank_btn.pack(side="left", padx=(0, 10))

        self.load_blocked_btn = ctk.CTkButton(targets_tools_frame, text="Upload Blocked Items", 
                                              command=self.load_blocked_from_excel, 
                                              font=("Segoe UI", 12, "bold"), width=140, fg_color="#c0392b", hover_color="#e74c3c")
        self.load_blocked_btn.pack(side="left")
        
        self.load_similar_btn = ctk.CTkButton(targets_tools_frame, text="Upload Similar Excel", 
                                      command=self.load_similar_from_excel, 
                                      font=("Segoe UI", 12, "bold"), width=140, fg_color="#3498db", hover_color="#2980b9")
        self.load_similar_btn.pack(side="left", padx=(10, 0))
        
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=30)
        header_frame.pack(fill="x", padx=40, pady=0)
        ctk.CTkLabel(header_frame, text="Branch Name", width=200, anchor="w", font=("Segoe UI", 12, "bold")).pack(side="left", padx=10)
        ctk.CTkLabel(header_frame, text="Pharma (Days)", width=120, font=("Segoe UI", 12, "bold")).pack(side="left", padx=15)
        ctk.CTkLabel(header_frame, text="Non-Pharma (Days)", width=120, font=("Segoe UI", 12, "bold")).pack(side="left", padx=10)

        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=(0, 5))

        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent", height=50)
        self.progress_frame.pack(fill="x", padx=20, pady=0)
        self.progress_frame.pack_propagate(False) 

        self.progress_label = ctk.CTkLabel(self.progress_frame, text="", font=("Segoe UI", 12, "bold"), text_color="#3498db")
        self.calc_progress = ctk.CTkProgressBar(self.progress_frame, width=400, fg_color="#ecf0f1", progress_color="#2ecc71")
        self.calc_progress.set(0)

        self.process_btn = ctk.CTkButton(self, text="Calculate & Export Results", 
                                         height=50, font=("Segoe UI", 16, "bold"),
                                         command=self.process_data, state="disabled")
        self.process_btn.pack(pady=(5, 10), fill="x", padx=20)

        self.history_btn = ctk.CTkButton(self, text="Export Orders History (Database)", 
                                         height=40, font=("Segoe UI", 14, "bold"),
                                         fg_color="#27ae60", hover_color="#2ecc71",
                                         command=self.export_history)
        self.history_btn.pack(pady=(0, 20), fill="x", padx=20)

    def toggle_theme(self):
        if self.theme_switch.get() == 1:
            ctk.set_appearance_mode("Light")
            self.theme_switch.configure(text="Dark Mode")
        else:
            ctk.set_appearance_mode("Dark")
            self.theme_switch.configure(text="Light Mode")

    def update_progress(self, val, text):
        if not self.calc_progress.winfo_ismapped():
            self.progress_label.pack(side="top")
            self.calc_progress.pack(side="top", pady=5)
            
        self.calc_progress.set(val)
        self.progress_label.configure(text=text)
        self.update_idletasks()

    def hide_progress(self):
        self.calc_progress.pack_forget()
        self.progress_label.pack_forget()

    def download_main_template(self):
        cols = ['Plnt', 'Plant', 'Material', 'Material Group', 'Material Description', 'Branch Stock', 'Pending to Branch', 'Display', 'Dc Stock', 'Pending from DC', 'Consumption90D', 'Ref.Cons 30D', 'Ref.Cons First 5D', 'Sales Price', 'Max Receipt', 'Main Category', 'SubCategory 1', 'Storage Condition', 'Manufacturer Name']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], initialfile="Main_Data_Template.xlsx", title="Save Main Template")
        if path: df.to_excel(path, index=False)

    def download_targets_template(self):
        cols = ['Plnt', 'Plant', 'Main Category', 'Target Days']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], initialfile="Targets_Template.xlsx", title="Save Targets Template")
        if path: df.to_excel(path, index=False)

    def download_rank_template(self):
        cols = ['Plnt', 'Plant', 'Rank']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], initialfile="Rank_Template.xlsx", title="Save Rank Template")
        if path: df.to_excel(path, index=False)

    def download_blocked_template(self):
        cols = ['Plnt', 'Plant', 'Material', 'Material Description']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], initialfile="Blocked_Template.xlsx", title="Save Block Template")
        if path: df.to_excel(path, index=False)

    def standardize_columns(self, df):
        df.columns = df.columns.astype(str).str.strip()
        rename_map = {
            'Branch Stock': 'Stock',
            'Pending to Branch': 'Pending preparation to branch',
            'Pending from DC': 'Pending preparation from DC',
            'Consumption90D': 'Consumption last 90 days',
            'Ref.Cons 30D': 'Consumption last 30 days',
            'Ref.Cons First 5D': 'Consumption first 5 days of last month',
            'Min PR Date': 'first receiving date',   
            'MAX PR Date': 'last receiving date'     
        }
        df.rename(columns=rename_map, inplace=True)
        return df

    def upload_and_load_branches(self):
        filetypes = (('Excel files', '*.xlsx *.xls'), ('All files', '*.*'))
        path = fd.askopenfilename(title='Open dataset', filetypes=filetypes)
        
        if path:
            try:
                self.file_path = path
                df = pd.read_excel(path)
                df = self.standardize_columns(df)
                
                plant_col = 'Plant' if 'Plant' in df.columns else 'Plnt'
                if plant_col not in df.columns:
                    messagebox.showerror("Format Error", f"Column '{plant_col}' not found in the dataset.")
                    return

                branches = df[plant_col].dropna().unique()
                self.file_label.configure(text=f"Loaded Dataset: {os.path.basename(path)}", text_color="#2ecc71")
                
                for widget in self.scroll_frame.winfo_children(): widget.destroy()
                self.branch_inputs = {}

                for branch in sorted(branches):
                    row_frame = ctk.CTkFrame(self.scroll_frame)
                    row_frame.pack(fill="x", pady=5, padx=5)
                    ctk.CTkLabel(row_frame, text=str(branch), width=200, anchor="w", font=("Segoe UI", 14)).pack(side="left", padx=10)
                    
                    p_entry = ctk.CTkEntry(row_frame, placeholder_text="Pharma", width=120)
                    p_entry.pack(side="left", padx=15)
                    
                    np_entry = ctk.CTkEntry(row_frame, placeholder_text="Non-Pharma", width=120)
                    np_entry.pack(side="left", padx=10)
                    
                    self.branch_inputs[branch] = {'pharma': p_entry, 'non_pharma': np_entry}

                self.process_btn.configure(state="normal")
                messagebox.showinfo("Success", "Branches extracted successfully! Upload target Excel or enter manually.")
            except Exception as e:
                messagebox.showerror("File Error", f"Failed to load the file:\n{e}")

    def load_targets_from_excel(self):
        if not self.branch_inputs:
            messagebox.showwarning("Warning", "Please upload the main dataset first.")
            return
        filetypes = (('Excel files', '*.xlsx *.xls'), ('All files', '*.*'))
        path = fd.askopenfilename(title='Open Targets Excel', filetypes=filetypes)
        if path:
            try:
                df_targets = pd.read_excel(path)
                target_col = next((col for col in df_targets.columns if 'target' in str(col).lower() or 'days' in str(col).lower()), None)
                cat_col = next((col for col in df_targets.columns if 'category' in str(col).lower()), None)
                
                if not cat_col or not target_col:
                    messagebox.showerror("Format Error", "Targets Excel must contain 'Main Category' and 'Target Days'.")
                    return
                for b, inputs in self.branch_inputs.items():
                    inputs['pharma'].delete(0, 'end')
                    inputs['non_pharma'].delete(0, 'end')
                applied_count = 0
                for _, row in df_targets.iterrows():
                    possible_plants = []
                    if 'Plnt' in df_targets.columns: possible_plants.append(str(row['Plnt']).strip())
                    if 'Plant' in df_targets.columns: possible_plants.append(str(row['Plant']).strip())
                    cat = str(row[cat_col]).strip().lower()
                    try: target_val = int(row[target_col])
                    except: continue
                    matched_branch = next((p for p in possible_plants if p in self.branch_inputs), None)
                    if matched_branch:
                        if 'non-pharma' in cat or 'non_pharma' in cat or cat == 'non pharma':
                            self.branch_inputs[matched_branch]['non_pharma'].delete(0, 'end')
                            self.branch_inputs[matched_branch]['non_pharma'].insert(0, str(target_val))
                            applied_count += 1
                        elif 'pharma' in cat:
                            self.branch_inputs[matched_branch]['pharma'].delete(0, 'end')
                            self.branch_inputs[matched_branch]['pharma'].insert(0, str(target_val))
                            applied_count += 1
                messagebox.showinfo("Success", f"Applied {applied_count} target configurations.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load targets:\n{e}")

    def load_rank_from_excel(self):
        filetypes = (('Excel files', '*.xlsx *.xls'), ('All files', '*.*'))
        path = fd.askopenfilename(title='Open Rank Excel', filetypes=filetypes)
        if path:
            try:
                df_rank = pd.read_excel(path)
                plant_cols = [c for c in df_rank.columns if c.strip().lower() in ['plnt', 'plant', 'branch']]
                
                if not plant_cols:
                    messagebox.showerror("Format Error", "Rank Excel must contain 'Plant' or 'Plnt' column.")
                    return
                
                rank_col = next((c for c in df_rank.columns if c.strip().lower() == 'rank'), None)
                
                self.rank_data.clear() 
                applied = 0
                current_rank = 1 
                
                for _, row in df_rank.iterrows():
                    r_val = 999
                    if rank_col:
                        try: r_val = int(row[rank_col])
                        except: r_val = 999
                    else:
                        r_val = current_rank
                        current_rank += 1
                        
                    row_added = False
                    for p_col in plant_cols:
                        b_val = str(row[p_col]).strip()
                        if b_val and b_val != 'nan':
                            self.rank_data[b_val] = r_val
                            row_added = True
                            
                    if row_added:
                        applied += 1
                        
                messagebox.showinfo("Success", f"Loaded ranks for {applied} branches successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load Rank Excel:\n{e}")

    def load_blocked_from_excel(self):
        filetypes = (('Excel files', '*.xlsx *.xls'), ('All files', '*.*'))
        path = fd.askopenfilename(title='Open Blocked Items Excel', filetypes=filetypes)
        if path:
            try:
                df_b = pd.read_excel(path)
                plant_cols = [c for c in df_b.columns if c.strip().lower() in ['plnt', 'plant', 'branch']]
                m_col = next((c for c in df_b.columns if c.strip().lower() in ['material', 'item code']), None)
                
                if not plant_cols:
                    messagebox.showerror("Format Error", "Blocked Excel must contain 'Plant/Plnt' column.")
                    return
                
                self.blocked_items.clear()
                self.blocked_branches.clear()
                
                count_items = 0
                for _, row in df_b.iterrows():
                    row_counted = False
                    for p_col in plant_cols:
                        b = str(row[p_col]).strip()
                        if b and b != 'nan':
                            if m_col:
                                m = str(row[m_col]).replace('.0', '').strip()
                                if m and m != 'nan' and m != '':
                                    self.blocked_items.add((b, m))
                                    if not row_counted:
                                        count_items += 1
                                        row_counted = True
                                else:
                                    self.blocked_branches.add(b)
                            else:
                                self.blocked_branches.add(b)
                                
                messagebox.showinfo("Success", f"Loaded {count_items} blocked items and {len(self.blocked_branches)} blocked branches successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load Blocked Excel:\n{e}")

    def process_data(self):
        try:
            self.process_btn.configure(state="disabled")
            
            self.update_progress(0.1, "Loading main dataset...")
            df = pd.read_excel(self.file_path)
            df = self.standardize_columns(df)
            plant_col = 'Plant' if 'Plant' in df.columns else 'Plnt'
            
            self.update_progress(0.2, "Filtering blocked items & branches...")
            df_blocked_output = pd.DataFrame(columns=df.columns) 
            
            if self.blocked_items or self.blocked_branches:
                df['temp_mat'] = df['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                mask = pd.Series(False, index=df.index)
                
                for p_col in ['Plnt', 'Plant']:
                    if p_col in df.columns:
                        df['temp_p'] = df[p_col].astype(str).str.strip()
                        if self.blocked_items:
                            mask = mask | df.set_index(['temp_p', 'temp_mat']).index.isin(self.blocked_items)
                        if self.blocked_branches:
                            mask = mask | df['temp_p'].isin(self.blocked_branches)
                        df.drop(columns=['temp_p'], inplace=True)
                
                df_blocked_output = df[mask].drop(columns=['temp_mat']).copy()
                df = df[~mask].drop(columns=['temp_mat']).copy()

            if df.empty:
                messagebox.showinfo("Result Empty", "No items left to process after filtering blocked items.")
                self.hide_progress()
                self.process_btn.configure(state="normal")
                return

            self.update_progress(0.25, "Processing Similar Items...")
            if 'temp_mat' not in df.columns:
                df['temp_mat'] = df['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                
            df['Main_Group_Mat'] = df['temp_mat']
            df['Item_Role'] = 'Main' 

            if hasattr(self, 'similar_df') and self.similar_df is not None:
                sim_df = self.similar_df.copy()
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

            self.update_progress(0.3, "Applying targets & configuring rules...")
            if 'Material Description' not in df.columns: df['Material Description'] = "Unknown"
            if 'Display' not in df.columns: df['Display'] = 0

            targets_map = {}
            for b, inputs in self.branch_inputs.items():
                try:
                    p_val = inputs['pharma'].get().strip()
                    np_val = inputs['non_pharma'].get().strip()
                    targets_map[b] = {'pharma': float(p_val) if p_val else 0.0, 'non_pharma': float(np_val) if np_val else 0.0}
                except ValueError:
                    targets_map[b] = {'pharma': 0.0, 'non_pharma': 0.0}

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

            self.update_progress(0.5, "Running base distribution engine (Push & Pull)...")
            
            def process_material_group(group):
                branch_group = group.drop_duplicates(subset=[plant_col]).copy()
                
                def evaluate_requirements(current_targets, use_display=True):
                    req = (branch_group['daily_consumption'] * current_targets) - (branch_group['Stock'] + branch_group['Pending preparation to branch'])
                    req_updated = req.copy()
                    req_updated[req_updated < 0] = 0
                    
                    if use_display:
                        curr_tot = branch_group['Stock'] + req_updated + branch_group['Pending preparation to branch']
                        mask_disp = (branch_group['Display'] > 0) & (curr_tot < branch_group['Display'])
                        req_updated[mask_disp] = branch_group['Display'][mask_disp] - branch_group['Stock'][mask_disp] - branch_group['Pending preparation to branch'][mask_disp]
                    
                    req_updated[(branch_group['daily_consumption'] == 0) & (branch_group['Display'] == 0)] = 0
                    return req_updated, np.ceil(req_updated)

                initial_targets = branch_group['target stock days chosen'].copy()
                raw_req, rounded_req = evaluate_requirements(initial_targets, use_display=True)
                _, absolute_full_req = evaluate_requirements(initial_targets, use_display=True)
                
                branch_group['original_raw_required'] = raw_req
                branch_group['original_required'] = rounded_req
                
                group['original_raw_required'] = 0.0
                group['original_required'] = 0
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
                group['rounded up required'] = 0
                group['Final Allocated Target Days'] = group['target stock days chosen']
                
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
                temp_group['Rank'] = temp_group[rank_lookup_col].map(lambda x: self.rank_data.get(str(x).strip(), 999))
                
                # الدورة الأولى: سد العجز الفعلي في المطلوب المطلق
                unfulfilled = absolute_full_req - best_rounded
                unfulfilled[unfulfilled < 0] = 0

                if remainder > 0 and unfulfilled.sum() > 0:
                    temp_group['Unfulfilled'] = unfulfilled
                    sorted_idx = temp_group[temp_group['Unfulfilled'] > 0].sort_values(by=['daily_consumption', 'Rank'], ascending=[False, True]).index
                    for current_idx in sorted_idx:
                        if remainder <= 0: break
                        needed = temp_group.loc[current_idx, 'Unfulfilled']
                        taken = min(needed, remainder)
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
                group['rounded up required'] = 0

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
                    group.loc[group_mask, 'Final Allocated Target Days'] = targets_dict.get(b_name, 0)

                    if total_rounded_need <= 0: continue

                    remaining_to_fulfill = total_rounded_need
                    for m_code in sorted_mats:
                        if remaining_to_fulfill <= 0: break
                        m_avail = dc_stock_dict.get(m_code, 0)
                        if m_avail <= 0: continue

                        take = min(remaining_to_fulfill, m_avail)
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
            
            self.update_progress(0.8, "Finalizing calculations & coverage...")
            
            df['DC Capped Required'] = df['rounded up required'] 
            df['rounded up required'] = df['original_required'].apply(lambda x: int(max(0, np.ceil(x))) if pd.notnull(x) else 0)
            df['required'] = df['original_raw_required']
            
            df['Final Required'] = df['DC Capped Required'].apply(lambda x: int(max(0, np.ceil(x))) if pd.notnull(x) else 0)
            
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
            
            if df_final.empty:
                messagebox.showinfo("Result Empty", "No data available to export.")
                self.hide_progress()
                self.process_btn.configure(state="normal")
                return

            self.update_progress(0.9, "Preparing export sheets...")
            
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
                    
            main_output = df_final[output_cols]

            df_action_only = df_final[df_final['Final Required'] > 0].copy()
            
            # Branch Summary relies only on items that actually got allocated
            summary_data = df_action_only.groupby(plant_col).agg(
                Total_Items_Prepared=('Material', 'count'),
                Sum_of_Quantities=('Final Required', 'sum')
            ).reset_index() if plant_col in df_action_only.columns else pd.DataFrame()
            
            # --- FIX 2: Use df_final instead of df_action_only so undistributed items appear ---
            dc_summary = df_final.groupby('Material').agg(
                Material_Description=('Material Description', 'first'),
                Initial_DC_Stock=('Dc Stock', 'first'),
                Total_Allocated=('Final Required', 'sum')
            ).reset_index() if 'Material' in df_final.columns else pd.DataFrame()
            
            if not dc_summary.empty:
                dc_summary['Remaining_DC_Stock'] = dc_summary['Initial_DC_Stock'] - dc_summary['Total_Allocated']
            
            df_adjusted_base = df_final.copy()
            df_adjusted_base['Original Required'] = df_adjusted_base['rounded up required'].astype(int)
            df_adjusted_base['Adjusted Required'] = df_adjusted_base['Final Required'].astype(int)
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
                conn = sqlite3.connect(self.db_name)
                db_data.to_sql('orders_history', conn, if_exists='append', index=False)
                conn.close()
            except Exception as e:
                messagebox.showwarning("Database Warning", f"Could not save history to database: {e}")

            self.update_progress(0.9, "Choosing save location...")
            save_path = fd.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], title="Save Output As", initialfile=f"Replenishment_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx")
            
            if save_path:
                total_sheets = 3
                if not adjusted_df.empty: total_sheets += 1
                if not df_blocked_output.empty: total_sheets += 1
                if hasattr(self, 'similar_df') and self.similar_df is not None: total_sheets += 1
                
                current_sheet = 0
                
                def update_save_progress(sheet_name):
                    nonlocal current_sheet
                    current_sheet += 1
                    progress_value = 0.9 + (0.1 * (current_sheet / total_sheets))
                    self.update_progress(progress_value, f"Saving Sheet: {sheet_name} ({current_sheet}/{total_sheets})...")

                with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
                    update_save_progress('Final Requirement')
                    main_output.to_excel(writer, sheet_name='Final Requirement', index=False)
                    
                    update_save_progress('Branch Summary')
                    summary_data.to_excel(writer, sheet_name='Branch Summary', index=False)
                    
                    update_save_progress('DC Stock Summary')
                    dc_summary.to_excel(writer, sheet_name='DC Stock Summary', index=False)
                    
                    if not adjusted_df.empty:
                        update_save_progress('Adjusted Items')
                        adjusted_df.to_excel(writer, sheet_name='Adjusted Items', index=False)
                    
                    if not df_blocked_output.empty:
                        update_save_progress('Blocked Items')
                        df_blocked_output.to_excel(writer, sheet_name='Blocked Items', index=False)

                    if hasattr(self, 'similar_df') and self.similar_df is not None:
                        self.update_progress(0.98, "Preparing Similars Sheet data...")
                        m_main_col = next((c for c in self.similar_df.columns if 'main' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), self.similar_df.columns[0])
                        m_sim_col = next((c for c in self.similar_df.columns if 'similar' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), self.similar_df.columns[2])
                        main_codes = self.similar_df[m_main_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique()
                        sim_codes = self.similar_df[m_sim_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique()
                        all_sim_main_codes = set(main_codes).union(set(sim_codes))
                        
                        df_all_for_similars = df.copy()
                        for col in output_cols:
                            if col not in df_all_for_similars.columns: df_all_for_similars[col] = ""
                        df_all_for_similars = df_all_for_similars[output_cols]
                        
                        clean_materials = df_all_for_similars['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                        df_sim_detailed = df_all_for_similars[clean_materials.isin(all_sim_main_codes)].copy()
                        df_sim_detailed = df_sim_detailed.sort_values(by=['Material'])
                        
                        update_save_progress('Similars')
                        df_sim_detailed.to_excel(writer, sheet_name='Similars', index=False)
                
                self.update_progress(1.0, "Export Completed Successfully!")
                messagebox.showinfo("Export Successful", f"Calculations updated successfully! Results exported to:\n{save_path}")

        except Exception as e:
            messagebox.showerror("Processing Error", f"An error occurred during calculation:\n{str(e)}")
        finally:
            self.hide_progress()
            self.process_btn.configure(state="normal")

    def export_history(self):
        if not os.path.exists(self.db_name):
            messagebox.showinfo("History Empty", "No history found.")
            return
        try:
            conn = sqlite3.connect(self.db_name)
            history_df = pd.read_sql("SELECT * FROM orders_history", conn)
            conn.close()
            if history_df.empty:
                messagebox.showinfo("History Empty", "The history database is currently empty.")
                return
            save_path = fd.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], title="Save History As", initialfile="Lotus_Full_History.xlsx")
            if save_path:
                history_df.to_excel(save_path, index=False)
                messagebox.showinfo("Success", f"Full history exported successfully to:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to export history:\n{e}")

if __name__ == "__main__":
    app = LotusApp()
    app.mainloop()