"""Generate a simple written PDF guide for Purchase and Replenishment engines."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent.parent / "docs" / "Lotus-Logic-Guide.pdf"

MARGIN = 18
LINE = 6


class GuidePDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "Lotus Inventory - Engine Guide", align="R")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def section_title(self, title: str):
        self.set_x(self.l_margin)
        self.ln(4)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(30, 100, 60)
        self.multi_cell(self.epw, 8, title)
        self.ln(2)

    def sub_title(self, title: str):
        self.set_x(self.l_margin)
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(40, 40, 40)
        self.multi_cell(self.epw, 7, title)
        self.ln(1)

    def body(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(self.epw, LINE, text)
        self.ln(1)

    def bullet(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(self.epw, LINE, f"- {text}")

    def label_line(self, label: str, value: str):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 30, 30)
        self.cell(self.epw, LINE, label, new_x="LMARGIN", new_y="NEXT")
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 10)
        self.multi_cell(self.epw, LINE, value)


def file_block(pdf: GuidePDF, name: str, required: bool, columns: str, purpose: str, effect: list[str]):
    pdf.sub_title(name)
    pdf.label_line("Status:", "Required" if required else "Optional")
    pdf.label_line("Columns:", columns)
    pdf.body(purpose)
    pdf.body("What the engine does with this file:")
    for item in effect:
        pdf.bullet(item)
    pdf.ln(2)


def build_pdf() -> None:
    pdf = GuidePDF()
    pdf.set_auto_page_break(auto=True, margin=MARGIN)
    pdf.add_page()

    # Cover
    pdf.ln(40)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(30, 100, 60)
    pdf.cell(0, 12, "Lotus Inventory Management", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 10, "Engine Upload Files & Logic Guide", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(
        pdf.epw,
        7,
        "This guide explains each Excel file you upload in the Purchase (Inventory) "
        "Engine and the Replenishment Engine, and how the system uses them.",
        align="C",
    )

    # ==================== PURCHASE ENGINE ====================
    pdf.add_page()
    pdf.section_title("1. Purchase (Inventory) Engine")
    pdf.body(
        "The Purchase Engine reads branch-level ERP data and calculates POS requirements, "
        "purchase quantities, overstock pullbacks, and company-level buy/transfer decisions. "
        "Upload the files below on the Inventory Engine page, then click Run."
    )

    file_block(
        pdf,
        "1. ERP Sheet",
        required=True,
        columns="Plnt/Plant, Material, Material Group, Material Description, Branch Stock, "
        "Pending to Branch, Open PO Quantity, Display, Dc Stock, Pending from DC, "
        "Consumption 180Day, Consumption90D, Ref.Cons 30D, Ref.Cons First 5D, Sales Price, "
        "Max Receipt, Main Category, SubCategory 1, Storage Condition, Manufacturer Name, "
        "Created On, Days Since Last STO, Days from last sell",
        purpose="The main dataset. One row per item per branch. This is the source of all stock, "
        "consumption, display, and DC quantities.",
        effect=[
            "Standardizes column names (e.g. Branch Stock becomes Stock).",
            "Calculates daily consumption from 90-day consumption using a dynamic window (30, 45, or 90 days).",
            "Computes POS REQ = (Daily Consumption x Target Days) - (Stock + Pending to Branch).",
            "Raises POS REQ if Stock + REQ is below the Display minimum shelf quantity.",
            "Computes Purchase Quantity using Purchase Target Days (from Targets or Purchase Trg file).",
            "Computes Overstock QTY from Overstock Target Days.",
            "Rolls up totals per Material for company-level decisions.",
        ],
    )

    file_block(
        pdf,
        "2. Targets",
        required=True,
        columns="Plnt/Plant, Main Category, Target Days, Overstock Target Days, "
        "Target Distribution Target Days",
        purpose="Sets how many days of stock each branch should hold, split by Pharma / Non-Pharma category.",
        effect=[
            "Target Days - used for POS REQ calculation.",
            "Overstock Target Days - used to calculate excess stock (Overstock QTY).",
            "Target Distribution Target Days - used in branch reallocation phase.",
            "If no category column is present, values apply to all items in that branch.",
            "Default fallback: Target Days = 35, Overstock = 45, Distribution = 30.",
        ],
    )

    file_block(
        pdf,
        "2.b Purchase Trg (Purchase Targets)",
        required=False,
        columns="Plnt/Plant, Main Category, Target Days",
        purpose="Optional separate target days used only for Purchase Quantity (not POS REQ).",
        effect=[
            "If uploaded, Purchase Quantity = (Daily Consumption x Purchase Target Days) - Total Stock.",
            "If not uploaded, Purchase Target Days stays 0 unless set inside the Targets file.",
            "Display rule still applies: Purchase Quantity is raised to reach Display minimum.",
        ],
    )

    file_block(
        pdf,
        "3. Rank",
        required=True,
        columns="Plnt/Plant, Rank",
        purpose="Defines branch priority order (1 = highest priority).",
        effect=[
            "Used during Smart Pullback - when pulling overstock from branches, lower rank number = pulled first.",
            "Used during Branch Reallocation - higher-priority branches receive stock first.",
            "Branches not in the file get rank 999 (lowest priority).",
        ],
    )

    file_block(
        pdf,
        "4. Avoid Zero",
        required=True,
        columns="Plnt/Plant/Branch Name, Material, Category",
        purpose="Marks items, categories, or entire branches that must never be pulled to zero stock.",
        effect=[
            "If Material is filled - that specific item at that branch is protected.",
            "If Category is filled (Pharma / Non-Pharma / All) - all items in that category at the branch are protected.",
            "If only branch is filled - all items at that branch are protected.",
            "Protected items are skipped during overstock pullback calculations.",
        ],
    )

    file_block(
        pdf,
        "5. Blocked Items",
        required=False,
        columns="Plnt/Plant, Material, Material Description",
        purpose="Items or branches that should not receive normal POS REQ or Purchase quantities.",
        effect=[
            "If Material is empty - the entire branch is blocked.",
            "If Material is filled - only that item at that branch is blocked.",
            "Blocked rows get Final Positive REQ = 0 and Purchase Quantity = 0.",
            "Exception: if Display > Stock, the engine keeps the Display shortfall in REQ and Purchase.",
        ],
    )

    file_block(
        pdf,
        "6. Blocked OS (Blocked Overstock)",
        required=False,
        columns="Plnt/Plant, Material, Material Description",
        purpose="Items or branches excluded from overstock pullback (OS) calculations.",
        effect=[
            "Same format as Blocked Items - branch-level or item-level.",
            "Overstock QTY is set to 0 for blocked rows.",
            "These rows are exported to a separate Blocked OS sheet.",
            "Does not affect POS REQ or Purchase Quantity.",
        ],
    )

    file_block(
        pdf,
        "7. Similar Items",
        required=False,
        columns="Material (Main), Material description (Main), Material (Similar), "
        "Material description (Similar)",
        purpose="Links a Similar SKU to a Main SKU so their stock and consumption are combined.",
        effect=[
            "At each branch, Similar item stock/consumption/display is merged into the Main item.",
            "The Similar item is automatically added to Blocked Items and Blocked OS.",
            "Similar rows are marked 'Merged as Similar & Blocked'.",
            "Company Totals sheet keeps both Main and Similar material codes visible.",
        ],
    )

    pdf.add_page()
    pdf.sub_title("Purchase Engine - Processing Steps (after uploads)")
    steps = [
        "Load ERP Sheet and standardize columns.",
        "Merge Similar Items (if uploaded) - combine stock/consumption into Main SKU.",
        "Apply Targets and Purchase Targets - set Target Days per branch/category.",
        "Apply Avoid Zero flags.",
        "Calculate daily consumption, POS REQ, Purchase Quantity, and Overstock QTY.",
        "Apply Display minimum rules on POS REQ and Purchase Quantity.",
        "Apply Blocked Items rules (keep Display shortfall if needed).",
        "Apply Blocked OS rules (zero out overstock).",
        "Aggregate to Company Totals - decide BUY vs Pullback/Transfer per material.",
        "Run Smart Pullback Algorithm using Rank and Avoid Zero.",
        "Run Branch Reallocation using Rank and Distribution Target Days.",
        "Export Excel with POS, Purchase, Company Totals, Blocked, and history sheets.",
    ]
    for i, step in enumerate(steps, 1):
        pdf.bullet(f"{i}. {step}")

    # ==================== REPLENISHMENT ENGINE ====================
    pdf.add_page()
    pdf.section_title("2. Replenishment Engine")
    pdf.body(
        "The Replenishment Engine distributes available DC stock to branches based on "
        "target days, consumption, Display minimums, and branch rank. "
        "Upload files on the Replenishment page, configure branch targets, then click Run."
    )

    file_block(
        pdf,
        "1. Main Dataset",
        required=True,
        columns="Plnt/Plant, Material, Material Group, Material Description, Branch Stock, "
        "Pending to Branch, Display, Dc Stock, Pending from DC, Consumption90D, "
        "Ref.Cons 30D, Ref.Cons First 5D, Sales Price, Max Receipt, Main Category, "
        "SubCategory 1, Storage Condition, Manufacturer Name",
        purpose="The main dataset. One row per item per branch. Source of stock, pending, "
        "display, DC stock, and consumption.",
        effect=[
            "Branch list is extracted from this file for target configuration.",
            "Stock + Pending to Branch = effective branch stock.",
            "DC Stock minus Pending from DC = available DC quantity for allocation.",
            "Daily consumption is calculated from 90-day consumption (30/45/90 day window).",
            "Required quantity per branch = (Daily Consumption x Target Days) - (Stock + Pending).",
            "Display rule: if Stock + Pending + Required < Display, Required is raised to fill Display gap.",
        ],
    )

    file_block(
        pdf,
        "2. Targets",
        required=False,
        columns="Plnt/Plant, Main Category, Target Days",
        purpose="Sets target stock days per branch, split by Pharma / Non-Pharma.",
        effect=[
            "Can also be configured manually in the UI after uploading Main Dataset.",
            "Pharma items use the Pharma target days for that branch.",
            "Non-Pharma items use the Non-Pharma target days.",
            "If consumption in first 5 days of last month is high (>80% of monthly rate), target is forced to 30 days.",
        ],
    )

    file_block(
        pdf,
        "3. Rank",
        required=False,
        columns="Plnt/Plant, Rank",
        purpose="Branch priority when DC stock is not enough for all branches.",
        effect=[
            "Lower rank number = higher priority.",
            "When DC stock is limited, the engine scales down target days proportionally.",
            "Remaining DC units are allocated to highest-priority branches first (by rank).",
            "Branches not listed get rank 999.",
        ],
    )

    file_block(
        pdf,
        "4. Blocked Items",
        required=False,
        columns="Plnt/Plant, Material, Material Description",
        purpose="Items or branches excluded from normal DC allocation.",
        effect=[
            "Blocked rows are removed from the main DC engine calculation.",
            "Exported separately with Final Required based on Display only.",
            "If Display > Stock + Pending, Final Required = Display gap (shelf fill only).",
            "If no Display gap, Final Required = 0.",
            "These rows skip the 20% rule and DC cap logic.",
        ],
    )

    file_block(
        pdf,
        "5. Similar Items",
        required=False,
        columns="Material (Main), Material description (Main), Material (Similar), "
        "Material description (Similar)",
        purpose="Groups Similar SKUs under a Main SKU for combined stock and consumption.",
        effect=[
            "Stock and consumption of Main + Similar are summed per branch group.",
            "Similar items are marked Item_Role = Similar; Main items stay as Main.",
            "DC allocation is calculated on the combined group totals.",
            "Main/Similar pairs are protected from forced DC drain logic.",
        ],
    )

    pdf.add_page()
    pdf.sub_title("Replenishment Engine - Processing Steps (after uploads)")
    steps = [
        "Load Main Dataset and standardize columns.",
        "Separate Blocked Items/Branches - keep Display-only requirements.",
        "Group Similar Items - combine stock and consumption under Main SKU.",
        "Apply branch Targets (from file or UI) - Pharma / Non-Pharma days.",
        "Calculate daily consumption and required quantity per branch.",
        "Apply Display minimum rule on required quantity.",
        "Check total required vs available DC stock.",
        "If over DC limit - scale target days down (binary search) to fit DC stock.",
        "Allocate remaining DC units by branch Rank (priority fill).",
        "Apply 20% rule - if required is less than 20% of current stock, set to 0 "
        "(skipped for blocked Display-only rows).",
        "Merge blocked Display rows back into export.",
        "Export multi-sheet Excel with allocation results per branch.",
    ]
    for i, step in enumerate(steps, 1):
        pdf.bullet(f"{i}. {step}")

    pdf.ln(4)
    pdf.sub_title("Key Formulas (both engines)")
    pdf.bullet("Daily Consumption = Consumption 90Day / chosen days (30, 45, or 90)")
    pdf.bullet("Display Gap = ceil(Display - Stock - Pending to Branch)  [when Display > 0]")
    pdf.bullet("Available DC = Dc Stock - Pending from DC")
    pdf.bullet("Purchase: POS REQ = max(0, Daily Consumption x Target Days - Total Stock)")
    pdf.bullet("Replenishment: Required = max(0, Daily Consumption x Target Days - (Stock + Pending))")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build_pdf()
