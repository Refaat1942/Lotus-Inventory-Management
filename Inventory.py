import customtkinter as ctk
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as messagebox
import pandas as pd
import numpy as np
from PIL import Image
import os
import sys
import sqlite3
import datetime
import hashlib
import uuid
import math
import socket
import platform
import base64
import subprocess

# ==========================================
# نظام الحماية والتفعيل (Offline License)
# ==========================================
SECRET_SALT = "LOTUS_PHARMA_2026_SUPER_SECRET_KEY"

def get_machine_id():
    try:
        # قراءة السيريال الخاص باللوحة الأم أو الجهاز
        output = subprocess.check_output('wmic baseboard get serialnumber', shell=True).decode()
        hw_id = output.replace('SerialNumber', '').strip()
        
        # إذا لم يكن هناك سيريال للوحة الأم، نقرأ الـ UUID الخاص بنظام الويندوز
        if not hw_id or hw_id.lower() in ["none", "default string", "to be filled by o.e.m."]:
            output = subprocess.check_output('wmic csproduct get uuid', shell=True).decode()
            hw_id = output.replace('UUID', '').strip()
            
        if hw_id:
            return hashlib.md5(hw_id.encode()).hexdigest()[:10].upper()
            
    except Exception:
        pass
        
    # حل أخير في حالة فشل الأوامر السابقة
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
        
        self.entry = ctk.CTkEntry(self, width=400, height=45, justify="center", font=("Segoe UI", 18, "bold"), placeholder_text="أدخل كود التفعيل هنا (يمكنك اللصق بالماوس)")
        self.entry.pack(pady=15)
        self._enable_copy_paste(self.entry) 
        
        btn = ctk.CTkButton(self, text="تفعيل النظام", font=("Segoe UI", 16, "bold"), height=40, command=self.submit)
        btn.pack(pady=10)
        
    def _enable_copy_paste(self, widget):
        menu = tk.Menu(self, tearoff=0, bg="#2c3e50", fg="white", font=("Segoe UI", 11))

        def paste_action():
            try:
                text = widget.clipboard_get()
                widget.insert("insert", text)
            except:
                pass

        def copy_action():
            try:
                text = widget.selection_get()
            except:
                text = widget.get()
            if text:
                widget.clipboard_clear()
                widget.clipboard_append(text)

        def cut_action():
            copy_action()
            widget.delete(0, "end")

        menu.add_command(label="Copy (نسخ)", command=copy_action)
        menu.add_command(label="Paste (لصق)", command=paste_action)
        menu.add_command(label="Cut (قص)", command=cut_action)

        def show_menu(event):
            widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)

        widget.bind("<Button-3>", show_menu)
        widget.bind("<Control-v>", lambda e: paste_action() or "break")
        widget.bind("<Control-c>", lambda e: copy_action() or "break")
        widget.bind("<Control-x>", lambda e: cut_action() or "break")

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
    
    msg = f"هذا الجهاز غير مصرح له باستخدام النظام.\n\nتم إنشاء ملف مشفر باسم ({info_file}) بجوار البرنامج.\nيحتوي على بيانات جهازك (رقم التعريف، اسم الجهاز، والنظام).\n\nبرجاء إرسال هذا الملف للإدارة للحصول على كود التفعيل."
    
    dialog = ActivationDialog(root, msg)
    root.wait_window(dialog)
    
    user_key = dialog.user_key

    if user_key and user_key.strip().upper() == expected_key:
        with open(license_file, "w") as f:
            f.write(user_key.strip().upper())
        messagebox.showinfo("نجاح", "تم تفعيل النظام بنجاح! شكراً لك.")
        root.destroy()
        return True
    else:
        messagebox.showerror("خطأ", "كود التفعيل غير صحيح أو تم الإلغاء. سيتم إغلاق النظام.")
        sys.exit()

check_license()
# ==========================================

# --- App Version ---
APP_VERSION = "v9.7.8 (Targets Update & Progress Export)"

