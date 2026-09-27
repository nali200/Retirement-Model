import os
import re
import glob
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
from PIL import Image

# 1. Try loading PyTesseract for image OCR
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# 2. Try loading pypdf for PDF text extraction
try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# 3. Try loading yfinance for automatic public market NAV lookups
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# Page Configuration
st.set_page_config(
    page_title="30-Year Wealth & Tax Engine",
    page_icon="📈",
    layout="wide"
)

# ==============================================================================
# 1. MODERN FINTECH STYLING (CSS)
# ==============================================================================
st.markdown("""
<style>
    /* Dark Slate Background */
    .stApp {
        background-color: #0F172A;
        color: #F8FAFC;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Modern Glassmorphism Cards */
    .fintech-card {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        backdrop-filter: blur(12px);
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
    }
    
    /* Directive Action Cards */
    .directive-card-info {
        background: rgba(30, 41, 59, 0.8);
        border-left: 5px solid #3B82F6;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .directive-card-success {
        background: rgba(30, 41, 59, 0.8);
        border-left: 5px solid #10B981;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .directive-card-warning {
        background: rgba(30, 41, 59, 0.8);
        border-left: 5px solid #F59E0B;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }

    /* Metric Subtext & Badges */
    .metric-label {
        color: #94A3B8;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-value {
        color: #F8FAFC;
        font-size: 1.8rem;
        font-weight: 700;
        margin-top: 4px;
        margin-bottom: 4px;
    }
    .badge-green {
        background: rgba(16, 185, 129, 0.2);
        color: #34D399;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-blue {
        background: rgba(59, 130, 246, 0.2);
        color: #60A5FA;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. AUTOMATED PUBLIC MARKET NAV LOOKUP
# ==============================================================================
@st.cache_data(ttl=3600)
def fetch_closest_trading_nav(target_date_str, fallback_price=100.0):
    if not YFINANCE_AVAILABLE:
        return float(fallback_price), "Model Projection (yfinance offline)"

    try:
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        today_dt = datetime.now()

        if target_dt > today_dt:
            return float(fallback_price), "Future Date (Model Projection)"

        start_dt = target_dt - timedelta(days=7)
        end_dt = target_dt + timedelta(days=1)

        ticker = yf.Ticker("VUG")
        df = ticker.history(start=start_dt.strftime("%Y-%m-%d"), end=end_dt.strftime("%Y-%m-%d"))

        if not df.empty:
            latest_close = float(df['Close'].iloc[-1])
            actual_trade_date = df.index[-1].strftime("%m/%d/%Y")
            return float(latest_close), f"Live Market ({actual_trade_date})"
    except Exception:
        pass

    return float(fallback_price), "Model Projection (Fallback)"

def get_quarter_close_date_str(year, quarter):
    q_end_map = {
        1: f"{year - 1}-12-31",
        2: f"{year}-03-31",
        3: f"{year}-06-30",
        4: f"{year}-09-30"
    }
    return q_end_map[quarter]

# ==============================================================================
# 3. UNIFIED DOCUMENT PARSER (PDF & IMAGES)
# ==============================================================================
def parse_financials_from_document(uploaded_file):
    """
    Extracts financial balances from PDF files (using pypdf) 
    or image files (using PyTesseract OCR).
    """
    extracted_text = ""
    file_name = uploaded_file.name.lower()

    if file_name.endswith(".pdf"):
        if not PYPDF_AVAILABLE:
            st.warning("`pypdf` library not installed. Please add `pypdf` to requirements.txt.")
            return {}
        try:
            reader = pypdf.PdfReader(uploaded_file)
            for page in reader.pages:
                extracted_text += (page.extract_text() or "") + "\n"
        except Exception as e:
            st.error(f"Error reading PDF file: {e}")
            return {}
    else:
        if not OCR_AVAILABLE:
            st.warning("`pytesseract` library not installed. Manual entry active.")
            return {}
        try:
            image = Image.open(uploaded_file)
            extracted_text = pytesseract.image_to_string(image)
        except Exception as e:
            st.error(f"Error scanning image file: {e}")
            return {}

    parsed_values = {}
    lines = extracted_text.split('\n')

    for line in lines:
        amounts = re.findall(r'\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)', line)
        if amounts:
            val_str = amounts[0].replace(',', '')
            try:
                val = float(val_str)
                line_lower = line.lower()

                if 'taxable' in line_lower and 'taxable' not in parsed_values:
                    parsed_values['taxable'] = val
                elif ('inherited' in line_lower or 'rmd' in line_lower) and 'inh_ira' not in parsed_values:
                    parsed_values['inh_ira'] = val
                elif 'roth' in line_lower and 'roth' not in parsed_values:
                    parsed_values['roth'] = val
                elif ('sidecar' in line_lower or 'bond' in line_lower) and 'sidecar' not in parsed_values:
                    parsed_values['sidecar'] = val
                elif 'dividend' in line_lower and 'dividend' not in parsed_values:
                    parsed_values['dividend'] = val
                elif ('social security' in line_lower or 'ss' in line_lower) and 'ss' not in parsed_values:
                    parsed_values['ss'] = val
                elif 'medical' in line_lower and 'medical' not in parsed_values:
                    parsed_values['medical'] = val
                elif 'salt' in line_lower and 'salt' not in parsed_values:
                    parsed_values['salt'] = val
            except ValueError:
                pass

    return parsed_values

# ==============================================================================
# 4. MASTER EXCEL / CSV LOADER
# ==============================================================================
class SingleFileModelLoader:
    def __init__(self, file_or_folder="."):
        self.file_or_folder = file_or_folder
        self.sheets = {}
        self.load_model()

    def load_model(self):
        excel_files = glob.glob("*.xlsx") if isinstance(self.file_or_folder, str) else []
        
        if hasattr(self.file_or_folder, "name") and self.file_or_folder.name.endswith(".xlsx"):
            xls = pd.ExcelFile(self.file_or_folder)
            for sheet in xls.sheet_names:
                self.sheets[clean_sheet_name(sheet)] = pd.read_excel(xls, sheet_name=sheet)
        elif len(excel_files) > 0:
            xls = pd.ExcelFile(excel_files[0])
            for sheet in xls.sheet_names:
                self.sheets[clean_sheet_name(sheet)] = pd.read_excel(xls, sheet_name=sheet)
        else:
            folder = self.file_or_folder if isinstance(self.file_or_folder, str) else "."
            self.sheets['main'] = pd.read_csv(os.path.join(folder, 'Official_retirement_model_9-23_Main.csv'))
            self.sheets['outside'] = pd.read_csv(os.path.join(folder, 'Official_retirement_model_9-23_Outside_Income.csv'))
            self.sheets['ira'] = pd.read_csv(os.path.join(folder, 'Official_retirement_model_9-23_Inherited_and_Roth_IRA.csv'))
            self.sheets['cg'] = pd.read_csv(os.path.join(folder, 'Official_retirement_model_9-23_Capital_Gains.csv'))
            self.sheets['sched_a'] = pd.read_csv(os.path.join(folder, 'Official_retirement_model_9-23_Schedule_A.csv'))

        for key in self.sheets:
            df = self.sheets[key]
            year_col = [c for c in df.columns if 'Year' in c or 'year' in c]
            if year_col:
                df.dropna(subset=[year_col[0]], inplace=True)
                df['Year'] = df[year_col[0]].astype(int)

    def get_available_years(self):
        df = self.get_sheet('main')
        return sorted(df['Year'].unique().tolist())

    def get_sheet(self, key_name):
        for k in self.sheets:
            if key_name in k.lower():
                return self.sheets[k]
        return list(self.sheets.values())[0]

    def get_baseline_values(self, year):
        df_main = self.get_sheet('main')
        df_out = self.get_sheet('outside')
        df_ira = self.get_sheet('ira')
        df_cg = self.get_sheet('cg')
        df_sched = self.get_sheet('sched')

        r_main = df_main[df_main['Year'] == year].iloc[0]
        r_out = df_out[df_out['Year'] == year].iloc[0]
        r_ira = df_ira[df_ira['Year'] == year].iloc[0]
        r_cg = df_cg[df_cg['Year'] == year].iloc[0]
        r_sched = df_sched[df_sched['Year'] == year].iloc[0]

        return {
            'year': int(year),
            'annual_budget': float(r_main['Annual Budget']),
            'ss_annual': float(r_out['Combined Social Security (1% COLA)']),
            'annuity_aug': float(r_out['Equitrust Annuity (Roth)']),
            'irs_divisor': float(r_ira['IRS Divisor']),
            'vug_jan1_nav': float(r_cg['VUG Share Price']),
            'projected_taxable': float(r_main['Taxable Pool End']),
            'projected_inh_ira': float(r_main['Inherited IRA End']),
            'projected_roth_ira': float(r_main['Roth IRAs End']),
            'projected_total': float(r_main['Total Net Assets']),
            'inv_int_expense': float(r_sched['Investment Interest Expense from Viatar K-1']),
            'sec163d_election': float(r_sched['Optimal § 163(d) Election']),
            'allowed_inv_int_baseline': float(r_sched['Allowed Investment Interest Deduction']),
            'obbba_salt_cap': float(r_sched['OBBBA Base SALT Cap'])
        }

def clean_sheet_name(name):
    return name.lower().replace(' ', '_').replace('-', '_')

@st.cache_resource
def get_default_loader():
    return SingleFileModelLoader()

loader = get_default_loader()

# ==============================================================================
# 5. REBALANCING ENGINE (SEP 30 BASELINE + 250% SIDECAR CAP)
# ==============================================================================
def compute_sep30_baseline_directives(year, quarter, current_public_nav, sep30_prior_nav, actual_inh_ira_bal, sidecar_balance):
    data = loader.get_baseline_values(year)
    q_budget = data['annual_budget'] / 4.0
    q_ss = data['ss_annual'] / 4.0

    divisor = data['irs_divisor']
    actual_rmd = (actual_inh_ira_bal / divisor) if (divisor > 0 and actual_inh_ira_bal > 0) else 0.0

    if quarter == 1:
        inflows = q_ss + actual_rmd
        rmd_directive = (f"Execute calculated RMD of **${actual_rmd:,.2f}** from Inherited IRA to checking "
                         f"(${actual_inh_ira_bal:,.2f} ÷ {divisor:.1f} IRS Divisor)."
                         if actual_rmd > 0 else "Inherited IRA balance is $0 (RMD = $0).")
    elif quarter == 2:
        inflows = q_ss
        rmd_directive = "No RMD scheduled for Q2."
    elif quarter == 3:
        inflows = q_ss + data['annuity_aug']
        rmd_directive = "No RMD scheduled for Q3."
    else:
        inflows = q_ss
        rmd_directive = "No RMD scheduled for Q4."

    net_draw = q_budget - inflows
    annual_net_draw = net_draw * 4.0
    sidecar_cap = 2.50 * annual_net_draw

    r_vug_pct = ((current_public_nav - sep30_prior_nav) / sep30_prior_nav) * 100.0
    cum_hurdle_pct = quarter * 2.75

    quarter_labels = {
        1: "Prior Sep 30 → Jan 1 (Q1)",
        2: "Prior Sep 30 → Apr 1 (Q2)",
        3: "Prior Sep 30 → Jul 1 (Q3)",
        4: "Prior Sep 30 → Oct 1 (Q4)"
    }
    period_label = quarter_labels[quarter]

    if r_vug_pct > cum_hurdle_pct:
        draw_source = "VUG Equity Pool"
        excess_pct = r_vug_pct - cum_hurdle_pct

        if sidecar_balance >= sidecar_cap:
            sidecar_directive = (
                f"**ABOVE TARGET PERFORMANCE** ({period_label}: +{r_vug_pct:.2f}% vs target of {cum_hurdle_pct:.2f}%). "
                f"Liquidate **${net_draw:,.2f}** from VUG. **SIDECAR FULLY FUNDED AT 250% CAP** "
                f"(${sidecar_balance:,.2f} ≥ cap of ${sidecar_cap:,.2f}). "
                f"No excess gain harvested to Sidecar; all remaining growth retained in VUG."
            )
            directive_status = "success"
        else:
            needed_room = sidecar_cap - sidecar_balance
            sidecar_directive = (
                f"**ABOVE TARGET PERFORMANCE** ({period_label}: +{r_vug_pct:.2f}% vs target of {cum_hurdle_pct:.2f}%). "
                f"Liquidate **${net_draw:,.2f}** from VUG. Harvest excess gain (+{excess_pct:.2f}%) "
                f"into Sidecar US Govt Bond Fund up to the 250% cap of ${sidecar_cap:,.2f} "
                f"(Room remaining: ${needed_room:,.2f})."
            )
            directive_status = "success"
    elif r_vug_pct > 0.0:
        draw_source = "VUG Equity Pool"
        sidecar_directive = (
            f"**MODERATE PERFORMANCE** ({period_label}: +{r_vug_pct:.2f}% vs target of {cum_hurdle_pct:.2f}%). "
            f"Liquidate **${net_draw:,.2f}** directly from VUG. Leave Sidecar Bond Fund untouched."
        )
        directive_status = "info"
    else:
        draw_source = "Sidecar Bond Reserve"
        sidecar_directive = (
            f"**MARKET DOWNSIDE** ({period_label}: {r_vug_pct:.2f}%). **DO NOT SELL VUG.** "
            f"Draw full net cash distribution of **${net_draw:,.2f}** from Vanguard US Govt Bond Fund (Sidecar)."
        )
        directive_status = "warning"

    return {
        'q_budget': q_budget,
        'inflows': inflows,
        'net_draw': net_draw,
        'annual_net_draw': annual_net_draw,
        'sidecar_cap': sidecar_cap,
        'actual_rmd': actual_rmd,
        'irs_divisor': divisor,
        'r_vug_pct': r_vug_pct,
        'cum_hurdle_pct': cum_hurdle_pct,
        'period_label': period_label,
        'draw_source': draw_source,
        'rmd_directive': rmd_directive,
        'sidecar_directive': sidecar_directive,
        'directive_status': directive_status
    }

def simulate_viatar_tax_k1_optimizer(year, w2_income, actual_ss, actual_roth_conv, actual_div, actual_cg,
                                      actual_med, actual_salt, salt_exceeds_cap, actual_mortgage, actual_charity):
    data = loader.get_baseline_values(year)
    inv_int_expense_model = data['inv_int_expense']
    obbba_salt_cap = data['obbba_salt_cap']

    target_interest_deduction = min(inv_int_expense_model, data['allowed_inv_int_baseline'])
    dynamic_sec163d_election = max(0.0, target_interest_deduction - actual_div)
    allowed_inv_int_deduction = actual_div + dynamic_sec163d_election

    taxable_ss = 0.85 * actual_ss
    salt_deduction = obbba_salt_cap if salt_exceeds_cap else min(actual_salt, obbba_salt_cap)

    fixed_deductions = salt_deduction + actual_mortgage + actual_charity + allowed_inv_int_deduction
    numerator = 20000.0 + actual_med + fixed_deductions
    agi_target = numerator / 1.075

    gross_ordinary_before_viatar = (w2_income + taxable_ss + actual_div + actual_roth_conv + dynamic_sec163d_election)
    required_viatar_loss = gross_ordinary_before_viatar + actual_cg - agi_target

    med_deductible = max(0.0, actual_med - (0.075 * agi_target))
    total_sched_a = med_deductible + fixed_deductions
    taxable_ordinary = agi_target - total_sched_a

    return {
        'inv_int_expense_model': inv_int_expense_model,
        'dynamic_sec163d_election': dynamic_sec163d_election,
        'allowed_inv_int_deduction': allowed_inv_int_deduction,
        'gross_ordinary_before_viatar': gross_ordinary_before_viatar,
        'agi_target': agi_target,
        'required_viatar_loss': max(0.0, required_viatar_loss),
        'total_sched_a': total_sched_a,
        'taxable_ordinary': taxable_ordinary
    }

# ==============================================================================
# 6. STREAMLIT INTERFACE
# ==============================================================================
st.title("📈 30-Year Wealth & Tax Engine")

# EXPANDABLE TOP PANELS FOR FILES
with st.expander("📁 Optional: Upload Master Excel File (.xlsx)"):
    excel_file = st.file_uploader("Upload Master Excel Workbook", type=["xlsx"])
    if excel_file is not None:
        loader = SingleFileModelLoader(excel_file)
        st.success("Master Excel Workbook loaded successfully!")

with st.expander("📷 Optional: Upload Statement PDF or Image Screenshot"):
    uploaded_doc = st.file_uploader("Upload PDF or Image Statement", type=["pdf", "png", "jpg", "jpeg"])
    parsed_doc = {}
    if uploaded_doc is not None:
        parsed_doc = parse_financials_from_document(uploaded_doc)
        if parsed_doc:
            st.success(f"Extracted values: {parsed_doc}")

# SIDEBAR CONTROLS
st.sidebar.header("🕹️ Controls")
available_years = loader.get_available_years()
selected_year = st.sidebar.selectbox("Model Year", options=available_years, index=1)
selected_quarter = st.sidebar.radio(
    "Execution Date",
    options=[1, 2, 3, 4],
    index=0,
    format_func=lambda x: f"Q{x} ({'Jan 1' if x==1 else 'Apr 1' if x==2 else 'Jul 1' if x==3 else 'Oct 1'})"
)

baseline_data = loader.get_baseline_values(selected_year)

# AUTOMATED PUBLIC MARKET LOOKUPS
st.sidebar.markdown("---")
st.sidebar.header("🌐 Public Market NAVs")

sep30_date_str = f"{selected_year - 1}-09-30"
fallback_sep30_price = baseline_data['vug_jan1_nav'] / 1.0275
auto_sep30_nav, sep30_source = fetch_closest_trading_nav(sep30_date_str, fallback_price=fallback_sep30_price)

q_close_date_str = get_quarter_close_date_str(selected_year, selected_quarter)
fallback_q_price = fallback_sep30_price * (1 + (selected_quarter * 0.0275))
auto_q_nav, q_source = fetch_closest_trading_nav(q_close_date_str, fallback_price=fallback_q_price)

sep30_prior_nav = st.sidebar.number_input(
    f"Prior 9/30 Close (${sep30_date_str})",
    value=auto_sep30_nav,
    step=0.50,
    format="%.2f"
)
st.sidebar.caption(f"Status: **{sep30_source}**")

current_public_nav = st.sidebar.number_input(
    f"Q{selected_quarter} Close (${q_close_date_str})",
    value=auto_q_nav,
    step=0.50,
    format="%.2f"
)
st.sidebar.caption(f"Status: **{q_source}**")

st.sidebar.markdown("### Account Balances")
default_taxable = parsed_doc.get('taxable', baseline_data['projected_taxable'])
default_inh_ira = parsed_doc.get('inh_ira', baseline_data['projected_inh_ira'])
default_roth = parsed_doc.get('roth', baseline_data['projected_roth_ira'])
default_sidecar = parsed_doc.get('sidecar', 150000.0)

actual_taxable = st.sidebar.number_input("Taxable Pool Balance ($)", value=default_taxable, step=10000.0)
actual_inh_ira = st.sidebar.number_input("Inherited IRA Balance ($)", value=default_inh_ira, step=5000.0)
actual_roth = st.sidebar.number_input("Roth IRAs Balance ($)", value=default_roth, step=10000.0)
actual_sidecar = st.sidebar.number_input("Sidecar Bond Fund Balance ($)", value=default_sidecar, step=5000.0)

# Run Engine
q_res = compute_sep30_baseline_directives(
    selected_year, selected_quarter, current_public_nav, sep30_prior_nav, actual_inh_ira, actual_sidecar
)

# INTERFACE TABS
tab1, tab2, tab3 = st.tabs([
    "📋 Action Directives",
    "📊 Performance Scorecard",
    "🧮 K-1 Tax Optimizer"
])

with tab1:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="fintech-card">
            <div class="metric-label">ANNUAL BUDGET TARGET</div>
            <div class="metric-value">${baseline_data['annual_budget']:,.0f}</div>
            <span class="badge-blue">Model Baseline</span>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="fintech-card">
            <div class="metric-label">TARGET HURDLE GROWTH</div>
            <div class="metric-value">{q_res['cum_hurdle_pct']:.2f}%</div>
            <span class="badge-blue">Q{selected_quarter} Prorated</span>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="fintech-card">
            <div class="metric-label">EVALUATED RETURN</div>
            <div class="metric-value">{q_res['r_vug_pct']:+.2f}%</div>
            <span class="badge-green">{q_res['period_label']}</span>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="fintech-card">
            <div class="metric-label">SIDECAR 250% CAP</div>
            <div class="metric-value">${q_res['sidecar_cap']:,.0f}</div>
            <span class="badge-blue">2.5× Annual Net Draw</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### 🎫 Executable Action Directive Tickets")

    st.markdown(f"""
    <div class="directive-card-info">
        <strong style="color:#60A5FA;">🔷 1. REQUIRED MINIMUM DISTRIBUTION (RMD) DIRECTIVE</strong><br>
        <span style="font-size:1.05rem; color:#F8FAFC;">{q_res['rmd_directive']}</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="directive-card-success">
        <strong style="color:#34D399;">🟩 2. NET CASH DRAW DIRECTIVE</strong><br>
        <span style="font-size:1.05rem; color:#F8FAFC;">Liquidate <strong>${q_res['net_draw']:,.2f}</strong> from <strong>{q_res['draw_source']}</strong> to satisfy budget & tax vouchers.</span>
    </div>
    """, unsafe_allow_html=True)

    card_class = "directive-card-success" if q_res['directive_status'] == 'success' else ("directive-card-info" if q_res['directive_status'] == 'info' else "directive-card-warning")
    st.markdown(f"""
    <div class="{card_class}">
        <strong style="color:#34D399;">❇️ 3. SIDECAR REBALANCE & HARVEST DIRECTIVE</strong><br>
        <span style="font-size:1.05rem; color:#F8FAFC;">{q_res['sidecar_directive']}</span>
    </div>
    """, unsafe_allow_html=True)

    total_actual = actual_taxable + actual_inh_ira + actual_roth + actual_sidecar
    total_proj = baseline_data['projected_total']
    variance = total_actual - total_proj
    var_pct = (variance / total_proj) * 100.0

    st.markdown(f"""
    <div class="directive-card-info">
        <strong style="color:#60A5FA;">📊 4. SCORECARD STATUS</strong><br>
        <span style="font-size:1.05rem; color:#F8FAFC;">Total Net Assets stand at <strong>${total_actual:,.2f}</strong> vs <strong>${total_proj:,.2f}</strong> projected (<strong>{var_pct:+.2f}%</strong> variance).</span>
    </div>
    """, unsafe_allow_html=True)

with tab2:
    st.subheader(f"Performance Scorecard ({selected_year})")

    scorecard_data = {
        "Account / Asset Pool": [
            "Taxable Pool (VUG + Cash)",
            "Inherited IRA",
            "Roth IRAs (Total)",
            "Sidecar US Govt Bond Fund",
            "Total Retirement Net Assets"
        ],
        "Model Projected ($)": [
            baseline_data['projected_taxable'],
            baseline_data['projected_inh_ira'],
            baseline_data['projected_roth_ira'],
            0.0,
            baseline_data['projected_total']
        ],
        "Actual Statement Balance ($)": [
            actual_taxable,
            actual_inh_ira,
            actual_roth,
            actual_sidecar,
            total_actual
        ]
    }

    df_score = pd.DataFrame(scorecard_data)
    df_score["Variance ($)"] = df_score["Actual Statement Balance ($)"] - df_score["Model Projected ($)"]
    df_score["Variance (%)"] = (df_score["Variance ($)"] / df_score["Model Projected ($)"]) * 100.0

    df_display = df_score.copy()
    df_display["Model Projected ($)"] = df_display["Model Projected ($)"].apply(lambda x: f"${x:,.2f}" if x > 0 else "—")
    df_display["Actual Statement Balance ($)"] = df_display["Actual Statement Balance ($)"].apply(lambda x: f"${x:,.2f}")
    df_display["Variance ($)"] = df_display["Variance ($)"].apply(lambda x: f"${x:+,.2f}")
    df_display["Variance (%)"] = df_display["Variance (%)"].apply(lambda x: f"{x:+.2f}%" if x != float('inf') else "N/A")

    st.table(df_display)

with tab3:
    st.subheader(f"Schedule K-1 Viatar Loss Optimizer ({selected_year})")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### Income Inputs")
        input_w2 = st.number_input("Actual W-2 Gross Earnings ($)", value=0.0, step=1000.0)
        input_ss = st.number_input("Actual Gross Social Security ($)", value=baseline_data['ss_annual'], step=1000.0)
        input_roth = st.number_input("Actual Roth IRA Conversion ($)", value=200000.0 if selected_year <= 2032 else 0.0, step=10000.0)
        input_div = st.number_input("Actual VUG Dividend Income ($)", value=17049.30, step=1000.0)
        input_cg = st.number_input("Actual Realized Capital Gains ($)", value=0.0, step=1000.0)

    with c2:
        st.markdown("#### Schedule A Deduction Inputs")
        input_med = st.number_input("Actual Unreimbursed Medical ($)", value=56847.0, step=2500.0)
        salt_over_cap = st.radio("Do SALT taxes exceed $40,400 OBBBA cap?", options=["Yes", "No"], index=0) == "Yes"
        input_salt = st.number_input("Actual SALT Taxes Paid ($)", value=60000.0, step=5000.0)
        input_mortgage = st.number_input("Actual Mortgage Interest ($)", value=3746.0, step=500.0)
        input_charity = st.number_input("Actual Charitable Contributions ($)", value=4000.0, step=500.0)

    tax_sim = simulate_viatar_tax_k1_optimizer(
        selected_year, input_w2, input_ss, input_roth, input_div, input_cg,
        input_med, input_salt, salt_over_cap, input_mortgage, input_charity
    )

    st.markdown("---")
    st.markdown(f"""
    <div class="fintech-card" style="text-align: center; border: 1px solid #3B82F6;">
        <div class="metric-label" style="font-size: 1rem; color: #60A5FA;">REQUIRED VIATAR BUSINESS LOSS (SCHEDULE K-1)</div>
        <div class="metric-value" style="font-size: 2.8rem; color: #34D399;">${tax_sim['required_viatar_loss']:,.2f}</div>
        <span class="badge-green">Target $20,000 Taxable Ordinary Income Floor Locked</span>
    </div>
    """, unsafe_allow_html=True)

    st.write(f"• **Viatar K-1 Investment Interest Expense (Model CSV)**: ${tax_sim['inv_int_expense_model']:,.2f}")
    st.write(f"• **Dynamic § 163(d) Capital Gain Election**: ${tax_sim['dynamic_sec163d_election']:,.2f}")
    st.write(f"• **Allowed Investment Interest Deduction**: ${tax_sim['allowed_inv_int_deduction']:,.2f}")
    st.write(f"• **Gross Ordinary Income (before Viatar loss)**: ${tax_sim['gross_ordinary_before_viatar']:,.2f}")
    st.write(f"• **Target Adjusted Gross Income (AGI)**: ${tax_sim['agi_target']:,.2f}")
    st.write(f"• **Total Schedule A Itemized Deductions**: ${tax_sim['total_sched_a']:,.2f}")
    st.write(f"• **Net Taxable Ordinary Income**: ${tax_sim['taxable_ordinary']:,.2f}")
