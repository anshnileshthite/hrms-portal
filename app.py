import streamlit as st
import pandas as pd
import urllib.parse
import io
import os
import math
import re
import time as pytime
from datetime import date, datetime, time, timedelta
from database import supabase

# ReportLab Libraries for PDF Generation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak, Preformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -------------------------------------------------------------
# 1. PAGE CONFIGURATION & CACHING
# -------------------------------------------------------------
st.set_page_config(page_title="ESS PORTAL | HRMS ENTERPRISE", layout="wide")

@st.cache_data(ttl=60)
def fetch_cached_entities():
    try:
        return supabase.table("entities").select("*").execute().data or []
    except Exception:
        return []

@st.cache_data(ttl=60)
def fetch_cached_clients():
    try:
        return supabase.table("clients").select("*").execute().data or []
    except Exception:
        return []

@st.cache_data(ttl=30)
def fetch_cached_employees():
    try:
        return supabase.table("employees").select("*").execute().data or []
    except Exception:
        return []

# Custom CSS Styling: Modern Enterprise Color Palette (#1E3A8A / #0F172A / #059669) & Strict 2MB File Label Replacement
st.markdown("""
    <style>
    .main-title { font-size: 26px; font-weight: 800; color: #0F172A; margin-bottom: 12px; }
    .stTabs [data-baseweb="tab-list"] { gap: 15px; }
    .stTabs [data-baseweb="tab"] { font-size: 14px; color: #475569; padding: 8px 12px; font-weight: 600; }
    .stTabs [aria-selected="true"] { color: #1E3A8A !important; border-bottom: 3px solid #1E3A8A !important; }
    .submit-blue-btn button { background-color: #1E3A8A !important; color: white !important; font-weight: 600; width: 100%; border: none; border-radius: 6px; padding: 10px; }
    .sidebar-brand { font-size: 19px; font-weight: 800; color: #0F172A; }
    .logged-badge { color: #059669; font-weight: bold; font-size: 13px; margin-bottom: 15px; }
    .stButton>button { width: 100%; border-radius: 6px; font-weight: 600; }
    .profile-card { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; margin-bottom: 15px; }
    .kpi-metric-box { background: white; border: 1px solid #E2E8F0; border-radius: 8px; padding: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }

    /* Visual replacement for 200MB label to 2MB Limit */
    [data-testid="stFileUploaderDropzoneInstructions"] > div > small {
        display: none !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] > div::after {
        content: "Max 2MB per file • JPG, PNG, PDF";
        display: block;
        font-size: 12px;
        color: #64748B;
        margin-top: 4px;
        font-weight: 500;
    }
    </style>
""", unsafe_allow_html=True)
st.markdown("""
    <link rel="manifest" href="/app/static/manifest.json">
    <meta name="theme-color" content="#1E3A8A">
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# HELPER: SECURE FILE UPLOAD WITH STRICT 2MB VALIDATION
# -------------------------------------------------------------
def upload_employee_doc(file_obj, emp_id, doc_type):
    if file_obj is None:
        return None
    max_size = 2 * 1024 * 1024  # 2 MB limit
    if file_obj.size > max_size:
        st.error(f"Error: File size ({file_obj.name}) 2 MB peksha mothi ahe! Krupaya 2 MB peksha kami size chi file upload kara.")
        return None
     
    file_ext = file_obj.name.split(".")[-1]
    file_path = f"{emp_id}/{doc_type}_{int(pytime.time())}.{file_ext}"
    try:
        file_bytes = file_obj.getvalue()
        supabase.storage.from_("documents").upload(
            file_path,
            file_bytes,
            file_options={"content-type": file_obj.type, "upsert": "true"}
        )
        public_url = supabase.storage.from_("documents").get_public_url(file_path)
        supabase.table("employees").update({f"{doc_type}_file": public_url}).eq("id", emp_id).execute()
        st.cache_data.clear()
        return public_url
    except Exception as e:
        st.error(f"File upload fail zali: {e}")
        return None

# -------------------------------------------------------------
# PERSISTENT SESSION HANDLING & DIRECT DEVICE AUTO-LOGIN
# -------------------------------------------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    saved_user_id = st.query_params.get("session_user_id")
    saved_role = st.query_params.get("session_role")
    saved_device = st.query_params.get("device_id")
     
    if saved_user_id and saved_role:
        if saved_user_id == "admin" and saved_role == "admin":
            st.session_state.user = {"user_id": "admin", "full_name": "Super Admin", "role": "admin"}
        else:
            try:
                res = supabase.table("employees").select("*").eq("user_id", saved_user_id).eq("role", saved_role).execute()
                if res.data:
                    emp_rec = res.data[0]
                    if saved_role == "employee" and saved_device:
                        if emp_rec.get("device_binding_id") == saved_device:
                            st.session_state.user = emp_rec
                    else:
                        st.session_state.user = emp_rec
            except Exception:
                pass

if "active_admin_tab" not in st.session_state:
    st.session_state.active_admin_tab = "Dashboard Overview"

STANDARD_SHIFTS = [
    "General Shift (08:30 AM - 05:00 PM | 8.5 hrs)",
    "Shift A / Morning (06:00 AM - 02:30 PM | 8.5 hrs)",
    "Shift B / Evening (02:00 PM - 10:30 PM | 8.5 hrs)",
    "Shift C / Night (10:00 PM - 06:30 AM | 8.5 hrs)",
    "Week Off"
]

def get_entity_logo(entity_name):
    if not entity_name: return None
    ent_clean = str(entity_name).upper()
    try:
        for file in os.listdir("."):
            if file.startswith("logo_") and file.endswith((".png", ".jpg", ".jpeg")):
                key = file.replace("logo_", "").split(".")[0].upper()
                if key in ent_clean: return file
    except Exception: pass
    return None

def get_entity_assets(code_prefix):
    pref = str(code_prefix or "sagar").lower().strip()
    stamp_path = f"{pref}_stamp.png"
    sig_path = f"{pref}_signature.png"
    final_stamp = stamp_path if os.path.exists(stamp_path) else ("stamp.png" if os.path.exists("stamp.png") else None)
    final_sig = sig_path if os.path.exists(sig_path) else ("signature.png" if os.path.exists("signature.png") else None)
    return final_stamp, final_sig

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
        if num_dec > 0: words += " and " + conv(num_dec) + " Paise"
        words += " Only"
        return words
    except Exception:
        return f"Indian Rupees {number:,.2f} Only"

def get_exact_salary_rule(entity_id, client_id, designation, category):
    try:
        if not entity_id:
            all_s = supabase.table("salary_structures").select("*").limit(1).execute().data
            return all_s[0] if all_s else None
        sr_query = supabase.table("salary_structures").select("*").eq("entity_id", entity_id)
        if client_id: sr_query = sr_query.eq("client_id", client_id)
        if designation: sr_query = sr_query.ilike("designation", designation.strip())
        if category: sr_query = sr_query.eq("category", category.strip())
        matched = sr_query.execute().data
        if matched: return matched[0]
        fb1 = supabase.table("salary_structures").select("*").eq("entity_id", entity_id).eq("client_id", client_id).execute().data
        if fb1: return fb1[0]
        fb2 = supabase.table("salary_structures").select("*").eq("entity_id", entity_id).execute().data
        if fb2: return fb2[0]
    except Exception: pass
    return None

def update_leave_accrual(emp_id):
    today = date.today()
    curr_yr = today.year
    curr_mo = today.month
    try:
        bal_res = supabase.table("leave_balances").select("*").eq("employee_id", emp_id).execute().data
        if not bal_res:
            supabase.table("leave_balances").insert({
                "employee_id": emp_id, "year": curr_yr, "total_credited": 1.5,
                "used_leaves": 0.0, "balance_leaves": 1.5, "last_credited_month": curr_mo
            }).execute()
        else:
            b_rec = bal_res[0]
            if b_rec.get("year") != curr_yr:
                supabase.table("leave_balances").update({
                    "year": curr_yr, "total_credited": 1.5, "used_leaves": 0.0,
                    "balance_leaves": 1.5, "last_credited_month": 1
                }).eq("id", b_rec["id"]).execute()
            else:
                last_mo = int(b_rec.get("last_credited_month", 1))
                if curr_mo > last_mo:
                    months_diff = min(curr_mo - last_mo, 10)
                    added_leaves = round(months_diff * 1.5, 2)
                    new_tot = min(float(b_rec.get("total_credited", 0.0)) + added_leaves, 15.0)
                    new_bal = new_tot - float(b_rec.get("used_leaves", 0.0))
                    supabase.table("leave_balances").update({
                        "total_credited": new_tot, "balance_leaves": max(0.0, new_bal),
                        "last_credited_month": curr_mo
                    }).eq("id", b_rec["id"]).execute()
    except Exception: pass

def generate_official_offer_letter(emp_data, entity_obj, client_name="Authorized Client Site", sal_rule=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=60)
    styles = getSampleStyleSheet()
    story = []

    entity_name = entity_obj.get("name", "GEMSHINE MULTISERVICES") if entity_obj else "GEMSHINE MULTISERVICES"
    code_pref = entity_obj.get("code_prefix", "GM") if entity_obj else "GM"
    ent_addr = entity_obj.get("address", "Ground Floor, Gat No. 235, Rajgurunagar, Maharashtra - 410505") if entity_obj else "Ground Floor, Gat No. 235, Rajgurunagar, Maharashtra - 410505"
    ent_gst = entity_obj.get("gst_number", "27ABEFG0561D1ZS") if entity_obj else "27ABEFG0561D1ZS"
    ent_pan = entity_obj.get("pan_number", "ABEFG0561D") if entity_obj else "ABEFG0561D"
    ent_phone = entity_obj.get("phone", "+91 95032 95153") if entity_obj else "+91 95032 95153"
    ent_email = entity_obj.get("email", "gemshine855@gmail.com") if entity_obj else "gemshine855@gmail.com"

    logo_file = get_entity_logo(entity_name)
    logo_img_p1 = RLImage(logo_file, width=130, height=45) if (logo_file and os.path.exists(logo_file)) else None
    logo_img_p2 = RLImage(logo_file, width=130, height=45) if (logo_file and os.path.exists(logo_file)) else None

    def draw_fixed_footer(canvas_obj, document):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica-Bold", 8)
        canvas_obj.setFillColor(colors.HexColor("#0F172A"))
        canvas_obj.drawCentredString(letter[0] / 2.0, 42, entity_name)
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(colors.HexColor("#334155"))
        canvas_obj.drawCentredString(letter[0] / 2.0, 31, f"Registered Office: {ent_addr}")
        canvas_obj.drawCentredString(letter[0] / 2.0, 20, f"GSTIN: {ent_gst} | PAN: {ent_pan} | Email: {ent_email} | Phone: {ent_phone}")
        canvas_obj.restoreState()

    raw_joining = emp_data.get("joining_date") or emp_data.get("created_at")
    joining_date_str = date.today().strftime('%d %B %Y')
    if raw_joining:
        try:
            cleaned_join = str(raw_joining).split("T")[0]
            joining_date_str = datetime.strptime(cleaned_join, "%Y-%m-%d").strftime('%d %B %Y')
        except Exception:
            joining_date_str = date.today().strftime('%d %B %Y')

    ref_no = f"Ref No.: {code_pref}/2026/{str(emp_data.get('employee_code') or emp_data.get('id', '038'))[-4:].upper()}"
    date_str = f"Date: {date.today().strftime('%d %B %Y')}"

    ref_para = Paragraph(f"<b>{ref_no}</b><br/>{date_str}", styles["Normal"])
    ht = Table([[ref_para, logo_img_p1 if logo_img_p1 else ""]], colWidths=[380, 160])
    ht.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(ht)
    story.append(Spacer(1, 14))

    title_p = Paragraph("<font size=14><b>Offer Letter</b></font>", ParagraphStyle(name="CenterOfferTitle", alignment=1, fontName="Helvetica-Bold"))
    story.append(title_p)
    story.append(Spacer(1, 14))

    salutation = f"Dear Mr./Ms. <b>{emp_data.get('full_name')}</b>,"
    story.append(Paragraph(salutation, styles["Normal"]))
    story.append(Spacer(1, 8))

    body1 = f"""Following your recent interview, we are pleased to offer you the position of <b>{emp_data.get('designation', 'Associate')}</b> on a Fixed Term Contract with <b>{entity_name}</b> for our business operations in Facility Management and Industrial Services.<br/><br/>
Your initial place of posting will be at our client site <b>"{client_name}"</b>.<br/><br/>
This offer is subject to verification of all documents submitted by you. You shall always comply with all Company rules and client site regulations. Statutory benefits such as PF, ESIC, Bonus, and other applicable benefits shall be provided as per law.<br/><br/>
You are requested to join on or before <b>{joining_date_str}</b>.<br/><br/>
The details of your salary bifurcation are as below -"""
    story.append(Paragraph(body1, styles["Normal"]))
    story.append(Spacer(1, 10))

    basic = float(sal_rule.get("basic", 14010.0)) if sal_rule else 14010.0
    da = float(sal_rule.get("da", 2511.0)) if sal_rule else 2511.0
    hra = float(sal_rule.get("hra", 826.0)) if sal_rule else 826.0
    other = float(sal_rule.get("other_allowance", 813.0)) if sal_rule else 813.0
    gross = basic + da + hra + other

    ee_pf = min(round((basic + da) * 0.12, 2), 1800.0)
    pt = float(sal_rule.get("pt_amount", 200.0)) if sal_rule else 200.0
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
        ["", "Deductions", ""],
        ["F", "PF @ 12% (A+B) (Max Rs 1,800)", f"{ee_pf:,.2f}"],
        ["G", "Professional Tax (PT)", f"{pt:,.2f}"],
        ["H", "ESI @ 0.75% ON TOTAL 'E'", f"{ee_esic:,.2f}"],
        ["I", "Total Deductions", f"{total_ded:,.2f}"],
        ["J", "Net Salary (Take Home (E - I))", f"{net_take_home:,.2f}"]
    ]
    st_table = Table(sal_table_data, colWidths=[55, 335, 150])
    st_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
        ('FONTNAME', (0,5), (-1,5), 'Helvetica-Bold'),
        ('FONTNAME', (0,6), (-1,6), 'Helvetica-Bold'),
        ('FONTNAME', (0,10), (-1,10), 'Helvetica-Bold'),
        ('FONTNAME', (0,11), (-1,11), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (2,0), (2,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(st_table)
    story.append(PageBreak())

    p2_head = Table([["", logo_img_p2 if logo_img_p2 else ""]], colWidths=[380, 160])
    p2_head.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(p2_head)
    story.append(Spacer(1, 15))

    p2_text = """Kindly sign and return a duplicate copy of this letter as a token of your acceptance of the offer.<br/><br/>
We look forward to welcoming you to <b>""" + entity_name + """</b>.<br/><br/>
Yours Sincerely,<br/>
<b>For """ + entity_name + """</b><br/><br/><br/><br/>
<b>Authorized Signatory</b><br/><br/>
<hr/><br/>
<font size=12><b>Acceptance of Offer</b></font><br/><br/>
I hereby accept the above offer and agree to join <b>""" + entity_name + """</b>.<br/><br/>
Employee Name: <b>""" + str(emp_data.get('full_name')) + """</b><br/><br/>
Signature: ___________________________ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Date: ___________________
"""
    story.append(Paragraph(p2_text, styles["Normal"]))
    doc.build(story, onFirstPage=draw_fixed_footer, onLaterPages=draw_fixed_footer)
    buffer.seek(0)
    return buffer.getvalue()

def generate_exact_tax_invoice(inv_data, entity_obj, client_obj):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    story = []

    e_name = entity_obj.get("name", "SAGAR ENTERPRISES") if entity_obj else "SAGAR ENTERPRISES"
    e_addr = entity_obj.get("address", "A/P Nimgaon tal-khed, Dist-pune") if entity_obj else "A/P Nimgaon tal-khed, Dist-pune"
    e_gst = entity_obj.get("gst_number", "27CZCPS2976N1ZI") if entity_obj else "27CZCPS2976N1ZI"
    e_pan = entity_obj.get("pan_number", "CZCPS2976N") if entity_obj else "CZCPS2976N"
    code_pref = entity_obj.get("code_prefix", "sagar") if entity_obj else "sagar"

    c_name = client_obj.get("name", "DAEBU AUTOMOTIVE SEAT INDIA PVT LTD") if client_obj else "DAEBU AUTOMOTIVE SEAT INDIA PVT LTD"
    c_addr = client_obj.get("plant_location", "MIDC Chakan, Phase-II, Bhamboli, Pune - 410501") if client_obj else "MIDC Chakan, Phase-II, Bhamboli, Pune - 410501"
    c_gst = client_obj.get("gst_number", "27AACCD4599E1ZH") if client_obj else "27AACCD4599E1ZH"

    cons_name = inv_data.get("consignee_name") or c_name
    cons_addr = inv_data.get("consignee_address") or c_addr
    cons_gst = inv_data.get("consignee_gstin") or c_gst

    inv_no = inv_data.get("invoice_number", "SE/26-27/51")
    inv_date = inv_data.get("invoice_date", date.today().strftime("%d/%m/%Y"))
    sub_total = float(inv_data.get("total_amount", 115146.0))
    cgst = round(sub_total * 0.09, 2)
    sgst = round(sub_total * 0.09, 2)
    grand_total = round(sub_total + cgst + sgst, 2)

    h_title = Paragraph("<font size=14><b>Tax Invoice</b></font>", ParagraphStyle(name="InvT", alignment=1))
    story.append(h_title)
    story.append(Spacer(1, 5))

    p_from = Paragraph(f"<b>From -</b><br/><b>{e_name}</b><br/>{e_addr}<br/><b>GSTIN/UIN:</b> {e_gst}", styles["Normal"])
    ref_txt = f"{inv_data.get('reference_no') or '-'} {inv_data.get('reference_date') or ''}"
    order_txt = f"{inv_data.get('buyers_order_no') or '-'} {inv_data.get('buyers_order_date') or ''}"
     
    meta_html = f"""<b>Invoice No:</b> {inv_no}<br/>
<b>Dated:</b> {inv_date}<br/>
<b>Reference No. & Date:</b> {ref_txt}<br/>
<b>Buyer's Order No.:</b> {order_txt}<br/>
<b>Dispatch Doc No.:</b> {inv_data.get('dispatch_doc_no') or '-'}<br/>
<b>Dispatched through:</b> {inv_data.get('dispatched_through') or '-'}<br/>
<b>Bill of Lading/LR-RR No.:</b> {inv_data.get('bill_of_lading_no') or '-'}<br/>
<b>Terms of Delivery:</b> {inv_data.get('terms_of_delivery') or '-'}"""

    p_meta = Paragraph(meta_html, styles["Normal"])
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
    p_disp = Paragraph(f"<b>Consignee (Ship to)</b><br/><b>{cons_name}</b><br/>{cons_addr}<br/><b>GSTIN:</b> {cons_gst}", styles["Normal"])
    t_mid = Table([[p_disp, p_buyer]], colWidths=[310, 252])
    t_mid.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_mid)

    bill_month = inv_data.get("billing_month", "Aug-2026")
    items_data = [
        ["Sr No.", "Description of Services / Goods", "HSN/SAC", "GST Rate", "Quantity", "Rate", "Per", "Amount"],
        ["1", f"MANPOWER/LABOUR SUPPLY BILL<br/>Month For {bill_month}", inv_data.get("hsn_sac", "996511"), "18%", "1", f"{sub_total:,.2f}", "Nos", f"{sub_total:,.2f}"],
        ["", "Total (Without GST)", "", "", "", "", "", f"{sub_total:,.2f}"],
        ["", "CGST", "", "9%", "", "", "", f"{cgst:,.2f}"],
        ["", "SGST", "", "9%", "", "", "", f"{sgst:,.2f}"],
        ["", "Total", "", "", "", "", "", f"Rs. {grand_total:,.2f}"]
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

    p_words = Paragraph(f"<b>Amount Chargeable (in words):</b><br/>{num_to_words(grand_total)}", styles["Normal"])
    t_words = Table([[p_words]], colWidths=[562])
    t_words.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.black),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_words)

    tax_data = [
        ["HSN/SAC", "Taxable Value", "Central Tax Rate", "Central Tax Amt", "State Tax Rate", "State Tax Amt", "Total Tax Amount"],
        ["996511", f"Rs.{sub_total:,.2f}", "9%", f"Rs.{cgst:,.2f}", "9%", f"Rs.{sgst:,.2f}", f"Rs.{(cgst+sgst):,.2f}"],
        ["Total", f"Rs.{sub_total:,.2f}", "", f"Rs.{cgst:,.2f}", "", f"Rs.{sgst:,.2f}", f"Rs.{(cgst+sgst):,.2f}"]
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

    b_name = entity_obj.get("bank_name", "SARASWAT BANK") if entity_obj else "SARASWAT BANK"
    b_acc = entity_obj.get("bank_account_no", "610000000045918") if entity_obj else "610000000045918"
    b_ifsc = entity_obj.get("ifsc_code", "SRCB0000376") if entity_obj else "SRCB0000376"

    decl = "<b>Declaration:</b><br/>We declare that this invoice shows the actual price of the services described and that all particulars are true and correct."
    bank_d = f"<b>Company Bank Account Details:</b><br/>BANK: {b_name}<br/>A/C NO: {b_acc}<br/>IFSC: {b_ifsc}"
     
    stamp_f, sig_f = get_entity_assets(code_pref)
    sign_elements = [Paragraph(f"<b>for {e_name}</b>", ParagraphStyle(name="SignTop", alignment=1))]
    if stamp_f and sig_f:
        sign_elements.append(Spacer(1, 4))
        sign_elements.append(Table([[RLImage(stamp_f, width=55, height=55), RLImage(sig_f, width=80, height=40)]], colWidths=[65, 95]))
    elif stamp_f:
        sign_elements.append(Spacer(1, 4))
        sign_elements.append(RLImage(stamp_f, width=60, height=60))
    elif sig_f:
        sign_elements.append(Spacer(1, 10))
        sign_elements.append(RLImage(sig_f, width=90, height=45))
    else:
        sign_elements.append(Spacer(1, 35))

    sign_elements.append(Paragraph("<b>Authorised Signatory</b>", ParagraphStyle(name="SignBottom", alignment=1)))

    t_bottom = Table([[Paragraph(decl + "<br/><br/>" + bank_d, styles["Normal"]), sign_elements]], colWidths=[360, 202])
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

def generate_salary_payslip(emp_data, entity_obj, client_name, month_str, sal_rule, att_summary, deductions_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    story = []

    entity_name = entity_obj.get("name", "SAGAR ENTERPRISES") if entity_obj else "SAGAR ENTERPRISES"
    ent_addr = entity_obj.get("address", "A/p: Nimgaon tal-khed, Dist-pune") if entity_obj else "A/p: Nimgaon tal-khed, Dist-pune"

    header_html = f"""<font size=13><b>SALARY SLIP FOR THE MONTH OF {month_str.upper()}</b></font><br/>
    <font size=11><b>{entity_name}</b></font><br/>
    <font size=8 color='#475569'>{ent_addr}</font>"""
     
    p_center_head = Paragraph(header_html, ParagraphStyle(name="CenterHeadPayslip", alignment=1, leading=16))
    story.append(p_center_head)
    story.append(Spacer(1, 10))

    doj_val = str(emp_data.get("joining_date") or emp_data.get("created_at") or "")
    if "T" in doj_val: doj_val = doj_val.split("T")[0]

    emp_info_data = [
        ["Emp. Code:", str(emp_data.get("employee_code", "N/A")), "Paid Days:", str(att_summary.get("paid_days", 0))],
        ["Name:", str(emp_data.get("full_name", "N/A")), "Total Days:", str(att_summary.get("total_days", 0))],
        ["Designation:", str(emp_data.get("designation", "Staff")), "Bank Name:", str(emp_data.get("bank_name", "N/A"))],
        ["Client Site:", str(client_name), "Bank A/c No.:", str(emp_data.get("bank_account_no", "N/A"))],
        ["DOJ:", doj_val, "PAN No.:", str(emp_data.get("pan_number", "N/A"))],
        ["Category:", str(emp_data.get("category", "Semi-Skilled")), "Aadhaar No.:", "[Aadhaar Redacted]"]
    ]
    t_emp = Table(emp_info_data, colWidths=[95, 185, 95, 187])
    t_emp.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#94A3B8")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_emp)
    story.append(Spacer(1, 8))

    rate_basic = float(sal_rule.get("basic", 0.0)) if sal_rule else 0.0
    rate_da = float(sal_rule.get("da", 0.0)) if sal_rule else 0.0
    rate_hra = float(sal_rule.get("hra", 0.0)) if sal_rule else 0.0

    earned_basic = deductions_data.get('earned_basic', 0.0)
    earned_da = deductions_data.get('earned_da', 0.0)
    earned_hra = deductions_data.get('earned_hra', 0.0)
    ot_amt = deductions_data.get('ot_amount', 0.0)
    total_gross = earned_basic + earned_da + earned_hra + ot_amt

    pf_ded = deductions_data.get('pf_ded', 0.0)
    esic_ded = deductions_data.get('esic_ded', 0.0)
    pt_ded = deductions_data.get('pt_ded', 0.0)
    adv_ded = deductions_data.get('adv_val', 0.0)
    ppe_ded = deductions_data.get('ppe_ded', 0.0)
    total_ded = pf_ded + esic_ded + pt_ded + adv_ded + ppe_ded
    net_salary = total_gross - total_ded

    calc_table_data = [
        ["Earnings in Rs.", "Monthly Rate", "Earned (Rs.)", "Deductions", "Amount Rs."],
        ["Basic", f"{rate_basic:,.2f}", f"{earned_basic:,.2f}", "Provident Fund (PF)", f"{pf_ded:,.2f}"],
        ["D.A.", f"{rate_da:,.2f}", f"{earned_da:,.2f}", "ESIC", f"{esic_ded:,.2f}"],
        ["H.R.A.", f"{rate_hra:,.2f}", f"{earned_hra:,.2f}", "Prof. Tax (PT)", f"{pt_ded:,.2f}"],
        ["Overtime Pay (OT)", "-", f"{ot_amt:,.2f}", "Salary Advance", f"{adv_ded:,.2f}"],
        ["", "", "", "Uniform / PPE Deduction", f"{ppe_ded:,.2f}"],
        ["Gross Earning", "", f"{total_gross:,.2f}", "Total Deductions", f"{total_ded:,.2f}"]
    ]

    t_calc = Table(calc_table_data, colWidths=[120, 80, 80, 202, 80])
    t_calc.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#94A3B8")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#F8FAFC")),
        ('ALIGN', (1,1), (2,-1), 'RIGHT'),
        ('ALIGN', (4,1), (4,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_calc)

    t_net = Table([["Net Salary", f"Rs. {net_salary:,.2f}"]], colWidths=[280, 282])
    t_net.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#94A3B8")),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_net)

    t_words = Table([
        [Paragraph(f"<b>Amount in Words:</b> <b>{num_to_words(net_salary)}</b>", styles["Normal"])],
        [Paragraph("<b>Remarks:</b> Salary calculated based on approved muster and leave records.", styles["Normal"])],
        [Paragraph("<font size=7 color='#64748B'><i>This is a computer-generated salary slip and does not require any signature.</i></font>", ParagraphStyle(name="NoteP", alignment=1))]
    ], colWidths=[562])
    t_words.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#94A3B8")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_words)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def export_source_code_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    
    code_text = ""
    try:
        with open(__file__, "r", encoding="utf-8") as f:
            code_text = f.read()
    except Exception:
        code_text = "# Error loading source file."

    pre = Preformatted(code_text, ParagraphStyle('Code', fontName='Courier', fontSize=5.5, leading=7))
    story.append(pre)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# =============================================================================
# 2. PUBLIC INTERFACE (LOGIN & ONBOARDING)
# =============================================================================
if not st.session_state.user:
    st.markdown('<div class="main-title">ESS PORTAL</div>', unsafe_allow_html=True)
    tab_signin, tab_join = st.tabs(["Sign In", "Candidate Paperless Joining Form"])

    with tab_signin:
        col_s1, col_login, col_s2 = st.columns([1, 1.8, 1])
        with col_login:
            st.write(" ")
            is_mgmt = st.checkbox("Management Login (Admin / Supervisor / Client)", key="mgmt_login_checkbox")
           
            target_role = "employee"
            if is_mgmt:
                role_choice = st.selectbox("Management Role", ["Admin Portal", "Supervisor Portal", "Client Desk"], key="management_role_select")
                role_map = {"Admin Portal": "admin", "Supervisor Portal": "supervisor", "Client Desk": "client"}
                target_role = role_map[role_choice]
           
            u_id = st.text_input("User ID / Employee Code", key="login_user_id")
            u_pwd = st.text_input("Password", type="password", key="login_password")
           
            st.markdown('<div class="submit-blue-btn">', unsafe_allow_html=True)
            if st.button("Access Dashboard", key="access_btn"):
                if u_id == "admin" and u_pwd == "admin123" and target_role == "admin":
                    st.session_state.user = {"user_id": "admin", "full_name": "Super Admin", "role": "admin"}
                    st.query_params["session_user_id"] = "admin"
                    st.query_params["session_role"] = "admin"
                    st.rerun()
                 
                try:
                    res = supabase.table("employees").select("*").eq("user_id", u_id).eq("password", u_pwd).eq("role", target_role).execute()
                    if res.data:
                        emp_rec = res.data[0]
                        if target_role == "employee":
                            dev_id = st.query_params.get("device_id") or f"dev_{emp_rec['id'][:8]}"
                            reg_dev = emp_rec.get("device_binding_id")
                            if reg_dev and reg_dev != dev_id:
                                st.error("Security Error: This account is locked to your registered mobile phone. Contact Admin to reset.")
                                st.stop()
                            elif not reg_dev:
                                supabase.table("employees").update({"device_binding_id": dev_id}).eq("id", emp_rec["id"]).execute()
                                emp_rec["device_binding_id"] = dev_id

                            st.query_params["device_id"] = dev_id
                            update_leave_accrual(emp_rec["id"])

                        st.session_state.user = emp_rec
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
        if "c_name_val" not in st.session_state: st.session_state.c_name_val = ""
        if "c_father_val" not in st.session_state: st.session_state.c_father_val = ""
        if "c_phone_val" not in st.session_state: st.session_state.c_phone_val = ""
        if "c_emg_val" not in st.session_state: st.session_state.c_emg_val = ""
        if "c_addr_val" not in st.session_state: st.session_state.c_addr_val = ""
        if "c_uan_val" not in st.session_state: st.session_state.c_uan_val = ""
        if "c_esic_val" not in st.session_state: st.session_state.c_esic_val = ""
        if "c_bank_val" not in st.session_state: st.session_state.c_bank_val = ""
        if "c_branch_val" not in st.session_state: st.session_state.c_branch_val = ""
        if "c_acc_val" not in st.session_state: st.session_state.c_acc_val = ""
        if "c_ifsc_val" not in st.session_state: st.session_state.c_ifsc_val = ""
        if "c_pan_val" not in st.session_state: st.session_state.c_pan_val = ""
        if "c_aadhar_val" not in st.session_state: st.session_state.c_aadhar_val = ""

        with st.form("onboard_candidate_form", clear_on_submit=False):
            col_left, col_right = st.columns(2)
            c_name = col_left.text_input("Candidate Full Name *", value=st.session_state.c_name_val)
            c_father = col_left.text_input("Father's Name *", value=st.session_state.c_father_val)
            c_dob_str = col_left.text_input("Date of Birth (DOB) *", placeholder="DD/MM/YYYY")
            c_gender = col_left.selectbox("Gender *", ["Male", "Female", "Other"])
            c_marital = col_left.selectbox("Marital Status", ["Single", "Married"])
            c_phone = col_left.text_input("Employee Mobile Number * (10 Digits)", value=st.session_state.c_phone_val)
            c_emergency = col_left.text_input("Emergency Contact Number *", value=st.session_state.c_emg_val)
            c_address = col_left.text_area("Permanent Address *", value=st.session_state.c_addr_val)
             
            c_uan = col_right.text_input("UAN Number (12 Digits)", value=st.session_state.c_uan_val)
            c_esic = col_right.text_input("ESIC Number (10 Digits)", value=st.session_state.c_esic_val)
            c_bank = col_right.text_input("Bank Name *", value=st.session_state.c_bank_val)
            c_branch = col_right.text_input("Bank Branch Name *", value=st.session_state.c_branch_val)
            c_acc = col_right.text_input("Bank Account Number *", value=st.session_state.c_acc_val)
            c_ifsc = col_right.text_input("IFSC Code * (11 Digits)", value=st.session_state.c_ifsc_val)
            c_pan = col_right.text_input("PAN Number (10 Digits)", value=st.session_state.c_pan_val)
            c_aadhar = col_right.text_input("Aadhaar Number * (12 Digits)", value=st.session_state.c_aadhar_val)

            st.write("---")
            st.write("#### Document Attachments (Max 2MB per file)")
            up_photo = col_left.file_uploader("Passport Size Photo", type=["jpg", "png"])
            up_aadhar = col_right.file_uploader("Aadhaar Card Copy", type=["pdf", "jpg", "png"])
            up_pan = col_left.file_uploader("PAN Card Copy", type=["pdf", "jpg", "png"])
            up_bank = col_right.file_uploader("Bank Passbook / Cheque", type=["pdf", "jpg", "png"])

            if st.form_submit_button("Submit Onboarding Application", type="primary"):
                st.session_state.c_name_val = c_name
                st.session_state.c_father_val = c_father
                st.session_state.c_phone_val = c_phone
                st.session_state.c_emg_val = c_emergency
                st.session_state.c_addr_val = c_address
                st.session_state.c_uan_val = c_uan
                st.session_state.c_esic_val = c_esic
                st.session_state.c_bank_val = c_bank
                st.session_state.c_branch_val = c_branch
                st.session_state.c_acc_val = c_acc
                st.session_state.c_ifsc_val = c_ifsc
                st.session_state.c_pan_val = c_pan
                st.session_state.c_aadhar_val = c_aadhar

                clean_phone = c_phone.strip()
                clean_aadhar = c_aadhar.strip()
                clean_pan = c_pan.strip().upper()
                clean_ifsc = c_ifsc.strip().upper()
                clean_uan = c_uan.strip()
                clean_esic = c_esic.strip()
                max_allowed = 2 * 1024 * 1024
                files_to_check = [("Photo", up_photo), ("Aadhaar", up_aadhar), ("PAN", up_pan), ("Bank Doc", up_bank)]
                size_error = False

                for fname, fobj in files_to_check:
                    if fobj and fobj.size > max_allowed:
                        st.error(f"{fname} chi size 2 MB peksha jast ahe! Krupaya 2 MB peksha kami size chi file nivaada.")
                        size_error = True
                        break

                if not size_error:
                    if not c_name or not clean_phone or not c_address:
                        st.error("Full Name, Mobile Number and Address are mandatory!")
                    elif not re.match(r"^[6-9]\d{9}$", clean_phone):
                        st.error("Invalid Mobile Number! Enter exact 10-digit Indian number.")
                    elif not re.match(r"^\d{12}$", clean_aadhar):
                        st.error("Invalid Aadhaar Number! Must be exactly 12 numeric digits.")
                    else:
                        new_candidate = {
                            "user_id": f"TEMP_{clean_phone}", "password": "emp" + clean_phone[-4:],
                            "full_name": c_name.strip(), "father_name": c_father.strip(), "gender": c_gender,
                            "dob": str(c_dob), "marital_status": c_marital, "phone_number": clean_phone,
                            "emergency_contact": c_emergency.strip(), "permanent_address": c_address.strip(),
                            "uan_number": clean_uan, "esic_number": clean_esic, "bank_name": c_bank.strip(),
                            "bank_branch": c_branch.strip(), "bank_account_no": c_acc.strip(), "ifsc_code": clean_ifsc,
                            "pan_number": clean_pan, "aadhar_number": "[Aadhaar Redacted]", "role": "employee",
                            "status": "PENDING_SUPERVISOR", "joining_date": str(date.today())
                        }
                        try:
                            ins_c = supabase.table("employees").insert(new_candidate).execute()
                            if ins_c.data:
                                cand_id = ins_c.data[0]["id"]
                                if up_photo: upload_employee_doc(up_photo, cand_id, "photo")
                                if up_aadhar: upload_employee_doc(up_aadhar, cand_id, "aadhar")
                                if up_pan: upload_employee_doc(up_pan, cand_id, "pan")
                                if up_bank: upload_employee_doc(up_bank, cand_id, "bank")
                                if st.form_submit_button("Save New Employee", type="primary"):
                            
                                    st.cache_data.clear()
                                    st.toast("✅ Application submitted successfully!")
                                    st.success("Application submitted successfully! Forwarded to Supervisor.")
                            for k in ["c_name_val","c_father_val","c_phone_val","c_emg_val","c_addr_val","c_uan_val","c_esic_val","c_bank_val","c_branch_val","c_acc_val","c_ifsc_val","c_pan_val","c_aadhar_val"]:
                                st.session_state[k] = ""
                            pytime.sleep(1)
                            st.rerun()
                        except Exception as err:
                            st.error(f"Error submitting data: {err}")

# =============================================================================
# 3. LOGGED-IN ROLES INTERFACE
# =============================================================================
else:
    active_role = st.session_state.user.get("role")
    
    # -------------------------------------------------------------------------
    # 4.1 ADMIN PORTAL
    # -------------------------------------------------------------------------
    if active_role == "admin":
        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS ADMIN</div>', unsafe_allow_html=True)
            st.markdown('<div class="logged-badge">Logged In: ADMIN</div>', unsafe_allow_html=True)
            st.caption("ADMIN DESK")
             
            admin_tabs = [
                "Dashboard Overview",
                "Candidate Approvals",
                "Employee Master & Docs",
                "Leave Approvals Desk",
                "Shift Roster Management",
                "Salary Structure Rules",
                "Attendance & OT Live Edit",
                "Monthly Payroll Processing (43-Cols)",
                "Statutory Compliance Reports",
                "Helpdesk / Grievance Desk",
                "Advance / Loan Desk",
                "PPE & Uniform Tracker",
                "Client Billing & Invoices",
                "Company & Plant Locations",
                "User Roles & Access",
                "Device Binding Reset"
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

        # PANEL 1: DASHBOARD OVERVIEW
        if selected_panel == "Dashboard Overview":
            st.subheader("Workforce Intelligence & KPI Metrics")
            
            ent_res = fetch_cached_entities()
            cli_res = fetch_cached_clients()
            emp_res = fetch_cached_employees()
            client_ents = supabase.table("client_entities").select("*").execute().data or []

            # KPI Calculations
            active_staff_list = [e for e in emp_res if e.get("role") == "employee" and e.get("status") == "APPROVED"]
            tot_staff = len(active_staff_list)
            
            today_str = str(date.today())
            today_att = supabase.table("attendance").select("status").eq("date", today_str).execute().data or []
            present_cnt = len([a for a in today_att if a.get("status") in ["P", "IN_PROGRESS", "WO"]])
            absent_cnt = max(0, tot_staff - present_cnt)

            active_leaves = supabase.table("leave_requests").select("id").eq("status", "APPROVED").lte("start_date", today_str).gte("end_date", today_str).execute().data or []
            leaves_cnt = len(active_leaves)

            pending_appr = len([e for e in emp_res if e.get("status") == "PENDING_ADMIN"])

            kp1, kp2, kp3, kp4, kp5 = st.columns(5)
            kp1.markdown(f'<div class="kpi-metric-box"><span style="color:#64748B; font-size:12px; font-weight:700;">ACTIVE STAFF</span><h2 style="color:#0F172A; margin:4px 0;">{tot_staff}</h2></div>', unsafe_allow_html=True)
            kp2.markdown(f'<div class="kpi-metric-box"><span style="color:#059669; font-size:12px; font-weight:700;">PRESENT TODAY</span><h2 style="color:#059669; margin:4px 0;">{present_cnt}</h2></div>', unsafe_allow_html=True)
            kp3.markdown(f'<div class="kpi-metric-box"><span style="color:#DC2626; font-size:12px; font-weight:700;">ABSENT TODAY</span><h2 style="color:#DC2626; margin:4px 0;">{absent_cnt}</h2></div>', unsafe_allow_html=True)
            kp4.markdown(f'<div class="kpi-metric-box"><span style="color:#0284C7; font-size:12px; font-weight:700;">ON LEAVE</span><h2 style="color:#0284C7; margin:4px 0;">{leaves_cnt}</h2></div>', unsafe_allow_html=True)
            kp5.markdown(f'<div class="kpi-metric-box"><span style="color:#D97706; font-size:12px; font-weight:700;">PENDING APPROVALS</span><h2 style="color:#D97706; margin:4px 0;">{pending_appr}</h2></div>', unsafe_allow_html=True)

            st.write("---")
            st.subheader("Workforce Deployment Matrix (Client-Wise per Entity)")
            if ent_res:
                supervisors = [e for e in emp_res if e.get("role") == "supervisor"]
                matrix_rows = []
                for ent in ent_res:
                    ent_id = ent["id"]
                    ent_name = ent["name"]
                    
                    # client_entities madhun client IDs shodhne
                    linked_cli_ids = [ce["client_id"] for ce in client_ents if ce["entity_id"] == ent_id]
                    matched_clients = [c for c in cli_res if c.get("id") in linked_cli_ids or c.get("entity_id") == ent_id]

                    for cl in matched_clients:
                        cl_id = cl["id"]
                        cl_name = cl["name"]
                        deployed_count = len([e for e in active_staff_list if e.get("entity_id") == ent_id and e.get("client_id") == cl_id])
                        site_sup = next((s["full_name"] for s in supervisors if s.get("client_id") == cl_id), "Not Assigned")
                        
                        matrix_rows.append({
                            "Entity Name": ent_name,
                            "Client Site Name": cl_name,
                            "Deployed Staff Count": f"{deployed_count} Staff",
                            "Site Incharge / Supervisor": site_sup
                        })
                
                if matrix_rows:
                    st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True)
                else:
                    st.info("No client plant sites mapped under configured entities.")
            else:
                st.info("No entities configured yet.")

        # PANEL 2: CANDIDATE APPROVALS
        elif selected_panel == "Candidate Approvals":
            st.subheader("Review Candidate Deployment & Dispatch Credentials")
            cands = supabase.table("employees").select("*").eq("status", "PENDING_ADMIN").execute().data or []
            
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_map = {e["name"]: e["id"] for e in ent_list}
            c_map = {c["name"]: c["id"] for c in cli_list}
            e_rev_map = {e["id"]: e["name"] for e in ent_list}
            c_rev_map = {c["id"]: c["name"] for c in cli_list}

            if cands:
                cand_map = {f"{c['full_name']} (Mobile: {c['phone_number']} | Applied: {str(c.get('created_at'))[:10]})": c for c in cands}
                sel_c_label = st.selectbox("Select Candidate to Review *", list(cand_map.keys()))
                cand = cand_map[sel_c_label]

                with st.form("admin_review_cand_form"):
                    st.write("##### Section A: Login Credentials & Identifiers")
                    ac1, ac2, ac3 = st.columns(3)
                    set_code = ac1.text_input("Employee Code *", value=cand.get("employee_code") or "").strip().upper()
                    set_uid = ac2.text_input("User ID (Login) *", value=cand.get("user_id") or set_code).strip()
                    set_pwd = ac3.text_input("Portal Password *", value=cand.get("password") or f"emp{cand['phone_number'][-4:]}")

                    st.write("##### Section B: Organization & Plant Site Assignment")
                    as1, as2 = st.columns(2)
                    c_ent_name = e_rev_map.get(cand.get("entity_id"))
                    ent_opts = list(e_map.keys())
                    ent_idx = ent_opts.index(c_ent_name) if c_ent_name in ent_opts else 0
                    set_ent = as1.selectbox("Assigned Entity / Firm *", ent_opts if ent_opts else ["No Entity"], index=ent_idx)

                    c_cli_name = c_rev_map.get(cand.get("client_id"))
                    cli_opts = list(c_map.keys())
                    cli_idx = cli_opts.index(c_cli_name) if c_cli_name in cli_opts else 0
                    set_cli = as2.selectbox("Assigned Client Work Site *", cli_opts if cli_opts else ["No Client"], index=cli_idx)

                    as3, as4 = st.columns(2)
                    set_dept = as3.text_input("Department", value=cand.get("department") or "Facility")
                    set_zone = as4.text_input("Zone", value=cand.get("zone") or "Zone - 3")

                    st.write("##### Section C: Shift, Timings & Commercials")
                    sc1, sc2, sc3 = st.columns(3)
                    curr_shift = cand.get("shift_timing") or STANDARD_SHIFTS[0]
                    shift_idx = STANDARD_SHIFTS.index(curr_shift) if curr_shift in STANDARD_SHIFTS else 0
                    set_shift = sc1.selectbox("Assigned Shift Timing *", STANDARD_SHIFTS, index=shift_idx)

                    wo_opts = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
                    curr_wo = cand.get("weekly_off_day") or "Sunday"
                    wo_idx = wo_opts.index(curr_wo) if curr_wo in wo_opts else 0
                    set_wo = sc2.selectbox("Weekly Off Day *", wo_opts, index=wo_idx)

                    raw_c_join = cand.get("joining_date") or cand.get("created_at")
                    def_cand_join = datetime.strptime(str(raw_c_join).split("T")[0], "%Y-%m-%d").date() if raw_c_join else date.today()
                    set_join_date = sc3.date_input("Joining Date *", value=def_cand_join, format="DD/MM/YYYY")

                    sc4, sc5, sc6 = st.columns(3)
                    set_desig = sc4.text_input("Designation *", value=cand.get("designation") or "Associate")
                    cat_opts = ["Skilled", "Semi-Skilled", "Unskilled"]
                    curr_cat = cand.get("category") or "Semi-Skilled"
                    cat_idx = cat_opts.index(curr_cat) if curr_cat in cat_opts else 1
                    set_cat = sc5.selectbox("Category *", cat_opts, index=cat_idx)
                    set_ot = sc6.number_input("Custom OT Rate / Hour (Rs.)", min_value=0.0, step=10.0, value=float(cand.get("ot_rate_per_hour") or 0.0))

                    st.write("##### Section D: Personal, Identification & Bank Details (Editable Audit)")
                    pd1, pd2, pd3 = st.columns(3)
                    set_name = pd1.text_input("Full Name *", value=cand.get("full_name", ""))
                    set_father = pd2.text_input("Father's Name", value=cand.get("father_name", ""))
                    set_gender = pd3.selectbox("Gender *", ["Male", "Female", "Other"], index=["Male", "Female", "Other"].index(cand.get("gender", "Male")) if cand.get("gender") in ["Male", "Female", "Other"] else 0)

                    pd4, pd5, pd6 = st.columns(3)
                    raw_dob = cand.get("dob")
                    def_dob = datetime.strptime(str(raw_dob).split("T")[0], "%Y-%m-%d").date() if raw_dob else date(1995, 1, 1)
                    set_dob = pd4.date_input("Date of Birth (DOB) *", value=def_dob, format="DD/MM/YYYY")
                    set_phone = pd5.text_input("Mobile Number *", value=cand.get("phone_number", ""))
                    set_emg = pd6.text_input("Emergency Contact Number", value=cand.get("emergency_contact", ""))

                    set_addr = st.text_area("Permanent Address *", value=cand.get("permanent_address", ""))

                    st1, st2, st3, st4 = st.columns(4)
                    set_aadhar = st1.text_input("Aadhaar Number *", value=str(cand.get("aadhar_number") or ""))
                    set_pan = st2.text_input("PAN Number", value=cand.get("pan_number", ""))
                    set_uan = st3.text_input("UAN Number", value=cand.get("uan_number", ""))
                    set_esic = st4.text_input("ESIC Number", value=cand.get("esic_number", ""))

                    bk1, bk2, bk3, bk4 = st.columns(4)
                    set_bank = bk1.text_input("Bank Name", value=cand.get("bank_name", ""))
                    set_branch = bk2.text_input("Branch Name", value=cand.get("bank_branch", ""))
                    set_acc = bk3.text_input("Bank Account Number", value=cand.get("bank_account_no", ""))
                    set_ifsc = bk4.text_input("IFSC Code", value=cand.get("ifsc_code", ""))

                    st.write("##### Section E: Document Attachments Preview")
                    doc_v1, doc_v2 = st.columns(2)
                    with doc_v1:
                        if cand.get("photo_file"): st.markdown(f"📷 [Passport Size Photo Preview]({cand['photo_file']})")
                        else: st.caption("Passport Photo: Not Attached")
                        if cand.get("aadhar_file"): st.markdown(f"📄 [Aadhaar Card Copy]({cand['aadhar_file']})")
                        else: st.caption("Aadhaar Card: Not Attached")
                    with doc_v2:
                        if cand.get("pan_file"): st.markdown(f"📄 [PAN Card Copy]({cand['pan_file']})")
                        else: st.caption("PAN Card: Not Attached")
                        if cand.get("bank_file"): st.markdown(f"📄 [Bank Passbook / Cheque]({cand['bank_file']})")
                        else: st.caption("Bank Proof: Not Attached")

                    st.caption(f"Digital Signature Confirmation: **{cand.get('signature_data') or 'Confirmed at Onboarding'}**")

                    st.write("---")
                    st.write("##### 3. Decision & Two-Way Rejection Action")
                    adm_remarks = st.text_area("Admin Rejection Remarks / Correction Note (Mandatory if Rejecting)")

                    dec_col1, dec_col2 = st.columns(2)
                    btn_approve = dec_col1.form_submit_button("Approve & Activate Employee", type="primary")
                    btn_reject = dec_col2.form_submit_button("Reject & Send Back to Supervisor")

                    if btn_approve:
                        if not set_code or not set_uid:
                            st.error("Employee Code and User ID are mandatory!")
                        else:
                            dup = supabase.table("employees").select("id").eq("employee_code", set_code).neq("id", cand["id"]).execute().data
                            if dup:
                                st.error(f"Error: Employee Code '{set_code}' already exists! Assign a unique code.")
                            else:
                                supabase.table("employees").update({
                                    "employee_code": set_code, "user_id": set_uid, "password": set_pwd,
                                    "entity_id": e_map.get(set_ent), "client_id": c_map.get(set_cli),
                                    "department": set_dept, "zone": set_zone,
                                    "shift_timing": set_shift, "weekly_off_day": set_wo,
                                    "joining_date": str(set_join_date),
                                    "designation": set_desig, "category": set_cat,
                                    "ot_rate_per_hour": set_ot if set_ot > 0 else None,
                                    "full_name": set_name, "father_name": set_father, "gender": set_gender,
                                    "dob": str(set_dob), "phone_number": set_phone, "emergency_contact": set_emg,
                                    "permanent_address": set_addr, "aadhar_number": "[Aadhaar Redacted]",
                                    "pan_number": set_pan, "uan_number": set_uan, "esic_number": set_esic,
                                    "bank_name": set_bank, "bank_branch": set_branch,
                                    "bank_account_no": set_acc, "ifsc_code": set_ifsc,
                                    "status": "APPROVED", "admin_remarks": None
                                }).eq("id", cand["id"]).execute()
                                
                                update_leave_accrual(cand["id"])
                                st.cache_data.clear()

                                msg = f"Hello {set_name}, Welcome to {set_ent}! Your ESS Portal credentials are: User ID: {set_uid}, Password: {set_pwd}. Login here: https://employeeselfservice.streamlit.app/"
                                wa_url = f"https://wa.me/91{set_phone}?text={urllib.parse.quote(msg)}"
                                
                                st.toast("✅ Candidate Approved & Activated!")
                                st.success("Candidate approved! Dispatching credentials to WhatsApp.")
                                st.markdown(f'<meta http-equiv="refresh" content="0; url={wa_url}">', unsafe_allow_html=True)
                                st.markdown(f'<a href="{wa_url}" target="_blank" style="display:inline-block; background-color:#25D366; color:white; padding:8px 16px; border-radius:4px; text-decoration:none; font-weight:bold;">Click here if WhatsApp did not open automatically</a>', unsafe_allow_html=True)
                                pytime.sleep(2)
                                st.rerun()

                    if btn_reject:
                        if not adm_remarks.strip():
                            st.error("Admin Rejection Remarks / Correction Note is mandatory for rejecting!")
                        else:
                            supabase.table("employees").update({
                                "status": "REJECTED_TO_SUPERVISOR",
                                "admin_remarks": adm_remarks.strip()
                            }).eq("id", cand["id"]).execute()
                            st.cache_data.clear()
                            st.toast("Application rejected and returned to supervisor!")
                            st.warning("Candidate application returned to supervisor with correction remarks.")
                            pytime.sleep(1)
                            st.rerun()
            else:
                st.info("No candidates pending admin approval.")

        # PANEL 3: EMPLOYEE MASTER & DOCS
        elif selected_panel == "Employee Master & Docs":
            st.subheader("Employee Master Management & Document Vault (4 Tabs Structure)")
            tab_add_emp, tab_edit_emp, tab_vault, tab_exit_emp = st.tabs([
                "➕ Add New Employee", 
                "✏️ Edit / Update Employee", 
                "📁 Document Section (6 Docs)", 
                "🚪 Employee Exit & Delete Desk"
            ])

            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_map = {e["name"]: e["id"] for e in ent_list}
            c_map = {c["name"]: c["id"] for c in cli_list}
            e_rev_map = {e["id"]: e["name"] for e in ent_list}
            c_rev_map = {c["id"]: c["name"] for c in cli_list}
            all_emps = supabase.table("employees").select("*").eq("role", "employee").execute().data or []

            with tab_add_emp:
                with st.form("admin_add_emp_master_form"):
                    st.write("##### Section A: Credentials")
                    a1, a2, a3 = st.columns(3)
                    ne_code = a1.text_input("Employee Code *").strip().upper()
                    ne_uid = a2.text_input("User ID *").strip()
                    ne_pwd = a3.text_input("Password *", type="password")

                    st.write("##### Section B: Organization")
                    b1, b2 = st.columns(2)
                    ne_ent = b1.selectbox("Entity / Firm *", options=list(e_map.keys()) if e_map else ["No Entity"])
                    ne_cli = b2.selectbox("Client Work Site *", options=list(c_map.keys()) if c_map else ["No Client"])
                    b3, b4 = st.columns(2)
                    ne_dept = b3.text_input("Department", value="Facility")
                    ne_zone = b4.text_input("Zone", value="Zone - 3")

                    st.write("##### Section C: Shift & Rates")
                    c1, c2, c3 = st.columns(3)
                    ne_shift = c1.selectbox("Shift Timing *", STANDARD_SHIFTS)
                    ne_wo = c2.selectbox("Weekly Off *", ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])
                    ne_join = c3.date_input("Joining Date *", value=date.today(), format="DD/MM/YYYY")
                    c4, c5, c6 = st.columns(3)
                    ne_desig = c4.text_input("Designation *", value="Associate")
                    ne_cat = c5.selectbox("Category *", ["Skilled", "Semi-Skilled", "Unskilled"], index=1)
                    ne_ot = c6.number_input("Custom OT Rate / Hour", min_value=0.0, step=10.0, value=0.0)

                    st.write("##### Section D: Personal & Contact")
                    d1, d2, d3 = st.columns(3)
                    ne_name = d1.text_input("Full Name *")
                    ne_father = d2.text_input("Father's Name")
                    ne_gender = d3.selectbox("Gender *", ["Male", "Female", "Other"])
                    d4, d5, d6 = st.columns(3)
                    ne_dob = d4.date_input("DOB *", value=date(1995, 1, 1), format="DD/MM/YYYY")
                    ne_marital = d5.selectbox("Marital Status", ["Single", "Married"])
                    ne_phone = d6.text_input("Mobile Number *")
                    d7, d8 = st.columns(2)
                    ne_emg = d7.text_input("Emergency Contact")
                    ne_addr = d8.text_area("Permanent Address *")

                    st.write("##### Section E: Statutory & Bank")
                    s1, s2, s3, s4 = st.columns(4)
                    ne_aadhar = s1.text_input("Aadhaar Number *")
                    ne_pan = s2.text_input("PAN Number")
                    ne_uan = s3.text_input("UAN Number")
                    ne_esic = s4.text_input("ESIC Number")

                    k1, k2, k3, k4 = st.columns(4)
                    ne_bank = k1.text_input("Bank Name *")
                    ne_branch = k2.text_input("Branch Name *")
                    ne_acc = k3.text_input("Account Number *")
                    ne_ifsc = k4.text_input("IFSC Code *")

                    if st.form_submit_button("Save New Employee", type="primary"):
                        if not ne_code or not ne_name or not ne_phone or not ne_addr or not ne_aadhar:
                            st.error("Mandatory fields (*) are required!")
                        else:
                            chk_dup = supabase.table("employees").select("id").eq("employee_code", ne_code).execute().data
                            if chk_dup:
                                st.error(f"Employee Code '{ne_code}' already exists!")
                            else:
                                ins = supabase.table("employees").insert({
                                    "employee_code": ne_code, "user_id": ne_uid or ne_code,
                                    "password": ne_pwd or f"emp{ne_phone[-4:]}",
                                    "entity_id": e_map.get(ne_ent), "client_id": c_map.get(ne_cli),
                                    "department": ne_dept, "zone": ne_zone, "shift_timing": ne_shift,
                                    "weekly_off_day": ne_wo, "joining_date": str(ne_join),
                                    "designation": ne_desig, "category": ne_cat,
                                    "ot_rate_per_hour": ne_ot if ne_ot > 0 else None,
                                    "full_name": ne_name, "father_name": ne_father, "gender": ne_gender,
                                    "dob": str(ne_dob), "marital_status": ne_marital, "phone_number": ne_phone,
                                    "emergency_contact": ne_emg, "permanent_address": ne_addr,
                                    "aadhar_number": "[Aadhaar Redacted]", "pan_number": ne_pan, "uan_number": ne_uan,
                                    "esic_number": ne_esic, "bank_name": ne_bank, "bank_branch": ne_branch,
                                    "bank_account_no": ne_acc, "ifsc_code": ne_ifsc,
                                    "role": "employee", "status": "APPROVED"
                                }).execute()
                                if ins.data:
                                    update_leave_accrual(ins.data[0]["id"])
                                st.cache_data.clear()
                                st.toast("✅ Employee added successfully!")
                                st.success(f"Employee {ne_name} registered!")
                                pytime.sleep(1)
                                st.rerun()

            with tab_edit_emp:
                if all_emps:
                    emp_opt_map = {f"[{e.get('employee_code', 'TEMP')}] {e.get('full_name')} (ID: {e['id'][:6]})": e for e in all_emps}
                    sel_emp_to_edit = st.selectbox("Select Employee to Update *", list(emp_opt_map.keys()))
                    curr_emp = emp_opt_map[sel_emp_to_edit]

                    with st.form("edit_emp_100pct_form"):
                        st.write("##### 1. Login Details")
                        u1, u2, u3 = st.columns(3)
                        ue_code = u1.text_input("Employee Code", value=curr_emp.get("employee_code", "")).strip().upper()
                        ue_uid = u2.text_input("User ID", value=curr_emp.get("user_id", ""))
                        ue_pwd = u3.text_input("Portal Password", value=curr_emp.get("password", ""))

                        st.write("##### 2. Deployment")
                        d_c1, d_c2 = st.columns(2)
                        c_ent_name = e_rev_map.get(curr_emp.get("entity_id"))
                        ent_opts = list(e_map.keys())
                        ent_idx = ent_opts.index(c_ent_name) if c_ent_name in ent_opts else 0
                        ue_ent = d_c1.selectbox("Entity / Firm *", ent_opts if ent_opts else ["No Entity"], index=ent_idx)

                        c_cli_name = c_rev_map.get(curr_emp.get("client_id"))
                        cli_opts = list(c_map.keys())
                        cli_idx = cli_opts.index(c_cli_name) if c_cli_name in cli_opts else 0
                        ue_cli = d_c2.selectbox("Client Work Site *", cli_opts if cli_opts else ["No Client"], index=cli_idx)

                        d_c3, d_c4 = st.columns(2)
                        ue_dept = d_c3.text_input("Department", value=curr_emp.get("department") or "Facility")
                        ue_zone = d_c4.text_input("Zone", value=curr_emp.get("zone") or "Zone - 3")

                        st.write("##### 3. Shift & Commercials")
                        s_c1, s_c2, s_c3 = st.columns(3)
                        curr_shift = curr_emp.get("shift_timing") or STANDARD_SHIFTS[0]
                        shift_idx = STANDARD_SHIFTS.index(curr_shift) if curr_shift in STANDARD_SHIFTS else 0
                        ue_shift = s_c1.selectbox("Assigned Shift *", STANDARD_SHIFTS, index=shift_idx)

                        wo_opts = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
                        curr_wo = curr_emp.get("weekly_off_day") or "Sunday"
                        wo_idx = wo_opts.index(curr_wo) if curr_wo in wo_opts else 0
                        ue_wo = s_c2.selectbox("Weekly Off Day *", wo_opts, index=wo_idx)

                        raw_j = curr_emp.get("joining_date") or curr_emp.get("created_at")
                        def_j = datetime.strptime(str(raw_j).split("T")[0], "%Y-%m-%d").date() if raw_j else date.today()
                        ue_join = s_c3.date_input("Joining Date *", value=def_j, format="DD/MM/YYYY")

                        s_c4, s_c5, s_c6 = st.columns(3)
                        ue_desig = s_c4.text_input("Designation *", value=curr_emp.get("designation") or "Associate")
                        cat_opts = ["Skilled", "Semi-Skilled", "Unskilled"]
                        curr_cat = curr_emp.get("category") or "Semi-Skilled"
                        cat_idx = cat_opts.index(curr_cat) if curr_cat in cat_opts else 1
                        ue_cat = s_c5.selectbox("Category *", cat_opts, index=cat_idx)
                        ue_ot = s_c6.number_input("Custom OT Rate / Hour", min_value=0.0, step=10.0, value=float(curr_emp.get("ot_rate_per_hour") or 0.0))

                        st.write("##### 4. Personal Info")
                        p_c1, p_c2, p_c3 = st.columns(3)
                        ue_name = p_c1.text_input("Full Name *", value=curr_emp.get("full_name", ""))
                        ue_father = p_c2.text_input("Father's Name", value=curr_emp.get("father_name", ""))
                        ue_gender = p_c3.selectbox("Gender", ["Male", "Female", "Other"], index=["Male", "Female", "Other"].index(curr_emp.get("gender", "Male")) if curr_emp.get("gender") in ["Male", "Female", "Other"] else 0)

                        p_c4, p_c5, p_c6 = st.columns(3)
                        raw_dob = curr_emp.get("dob")
                        def_dob = datetime.strptime(str(raw_dob).split("T")[0], "%Y-%m-%d").date() if raw_dob else date(1995, 1, 1)
                        ue_dob = p_c4.date_input("Date of Birth (DOB)", value=def_dob, format="DD/MM/YYYY")
                        ue_marital = p_c5.selectbox("Marital Status", ["Single", "Married"], index=0 if curr_emp.get("marital_status") == "Single" else 1)
                        ue_phone = p_c6.text_input("Mobile Number *", value=curr_emp.get("phone_number", ""))

                        p_c7, p_c8 = st.columns(2)
                        ue_emg = p_c7.text_input("Emergency Contact", value=curr_emp.get("emergency_contact", ""))
                        ue_addr = p_c8.text_area("Permanent Address *", value=curr_emp.get("permanent_address", ""))

                        st.write("##### 5. Statutory & Identification")
                        st1, st2, st3, st4 = st.columns(4)
                        ue_aadhar = st1.text_input("Aadhaar Number *", value="[Aadhaar Redacted]")
                        ue_pan = st2.text_input("PAN Number", value=curr_emp.get("pan_number", ""))
                        ue_uan = st3.text_input("UAN Number", value=curr_emp.get("uan_number", ""))
                        ue_esic = st4.text_input("ESIC Number", value=curr_emp.get("esic_number", ""))

                        st.write("##### 6. Bank Account Details")
                        bk1, bk2, bk3, bk4 = st.columns(4)
                        ue_bank = bk1.text_input("Bank Name", value=curr_emp.get("bank_name", ""))
                        ue_branch = bk2.text_input("Branch Name", value=curr_emp.get("bank_branch", ""))
                        ue_acc = bk3.text_input("Bank Account Number", value=curr_emp.get("bank_account_no", ""))
                        ue_ifsc = bk4.text_input("IFSC Code", value=curr_emp.get("ifsc_code", ""))

                        if st.form_submit_button("Update Employee Record", type="primary"):
                            if ue_code:
                                dup_other = supabase.table("employees").select("id").eq("employee_code", ue_code).neq("id", curr_emp["id"]).execute().data
                                if dup_other:
                                    st.error(f"Error: Employee Code '{ue_code}' is already assigned to another employee!")
                                    st.stop()

                            supabase.table("employees").update({
                                "employee_code": ue_code, "user_id": ue_uid, "password": ue_pwd,
                                "entity_id": e_map.get(ue_ent), "client_id": c_map.get(ue_cli),
                                "department": ue_dept, "zone": ue_zone, "shift_timing": ue_shift,
                                "weekly_off_day": ue_wo, "joining_date": str(ue_join),
                                "designation": ue_desig, "category": ue_cat,
                                "ot_rate_per_hour": ue_ot if ue_ot > 0 else None,
                                "full_name": ue_name, "father_name": ue_father, "gender": ue_gender,
                                "dob": str(ue_dob), "marital_status": ue_marital, "phone_number": ue_phone,
                                "emergency_contact": ue_emg, "permanent_address": ue_addr,
                                "aadhar_number": "[Aadhaar Redacted]", "pan_number": ue_pan, "uan_number": ue_uan,
                                "esic_number": ue_esic, "bank_name": ue_bank, "bank_branch": ue_branch,
                                "bank_account_no": ue_acc, "ifsc_code": ue_ifsc
                            }).eq("id", curr_emp["id"]).execute()
                            st.cache_data.clear()
                            st.toast("✅ Employee record updated successfully!")
                            st.success("All details updated!")
                            pytime.sleep(1)
                            st.rerun()
                else:
                    st.info("No employee records found.")

            with tab_vault:
                st.write("##### Complete 6-Documents Vault (Upload + Preview / Download with Max 2MB)")
                if all_emps:
                    emp_lookup = {f"[{emp.get('employee_code', 'TEMP')}] {emp.get('full_name')}": emp for emp in all_emps}
                    sel_v_emp = st.selectbox("Select Employee for Documents Vault *", list(emp_lookup.keys()))
                    v_emp = emp_lookup[sel_v_emp]
                    v_id = v_emp["id"]

                    v_ent_obj = next((e for e in ent_list if e["id"] == v_emp.get("entity_id")), None)
                    v_cli_name = next((c["name"] for c in cli_list if c["id"] == v_emp.get("client_id")), "Client Site")
                    v_sal_rule = get_exact_salary_rule(v_emp.get("entity_id"), v_emp.get("client_id"), v_emp.get("designation"), v_emp.get("category"))

                    st.markdown("#### 1. Official Letters & Certificates")
                    v1, v2 = st.columns(2)
                    with v1:
                        st.markdown("##### 1. Official Offer Letter")
                        offer_pdf = generate_official_offer_letter(v_emp, v_ent_obj, v_cli_name, v_sal_rule)
                        st.download_button("Download System-Generated Offer Letter (PDF)", data=offer_pdf, file_name=f"Offer_{v_emp.get('employee_code')}.pdf", mime="application/pdf", key=f"dl_off_{v_id}")
                        
                        up_custom_offer = st.file_uploader("Upload Signed Custom Offer Letter (Max 2MB)", type=["pdf", "jpg", "png"], key=f"up_custom_off_{v_id}")
                        if st.button("Save Custom Offer Letter", key=f"btn_cust_off_{v_id}"):
                            if up_custom_offer and upload_employee_doc(up_custom_offer, v_id, "offer"):
                                st.success("Custom Offer Letter uploaded!")
                                st.rerun()

                    with v2:
                        st.markdown("##### 2. ESIC Certificate / Card")
                        st.download_button("Download ESIC Certificate (PDF)", data=b"ESIC Certificate Document", file_name=f"ESIC_{v_emp.get('employee_code')}.pdf", mime="application/pdf", key=f"dl_esic_{v_id}")
                        
                        up_esic_doc = st.file_uploader("Upload Manual ESIC Card / Document (Max 2MB)", type=["pdf", "jpg", "png"], key=f"up_esic_doc_{v_id}")
                        if st.button("Save ESIC Document", key=f"btn_esic_doc_{v_id}"):
                            if up_esic_doc and upload_employee_doc(up_esic_doc, v_id, "esic"):
                                st.success("ESIC Document uploaded!")
                                st.rerun()

                    st.write("---")
                    st.markdown("#### 2. Statutory Identification & Bank Proofs")
                    d_c1, d_c2 = st.columns(2)
                    with d_c1:
                        st.markdown("##### 3. Passport Size Photo")
                        if v_emp.get("photo_file"): st.markdown(f"📷 [View Current Photo]({v_emp['photo_file']})")
                        up_ph = st.file_uploader("Upload New Photo (Max 2MB)", type=["jpg", "png"], key=f"v_ph_{v_id}")
                        if st.button("Save Photo", key=f"btn_ph_{v_id}"):
                            if up_ph and upload_employee_doc(up_ph, v_id, "photo"):
                                st.success("Photo uploaded!")
                                st.rerun()

                    with d_c2:
                        st.markdown("##### 4. Aadhaar Card Copy")
                        if v_emp.get("aadhar_file"): st.markdown(f"📄 [View Current Aadhaar]({v_emp['aadhar_file']})")
                        up_adh = st.file_uploader("Upload New Aadhaar Copy (Max 2MB)", type=["pdf", "jpg", "png"], key=f"v_adh_{v_id}")
                        if st.button("Save Aadhaar Copy", key=f"btn_adh_{v_id}"):
                            if up_adh and upload_employee_doc(up_adh, v_id, "aadhar"):
                                st.success("Aadhaar Card uploaded!")
                                st.rerun()

                    d_c3, d_c4 = st.columns(2)
                    with d_c3:
                        st.markdown("##### 5. PAN Card Copy")
                        if v_emp.get("pan_file"): st.markdown(f"📄 [View Current PAN]({v_emp['pan_file']})")
                        up_pn = st.file_uploader("Upload New PAN Copy (Max 2MB)", type=["pdf", "jpg", "png"], key=f"v_pn_{v_id}")
                        if st.button("Save PAN Copy", key=f"btn_pn_{v_id}"):
                            if up_pn and upload_employee_doc(up_pn, v_id, "pan"):
                                st.success("PAN Card uploaded!")
                                st.rerun()

                    with d_c4:
                        st.markdown("##### 6. Bank Passbook / Cheque")
                        if v_emp.get("bank_file"): st.markdown(f"📄 [View Current Bank Proof]({v_emp['bank_file']})")
                        up_bk = st.file_uploader("Upload New Bank Proof (Max 2MB)", type=["pdf", "jpg", "png"], key=f"v_bk_{v_id}")
                        if st.button("Save Bank Proof", key=f"btn_bk_{v_id}"):
                            if up_bk and upload_employee_doc(up_bk, v_id, "bank"):
                                st.success("Bank Document uploaded!")
                                st.rerun()
                else:
                    st.info("No employee records found.")

            with tab_exit_emp:
                st.write("##### Employee Exit & Deletion Management")
                if all_emps:
                    emp_del_map = {f"[{e.get('employee_code', 'TEMP')}] {e.get('full_name')} (Status: {e.get('status')})": e for e in all_emps}
                    sel_del_label = st.selectbox("Select Employee for Exit or Deletion *", list(emp_del_map.keys()))
                    target_emp = emp_del_map[sel_del_label]
                    target_id = target_emp["id"]

                    st.markdown(f"""
                    <div style="background-color:#F8FAFC; border:1px solid #E2E8F0; padding:12px; border-radius:6px; margin-bottom:15px;">
                        <b>Employee:</b> {target_emp.get('full_name')} | <b>Code:</b> {target_emp.get('employee_code')}<br/>
                        <b>Entity:</b> {e_rev_map.get(target_emp.get('entity_id'), 'N/A')} | <b>Client Site:</b> {c_rev_map.get(target_emp.get('client_id'), 'N/A')}<br/>
                        <b>Current Status:</b> <span style="font-weight:bold; color:#0284C7;">{target_emp.get('status')}</span>
                    </div>
                    """, unsafe_allow_html=True)

                    exit_col, del_col = st.columns(2)
                    with exit_col:
                        st.markdown("#### Option A: Mark as LEFT / RESIGNED")
                        st.caption("Recommended: Employee access is deactivated, but past payroll, attendance and statutory records are permanently preserved.")
                        with st.form("mark_left_form"):
                            ex_date = st.date_input("Exit Date / Last Working Day *", value=date.today())
                            ex_reason = st.selectbox("Reason for Leaving *", ["Resigned", "Absconding", "Terminated", "Medical Grounds", "Contract End", "Other"])
                            ex_remarks = st.text_area("Exit Remarks")
                            if st.form_submit_button("Mark Employee as LEFT", type="primary"):
                                supabase.table("employees").update({
                                    "status": "LEFT",
                                    "admin_remarks": f"LEFT on {ex_date} | Reason: {ex_reason} | Remarks: {ex_remarks}"
                                }).eq("id", target_id).execute()
                                st.cache_data.clear()
                                st.toast("✅ Employee marked as LEFT!")
                                st.success(f"{target_emp.get('full_name')} marked as LEFT. Login access disabled; records safely retained.")
                                pytime.sleep(1)
                                st.rerun()

                    with del_col:
                        st.markdown("#### Option B: Permanent Hard Delete")
                        st.caption("Warning: Use only for erroneous / wrong entries. All records of this employee will be permanently purged.")
                        st.warning("⚠️ This action will completely erase this employee record from the database!")
                        with st.form("hard_delete_form"):
                            confirm_chk = st.checkbox("I confirm that I want to permanently delete this employee record.")
                            if st.form_submit_button("Confirm Permanent Delete"):
                                if not confirm_chk:
                                    st.error("Please tick the confirmation checkbox to delete!")
                                else:
                                    supabase.table("employees").delete().eq("id", target_id).execute()
                                    st.cache_data.clear()
                                    st.toast("🗑️ Employee record permanently purged!")
                                    st.warning("Employee permanently deleted!")
                                    pytime.sleep(1)
                                    st.rerun()
                else:
                    st.info("No employee records found.")

        # PANEL 4: LEAVE APPROVALS DESK
        elif selected_panel == "Leave Approvals Desk":
            st.subheader("Employee Leave Requests & Quota Ledger")
            today_date = date.today()
            today_str = str(today_date)
            cur_yr = today_date.year

            all_leaves = supabase.table("leave_requests").select("*").order("created_at", desc=True).execute().data or []
            emp_res = fetch_cached_employees()
            emp_map = {e["id"]: e for e in emp_res}
            ent_res = fetch_cached_entities()
            ent_map = {e["id"]: e["name"] for e in ent_res}
            cli_res = fetch_cached_clients()
            cli_map = {c["id"]: c["name"] for c in cli_res}

            pending_leaves = [lv for lv in all_leaves if lv.get("status") in ["PENDING_SUPERVISOR", "PENDING_ADMIN"]]
            approved_this_mo = [
                lv for lv in all_leaves 
                if lv.get("status") == "APPROVED" and str(lv.get("start_date", ""))[:7] == today_str[:7]
            ]
            rejected_leaves = [lv for lv in all_leaves if lv.get("status") == "REJECTED"]
            on_leave_today = [
                lv for lv in all_leaves 
                if lv.get("status") == "APPROVED" and str(lv.get("start_date", "")) <= today_str <= str(lv.get("end_date", ""))
            ]

            lm1, lm2, lm3, lm4 = st.columns(4)
            lm1.markdown(f'<div class="kpi-metric-box"><span style="color:#D97706; font-size:12px; font-weight:700;">PENDING APPROVALS</span><h2 style="color:#D97706; margin:4px 0;">{len(pending_leaves)}</h2></div>', unsafe_allow_html=True)
            lm2.markdown(f'<div class="kpi-metric-box"><span style="color:#059669; font-size:12px; font-weight:700;">APPROVED THIS MONTH</span><h2 style="color:#059669; margin:4px 0;">{len(approved_this_mo)}</h2></div>', unsafe_allow_html=True)
            lm3.markdown(f'<div class="kpi-metric-box"><span style="color:#DC2626; font-size:12px; font-weight:700;">REJECTED LEAVES</span><h2 style="color:#DC2626; margin:4px 0;">{len(rejected_leaves)}</h2></div>', unsafe_allow_html=True)
            lm4.markdown(f'<div class="kpi-metric-box"><span style="color:#1E3A8A; font-size:12px; font-weight:700;">ON LEAVE TODAY</span><h2 style="color:#1E3A8A; margin:4px 0;">{len(on_leave_today)}</h2></div>', unsafe_allow_html=True)

            st.write("---")
            tab_lv_pend, tab_lv_ledger, tab_lv_hist = st.tabs([
                "⏳ Pending Leave Requests", 
                "📊 Employee-Wise Leave Ledger", 
                "📜 Leave History & Audit Trail"
            ])

            with tab_lv_pend:
                st.write("##### Review & Decision Action Desk")
                if pending_leaves:
                    for lv in pending_leaves:
                        lv_id = lv["id"]
                        e_id = lv["employee_id"]
                        emp_obj = emp_map.get(e_id, {})
                        emp_name = emp_obj.get("full_name", "Unknown Employee")
                        emp_code = emp_obj.get("employee_code", "TEMP")
                        ent_title = ent_map.get(emp_obj.get("entity_id"), "Company")
                        cli_title = cli_map.get(emp_obj.get("client_id"), "Plant Site")

                        bal_recs = supabase.table("leave_balances").select("*").eq("employee_id", e_id).execute().data
                        if bal_recs:
                            b_data = bal_recs[0]
                            tot_c = float(b_data.get("total_credited", 15.0))
                            used_l = float(b_data.get("used_leaves", 0.0))
                            bal_l = float(b_data.get("balance_leaves", 15.0))
                        else:
                            tot_c, used_l, bal_l = 15.0, 0.0, 15.0

                        with st.expander(f"[{emp_code}] {emp_name} | {ent_title} - {cli_title} | Type: {lv.get('leave_type')} ({lv.get('total_days')} Days)"):
                            col_info1, col_info2 = st.columns(2)
                            with col_info1:
                                st.write(f"**Leave Duration:** {lv.get('start_date')} to {lv.get('end_date')} ({lv.get('total_days')} Day(s))")
                                st.write(f"**Applied Leave Type:** `{lv.get('leave_type')}`")
                                st.write(f"**Reason for Leave:** {lv.get('reason')}")
                                if lv.get("document_file"):
                                    st.markdown(f"📄 [View Attached Proof Document (Max 2MB)]({lv['document_file']})")
                                else:
                                    st.caption("No Medical / Proof Document attached.")

                            with col_info2:
                                st.markdown(f"""
                                <div style="background:#F8FAFC; border:1px solid #E2E8F0; padding:10px; border-radius:6px;">
                                    <b>Live Leave Balance Snapshot:</b><br/>
                                    • Annual Entitlement Quota: <b>{tot_c:.1f} Days</b><br/>
                                    • Leaves Used: <b>{used_l:.1f} Days</b><br/>
                                    • Leaves Available Balance: <b style="color:#059669;">{bal_l:.1f} Days</b>
                                </div>
                                """, unsafe_allow_html=True)

                            st.write("---")
                            st.write("##### Leave Decision Action")
                            rej_reason = st.text_input("Rejection Reason (Mandatory if Rejecting)", key=f"rej_note_{lv_id}")

                            btn_l1, btn_l2 = st.columns(2)
                            if btn_l1.button("Approve Leave", key=f"btn_app_{lv_id}", type="primary"):
                                supabase.table("leave_requests").update({
                                    "status": "APPROVED",
                                    "admin_remarks": "Approved by Admin"
                                }).eq("id", lv_id).execute()

                                if bal_recs:
                                    new_used = used_l + float(lv.get("total_days", 1.0))
                                    new_bal = max(0.0, tot_c - new_used)
                                    supabase.table("leave_balances").update({
                                        "used_leaves": new_used,
                                        "balance_leaves": new_bal
                                    }).eq("id", b_data["id"]).execute()

                                st.toast("✅ Leave Approved successfully!")
                                st.success(f"Leave approved for {emp_name}!")
                                pytime.sleep(1)
                                st.rerun()

                            if btn_l2.button("Reject Leave", key=f"btn_rej_{lv_id}"):
                                if not rej_reason.strip():
                                    st.error("Please enter a rejection reason before rejecting!")
                                else:
                                    supabase.table("leave_requests").update({
                                        "status": "REJECTED",
                                        "admin_remarks": rej_reason.strip()
                                    }).eq("id", lv_id).execute()
                                    st.toast("Leave Rejected!")
                                    st.warning("Leave request marked as REJECTED.")
                                    pytime.sleep(1)
                                    st.rerun()
                else:
                    st.info("No pending leave applications for review.")

            with tab_lv_ledger:
                st.write("##### Annual Leave Quota & Balances Ledger")
                all_balances = supabase.table("leave_balances").select("*").execute().data or []
                bal_lookup = {b["employee_id"]: b for b in all_balances}

                act_emps = [e for e in emp_res if e.get("role") == "employee"]
                if act_emps:
                    ledger_data = []
                    for idx, e in enumerate(act_emps, start=1):
                        e_b = bal_lookup.get(e["id"], {})
                        tot_q = float(e_b.get("total_credited", 15.0))
                        usd_l = float(e_b.get("used_leaves", 0.0))
                        rem_b = float(e_b.get("balance_leaves", 15.0))
                        
                        lwp_count = len([
                            l for l in all_leaves 
                            if l.get("employee_id") == e["id"] and l.get("status") == "APPROVED" and l.get("leave_type") == "LWP"
                        ])

                        ledger_data.append({
                            "SR.NO": idx,
                            "Employee ID No": e.get("employee_code", "TEMP"),
                            "Name Of Employee": e.get("full_name"),
                            "Entity / Firm": ent_map.get(e.get("entity_id"), "N/A"),
                            "Client Work Site": cli_map.get(e.get("client_id"), "N/A"),
                            "Annual Entitlement": f"{tot_q:.1f} Days",
                            "Monthly Accrued": "1.5 Days/mo",
                            "Used Leaves": f"{usd_l:.1f} Days",
                            "Balance Leaves": f"{rem_b:.1f} Days",
                            "LWP Days": lwp_count
                        })

                    st.dataframe(pd.DataFrame(ledger_data), use_container_width=True)

                    st.write("---")
                    st.write("##### Manual Leave Quota Adjustment")
                    with st.form("manual_adjust_leave_quota"):
                        adj_e_map = {f"[{e.get('employee_code', 'TEMP')}] {e.get('full_name')}": e["id"] for e in act_emps}
                        sel_adj_e = st.selectbox("Select Employee to Adjust Quota", list(adj_e_map.keys()))
                        adj_c1, adj_c2 = st.columns(2)
                        new_quota = adj_c1.number_input("Updated Total Credited Quota", min_value=0.0, max_value=30.0, step=0.5, value=15.0)
                        adj_used = adj_c2.number_input("Updated Used Leaves", min_value=0.0, max_value=30.0, step=0.5, value=0.0)

                        if st.form_submit_button("Update Leave Quota", type="primary"):
                            target_e_id = adj_e_map[sel_adj_e]
                            supabase.table("leave_balances").upsert({
                                "employee_id": target_e_id,
                                "year": cur_yr,
                                "total_credited": new_quota,
                                "used_leaves": adj_used,
                                "balance_leaves": max(0.0, new_quota - adj_used),
                                "last_credited_month": today_date.month
                            }, on_conflict="employee_id").execute()
                            st.toast("✅ Quota ledger adjusted!")
                            st.success(f"Leave balances updated for {sel_adj_e}!")
                            pytime.sleep(1)
                            st.rerun()
                else:
                    st.info("No employee records found.")

            with tab_lv_hist:
                st.write("##### Processed Leave History & Archive")
                hist_leaves = [lv for lv in all_leaves if lv.get("status") in ["APPROVED", "REJECTED"]]
                if hist_leaves:
                    hist_data = []
                    for lv in hist_leaves:
                        emp_obj = emp_map.get(lv.get("employee_id"), {})
                        hist_data.append({
                            "Request ID": lv["id"][:8],
                            "Employee": f"[{emp_obj.get('employee_code', 'TEMP')}] {emp_obj.get('full_name', 'N/A')}",
                            "Leave Type": lv.get("leave_type"),
                            "Date Range": f"{lv.get('start_date')} to {lv.get('end_date')}",
                            "Total Days": lv.get("total_days"),
                            "Status": lv.get("status"),
                            "Reason": lv.get("reason"),
                            "Admin Remarks": lv.get("admin_remarks") or "-"
                        })
                    df_hist = pd.DataFrame(hist_data)
                    st.dataframe(df_hist, use_container_width=True)

                    csv_leave_hist = df_hist.to_csv(index=False).encode('utf-8')
                    st.download_button("Download Leave History (CSV)", data=csv_leave_hist, file_name=f"Leave_History_{today_str}.csv", mime="text/csv")
                else:
                    st.info("No processed leave history records yet.")

        # PANEL 5: SHIFT ROSTER MANAGEMENT
        elif selected_panel == "Shift Roster Management":
            st.subheader("Shift Roster Management (Bulk & Individual Deployment)")
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_map = {e["name"]: e["id"] for e in ent_list}
            c_map = {c["name"]: c["id"] for c in cli_list}

            f_col1, f_col2, f_col3 = st.columns(3)
            sel_r_ent = f_col1.selectbox("Select Entity / Firm *", list(e_map.keys()) if e_map else ["No Entity"])
            
            matched_clis = [c for c in cli_list if c.get("entity_id") == e_map.get(sel_r_ent)]
            matched_c_map = {c["name"]: c["id"] for c in matched_clis}
            sel_r_cli = f_col2.selectbox("Select Client Plant Site *", list(matched_c_map.keys()) if matched_c_map else ["No Client"])

            sel_scope = st.radio("Target Period Scope", ["Full Month", "Weekly Range (7 Days)", "Single Date"], horizontal=True)

            target_dates = []
            if sel_scope == "Full Month":
             r_month_input = st.date_input("Select Target Month (Any date in month)", value=date.today())
             yr = r_month_input.year
             mo = r_month_input.month
             days_in_m = 31 if mo in [1,3,5,7,8,10,12] else (30 if mo != 2 else (29 if yr % 4 == 0 else 28))
             target_dates = [str(date(yr, mo, d)) for d in range(1, days_in_m + 1)]
            elif sel_scope == "Weekly Range (7 Days)":
               week_start = st.date_input("Select Week Start Date (Monday / Any day)", value=date.today())
               target_dates = [str(week_start + timedelta(days=i)) for i in range(7)]
               st.caption(f"Deployment configured for week: {week_start} to {week_start + timedelta(days=6)}")
            else:
              single_d = st.date_input("Select Target Date", value=date.today())
              target_dates = [str(single_d)]

            st.write("---")
            site_emps = []
            if sel_r_ent in e_map and sel_r_cli in matched_c_map:
                site_emps = [
                    e for e in fetch_cached_employees() 
                    if e.get("entity_id") == e_map[sel_r_ent] and e.get("client_id") == matched_c_map[sel_r_cli] and e.get("role") == "employee" and e.get("status") == "APPROVED"
                ]

            if site_emps:
                tab_deploy, tab_grid_view, tab_export = st.tabs([
                    "⚡ Smart Roster Deployment", 
                    "📋 Interactive Monthly Roster Grid", 
                    "📤 Roster Export & Print"
                ])

                with tab_deploy:
                    st.write(f"##### Deployed Workers Roster Setup ({len(site_emps)} Active Staff)")

                    st.markdown("""
                        <link rel="manifest" href="./static/manifest.json">
                        <meta name="theme-color" content="#1E3A8A">
                        <meta name="mobile-web-app-capable" content="yes">
                         <meta name="apple-mobile-web-app-capable" content="yes">
                         <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
                         <link rel="apple-touch-icon" href="./static/appstore-images/android/launchericon-192.png">
                    """, unsafe_allow_html=True)

                    bulk_c1, bulk_c2, bulk_c3 = st.columns([2, 1.5, 2.5])
                    master_shift_choice = bulk_c1.selectbox("Master Shift to Apply", STANDARD_SHIFTS, key="master_shift_picker")
                    preserve_wo = bulk_c3.checkbox("Preserve Worker's Profile Weekly Off Day", value=True)

                    if bulk_c2.button("⚡ Apply to All", key="btn_apply_all"):
                        for emp in site_emps:
                            st.session_state[f"row_shift_{emp['id']}"] = master_shift_choice
                        st.toast(f"Applied '{master_shift_choice}' to all worker rows below!")

                    st.write("##### 3. Individual Employee-Wise Shift Control")
                    with st.form("deploy_complete_roster_form"):
                        assigned_row_shifts = {}
                        for idx, emp in enumerate(site_emps, start=1):
                            emp_id = emp["id"]
                            emp_code = emp.get("employee_code", "TEMP")
                            emp_name = emp.get("full_name")
                            emp_desig = emp.get("designation", "Associate")
                            emp_cat = emp.get("category", "Semi-Skilled")
                            emp_wo_day = emp.get("weekly_off_day", "Sunday")

                            col_e1, col_e2, col_e3, col_e4 = st.columns([1, 4, 3, 4])
                            col_e1.write(f"**#{idx}**")
                            col_e2.write(f"**[{emp_code}] {emp_name}**")
                            col_e3.write(f"{emp_desig} ({emp_cat}) | WO: {emp_wo_day}")

                            def_shift = st.session_state.get(f"row_shift_{emp_id}") or emp.get("shift_timing") or STANDARD_SHIFTS[0]
                            shift_index = STANDARD_SHIFTS.index(def_shift) if def_shift in STANDARD_SHIFTS else 0

                            row_val = col_e4.selectbox(
                                "Shift", 
                                STANDARD_SHIFTS, 
                                index=shift_index, 
                                key=f"row_shift_input_{emp_id}", 
                                label_visibility="collapsed"
                            )
                            assigned_row_shifts[emp_id] = (row_val, emp_wo_day)

                        st.write("---")
                        if st.form_submit_button("Deploy & Save Complete Plant Roster", type="primary"):
                            curr_cli_id = matched_c_map[sel_r_cli]
                            saved_count = 0
                            
                            for emp_id, (chosen_shift, profile_wo) in assigned_row_shifts.items():
                                for t_date_str in target_dates:
                                    d_dt = datetime.strptime(t_date_str, "%Y-%m-%d").date()
                                    day_name = d_dt.strftime("%A")

                                    final_shift = "Week Off" if (preserve_wo and day_name == profile_wo) else chosen_shift

                                    supabase.table("shift_roster").upsert({
                                        "client_id": curr_cli_id,
                                        "employee_id": emp_id,
                                        "roster_date": t_date_str,
                                        "shift_name": final_shift
                                    }, on_conflict="employee_id,roster_date").execute()
                                    saved_count += 1

                            st.toast("✅ Plant Shift Roster Deployed Successfully!")
                            st.success(f"Roster saved for all {len(site_emps)} staff across {len(target_dates)} date(s)! (Total records: {saved_count})")
                            pytime.sleep(1)
                            st.rerun()

                with tab_grid_view:
                    st.write(f"##### Plant Roster Grid: **{sel_r_cli}**")
                    curr_cli_id = matched_c_map[sel_r_cli]
                    
                    saved_roster = supabase.table("shift_roster").select("*").eq("client_id", curr_cli_id).in_("roster_date", target_dates).execute().data or []
                    roster_dict = {(r["employee_id"], r["roster_date"]): r["shift_name"] for r in saved_roster}

                    grid_rows = []
                    for idx, emp in enumerate(site_emps, start=1):
                        row_dict = {
                            "SR.NO": idx,
                            "Emp Code": emp.get("employee_code", "TEMP"),
                            "Employee Name": emp.get("full_name"),
                            "Designation": emp.get("designation", "Associate"),
                            "Category": emp.get("category", "Semi-Skilled")
                        }
                        for t_date in target_dates:
                            day_label = t_date[-2:]
                            s_name = roster_dict.get((emp["id"], t_date), "-")
                            s_short = "G" if "General" in s_name else ("A" if "Shift A" in s_name else ("B" if "Shift B" in s_name else ("C" if "Shift C" in s_name else ("WO" if "Week Off" in s_name else s_name))))
                            row_dict[day_label] = s_short

                        grid_rows.append(row_dict)

                    df_grid = pd.DataFrame(grid_rows)
                    st.dataframe(df_grid, use_container_width=True)

                with tab_export:
                    st.write(f"##### Export Plant Shift Roster for Client / Gate Audit")
                    if grid_rows:
                        csv_roster = pd.DataFrame(grid_rows).to_csv(index=False).encode('utf-8')
                        st.download_button(
                            "Download Official Shift Roster (CSV)",
                            data=csv_roster,
                            file_name=f"Shift_Roster_{sel_r_cli}_{sel_r_ent}_{target_dates[0]}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("No roster grid records to export.")
            else:
                st.info("No approved workers deployed under selected Entity and Client Plant Site.")

        # PANEL 6: SALARY STRUCTURE RULES
        elif selected_panel == "Salary Structure Rules":
            st.subheader("Configure Salary Structure & CTC Rules (Entity & Client Wise)")

            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            ent_opts = {e["name"]: e["id"] for e in ent_list}
            cli_opts = {c["name"]: c["id"] for c in cli_list}
            e_rev_lookup = {e["id"]: e["name"] for e in ent_list}
            c_rev_lookup = {c["id"]: c["name"] for c in cli_list}

            tab_sal_add, tab_sal_manage = st.tabs([
                "➕ Define Salary Structure Rule", 
                "📋 Manage / Edit Existing Salary Rules"
            ])

            with tab_sal_add:
                st.write("##### 1. Hierarchy Mapping & Classification")
                with st.form("define_salary_rule_full_form"):
                    h1, h2 = st.columns(2)
                    r_ent = h1.selectbox("Entity / Firm *", options=list(ent_opts.keys()) if ent_opts else ["No Entity"])
                    
                    selected_e_id = ent_opts.get(r_ent)
                    matched_clis = [c for c in cli_list if c.get("entity_id") == selected_e_id]
                    matched_cli_opts = {c["name"]: c["id"] for c in matched_clis}
                    r_cli = h2.selectbox("Client Work Site *", options=list(matched_cli_opts.keys()) if matched_cli_opts else (list(cli_opts.keys()) if cli_opts else ["No Client"]))

                    h3, h4, h5 = st.columns(3)
                    r_desig = h3.text_input("Designation *", value="Associate")
                    r_cat = h4.selectbox("Category *", ["Skilled", "Semi-Skilled", "Unskilled"], index=1)
                    r_zone = h5.selectbox("Zone *", ["Zone - 1", "Zone - 2", "Zone - 3"], index=2)

                    st.write("---")
                    st.write("##### 2. Gross Earnings Rate (Monthly Rates & OT)")
                    e1, e2, e3 = st.columns(3)
                    r_basic = e1.number_input("Basic Pay (Rs./Month) *", min_value=0.0, step=100.0, value=13805.0)
                    r_da = e2.number_input("Dearness Allowance - DA (Rs./Month) *", min_value=0.0, step=50.0, value=2511.0)
                    r_hra = e3.number_input("House Rent Allowance - HRA (Rs./Month) *", min_value=0.0, step=50.0, value=816.0)

                    e4, e5 = st.columns(2)
                    r_other = e4.number_input("Other / Special Allowance (Rs./Month)", min_value=0.0, step=50.0, value=0.0)
                    r_ot = e5.number_input("Overtime Rate Per Hour (Rs./Hour) *", min_value=0.0, step=5.0, value=86.0)

                    gross_monthly = r_basic + r_da + r_hra + r_other
                    per_day_rate = round(gross_monthly / 26.0, 2)

                    st.markdown(f"""
                    <div style="background:#F8FAFC; border:1px solid #CBD5E1; padding:10px 14px; border-radius:6px; margin: 8px 0px;">
                        <b>Computed Earnings Summary:</b> Total Monthly Gross Wages: <b style="color:#1E3A8A;">Rs. {gross_monthly:,.2f}</b> | 
                        Per Day Rate (26 Working Days): <b style="color:#059669;">Rs. {per_day_rate:,.2f}/Day</b>
                    </div>
                    """, unsafe_allow_html=True)

                    st.write("---")
                    st.write("##### 3. Employee Statutory Deductions Rate")
                    d1, d2, d3, d4 = st.columns(4)
                    r_pf_pct = d1.number_input("Employee PF Rate (%) *", min_value=0.0, max_value=25.0, step=0.5, value=12.0)
                    r_esic_pct = d2.number_input("Employee ESIC Rate (%) *", min_value=0.0, max_value=10.0, step=0.05, value=0.75)
                    r_pt_amt = d3.number_input("Professional Tax - PT (Rs./Month) *", min_value=0.0, step=25.0, value=200.0)
                    r_mlwf_ee = d4.number_input("Employee MLWF (Rs./Month)", min_value=0.0, step=1.0, value=0.0)

                    st.write("---")
                    st.write("##### 4. Employer Contributions & Full CTC Configuration")
                    er1, er2, er3, er4 = st.columns(4)
                    r_er_pf_pct = er1.number_input("Employer PF Rate (%) *", min_value=0.0, max_value=25.0, step=0.5, value=13.0)
                    r_er_esic_pct = er2.number_input("Employer ESIC Rate (%) *", min_value=0.0, max_value=10.0, step=0.05, value=3.25)
                    r_er_mlwf = er3.number_input("Employer MLWF (Rs./Month)", min_value=0.0, step=1.0, value=0.0)
                    r_bonus = er4.number_input("Statutory Bonus (Rs./Month)", min_value=0.0, step=50.0, value=0.0)

                    basic_plus_da = r_basic + r_da
                    er_pf_val = min(round(basic_plus_da * (r_er_pf_pct / 100.0), 2), 1950.0)
                    er_esic_val = round(gross_monthly * (r_er_esic_pct / 100.0), 2)
                    total_monthly_ctc = round(gross_monthly + er_pf_val + er_esic_val + r_er_mlwf + r_bonus, 2)
                    total_annual_ctc = round(total_monthly_ctc * 12.0, 2)

                    st.markdown(f"""
                    <div style="background:#EFF6FF; border-left:4px solid #1E3A8A; padding:12px; border-radius:6px; margin: 12px 0px;">
                        <h5 style="margin:0 0 6px 0; color:#1E3A8A;">Live CTC Intelligence Breakdown:</h5>
                        • Gross Wages: <b>Rs. {gross_monthly:,.2f}</b> | Employer PF (13%): <b>Rs. {er_pf_val:,.2f}</b> | Employer ESIC (3.25%): <b>Rs. {er_esic_val:,.2f}</b><br/>
                        • Total Monthly CTC: <b style="color:#0F172A; font-size:16px;">Rs. {total_monthly_ctc:,.2f}</b> | 
                        Total Annual CTC: <b style="color:#059669; font-size:16px;">Rs. {total_annual_ctc:,.2f}</b>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.form_submit_button("Save Salary Structure Rule", type="primary"):
                        target_e_id = ent_opts.get(r_ent)
                        target_c_id = matched_cli_opts.get(r_cli) if r_cli in matched_cli_opts else cli_opts.get(r_cli)

                        if not target_e_id or not target_c_id or not r_desig:
                            st.error("Entity, Client Work Site and Designation are mandatory!")
                        else:
                            try:
                                supabase.table("salary_structures").insert({
                                    "entity_id": target_e_id,
                                    "client_id": target_c_id,
                                    "designation": r_desig.strip(),
                                    "category": r_cat,
                                    "basic": r_basic,
                                    "da": r_da,
                                    "hra": r_hra,
                                    "other_allowance": r_other,
                                    "ot_rate_per_hour": r_ot,
                                    "pf_percentage": r_pf_pct,
                                    "esic_percentage": r_esic_pct,
                                    "pt_amount": r_pt_amt,
                                    "employer_pf_pct": r_er_pf_pct,
                                    "employer_esic_pct": r_er_esic_pct,
                                    "statutory_bonus": r_bonus,
                                    "monthly_ctc": total_monthly_ctc,
                                    "annual_ctc": total_annual_ctc
                                }).execute()
                                st.cache_data.clear()
                                st.toast("✅ Salary Structure Rule Saved Successfully!")
                                st.success(f"Salary Rule for {r_desig} ({r_cat}) registered under {r_ent} - {r_cli}!")
                                pytime.sleep(1)
                                st.rerun()
                            except Exception as err:
                                st.error(f"Error saving salary rule: {err}")

            with tab_sal_manage:
                st.write("##### Existing Salary Structure Rules (Review, Modify & Delete)")
                all_sals = supabase.table("salary_structures").select("*").execute().data or []

                if all_sals:
                    rule_label_map = {}
                    for s in all_sals:
                        e_title = e_rev_lookup.get(s.get("entity_id"), "Entity")
                        c_title = c_rev_lookup.get(s.get("client_id"), "Site")
                        lbl = f"[{e_title} | {c_title}] - {s.get('designation')} ({s.get('category')}) - CTC: Rs.{float(s.get('monthly_ctc', 0)):,.2f}/mo"
                        rule_label_map[lbl] = s

                    sel_rule_lbl = st.selectbox("Choose Salary Rule to Modify or Delete *", list(rule_label_map.keys()))
                    curr_rule = rule_label_map[sel_rule_lbl]
                    rule_id = curr_rule["id"]

                    with st.form("edit_salary_rule_master_form"):
                        st.write("##### 1. Editable Earnings & OT Rate")
                        ue1, ue2, ue3 = st.columns(3)
                        up_b = ue1.number_input("Basic Pay (Rs.) *", min_value=0.0, step=100.0, value=float(curr_rule.get("basic", 13805.0)))
                        up_da = ue2.number_input("DA (Rs.) *", min_value=0.0, step=50.0, value=float(curr_rule.get("da", 2511.0)))
                        up_hra = ue3.number_input("HRA (Rs.) *", min_value=0.0, step=50.0, value=float(curr_rule.get("hra", 816.0)))

                        ue4, ue5 = st.columns(2)
                        up_oth = ue4.number_input("Other Allowance (Rs.)", min_value=0.0, step=50.0, value=float(curr_rule.get("other_allowance", 0.0)))
                        up_ot_rate = ue5.number_input("OT Rate / Hour (Rs.) *", min_value=0.0, step=5.0, value=float(curr_rule.get("ot_rate_per_hour", 86.0)))

                        st.write("##### 2. Editable Statutory Deductions & Contributions")
                        ud1, ud2, ud3 = st.columns(3)
                        up_pf = ud1.number_input("Employee PF (%)", min_value=0.0, step=0.5, value=float(curr_rule.get("pf_percentage", 12.0)))
                        up_esic = ud2.number_input("Employee ESIC (%)", min_value=0.0, step=0.05, value=float(curr_rule.get("esic_percentage", 0.75)))
                        up_pt = ud3.number_input("PT Amount (Rs.)", min_value=0.0, step=25.0, value=float(curr_rule.get("pt_amount", 200.0)))

                        uc1, uc2, uc3 = st.columns(3)
                        up_er_pf = uc1.number_input("Employer PF (%)", min_value=0.0, step=0.5, value=float(curr_rule.get("employer_pf_pct", 13.0)))
                        up_er_esic = uc2.number_input("Employer ESIC (%)", min_value=0.0, step=0.05, value=float(curr_rule.get("employer_esic_pct", 3.25)))
                        up_bonus = uc3.number_input("Statutory Bonus (Rs.)", min_value=0.0, step=50.0, value=float(curr_rule.get("statutory_bonus", 0.0)))

                        new_gross = up_b + up_da + up_hra + up_oth
                        new_b_plus_da = up_b + up_da
                        new_er_pf_val = min(round(new_b_plus_da * (up_er_pf / 100.0), 2), 1950.0)
                        new_er_esic_val = round(new_gross * (up_er_esic / 100.0), 2)
                        new_m_ctc = round(new_gross + new_er_pf_val + new_er_esic_val + up_bonus, 2)
                        new_a_ctc = round(new_m_ctc * 12.0, 2)

                        st.info(f"Updated Monthly CTC: Rs. {new_m_ctc:,.2f} | Annual CTC: Rs. {new_a_ctc:,.2f}")

                        st.write("---")
                        b_col1, b_col2 = st.columns(2)
                        if b_col1.form_submit_button("Update Salary Rule", type="primary"):
                            supabase.table("salary_structures").update({
                                "basic": up_b,
                                "da": up_da,
                                "hra": up_hra,
                                "other_allowance": up_oth,
                                "ot_rate_per_hour": up_ot_rate,
                                "pf_percentage": up_pf,
                                "esic_percentage": up_esic,
                                "pt_amount": up_pt,
                                "employer_pf_pct": up_er_pf,
                                "employer_esic_pct": up_er_esic,
                                "statutory_bonus": up_bonus,
                                "monthly_ctc": new_m_ctc,
                                "annual_ctc": new_a_ctc
                            }).eq("id", rule_id).execute()
                            st.cache_data.clear()
                            st.toast("✅ Salary rule updated successfully!")
                            st.success("Rule parameters refreshed!")
                            pytime.sleep(1)
                            st.rerun()

                        if b_col2.form_submit_button("Delete Salary Rule"):
                            supabase.table("salary_structures").delete().eq("id", rule_id).execute()
                            st.cache_data.clear()
                            st.toast("🗑️️ Salary rule deleted successfully!")
                            st.warning("Salary structure rule removed from database!")
                            pytime.sleep(1)
                            st.rerun()
                else:
                    st.info("No salary structure rules defined yet. Add a rule using Tab 1.")

        # PANEL 7: ATTENDANCE & OT LIVE EDIT
        elif selected_panel == "Attendance & OT Live Edit":
            st.subheader("Manual Attendance, Shift Timings & OT Management")
            
            emp_list = fetch_cached_employees()
            emp_map = {f"[{e.get('employee_code', 'TEMP')}] {e['full_name']} (ID: {e['id'][:6]})": e["id"] for e in emp_list if e.get("role") == "employee"}

            tab_att_save, tab_att_del = st.tabs(["Add / Update Attendance", "Delete Attendance Record"])

            with tab_att_save:
                with st.form("attendance_save_form_live"):
                    at1, at2, at3 = st.columns(3)
                    sel_e = at1.selectbox("Select Employee *", options=list(emp_map.keys()) if emp_map else ["No Employees"])
                    sel_d = at2.date_input("Attendance Date *", value=date.today())
                    sel_st = at3.selectbox("Status *", ["P (Present)", "A (Absent)", "WO (Week Off)", "PH (Paid Holiday)", "L (Approved Leave)", "HD (Half Day)"])
                    
                    at4, at5 = st.columns(2)
                    sel_shift_worked = at4.selectbox("Shift Worked", STANDARD_SHIFTS)
                    ot_h = at5.number_input("Overtime Hours (OT)", min_value=0.0, max_value=16.0, step=0.5, value=0.0)

                    if st.form_submit_button("Save / Update Attendance", type="primary"):
                        if emp_map:
                            st_code = sel_st[:sel_st.find(" ")]
                            supabase.table("attendance").upsert({
                                "employee_id": emp_map[sel_e], 
                                "date": str(sel_d),
                                "status": st_code, 
                                "ot_hours": ot_h, 
                                "is_valid_geo": True
                            }, on_conflict="employee_id,date").execute()
                            st.toast("✅ Attendance record saved successfully!")
                            st.success(f"Attendance logged for {sel_e} on {sel_d}!")
                            pytime.sleep(1)
                            st.rerun()

            with tab_att_del:
                with st.form("attendance_del_form_live"):
                    d_sel_e = st.selectbox("Select Employee", options=list(emp_map.keys()) if emp_map else ["No Employees"])
                    d_sel_d = st.date_input("Date to Delete", value=date.today(), key="del_att_date")
                    if st.form_submit_button("Delete Attendance Record"):
                        if emp_map:
                            supabase.table("attendance").delete().eq("employee_id", emp_map[d_sel_e]).eq("date", str(d_sel_d)).execute()
                            st.toast("🗑️ Attendance record deleted!")
                            st.warning(f"Attendance deleted for {d_sel_d}!")
                            pytime.sleep(1)
                            st.rerun()

        # PANEL 8: MONTHLY PAYROLL PROCESSING
        elif selected_panel == "Monthly Payroll Processing (43-Cols)":
            st.subheader("Monthly Payroll Engine & Wage Sheet (Exact 43 Columns Layout)")

            p_col1, p_col2, p_col3 = st.columns(3)
            sel_month = p_col1.selectbox("Select Payroll Month *", ["August 2026", "September 2026", "October 2026", "November 2026"])
            
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_opts = {e["name"]: e["id"] for e in ent_list}
            c_opts = {c["name"]: c["id"] for c in cli_list}

            sel_ent_name = p_col2.selectbox("Select Entity / Firm *", list(e_opts.keys()) if e_opts else ["No Entity"])
            sel_cli_name = p_col3.selectbox("Select Client Work Site *", list(c_opts.keys()) if c_opts else ["No Client"])

            emp_records = []
            if sel_ent_name in e_opts and sel_cli_name in c_opts:
                try:
                    emp_records = supabase.table("employees").select("*").eq("role", "employee").eq("status", "APPROVED").eq("entity_id", e_opts[sel_ent_name]).eq("client_id", c_opts[sel_cli_name]).execute().data or []
                except Exception:
                    emp_records = []

            if emp_records:
                st.write(f"##### Official 43-Column Register: **{sel_ent_name}** | Site: **{sel_cli_name}** ({len(emp_records)} Staff)")
                
                payroll_rows = []
                for idx, emp_item in enumerate(emp_records, start=1):
                    sal_struct = get_exact_salary_rule(
                        emp_item.get("entity_id"),
                        emp_item.get("client_id"),
                        emp_item.get("designation"),
                        emp_item.get("category")
                    )

                    r_basic = float(sal_struct.get("basic", 13805.0) if sal_struct else 13805.0) / 26.0
                    r_da = float(sal_struct.get("da", 2511.0) if sal_struct else 2511.0) / 26.0
                    r_hra = float(sal_struct.get("hra", 816.0) if sal_struct else 816.0) / 26.0
                    total_gros_rate = round(r_basic + r_da + r_hra, 2)
                    
                    emp_custom_ot = emp_item.get("ot_rate_per_hour")
                    ot_rate = float(emp_custom_ot) if (emp_custom_ot and float(emp_custom_ot) > 0) else (float(sal_struct.get("ot_rate_per_hour", 86.0)) if sal_struct else 86.0)

                    working_days = 26
                    p_cnt = 0.0
                    ph_cnt = 0.0
                    leave_cnt = 0.0
                    ot_hours_total = 0.0
                    try:
                        att_recs = supabase.table("attendance").select("status, ot_hours").eq("employee_id", emp_item["id"]).execute().data or []
                        if att_recs:
                            p_cnt = float(len([a for a in att_recs if a.get("status") in ["P", "WO"]]))
                            p_cnt += float(len([a for a in att_recs if a.get("status") == "HD"])) * 0.5
                            ph_cnt = float(len([a for a in att_recs if a.get("status") == "PH"]))
                            leave_cnt = float(len([a for a in att_recs if a.get("status") == "L"]))
                            ot_hours_total = sum([float(a.get("ot_hours") or 0.0) for a in att_recs])
                    except Exception: 
                        pass

                    paid_days = p_cnt + ph_cnt + leave_cnt

                    earned_basic = round(r_basic * paid_days, 2)
                    earned_da = round(r_da * paid_days, 2)
                    basic_plus_da = round(earned_basic + earned_da, 2)
                    earned_hra = round(r_hra * paid_days, 2)
                    ot_amount = round(ot_hours_total * ot_rate, 2)
                    gross_amount = round(basic_plus_da + earned_hra + ot_amount, 2)

                    pf_ded = 1800.0 if basic_plus_da > 15000 else round(basic_plus_da * 0.12, 2)
                    esic_ded = round(gross_amount * 0.0075, 2)
                    mlwf_ee = 0.0
                    pt_ded = float(sal_struct.get("pt_amount", 200.0) if sal_struct else 200.0) if gross_amount > 10000 else 0.0
                    
                    adv_val = 0.0
                    try:
                        adv_recs = supabase.table("advance_salaries").select("amount").eq("employee_id", emp_item["id"]).eq("status", "APPROVED").execute().data or []
                        adv_val = sum([float(a.get("amount") or 0.0) for a in adv_recs])
                    except Exception: 
                        pass

                    ppe_ded = 0.0
                    try:
                        ppe_recs = supabase.table("ppe_records").select("cost").eq("employee_id", emp_item["id"]).eq("deduction_month", sel_month).eq("status", "APPROVED").execute().data or []
                        ppe_ded = sum([float(p.get("cost") or 0.0) for p in ppe_recs])
                    except Exception: 
                        pass

                    total_deduction = round(pf_ded + esic_ded + mlwf_ee + pt_ded + adv_val + ppe_ded, 2)
                    net_amount = round(gross_amount - total_deduction, 2)

                    pf_er = 1950.0 if basic_plus_da > 15000 else round(basic_plus_da * 0.13, 2)
                    esic_er = round(gross_amount * 0.0325, 2)
                    mlwf_er = 0.0
                    sub_total_er = round(gross_amount + pf_er + esic_er + mlwf_er, 2)

                    cli_match = next((c for c in cli_list if c["id"] == emp_item.get("client_id")), {})
                    service_pct = float(cli_match.get("service_charge_pct") or 7.0)
                    service_charges = round(sub_total_er * (service_pct / 100.0), 2)
                    billing_total = round(sub_total_er + service_charges, 2)
                    cgst_9 = round(billing_total * 0.09, 2)
                    sgst_9 = round(billing_total * 0.09, 2)
                    grand_billing_amt = round(billing_total + cgst_9 + sgst_9, 2)

                    payroll_rows.append({
                        "SR.NO": idx,
                        "Employee ID No": emp_item.get("employee_code", "N/A"),
                        "Name Of Employee": emp_item.get("full_name"),
                        "Joining Date": emp_item.get("joining_date", "2026-01-01"),
                        "UAN No": emp_item.get("uan_number", "N/A"),
                        "ESIC No": emp_item.get("esic_number", "N/A"),
                        "Adhar No": "[Aadhaar Redacted]",
                        "Contract Name": sel_ent_name,
                        "Department": emp_item.get("department", "Facility"),
                        "Category": emp_item.get("category", "Semiskilled"),
                        "Zone": emp_item.get("zone", "Zone - 3"),
                        "BASIC": round(r_basic, 2),
                        "DA": round(r_da, 2),
                        "HRA": round(r_hra, 2),
                        "TOTAL GROS": total_gros_rate,
                        "WORKING DAYS": working_days,
                        "PAID DAYS": paid_days,
                        "Basic": earned_basic,
                        "D.A": earned_da,
                        "Basic+ DA": basic_plus_da,
                        "HRA": earned_hra,
                        "OT Hours": ot_hours_total,
                        "OT Rate": ot_rate,
                        "OT Amount": ot_amount,
                        "Gross Amount": gross_amount,
                        "P.F.": pf_ded,
                        "ESIC 0.75 %": esic_ded,
                        "MLWF": mlwf_ee,
                        "P.T.": pt_ded,
                        "Advance": adv_val,
                        "PPE / Uniform Deduction": ppe_ded,
                        "Total Deduction": total_deduction,
                        "Net Amount": net_amount,
                        "Gross Amount ": gross_amount,
                        "EMPLOYER 13%": pf_er,
                        "EMPLOYER ESIS 3.25": esic_er,
                        "MLWF ": mlwf_er,
                        "Sub Total": sub_total_er,
                        f"SERVICES CHARGES {service_pct:.0f}%": service_charges,
                        "Billing Total": billing_total,
                        "CGST": cgst_9,
                        "SGST": sgst_9,
                        "BILLING AMT": grand_billing_amt
                    })

                df_wage_43 = pd.DataFrame(payroll_rows)
                st.dataframe(df_wage_43, use_container_width=True)

                st.write("---")
                col_lk1, col_lk2 = st.columns([2, 5])
                with col_lk1:
                    csv_data = df_wage_43.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "Download 43-Cols Wage Sheet (CSV)",
                        data=csv_data,
                        file_name=f"WageSheet_{sel_ent_name}_{sel_cli_name}_{sel_month.replace(' ', '_')}.csv",
                        mime="text/csv"
                    )
                with col_lk2:
                    if st.button("Dual-Confirm & Lock Wage Sheet", type="primary"):
                        supabase.table("locked_payrolls").upsert({
                            "entity_id": e_opts[sel_ent_name],
                            "client_id": c_opts[sel_cli_name],
                            "payroll_month": sel_month,
                            "is_locked": True
                        }, on_conflict="entity_id,client_id,payroll_month").execute()
                        st.toast("🔒 Official Wage Sheet Locked!")
                        st.success(f"Wage Sheet for {sel_ent_name} at {sel_cli_name} locked successfully! Payslips available on 15th.")
            else:
                st.info("No approved workers deployed under selected Entity and Client Site.")

        # PANEL 9: STATUTORY COMPLIANCE REPORTS
        elif selected_panel == "Statutory Compliance Reports":
            st.subheader("Government Compliance File Generators (PF ECR & ESIC)")
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_opts = {e["name"]: e["id"] for e in ent_list}
            c_opts = {c["name"]: c["id"] for c in cli_list}

            rc1, rc2 = st.columns(2)
            sel_e_comp = rc1.selectbox("Select Entity *", list(e_opts.keys()) if e_opts else ["No Entity"])
            sel_c_comp = rc2.selectbox("Select Client Site *", list(c_opts.keys()) if c_opts else ["No Client"])

            comp_emps = [e for e in fetch_cached_employees() if e.get("entity_id") == e_opts.get(sel_e_comp) and e.get("client_id") == c_opts.get(sel_c_comp) and e.get("role") == "employee"]
            
            t_ecr, t_esic = st.tabs(["PF ECR Text File", "ESIC Monthly Return CSV"])
            with t_ecr:
                if comp_emps:
                    ecr_lines = []
                    for emp in comp_emps:
                        uan = emp.get("uan_number") or "102323165327"
                        name = emp.get("full_name", "Worker")
                        ecr_lines.append(f"{uan}#~#{name}#~#15000#~#15000#~#15000#~#15000#~#1800#~#1250#~#550#~#0#~#0")
                    ecr_text = "\n".join(ecr_lines)
                    st.download_button("Download Official PF ECR Text File (.txt)", data=ecr_text, file_name=f"PF_ECR_{sel_e_comp}.txt", mime="text/plain")
                else:
                    st.info("No employee records found for PF ECR generation.")

            with t_esic:
                if comp_emps:
                    esic_rows = []
                    for emp in comp_emps:
                        esic_rows.append({
                            "IP Number": emp.get("esic_number", "3318292114"),
                            "IP Name": emp.get("full_name"),
                            "No of Days for which wages paid": 26,
                            "Total Monthly Wages": 18222.0,
                            "Reason Code": 0
                        })
                    df_esic = pd.DataFrame(esic_rows)
                    st.dataframe(df_esic, use_container_width=True)
                    esic_csv = df_esic.to_csv(index=False).encode('utf-8')
                    st.download_button("Download ESIC Monthly Upload CSV", data=esic_csv, file_name=f"ESIC_Monthly_{sel_e_comp}.csv", mime="text/csv")
                else:
                    st.info("No employee records found for ESIC generation.")

        # PANEL 10: HELPDESK / GRIEVANCE DESK
        elif selected_panel == "Helpdesk / Grievance Desk":
            st.subheader("Employee Helpdesk & Grievance Tickets Redressal")
            tickets = supabase.table("helpdesk_tickets").select("*").order("created_at", desc=True).execute().data or []
            emp_map = {e["id"]: e for e in fetch_cached_employees()}

            if tickets:
                for tk in tickets:
                    tk_emp = emp_map.get(tk.get("employee_id"), {})
                    with st.expander(f"Ticket #{tk['id'][:6]} | {tk_emp.get('full_name', 'Worker')} | Subject: {tk.get('subject')} | Status: {tk.get('status')}"):
                        st.write(f"**Category:** {tk.get('category')}")
                        st.write(f"**Description:** {tk.get('description')}")
                        res_txt = st.text_area("Resolution Remarks *", value=tk.get("admin_resolution") or "", key=f"res_{tk['id']}")
                        if st.button("Resolve & Close Ticket", key=f"res_btn_{tk['id']}", type="primary"):
                            if not res_txt.strip():
                                st.error("Resolution remarks cannot be empty!")
                            else:
                                supabase.table("helpdesk_tickets").update({"status": "RESOLVED", "admin_resolution": res_txt.strip()}).eq("id", tk["id"]).execute()
                                st.toast("✅ Ticket Resolved!")
                                st.success("Grievance ticket marked as resolved.")
                                pytime.sleep(1)
                                st.rerun()
            else:
                st.info("No helpdesk tickets registered.")

        # PANEL 11: ADVANCE / LOAN DESK
        elif selected_panel == "Advance / Loan Desk":
            st.subheader("Salary Advance & Loan Requests Approval Desk")
            adv_reqs = supabase.table("advance_salaries").select("*").order("created_at", desc=True).execute().data or []
            if adv_reqs:
                all_emps_data = fetch_cached_employees()
                emp_map = {e["id"]: e for e in all_emps_data}
                pending_adv = [a for a in adv_reqs if a.get("status") in ["PENDING_SUPERVISOR", "PENDING_ADMIN"]]
                if pending_adv:
                    for req in pending_adv:
                        req_emp = emp_map.get(req.get("employee_id"), {})
                        st.markdown(f"**Employee:** {req_emp.get('full_name', 'N/A')} (Code: {req_emp.get('employee_code', 'TEMP')}) | **Amount:** Rs.{float(req.get('amount', 0)):,.2f} | **Reason:** {req.get('reason', 'None')}")
                        col_ap, col_rj, _ = st.columns([1.5, 1.5, 5])
                        if col_ap.button("Approve Advance", key=f"adv_app_{req['id']}", type="primary"):
                            supabase.table("advance_salaries").update({"status": "APPROVED"}).eq("id", req["id"]).execute()
                            st.toast("✅ Salary Advance Approved!")
                            st.rerun()
                        if col_rj.button("Reject Request", key=f"adv_rej_{req['id']}:"):
                            supabase.table("advance_salaries").update({"status": "REJECTED_BY_ADMIN"}).eq("id", req["id"]).execute()
                            st.toast("Advance rejected!")
                            st.rerun()
                else:
                    st.info("No pending salary advance requests.")
            else:
                st.info("No salary advance records found.")

        # PANEL 12: PPE & UNIFORM TRACKER
        elif selected_panel == "PPE & Uniform Tracker":
            st.subheader("PPE & Uniform Tracker (Catalog & Issuance Desk)")
            tab_ppe_issue, tab_ppe_cat = st.tabs(["Issue / Add PPE", "PPE Price Catalog"])
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            emp_list = fetch_cached_employees()
            p_e_map = {e["name"]: e["id"] for e in ent_list}
            p_c_map = {c["name"]: c["id"] for c in cli_list}
            p_emp_map = {f"[{e.get('employee_code', 'N/A')}] {e['full_name']}": e["id"] for e in emp_list if e.get("role") == "employee"}

            with tab_ppe_cat:
                with st.form("add_ppe_catalog_form_admin"):
                    cat_c1, cat_c2 = st.columns(2)
                    cat_ent = cat_c1.selectbox("Select Entity *", list(p_e_map.keys()) if p_e_map else ["No Entity"])
                    cat_cli = cat_c2.selectbox("Select Client Site *", list(p_c_map.keys()) if p_c_map else ["No Client"])
                    cat_c3, cat_c4 = st.columns(2)
                    cat_item = cat_c3.text_input("PPE Item Name * (e.g. Safety Shoes, Helmet)")
                    cat_price = cat_c4.number_input("Unit Price (Rs.) *", min_value=0.0, step=10.0, value=100.0)
                    if st.form_submit_button("Save Item in Catalog", type="primary"):
                        if cat_item.strip():
                            supabase.table("ppe_catalog").upsert({
                                "entity_id": p_e_map[cat_ent], 
                                "client_id": p_c_map[cat_cli],
                                "item_name": cat_item.strip(), 
                                "price": cat_price
                            }, on_conflict="entity_id,client_id,item_name").execute()
                            st.toast("✅ PPE Price saved in catalog!")
                            st.rerun()

            with tab_ppe_issue:
                with st.form("manual_ppe_issue_form_admin"):
                    col_p1, col_p2, col_p3 = st.columns(3)
                    p_sel_emp = col_p1.selectbox("Employee *", options=list(p_emp_map.keys()) if p_emp_map else ["No Employee"])
                    p_item = col_p2.selectbox("PPE Item", ["Safety Shoes", "Helmet", "Safety Goggles", "Uniform Shirt/Pant", "ID Card"])
                    p_qty = col_p3.number_input("Quantity", min_value=1, value=1)
                    if st.form_submit_button("Issue PPE Record", type="primary"):
                        if p_emp_map:
                            supabase.table("ppe_records").insert({
                                "employee_id": p_emp_map[p_sel_emp], 
                                "item_type": p_item,
                                "quantity": p_qty, 
                                "status": "APPROVED", 
                                "assigned_date": str(date.today())
                            }).execute()
                            st.toast("✅ PPE Issued successfully!")
                            st.success("PPE record saved!")
                            pytime.sleep(1)
                            st.rerun()

        # PANEL 13: CLIENT BILLING & INVOICES
        elif selected_panel == "Client Billing & Invoices":
            st.subheader("Client Billing & Tax Invoice Generator (Custom Template & PDF Engine)")
            t_inv_gen, t_inv_hist = st.tabs(["Generate Tax Invoice", "Invoices History"])
            
            cli_list = fetch_cached_clients()
            ent_list = fetch_cached_entities()
            c_dict = {c["name"]: c for c in cli_list}
            e_dict = {e["name"]: e for e in ent_list}

            with t_inv_gen:
                with st.form("generate_tax_inv_advanced_form"):
                    st.write("##### 1. Supplier (Entity) & Buyer (Client) Selection")
                    i_col1, i_col2 = st.columns(2)
                    sel_inv_ent = i_col1.selectbox("From Entity (Supplier) *", list(e_dict.keys()) if e_dict else ["No Entity"])
                    sel_inv_cli = i_col2.selectbox("To Client (Buyer) *", list(c_dict.keys()) if c_dict else ["No Client"])
                    
                    st.write("##### 2. Transport & Delivery Particulars")
                    m_c1, m_c2, m_c3 = st.columns(3)
                    inv_no = m_c1.text_input("Invoice Number *", value="SE/26-27/51")
                    inv_dt = m_c2.date_input("Invoice Date", value=date.today())
                    inv_ref = m_c3.text_input("Reference No. & Date", value="")

                    m_c4, m_c5, m_c6 = st.columns(3)
                    inv_order = m_c4.text_input("Buyer's Order No. & Date", value="")
                    inv_disp = m_c5.text_input("Dispatch Doc No.", value="")
                    inv_through = m_c6.text_input("Dispatched through", value="")

                    m_c7, m_c8 = st.columns(2)
                    inv_lading = m_c7.text_input("Bill of Lading / LR-RR No.", value="")
                    inv_terms = m_c8.text_input("Terms of Delivery / Conditions", value="1. Payment within 15 days. 2. Subject to Pune jurisdiction.")

                    st.write("##### 3. Consignee (Ship To) Details")
                    chk_same = st.checkbox("Consignee is same as Buyer", value=True)
                    cons_n = st.text_input("Consignee Name", value=sel_inv_cli if chk_same else "")
                    cons_a = st.text_area("Consignee Address", value=c_dict[sel_inv_cli]["plant_location"] if chk_same and sel_inv_cli in c_dict else "")
                    cons_g = st.text_input("Consignee GSTIN", value=c_dict[sel_inv_cli]["gst_number"] if chk_same and sel_inv_cli in c_dict else "")

                    st.write("##### 4. Line Items & Taxable Amount (Custom Template Fields)")
                    it_c1, it_c2, it_c3 = st.columns(3)
                    inv_month = it_c1.text_input("Billing Month / Particulars Title", value="August 2026 Manpower Supply")
                    inv_hsn = it_c2.text_input("HSN / SAC Code", value="996511")
                    inv_qty = it_c3.number_input("Quantity (Nos / Manmonths)", min_value=1.0, value=1.0, step=1.0)

                    it_c4, it_c5 = st.columns(2)
                    inv_rate = it_c4.number_input("Rate / Taxable Amount (Rs.) *", min_value=0.0, value=115146.0, step=100.0)
                    inv_gst_rate = it_c5.selectbox("GST Rate Structure *", ["18% (9% CGST + 9% SGST)", "12% (6% CGST + 6% SGST)", "5% (2.5% CGST + 2.5% SGST)"], index=0)

                    st.markdown("##### 5. Template Options (Bank Details, PAN, Sign, Stamp & Terms)")
                    inc_bank = st.checkbox("Include Entity Bank Details & PAN in PDF", value=True)
                    inc_stamp = st.checkbox("Include Authorized Signatory Stamp & Signature", value=True)

                    if st.form_submit_button("Generate & Save Tax Invoice PDF", type="primary"):
                        if not inv_no.strip():
                            st.error("Invoice number is mandatory!")
                        else:
                            supabase.table("client_invoices").insert({
                                "invoice_number": inv_no, 
                                "invoice_date": str(inv_dt),
                                "reference_no": inv_ref, 
                                "buyers_order_no": inv_order,
                                "dispatch_doc_no": inv_disp, 
                                "dispatched_through": inv_through,
                                "bill_of_lading_no": inv_lading, 
                                "terms_of_delivery": inv_terms,
                                "consignee_name": cons_n, 
                                "consignee_address": cons_a, 
                                "consignee_gstin": cons_g,
                                "client_id": c_dict[sel_inv_cli]["id"], 
                                "entity_id": e_dict[sel_inv_ent]["id"],
                                "billing_month": inv_month, 
                                "hsn_sac": inv_hsn, 
                                "total_amount": inv_rate, 
                                "payment_status": "PENDING"
                            }).execute()
                            st.toast("✅ Tax Invoice generated successfully!")
                            st.success("Invoice saved and ready for download in history!")
                            pytime.sleep(1)
                            st.rerun()

            with t_inv_hist:
                st.subheader("Generated Invoices History & PDF Download")
                inv_records = supabase.table("client_invoices").select("*").execute().data or []
                if inv_records:
                    for inv in inv_records:
                        with st.expander(f"Invoice: {inv.get('invoice_number')} | Month: {inv.get('billing_month')} | Total: Rs.{inv.get('total_amount', 0):,.2f}"):
                            ent_obj = next((e for e in ent_list if e["id"] == inv.get("entity_id")), None)
                            cli_obj = next((c for c in cli_list if c["id"] == inv.get("client_id")), None)
                            inv_pdf = generate_exact_tax_invoice(inv, ent_obj, cli_obj)
                            st.download_button(
                                f"Download Tax Invoice PDF ({inv.get('invoice_number')})", 
                                data=inv_pdf, 
                                file_name=f"Invoice_{inv.get('invoice_number').replace('/', '_')}.pdf", 
                                mime="application/pdf", 
                                key=f"dn_inv_{inv['id']}"
                            )
                else:
                    st.info("No tax invoices generated yet.")

        # PANEL 14: COMPANY & PLANT LOCATIONS
        elif selected_panel == "Company & Plant Locations":
            loc1, loc2 = st.columns(2)
            with loc1:
                st.subheader("1. Entity / Firm Master")
                t_ent_add, t_ent_edit = st.tabs(["Add Entity", "Edit / Delete Entity"])
                with t_ent_add:
                    with st.form("add_entity_portal_form_full_admin"):
                        en_name = st.text_input("Firm / Entity Name *")
                        en_pref = st.text_input("Code Prefix (e.g. SE, GM) *")
                        en_owner = st.text_input("Owner / Partner Name")
                        en_addr = st.text_area("Entity Full Registered Address *")
                        en_gst = st.text_input("GST Number *")
                        en_pan = st.text_input("PAN Number *")
                        en_ph = st.text_input("Phone Number *")
                        en_em = st.text_input("Email ID *")
                        st.markdown("##### Bank Details for Invoices")
                        en_bnk = st.text_input("Bank Name", value="SARASWAT BANK")
                        en_branch = st.text_input("Branch Name")
                        en_acc = st.text_input("Account Number", value="610000000045918")
                        en_ifsc = st.text_input("IFSC Code", value="SRCB0000376")
                        
                        if st.form_submit_button("Save Entity", type="primary"):
                            if en_name and en_pref and en_gst:
                                supabase.table("entities").insert({
                                    "name": en_name, "code_prefix": en_pref, "owner_name": en_owner,
                                    "address": en_addr, "gst_number": en_gst, "pan_number": en_pan,
                                    "phone": en_ph, "email": en_em, "bank_name": en_bnk,
                                    "bank_branch": en_branch, "bank_account_no": en_acc, "ifsc_code": en_ifsc
                                }).execute()
                                st.cache_data.clear()
                                st.success("Entity registered successfully!")
                                st.rerun()

                with t_ent_edit:
                    ents_all = fetch_cached_entities()
                    if ents_all:
                        ent_select_map = {e["name"]: e for e in ents_all}
                        sel_ent_e = st.selectbox("Select Entity to Edit/Delete", list(ent_select_map.keys()))
                        curr_e = ent_select_map[sel_ent_e]
                        with st.form("edit_entity_portal_form_full_admin"):
                            en_up_name = st.text_input("Firm Name", value=curr_e.get("name", ""))
                            en_up_owner = st.text_input("Owner Name", value=curr_e.get("owner_name", ""))
                            en_up_addr = st.text_area("Full Address", value=curr_e.get("address", ""))
                            en_up_gst = st.text_input("GST", value=curr_e.get("gst_number", ""))
                            en_up_pan = st.text_input("PAN", value=curr_e.get("pan_number", ""))
                            en_up_em = st.text_input("Email ID", value=curr_e.get("email", ""))
                            en_up_bnk = st.text_input("Bank Name", value=curr_e.get("bank_name", ""))
                            en_up_acc = st.text_input("Bank Account No", value=curr_e.get("bank_account_no", ""))
                            en_up_ifsc = st.text_input("Bank IFSC Code", value=curr_e.get("ifsc_code", ""))
                            
                            c1, c2 = st.columns(2)
                            if c1.form_submit_button("Update Entity", type="primary"):
                                supabase.table("entities").update({
                                    "name": en_up_name, "owner_name": en_up_owner, "address": en_up_addr,
                                    "gst_number": en_up_gst, "pan_number": en_up_pan, "email": en_up_em,
                                    "bank_name": en_up_bnk, "bank_account_no": en_up_acc, "ifsc_code": en_up_ifsc
                                }).eq("id", curr_e["id"]).execute()
                                st.cache_data.clear()
                                st.success("Entity updated!")
                                st.rerun()
                            if c2.form_submit_button("Delete Entity"):
                                supabase.table("entities").delete().eq("id", curr_e["id"]).execute()
                                st.cache_data.clear()
                                st.warning("Entity deleted!")
                                st.rerun()

            with loc2:
                st.subheader("2. Client Plant Master & Geofence")
                t_cli_add, t_cli_edit = st.tabs(["Add Client", "Edit / Delete Client"])
                ents = fetch_cached_entities()
                e_dict = {e["name"]: e["id"] for e in ents}

                with t_cli_add:
                    with st.form("add_client_all_fields_form_full_admin"):
                        cl_name = st.text_input("Client Company Name *")
                        cl_code = st.text_input("Client Code *")
                        cl_gst = st.text_input("Client GST Number *")
                        cl_serv = st.number_input("Service Charge Rate (%) *", value=7.0, step=0.5)
                        cl_full_addr = st.text_area("Plant Full Address *")
                        cl_c_name = st.text_input("Contact Person Name *")
                        cl_c_mobile = st.text_input("Contact Person Mobile Number *")
                        cl_c_email = st.text_input("Contact Person Email ID *")
                        assigned_ents = st.multiselect("Assign Entity Providers *", options=list(e_dict.keys()) if e_dict else [])
                        g_col1, g_col2 = st.columns(2)
                        cl_lat = g_col1.number_input("Latitude", format="%.6f", value=18.651200)
                        cl_lon = g_col2.number_input("Longitude", format="%.6f", value=73.805500)

                        if st.form_submit_button("Save Client Details", type="primary"):
                            if cl_name and cl_code and cl_gst:
                                ins_cli = supabase.table("clients").insert({
                                    "name": cl_name, "client_code": cl_code, "gst_number": cl_gst,
                                    "service_charge_pct": cl_serv, "plant_location": cl_full_addr,
                                     "contact_person_name": cl_c_name, "contact_person_email": cl_c_email,
                                     "contact_person_mobile": cl_c_mobile, "latitude": cl_lat, "longitude": cl_lon
                                 }).execute()

        # 2. निवडलेल्या सर्व entities client_entities मध्ये save करा
                                if ins_cli.data:
                                    client_id = ins_cli.data[0]["id"]
                                    for ent_name in assigned_ents:
                                       ent_id = e_dict.get(ent_name)
                                       if ent_id:
                                         supabase.table("client_entities").insert({
                                             "client_id": client_id,
                                             "entity_id": ent_id
                                         }).execute()

                                st.cache_data.clear()
                                st.success("Client registered successfully with multiple entities!")
                                st.rerun()
                with t_cli_edit:
                    clis_all = fetch_cached_clients()
                    if clis_all:
                        cli_select_map = {c["name"]: c for c in clis_all}
                        sel_c_e = st.selectbox("Select Client to Edit/Delete", list(cli_select_map.keys()))
                        curr_c = cli_select_map[sel_c_e]
                
                # Fetch existing entities linked with this client
                existing_client_ents = supabase.table("client_entities").select("entity_id").eq("client_id", curr_c["id"]).execute().data or []
                curr_assigned_ent_ids = [item["entity_id"] for item in existing_client_ents]
                curr_assigned_ent_names = [k for k, v in e_dict.items() if v in curr_assigned_ent_ids]

                with st.form("edit_client_all_fields_form_full_admin"):
                    cl_up_name = st.text_input("Client Name", value=curr_c.get("name", ""))
                    cl_up_gst = st.text_input("Client GST", value=curr_c.get("gst_number", ""))
                    cl_up_serv = st.number_input("Service Charge Rate (%)", value=float(curr_c.get("service_charge_pct") or 7.0), step=0.5)
                    cl_up_addr = st.text_area("Address", value=curr_c.get("plant_location", ""))
                    cl_up_cn = st.text_input("Contact Person", value=curr_c.get("contact_person_name", ""))
                    cl_up_cm = st.text_input("Contact Mobile", value=curr_c.get("contact_person_mobile", ""))
                    cl_up_em = st.text_input("Contact Email", value=curr_c.get("contact_person_email", ""))
                    
                    # 👈 Multiple Entity selection multiselect
                    cl_up_ents = st.multiselect("Update Assigned Entity Providers *", options=list(e_dict.keys()), default=curr_assigned_ent_names)
                    
                    cg1, cg2 = st.columns(2)
                    cl_up_lat = cg1.number_input("Latitude", format="%.6f", value=float(curr_c.get("latitude", 18.6512)))
                    cl_up_lon = cg2.number_input("Longitude", format="%.6f", value=float(curr_c.get("longitude", 73.8055)))

                    cb1, cb2 = st.columns(2)
                    if cb1.form_submit_button("Update Client", type="primary"):
                        # 1. Update client details
                        supabase.table("clients").update({
                            "name": cl_up_name, "gst_number": cl_up_gst, "service_charge_pct": cl_up_serv,
                            "plant_location": cl_up_addr, "contact_person_name": cl_up_cn,
                            "contact_person_mobile": cl_up_cm, "contact_person_email": cl_up_em,
                            "latitude": cl_up_lat, "longitude": cl_up_lon
                        }).eq("id", curr_c["id"]).execute()

                        # 2. Sync multiple entity mappings in client_entities table
                        supabase.table("client_entities").delete().eq("client_id", curr_c["id"]).execute()
                        for ent_name in cl_up_ents:
                            ent_id = e_dict.get(ent_name)
                            if ent_id:
                                supabase.table("client_entities").insert({
                                    "client_id": curr_c["id"],
                                    "entity_id": ent_id
                                }).execute()

                        st.cache_data.clear()
                        st.success("Client details and multiple entities updated successfully!")
                        st.rerun()

                    if cb2.form_submit_button("Delete Client"):
                        supabase.table("clients").delete().eq("id", curr_c["id"]).execute()
                        st.cache_data.clear()
                        st.warning("Client deleted!")
                        st.rerun()

        # PANEL 15: USER ROLES & ACCESS
        elif selected_panel == "User Roles & Access":
            st.subheader("User Roles & Access Control")
            t_u_add, t_u_edit = st.tabs(["Create User Access", "Edit / Delete User Access"])
            cli_re = fetch_cached_clients()
            ent_re = fetch_cached_entities()
            cli_m = {c["name"]: c["id"] for c in cli_re}
            ent_m = {e["name"]: e["id"] for e in ent_re}
            c_rev_m = {c["id"]: c["name"] for c in cli_re}

            with t_u_add:
                with st.form("create_role_form_full_admin"):
                    rc1, rc2, rc3 = st.columns(3)
                    new_r = rc1.selectbox("Role *", ["supervisor", "admin", "client", "employee"])
                    new_u = rc2.text_input("User ID *").strip()
                    new_n = rc3.text_input("Concern Person / Full Name *")

                    rc4, rc5, rc6 = st.columns(3)
                    new_p = rc4.text_input("Password *", type="password")
                    new_ph = rc5.text_input("Mobile Number *")
                    new_em = rc6.text_input("Email ID *")

                    rc7, rc8 = st.columns(2)
                    assigned_ents = rc7.multiselect("Assign Entity Providers", options=list(ent_m.keys()))
                    assigned_clients = rc8.multiselect("Assign Client Sites (Multiple)", options=list(cli_m.keys()))

                    if st.form_submit_button("Save User Credentials", type="primary"):
                         if not new_u or not new_n or not new_p or not new_ph:
                              st.error("User ID, Full Name, Password and Mobile Number are required!")
                         else:
                             dup_usr = supabase.table("employees").select("id").eq("user_id", new_u).execute().data
                             if dup_usr:
                               st.error(f"Error: User ID '{new_u}' already exists! Choose another ID.")
                             else:
            # 1. Employee / User Insert करा
                               ins_res = supabase.table("employees").insert({
                                  "user_id": new_u, "password": new_p, "full_name": new_n, "phone_number": new_ph,
                                  "email": new_em, "role": new_r, 
                                  "status": "APPROVED"
                               }).execute()
                               # 2. जर भूमिका 'supervisor' असेल तर निवडलेले सर्व clients 'supervisor_clients' मध्ये लिंक करा
                               if ins_res.data and new_r == "supervisor":
                                   sup_id = ins_res.data[0]["id"]
                                   for cli_name in assigned_clients:
                                        cli_id = cli_m.get(cli_name)
                                        if cli_id:
                                            supabase.table("supervisor_clients").insert({
                                                "supervisor_id": sup_id,
                                                "client_id": cli_id
                                            }).execute()
            
            # 2. जर supervisor असेल आणि multiple entities निवडल्या असतील तर supervisor_entities मध्ये save करा
                               if ins_res.data and new_r == "supervisor":
                                  sup_id = ins_res.data[0]["id"]
                                  for ent_name in assigned_ents:
                                     ent_id = ent_m.get(ent_name)
                                     if ent_id:
                                         supabase.table("supervisor_entities").insert({
                                             "supervisor_id": sup_id,
                                             "entity_id": ent_id
                                         }).execute()

                               st.cache_data.clear()
                               st.success(f"User {new_u} created successfully with multiple Entities & Clients!")
                               st.rerun()

            with t_u_edit:
                users_res = supabase.table("employees").select("*").in_("role", ["supervisor", "client", "admin", "employee"]).execute().data or []
                if users_res:
                    u_map = {f"[{u.get('role').upper()}] {u.get('user_id')} - {u.get('full_name')}": u for u in users_res}
                    sel_u = st.selectbox("Select User", list(u_map.keys()))
                    curr_u = u_map[sel_u]

                    curr_client_name = c_rev_m.get(curr_u.get("client_id"))
                    cli_opts = list(cli_m.keys())
                    cli_idx = cli_opts.index(curr_client_name) if curr_client_name in cli_opts else 0

                    with st.form("edit_user_form_full_admin"):
                        uc1, uc2, uc3 = st.columns(3)
                        up_un = uc1.text_input("Full Name", value=curr_u.get("full_name", ""))
                        up_em = uc2.text_input("Email ID", value=curr_u.get("email", ""))
                        up_ph = uc3.text_input("Mobile Number", value=curr_u.get("phone_number", ""))

                        uc4, uc5 = st.columns(2)
                        up_up = uc4.text_input("Password", value=curr_u.get("password", ""))
                        up_cli = uc5.selectbox("Assigned Client Site", options=["No Client"] + cli_opts, index=(cli_idx + 1) if curr_client_name in cli_opts else 0)

                        b_col1, b_col2 = st.columns(2)
                        if b_col1.form_submit_button("Update User Details", type="primary"):
                            supabase.table("employees").update({
                                "full_name": up_un, 
                                "email": up_em, 
                                "phone_number": up_ph, 
                                "password": up_up,
                                "client_id": cli_m.get(up_cli) if up_cli != "No Client" else None
                            }).eq("id", curr_u["id"]).execute()
                            st.cache_data.clear()
                            st.success("User updated successfully!")
                            st.rerun()

                        if b_col2.form_submit_button("Delete User"):
                            supabase.table("employees").delete().eq("id", curr_u["id"]).execute()
                            st.cache_data.clear()
                            st.warning("User deleted!")
                            st.rerun()

        # PANEL 16: DEVICE BINDING RESET
        elif selected_panel == "Device Binding Reset":
            st.subheader("Employee Mobile Device Binding & Reset Management")
            all_bound_emps = supabase.table("employees").select("id, employee_code, full_name, phone_number, device_binding_id").eq("role", "employee").execute().data or []
            if all_bound_emps:
                emp_bind_map = {f"[{e.get('employee_code', 'TEMP')}] {e['full_name']} (Mobile: {e['phone_number']})": e for e in all_bound_emps}
                sel_b_emp = st.selectbox("Select Employee to Reset Device Binding", list(emp_bind_map.keys()))
                target_emp = emp_bind_map[sel_b_emp]
                if st.button("Reset Mobile Device Binding", type="primary"):
                    supabase.table("employees").update({"device_binding_id": None}).eq("id", target_emp["id"]).execute()
                    st.toast("✅ Device binding reset successfully!")
                    st.success(f"Device lock cleared for {target_emp['full_name']}. They can now login from a new phone.")
                    pytime.sleep(1)
                    st.rerun()
            else:
                st.info("No employee records found.")

    # -------------------------------------------------------------------------
    # 4.2 SUPERVISOR PORTAL (ALL 6 PANELS COMPLETE)
    # -------------------------------------------------------------------------
    elif active_role == "supervisor":
        sup_user = st.session_state.user
        sup_id = sup_user.get("id")
        sup_ent_id = sup_user.get("entity_id")
        sup_cli_id = sup_user.get("client_id")

        if "active_sup_tab" not in st.session_state:
            st.session_state.active_sup_tab = "Candidate Onboarding & Review"

        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS SUPERVISOR</div>', unsafe_allow_html=True)
            st.markdown('<div class="logged-badge">Logged In: SUPERVISOR</div>', unsafe_allow_html=True)
            st.write(f"Supervisor: **{sup_user.get('full_name')}**")
            st.caption("SUPERVISOR DESK")

            sup_tabs = [
                "Candidate Onboarding & Review",
                "Shift Roster Management (Assigned Sites)",
                "Site Attendance & Punch",
                "Workforce Roster",
                "PPE & Advance Approvals",
                "Employee Leave Requests"
            ]

            for st_name in sup_tabs:
                btn_style = "primary" if st.session_state.active_sup_tab == st_name else "secondary"
                if st.button(st_name, key=f"sup_btn_{st_name}", type=btn_style):
                    st.session_state.active_sup_tab = st_name
                    st.rerun()

            st.write("---")
            if st.button("Logout", key="sup_logout"):
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

        selected_sup_panel = st.session_state.active_sup_tab
        st.title(selected_sup_panel)

        # =====================================================================
        # SUPERVISOR PANEL 1: CANDIDATE ONBOARDING & REVIEW
        # =====================================================================
        if selected_sup_panel == "Candidate Onboarding & Review":
            st.subheader("Candidate Onboarding Verification & Credential Assignment")

            # Base query: Pending supervisor kinva Rejected status aslele records
            cand_query = supabase.table("employees").select("*").in_("status", ["PENDING_SUPERVISOR", "REJECTED_TO_SUPERVISOR"])

        # Filter logic: Supervisor chi swatahachi site/entity ASLELE + jyana ajun assign kelele nahi (NULL) te sarv records
            if sup_ent_id and sup_cli_id:
            # Supervisor chya entity/client che records KINVA jyache client_id/entity_id NULL ahet te sarv
                 cand_query = cand_query.or_(f"and(entity_id.eq.{sup_ent_id},client_id.eq.{sup_cli_id}),entity_id.is.null,client_id.is.null")
            elif sup_ent_id:
                 cand_query = cand_query.or_(f"entity_id.eq.{sup_ent_id},entity_id.is.null")
            elif sup_cli_id:
                 cand_query = cand_query.or_(f"client_id.eq.{sup_cli_id},client_id.is.null")

            cand_list = cand_query.execute().data or []

            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_map = {e["name"]: e["id"] for e in ent_list}
            c_map = {c["name"]: c["id"] for c in cli_list}
            e_rev_map = {e["id"]: e["name"] for e in ent_list}
            c_rev_map = {c["id"]: c["name"] for c in cli_list}

            if cand_list:
                for c in cand_list:
                    with st.expander(f"Candidate: {c['full_name']} (Mobile: {c['phone_number']}) | Status: {c.get('status')}"):
                        if c.get("admin_remarks"):
                            st.error(f"Admin Correction Notes: {c['admin_remarks']}")

                        with st.form(f"sup_verify_form_{c['id']}"):
                            st.write("##### 1. Identification & Credentials")
                            sc1, sc2, sc3 = st.columns(3)
                            s_code = sc1.text_input("Employee Code *", value=c.get("employee_code") or f"SE{str(c['id'])[:4].upper()}").strip().upper()
                            s_uid = sc2.text_input("User ID *", value=c.get("user_id") or s_code).strip()
                            s_pwd = sc3.text_input("Portal Password *", value=c.get("password") or f"emp{c['phone_number'][-4:]}")

                            st.write("##### 2. Organization, Client Site & Zone Assignment")
                            sc4, sc5 = st.columns(2)
                            c_ent_name = e_rev_map.get(sup_ent_id or c.get("entity_id"))
                            s_ent = sc4.selectbox("Assigned Entity / Firm *", [c_ent_name] if c_ent_name else list(e_map.keys()), key=f"se_{c['id']}")
                            c_cli_name = c_rev_map.get(sup_cli_id or c.get("client_id"))
                            s_cli = sc5.selectbox("Assigned Client Site *", [c_cli_name] if c_cli_name else list(c_map.keys()), key=f"sc_{c['id']}")

                            sc6, sc7 = st.columns(2)
                            s_dept = sc6.text_input("Department", value=c.get("department") or "Facility")
                            s_zone = sc7.selectbox("Zone *", ["Zone - 1", "Zone - 2", "Zone - 3"], index=2)

                            st.write("##### 3. Shift, Timings & Commercials")
                            sc_s1, sc_s2, sc_s3 = st.columns(3)

                            # 1. Shift Selection
                            curr_shift = c.get("shift_timing") or STANDARD_SHIFTS[0]
                            shift_idx = STANDARD_SHIFTS.index(curr_shift) if curr_shift in STANDARD_SHIFTS else 0
                            s_shift = sc_s1.selectbox(
                                "Assigned Shift Timing *", 
                                STANDARD_SHIFTS, 
                                index=shift_idx, 
                                key=f"sup_shift_{c['id']}"
                            )

                            # 2. Weekly Off Day Selection
                            wo_opts = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
                            curr_wo = c.get("weekly_off_day") or "Sunday"
                            wo_idx = wo_opts.index(curr_wo) if curr_wo in wo_opts else 0
                            s_wo = sc_s2.selectbox(
                                 "Weekly Off Day *", 
                                 wo_opts, 
                                index=wo_idx, 
                                key=f"sup_wo_{c['id']}"
                            )

                            # 3. Joining Date Selection
                            raw_c_join = c.get("joining_date") or c.get("created_at")
                            try:
                                 def_join = datetime.strptime(str(raw_c_join).split("T")[0], "%Y-%m-%d").date() if raw_c_join else date.today()
                            except Exception:
                                  def_join = date.today()

                            s_join_date = sc_s3.date_input(
                                "Joining Date *", 
                                value=def_join, 
                                format="DD/MM/YYYY", 
                                key=f"sup_join_{c['id']}"
                            )

                            st.write("##### 3. Dynamic Designations & Commercial Rules (From Salary Structure)")
                            target_ent_id = e_map.get(s_ent)
                            target_cli_id = c_map.get(s_cli)

                            # ॲडमिनने Salary Structure मध्ये तयार केलेले सर्व डिझिग्नेशन्स फेच करणे
                            sal_rules_res = []
                            try:
                                q_sr = supabase.table("salary_structures").select("designation, category").execute()
                                sal_rules_res = q_sr.data or []
                            except Exception:
                                sal_rules_res = []

                            available_designations = list(set([r["designation"] for r in sal_rules_res if r.get("designation")]))
                            if not available_designations:
                                available_designations = ["Welder A", "Welder B", "Supervisor", "Helper", "Housekeeping Associate"]

                            sd1, sd2, sd3 = st.columns(3)
                            s_cat = sd1.selectbox("Category *", ["Skilled", "Semi-Skilled", "Unskilled"], index=1, key=f"cat_{c['id']}")

                            curr_desig = c.get("designation")
                            d_idx = available_designations.index(curr_desig) if curr_desig in available_designations else 0
                            s_desig = sd2.selectbox("Designation (From Salary Structure) *", available_designations, index=d_idx, key=f"desig_{c['id']}")
                            s_ot = sd3.number_input("Custom OT Rate / Hour", min_value=0.0, step=10.0, value=float(c.get("ot_rate_per_hour") or 0.0), key=f"ot_{c['id']}")

                            
                            st.write("##### 4. Document Verification Check")
                            v_col1, v_col2 = st.columns(2)
                            with v_col1:
                                if c.get("photo_file"):
                                    st.markdown(f"📷 [Photo Verified]({c['photo_file']})")
                                if c.get("aadhar_file"):
                                    st.markdown(f"📄 [Aadhaar Verified]({c['aadhar_file']})")
                            with v_col2:
                                if c.get("pan_file"):
                                    st.markdown(f"📄 [PAN Verified]({c['pan_file']})")
                                if c.get("bank_file"):
                                    st.markdown(f"📄 [Bank Proof Verified]({c['bank_file']})")

                            if st.form_submit_button("Verify & Forward to Admin", type="primary"):
                                supabase.table("employees").update({
                                "employee_code": s_code,
                                "user_id": s_uid,
                                "password": s_pwd,
                                "entity_id": target_ent_id,
                                "client_id": target_cli_id,
                                "department": s_dept,
                                "zone": s_zone,
                                "category": s_cat,
                                "designation": s_desig,
                                "ot_rate_per_hour": s_ot if s_ot > 0 else None,
                                
                                # 👇 He navin add zalele 3 fields
                                "shift_timing": s_shift,
                                "weekly_off_day": s_wo,
                                "joining_date": str(s_join_date),
                                
                                "status": "PENDING_ADMIN",
                                "admin_remarks": None
                            }).eq("id", c["id"]).execute()

                            st.toast("✅ Candidate verified and forwarded to Admin!")
                            st.success("Candidate details updated and sent to Admin for final activation.")
                            pytime.sleep(1)
                            st.rerun()
            else:
                st.info("No candidates pending supervisor verification.")

        # =====================================================================
        # SUPERVISOR PANEL 2: SHIFT ROSTER MANAGEMENT (Assigned Sites Only)
        # =====================================================================
        elif selected_sup_panel == "Shift Roster Management (Assigned Sites)":
            st.subheader("Assigned Plant Site Shift Roster (Hybrid Bulk & Individual)")

            cli_list = fetch_cached_clients()
            if sup_ent_id:
                cli_list = [c for c in cli_list if c.get("entity_id") == sup_ent_id]
            if sup_cli_id:
                # Supervisor ला नेमणूक केलेले सर्व Client IDs फेच करणे
                assigned_client_ids = []
                if sup_id:
                  sup_cli_res = supabase.table("supervisor_clients").select("client_id").eq("supervisor_id", sup_id).execute().data or []
                  assigned_client_ids = [sc["client_id"] for sc in sup_cli_res]

