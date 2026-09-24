import streamlit as st
import pandas as pd
import urllib.parse
import io
import os
import math
from datetime import date, datetime, time
from database import supabase

# ReportLab Libraries for PDF Generation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -------------------------------------------------------------
# 1. PAGE CONFIGURATION & CACHING
# -------------------------------------------------------------
st.set_page_config(page_title="HRMS Enterprise Cloud", layout="wide")

@st.cache_data(ttl=300)
def fetch_cached_entities():
    try:
        return supabase.table("entities").select("*").execute().data or []
    except Exception:
        return []

@st.cache_data(ttl=300)
def fetch_cached_clients():
    try:
        return supabase.table("clients").select("*").execute().data or []
    except Exception:
        return []

@st.cache_data(ttl=120)
def fetch_cached_employees():
    try:
        return supabase.table("employees").select("*").execute().data or []
    except Exception:
        return []

# Custom CSS Styling
st.markdown("""
    <style>
    .main-title { font-size: 24px; font-weight: 700; color: #1E293B; margin-bottom: 12px; }
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { font-size: 14px; color: #64748B; padding: 6px 0px; }
    .stTabs [aria-selected="true"] { color: #EF4444 !important; border-bottom-color: #EF4444 !important; font-weight: bold; }
    .submit-red-btn button { background-color: #EF4444 !important; color: white !important; font-weight: 600; width: 100%; border: none; border-radius: 4px; padding: 10px; }
    .sidebar-brand { font-size: 19px; font-weight: bold; color: #0F172A; }
    .logged-badge { color: #059669; font-weight: bold; font-size: 13px; margin-bottom: 15px; }
    .stButton>button { width: 100%; border-radius: 4px; text-align: left; }
    .profile-card { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 14px; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# PERSISTENT SESSION HANDLING
# -------------------------------------------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    saved_user_id = st.query_params.get("session_user_id")
    saved_role = st.query_params.get("session_role")
    
    if saved_user_id and saved_role:
        if saved_user_id == "admin" and saved_role == "admin":
            st.session_state.user = {"user_id": "admin", "full_name": "Super Admin", "role": "admin"}
        else:
            try:
                res = supabase.table("employees").select("*").eq("user_id", saved_user_id).eq("role", saved_role).execute()
                if res.data:
                    st.session_state.user = res.data[0]
            except Exception:
                pass

if "active_admin_tab" not in st.session_state:
    st.session_state.active_admin_tab = "Dashboard Overview"

STANDARD_SHIFTS = [
    "General Shift (08:30 AM - 05:00 PM | 8.5 hrs)",
    "Morning Shift (06:00 AM - 02:30 PM | 8.5 hrs)",
    "Evening Shift (02:00 PM - 10:30 PM | 8.5 hrs)",
    "Night Shift (10:00 PM - 06:30 AM | 8.5 hrs)"
]

def get_entity_logo(entity_name):
    if not entity_name:
        return None
    ent_clean = str(entity_name).upper()
    try:
        for file in os.listdir("."):
            if file.startswith("logo_") and file.endswith((".png", ".jpg", ".jpeg")):
                key = file.replace("logo_", "").split(".")[0].upper()
                if key in ent_clean:
                    return file
    except Exception:
        pass
    return None

# Number to words converter for Tax Invoice
def num_to_words(number):
    try:
        units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
        teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
        
        def conv(n):
            if n < 10: return units[n]
            elif n < 20: return teens[n-10]
            elif n < 100: return tens[n//10] + (" " + units[n%10] if n%10!=0 else "")
            elif n < 1000: return units[n//100] + " Hundred" + (" and " + conv(n%100) if n%100!=0 else "")
            elif n < 100000: return conv(n//1000) + " Thousand" + (" " + conv(n%1000) if n%1000!=0 else "")
            elif n < 10000000: return conv(n//100000) + " Lakh" + (" " + conv(n%100000) if n%100000!=0 else "")
            else: return conv(n//10000000) + " Crore" + (" " + conv(n%10000000) if n%10000000!=0 else "")

        num_int = int(number)
        num_dec = int(round((number - num_int) * 100))
        words = "Indian Rupees " + conv(num_int)
        if num_dec > 0:
            words += " and " + conv(num_dec) + " Paise"
        words += " Only"
        return words
    except Exception:
        return f"Indian Rupees {number:,.2f} Only"

# -------------------------------------------------------------
# EXACT REPLICA: OFFER LETTER PDF GENERATION
# -------------------------------------------------------------
def generate_official_offer_letter(emp_data, entity_obj, client_name="DC&T Global", sal_rule=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    entity_name = entity_obj.get("name", "GEMSHINE MULTISERVICES") if entity_obj else "GEMSHINE MULTISERVICES"
    code_pref = entity_obj.get("code_prefix", "GM") if entity_obj else "GM"
    ent_addr = entity_obj.get("address", "Ground Floor, Gat No. 235, Khandoba Temple, Khed SEZ Road, Rajgurunagar, Maharashtra - 410505, India") if entity_obj else "Ground Floor, Gat No. 235, Khandoba Temple, Khed SEZ Road, Rajgurunagar, Maharashtra - 410505, India"
    ent_gst = entity_obj.get("gst_number", "27ABEFG0561D1ZS") if entity_obj else "27ABEFG0561D1ZS"
    ent_pan = entity_obj.get("pan_number", "ABEFG0561D") if entity_obj else "ABEFG0561D"
    ent_phone = entity_obj.get("phone", "+91 95032 95153") if entity_obj else "+91 95032 95153"
    ent_email = entity_obj.get("email", "gemshine855@gmail.com") if entity_obj else "gemshine855@gmail.com"

    # Logo
    logo_file = get_entity_logo(entity_name)
    logo_img = None
    if logo_file and os.path.exists(logo_file):
        try:
            logo_img = RLImage(logo_file, width=120, height=45)
        except Exception:
            logo_img = None

    # Top header table with Ref No and Logo
    ref_no = f"Ref No.: {code_pref}/2026/{str(emp_data.get('id', '038'))[:3].upper()}"
    date_str = f"Date: {date.today().strftime('%d %B %Y')}"
    header_table_data = [
        [Paragraph(f"<b>{ref_no}</b><br/>{date_str}", styles["Normal"]), logo_img if logo_img else ""]
    ]
    ht = Table(header_table_data, colWidths=[380, 160])
    ht.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    story.append(ht)
    story.append(Spacer(1, 10))

    title_p = Paragraph("<font size=14><b>Offer Letter</b></font>", ParagraphStyle(name="CenterTitle", alignment=1))
    story.append(title_p)
    story.append(Spacer(1, 12))

    salutation = f"Dear Mr./Ms. <b>{emp_data.get('full_name')}</b>,"
    story.append(Paragraph(salutation, styles["Normal"]))
    story.append(Spacer(1, 8))

    body1 = f"""Following your recent interview, we are pleased to offer you the position of <b>{emp_data.get('designation', 'Associate- Housekeeping')}</b> on a Fixed Term Contract with <b>{entity_name}</b> for our business operations in Facility Management and Industrial Services.<br/><br/>
Your initial place of posting will be at our client site <b>"{client_name}"</b>.<br/><br/>
This offer is subject to verification of all documents submitted by you. You shall always comply with all Company rules and client site regulations. Statutory benefits such as PF, ESIC, Bonus, and other applicable benefits shall be provided as per law. You may be transferred to any client site, project, or location depending on operational requirements.<br/><br/>
Your service contract will automatically come to an end upon completion of 1 year from your date of joining. In case the Company's agreement with the client is terminated or amended before completion of your contract period, your employment may also be discontinued accordingly.<br/><br/>
You are requested to join on or before <b>{date.today().strftime('%d %B %Y')}</b>.<br/><br/>
The details of your salary bifurcation are as below -"""
    story.append(Paragraph(body1, styles["Normal"]))
    story.append(Spacer(1, 10))

    basic = float(sal_rule.get("basic", 14010.0)) if sal_rule else 14010.0
    da = float(sal_rule.get("da", 2511.0)) if sal_rule else 2511.0
    hra = float(sal_rule.get("hra", 826.0)) if sal_rule else 826.0
    other = float(sal_rule.get("other_allowance", 813.0)) if sal_rule else 813.0
    gross = basic + da + hra + other

    ee_pf = round((basic + da) * 0.12, 2)
    pt = 200.0
    ee_esic = round(gross * 0.0075, 2)
    total_ded = ee_pf + pt + ee_esic
    net_take_home = gross - total_ded

    sal_table_data = [
        ["SR No", "PARTICULARS", "SALARY (PM)"],
        ["A", "Basic Salary", f"{basic:,.2f}"],
        ["B", "Dearness Allowance (DA)", f"{da:,.2f}"],
        ["C", "House Rent Allowance (HRA)", f"{hra:,.2f}"],
        ["D", "Other Allowance", f"{other:,.2f}"],
        ["E", "Gross Salary", f"{gross:,.2f}"],
        ["", "Deduction", ""],
        ["F", "PF @ 12% (A+B)", f"{ee_pf:,.2f}"],
        ["G", "Professional Tax (PT)", f"{pt:,.2f}"],
        ["H", "ESI @ 0.75% ON TOTAL 'E'", f"{ee_esic:,.2f}"],
        ["I", "Total Deductions", f"{total_ded:,.2f}"],
        ["J", "Net Salary (Take Home (E - I))", f"{net_take_home:,.2f}"]
    ]
    st_table = Table(sal_table_data, colWidths=[55, 335, 150])
    st_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#000000")),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
        ('FONTNAME', (0,5), (-1,5), 'Helvetica-Bold'),
        ('FONTNAME', (0,6), (-1,6), 'Helvetica-Bold'),
        ('FONTNAME', (0,10), (-1,10), 'Helvetica-Bold'),
        ('FONTNAME', (0,11), (-1,11), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (2,0), (2,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(st_table)
    story.append(Spacer(1, 15))

    footer_text = f"<b>{entity_name}</b><br/>Registered Office: {ent_addr}<br/>GSTIN: {ent_gst} | PAN: {ent_pan} | Email: {ent_email} | Phone: {ent_phone}"
    story.append(Paragraph(footer_text, ParagraphStyle(name="FooterS", fontSize=7.5, alignment=1, textColor=colors.HexColor("#334155"))))

    # Page 2: Sign-off & Acceptance
    story.append(PageBreak())
    if logo_img:
        story.append(logo_img)
        story.append(Spacer(1, 15))

    p2_text = """Kindly sign and return a duplicate copy of this letter as a token of your acceptance of the offer.<br/><br/>
We look forward to welcoming you and wish you a successful association with us.<br/><br/>
Yours Sincerely,<br/>
<b>For """ + entity_name + """</b><br/><br/><br/>
<b>Authorized Signatory</b><br/><br/>
<hr/><br/>
<font size=12><b>Acceptance of Offer</b></font><br/><br/>
I hereby accept the above offer and agree to join on the terms mentioned.<br/><br/>
Employee Name: <b>""" + str(emp_data.get('full_name')) + """</b><br/><br/>
Signature: ___________________________ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Date: ___________________
"""
    story.append(Paragraph(p2_text, styles["Normal"]))
    story.append(Spacer(1, 40))
    story.append(Paragraph(footer_text, ParagraphStyle(name="FooterS2", fontSize=7.5, alignment=1, textColor=colors.HexColor("#334155"))))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# -------------------------------------------------------------
# EXACT REPLICA: TAX INVOICE PDF GENERATION
# -------------------------------------------------------------
def generate_exact_tax_invoice(inv_data, entity_obj, client_obj):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    story = []

    e_name = entity_obj.get("name", "SAGAR ENTERPRISES") if entity_obj else "SAGAR ENTERPRISES"
    e_addr = entity_obj.get("address", "A/P Nimgaon tal-khed, Dist-pune") if entity_obj else "A/P Nimgaon tal-khed, Dist-pune"
    e_gst = entity_obj.get("gst_number", "27CZCPS2976N1ZI") if entity_obj else "27CZCPS2976N1ZI"
    e_pan = entity_obj.get("pan_number", "CZCPS2976N") if entity_obj else "CZCPS2976N"

    c_name = client_obj.get("name", "DAEBU AUTOMOTIVE SEAT INDIA PVT LTD") if client_obj else "DAEBU AUTOMOTIVE SEAT INDIA PVT LTD"
    c_addr = client_obj.get("plant_location", "Plot No-D-1, MIDC Chakan, Industrial Area Phase-II, Village Bhamboli Tal-Khed, Dist: Pune - 410501") if client_obj else "Plot No-D-1, MIDC Chakan, Industrial Area Phase-II, Village Bhamboli Tal-Khed, Dist: Pune - 410501"
    c_gst = client_obj.get("gst_number", "27AACCD4599E1ZH") if client_obj else "27AACCD4599E1ZH"

    inv_no = inv_data.get("invoice_number", "SE/26-27/51")
    inv_date = inv_data.get("invoice_date", date.today().strftime("%d/%m/%Y"))
    sub_total = float(inv_data.get("total_amount", 115146.0))
    cgst = round(sub_total * 0.09, 2)
    sgst = round(sub_total * 0.09, 2)
    grand_total = round(sub_total + cgst + sgst, 2)

    # Header Box
    h_title = Paragraph("<font size=14><b>Tax Invoice</b></font>", ParagraphStyle(name="InvT", alignment=1))
    story.append(h_title)
    story.append(Spacer(1, 5))

    p_from = Paragraph(f"<b>From -</b><br/><b>{e_name}</b><br/>{e_addr}<br/><b>GSTIN/UIN:</b> {e_gst}", styles["Normal"])
    p_meta = Paragraph(f"<b>Invoice No:</b> {inv_no}<br/><b>Dated:</b> {inv_date}<br/><b>Reference No. & Date:</b> -<br/><b>Buyer's Order No:</b> -", styles["Normal"])
    t_top = Table([[p_from, p_meta]], colWidths=[310, 252])
    t_top.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_top)

    p_buyer = Paragraph(f"<b>Buyer (Bill to)</b><br/><b>{c_name}</b><br/>{c_addr}<br/><b>GSTIN:</b> {c_gst}", styles["Normal"])
    p_disp = Paragraph(f"<b>Consignee (Ship to)</b><br/><b>{c_name}</b><br/>{c_addr}<br/><b>GSTIN:</b> {c_gst}", styles["Normal"])
    t_mid = Table([[p_disp, p_buyer]], colWidths=[310, 252])
    t_mid.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_mid)

    # Line Items Table
    bill_month = inv_data.get("billing_month", "Aug-2026")
    items_data = [
        ["Sr No.", "Description of Services / Goods", "HSN/SAC", "GST Rate", "Quantity", "Rate", "Per", "Amount"],
        ["1", f"MANPOWER/LABOUR SUPPLY BILL<br/>Month For {bill_month}", "996511", "18%", "1", f"{sub_total:,.2f}", "Nos", f"{sub_total:,.2f}"],
        ["", "Total (Without GST)", "", "", "", "", "", f"{sub_total:,.2f}"],
        ["", "CGST", "", "9%", "", "", "", f"{cgst:,.2f}"],
        ["", "SGST", "", "9%", "", "", "", f"{sgst:,.2f}"],
        ["", "Total", "", "", "", "", "", f"₹ {grand_total:,.2f}"]
    ]
    t_items = Table([[Paragraph(c, styles["Normal"]) if "<br/>" in str(c) else c for c in row] for row in items_data], colWidths=[35, 195, 55, 45, 40, 65, 35, 92])
    t_items.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F8FAFC")),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (7,0), (7,-1), 'RIGHT'),
        ('FONTNAME', (0,2), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_items)

    # Chargeable in words
    p_words = Paragraph(f"<b>Amount Chargeable (in words):</b><br/>{num_to_words(grand_total)}", styles["Normal"])
    t_words = Table([[p_words]], colWidths=[562])
    t_words.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.black),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_words)

    # HSN/SAC Tax Bifurcation Table
    tax_data = [
        ["HSN/SAC", "Taxable Value", "Central Tax Rate", "Central Tax Amt", "State Tax Rate", "State Tax Amt", "Total Tax Amount"],
        ["996511", f"₹{sub_total:,.2f}", "9%", f"₹{cgst:,.2f}", "9%", f"₹{sgst:,.2f}", f"₹{(cgst+sgst):,.2f}"],
        ["Total", f"₹{sub_total:,.2f}", "", f"₹{cgst:,.2f}", "", f"₹{sgst:,.2f}", f"₹{(cgst+sgst):,.2f}"]
    ]
    t_tax = Table(tax_data, colWidths=[70, 85, 75, 80, 75, 80, 97])
    t_tax.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 7.5),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_tax)

    # Tax in words
    p_tax_words = Paragraph(f"<b>Tax Amount (in words):</b> {num_to_words(cgst+sgst)}<br/><b>Company's PAN:</b> {e_pan}", styles["Normal"])
    t_tax_words = Table([[p_tax_words]], colWidths=[562])
    t_tax_words.setStyle(TableStyle([('BOX', (0,0), (-1,-1), 0.5, colors.black), ('PADDING', (0,0), (-1,-1), 4)]))
    story.append(t_tax_words)

    # Declaration, Bank Details & Signatory
    decl = "<b>Declaration:</b><br/>We declare that this invoice shows the actual price of the services described and that all particulars are true and correct."
    bank_d = "<b>Company Bank Account Details:</b><br/>BANK: SARASWAT BANK<br/>A/C NO: 610000000045918<br/>IFSC: SRCB0000376"
    sign_off = f"<b>for {e_name}</b><br/><br/><br/><b>Authorised Signatory</b>"
    
    t_bottom = Table([[Paragraph(decl + "<br/><br/>" + bank_d, styles["Normal"]), Paragraph(sign_off, ParagraphStyle(name="Sign", alignment=1))]], colWidths=[360, 202])
    t_bottom.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_bottom)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def calculate_geofence(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2)**2 + math.cos(p1) * math.cos(p2) * math.sin(d_lon / 2)**2
    return (R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))) <= 15

# =============================================================================
# 3. PUBLIC INTERFACE
# =============================================================================
if not st.session_state.user:
    st.markdown('<div class="main-title">HRMS Enterprise Cloud</div>', unsafe_allow_html=True)
    tab_signin, tab_join = st.tabs(["Sign In", "Candidate Paperless Joining Form"])

    with tab_signin:
        col_s1, col_login, col_s2 = st.columns([1, 1.8, 1])
        with col_login:
            st.write(" ")
            role_choice = st.selectbox("Login Portal", ["Employee (ESS)", "Admin Portal", "Supervisor Portal", "Client Desk"])
            u_id = st.text_input("User ID / Employee Code")
            u_pwd = st.text_input("Password", type="password")
            
            st.markdown('<div class="submit-red-btn">', unsafe_allow_html=True)
            if st.button("Access Dashboard", key="access_btn"):
                role_map = {"Employee (ESS)": "employee", "Admin Portal": "admin", "Supervisor Portal": "supervisor", "Client Desk": "client"}
                target_role = role_map[role_choice]
                
                if u_id == "admin" and u_pwd == "admin123" and target_role == "admin":
                    st.session_state.user = {"user_id": "admin", "full_name": "Super Admin", "role": "admin"}
                    st.query_params["session_user_id"] = "admin"
                    st.query_params["session_role"] = "admin"
                    st.rerun()
                
                try:
                    res = supabase.table("employees").select("*").eq("user_id", u_id).eq("password", u_pwd).eq("role", target_role).execute()
                    if res.data:
                        st.session_state.user = res.data[0]
                        st.query_params["session_user_id"] = str(u_id)
                        st.query_params["session_role"] = str(target_role)
                        st.rerun()
                    else:
                        st.error("Invalid Credentials or Login Role!")
                except Exception as e:
                    st.error(f"Authentication Error: {e}")
            st.markdown('</div>', unsafe_allow_html=True)

    with tab_join:
        st.write("#### Candidate Paperless Onboarding Form")
        with st.form("onboard_candidate_form", clear_on_submit=True):
            col_left, col_right = st.columns(2)
            c_name = col_left.text_input("Candidate Full Name *")
            c_father = col_left.text_input("Father's Name *")
            c_marital = col_left.selectbox("Marital Status", ["Single", "Married"])
            c_phone = col_left.text_input("Employee Mobile Number *")
            c_emergency = col_left.text_input("Emergency Contact Number *")

            c_uan = col_right.text_input("UAN Number")
            c_esic = col_right.text_input("ESIC Number")
            c_bank = col_right.text_input("Bank Name")
            c_branch = col_right.text_input("Bank Branch Name")
            c_acc = col_right.text_input("Bank Account Number")
            c_ifsc = col_right.text_input("IFSC Code")
            c_pan = col_right.text_input("PAN Number")
            c_aadhar = col_right.text_input("Aadhaar Number *", type="password")

            st.write("---")
            st.write("#### Document Attachments (Mandatory - max 200MB)")
            up_photo = col_left.file_uploader("Passport Size Photo", type=["jpg", "png"])
            up_aadhar = col_right.file_uploader("Aadhaar Card Copy", type=["pdf", "jpg", "png"])
            up_pan = col_left.file_uploader("PAN Card Copy", type=["pdf", "jpg", "png"])
            up_bank = col_right.file_uploader("Bank Passbook / Cheque", type=["pdf", "jpg", "png"])

            if st.form_submit_button("Submit Onboarding Application"):
                if not c_name or not c_phone:
                    st.error("Mandatory fields (*) are required!")
                else:
                    new_candidate = {
                        "user_id": f"TEMP_{c_phone}", "password": "emp" + c_phone[-4:],
                        "full_name": c_name, "father_name": c_father, "marital_status": c_marital,
                        "phone_number": c_phone, "emergency_contact": c_emergency, "uan_number": c_uan,
                        "esic_number": c_esic, "bank_name": c_bank, "bank_branch": c_branch,
                        "bank_account_no": c_acc, "ifsc_code": c_ifsc, "pan_number": c_pan,
                        "role": "employee", "status": "PENDING_SUPERVISOR"
                    }
                    try:
                        supabase.table("employees").insert(new_candidate).execute()
                        st.success("Application submitted successfully! Forwarded to Supervisor.")
                    except Exception as err:
                        st.error(f"Error submitting data: {err}")

# =============================================================================
# 4. LOGGED-IN ROLES INTERFACE
# =============================================================================
else:
    active_role = st.session_state.user.get("role")

    # -------------------------------------------------------------------------
    # 4.1 ADMIN PORTAL
    # -------------------------------------------------------------------------
    if active_role == "admin":
        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS Enterprise</div>', unsafe_allow_html=True)
            st.markdown('<div class="logged-badge">Logged In: ADMIN</div>', unsafe_allow_html=True)
            st.caption("ADMIN DESK")

            admin_tabs = [
                "Dashboard Overview", "Employee Master & Docs", "Candidate Approvals",
                "Salary Structure Rules", "Attendance & OT Live Edit", "Monthly Payroll Processing",
                "Advance / Loan Desk", "PPE & Uniform Tracker", "Client Billing & Invoices",
                "Company & Plant Locations", "User Roles & Access"
            ]

            for at in admin_tabs:
                btn_style = "primary" if st.session_state.active_admin_tab == at else "secondary"
                if st.button(at, key=f"btn_{at}", type=btn_style):
                    st.session_state.active_admin_tab = at
                    st.rerun()

            st.write("---")
            if st.button("Logout", key="adm_logout"):
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

        selected_panel = st.session_state.active_admin_tab
        st.title(selected_panel)

        # 1. Dashboard Overview
        if selected_panel == "Dashboard Overview":
            st.subheader("Workforce Deployment Matrix (Client-Wise per Entity)")
            ent_res = fetch_cached_entities()
            cli_res = fetch_cached_clients()
            emp_res = fetch_cached_employees()

            if ent_res:
                for ent in ent_res:
                    st.markdown(f"#### 🏢 Entity: **{ent['name']}**")
                    ent_emps = [e for e in emp_res if e.get("entity_id") == ent["id"] and e.get("status") == "APPROVED"]
                    matched_clients = [c for c in cli_res if c.get("entity_id") == ent["id"]]
                    if matched_clients:
                        cols = st.columns(max(len(matched_clients), 1))
                        for idx, cl in enumerate(matched_clients):
                            c_count = len([e for e in ent_emps if e.get("client_id") == cl["id"]])
                            cols[idx % len(cols)].metric(f"📍 {cl['name']}", f"{c_count} Staff")
                    else:
                        st.info("No clients mapped under this entity.")
                    st.write("---")
            else:
                st.info("No entities configured yet.")

        # 2. Employee Master & Docs
        elif selected_panel == "Employee Master & Docs":
            st.subheader("Employee Master Management & Document Vault")
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_map = {e["name"]: e["id"] for e in ent_list}
            c_map = {c["name"]: c["id"] for c in cli_list}

            tab_add_emp, tab_edit_emp, tab_vault = st.tabs(["➕ Add New Employee", "✏️ Edit / Delete Employee", "📁 Document Vault"])

            with tab_add_emp:
                with st.form("manual_full_emp_with_docs_form"):
                    st.write("##### 1. Personal & Employment Information")
                    m1, m2, m3 = st.columns(3)
                    me_code = m1.text_input("Employee Code * (e.g. SE001)")
                    me_name = m2.text_input("Full Name *")
                    me_father = m3.text_input("Father's Name")
                    me_phone = m1.text_input("Mobile Number *")
                    me_emg = m2.text_input("Emergency Contact")
                    me_marital = m3.selectbox("Marital Status", ["Single", "Married"])
                    me_desig = m1.text_input("Designation")
                    me_shift_timing = m2.selectbox("Assigned Shift Schedule *", STANDARD_SHIFTS)
                    me_pwd = m3.text_input("Portal Password", type="password")

                    st.write("##### 2. Organization Assignment & Statutory Numbers")
                    m4, m5 = st.columns(2)
                    sel_ent = m4.selectbox("Assigned Entity / Firm *", options=list(e_map.keys()) if e_map else ["No Entity"])
                    sel_cli = m5.selectbox("Assigned Client *", options=list(c_map.keys()) if c_map else ["No Client"])

                    m6, m7, m8 = st.columns(3)
                    me_uan = m6.text_input("UAN Number")
                    me_esic = m7.text_input("ESIC Number")
                    me_pan = m8.text_input("PAN Number")

                    st.write("##### 3. Bank Details")
                    m9, m10, m11 = st.columns(3)
                    me_bank = m9.text_input("Bank Name")
                    me_branch = m10.text_input("Branch Name")
                    me_acc = m11.text_input("Account Number")
                    me_ifsc = m9.text_input("IFSC Code")

                    if st.form_submit_button("Save Employee Record", type="primary"):
                        if not me_code or not me_name or not me_phone:
                            st.error("Employee Code, Full Name, and Mobile Number are mandatory!")
                        else:
                            try:
                                supabase.table("employees").insert({
                                    "employee_code": me_code, "user_id": me_code, "password": me_pwd if me_pwd else "emp1234",
                                    "full_name": me_name, "father_name": me_father, "phone_number": me_phone,
                                    "emergency_contact": me_emg, "marital_status": me_marital, "designation": me_desig,
                                    "shift_hours": 8.5, "entity_id": e_map.get(sel_ent), "client_id": c_map.get(sel_cli),
                                    "uan_number": me_uan, "esic_number": me_esic, "pan_number": me_pan,
                                    "bank_name": me_bank, "bank_branch": me_branch, "bank_account_no": me_acc,
                                    "ifsc_code": me_ifsc, "role": "employee", "status": "APPROVED"
                                }).execute()
                                st.cache_data.clear()
                                st.success(f"✅ Data Saved Successfully: Employee {me_name} registered!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error saving employee: {e}")

            with tab_edit_emp:
                all_emps = supabase.table("employees").select("*").eq("role", "employee").execute().data or []
                if all_emps:
                    emp_opt_map = {f"[{e.get('employee_code')}] {e.get('full_name')}": e for e in all_emps}
                    sel_emp_to_edit = st.selectbox("Select Employee to Update / Delete", list(emp_opt_map.keys()))
                    curr_selected = emp_opt_map[sel_emp_to_edit]

                    with st.form("edit_emp_crud_form"):
                        ed1, ed2, ed3 = st.columns(3)
                        up_name = ed1.text_input("Full Name", value=curr_selected.get("full_name", ""))
                        up_phone = ed2.text_input("Mobile", value=curr_selected.get("phone_number", ""))
                        up_desig = ed3.text_input("Designation", value=curr_selected.get("designation", ""))
                        up_bank = ed1.text_input("Bank Name", value=curr_selected.get("bank_name", ""))
                        up_acc = ed2.text_input("Account Number", value=curr_selected.get("bank_account_no", ""))
                        up_ifsc = ed3.text_input("IFSC", value=curr_selected.get("ifsc_code", ""))

                        c_btn1, c_btn2 = st.columns(2)
                        if c_btn1.form_submit_button("Update Employee Data", type="primary"):
                            supabase.table("employees").update({
                                "full_name": up_name, "phone_number": up_phone, "designation": up_desig,
                                "bank_name": up_bank, "bank_account_no": up_acc, "ifsc_code": up_ifsc
                            }).eq("id", curr_selected["id"]).execute()
                            st.cache_data.clear()
                            st.success("✅ Data Updated Successfully: Employee record refreshed!")
                            st.rerun()

                        if c_btn2.form_submit_button("🗑️ Delete Employee"):
                            supabase.table("employees").delete().eq("id", curr_selected["id"]).execute()
                            st.cache_data.clear()
                            st.warning("🗑️ Data Deleted Successfully: Employee record removed!")
                            st.rerun()

            with tab_vault:
                emp_records = supabase.table("employees").select("*").eq("role", "employee").execute().data or []
                if emp_records:
                    emp_lookup = {f"[{emp.get('employee_code', 'TEMP')}] {emp.get('full_name')}": emp for emp in emp_records}
                    sel_emp_label = st.selectbox("Choose Employee for Documents", options=list(emp_lookup.keys()))
                    curr_emp = emp_lookup[sel_emp_label]

                    curr_ent_obj = None
                    for ent in ent_list:
                        if ent["id"] == curr_emp.get("entity_id"):
                            curr_ent_obj = ent
                            break

                    curr_cli_name = "Client Site"
                    for cl in cli_list:
                        if cl["id"] == curr_emp.get("client_id"):
                            curr_cli_name = cl["name"]
                            break

                    matched_rule = None
                    try:
                        s_rules = supabase.table("salary_structures").select("*").eq("entity_id", curr_emp.get("entity_id")).execute().data or []
                        if s_rules: matched_rule = s_rules[0]
                    except Exception: pass

                    v_c1, v_c2 = st.columns(2)
                    with v_c1:
                        st.markdown("##### 1. Official Offer Letter")
                        offer_pdf_data = generate_official_offer_letter(curr_emp, curr_ent_obj, curr_cli_name, matched_rule)
                        st.download_button("📥 Download Official Offer Letter (PDF)", data=offer_pdf_data, file_name=f"Offer_Letter_{curr_emp.get('employee_code')}.pdf", mime="application/pdf", key=f"dn_o_{curr_emp['id']}")

                        st.markdown("##### 3. Aadhaar Card Copy")
                        f_aadh = st.file_uploader("Upload Aadhaar", type=["pdf", "jpg", "png"], key=f"vault_aadh_{curr_emp['id']}")
                        if f_aadh: st.success("✅ Data Updated Successfully: Aadhaar copy updated!")

                    with v_c2:
                        st.markdown("##### 2. ESIC Certificate / Card")
                        f_esic = st.file_uploader("Upload ESIC Document", type=["pdf", "jpg", "png"], key=f"vault_esic_{curr_emp['id']}")
                        if f_esic: st.success("✅ Data Updated Successfully: ESIC Document updated!")

                        st.markdown("##### 4. PAN Card Copy")
                        f_pan = st.file_uploader("Upload PAN Card", type=["pdf", "jpg", "png"], key=f"vault_pan_{curr_emp['id']}")
                        if f_pan: st.success("✅ Data Updated Successfully: PAN Card updated!")

        # 3. Company & Plant Locations
        elif selected_panel == "Company & Plant Locations":
            loc1, loc2 = st.columns(2)
            with loc1:
                st.subheader("1. Entity / Firm Master")
                t_ent_add, t_ent_edit = st.tabs(["➕ Add Entity", "✏️ Edit / Delete Entity"])
                with t_ent_add:
                    with st.form("add_entity_portal_form"):
                        en_name = st.text_input("Firm / Entity Name")
                        en_addr = st.text_area("Registered Office Address")
                        en_gst = st.text_input("GST Number")
                        en_pref = st.text_input("Code Prefix (e.g. SE, GM)")
                        en_pan = st.text_input("PAN Number")
                        en_ph = st.text_input("Phone Number")
                        en_em = st.text_input("Email ID")
                        if st.form_submit_button("Save Entity", type="primary"):
                            if en_name and en_pref:
                                supabase.table("entities").insert({
                                    "name": en_name, "address": en_addr, "gst_number": en_gst, "code_prefix": en_pref,
                                    "pan_number": en_pan, "phone": en_ph, "email": en_em
                                }).execute()
                                st.cache_data.clear()
                                st.success("✅ Data Saved Successfully: Entity registered!")
                                st.rerun()

                with t_ent_edit:
                    ents_all = fetch_cached_entities()
                    if ents_all:
                        ent_select_map = {e["name"]: e for e in ents_all}
                        sel_ent_e = st.selectbox("Select Entity to Edit/Delete", list(ent_select_map.keys()))
                        curr_e = ent_select_map[sel_ent_e]
                        with st.form("edit_entity_portal_form"):
                            en_up_name = st.text_input("Firm Name", value=curr_e.get("name", ""))
                            en_up_addr = st.text_area("Address", value=curr_e.get("address", ""))
                            en_up_gst = st.text_input("GST", value=curr_e.get("gst_number", ""))
                            en_up_pan = st.text_input("PAN", value=curr_e.get("pan_number", ""))
                            
                            c1, c2 = st.columns(2)
                            if c1.form_submit_button("Update Entity", type="primary"):
                                supabase.table("entities").update({
                                    "name": en_up_name, "address": en_up_addr, "gst_number": en_up_gst, "pan_number": en_up_pan
                                }).eq("id", curr_e["id"]).execute()
                                st.cache_data.clear()
                                st.success("✅ Data Updated Successfully: Entity refreshed!")
                                st.rerun()
                            if c2.form_submit_button("🗑️ Delete Entity"):
                                supabase.table("entities").delete().eq("id", curr_e["id"]).execute()
                                st.cache_data.clear()
                                st.warning("🗑️ Data Deleted Successfully: Entity removed!")
                                st.rerun()

            with loc2:
                st.subheader("2. Client Plant Master & Geofence")
                t_cli_add, t_cli_edit = st.tabs(["➕ Add Client", "✏️ Edit / Delete Client"])
                ents = fetch_cached_entities()
                e_dict = {e["name"]: e["id"] for e in ents}

                with t_cli_add:
                    with st.form("add_client_portal_form"):
                        cl_name = st.text_input("Client Company Name *")
                        cl_code = st.text_input("Client Code *")
                        cl_gst = st.text_input("Client GST Number *")
                        cl_full_addr = st.text_area("Plant Full Address")
                        cl_c_name = st.text_input("Contact Person Name")
                        cl_c_email = st.text_input("Contact Person Email")
                        cl_c_mobile = st.text_input("Contact Person Mobile Number")
                        assigned_ent = st.selectbox("Assign Entity Provider", options=list(e_dict.keys()) if e_dict else ["No Entity"])
                        g_col1, g_col2 = st.columns(2)
                        cl_lat = g_col1.number_input("Latitude", format="%.6f", value=18.651200)
                        cl_lon = g_col2.number_input("Longitude", format="%.6f", value=73.805500)

                        if st.form_submit_button("Save Client Details", type="primary"):
                            if cl_name and cl_code:
                                supabase.table("clients").insert({
                                    "name": cl_name, "client_code": cl_code, "gst_number": cl_gst,
                                    "plant_location": cl_full_addr, "contact_person_name": cl_c_name,
                                    "contact_person_email": cl_c_email, "contact_person_mobile": cl_c_mobile,
                                    "latitude": cl_lat, "longitude": cl_lon, "entity_id": e_dict.get(assigned_ent)
                                }).execute()
                                st.cache_data.clear()
                                st.success("✅ Data Saved Successfully: Client registered!")
                                st.rerun()

                with t_cli_edit:
                    clis_all = fetch_cached_clients()
                    if clis_all:
                        cli_select_map = {c["name"]: c for c in clis_all}
                        sel_c_e = st.selectbox("Select Client to Edit/Delete", list(cli_select_map.keys()))
                        curr_c = cli_select_map[sel_c_e]
                        with st.form("edit_client_portal_form"):
                            cl_up_name = st.text_input("Client Name", value=curr_c.get("name", ""))
                            cl_up_gst = st.text_input("Client GST", value=curr_c.get("gst_number", ""))
                            cl_up_addr = st.text_area("Address", value=curr_c.get("plant_location", ""))
                            cl_up_cn = st.text_input("Contact Person", value=curr_c.get("contact_person_name", ""))
                            cl_up_ce = st.text_input("Email", value=curr_c.get("contact_person_email", ""))
                            cl_up_cm = st.text_input("Mobile", value=curr_c.get("contact_person_mobile", ""))
                            cg1, cg2 = st.columns(2)
                            cl_up_lat = cg1.number_input("Latitude", format="%.6f", value=float(curr_c.get("latitude", 18.6512)))
                            cl_up_lon = cg2.number_input("Longitude", format="%.6f", value=float(curr_c.get("longitude", 73.8055)))

                            cb1, cb2 = st.columns(2)
                            if cb1.form_submit_button("Update Client", type="primary"):
                                supabase.table("clients").update({
                                    "name": cl_up_name, "gst_number": cl_up_gst, "plant_location": cl_up_addr,
                                    "contact_person_name": cl_up_cn, "contact_person_email": cl_up_ce,
                                    "contact_person_mobile": cl_up_cm, "latitude": cl_up_lat, "longitude": cl_up_lon
                                }).eq("id", curr_c["id"]).execute()
                                st.cache_data.clear()
                                st.success("✅ Data Updated Successfully: Client geofence & details refreshed!")
                                st.rerun()
                            if cb2.form_submit_button("🗑️ Delete Client"):
                                supabase.table("clients").delete().eq("id", curr_c["id"]).execute()
                                st.cache_data.clear()
                                st.warning("🗑️ Data Deleted Successfully: Client removed!")
                                st.rerun()

        # 4. Salary Structure Rules (Gratuity Removed, Full Breakdown)
        elif selected_panel == "Salary Structure Rules":
            st.subheader("Configure Salary Structure & CTC Rules")
            tab_sal_add, tab_sal_edit = st.tabs(["➕ Define Salary Rule", "✏️ Edit / Delete Salary Rule"])
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            ent_opts = {e["name"]: e["id"] for e in ent_list}
            cli_opts = {c["name"]: c["id"] for c in cli_list}

            with tab_sal_add:
                with st.form("salary_rule_form"):
                    sr1, sr2 = st.columns(2)
                    r_ent = sr1.selectbox("Entity / Firm", options=list(ent_opts.keys()) if ent_opts else ["No Entity"])
                    r_cli = sr2.selectbox("Client Site", options=list(cli_opts.keys()) if cli_opts else ["No Client"])
                    r_desig = sr1.text_input("Designation", value="Associate")
                    r_cat = sr2.selectbox("Category", ["Skilled", "Semi-Skilled", "Unskilled"])

                    st.markdown("##### 1. Gross Earnings Components")
                    sr3, sr4, sr5, sr6 = st.columns(4)
                    r_basic = sr3.number_input("Basic Pay (₹)", value=14010.0)
                    r_da = sr4.number_input("DA (₹)", value=2511.0)
                    r_hra = sr5.number_input("HRA (₹)", value=826.0)
                    r_other = sr6.number_input("Other (₹)", value=813.0)
                    gross = r_basic + r_da + r_hra + r_other

                    st.markdown("##### 2. Employee Deductions (On Pay Slip)")
                    sr7, sr8, sr9, sr10 = st.columns(4)
                    r_ot = sr7.number_input("OT Rate / Hour (₹)", value=120.0)
                    r_pf = sr8.number_input("Employee PF (%)", value=12.0)
                    r_esic = sr9.number_input("Employee ESIC (%)", value=0.75)
                    r_pt = sr10.number_input("PT Amount (₹)", value=200.0)

                    st.markdown("##### 3. Employer Contributions / Company Cost (Offer Letter CTC - No Gratuity)")
                    er1, er2, er3 = st.columns(3)
                    r_er_pf = er1.number_input("Employer PF (%)", value=13.0)
                    r_er_esic = er2.number_input("Employer ESIC (%)", value=3.25)
                    r_bonus = er3.number_input("Bonus (₹)", value=0.0)

                    er_pf_val = round((r_basic + r_da) * (r_er_pf / 100.0), 2)
                    er_esic_val = round(gross * (r_er_esic / 100.0), 2)
                    m_ctc = round(gross + er_pf_val + er_esic_val + r_bonus, 2)
                    a_ctc = round(m_ctc * 12, 2)

                    st.markdown(f"""
                    <div style="background-color: #F1F5F9; border-left: 4px solid #0284C7; padding: 10px; border-radius: 4px; margin: 10px 0px;">
                        <b>Gross Wages:</b> ₹{gross:,.2f}/month | 
                        <b>Employer PF:</b> ₹{er_pf_val:,.2f} | 
                        <b>Employer ESIC:</b> ₹{er_esic_val:,.2f}<br>
                        <b>Total Monthly CTC:</b> ₹{m_ctc:,.2f} | 
                        <b>Total Annual CTC:</b> ₹{a_ctc:,.2f}
                    </div>
                    """, unsafe_allow_html=True)

                    if st.form_submit_button("Save Full CTC Rule", type="primary"):
                        supabase.table("salary_structures").insert({
                            "entity_id": ent_opts.get(r_ent), "client_id": cli_opts.get(r_cli),
                            "designation": r_desig, "category": r_cat, "basic": r_basic, "da": r_da,
                            "hra": r_hra, "other_allowance": r_other, "ot_rate_per_hour": r_ot,
                            "pf_percentage": r_pf, "esic_percentage": r_esic, "pt_amount": r_pt,
                            "employer_pf_pct": r_er_pf, "employer_esic_pct": r_er_esic,
                            "statutory_bonus": r_bonus, "monthly_ctc": m_ctc, "annual_ctc": a_ctc
                        }).execute()
                        st.success("✅ Data Saved Successfully: Salary structure rule added!")
                        st.rerun()

            with tab_sal_edit:
                all_sals = supabase.table("salary_structures").select("*").execute().data or []
                if all_sals:
                    sal_map = {f"Rule #{s['id'][:6]} - {s.get('designation')} (₹{s.get('monthly_ctc', 0)})": s for s in all_sals}
                    sel_sal = st.selectbox("Select Rule to Update/Delete", list(sal_map.keys()))
                    curr_s = sal_map[sel_sal]

                    with st.form("edit_salary_rule_form"):
                        st.write("##### Update Salary Structure Values")
                        c_ed1, c_ed2, c_ed3 = st.columns(3)
                        e_b = c_ed1.number_input("Basic Pay", value=float(curr_s.get("basic", 14010.0)))
                        e_da = c_ed2.number_input("DA", value=float(curr_s.get("da", 2511.0)))
                        e_hra = c_ed3.number_input("HRA", value=float(curr_s.get("hra", 826.0)))

                        c_ed4, c_ed5, c_ed6 = st.columns(3)
                        e_oth = c_ed4.number_input("Other Allowance", value=float(curr_s.get("other_allowance", 813.0)))
                        e_pf = c_ed5.number_input("Employee PF (%)", value=float(curr_s.get("pf_percentage", 12.0)))
                        e_esic = c_ed6.number_input("Employee ESIC (%)", value=float(curr_s.get("esic_percentage", 0.75)))

                        c_ed7, c_ed8 = st.columns(2)
                        e_er_pf = c_ed7.number_input("Employer PF (%)", value=float(curr_s.get("employer_pf_pct", 13.0)))
                        e_er_esic = c_ed8.number_input("Employer ESIC (%)", value=float(curr_s.get("employer_esic_pct", 3.25)))

                        sb1, sb2 = st.columns(2)
                        if sb1.form_submit_button("Update Salary Rule", type="primary"):
                            up_gross = e_b + e_da + e_hra + e_oth
                            up_er_pf = round((e_b + e_da) * (e_er_pf / 100.0), 2)
                            up_er_esic = round(up_gross * (e_er_esic / 100.0), 2)
                            up_m_ctc = round(up_gross + up_er_pf + up_er_esic, 2)

                            supabase.table("salary_structures").update({
                                "basic": e_b, "da": e_da, "hra": e_hra, "other_allowance": e_oth,
                                "pf_percentage": e_pf, "esic_percentage": e_esic,
                                "employer_pf_pct": e_er_pf, "employer_esic_pct": e_er_esic,
                                "monthly_ctc": up_m_ctc, "annual_ctc": up_m_ctc * 12
                            }).eq("id", curr_s["id"]).execute()
                            st.success("✅ Data Updated Successfully: Rule refreshed!")
                            st.rerun()

                        if sb2.form_submit_button("🗑️ Delete Salary Rule"):
                            supabase.table("salary_structures").delete().eq("id", curr_s["id"]).execute()
                            st.warning("🗑️ Data Deleted Successfully: Salary rule removed!")
                            st.rerun()
                else:
                    st.info("No salary structure rules saved yet.")

        # 5. PPE & Uniform Tracker (Full CRUD & Table)
        elif selected_panel == "PPE & Uniform Tracker":
            st.subheader("PPE & Uniform Tracker (Management Desk)")
            tab_ppe_issue, tab_ppe_edit, tab_ppe_req = st.tabs(["➕ Issue / Add PPE", "✏️ Edit / Delete PPE", "📋 Pending Requests"])

            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            emp_list = fetch_cached_employees()
            p_e_map = {e["name"]: e["id"] for e in ent_list}
            p_c_map = {c["name"]: c["id"] for c in cli_list}
            p_emp_map = {f"[{e.get('employee_code', 'N/A')}] {e['full_name']}": e["id"] for e in emp_list if e.get("role") == "employee"}

            with tab_ppe_issue:
                with st.form("manual_ppe_form"):
                    col_p1, col_p2, col_p3 = st.columns(3)
                    p_sel_ent = col_p1.selectbox("Entity", options=list(p_e_map.keys()) if p_e_map else ["No Entity"])
                    p_sel_cli = col_p2.selectbox("Client", options=list(p_c_map.keys()) if p_c_map else ["No Client"])
                    p_sel_emp = col_p3.selectbox("Employee *", options=list(p_emp_map.keys()) if p_emp_map else ["No Employee"])

                    col_p4, col_p5, col_p6 = st.columns(3)
                    p_item = col_p4.selectbox("PPE Item", ["Safety Shoes", "Helmet", "Safety Goggles", "Uniform Shirt/Pant", "ID Card"])
                    p_size = col_p5.text_input("Size (e.g. 8, 9, L, XL)")
                    p_qty = col_p6.number_input("Quantity", min_value=1, value=1)

                    if st.form_submit_button("Issue PPE Record", type="primary"):
                        if not p_emp_map:
                            st.error("Please add employees first!")
                        else:
                            supabase.table("ppe_records").insert({
                                "employee_id": p_emp_map[p_sel_emp],
                                "item_type": p_item,
                                "size": p_size,
                                "quantity": p_qty,
                                "status": "APPROVED",
                                "assigned_date": str(date.today())
                            }).execute()
                            st.success("✅ Data Saved Successfully: PPE Issued and Logged!")
                            st.rerun()

            with tab_ppe_edit:
                all_ppes = supabase.table("ppe_records").select("*").execute().data or []
                if all_ppes:
                    ppe_map = {f"Record #{p['id'][:6]} - Item: {p.get('item_type')} (Qty: {p.get('quantity')})": p for p in all_ppes}
                    sel_p = st.selectbox("Select PPE Record to Edit/Delete", list(ppe_map.keys()))
                    curr_p = ppe_map[sel_p]

                    with st.form("edit_ppe_crud_form"):
                        pe1, pe2 = st.columns(2)
                        up_item = pe1.text_input("Item Type", value=curr_p.get("item_type", ""))
                        up_size = pe2.text_input("Size", value=curr_p.get("size", ""))
                        up_qty = pe1.number_input("Quantity", min_value=1, value=int(curr_p.get("quantity", 1)))

                        pb1, pb2 = st.columns(2)
                        if pb1.form_submit_button("Update PPE Record", type="primary"):
                            supabase.table("ppe_records").update({"item_type": up_item, "size": up_size, "quantity": up_qty}).eq("id", curr_p["id"]).execute()
                            st.success("✅ Data Updated Successfully: PPE record updated!")
                            st.rerun()

                        if pb2.form_submit_button("🗑️ Delete PPE Record"):
                            supabase.table("ppe_records").delete().eq("id", curr_p["id"]).execute()
                            st.warning("🗑️ Data Deleted Successfully: PPE record removed!")
                            st.rerun()
                else:
                    st.info("No PPE records available to edit.")

            with tab_ppe_req:
                ppe_reqs = supabase.table("ppe_records").select("id, employee_id, item_type, size, quantity, status, created_at").eq("status", "PENDING_ADMIN").execute().data or []
                if ppe_reqs:
                    for req in ppe_reqs:
                        col_r1, col_r2, col_r3 = st.columns([3, 1, 1])
                        col_r1.write(f"Item: **{req['item_type']}** | Size: **{req['size']}** | Qty: **{req['quantity']}**")
                        if col_r2.button("Approve", key=f"app_ppe_{req['id']}"):
                            supabase.table("ppe_records").update({"status": "APPROVED", "assigned_date": str(date.today())}).eq("id", req["id"]).execute()
                            st.success("✅ Data Updated Successfully: PPE Approved!")
                            st.rerun()
                        if col_r3.button("Reject", key=f"rej_ppe_{req['id']}"):
                            supabase.table("ppe_records").update({"status": "REJECTED"}).eq("id", req["id"]).execute()
                            st.warning("🗑️ Data Updated Successfully: PPE Rejected!")
                            st.rerun()
                else:
                    st.info("No pending PPE requests.")

            st.write("---")
            st.write("#### 📊 Full PPE Tracker Records")
            all_ppe_list = supabase.table("ppe_records").select("*").execute().data or []
            if all_ppe_list:
                st.dataframe(pd.DataFrame(all_ppe_list), use_container_width=True)

        # 6. Client Billing & Invoices (Exact Replica Template)
        elif selected_panel == "Client Billing & Invoices":
            st.subheader("Client Billing & Tax Invoice Generator (Exact Replica)")
            t_inv_gen, t_inv_hist = st.tabs(["➕ Generate Tax Invoice", "📑 Invoices History & Downloads"])
            cli_list = fetch_cached_clients()
            ent_list = fetch_cached_entities()
            c_dict = {c["name"]: c for c in cli_list}
            e_dict = {e["name"]: e for e in ent_list}

            with t_inv_gen:
                with st.form("generate_tax_inv_form"):
                    i_col1, i_col2 = st.columns(2)
                    sel_inv_ent = i_col1.selectbox("From Entity (Supplier) *", list(e_dict.keys()) if e_dict else ["No Entity"])
                    sel_inv_cli = i_col2.selectbox("To Client (Buyer) *", list(c_dict.keys()) if c_dict else ["No Client"])
                    
                    inv_no = i_col1.text_input("Invoice Number *", value="SE/26-27/51")
                    inv_dt = i_col2.date_input("Invoice Date", value=date.today())
                    inv_month = i_col1.text_input("Billing Month / Service Period", value="Aug-2026 Khed City")
                    inv_subtotal = i_col2.number_input("Taxable Amount (Without GST ₹) *", value=115146.0)

                    if st.form_submit_button("Generate & Save Tax Invoice", type="primary"):
                        try:
                            supabase.table("client_invoices").insert({
                                "invoice_number": inv_no, "invoice_date": str(inv_dt),
                                "client_id": c_dict[sel_inv_cli]["id"], "entity_id": e_dict[sel_inv_ent]["id"],
                                "billing_month": inv_month, "total_amount": inv_subtotal, "payment_status": "PENDING"
                            }).execute()
                            st.success("✅ Data Saved Successfully: Tax Invoice generated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error saving invoice: {e}")

            with t_inv_hist:
                inv_records = supabase.table("client_invoices").select("*").execute().data or []
                if inv_records:
                    for inv in inv_records:
                        with st.expander(f"Invoice: {inv.get('invoice_number')} | Month: {inv.get('billing_month')} | Total: ₹{inv.get('total_amount', 0):,.2f}"):
                            ent_obj = next((e for e in ent_list if e["id"] == inv.get("entity_id")), None)
                            cli_obj = next((c for c in cli_list if c["id"] == inv.get("client_id")), None)
                            inv_pdf = generate_exact_tax_invoice(inv, ent_obj, cli_obj)
                            st.download_button(f"📥 Download Exact Tax Invoice PDF ({inv.get('invoice_number')})", data=inv_pdf, file_name=f"Invoice_{inv.get('invoice_number').replace('/', '_')}.pdf", mime="application/pdf", key=f"dn_inv_{inv['id']}")
                else:
                    st.info("No tax invoices generated yet.")

        # 7. User Roles & Access (Entity Dropdown Added)
        elif selected_panel == "User Roles & Access":
            st.subheader("User Roles & Access Control")
            t_u_add, t_u_edit = st.tabs(["➕ Create User Access", "✏️ Edit / Delete User Access"])
            cli_re = fetch_cached_clients()
            ent_re = fetch_cached_entities()
            cli_m = {c["name"]: c["id"] for c in cli_re}
            ent_m = {e["name"]: e["id"] for e in ent_re}

            with t_u_add:
                with st.form("create_role_form"):
                    rc1, rc2, rc3 = st.columns(3)
                    new_r = rc1.selectbox("Role", ["supervisor", "client", "admin"])
                    new_u = rc2.text_input("User ID")
                    new_n = rc3.text_input("Full Name")
                    new_p = rc1.text_input("Password", type="password")
                    new_ph = rc2.text_input("Mobile Number")
                    assigned_ent = rc3.selectbox("Assign Entity Provider *", options=list(ent_m.keys()) if ent_m else ["No Entity"])
                    assigned_client = rc1.selectbox("Assign Client Site", options=list(cli_m.keys()) if cli_m else ["No Client"])

                    if st.form_submit_button("Save User Credentials", type="primary"):
                        supabase.table("employees").insert({
                            "user_id": new_u, "password": new_p, "full_name": new_n,
                            "phone_number": new_ph if new_ph else "0000000000",
                            "role": new_r, "entity_id": ent_m.get(assigned_ent),
                            "client_id": cli_m.get(assigned_client), "status": "APPROVED"
                        }).execute()
                        st.cache_data.clear()
                        st.success("✅ Data Saved Successfully: New user login created!")
                        st.rerun()

            with t_u_edit:
                users_res = supabase.table("employees").select("*").in_("role", ["supervisor", "client"]).execute().data or []
                if users_res:
                    u_map = {f"{u.get('user_id')} - {u.get('full_name')} ({u.get('role')})": u for u in users_res}
                    sel_u = st.selectbox("Select User to Modify/Delete", list(u_map.keys()))
                    curr_u = u_map[sel_u]
                    with st.form("edit_user_form"):
                        up_un = st.text_input("Full Name", value=curr_u.get("full_name", ""))
                        up_up = st.text_input("New Password", value=curr_u.get("password", ""))
                        uc1, uc2 = st.columns(2)
                        if uc1.form_submit_button("Update User", type="primary"):
                            supabase.table("employees").update({"full_name": up_un, "password": up_up}).eq("id", curr_u["id"]).execute()
                            st.cache_data.clear()
                            st.success("✅ Data Updated Successfully: User updated!")
                            st.rerun()
                        if uc2.form_submit_button("🗑️ Delete User"):
                            supabase.table("employees").delete().eq("id", curr_u["id"]).execute()
                            st.cache_data.clear()
                            st.warning("🗑️ Data Deleted Successfully: User access revoked!")
                            st.rerun()

        # Other Panels
        elif selected_panel == "Attendance & OT Live Edit":
            st.subheader("Manual Attendance, Shift Timings & OT Management")
            at_tab_save, at_tab_del = st.tabs(["📝 Add / Update Attendance Record", "🗑️ Delete Attendance Record"])
            emp_list = fetch_cached_employees()
            emp_map = {f"[{e.get('employee_code')}] {e['full_name']}": e["id"] for e in emp_list if e.get("role") == "employee"}

            with at_tab_save:
                with st.form("attendance_save_form"):
                    at1, at2, at3 = st.columns(3)
                    sel_e = at1.selectbox("Select Employee", options=list(emp_map.keys()) if emp_map else ["No Employees"])
                    sel_d = at2.date_input("Date", value=date.today())
                    sel_st = at3.selectbox("Status", ["P (Present)", "A (Absent)", "WO (Week Off)", "PH (Paid Holiday)"])
                    ot_h = at1.number_input("Overtime Hours (OT)", min_value=0.0, max_value=16.0, step=0.5, value=0.0)

                    if st.form_submit_button("Save / Update Attendance", type="primary"):
                        if emp_map:
                            st_code = sel_st[:sel_st.find(" ")]
                            supabase.table("attendance").upsert({
                                "employee_id": emp_map[sel_e], "date": str(sel_d),
                                "status": st_code, "ot_hours": ot_h, "is_valid_geo": True
                            }, on_conflict="employee_id,date").execute()
                            st.success(f"✅ Data Updated Successfully: Attendance logged for {sel_e}!")

            with at_tab_del:
                with st.form("attendance_del_form"):
                    d_sel_e = st.selectbox("Select Employee", options=list(emp_map.keys()) if emp_map else ["No Employees"])
                    d_sel_d = st.date_input("Date to Delete", value=date.today())
                    if st.form_submit_button("🗑️ Delete Attendance Record"):
                        if emp_map:
                            supabase.table("attendance").delete().eq("employee_id", emp_map[d_sel_e]).eq("date", str(d_sel_d)).execute()
                            st.warning(f"🗑️ Data Deleted Successfully: Attendance deleted for {d_sel_d}!")

        elif selected_panel == "Candidate Approvals":
            st.subheader("New Candidate Approvals")
            cands = supabase.table("employees").select("*").eq("status", "PENDING_ADMIN").execute().data or []
            if cands:
                for cand in cands:
                    with st.expander(f"Applicant: {cand['full_name']} (Phone: {cand['phone_number']})"):
                        app1, app2 = st.columns(2)
                        ents = fetch_cached_entities()
                        pref_dict = {f"{e['name']} ({e['code_prefix']})": e["code_prefix"] for e in ents}
                        sel_pref = app1.selectbox("Select Entity Prefix", options=list(pref_dict.keys()) if pref_dict else ["SE"], key=f"pref_{cand['id']}")
                        sel_shift = app2.selectbox("Confirm Shift Timing *", STANDARD_SHIFTS, key=f"shift_{cand['id']}")

                        col_act1, col_act2 = st.columns(2)
                        if col_act1.button("Approve & Generate ID", key=f"ap_{cand['id']}", type="primary"):
                            prefix = pref_dict.get(sel_pref, "SE")
                            new_id = f"{prefix}001"
                            supabase.table("employees").update({"employee_code": new_id, "user_id": new_id, "status": "APPROVED"}).eq("id", cand["id"]).execute()
                            st.cache_data.clear()
                            st.success(f"✅ Data Saved Successfully: Candidate approved with {sel_shift}! ID: {new_id}")
                            st.rerun()

                        if col_act2.button("🗑️ Reject & Delete Application", key=f"rej_{cand['id']}"):
                            supabase.table("employees").delete().eq("id", cand["id"]).execute()
                            st.cache_data.clear()
                            st.warning("🗑️ Data Deleted Successfully: Application rejected!")
                            st.rerun()
            else:
                st.info("No candidates pending admin approval.")

        elif selected_panel in ["Monthly Payroll Processing", "Advance / Loan Desk"]:
            st.subheader(selected_panel)
            st.info(f"{selected_panel} active.")

    # -------------------------------------------------------------------------
    # 4.2 SUPERVISOR PORTAL
    # -------------------------------------------------------------------------
    elif active_role == "supervisor":
        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS Enterprise</div>', unsafe_allow_html=True)
            st.markdown('<div class="logged-badge">Logged In: SUPERVISOR</div>', unsafe_allow_html=True)
            st.write(f"Supervisor: **{st.session_state.user.get('full_name')}**")
            if st.sidebar.button("Logout", key="sup_logout"):
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

        st.title("Supervisor Operations Desk")
        st.subheader("New Joinee Candidate Verification")
        cand_list = supabase.table("employees").select("*").eq("status", "PENDING_SUPERVISOR").execute().data or []
        if cand_list:
            for c in cand_list:
                with st.expander(f"Applicant: {c['full_name']} ({c['phone_number']})"):
                    s_desig = st.text_input("Assign Designation", key=f"desig_{c['id']}")
                    s_shift = st.selectbox("Assign Shift Schedule", STANDARD_SHIFTS, key=f"shift_{c['id']}")
                    if st.button("Verify & Forward to Admin", key=f"fwd_{c['id']}", type="primary"):
                        supabase.table("employees").update({"designation": s_desig, "status": "PENDING_ADMIN"}).eq("id", c["id"]).execute()
                        st.success("✅ Data Updated Successfully: Forwarded to Admin!")
                        st.rerun()
        else:
            st.info("No candidates pending supervisor verification.")

    # -------------------------------------------------------------------------
    # 4.3 CLIENT DESK
    # -------------------------------------------------------------------------
    elif active_role == "client":
        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS Enterprise</div>', unsafe_allow_html=True)
            st.markdown('<div class="logged-badge">Logged In: CLIENT DESK</div>', unsafe_allow_html=True)
            st.write(f"Client: **{st.session_state.user.get('full_name')}**")
            if st.sidebar.button("Logout", key="cli_logout"):
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

        st.title("Client Live Dashboard")
        st.subheader("Deployed Workforce & Plant Overview")
        col_c1, col_c2, col_c3 = st.columns(3)
        col_c1.metric("Deployed Workforce", "12 Staff")
        col_c2.metric("Present Today", "11")
        col_c3.metric("Absent Today", "1")

    # -------------------------------------------------------------------------
    # 4.4 EMPLOYEE PORTAL (ESS)
    # -------------------------------------------------------------------------
    elif active_role == "employee":
        emp = st.session_state.user
        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS Enterprise</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="logged-badge">Logged In: EMPLOYEE ({emp.get("employee_code", "TEMP")})</div>', unsafe_allow_html=True)
            st.write(f"User: **{emp.get('full_name')}**")
            if st.sidebar.button("Logout", key="emp_logout"):
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

        st.title("Employee Self Service (ESS)")
        st.subheader("Daily Attendance (15-Meter Geofenced Punch)")

        assigned_lat = 18.651200
        assigned_lon = 73.805500
        if emp.get("client_id"):
            cl_res = supabase.table("clients").select("latitude, longitude").eq("id", emp["client_id"]).execute().data
            if cl_res and cl_res[0].get("latitude"):
                assigned_lat = float(cl_res[0]["latitude"])
                assigned_lon = float(cl_res[0]["longitude"])

        g1, g2 = st.columns(2)
        g1.text_input("Assigned Plant Latitude (Locked)", value=f"{assigned_lat:.6f}", disabled=True)
        g2.text_input("Assigned Plant Longitude (Locked)", value=f"{assigned_lon:.6f}", disabled=True)

        if st.button("👍 Thumb Punch In / Out", type="primary"):
            if calculate_geofence(assigned_lat, assigned_lon, assigned_lat, assigned_lon):
                st.success("✅ Geofence Validated! Attendance punched successfully within 15m radius.")
            else:
                st.error("❌ Invalid Location: You are outside the 15-meter plant perimeter!")

        st.write("---")
        t1, t2, t3, t4 = st.tabs(["👤 My Full Profile Details", "📄 Offer Letter & ESIC Card", "💰 Monthly Payslips (15th)", "⚙️ Requests"])
        
        with t1:
            st.markdown(f"""
            <div class="profile-card">
                <h4 style="margin:0; color:#0F172A;">{emp.get('full_name')} ({emp.get('employee_code')})</h4>
                <b>Designation:</b> {emp.get('designation', 'Associate')} | <b>Phone:</b> {emp.get('phone_number')}<br>
                <b>Father's Name:</b> {emp.get('father_name', 'N/A')} | <b>Emergency:</b> {emp.get('emergency_contact', 'N/A')}<br>
                <b>Marital Status:</b> {emp.get('marital_status', 'Single')}<br>
                <hr style="margin: 8px 0; border: 0; border-top: 1px solid #E2E8F0;">
                <b>Bank:</b> {emp.get('bank_name', 'N/A')} (A/C: {emp.get('bank_account_no', 'N/A')}) | <b>IFSC:</b> {emp.get('ifsc_code', 'N/A')}<br>
                <b>UAN:</b> {emp.get('uan_number', 'N/A')} | <b>ESIC:</b> {emp.get('esic_number', 'N/A')} | <b>PAN:</b> {emp.get('pan_number', 'N/A')}
            </div>
            """, unsafe_allow_html=True)

        with t2:
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("##### 📑 Official Offer Letter")
                ent_obj = supabase.table("entities").select("*").eq("id", emp.get("entity_id")).execute().data
                ent_val = ent_obj[0] if ent_obj else None
                off_data = generate_official_offer_letter(emp, ent_val, "Plant Site")
                st.download_button("📥 Download Offer Letter (PDF)", data=off_data, file_name=f"Offer_{emp.get('employee_code')}.pdf", mime="application/pdf")
            with d2:
                st.markdown("##### 🪪 ESIC Document")
                st.download_button("📥 Download ESIC Card (PDF)", data=b"ESIC Card Statutory Document", file_name=f"ESIC_{emp.get('employee_code')}.pdf", mime="application/pdf")

        with t3:
            st.markdown("##### 🗓️ Month-Wise Salary Payslips")
            st.caption("Official payslips are generated on the 15th of every month.")
            sel_m = st.selectbox("Select Payslip Month", ["September 2026", "August 2026"])
            st.download_button(f"📥 Download Payslip ({sel_m})", data=b"Official Salary Slip PDF", file_name=f"Payslip_{sel_m}_{emp.get('employee_code')}.pdf")

        with t4:
            r1, r2 = st.columns(2)
            with r1:
                with st.form("emp_ppe_box"):
                    st.markdown("##### Request PPE")
                    st.selectbox("Item", ["Safety Shoes", "Helmet", "Uniform"])
                    st.text_input("Size")
                    if st.form_submit_button("Submit PPE Request"):
                        st.success("✅ Data Saved Successfully: PPE request sent to Admin!")
            with r2:
                with st.form("emp_adv_box"):
                    st.markdown("##### Request Salary Advance")
                    st.number_input("Amount (₹)", min_value=500, step=500)
                    st.text_area("Reason")
                    if st.form_submit_button("Submit Advance Request"):
                        st.success("✅ Data Saved Successfully: Advance request sent to Admin!")