# --- Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class LotusInventoryApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.withdraw()  
        self.file_path = None
        self.db_name = "lotus_inventory_history.db" 
        self.targets_df = None
        self.purchase_targets_df = None
        self.rank_data = {} 
        
        self.blocked_items = set()
        self.blocked_branches = set() # للفرع بالكامل
        self.similar_df = None # لملف الـ Similar 
        self.blocked_os_items = set() 
        self.blocked_os_branches = set() 
        self.avoid_zero_df = None 
        self.zero_overstock_var = tk.BooleanVar(value=True)
        self.high_sto_var = tk.StringVar(value="180") 

        self.splash = ctk.CTkToplevel(self)
        self.splash.overrideredirect(True) 
        
        width, height = 550, 450 
        screen_width = self.splash.winfo_screenwidth()
        screen_height = self.splash.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.splash.geometry(f'{width}x{height}+{x}+{y}')
        
        self.splash.configure(fg_color="#FFFFFF")
        self.splash.attributes('-topmost', True)

        try:
            logo_path = resource_path("logo.png")
            logo_img = ctk.CTkImage(light_image=Image.open(logo_path), dark_image=Image.open(logo_path), size=(160, 160))
            ctk.CTkLabel(self.splash, image=logo_img, text="").pack(pady=(50, 10))
        except:
            ctk.CTkLabel(self.splash, text="LOTUS", font=("Segoe UI", 65, "bold"), text_color="#c0392b").pack(pady=(60, 10))

        ctk.CTkLabel(self.splash, text=f"Lotus Inventory Management System", font=("Segoe UI", 22, "bold"), text_color="#2c3e50").pack(pady=5)
        
        self.progress_bar = ctk.CTkProgressBar(self.splash, width=300, height=8, fg_color="#ecf0f1", progress_color="#e74c3c")
        self.progress_bar.pack(pady=25)
        self.progress_bar.set(0)

        ctk.CTkLabel(self.splash, text="Copyright © Lotus Pharmacies 2026", font=("Segoe UI", 13, "bold"), text_color="#2c3e50").pack(side="bottom", pady=20)

        self.animation_step = 0
        self.animate_splash()

    def animate_splash(self):
        self.animation_step += 0.01
        self.progress_bar.set(self.animation_step)
        if self.animation_step < 1.0:
            self.after(50, self.animate_splash) 
        else:
            self.start_main_app()

    def start_main_app(self):
        self.splash.destroy()
        self.title(f"Lotus Inventory Management System - {APP_VERSION}")
        self.geometry("1150x900") 
        try: self.iconbitmap(resource_path("Inventory.ico"))
        except: pass
        self.deiconify()
        self.setup_ui()

    def _enable_copy_paste(self, widget):
        menu = tk.Menu(self, tearoff=0, bg="#2c3e50", fg="white", font=("Segoe UI", 11))

        def paste_action():
            try:
                text = widget.clipboard_get()
                widget.insert("insert", text)
            except:
                pass

        def copy_action():
            try:
                text = widget.selection_get()
            except:
                text = widget.get()
            if text:
                widget.clipboard_clear()
                widget.clipboard_append(text)

        def cut_action():
            copy_action()
            widget.delete(0, "end")

        menu.add_command(label="Copy (نسخ)", command=copy_action)
        menu.add_command(label="Paste (لصق)", command=paste_action)
        menu.add_command(label="Cut (قص)", command=cut_action)

        def show_menu(event):
            widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)

        widget.bind("<Button-3>", show_menu)
        widget.bind("<Control-v>", lambda e: paste_action() or "break")
        widget.bind("<Control-c>", lambda e: copy_action() or "break")
        widget.bind("<Control-x>", lambda e: cut_action() or "break")

    def setup_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(header, text=f"Lotus Inventory Management System", font=("Segoe UI", 28, "bold")).pack(side="left")
        self.theme_switch = ctk.CTkSwitch(header, text="Light Mode", command=self.toggle_theme, font=("Segoe UI", 12, "bold"))
        self.theme_switch.pack(side="right", pady=10)

        templates_frame = ctk.CTkFrame(self, fg_color="transparent")
        templates_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(templates_frame, text="Templates:", font=("Segoe UI", 14, "bold")).pack(side="left", padx=(0, 5))
        
        btn_width = 80 
        ctk.CTkButton(templates_frame, text="Main Data", width=btn_width, height=28, fg_color="#34495e", command=self.download_main_template).pack(side="left", padx=2)
        ctk.CTkButton(templates_frame, text="Targets", width=btn_width, height=28, fg_color="#34495e", command=self.download_targets_template).pack(side="left", padx=2)
        ctk.CTkButton(templates_frame, text="Purchase Trg", width=btn_width, height=28, fg_color="#34495e", command=self.download_purchase_targets_template).pack(side="left", padx=2)
        ctk.CTkButton(templates_frame, text="Rank", width=btn_width, height=28, fg_color="#34495e", command=self.download_rank_template).pack(side="left", padx=2)
        ctk.CTkButton(templates_frame, text="Blocked Items", width=btn_width, height=28, fg_color="#34495e", command=self.download_blocked_template).pack(side="left", padx=2)
        ctk.CTkButton(templates_frame, text="Blocked OS", width=btn_width, height=28, fg_color="#34495e", command=self.download_blocked_os_template).pack(side="left", padx=2)
        ctk.CTkButton(templates_frame, text="Avoid Zero", width=btn_width, height=28, fg_color="#34495e", command=self.download_avoid_zero_template).pack(side="left", padx=2)
        ctk.CTkButton(templates_frame, text="Similar", width=btn_width, height=28, fg_color="#34495e", command=self.download_similar_template).pack(side="left", padx=2)

        upload_frame = ctk.CTkFrame(self)
        upload_frame.pack(fill="x", padx=20, pady=15)
        self.file_label = ctk.CTkLabel(upload_frame, text="Please upload the Main ERP Raw Sheet.", font=("Segoe UI", 14))
        self.file_label.pack(side="left", padx=20, pady=15)
        ctk.CTkButton(upload_frame, text="1. Upload ERP Sheet", font=("Segoe UI", 14, "bold"), command=self.upload_main_file).pack(side="right", padx=20, pady=15)

        tools_frame_1 = ctk.CTkFrame(self, fg_color="transparent")
        tools_frame_1.pack(fill="x", padx=30, pady=(5, 5))
        
        up_btn_width = 125
        self.load_targets_btn = ctk.CTkButton(tools_frame_1, text="2. Upload Targets", command=self.load_targets_from_excel, font=("Segoe UI", 11, "bold"), width=up_btn_width, fg_color="#8e44ad", hover_color="#9b59b6")
        self.load_targets_btn.pack(side="left", padx=(0, 10))
        
        self.load_purchase_targets_btn = ctk.CTkButton(tools_frame_1, text="2.b Purchase Trg", command=self.load_purchase_targets_from_excel, font=("Segoe UI", 11, "bold"), width=up_btn_width, fg_color="#8e44ad", hover_color="#9b59b6")
        self.load_purchase_targets_btn.pack(side="left", padx=(0, 10))

        self.load_rank_btn = ctk.CTkButton(tools_frame_1, text="3. Upload Rank", command=self.load_rank_from_excel, font=("Segoe UI", 11, "bold"), width=up_btn_width, fg_color="#e67e22", hover_color="#d35400")
        self.load_rank_btn.pack(side="left", padx=(0, 10))
        
        self.load_avoid_zero_btn = ctk.CTkButton(tools_frame_1, text="4. Avoid Zero", command=self.load_avoid_zero_from_excel, font=("Segoe UI", 11, "bold"), width=up_btn_width, fg_color="#f39c12", hover_color="#d68910")
        self.load_avoid_zero_btn.pack(side="left")

        tools_frame_2 = ctk.CTkFrame(self, fg_color="transparent")
        tools_frame_2.pack(fill="x", padx=30, pady=(5, 15))
        self.load_blocked_btn = ctk.CTkButton(tools_frame_2, text="5. Blocked Items", command=self.load_blocked_from_excel, font=("Segoe UI", 11, "bold"), width=up_btn_width, fg_color="#c0392b", hover_color="#e74c3c")
        self.load_blocked_btn.pack(side="left", padx=(0, 10))
        self.load_blocked_os_btn = ctk.CTkButton(tools_frame_2, text="6. Blocked OS", command=self.load_blocked_os_from_excel, font=("Segoe UI", 11, "bold"), width=up_btn_width, fg_color="#c0392b", hover_color="#e74c3c")
        self.load_similar_btn = ctk.CTkButton(tools_frame_2, text="7. Upload Similar", command=self.load_similar_from_excel, font=("Segoe UI", 11, "bold"), width=up_btn_width, fg_color="#3498db", hover_color="#2980b9")
        self.load_similar_btn.pack(side="left", padx=(0, 10))
        self.load_blocked_os_btn.pack(side="left", padx=(0, 10))
        
        # --- NEW BUTTON: Clear Data ---
        self.clear_data_btn = ctk.CTkButton(tools_frame_2, text="Clear Uploaded Data", command=self.clear_all_data, font=("Segoe UI", 11, "bold"), width=up_btn_width, fg_color="#7f8c8d", hover_color="#95a5a6")
        self.clear_data_btn.pack(side="left", padx=(30, 0))
        
        config_frame = ctk.CTkFrame(self, fg_color="transparent")
        config_frame.pack(fill="x", padx=20, pady=5)

        self.zero_overstock_cb = ctk.CTkCheckBox(
            config_frame, 
            text="Include Pos/Neg Conditions (14, 15) for Overstock", 
            variable=self.zero_overstock_var, 
            onvalue=True, 
            offvalue=False,
            font=("Segoe UI", 13, "bold"), 
            fg_color="#c0392b", 
            hover_color="#e74c3c"
        )
        self.zero_overstock_cb.pack(side="left", padx=10)

        ctk.CTkLabel(config_frame, text=" |   High STO Threshold (Days):", font=("Segoe UI", 13, "bold")).pack(side="left", padx=(10, 5))
        self.sto_dropdown = ctk.CTkOptionMenu(
            config_frame, 
            variable=self.high_sto_var,
            values=["90", "120", "180", "Other..."],
            command=self.on_sto_select,
            width=90,
            fg_color="#2980b9", button_color="#27ae60", button_hover_color="#2ecc71"
        )
        self.sto_dropdown.pack(side="left", padx=5)
        
        self.custom_sto_entry = ctk.CTkEntry(config_frame, placeholder_text="Enter days", width=90)
        self._enable_copy_paste(self.custom_sto_entry) 

        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent", height=50)
        self.progress_frame.pack(fill="x", padx=20, pady=5)
        self.progress_frame.pack_propagate(False) 
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="", font=("Segoe UI", 12, "bold"), text_color="#e74c3c")
        self.calc_progress = ctk.CTkProgressBar(self.progress_frame, width=400, fg_color="#ecf0f1", progress_color="#c0392b")
        self.calc_progress.set(0)

        self.process_btn = ctk.CTkButton(self, text="7. Run Smart Inventory Engine", 
                                         height=60, font=("Segoe UI", 18, "bold"),
                                         fg_color="#27ae60", hover_color="#2ecc71",
                                         command=self.process_data, state="disabled")
        self.process_btn.pack(pady=(10, 10), fill="x", padx=20)

        self.history_btn = ctk.CTkButton(self, text="Export Pullback History (Database)", 
                                         height=40, font=("Segoe UI", 14, "bold"),
                                         fg_color="#34495e", hover_color="#2c3e50",
                                         command=self.export_history)
        self.history_btn.pack(pady=(0, 20), fill="x", padx=20)

    def on_sto_select(self, choice):
        if choice == "Other...":
            self.custom_sto_entry.pack(side="left", padx=5)
        else:
            self.custom_sto_entry.pack_forget()

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

    # --- NEW FUNCTION: Clear all variables and UI states ---
    def clear_all_data(self):
        self.file_path = None
        self.targets_df = None
        self.purchase_targets_df = None
        self.rank_data.clear()
        self.blocked_items.clear()
        self.blocked_branches.clear()
        self.similar_df = None
        if hasattr(self, 'load_similar_btn'): self.load_similar_btn.configure(text="Upload Similar", fg_color="#3498db")
        self.blocked_os_items.clear()
        self.blocked_os_branches.clear()
        self.avoid_zero_df = None

        # Reset Labels & Buttons
        self.file_label.configure(text="Please upload the Main ERP Raw Sheet.", text_color=("black", "white"))
        self.load_targets_btn.configure(text="2. Upload Targets", fg_color="#8e44ad")
        self.load_purchase_targets_btn.configure(text="2.b Purchase Trg", fg_color="#8e44ad")
        self.load_rank_btn.configure(text="3. Upload Rank", fg_color="#e67e22")
        self.load_avoid_zero_btn.configure(text="4. Avoid Zero", fg_color="#f39c12")
        self.load_blocked_btn.configure(text="5. Blocked Items", fg_color="#c0392b")
        self.load_blocked_os_btn.configure(text="6. Blocked OS", fg_color="#c0392b")
        
        self.process_btn.configure(state="disabled")
        self.hide_progress()
        messagebox.showinfo("Data Cleared", "All uploaded sheets and data have been cleared successfully!")

    def download_main_template(self):
        cols = [
            'Plnt', 'Plant', 'Material', 'Material Group', 'Material Description', 
            'Branch Stock', 'Pending to Branch', 'Open PO Quantity', 'Display', 
            'Dc Stock', 'Pending from DC', 'Consumption 180Day', 'Consumption90D', 
            'Ref.Cons 30D', 'Ref.Cons First 5D', 'Sales Price', 'Max Receipt', 
            'Main Category', 'SubCategory 1', 'Storage Condition', 'Manufacturer Name', 
            'Created On', 'Days Since Last STO', 'Days from last sell'
        ]
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", initialfile="Main_Data_Template.xlsx", title="Save Main Template")
        if path: df.to_excel(path, index=False)

    def download_targets_template(self):
        cols = ['Plnt', 'Plant', 'Main Category', 'Target Days', 'Overstock Target Days', 'Target Distribution Target Days']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", initialfile="Target_Days_Template.xlsx", title="Save Targets Template")
        if path: df.to_excel(path, index=False)
        
    def download_purchase_targets_template(self):
        cols = ['Plnt', 'Plant', 'Main Category', 'Target Days']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", initialfile="Purchase_Target_Days_Template.xlsx", title="Save Purchase Targets Template")
        if path: df.to_excel(path, index=False)

    def download_rank_template(self):
        cols = ['Plnt', 'Plant', 'Rank']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", initialfile="Rank_Template.xlsx", title="Save Rank Template")
        if path: df.to_excel(path, index=False)

    def download_blocked_template(self):
        cols = ['Plnt', 'Plant', 'Material', 'Material Description']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", initialfile="Blocked_Template.xlsx", title="Save Blocked Template")
        if path: df.to_excel(path, index=False)

    def download_blocked_os_template(self):
        cols = ['Plnt', 'Plant', 'Material', 'Material Description']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", initialfile="Blocked_OS_Template.xlsx", title="Save Blocked OS Template")
        if path: df.to_excel(path, index=False)

    def download_avoid_zero_template(self):
        cols = ['Plnt', 'Branch Name', 'Material', 'Category']
        df = pd.DataFrame(columns=cols)
        path = fd.asksaveasfilename(defaultextension=".xlsx", initialfile="Avoid_Zero_Stock_Template.xlsx", title="Save Avoid Zero Template")
        if path: df.to_excel(path, index=False)

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

    def standardize_columns(self, df):
        df.columns = df.columns.astype(str).str.strip()
        rename_map = {
            'Branch Stock': 'Stock',
            'Pending to Branch': 'Pending preparation to branch',
            'Pending from DC': 'Pending preparation from DC',
            'Consumption90D': 'Consumption 90Day',
            'Ref.Cons 30D': 'Consumption last 30 days',
            'Ref.Cons First 5D': 'Consumption first 5 days of last month'
        }
        df.rename(columns=rename_map, inplace=True)
        return df

    def upload_main_file(self):
        path = fd.askopenfilename(filetypes=[('Excel files', '*.xlsx *.xls')])
        if path:
            self.file_path = path
            self.file_label.configure(text=f"Loaded Dataset: {os.path.basename(path)}", text_color="#e74c3c")
            self.process_btn.configure(state="normal")
            messagebox.showinfo("Success", "Raw ERP Sheet loaded!")

    def load_targets_from_excel(self):
        path = fd.askopenfilename(filetypes=[('Excel files', '*.xlsx *.xls')])
        if path:
            try:
                self.targets_df = pd.read_excel(path)
                self.load_targets_btn.configure(text="Targets Loaded ✔", fg_color="#27ae60")
            except Exception: pass
            
    def load_purchase_targets_from_excel(self):
        path = fd.askopenfilename(filetypes=[('Excel files', '*.xlsx *.xls')])
        if path:
            try:
                self.purchase_targets_df = pd.read_excel(path)
                self.load_purchase_targets_btn.configure(text="Purchase Trg ✔", fg_color="#27ae60")
            except Exception: pass

    def load_rank_from_excel(self):
        path = fd.askopenfilename(filetypes=[('Excel files', '*.xlsx *.xls')])
        if path:
            try:
                df_rank = pd.read_excel(path)
                p_col = next((c for c in df_rank.columns if c.strip().lower() in ['plnt', 'plant', 'branch']), None)
                rank_col = next((c for c in df_rank.columns if c.strip().lower() == 'rank'), None)
                if p_col:
                    self.rank_data.clear() 
                    current_rank = 1 
                    for _, row in df_rank.iterrows():
                        b = str(row[p_col]).strip()
                        if b and b != 'nan' and b not in self.rank_data:
                            if rank_col:
                                try: self.rank_data[b] = int(row[rank_col])
                                except: self.rank_data[b] = 999
                            else:
                                self.rank_data[b] = current_rank
                                current_rank += 1 
                    self.load_rank_btn.configure(text="Rank Loaded ✔", fg_color="#27ae60")
            except Exception: pass

    def load_blocked_from_excel(self):
        path = fd.askopenfilename(filetypes=[('Excel files', '*.xlsx *.xls')])
        if path:
            try:
                df_b = pd.read_excel(path)
                p_cols = [c for c in df_b.columns if c.strip().lower() in ['plnt', 'plant', 'branch']]
                m_col = next((c for c in df_b.columns if c.strip().lower() in ['material', 'item code']), None)
                if p_cols:
                    self.blocked_items.clear()
                    self.blocked_branches.clear()
                    for _, row in df_b.iterrows():
                        for p_col in p_cols:
                            b = str(row[p_col]).strip()
                            if b and b != 'nan':
                                if m_col:
                                    m = str(row[m_col]).replace('.0', '').strip()
                                    if m and m != 'nan' and m != '':
                                        self.blocked_items.add((b, m))
                                    else:
                                        self.blocked_branches.add(b)
                                else:
                                    self.blocked_branches.add(b)
                    self.load_blocked_btn.configure(text="Blocked Items ✔", fg_color="#27ae60")
            except Exception: pass

    def load_blocked_os_from_excel(self):
        path = fd.askopenfilename(filetypes=[('Excel files', '*.xlsx *.xls')])
        if path:
            try:
                df_b = pd.read_excel(path)
                p_cols = [c for c in df_b.columns if c.strip().lower() in ['plnt', 'plant', 'branch']]
                m_col = next((c for c in df_b.columns if c.strip().lower() in ['material', 'item code']), None)
                
                if p_cols:
                    self.blocked_os_items.clear()
                    self.blocked_os_branches.clear()
                    for _, row in df_b.iterrows():
                        for p_col in p_cols:
                            b = str(row[p_col]).strip()
                            if b and b != 'nan':
                                if m_col:
                                    m = str(row[m_col]).replace('.0', '').strip()
                                    if m and m != 'nan':
                                        self.blocked_os_items.add((b, m))
                                    else:
                                        self.blocked_os_branches.add(b)
                                else:
                                    self.blocked_os_branches.add(b)
                    self.load_blocked_os_btn.configure(text="Blocked OS ✔", fg_color="#27ae60")
            except Exception: pass

    def load_avoid_zero_from_excel(self):
        path = fd.askopenfilename(filetypes=[('Excel files', '*.xlsx *.xls')])
        if path:
            try:
                self.avoid_zero_df = pd.read_excel(path)
                self.load_avoid_zero_btn.configure(text="Avoid Zero ✔", fg_color="#27ae60")
            except Exception: pass

    def process_data(self):
        missing_files = []
        
        if self.file_path is None: missing_files.append("- Main ERP Sheet")
        if self.targets_df is None: missing_files.append("- Targets")
        if not self.rank_data: missing_files.append("- Rank")
        if self.avoid_zero_df is None: missing_files.append("- Avoid Zero")

        sto_threshold = 180
        try:
            if self.high_sto_var.get() == "Other...":
                sto_text = self.custom_sto_entry.get().strip()
                if not sto_text: raise ValueError
                sto_threshold = int(sto_text)
            else:
                sto_threshold = int(self.high_sto_var.get())
                
            if sto_threshold < 0: raise ValueError
        except ValueError:
            missing_files.append("- High STO Threshold (Days)")

        if missing_files:
            error_msg = "Please upload the following missing requirements:\n\n" + "\n".join(missing_files)
            messagebox.showerror("Missing Data", error_msg)
            self.process_btn.configure(state="normal")
            return  

        try:
            self.process_btn.configure(state="disabled")
            
            self.update_progress(0.1, "Phase 2: Loading & Standardizing Dataset...")
            df = pd.read_excel(self.file_path)
            df = self.standardize_columns(df)
            plant_col = 'Plnt' if 'Plnt' in df.columns else 'Plant' 
            if 'Display' not in df.columns: df['Display'] = 0
            if 'Storage Condition' not in df.columns: df['Storage Condition'] = ""
            if 'Manufacturer Name' not in df.columns: df['Manufacturer Name'] = ""
            
            df['temp_mat'] = df['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            df['temp_p'] = df[plant_col].astype(str).str.strip()
            
            df['Action Status'] = 'Pending'
            if 'Days Since Last STO' not in df.columns: df['Days Since Last STO'] = 0

            df['is_main_item'] = False
            # =================== SIMILAR ITEMS LOGIC ===================
            if self.similar_df is not None:
                self.update_progress(0.15, "Merging Similar Items Data...")
                sim_df = self.similar_df.copy()
                # جلب أسماء العمدان مهما كان فيها مسافات
                m_main_col = next((c for c in sim_df.columns if 'main' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), sim_df.columns[0])
                m_sim_col = next((c for c in sim_df.columns if 'similar' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), sim_df.columns[2])
                
                agg_columns = ['Stock', 'Pending preparation to branch', 'Display', 
                               'Consumption 180Day', 'Consumption 90Day', 
                               'Consumption last 30 days', 'Consumption first 5 days of last month']
                               
                for _, row in sim_df.iterrows():
                    main_mat = str(row[m_main_col]).replace('.0', '').strip()
                    sim_mat = str(row[m_sim_col]).replace('.0', '').strip()
                    
                    if main_mat and sim_mat and main_mat != 'nan' and sim_mat != 'nan':
                        sim_mask = df['temp_mat'] == sim_mat
                        if sim_mask.any():
                            # لف على الفروع اللي فيها الصنف السيميلار
                            for b in df.loc[sim_mask, 'temp_p'].unique():
                                s_b_mask = (df['temp_p'] == b) & (df['temp_mat'] == sim_mat)
                                m_b_mask = (df['temp_p'] == b) & (df['temp_mat'] == main_mat)
                                
                                if m_b_mask.any():
                                    # جمع الأرقام
                                    for col in agg_columns:
                                        if col in df.columns:
                                            s_val = pd.to_numeric(df.loc[s_b_mask, col].values[0], errors='coerce')
                                            s_val = 0 if pd.isna(s_val) else s_val
                                            m_val = pd.to_numeric(df.loc[m_b_mask, col].values[0], errors='coerce')
                                            m_val = 0 if pd.isna(m_val) else m_val
                                            df.loc[m_b_mask, col] = m_val + s_val
                                    df.loc[m_b_mask, 'is_main_item'] = True
                                            
                                # إضافة السيميلار للبلوكد العادي والـ OS عشان ميتحسبش خالص
                                self.blocked_items.add((b, sim_mat))
                                self.blocked_os_items.add((b, sim_mat))
                                df.loc[s_b_mask, 'Action Status'] = 'Merged as Similar & Blocked'
            # ==========================================================

            self.update_progress(0.2, "Phase 3.1: Applying Targets & Purchase Targets...")
            df['Target Days'] = 35 
            df['Overstock Target Days'] = 45 
            df['Target Distribution Target Days'] = 30 
            df['Purchase Target Days'] = 0 
            
            # --- MODIFIED: Flexible Targets logic ---
            if self.targets_df is not None:
                t_df = self.targets_df.copy()
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

            if self.purchase_targets_df is not None:
                pt_df = self.purchase_targets_df.copy()
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

            self.update_progress(0.3, "Phase 3.2: Applying Avoid Zero Stock Logic...")
            
            df['Is_Avoid_Zero'] = False 
            
            if self.avoid_zero_df is not None:
                az_df = self.avoid_zero_df.copy()
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

            self.update_progress(0.4, "Phase 3.3 & 3.4: Dynamic Consumption & REQ Calculation...")
            
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
            df['Final Positive REQ'] = np.where(df['Calculated POS REQ'] > 0, np.ceil(df['Calculated POS REQ']), 0).astype(int)

            # الـ Positive REQ بيبص على الـ Display
            mask_pos_display = (F_stock + df['Final Positive REQ']) < df['Display']
            df.loc[mask_pos_display, 'Final Positive REQ'] = df['Display'] - F_stock
            df['Final Positive REQ'] = df['Final Positive REQ'].clip(lower=0).astype(int)

            OS_target = df['Overstock Target Days']
            df['Required Safe Stock'] = df['Daily Consumption'] * OS_target
            df['Calculated NEG REQ'] = df['Required Safe Stock'] - Total_Stock
            
            df['Final Negative REQ'] = np.where(df['Calculated NEG REQ'] < 0, np.trunc(df['Calculated NEG REQ']), 0)
            df['Overstock QTY'] = abs(df['Final Negative REQ'])

            # -- Purchase Calculation (Branch Level) --
            df['Purchase Quantity'] = np.where(
                (df['Daily Consumption'] * df['Purchase Target Days']) - Total_Stock > 0,
                np.ceil((df['Daily Consumption'] * df['Purchase Target Days']) - Total_Stock),
                0
            ).astype(int)
            
            # --- تعديل الـ Purchase للـ Display الإجباري ---
            mask_purch_display = (F_stock + df['Purchase Quantity']) < df['Display']
            df.loc[mask_purch_display, 'Purchase Quantity'] = df['Display'] - F_stock
            df['Purchase Quantity'] = df['Purchase Quantity'].clip(lower=0).astype(int)

            self.update_progress(0.5, "Phase 3.5: Filtering Blocked Lists & Protecting Display...")
            if self.blocked_items:
                mask_bi = df.set_index(['temp_p', 'temp_mat']).index.isin(self.blocked_items)
                df.loc[mask_bi, 'Final Positive REQ'] = 0
                df.loc[mask_bi, 'Purchase Quantity'] = 0
                df.loc[mask_bi & (df['Action Status'] != 'Merged as Similar & Blocked'), 'Action Status'] = 'Blocked Item (User List)'
            
            if hasattr(self, 'blocked_branches') and self.blocked_branches:
                mask_bb = df['temp_p'].isin(self.blocked_branches)
                df.loc[mask_bb, 'Final Positive REQ'] = 0
                df.loc[mask_bb, 'Purchase Quantity'] = 0
                df.loc[mask_bb, 'Action Status'] = 'Blocked Branch (User List)'
                
            df_blocked_os_output = pd.DataFrame()
            
            if self.blocked_os_branches:
                mask_bos_b = df['temp_p'].isin(self.blocked_os_branches)
                df_blocked_os_output = pd.concat([df_blocked_os_output, df[mask_bos_b]])
                df.loc[mask_bos_b, 'Overstock QTY'] = 0
                df.loc[mask_bos_b, 'Action Status'] = 'Blocked OS Branch (User List)'
                
            if self.blocked_os_items:
                mask_bos_i = df.set_index(['temp_p', 'temp_mat']).index.isin(self.blocked_os_items)
                df_blocked_os_output = pd.concat([df_blocked_os_output, df[mask_bos_i]])
                df.loc[mask_bos_i, 'Overstock QTY'] = 0
                df.loc[mask_bos_i & (df['Action Status'] != 'Merged as Similar & Blocked'), 'Action Status'] = 'Blocked OS Item (User List)'

            if not df_blocked_os_output.empty:
                df_blocked_os_output = df_blocked_os_output.drop_duplicates(subset=['temp_p', 'temp_mat'])

            mask_display = (F_stock - df['Overstock QTY']) < df['Display']
            df.loc[mask_display & (df['Overstock QTY'] > 0) & (df['Action Status'] == 'Pending'), 'Action Status'] = 'Protected by Display Qty'
            df.loc[mask_display, 'Overstock QTY'] = F_stock - df['Display']
            df['Overstock QTY'] = df['Overstock QTY'].clip(lower=0).astype(int)

            self.update_progress(0.6, "Calculating Company Totals & Applying Pos/Neg Rules...")
            
            df['Pending preparation from DC'] = pd.to_numeric(df.get('Pending preparation from DC', 0), errors='coerce').fillna(0)
            df['Open PO Quantity'] = pd.to_numeric(df.get('Open PO Quantity', 0), errors='coerce').fillna(0)
            
            num_cols_to_fill = ['Dc Stock']
            for c in num_cols_to_fill:
                if c not in df.columns: df[c] = 0
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
            company_totals = df.groupby(['Material']).agg(
                Material_Group=('Material Group', 'first'),
                Material_Description=('Material Description', 'first'),
                Total_Dc=('Dc Stock', 'first'),
                Total_Pending_From_DC=('Pending preparation from DC', 'first'),
                Total_Open_PO=('Open PO Quantity', 'first'),
                Main_Category=('Main Category', 'first'),
                SubCategory_1=('SubCategory 1', 'first'),
                Storage_Condition=('Storage Condition', 'first'),
                Manufacturer_Name=('Manufacturer Name', 'first'),
                Created_On=('Created On', 'first'),
                Total_Stock=('Stock', 'sum'),
                Store_Outbound=('Pending preparation to branch', 'sum'),
                Consumption_90Day=('Consumption 90Day', 'sum'),
                Cons_30_Day=('Consumption last 30 days', 'sum'),
                Cons_180Day=('Consumption 180Day', 'sum'),
                Final_Positive_REQ_Internal=('Final Positive REQ', 'sum'),
                Final_Negative_REQ_Internal=('Overstock QTY', 'sum'),
                Total_Purchase_REQ=('Purchase Quantity', 'sum'),
                Sales_Price=('Sales Price', 'first')
            ).reset_index()

            # === تعديل: الحفاظ على الأصناف الأساسية (Main) والبديلة (Similar) في شيت Company Totals ===
            if self.similar_df is not None:
                m_main_col_ct = next((c for c in self.similar_df.columns if 'main' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), self.similar_df.columns[0])
                m_sim_col_ct = next((c for c in self.similar_df.columns if 'similar' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), self.similar_df.columns[2])
                
                main_codes_ct = self.similar_df[m_main_col_ct].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique()
                sim_codes_ct = self.similar_df[m_sim_col_ct].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique()
                combined_codes_ct = set(main_codes_ct).union(set(sim_codes_ct))
                
                mask_sim_main = company_totals['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().isin(combined_codes_ct)
            else:
                mask_sim_main = False

            company_totals = company_totals[
                (company_totals['Final_Positive_REQ_Internal'] > 0) | 
                (company_totals['Final_Negative_REQ_Internal'] > 0) | 
                (company_totals['Total_Purchase_REQ'] > 0) |
                mask_sim_main
            ].copy()

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
                
                is_checked = bool(self.zero_overstock_var.get())
                
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

            self.update_progress(0.7, "Running 5-Phase Dynamic Smart Pullback Algorithm...")
            df['Branch Rank'] = df['temp_p'].map(lambda x: self.rank_data.get(str(x), 999))
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

                mat_mask = (df['Material'] == mat) & (df['Overstock QTY'] > 0)
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

                # السطور دي هتجبر الكود يكتب إن ده صنف مين مهما كانت حالته
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
            self.update_progress(0.85, "Calculating Stock Reallocation (Branch Transfers)...")
            
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
            
            # --- تعديل الـ Distribution للـ Display الإجباري ---
            mask_dist_display = (df['Final Positive REQ'] > 0) & ((F_stock + df['Final Positive REQ (Distribution)']) < df['Display'])
            df.loc[mask_dist_display, 'Final Positive REQ (Distribution)'] = df['Display'] - F_stock
            
            df['Final Positive REQ (Distribution)'] = df['Final Positive REQ (Distribution)'].clip(lower=0, upper=df['Final Positive REQ']).astype(int)

            materials_to_reallocate = df[df['Realloc_Available'] > 0]['Material'].unique()

            for mat in materials_to_reallocate:
                donors = df[(df['Material'] == mat) & (df['Realloc_Available'] > 0)].sort_values('Realloc_Available', ascending=False).to_dict('records')
                receivers = df[(df['Material'] == mat) & (df['Final Positive REQ (Distribution)'] > 0)].sort_values('Final Positive REQ (Distribution)', ascending=False).to_dict('records')

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

            self.update_progress(0.9, "Preparing export sheets...")
            
            df_purchase = pd.DataFrame()
            if not company_totals.empty:
                pulled_totals = df.groupby('Material')['Final Pullback QTY'].sum().reset_index()
                pulled_totals.rename(columns={'Final Pullback QTY': 'Total Pulled Overstock'}, inplace=True)
                company_totals = pd.merge(company_totals, pulled_totals, on='Material', how='left')
                company_totals['Total Pulled Overstock'] = company_totals['Total Pulled Overstock'].fillna(0).astype(int)

                company_totals['Company Purchase Quantity'] = (
                    company_totals['Total_Purchase_REQ'] 
                    - company_totals['Total Pulled Overstock'] 
                    - company_totals['Total_Open_PO'] 
                    - (company_totals['Total Dc'] - company_totals['Pending from DC'])
                )
                company_totals['Company Purchase Quantity'] = company_totals['Company Purchase Quantity'].clip(lower=0).astype(int)

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
            df_all = df_all.sort_values(by=['Final Pullback QTY', 'Final Positive REQ', 'Branch Rank'], ascending=[False, False, True])

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
                    conn = sqlite3.connect(self.db_name)
                    db_data.to_sql('inventory_history', conn, if_exists='append', index=False)
                    conn.close()
                except Exception: pass

            # --- MODIFIED: Export with Progress Updates ---
            self.update_progress(0.92, "Initializing Excel Export...")
            save_path = fd.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], title="Save Output As", initialfile=f"Lotus_Inventory_Decision_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx")
            
            if save_path:
                with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
                    self.update_progress(0.93, "Exporting Company Totals Sheet...")
                    if not company_totals.empty:
                        company_totals.to_excel(writer, sheet_name='Company Totals', index=False)
                        df_rules_14_15 = company_totals[company_totals['Exclusion_Status'].str.contains('Rule 14|Rule 15', na=False)].copy()
                    else:
                        pd.DataFrame(columns=['Message']).append({'Message': 'No Targets Available'}, ignore_index=True).to_excel(writer, sheet_name='Company Totals', index=False)
                        df_rules_14_15 = pd.DataFrame()
                    
                    self.update_progress(0.95, "Exporting Purchase & Reallocation Sheets...")
                    if not df_purchase.empty:
                        df_purchase.to_excel(writer, sheet_name='Purchase', index=False)
                    if not df_reallocation.empty:
                        df_reallocation.to_excel(writer, sheet_name='Stock Reallocation', index=False)
                        
                    self.update_progress(0.97, "Exporting All Items Sheet (May take a moment)...")
                    df_all.to_excel(writer, sheet_name='All Items (With Status)', index=False)
                    
                    self.update_progress(0.99, "Exporting Rules & Blocked Items Sheets...")
                    if not df_rules_14_15.empty:
                        df_rules_14_15.to_excel(writer, sheet_name='Rules 14 & 15 Items', index=False)
                    if not df_blocked_final.empty: 
                        df_blocked_final.to_excel(writer, sheet_name='Blocked Items', index=False)
                    if self.similar_df is not None:
                        self.update_progress(0.99, "Exporting Detailed Similars Sheet...")
                        
                        # === تعديل: إحضار أكواد الـ Main بجانب الـ Similar ===
                        m_main_col = next((c for c in self.similar_df.columns if 'main' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), self.similar_df.columns[0])
                        m_sim_col = next((c for c in self.similar_df.columns if 'similar' in c.lower() and 'material' in c.lower() and 'desc' not in c.lower()), self.similar_df.columns[2])
                        
                        # تطهير الأكواد من أي أصفار عشرية عشان التطابق ينجح
                        main_codes = self.similar_df[m_main_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique()
                        sim_codes = self.similar_df[m_sim_col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique()
                        
                        # دمج جميع الأكواد الأساسية والبديلة في قائمة واحدة
                        all_sim_main_codes = set(main_codes).union(set(sim_codes))
                        
                        clean_materials = df_all['Material'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                        
                        # فلترة شيت All Items بناءً على القائمة المدمجة
                        df_sim_detailed = df_all[clean_materials.isin(all_sim_main_codes)].copy()
                        
                        # ترتيب البيانات ليظهر الصنف الأساسي بجوار البديل
                        df_sim_detailed = df_sim_detailed.sort_values(by=['Material'])
                        
                        # تصدير في تاب اسمها Similars
                        df_sim_detailed.to_excel(writer, sheet_name='Similars', index=False)
                self.update_progress(1.0, "Done!")
                messagebox.showinfo("Export Successful", f"Engine run successfully!\nResults exported to:\n{save_path}")

        except Exception as e:
            import traceback
            traceback.print_exc()
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
            history_df = pd.read_sql("SELECT * FROM inventory_history", conn)
            conn.close()
            if history_df.empty:
                messagebox.showinfo("History Empty", "The history database is currently empty.")
                return
            save_path = fd.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], title="Save History As", initialfile="Lotus_Inventory_History.xlsx")
            if save_path:
                history_df.to_excel(save_path, index=False)
                messagebox.showinfo("Success", f"Full history exported successfully to:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to export history:\n{e}")

if __name__ == "__main__":
    app = LotusInventoryApp()
    app.mainloop()