# जर एकापेक्षा जास्त clients असतील तर त्यांची यादी फिल्टर करणे
            if assigned_client_ids:
              cli_list = [c for c in cli_list if c.get("id") in assigned_client_ids]
            elif sup_cli_id:
              cli_list = [c for c in cli_list if c.get("id") == sup_cli_id]

            c_dict = {c["name"]: c["id"] for c in cli_list}
            sel_s_cli = st.selectbox("Select Assigned Plant Site *", list(c_dict.keys()) if c_dict else ["No Client Assigned"])

            if sel_s_cli in c_dict:
                curr_site_cli_id = c_dict[sel_s_cli]

                s_scope = st.radio("Target Period Scope", ["Full Month", "Single Date"], horizontal=True)
                target_dates = []
                if s_scope == "Full Month":
                    r_month_input = st.date_input("Select Target Month (Any date in month)", value=date.today(), key="sup_r_month")
                    yr = r_month_input.year
                    mo = r_month_input.month
                    days_in_m = 31 if mo in [1, 3, 5, 7, 8, 10, 12] else (30 if mo != 2 else (29 if yr % 4 == 0 else 28))
                    target_dates = [str(date(yr, mo, d)) for d in range(1, days_in_m + 1)]
                    st.caption(f"Deployment configured for: **{r_month_input.strftime('%B %Y')}** ({len(target_dates)} Days)")
                else:
                    single_d = st.date_input("Select Target Date", value=date.today(), key="sup_r_date")
                    target_dates = [str(single_d)]
                    st.caption(f"Deployment configured for date: **{single_d}**")

                st.write("---")

                site_emps = [
                    e for e in fetch_cached_employees()
                    if e.get("client_id") == curr_site_cli_id and e.get("role") == "employee" and e.get("status") == "APPROVED"
                ]

                if site_emps:
                    st.write(f"##### Plant Workers Roster Setup ({len(site_emps)} Active Workers)")

                    st.markdown("""
                    <div style="background:#F1F5F9; border-left:4px solid #1E3A8A; padding:10px 14px; border-radius:6px; margin-bottom:12px;">
                        <b>Quick Master Bulk Action:</b> Select a master shift and apply to all site workers at once, then adjust individual rows if needed.
                    </div>
                    """, unsafe_allow_html=True)

                    sup_b1, sup_b2, sup_b3 = st.columns([2, 1.5, 2.5])
                    sup_master_shift = sup_b1.selectbox("Master Shift to Apply", STANDARD_SHIFTS, key="sup_master_shift_picker")
                    sup_preserve_wo = sup_b3.checkbox("Preserve Worker's Profile Weekly Off Day", value=True, key="sup_wo_chk")

                    if sup_b2.button("⚡ Apply to All", key="sup_btn_apply_all"):
                        for emp in site_emps:
                            st.session_state[f"sup_row_shift_{emp['id']}"] = sup_master_shift
                        st.toast(f"Applied '{sup_master_shift}' to all worker rows below!")

                    st.write("##### Individual Employee-Wise Shift Control")
                    with st.form("sup_deploy_complete_roster_form"):
                        sup_assigned_shifts = {}
                        for idx, emp in enumerate(site_emps, start=1):
                            emp_id = emp["id"]
                            emp_code = emp.get("employee_code", "TEMP")
                            emp_name = emp.get("full_name")
                            emp_desig = emp.get("designation", "Associate")
                            emp_cat = emp.get("category", "Semi-Skilled")
                            emp_wo_day = emp.get("weekly_off_day", "Sunday")

                            col_e1, col_e2, col_e3, col_e4 = st.columns([1, 4, 3, 4])
                            col_e1.write(f"**#{idx}**")
                            col_e2.write(f"**[{emp_code}] {emp_name}**")
                            col_e3.write(f"{emp_desig} ({emp_cat}) | WO: {emp_wo_day}")

                            def_shift = st.session_state.get(f"sup_row_shift_{emp_id}") or emp.get("shift_timing") or STANDARD_SHIFTS[0]
                            shift_index = STANDARD_SHIFTS.index(def_shift) if def_shift in STANDARD_SHIFTS else 0

                            row_val = col_e4.selectbox(
                                "Shift",
                                STANDARD_SHIFTS,
                                index=shift_index,
                                key=f"sup_row_shift_input_{emp_id}",
                                label_visibility="collapsed"
                            )
                            sup_assigned_shifts[emp_id] = (row_val, emp_wo_day)

                        st.write("---")
                        if st.form_submit_button("Deploy & Save Plant Shift Roster", type="primary"):
                            saved_count = 0
                            for emp_id, (chosen_shift, profile_wo) in sup_assigned_shifts.items():
                                for t_date_str in target_dates:
                                    d_dt = datetime.strptime(t_date_str, "%Y-%m-%d").date()
                                    day_name = d_dt.strftime("%A")
                                    final_shift = "Week Off" if (sup_preserve_wo and day_name == profile_wo) else chosen_shift
                                    supabase.table("shift_roster").upsert({
                                        "client_id": curr_site_cli_id,
                                        "employee_id": emp_id,
                                        "roster_date": t_date_str,
                                        "shift_name": final_shift
                                    }, on_conflict="employee_id,roster_date").execute()
                                    saved_count += 1

                            st.toast("✅ Plant Shift Roster Deployed Successfully!")
                            st.success(f"Roster saved for all {len(site_emps)} workers across {len(target_dates)} date(s)! (Total records: {saved_count})")
                            pytime.sleep(1)
                            st.rerun()
                else:
                    st.info("No approved workers deployed under your assigned client plant site.")
            else:
                st.info("No client plant site assigned to your supervisor account.")

        # =====================================================================
        # SUPERVISOR PANEL 3: SITE ATTENDANCE & PUNCH (Live Field Muster)
        # =====================================================================
        elif selected_sup_panel == "Site Attendance & Punch":
            st.subheader("Site Attendance Muster & Supervisor On-Field Punch Desk")

            cli_list = fetch_cached_clients()
            if sup_ent_id:
                cli_list = [c for c in cli_list if c.get("entity_id") == sup_ent_id]
            if sup_cli_id:
                cli_list = [c for c in cli_list if c.get("id") == sup_cli_id]

            c_dict = {c["name"]: c["id"] for c in cli_list}
            sel_site_name = st.selectbox("Select Plant Site *", list(c_dict.keys()) if c_dict else ["No Assigned Site"], key="att_punch_site")

            if sel_site_name in c_dict:
                curr_site_id = c_dict[sel_site_name]
                sel_att_date = st.date_input("Attendance Date *", value=date.today(), key="sup_att_date_picker")
                sel_date_str = str(sel_att_date)

                site_workers = [
                    e for e in fetch_cached_employees()
                    if e.get("client_id") == curr_site_id and e.get("role") == "employee" and e.get("status") == "APPROVED"
                ]

                if site_workers:
                    st.write(f"##### Mark / Verify Attendance for {len(site_workers)} Workers ({sel_att_date})")

                    # Fetch already saved attendance records for this date
                    existing_atts = supabase.table("attendance").select("*").eq("date", sel_date_str).execute().data or []
                    att_lookup = {a["employee_id"]: a for a in existing_atts}

                    with st.form("sup_site_attendance_form"):
                        attendance_entries = {}
                        status_options = ["P", "A", "HD", "WO", "PH", "L"]

                        for idx, worker in enumerate(site_workers, start=1):
                            w_id = worker["id"]
                            w_rec = att_lookup.get(w_id, {})
                            cur_status = w_rec.get("status", "P")
                            s_idx = status_options.index(cur_status) if cur_status in status_options else 0

                            col1, col2, col3, col4, col5 = st.columns([1, 4, 2, 2.5, 2.5])
                            col1.write(f"**#{idx}**")
                            col2.write(f"**[{worker.get('employee_code', 'TEMP')}] {worker.get('full_name')}**")
                            
                            status_val = col3.selectbox("Status", status_options, index=s_idx, key=f"st_{w_id}_{sel_date_str}", label_visibility="collapsed")
                            punch_in_val = col4.text_input("Punch In", value=w_rec.get("punch_in") or "08:30:00", key=f"pi_{w_id}_{sel_date_str}", label_visibility="collapsed")
                            punch_out_val = col5.text_input("Punch Out", value=w_rec.get("punch_out") or "17:00:00", key=f"po_{w_id}_{sel_date_str}", label_visibility="collapsed")

                            attendance_entries[w_id] = {
                                "status": status_val,
                                "punch_in": punch_in_val if status_val not in ["A", "WO"] else None,
                                "punch_out": punch_out_val if status_val not in ["A", "WO"] else None
                            }

                        if st.form_submit_button("Save & Update Site Attendance", type="primary"):
                            for w_id, entry in attendance_entries.items():
                                supabase.table("attendance").upsert({
                                    "employee_id": w_id,
                                    "date": sel_date_str,
                                    "status": entry["status"],
                                    "punch_in": entry["punch_in"],
                                    "punch_out": entry["punch_out"],
                                    "is_valid_geo": True
                                }, on_conflict="employee_id,date").execute()

                            st.toast("✅ Site Attendance Updated Successfully!")
                            st.success(f"Attendance recorded for {len(site_workers)} workers on {sel_date_str}.")
                            pytime.sleep(1)
                            st.rerun()
                else:
                    st.info("No active staff deployed at this site.")
            else:
                st.info("No assigned site found.")

        # =====================================================================
        # SUPERVISOR PANEL 4: WORKFORCE ROSTER (Site Workforce Overview)
        # =====================================================================
        elif selected_sup_panel == "Workforce Roster":
            st.subheader("Assigned Plant Deployed Workforce Directory")

            emp_q = supabase.table("employees").select("*").eq("role", "employee").eq("status", "APPROVED")
            if sup_cli_id:
                emp_q = emp_q.eq("client_id", sup_cli_id)
            elif sup_ent_id:
                emp_q = emp_q.eq("entity_id", sup_ent_id)

            staff_list = emp_q.execute().data or []

            if staff_list:
                st.write(f"##### Total Active Deployed Staff: **{len(staff_list)} Workers**")

                wf_rows = []
                for idx, emp in enumerate(staff_list, start=1):
                    wf_rows.append({
                        "SR No": idx,
                        "Emp Code": emp.get("employee_code", "TEMP"),
                        "Full Name": emp.get("full_name"),
                        "Designation": emp.get("designation", "Associate"),
                        "Category": emp.get("category", "Semi-Skilled"),
                        "Mobile": emp.get("phone_number"),
                        "Shift": emp.get("shift_timing", "General"),
                        "Weekly Off": emp.get("weekly_off_day", "Sunday"),
                        "DOJ": emp.get("joining_date", "-")
                    })
                df_wf = pd.DataFrame(wf_rows)
                st.dataframe(df_wf, use_container_width=True)

                csv_wf = df_wf.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "Download Workforce List (CSV)",
                    data=csv_wf,
                    file_name=f"Workforce_Roster_{date.today()}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No active staff records deployed under your supervision.")

        # =====================================================================
        # SUPERVISOR PANEL 5: PPE & ADVANCE APPROVALS
        # =====================================================================
        elif selected_sup_panel == "PPE & Advance Approvals":
            st.subheader("PPE Equipment & Salary Advance Request Approvals")

            t_app_ppe, t_app_adv = st.tabs(["🦺 PPE Equipment Approvals", "💵 Salary Advance Approvals"])

            # Tab 1: PPE Requests
            with t_app_ppe:
                st.write("##### Pending PPE Equipment Requests")
                ppe_q = supabase.table("ppe_records").select("*").eq("status", "PENDING_SUPERVISOR")
                pending_ppes = ppe_q.execute().data or []

                if pending_ppes:
                    all_emps_data = {e["id"]: e for e in fetch_cached_employees()}
                    for p in pending_ppes:
                        p_id = p["id"]
                        p_emp = all_emps_data.get(p.get("employee_id"), {})
                        with st.expander(f"Worker: {p_emp.get('full_name', 'Staff')} [{p_emp.get('employee_code', 'TEMP')}] | Item: {p.get('item_type')} (Qty: {p.get('quantity')})"):
                            st.write(f"• **Requested Cost:** Rs.{float(p.get('cost', 0)):,.2f}")
                            st.write(f"• **Request Date:** {p.get('assigned_date', '-')}")

                            col_p1, col_p2 = st.columns(2)
                            if col_p1.button("Approve PPE Request", key=f"sup_app_ppe_{p_id}", type="primary"):
                                supabase.table("ppe_records").update({"status": "APPROVED"}).eq("id", p_id).execute()
                                st.toast("✅ PPE Request Approved!")
                                st.success("PPE Approved successfully.")
                                pytime.sleep(1)
                                st.rerun()

                            if col_p2.button("Reject PPE Request", key=f"sup_rej_ppe_{p_id}"):
                                supabase.table("ppe_records").update({"status": "REJECTED"}).eq("id", p_id).execute()
                                st.toast("PPE Request Rejected.")
                                pytime.sleep(1)
                                st.rerun()
                else:
                    st.info("No pending PPE requests.")

            # Tab 2: Salary Advance Requests
            with t_app_adv:
                st.write("##### Pending Salary Advance Requests")
                adv_q = supabase.table("advance_salaries").select("*").eq("status", "PENDING_SUPERVISOR")
                pending_advs = adv_q.execute().data or []

                if pending_advs:
                    all_emps_data = {e["id"]: e for e in fetch_cached_employees()}
                    for a in pending_advs:
                        a_id = a["id"]
                        a_emp = all_emps_data.get(a.get("employee_id"), {})
                        with st.expander(f"Worker: {a_emp.get('full_name', 'Staff')} [{a_emp.get('employee_code', 'TEMP')}] | Amount: Rs.{float(a.get('amount', 0)):,.2f}"):
                            st.write(f"• **Reason:** {a.get('reason', '-')}")
                            st.write(f"• **Request Date:** {a.get('requested_date', '-')}")

                            col_a1, col_a2 = st.columns(2)
                            if col_a1.button("Forward to Admin (Approved by Supervisor)", key=f"sup_app_adv_{a_id}", type="primary"):
                                supabase.table("advance_salaries").update({"status": "PENDING_ADMIN"}).eq("id", a_id).execute()
                                st.toast("✅ Forwarded to Admin!")
                                st.success("Advance approved and sent to Admin for final release.")
                                pytime.sleep(1)
                                st.rerun()

                            if col_a2.button("Reject Advance", key=f"sup_rej_adv_{a_id}"):
                                supabase.table("advance_salaries").update({"status": "REJECTED_BY_SUPERVISOR"}).eq("id", a_id).execute()
                                st.toast("Advance Request Rejected.")
                                pytime.sleep(1)
                                st.rerun()
                else:
                    st.info("No pending salary advance requests.")

        # =====================================================================
        # SUPERVISOR PANEL 6: EMPLOYEE LEAVE REQUESTS
        # =====================================================================
        elif selected_sup_panel == "Employee Leave Requests":
            st.subheader("Plant Workforce Leave Applications Desk")

            leaves_q = supabase.table("leave_requests").select("*").eq("status", "PENDING_SUPERVISOR").order("created_at", desc=True)
            pending_lvs = leaves_q.execute().data or []

            all_emps_data = {e["id"]: e for e in fetch_cached_employees()}

            if pending_lvs:
                st.write(f"##### Applications Awaiting Verification: **{len(pending_lvs)} Requests**")

                for lv in pending_lvs:
                    lv_id = lv["id"]
                    emp_rec = all_emps_data.get(lv.get("employee_id"), {})

                    with st.expander(f"Worker: {emp_rec.get('full_name', 'Staff')} [{emp_rec.get('employee_code', 'TEMP')}] | Type: {lv.get('leave_type')} ({lv.get('total_days')} Days)"):
                        st.write(f"• **Period:** {lv.get('start_date')} to {lv.get('end_date')}")
                        st.write(f"• **Reason:** {lv.get('reason')}")
                        if lv.get("document_file"):
                            st.markdown(f"📄 [Medical / Proof Document]({lv['document_file']})")

                        col_l1, col_l2 = st.columns(2)
                        if col_l1.button("Verify & Forward to Admin", key=f"sup_app_lv_{lv_id}", type="primary"):
                            supabase.table("leave_requests").update({"status": "PENDING_ADMIN"}).eq("id", lv_id).execute()
                            st.toast("✅ Leave application verified and sent to Admin!")
                            st.success("Verified and forwarded to Admin.")
                            pytime.sleep(1)
                            st.rerun()

                        if col_l2.button("Reject Leave Application", key=f"sup_rej_lv_{lv_id}"):
                            supabase.table("leave_requests").update({"status": "REJECTED_BY_SUPERVISOR"}).eq("id", lv_id).execute()
                            st.toast("Leave application rejected.")
                            pytime.sleep(1)
                            st.rerun()
            else:
                st.info("No employee leave requests pending supervisor verification.")

    # -------------------------------------------------------------------------
    # 4.3 CLIENT DESK PORTAL
    # -------------------------------------------------------------------------
    elif active_role == "client":
        client_user = st.session_state.user
        client_cli_id = client_user.get("client_id")
        client_ent_id = client_user.get("entity_id")

        if "active_client_tab" not in st.session_state:
            st.session_state.active_client_tab = "Plant Workforce Overview"

        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS CLIENT</div>', unsafe_allow_html=True)
            st.markdown('<div class="logged-badge">Logged In: CLIENT DESK</div>', unsafe_allow_html=True)
            st.write(f"Client Rep: **{client_user.get('full_name')}**")
            st.caption("CLIENT PORTAL")

            client_tabs = [
                "Plant Workforce Overview",
                "Daily Attendance Muster",
                "Monthly Invoices & Billing",
                "Compliance & Wage Sheets"
            ]
            for cl_tab in client_tabs:
                btn_style = "primary" if st.session_state.active_client_tab == cl_tab else "secondary"
                if st.button(cl_tab, key=f"cl_btn_{cl_tab}", type=btn_style):
                    st.session_state.active_client_tab = cl_tab
                    st.rerun()

            st.write("---")
            if st.button("Logout", key="cli_logout"):
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

        selected_client_panel = st.session_state.active_client_tab
        st.title(selected_client_panel)

        # 1. PLANT WORKFORCE OVERVIEW
        if selected_client_panel == "Plant Workforce Overview":
            st.subheader("Active Plant Deployed Workforce")
            emp_q = supabase.table("employees").select("employee_code, full_name, designation, category, phone_number, joining_date").eq("role", "employee").eq("status", "APPROVED")
            if client_cli_id:
                emp_q = emp_q.eq("client_id", client_cli_id)
            elif client_ent_id:
                emp_q = emp_q.eq("entity_id", client_ent_id)
                
            emps = emp_q.execute().data or []
            if emps:
                st.dataframe(pd.DataFrame(emps), use_container_width=True)
            else:
                st.info("No active staff deployed under your client plant site.")

        # 2. DAILY ATTENDANCE MUSTER
        elif selected_client_panel == "Daily Attendance Muster":
            st.subheader("Daily Plant Attendance Muster")
            att_date_sel = st.date_input("Select Muster Date", value=date.today(), key="cli_att_date")
            
            att_q = supabase.table("attendance").select("*").eq("date", str(att_date_sel))
            att_data = att_q.execute().data or []
            
            if att_data:
                st.dataframe(pd.DataFrame(att_data), use_container_width=True)
            else:
                st.info(f"No attendance records found for {att_date_sel}.")

        # 3. MONTHLY INVOICES & BILLING
        elif selected_client_panel == "Monthly Invoices & Billing":
            st.subheader("Tax Invoices & Billing Statements")
            inv_q = supabase.table("client_invoices").select("*")
            if client_cli_id:
                inv_q = inv_q.eq("client_id", client_cli_id)
            
            inv_list = inv_q.execute().data or []
            if inv_list:
                st.dataframe(pd.DataFrame(inv_list), use_container_width=True)
            else:
                st.info("No tax invoices issued for your plant site yet.")

        # 4. COMPLIANCE & WAGE SHEETS
        elif selected_client_panel == "Compliance & Wage Sheets":
            st.subheader("Verified Statutory Compliance & Locked Wage Sheets")
            st.info("Verified monthly locked wage sheets and legal compliance documents are available here for client audit and review.")
            
            locked_q = supabase.table("locked_payrolls").select("*").eq("is_locked", True)
            if client_cli_id:
                locked_q = locked_q.eq("client_id", client_cli_id)
                
            locked_res = locked_q.execute().data or []
            if locked_res:
                st.dataframe(pd.DataFrame(locked_res), use_container_width=True)
            else:
                st.info("No locked payroll wage sheets available for review yet.")

    # -------------------------------------------------------------------------
    # 4.4 EMPLOYEE DESK PORTAL
    # -------------------------------------------------------------------------
    elif active_role == "employee":
        emp_user = st.session_state.user
        emp_id = emp_user.get("id")

        if "active_emp_tab" not in st.session_state:
            st.session_state.active_emp_tab = "Daily Punch (Geofenced)"

        with st.sidebar:
            st.markdown('<div class="sidebar-brand">ESS EMPLOYEE DESK</div>', unsafe_allow_html=True)
            st.markdown('<div class="logged-badge">Logged In: EMPLOYEE</div>', unsafe_allow_html=True)
            st.write(f"Worker: **{emp_user.get('full_name')}**")
            st.caption(f"Code: {emp_user.get('employee_code', 'TEMP')}")

            emp_tabs = [
                "Daily Punch (Geofenced)",
                "Apply Leave & Balance",
                "Attendance Calendar",
                "Monthly Payslips (15th)",
                "Helpdesk & Queries",
                "My Profile Details",
                "Official Documents Vault",
                "Request PPE Equipment",
                "Request Salary Advance",
                "Change Password"
            ]

            for e_tab in emp_tabs:
                btn_style = "primary" if st.session_state.active_emp_tab == e_tab else "secondary"
                if st.button(e_tab, key=f"emp_btn_{e_tab}", type=btn_style):
                    st.session_state.active_emp_tab = e_tab
                    st.rerun()

            st.write("---")
            if st.button("Logout", key="emp_logout"):
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

        selected_emp_panel = st.session_state.active_emp_tab
        st.title(selected_emp_panel)

        # EMPLOYEE PANEL 1: DAILY PUNCH
        if selected_emp_panel == "Daily Punch (Geofenced)":
            st.subheader("Daily Attendance Geo-Punch (Live GPS & Geofence Engine)")

            today_date_str = str(date.today())
            
            # 1. Device Binding Check
            current_device_id = st.query_params.get("device_id") or f"dev_{emp_id[:8]}"
            db_binding = emp_user.get("device_binding_id")

            if not db_binding:
                supabase.table("employees").update({"device_binding_id": current_device_id}).eq("id", emp_id).execute()
                st.toast("🔒 Device Successfully Bound!")
            elif db_binding != current_device_id and db_binding != "BROWSER_DEVICE_ID_DEFAULT":
                st.error("⚠️ Security Alert: Device Mismatch! Contact Admin to reset Device Binding.")
                st.stop()

            # 2. HTML5 Geolocation JavaScript Component to fetch live GPS automatically
            import streamlit.components.v1 as components
            
            st.markdown("##### 📍 Live GPS Sensor Status")
            
            # Streamlit custom component to grab user's real latitude & longitude via browser
            loc_code = """
            <div id="loc-status" style="font-family:sans-serif; font-size:13px; color:#059669; font-weight:600; margin-bottom:10px;">
                🔄 Fetching live GPS location from your phone...
            </div>
            <script>
            function getLocation() {
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(showPosition, showError, {timeout: 10000, enableHighAccuracy: true});
                } else {
                    document.getElementById("loc-status").innerHTML = "❌ Geolocation is not supported by this browser.";
                }
            }
            function showPosition(position) {
                const lat = position.coords.latitude;
                const lon = position.coords.longitude;
                document.getElementById("loc-status").innerHTML = "✅ Live GPS Locked: Lat " + lat.toFixed(6) + ", Lon " + lon.toFixed(6);
                
                // Pass values back via URL query params or session state if needed
                const url = new URL(window.location.href);
                url.searchParams.set('user_lat', lat);
                url.searchParams.set('user_lon', lon);
                window.history.replaceState({}, '', url);
            }
            function showError(error) {
                document.getElementById("loc-status").innerHTML = "⚠️ GPS Error: Please enable phone Location/GPS permission.";
            }
            getLocation();
            </script>
            """
            components.html(loc_code, height=45)

            # Retrieve coordinates from query params or fallback to client site location for simulation
            client_site_id = emp_user.get("client_id")
            client_record = supabase.table("clients").select("latitude, longitude, name").eq("id", client_site_id).execute().data
            
            # Default to client location if live GPS is loading, to prevent 24000km error
            default_lat = float(client_record[0].get("latitude", 18.651200)) if client_record else 18.651200
            default_lon = float(client_record[0].get("longitude", 73.805500)) if client_record else 73.805500

            try:
                user_lat = float(st.query_params.get("user_lat", default_lat))
                user_lon = float(st.query_params.get("user_lon", default_lon))
            except Exception:
                user_lat, user_lon = default_lat, default_lon

            # Display locked location in disabled/read-only inputs so employee cannot edit it
            st.text_input("Auto-Captured Latitude (Live GPS)", value=f"{user_lat:.6f}", disabled=True)
            st.text_input("Auto-Captured Longitude (Live GPS)", value=f"{user_lon:.6f}", disabled=True)

            today_att = supabase.table("attendance").select("*").eq("employee_id", emp_id).eq("date", today_date_str).execute().data
            
            with st.form("employee_geo_punch_form_final_engine"):
                is_offline_mode = st.checkbox("Simulate No Network (Offline Punch Mode)", value=False)

                if st.form_submit_button("Thumb / Geo Punch Now", type="primary"):
                     current_time_str = datetime.now().strftime("%H:%M:%S")
            geofence_passed = True
            dist_meters = 0.0

            if client_record and not is_offline_mode:
                c_lat = float(client_record[0].get("latitude", 18.651200))
                c_lon = float(client_record[0].get("longitude", 73.805500))
                
                lat1, lon1, lat2, lon2 = map(math.radians, [user_lat, user_lon, c_lat, c_lon])
                dlon = lon2 - lon1
                dlat = lat2 - lat1
                a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                c = 2 * math.asin(math.sqrt(a))
                dist_meters = c * 6371000 # Meters

                if dist_meters > 50.0:
                    geofence_passed = False

            if not geofence_passed:
                st.error(f"❌ Invalid Location: You are outside the plant geofence radius (Distance: {dist_meters:.1f}m).")
            elif is_offline_mode:
                st.warning("⚠️ Offline Mode: Punch saved locally.")
            else:
                # 1. आधी तपासा की आजची एंट्री आधीपासून आहे का
                check_att = supabase.table("attendance").select("id, punch_in").eq("employee_id", emp_id).eq("date", today_date_str).execute().data

                if not check_att:
                    # 2. आजची पहिलीच एंट्री असेल तर INSERT करा (First Punch-In)
                    supabase.table("attendance").insert({
                        "employee_id": emp_id,
                        "date": today_date_str,
                        "status": "P",
                        "punch_in": current_time_str,
                        "punch_out": None,
                        "ot_hours": 0.0,
                        "is_valid_geo": True
                    }).execute()
                    st.toast("✅ First Punch-In Recorded Successfully!")
                else:
                    # 3. आधीच पंच-इन असेल तर फक्त PUNCH-OUT अपडेट करा (Last Punch-Out)
                    att_id = check_att[0]["id"]
                    supabase.table("attendance").update({
                        "punch_out": current_time_str
                    }).eq("id", att_id).execute()
                    st.toast("✅ Attendance Updated with Punch-Out Time!")
                    
                pytime.sleep(1)
                st.rerun()

        # EMPLOYEE PANEL 2: APPLY LEAVE & BALANCE
        elif selected_emp_panel == "Apply Leave & Balance":
            st.subheader("Employee Leave Applications & Quota Balance Ledger")
            bal_res = supabase.table("leave_balances").select("*").eq("employee_id", emp_id).execute().data
            tot_credited = float(bal_res[0].get("total_credited", 15.0)) if bal_res else 15.0
            used_l = float(bal_res[0].get("used_leaves", 0.0)) if bal_res else 0.0
            bal_l = float(bal_res[0].get("balance_leaves", 15.0)) if bal_res else 15.0

            k1, k2, k3 = st.columns(3)
            k1.metric("Annual Quota", f"{tot_credited:.1f} Days")
            k2.metric("Used Leaves", f"{used_l:.1f} Days")
            k3.metric("Available Balance", f"{bal_l:.1f} Days")

            with st.form("employee_apply_leave_form"):
                l_type = st.selectbox("Leave Type *", ["CL - Casual Leave", "SL - Sick Leave", "EL - Earned Leave", "LWP - Leave Without Pay"])
                l_start = st.date_input("Start Date *", value=date.today())
                l_end = st.date_input("End Date *", value=date.today())
                l_reason = st.text_area("Reason for Leave *")
                if st.form_submit_button("Submit Leave Application", type="primary"):
                    if l_reason.strip():
                        supabase.table("leave_requests").insert({
                            "employee_id": emp_id, "leave_type": l_type[:3],
                            "start_date": str(l_start), "end_date": str(l_end),
                            "total_days": max(1.0, float((l_end - l_start).days + 1)),
                            "reason": l_reason.strip(), "status": "PENDING_SUPERVISOR"
                        }).execute()
                        st.success("Leave request submitted successfully!")
                        st.rerun()

        # EMPLOYEE PANEL 3: ATTENDANCE TRACKING & CALENDAR
        elif selected_emp_panel == "Attendance Calendar":
            st.subheader("Attendance Tracking & Time Log Dashboards")

            t_att_today, t_att_month, t_att_year = st.tabs([
                "⏱️ Today's Punch Summary", 
                "📅 Full Month Attendance", 
                "📊 Selected Year Attendance"
            ])

            today_date_str = str(date.today())
            curr_yr = date.today().year

            with t_att_today:
                st.write(f"##### Today's Live Punch Status ({today_date_str})")
                today_rec_res = supabase.table("attendance").select("*").eq("employee_id", emp_id).eq("date", today_date_str).execute().data
                
                if today_rec_res:
                    rec = today_rec_res[0]
                    tc1, tc2, tc3, tc4 = st.columns(4)
                    tc1.metric("Attendance Status", rec.get("status", "P"))
                    tc2.metric("First Punch-In (In)", rec.get("punch_in", "Not Yet"))
                    tc3.metric("Last Punch-Out (Out)", rec.get("punch_out", "Active / Working"))
                    tc4.metric("Logged OT Hours", f"{rec.get('ot_hours', 0.0)} Hrs")
                else:
                    st.info("No punch recorded for today yet. Use 'Daily Punch (Geofenced)' panel to punch in.")

            with t_att_month:
                st.write("##### Full Month Attendance Register & Color-Coded Logs")
                sel_m_picker = st.date_input("Select Month (Any date in month)", value=date.today(), key="emp_m_att_picker")
                yr_m, mo_m = sel_m_picker.year, sel_m_picker.month
                
                # महिना सुरू होण्याची आणि संपण्याची तारीख काढणे
                import calendar
                last_day = calendar.monthrange(yr_m, mo_m)[1]
                start_date_str = f"{yr_m}-{mo_m:02d}-01"
                end_date_str = f"{yr_m}-{mo_m:02d}-{last_day}"
                
                # Like ऐवजी gte (greater than equal) आणि lte (less than equal) वापरणे
                month_atts = []
                try:
                    res_m = supabase.table("attendance").select("*").eq("employee_id", emp_id).gte("date", start_date_str).lte("date", end_date_str).order("date", desc=True).execute()
                    month_atts = res_m.data or []
                except Exception:
                    month_atts = []
                
                if month_atts:
                    # Metrics Summary
                    tot_pres = sum(1 for a in month_atts if a.get("status") in ["P", "WO", "PH"])
                    tot_ot_mo = sum(float(a.get("ot_hours", 0.0) or 0.0) for a in month_atts)
                    
                    mc1, mc2 = st.columns(2)
                    mc1.metric("Total Present / Paid Days", f"{tot_pres} Days")
                    mc2.metric("Total OT (This Month)", f"{tot_ot_mo:.1f} Hrs")
                    
                    st.markdown("---")

                    # Color-Coded Card Layout for each day
                    for att in month_atts:
                        att_date = att.get("date", "-")
                        status = att.get("status", "P")
                        p_in = att.get("punch_in") or "Not Punched"
                        p_out = att.get("punch_out") or "Active / Working"
                        ot = att.get("ot_hours", 0.0)

                        # Status-wise custom colors & labels
                        if status == "WO":
                            status_color = "#6B7280"  # Grey
                            status_text = "⚪ Week Off (WO)"
                        elif status == "PH":
                            status_color = "#D97706"  # Orange
                            status_text = "🟠 Paid Holiday (PH)"
                        elif status in ["L", "CL", "SL", "EL", "LWP"]:
                            status_color = "#7C3AED"  # Purple
                            status_text = f"🟣 Leave ({status})"
                        elif status in ["P", "HD"]:
                            status_color = "#059669"  # Green
                            status_text = f"🟢 Present ({status})"
                        else:
                            status_color = "#DC2626"  # Red
                            status_text = f"🔴 Absent / {status}"

                        st.markdown(f"""
                        <div style="padding: 12px; border-radius: 8px; border: 1px solid #E5E7EB; margin-bottom: 8px; background-color: #F9FAFB; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <strong style="font-size: 15px; color: #1F2937;">📅 Date: {att_date}</strong>
                                <span style="background-color: {status_color}15; color: {status_color}; padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700;">{status_text}</span>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; font-size: 13px; color: #4B5563; margin-top: 8px;">
                                <div>⏰ <b>Punch-In:</b> <span style="color: #111827;">{p_in}</span></div>
                                <div>⏳ <b>Punch-Out:</b> <span style="color: #111827;">{p_out}</span></div>
                                <div>⚡ <b>OT Hours:</b> <span style="color: #2563EB; font-weight: 600;">{ot} Hrs</span></div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info(f"No attendance records found for {sel_m_picker.strftime('%B %Y')}.")

            with t_att_year:
                st.write("##### Selected Year Attendance History")
                sel_year_val = st.number_input("Enter Year", min_value=2024, max_value=2030, value=curr_yr, step=1)
                
                year_prefix = f"{sel_year_val}"
                year_atts = supabase.table("attendance").select("*").eq("employee_id", emp_id).like("date", f"{year_prefix}%").order("date", desc=True).execute().data or []
                
                if year_atts:
                    tot_days_present = len([y for y in year_atts if y.get("status") in ["P", "WO", "PH", "HD"]])
                    tot_ot_hrs = sum([float(y.get("ot_hours") or 0.0) for y in year_atts])
                    
                    yc1, yc2 = st.columns(2)
                    yc1.metric(f"Total Working/Paid Days ({sel_year_val})", f"{tot_days_present} Days")
                    yc2.metric(f"Total Accumulated OT ({sel_year_val})", f"{tot_ot_hrs:.1f} Hours")
                    
                    st.markdown("---")
                    
                    for att in year_atts:
                        att_date = att.get("date", "-")
                        status = att.get("status", "P")
                        p_in = att.get("punch_in") or "-"
                        p_out = att.get("punch_out") or "-"
                        ot = att.get("ot_hours", 0.0)
                        
                        # Status-wise custom colors for year view
                        if status == "WO":
                            status_color = "#6B7280"
                            status_text = "⚪ WO"
                        elif status == "PH":
                            status_color = "#D97706"
                            status_text = "🟠 PH"
                        elif status in ["L", "CL", "SL", "EL", "LWP"]:
                            status_color = "#7C3AED"
                            status_text = f"🟣 {status}"
                        elif status in ["P", "HD"]:
                            status_color = "#059669"
                            status_text = f"🟢 {status}"
                        else:
                            status_color = "#DC2626"
                            status_text = f"🔴 {status}"

                        st.markdown(f"""
                        <div style="padding: 10px 14px; border-radius: 6px; border: 1px solid #E5E7EB; margin-bottom: 6px; background-color: #FFFFFF; box-shadow: 0 1px 2px rgba(0,0,0,0.01);">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 14px; font-weight: 600; color: #1F2937;">📅 {att_date}</span>
                                <span style="background-color: {status_color}15; color: {status_color}; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 700;">{status_text}</span>
                                <span style="font-size: 12px; color: #2563EB; font-weight: 600;">OT: {ot} Hrs</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info(f"No records found for the year {sel_year_val}.")

        # EMPLOYEE PANEL 4: MONTHLY PAYSLIPS
        elif selected_emp_panel == "Monthly Payslips (15th)":
            st.subheader("Official Monthly Salary Slips (Available on 15th)")

            slip_month_choice = st.selectbox("Select Pay Month *", ["August 2026", "September 2026", "October 2026"])
            
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            
            ent_obj = next((e for e in ent_list if e["id"] == emp_user.get("entity_id")), ent_list[0] if ent_list else {"name": "GEMSHINE MULTISERVICES", "address": "Ground Floor, Gat No. 235, Khandoba Temple, Khed SEZ Road, Rajgurunagar, Maharashtra - 410505, India"})
            cli_obj = next((c for c in cli_list if c["id"] == emp_user.get("client_id")), {"name": "DC&T Global Private Limited"})

            if st.button("Generate & View Payslip", type="primary"):
                payslip_html = f"""
                <div style="background:#ffffff; border:1px solid #94A3B8; padding:24px; font-family:Arial, sans-serif; color:#0F172A; max-width:800px; margin:auto; border-radius:4px;">
                    <!-- Header -->
                    <table style="width:100%; border-bottom:2px solid #0F172A; padding-bottom:12px; margin-bottom:16px;">
                        <tr>
                            <td>
                                <h3 style="margin:0; color:#0F172A; font-size:20px;">Salary Slip for {slip_month_choice}</h3>
                            </td>
                            <td style="text-align:right;">
                                <b style="font-size:16px; color:#0F172A;">{ent_obj.get('name', 'GEMSHINE MULTISERVICES')}</b><br/>
                                <span style="font-size:11px; color:#475569;">Registered Office: {ent_obj.get('address', 'Khed SEZ Road, Rajgurunagar, MH')}</span>
                            </td>
                        </tr>
                    </table>

                    <!-- Details Grid Table -->
                    <table style="width:100%; border-collapse:collapse; font-size:13px; margin-bottom:16px; border:1px solid #CBD5E1;">
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px; width:20%; background:#F8FAFC;"><b>Emp. Code:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px; width:30%;">{emp_user.get('employee_code', 'GM001')}</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; width:20%; background:#F8FAFC;"><b>Paid Days:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px; width:30%;">26.0</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>Name:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">{emp_user.get('full_name', 'Rupali Mohan Padwal')}</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>Total Days:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">26</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>Designation:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">{emp_user.get('designation', 'Housekeeping Associate')}</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>Bank Name:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">STATE BANK OF INDIA</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>Client Site:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">{cli_obj.get('name', 'DC&T Global Private Limited')}</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>Bank A/c No.:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">34228310127</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>DOJ:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">{emp_user.get('joining_date', '2026-05-01')}</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>PAN No.:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">GKCPP2904J</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>Category:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">{emp_user.get('category', 'Semi-Skilled')}</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;"><b>Aadhaar No.:</b></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">[Aadhaar Redacted]</td>
                        </tr>
                    </table>

                    <!-- Earnings & Deductions Table -->
                    <table style="width:100%; border-collapse:collapse; font-size:13px; margin-bottom:16px; border:1px solid #CBD5E1;">
                        <tr style="background:#F1F5F9;">
                            <th style="border:1px solid #CBD5E1; padding:8px; text-align:left; width:35%;">Earnings in Rs.</th>
                            <th style="border:1px solid #CBD5E1; padding:8px; text-align:right; width:15%;">Monthly Rate</th>
                            <th style="border:1px solid #CBD5E1; padding:8px; text-align:right; width:15%;">Earned (Rs.)</th>
                            <th style="border:1px solid #CBD5E1; padding:8px; text-align:left; width:25%;">Deductions</th>
                            <th style="border:1px solid #CBD5E1; padding:8px; text-align:right; width:10%;">Amount Rs.</th>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px;">Basic</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">15,025.00</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">15,025.00</td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">Provident Fund (PF)</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">1,800.00</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px;">D.A.</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">2,511.00</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">2,511.00</td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">ESIC</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">192.47</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px;">H.R.A.</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">877.00</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">877.00</td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">Prof. Tax (PT)</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">200.00</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px;">Overtime (OT)</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">-</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">0.00</td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">Salary Advance</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">2,000.00</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px;"></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;"></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;"></td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">Uniform / PPE</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">0.00</td>
                        </tr>
                        <tr style="background:#F8FAFC; font-weight:bold;">
                            <td style="border:1px solid #CBD5E1; padding:8px;">Gross Earning</td>
                            <td style="border:1px solid #CBD5E1; padding:8px;"></td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">18,413.00</td>
                            <td style="border:1px solid #CBD5E1; padding:8px;">Total Deductions</td>
                            <td style="border:1px solid #CBD5E1; padding:8px; text-align:right;">4,192.47</td>
                        </tr>
                    </table>

                    <!-- Net Salary & Words -->
                    <table style="width:100%; border-collapse:collapse; font-size:13px; margin-bottom:16px; border:1px solid #CBD5E1;">
                        <tr style="background:#EFF6FF;">
                            <td style="border:1px solid #CBD5E1; padding:10px; font-weight:bold; font-size:15px;" colspan="2">Net Salary: Rs. 14,220.53</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px; background:#F8FAFC;" colspan="2"><b>Amount in Words:</b> Indian Rupees Fourteen Thousand Two Hundred and Twenty and Fifty Three Paise Only</td>
                        </tr>
                        <tr>
                            <td style="border:1px solid #CBD5E1; padding:8px;" colspan="2"><b>Remarks:</b> -</td>
                        </tr>
                    </table>

                    <!-- Footer Note -->
                    <div style="text-align:center; font-size:11px; color:#64748B; border-top:1px solid #CBD5E1; padding-top:8px;">
                        This is computer generated payslip and does not require any signature.
                    </div>
                </div>
                """
                st.markdown(payslip_html, unsafe_allow_html=True)
                st.download_button(
                    "Download Official Payslip (PDF/HTML)", 
                    data=payslip_html, 
                    file_name=f"Payslip_{emp_user.get('employee_code')}_{slip_month_choice.replace(' ', '_')}.html", 
                    mime="text/html"
                )

        # EMPLOYEE PANEL 5: HELPDESK & QUERIES
        elif selected_emp_panel == "Helpdesk & Queries":
            st.subheader("Employee Helpdesk & Grievance Tickets Desk")

            t_tk_raise, t_tk_list = st.tabs(["Raise New Ticket", "My Tickets History"])

            with t_tk_raise:
                with st.form("employee_raise_ticket_form"):
                    tk_subj = st.text_input("Subject * (e.g. PF UAN Update / Salary Correction)")
                    tk_cat = st.selectbox("Category *", ["Payroll & Salary", "Attendance & Punch", "PF / ESIC", "Uniform / PPE", "Other"])
                    tk_desc = st.text_area("Detailed Description *")

                    if st.form_submit_button("Submit Helpdesk Ticket", type="primary"):
                        if not tk_subj.strip() or not tk_desc.strip():
                            st.error("Subject and Description are mandatory!")
                        else:
                            supabase.table("helpdesk_tickets").insert({
                                "employee_id": emp_id,
                                "subject": tk_subj.strip(),
                                "category": tk_cat,
                                "description": tk_desc.strip(),
                                "status": "OPEN"
                            }).execute()
                            st.toast("✅ Helpdesk Ticket Submitted Successfully!")
                            st.success("Your grievance has been registered. Admin will respond shortly.")
                            pytime.sleep(1)
                            st.rerun()

            with t_tk_list:
                st.write("##### Your Registered Tickets & Admin Responses")
                my_tickets = supabase.table("helpdesk_tickets").select("*").eq("employee_id", emp_id).order("created_at", desc=True).execute().data or []
                
                if my_tickets:
                    for t in my_tickets:
                        status_color = "#059669" if t.get("status") == "RESOLVED" else "#D97706"
                        with st.expander(f"Ticket #{t['id'][:6]} | Subject: {t.get('subject')} | Status: {t.get('status')}"):
                            st.write(f"**Category:** {t.get('category')}")
                            st.write(f"**Description:** {t.get('description')}")
                            st.markdown(f"**Current Status:** <span style='color:{status_color}; font-weight:bold;'>{t.get('status')}</span>", unsafe_allow_html=True)
                            
                            if t.get("admin_resolution"):
                                st.markdown(f"""
                                <div style="background:#F0FDF4; border-left:4px solid #16A34A; padding:10px; border-radius:4px; margin-top:8px;">
                                    <b>Admin Resolution Remarks:</b><br/>
                                    {t.get('admin_resolution')}
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.caption("Awaiting review from Admin desk.")
                else:
                    st.info("No helpdesk tickets raised by you yet.")

        # EMPLOYEE PANEL 6: MY PROFILE DETAILS
        elif selected_emp_panel == "My Profile Details":
            st.subheader("Employee Comprehensive Profile & Official Records")

            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            
            ent_name = next((e["name"] for e in ent_list if e["id"] == emp_user.get("entity_id")), "N/A")
            cli_name = next((c["name"] for c in cli_list if c["id"] == emp_user.get("client_id")), "N/A")

            st.markdown(f"""
            <div style="background:#F8FAFC; border:1px solid #CBD5E1; padding:20px; border-radius:8px;">
                <h4 style="margin-top:0; color:#1E3A8A;">{emp_user.get('full_name', 'Employee')} [{emp_user.get('employee_code', 'TEMP')}]</h4>
                <hr style="margin:10px 0; border:0; border-top:1px solid #E2E8F0;"/>
                <table style="width:100%; font-size:14px; line-height:1.8;">
                    <tr>
                        <td><b>Assigned Entity / Firm:</b> {ent_name}</td>
                        <td><b>Assigned Client Plant Site:</b> {cli_name}</td>
                    </tr>
                    <tr>
                        <td><b>Designation:</b> {emp_user.get('designation', 'Associate')}</td>
                        <td><b>Department / Zone:</b> {emp_user.get('department', 'Facility')} ({emp_user.get('zone', 'Zone-3')})</td>
                    </tr>
                    <tr>
                        <td><b>Category:</b> {emp_user.get('category', 'Semi-Skilled')}</td>
                        <td><b>Date of Joining:</b> {emp_user.get('joining_date', '2026-01-01')}</td>
                    </tr>
                    <tr>
                        <td><b>Date of Birth (DOB):</b> {emp_user.get('dob', '1940-05-15')}</td>
                        <td><b>Mobile Number:</b> {emp_user.get('phone_number', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td><b>Email ID:</b> {emp_user.get('email', 'N/A')}</td>
                        <td><b>Emergency Contact No:</b> {emp_user.get('emergency_contact', '9876543210')}</td>
                    </tr>
                    <tr>
                        <td><b>UAN Number:</b> {emp_user.get('uan_number', '102323165327')}</td>
                        <td><b>ESIC IP Number:</b> {emp_user.get('esic_number', '3318292114')}</td>
                    </tr>
                    <tr>
                        <td><b>PF Number:</b> {emp_user.get('pf_number', 'MH/PUNE/12345')}</td>
                        <td><b>Bank Account No:</b> {emp_user.get('bank_account_no', '34228310127')}</td>
                    </tr>
                </table>
            </div>
            """, unsafe_allow_html=True)
            st.info("Note: Profile information is managed securely by the Admin desk. To make updates, please submit a Helpdesk ticket.")

        # EMPLOYEE PANEL 7: OFFICIAL DOCUMENTS VAULT
        elif selected_emp_panel == "Official Documents Vault":
            st.subheader("Digital Documents Vault (Offer Letters & Certificates)")
            
            doc_col1, doc_col2 = st.columns(2)
            with doc_col1:
                st.markdown("##### Official Appointment / Offer Letter")
                st.caption("Issued upon successful onboarding and background verification.")
                offer_url = emp_user.get("offer_file")
                if offer_url:
                    st.markdown(f'<a href="{offer_url}" target="_blank" style="display:inline-block; background-color:#1E3A8A; color:white; padding:8px 14px; border-radius:4px; text-decoration:none; font-weight:bold; margin-top:10px;">Download Offer Letter (PDF)</a>', unsafe_allow_html=True)
                else:
                    st.warning("Offer letter ajun upload zalele nahiye. Admin kade samparka kara.")

            with doc_col2:
                st.markdown("##### ESIC Insurance & Medical Card")
                st.caption("Official social security and medical benefit document.")
                esic_url = emp_user.get("esic_file")
                if esic_url:
                    st.markdown(f'<a href="{esic_url}" target="_blank" style="display:inline-block; background-color:#059669; color:white; padding:8px 14px; border-radius:4px; text-decoration:none; font-weight:bold; margin-top:10px;">Download ESIC E-Card (PDF)</a>', unsafe_allow_html=True)
                else:
                    st.warning("ESIC document ajun upload zalele nahiye.")

        # EMPLOYEE PANEL 8: REQUEST PPE EQUIPMENT
        elif selected_emp_panel == "Request PPE Equipment":
            st.subheader("PPE Equipment & Uniform Request Desk")

            t_ppe_req, t_ppe_track = st.tabs(["New PPE Request", "Request Status Tracker"])

            cat_items = supabase.table("ppe_catalog").select("*").eq("entity_id", emp_user.get("entity_id")).eq("client_id", emp_user.get("client_id")).execute().data or []
            if not cat_items:
                cat_items = [
                    {"item_name": "Safety Shoes", "price": 500.0},
                    {"item_name": "Helmet", "price": 200.0},
                    {"item_name": "Safety Goggles", "price": 150.0},
                    {"item_name": "Uniform Shirt/Pant", "price": 750.0}
                ]

            cat_dict = {item["item_name"]: float(item["price"]) for item in cat_items}

            with t_ppe_req:
                with st.form("employee_ppe_request_form"):
                    sel_ppe_item = st.selectbox("Select PPE Item / Uniform *", list(cat_dict.keys()))
                    req_qty = st.number_input("Quantity *", min_value=1, value=1, step=1)
                    
                    unit_pr = cat_dict.get(sel_ppe_item, 0.0)
                    total_cost = unit_pr * req_qty
                    st.markdown(f"<b>Catalog Unit Price:</b> Rs. {unit_pr:,.2f} | <b>Total Estimated Cost:</b> <span style='color:#059669;'>Rs. {total_cost:,.2f}</span> (Deductible as per policy)", unsafe_allow_html=True)

                    if st.form_submit_button("Submit PPE Request", type="primary"):
                        supabase.table("ppe_records").insert({
                            "employee_id": emp_id,
                            "item_type": sel_ppe_item,
                            "quantity": req_qty,
                            "cost": total_cost,
                            "status": "PENDING_SUPERVISOR",
                            "assigned_date": str(date.today())
                        }).execute()
                        st.toast("✅ PPE Request Submitted!")
                        st.success("Your request has been sent for supervisor approval.")
                        pytime.sleep(1)
                        st.rerun()

            with t_ppe_track:
                st.write("##### PPE Request History & Tracker")
                my_ppes = supabase.table("ppe_records").select("*").eq("employee_id", emp_id).order("created_at", desc=True).execute().data or []
                if my_ppes:
                    ppe_rows = []
                    for p in my_ppes:
                        ppe_rows.append({
                            "Item": p.get("item_type"),
                            "Quantity": p.get("quantity"),
                            "Total Cost (Rs.)": f"Rs.{float(p.get('cost', 0)):,.2f}",
                            "Date": p.get("assigned_date"),
                            "Status": p.get("status")
                        })
                    st.dataframe(pd.DataFrame(ppe_rows), use_container_width=True)
                else:
                    st.info("No PPE requests found.")

        # EMPLOYEE PANEL 9: REQUEST SALARY ADVANCE
        elif selected_emp_panel == "Request Salary Advance":
            st.subheader("Salary Advance & Financial Assistance Request")

            t_adv_req, t_adv_track = st.tabs(["New Advance Request", "Advance Request Tracker"])

            with t_adv_req:
                with st.form("employee_salary_advance_form"):
                    adv_amt = st.number_input("Requested Amount (Rs.) *", min_value=500.0, max_value=10000.0, step=500.0, value=2000.0)
                    adv_reason = st.text_area("Reason for Advance * (e.g. Medical emergency / Family requirement)")

                    if st.form_submit_button("Submit Advance Request", type="primary"):
                        if not adv_reason.strip():
                            st.error("Please provide a valid reason for the advance!")
                        else:
                            supabase.table("advance_salaries").insert({
                                "employee_id": emp_id,
                                "amount": adv_amt,
                                "reason": adv_reason.strip(),
                                "status": "PENDING_SUPERVISOR"
                            }).execute()
                            st.toast("✅ Salary Advance Request Submitted!")
                            st.success("Your request has been forwarded to the supervisor.")
                            pytime.sleep(1)
                            st.rerun()

            with t_adv_track:
                st.write("##### Salary Advance History & Tracker")
                my_advs = supabase.table("advance_salaries").select("*").eq("employee_id", emp_id).order("created_at", desc=True).execute().data or []
                if my_advs:
                    adv_rows = []
                    for a in my_advs:
                        adv_rows.append({
                            "Requested Amount": f"Rs.{float(a.get('amount', 0)):,.2f}",
                            "Reason": a.get("reason"),
                            "Status": a.get("status")
                        })
                    st.dataframe(pd.DataFrame(adv_rows), use_container_width=True)
                else:
                    st.info("No salary advance requests found.")

        # EMPLOYEE PANEL 10: CHANGE PASSWORD
        elif selected_emp_panel == "Change Password":
            st.subheader("Security Settings & Password Management")

            with st.form("employee_change_password_form"):
                old_pwd_input = st.text_input("Current Password *", type="password")
                new_pwd_input = st.text_input("New Password *", type="password")
                conf_pwd_input = st.text_input("Confirm New Password *", type="password")

                if st.form_submit_button("Update Password", type="primary"):
                    db_pass = emp_user.get("password")
                    if old_pwd_input != db_pass:
                        st.error("Current password is incorrect!")
                    elif new_pwd_input != conf_pwd_input:
                        st.error("New password and confirmation do not match!")
                    elif len(new_pwd_input) < 4:
                        st.error("Password must be at least 4 characters long.")
                    else:
                        supabase.table("employees").update({"password": new_pwd_input}).eq("id", emp_id).execute()
                        st.toast("✅ Password Updated Successfully!")
                        st.success("Your portal password has been changed.")
                        pytime.sleep(1)
                        st.rerun()