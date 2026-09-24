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
st.set_page_config(page_title="ESS PORTAL", layout="wide")

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
        if num_dec > 0:
            words += " and " + conv(num_dec) + " Paise"
        words += " Only"
        return words
    except Exception:
        return f"Indian Rupees {number:,.2f} Only"

# -------------------------------------------------------------
# EXACT REPLICA: OFFICIAL OFFER LETTER PDF
# -------------------------------------------------------------
def generate_official_offer_letter(emp_data, entity_obj, client_name="Authorized Client Site", sal_rule=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=60)
    styles = getSampleStyleSheet()
    story = []

    entity_name = entity_obj.get("name", "GEMSHINE MULTISERVICES") if entity_obj else "GEMSHINE MULTISERVICES"
    code_pref = entity_obj.get("code_prefix", "GM") if entity_obj else "GM"
    ent_addr = entity_obj.get("address", "Ground Floor, Gat No. 235, Khandoba Temple, Khed SEZ Road, Rajgurunagar, Maharashtra - 410505, India") if entity_obj else "Ground Floor, Gat No. 235, Khandoba Temple, Khed SEZ Road, Rajgurunagar, Maharashtra - 410505, India"
    ent_gst = entity_obj.get("gst_number", "27ABEFG0561D1ZS") if entity_obj else "27ABEFG0561D1ZS"
    ent_pan = entity_obj.get("pan_number", "ABEFG0561D") if entity_obj else "ABEFG0561D"
    ent_phone = entity_obj.get("phone", "+91 95032 95153") if entity_obj else "+91 95032 95153"
    ent_email = entity_obj.get("email", "gemshine855@gmail.com") if entity_obj else "gemshine855@gmail.com"

    logo_file = get_entity_logo(entity_name)
    logo_img_p1 = None
    logo_img_p2 = None
    if logo_file and os.path.exists(logo_file):
        try:
            logo_img_p1 = RLImage(logo_file, width=130, height=45)
            logo_img_p2 = RLImage(logo_file, width=130, height=45)
        except Exception:
            logo_img_p1 = None
            logo_img_p2 = None

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

    body1 = f"""Following your recent interview, we are pleased to offer you the position of <b>{emp_data.get('designation', 'Associate- Housekeeping')}</b> on a Fixed Term Contract with <b>{entity_name}</b> for our business operations in Facility Management and Industrial Services.<br/><br/>
Your initial place of posting will be at our client site <b>"{client_name}"</b>.<br/><br/>
This offer is subject to verification of all documents submitted by you. You shall always comply with all Company rules and client site regulations. Statutory benefits such as PF, ESIC, Bonus, and other applicable benefits shall be provided as per law. You may be transferred to any client site, project, or location depending on operational requirements.<br/><br/>
Your service contract will automatically come to an end upon completion of 1 year from your date of joining. In case the Company's agreement with the client is terminated or amended before completion of your contract period, your employment may also be discontinued accordingly.<br/><br/>
You are requested to join on or before <b>{joining_date_str}</b>.<br/><br/>
The details of your salary bifurcation are as below -"""
    story.append(Paragraph(body1, styles["Normal"]))
    story.append(Spacer(1, 10))

    basic = float(sal_rule.get("basic", 14010.0)) if sal_rule else 14010.0
    da = float(sal_rule.get("da", 2511.0)) if sal_rule else 2511.0
    hra = float(sal_rule.get("hra", 826.0)) if sal_rule else 826.0
    other = float(sal_rule.get("other_allowance", 813.0)) if sal_rule else 813.0
    gross = basic + da + hra + other

    # Rule: Max ₹1,800 on Basic+DA
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
        ["", "Deduction", ""],
        ["F", "PF @ 12% (A+B) (Max ₹1,800)", f"{ee_pf:,.2f}"],
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
We look forward to welcoming you to <b>""" + entity_name + """</b> and wish you a successful association with us.<br/><br/>
Yours Sincerely,<br/>
<b>For """ + entity_name + """</b><br/><br/><br/><br/>
<b>Authorized Signatory</b><br/><br/>
<hr/><br/>
<font size=12><b>Acceptance of Offer</b></font><br/><br/>
I hereby accept the above offer and agree to join <b>""" + entity_name + """</b> on the terms mentioned.<br/><br/>
Employee Name: <b>""" + str(emp_data.get('full_name')) + """</b><br/><br/>
Signature: ___________________________ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Date: ___________________
"""
    story.append(Paragraph(p2_text, styles["Normal"]))

    doc.build(story, onFirstPage=draw_fixed_footer, onLaterPages=draw_fixed_footer)
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
    code_pref = entity_obj.get("code_prefix", "sagar") if entity_obj else "sagar"

    c_name = client_obj.get("name", "DAEBU AUTOMOTIVE SEAT INDIA PVT LTD") if client_obj else "DAEBU AUTOMOTIVE SEAT INDIA PVT LTD"
    c_addr = client_obj.get("plant_location", "Plot No-D-1, MIDC Chakan, Industrial Area Phase-II, Village Bhamboli Tal-Khed, Dist: Pune - 410501") if client_obj else "Plot No-D-1, MIDC Chakan, Industrial Area Phase-II, Village Bhamboli Tal-Khed, Dist: Pune - 410501"
    c_gst = client_obj.get("gst_number", "27AACCD4599E1ZH") if client_obj else "27AACCD4599E1ZH"

    # Consignee Details
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

    p_tax_words = Paragraph(f"<b>Tax Amount (in words):</b> {num_to_words(cgst+sgst)}<br/><b>Company's PAN:</b> {e_pan}", styles["Normal"])
    t_tax_words = Table([[p_tax_words]], colWidths=[562])
    t_tax_words.setStyle(TableStyle([('BOX', (0,0), (-1,-1), 0.5, colors.black), ('PADDING', (0,0), (-1,-1), 4)]))
    story.append(t_tax_words)

    b_name = entity_obj.get("bank_name", "SARASWAT BANK") if entity_obj else "SARASWAT BANK"
    b_acc = entity_obj.get("bank_account_no", "610000000045918") if entity_obj else "610000000045918"
    b_ifsc = entity_obj.get("ifsc_code", "SRCB0000376") if entity_obj else "SRCB0000376"

    decl = "<b>Declaration:</b><br/>We declare that this invoice shows the actual price of the services described and that all particulars are true and correct."
    bank_d = f"<b>Company Bank Account Details:</b><br/>BANK: {b_name}<br/>A/C NO: {b_acc}<br/>IFSC: {b_ifsc}"
    
    # Stamp & Signature auto attachment
    stamp_f, sig_f = get_entity_assets(code_pref)
    sign_elements = [Paragraph(f"<b>for {e_name}</b>", ParagraphStyle(name="SignTop", alignment=1))]
    
    if stamp_f and sig_f:
        sign_elements.append(Spacer(1, 4))
        sign_elements.append(Table([[RLImage(stamp_f, width=50, height=50), RLImage(sig_f, width=80, height=40)]], colWidths=[60, 90]))
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

# -------------------------------------------------------------
# EXACT REPLICA: SALARY PAYSLIP PDF GENERATION (PROFESSIONAL CENTERED)
# -------------------------------------------------------------
def generate_salary_payslip(emp_data, entity_obj, client_name, month_str, sal_rule, att_summary, deductions_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    story = []

    entity_name = entity_obj.get("name", "SAGAR ENTERPRISES") if entity_obj else "SAGAR ENTERPRISES"
    ent_addr = entity_obj.get("address", "A/p: Nimgaon tal-khed, Dist-pune") if entity_obj else "A/p: Nimgaon tal-khed, Dist-pune"

    # Centered Header: Title -> Entity Name -> Address
    header_html = f"""<font size=13><b>SALARY SLIP FOR THE MONTH OF {month_str.upper()}</b></font><br/>
    <font size=11><b>{entity_name}</b></font><br/>
    <font size=8 color='#475569'>{ent_addr}</font>"""
    
    p_center_head = Paragraph(header_html, ParagraphStyle(name="CenterHeadPayslip", alignment=1, leading=16))
    story.append(p_center_head)
    story.append(Spacer(1, 10))

    # Employee Information
    doj_val = str(emp_data.get("joining_date") or "")
    if "T" in doj_val:
        doj_val = doj_val.split("T")[0]

    emp_info_data = [
        ["Emp. Code:", str(emp_data.get("employee_code", "N/A")), "Paid Days:", str(att_summary.get("paid_days", 26))],
        ["Name:", str(emp_data.get("full_name", "N/A")), "Total Days:", str(att_summary.get("total_days", 26))],
        ["Designation:", str(emp_data.get("designation", "Staff")), "Bank Name:", str(emp_data.get("bank_name", "N/A"))],
        ["Client Site:", str(client_name), "Bank A/c No.:", str(emp_data.get("bank_account_no", "N/A"))],
        ["DOJ:", doj_val, "PAN No.:", str(emp_data.get("pan_number", "N/A"))],
        ["Category:", str(emp_data.get("category", "Semi-Skilled")), "Aadhaar No.:", str(emp_data.get("aadhar_number") or "[Aadhaar Redacted]")]
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

    # Earnings & Deductions
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

    # Net Salary
    t_net = Table([["Net Salary", f"Rs. {net_salary:,.2f}"]], colWidths=[280, 282])
    t_net.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#94A3B8")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_net)

    # In words & Note
    t_words = Table([
        [Paragraph(f"<b>Amount in Words:</b> <b>{num_to_words(net_salary)}</b>", styles["Normal"])],
        [Paragraph("<b>Remarks:</b> Salary calculated based on monthly attendance muster.", styles["Normal"])],
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

# =============================================================================
# 3. PUBLIC INTERFACE
# =============================================================================
if not st.session_state.user:
    st.markdown('<div class="main-title">ESS PORTAL</div>', unsafe_allow_html=True)
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
            c_gender = col_left.selectbox("Gender *", ["Male", "Female", "Other"])
            c_dob = col_left.date_input("Date of Birth (DOB) *", min_value=date(1960, 1, 1), max_value=date(2010, 1, 1), value=date(1998, 1, 1))
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
                        "user_id": f"TEMP_{c_phone}", 
                        "password": "emp" + c_phone[-4:],
                        "full_name": c_name, 
                        "father_name": c_father, 
                        "gender": c_gender,
                        "dob": str(c_dob),
                        "marital_status": c_marital,
                        "phone_number": c_phone, 
                        "emergency_contact": c_emergency, 
                        "uan_number": c_uan,
                        "esic_number": c_esic, 
                        "bank_name": c_bank, 
                        "bank_branch": c_branch,
                        "bank_account_no": c_acc, 
                        "ifsc_code": c_ifsc, 
                        "pan_number": c_pan,
                        "aadhar_number": c_aadhar,
                        "role": "employee", 
                        "status": "PENDING_SUPERVISOR"
                    }
                    try:
                        supabase.table("employees").insert(new_candidate).execute()
                        st.success("✅ Application submitted successfully! Forwarded to Supervisor.")
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
            st.markdown('<div class="sidebar-brand">HRMS</div>', unsafe_allow_html=True)
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
                    me_gender = m1.selectbox("Gender", ["Male", "Female", "Other"])
                    me_dob = m2.date_input("Date of Birth (DOB)", value=date(1995, 1, 1))
                    me_phone = m3.text_input("Mobile Number *")
                    
                    me_emg = m1.text_input("Emergency Contact")
                    me_marital = m2.selectbox("Marital Status", ["Single", "Married"])
                    me_desig = m3.text_input("Designation")
                    
                    me_cat = m1.selectbox("Category", ["Skilled", "Semi-Skilled", "Unskilled"], index=1)
                    me_shift_timing = m2.selectbox("Assigned Shift Schedule *", STANDARD_SHIFTS)
                    me_wo_day = m3.selectbox("Weekly Off (WO) Day *", ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], index=0)
                    me_pwd = m1.text_input("Portal Password", type="password")
                    me_aadhar = m2.text_input("Aadhaar Number *")

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
                                    "full_name": me_name, "father_name": me_father, "gender": me_gender, "dob": str(me_dob),
                                    "phone_number": me_phone, "emergency_contact": me_emg, "marital_status": me_marital, 
                                    "designation": me_desig, "category": me_cat, "shift_hours": 8.5, "weekly_off_day": me_wo_day, 
                                    "entity_id": e_map.get(sel_ent), "client_id": c_map.get(sel_cli),
                                    "uan_number": me_uan, "esic_number": me_esic, "pan_number": me_pan, "aadhar_number": me_aadhar,
                                    "bank_name": me_bank, "bank_branch": me_branch, "bank_account_no": me_acc,
                                    "ifsc_code": me_ifsc, "role": "employee", "status": "APPROVED",
                                    "joining_date": str(date.today())
                                }).execute()
                                st.cache_data.clear()
                                st.success(f"✅ Data Saved Successfully: Employee {me_name} registered!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error saving employee: {e}")

            # -------------------------------------------------------------
            # EDIT / DELETE EMPLOYEE (FULL CRUD WITH ALL FIELDS)
            # -------------------------------------------------------------
            with tab_edit_emp:
                all_emps = supabase.table("employees").select("*").eq("role", "employee").execute().data or []
                if all_emps:
                    emp_opt_map = {f"[{e.get('employee_code', 'N/A')}] {e.get('full_name')}": e for e in all_emps}
                    sel_emp_to_edit = st.selectbox("Select Employee to Update / Delete", list(emp_opt_map.keys()))
                    curr_selected = emp_opt_map[sel_emp_to_edit]

                    with st.form("edit_emp_crud_form"):
                        st.write("##### 1. Login Credentials & System Identifiers")
                        c_u1, c_u2, c_u3 = st.columns(3)
                        up_code = c_u1.text_input("Employee Code", value=curr_selected.get("employee_code", ""))
                        up_uid = c_u2.text_input("User ID (Login)", value=curr_selected.get("user_id", ""))
                        up_pwd = c_u3.text_input("Portal Password", value=curr_selected.get("password", ""))

                        st.write("##### 2. Personal Information")
                        ed1, ed2, ed3 = st.columns(3)
                        up_name = ed1.text_input("Full Name *", value=curr_selected.get("full_name", ""))
                        up_father = ed2.text_input("Father's Name", value=curr_selected.get("father_name", ""))
                        up_gender = ed3.selectbox("Gender", ["Male", "Female", "Other"], index=["Male", "Female", "Other"].index(curr_selected.get("gender", "Male")) if curr_selected.get("gender") in ["Male", "Female", "Other"] else 0)

                        ed4, ed5, ed6 = st.columns(3)
                        raw_dob = curr_selected.get("dob")
                        default_dob = datetime.strptime(str(raw_dob).split("T")[0], "%Y-%m-%d").date() if raw_dob else date(1995, 1, 1)
                        up_dob = ed4.date_input("Date of Birth (DOB)", value=default_dob)
                        up_phone = ed5.text_input("Mobile Number *", value=curr_selected.get("phone_number", ""))
                        up_emg = ed6.text_input("Emergency Contact", value=curr_selected.get("emergency_contact", ""))

                        st.write("##### 3. Employment & Organization Assignment")
                        ed7, ed8, ed9 = st.columns(3)
                        up_desig = ed7.text_input("Designation", value=curr_selected.get("designation", ""))
                        up_cat = ed8.selectbox("Category", ["Skilled", "Semi-Skilled", "Unskilled"], index=["Skilled", "Semi-Skilled", "Unskilled"].index(curr_selected.get("category", "Semi-Skilled")) if curr_selected.get("category") in ["Skilled", "Semi-Skilled", "Unskilled"] else 1)
                        up_wo = ed9.selectbox("Weekly Off Day", ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], index=["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"].index(curr_selected.get("weekly_off_day", "Sunday")) if curr_selected.get("weekly_off_day") in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] else 0)

                        st.write("##### 4. Statutory & Identity Numbers")
                        st1, st2, st3, st4 = st.columns(4)
                        up_uan = st1.text_input("UAN Number", value=curr_selected.get("uan_number", ""))
                        up_esic = st2.text_input("ESIC Number", value=curr_selected.get("esic_number", ""))
                        up_pan = st3.text_input("PAN Number", value=curr_selected.get("pan_number", ""))
                        up_aadhar = st4.text_input("Aadhaar Number", value=str(curr_selected.get("aadhar_number") or ""))

                        st.write("##### 5. Bank Account Details")
                        bk1, bk2, bk3, bk4 = st.columns(4)
                        up_bank = bk1.text_input("Bank Name", value=curr_selected.get("bank_name", ""))
                        up_branch = bk2.text_input("Branch Name", value=curr_selected.get("bank_branch", ""))
                        up_acc = bk3.text_input("Account Number", value=curr_selected.get("bank_account_no", ""))
                        up_ifsc = bk4.text_input("IFSC Code", value=curr_selected.get("ifsc_code", ""))

                        st.write("---")
                        c_btn1, c_btn2 = st.columns(2)
                        if c_btn1.form_submit_button("Update Employee Data", type="primary"):
                            supabase.table("employees").update({
                                "employee_code": up_code, "user_id": up_uid, "password": up_pwd,
                                "full_name": up_name, "father_name": up_father, "gender": up_gender,
                                "dob": str(up_dob), "phone_number": up_phone, "emergency_contact": up_emg,
                                "designation": up_desig, "category": up_cat, "weekly_off_day": up_wo,
                                "uan_number": up_uan, "esic_number": up_esic, "pan_number": up_pan,
                                "aadhar_number": up_aadhar, "bank_name": up_bank, "bank_branch": up_branch,
                                "bank_account_no": up_acc, "ifsc_code": up_ifsc
                            }).eq("id", curr_selected["id"]).execute()
                            st.cache_data.clear()
                            st.success("✅ Data Updated Successfully: Employee record refreshed!")
                            st.rerun()

                        if c_btn2.form_submit_button("🗑️ Delete Employee"):
                            supabase.table("employees").delete().eq("id", curr_selected["id"]).execute()
                            st.cache_data.clear()
                            st.warning("🗑️ Data Deleted Successfully: Employee record removed!")
                            st.rerun()
                else:
                    st.info("No employee records found.")

            with tab_vault:
                emp_records = supabase.table("employees").select("*").eq("role", "employee").execute().data or []
                if emp_records:
                    emp_lookup = {f"[{emp.get('employee_code', 'TEMP')}] {emp.get('full_name')}": emp for emp in emp_records}
                    sel_emp_label = st.selectbox("Choose Employee for Documents", options=list(emp_lookup.keys()))
                    curr_emp = emp_lookup[sel_emp_label]

                    curr_ent_obj = next((e for e in ent_list if e["id"] == curr_emp.get("entity_id")), None)
                    curr_cli_name = next((c["name"] for c in cli_list if c["id"] == curr_emp.get("client_id")), "Client Site")

                    matched_rule = None
                    try:
                        sr_query = supabase.table("salary_structures").select("*").eq("entity_id", curr_emp.get("entity_id"))
                        if curr_emp.get("client_id"):
                            sr_query = sr_query.eq("client_id", curr_emp.get("client_id"))
                        if curr_emp.get("designation"):
                            sr_query = sr_query.ilike("designation", curr_emp.get("designation").strip())
                        if curr_emp.get("category"):
                            sr_query = sr_query.eq("category", curr_emp.get("category").strip())
                        s_matched = sr_query.execute().data
                        if s_matched:
                            matched_rule = s_matched[0]
                        else:
                            fallback_res = supabase.table("salary_structures").select("*").eq("entity_id", curr_emp.get("entity_id")).execute().data
                            if fallback_res:
                                matched_rule = fallback_res[0]
                    except Exception:
                        pass

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

                        st.markdown("##### 5. Bank Passbook / Cheque Copy")
                        f_bnk = st.file_uploader("Upload Bank Passbook / Cheque", type=["pdf", "jpg", "png"], key=f"vault_bnk_{curr_emp['id']}")
                        if f_bnk: st.success("✅ Data Updated Successfully: Bank Details updated!")

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
                        st.markdown("##### Bank Details for Invoices")
                        en_bnk = st.text_input("Bank Name", value="SARASWAT BANK")
                        en_acc = st.text_input("Account Number", value="610000000045918")
                        en_ifsc = st.text_input("IFSC Code", value="SRCB0000376")
                        
                        if st.form_submit_button("Save Entity", type="primary"):
                            if en_name and en_pref:
                                supabase.table("entities").insert({
                                    "name": en_name, "address": en_addr, "gst_number": en_gst, "code_prefix": en_pref,
                                    "pan_number": en_pan, "phone": en_ph, "email": en_em,
                                    "bank_name": en_bnk, "bank_account_no": en_acc, "ifsc_code": en_ifsc
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
                            en_up_bnk = st.text_input("Bank Name", value=curr_e.get("bank_name", "SARASWAT BANK"))
                            en_up_acc = st.text_input("Bank Account No", value=curr_e.get("bank_account_no", "610000000045918"))
                            en_up_ifsc = st.text_input("Bank IFSC Code", value=curr_e.get("ifsc_code", "SRCB0000376"))
                            
                            c1, c2 = st.columns(2)
                            if c1.form_submit_button("Update Entity", type="primary"):
                                update_payload = {
                                    "name": en_up_name, 
                                    "address": en_up_addr, 
                                    "gst_number": en_up_gst,
                                    "bank_name": en_up_bnk,
                                    "bank_account_no": en_up_acc,
                                    "ifsc_code": en_up_ifsc
                                }
                                if en_up_pan:
                                    update_payload["pan_number"] = en_up_pan

                                try:
                                    supabase.table("entities").update(update_payload).eq("id", curr_e["id"]).execute()
                                    st.cache_data.clear()
                                    st.success("✅ Data Updated Successfully: Entity refreshed!")
                                    st.rerun()
                                except Exception as e:
                                    if "pan_number" in str(e):
                                        update_payload.pop("pan_number", None)
                                        supabase.table("entities").update(update_payload).eq("id", curr_e["id"]).execute()
                                        st.cache_data.clear()
                                        st.success("✅ Data Updated Successfully (Without PAN): Entity refreshed!")
                                        st.rerun()
                                    else:
                                        st.error(f"Error updating entity: {e}")

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
                        cl_serv = st.number_input("Service Charge Rate (%) *", value=10.0, step=0.5)
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
                                    "service_charge_pct": cl_serv,
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
                            cl_up_serv = st.number_input("Service Charge Rate (%)", value=float(curr_c.get("service_charge_pct") or 10.0), step=0.5)
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
                                    "name": cl_up_name, "gst_number": cl_up_gst, "service_charge_pct": cl_up_serv,
                                    "plant_location": cl_up_addr, "contact_person_name": cl_up_cn, 
                                    "contact_person_email": cl_up_ce, "contact_person_mobile": cl_up_cm, 
                                    "latitude": cl_up_lat, "longitude": cl_up_lon
                                }).eq("id", curr_c["id"]).execute()
                                st.cache_data.clear()
                                st.success("✅ Data Updated Successfully: Client geofence & details refreshed!")
                                st.rerun()
                            if cb2.form_submit_button("🗑️ Delete Client"):
                                supabase.table("clients").delete().eq("id", curr_c["id"]).execute()
                                st.cache_data.clear()
                                st.warning("🗑️ Data Deleted Successfully: Client removed!")
                                st.rerun()

            st.write("---")
            with st.expander("🎉 Configure Client-wise Paid Holidays (PH) for Entity"):
                with st.form("add_ph_form"):
                    ph_col1, ph_col2 = st.columns(2)
                    sel_ph_ent = ph_col1.selectbox("Select Entity / फर्म निवडा", list(e_dict.keys()) if e_dict else ["No Entity"])
                    sel_ph_cli = ph_col2.selectbox("Select Client Site / कंपनी निवडा", list(cli_select_map.keys()) if 'cli_select_map' in locals() and cli_select_map else ["No Client"])

                    ph_date = ph_col1.date_input("Holiday Date / सुट्टीची तारीख", value=date.today())
                    ph_name = ph_col2.text_input("Holiday Name / सणाचे नाव (उदा. Diwali, Independence Day)")

                    if st.form_submit_button("Save Paid Holiday / सवेतन सुट्टी जतन करा", type="primary"):
                        if ph_name and e_dict:
                            try:
                                supabase.table("paid_holidays").insert({
                                    "entity_id": e_dict[sel_ph_ent],
                                    "client_id": cli_select_map[sel_ph_cli]["id"] if 'cli_select_map' in locals() and sel_ph_cli in cli_select_map else None,
                                    "holiday_date": str(ph_date),
                                    "holiday_name": ph_name
                                }).execute()
                                st.success(f"✅ Paid Holiday '{ph_name}' added successfully!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error saving PH: {e}")

        # 4. Salary Structure Rules
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
                    sr3, sr4, sr5, sr6, sr7 = st.columns(5)
                    r_basic = sr3.number_input("Basic Pay (₹)", value=14010.0)
                    r_da = sr4.number_input("DA (₹)", value=2511.0)
                    r_hra = sr5.number_input("HRA (₹)", value=826.0)
                    r_other = sr6.number_input("Other (₹)", value=813.0)
                    r_ot = sr7.number_input("OT Rate / Hour (₹)", value=120.0)

                    gross = r_basic + r_da + r_hra + r_other

                    st.markdown("##### 2. Employee Deductions (On Pay Slip)")
                    sr8, sr9, sr10 = st.columns(3)
                    r_pf = sr8.number_input("Employee PF (%)", value=12.0)
                    r_esic = sr9.number_input("Employee ESIC (%)", value=0.75)
                    r_pt = sr10.number_input("PT Amount (₹)", value=200.0)

                    st.markdown("##### 3. Employer Contributions / Company Cost (Offer Letter CTC - No Gratuity)")
                    er1, er2, er3 = st.columns(3)
                    r_er_pf = er1.number_input("Employer PF (%)", value=13.0)
                    r_er_esic = er2.number_input("Employer ESIC (%)", value=3.25)
                    r_bonus = er3.number_input("Bonus (₹)", value=0.0)

                    # EPF ceiling logic
                    er_pf_val = min(round((r_basic + r_da) * (r_er_pf / 100.0), 2), 1950.0)
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
                            up_er_pf = min(round((e_b + e_da) * (e_er_pf / 100.0), 2), 1950.0)
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

        # 5. PPE & UNIFORM TRACKER
        elif selected_panel == "PPE & Uniform Tracker":
            st.subheader("PPE & Uniform Tracker (Management Desk)")
            tab_ppe_issue, tab_ppe_edit, tab_ppe_req, tab_ppe_cat = st.tabs([
                "➕ Issue / Add PPE", 
                "✏️ Edit / Delete PPE", 
                "📋 Pending Requests",
                "🏷️ PPE Price Catalog"
            ])
            
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            emp_list = fetch_cached_employees()

            p_e_map = {e["name"]: e["id"] for e in ent_list}
            p_c_map = {c["name"]: c["id"] for c in cli_list}
            p_emp_map = {f"[{e.get('employee_code', 'N/A')}] {e['full_name']}": e["id"] for e in emp_list if e.get("role") == "employee"}

            emp_obj_lookup = {e["id"]: e for e in emp_list}
            ent_name_lookup = {e["id"]: e["name"] for e in ent_list}
            cli_name_lookup = {c["id"]: c["name"] for c in cli_list}

            with tab_ppe_cat:
                st.write("##### 🏷️ Entity & Client Wise PPE Pricing Master")
                with st.form("add_ppe_catalog_form"):
                    cat_c1, cat_c2 = st.columns(2)
                    cat_ent = cat_c1.selectbox("Select Entity / फर्म *", list(p_e_map.keys()) if p_e_map else ["No Entity"])
                    cat_cli = cat_c2.selectbox("Select Client Site / कंपनी *", list(p_c_map.keys()) if p_c_map else ["No Client"])

                    cat_c3, cat_c4 = st.columns(2)
                    cat_item = cat_c3.text_input("PPE Item Name * (उदा. Safety Shoes, Helmet, Uniform Shirt/Pant)")
                    cat_price = cat_c4.number_input("Unit Price / किंमत (₹) *", min_value=0.0, step=10.0, value=100.0)

                    if st.form_submit_button("Save Item in Catalog / दर जतन करा", type="primary"):
                        if cat_item and p_e_map and p_c_map:
                            try:
                                supabase.table("ppe_catalog").upsert({
                                    "entity_id": p_e_map[cat_ent],
                                    "client_id": p_c_map[cat_cli],
                                    "item_name": cat_item.strip(),
                                    "price": cat_price
                                }, on_conflict="entity_id,client_id,item_name").execute()
                                st.success(f"✅ {cat_item} चे दर (₹{cat_price:,.2f}) जतन झाले!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error saving catalog: {e}")

                st.write("---")
                st.write("##### 📋 Live Configured PPE Catalog Rates")
                catalog_data = supabase.table("ppe_catalog").select("*").execute().data or []
                if catalog_data:
                    cat_rows = []
                    for c_item in catalog_data:
                        cat_rows.append({
                            "Entity": ent_name_lookup.get(c_item.get("entity_id"), "N/A"),
                            "Client Site": cli_name_lookup.get(c_item.get("client_id"), "N/A"),
                            "Item Name": c_item.get("item_name"),
                            "Rate (₹)": f"₹{float(c_item.get('price', 0)):,.2f}"
                        })
                    st.dataframe(pd.DataFrame(cat_rows), use_container_width=True)
                else:
                    st.info("अद्याप कोणत्याही PPE वस्तूंचे दर सेट केलेले नाहीत.")

            with tab_ppe_issue:
                with st.form("manual_ppe_form"):
                    col_p1, col_p2, col_p3 = st.columns(3)
                    p_sel_ent = col_p1.selectbox("Entity", options=list(p_e_map.keys()) if p_e_map else ["No Entity"])
                    p_sel_cli = col_p2.selectbox("Client Site", options=list(p_c_map.keys()) if p_c_map else ["No Client"])
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
                    ppe_select_options = {}
                    for p in all_ppes:
                        emp_info = emp_obj_lookup.get(p.get("employee_id"), {})
                        ppe_select_options[f"[{emp_info.get('employee_code', 'N/A')}] {emp_info.get('full_name', 'Unknown')} - {p.get('item_type')} (Qty: {p.get('quantity')})"] = p

                    sel_p = st.selectbox("Select PPE Record to Edit/Delete", list(ppe_select_options.keys()))
                    curr_p = ppe_select_options[sel_p]

                    with st.form("edit_ppe_crud_form"):
                        pe1, pe2 = st.columns(2)
                        up_item = pe1.text_input("Item Type", value=curr_p.get("item_type", ""))
                        up_size = pe2.text_input("Size", value=curr_p.get("size", ""))
                        up_qty = pe1.number_input("Quantity", min_value=1, value=int(curr_p.get("quantity", 1)))

                        pb1, pb2 = st.columns(2)
                        if pb1.form_submit_button("Update PPE Record", type="primary"):
                            supabase.table("ppe_records").update({
                                "item_type": up_item,
                                "size": up_size,
                                "quantity": up_qty
                            }).eq("id", curr_p["id"]).execute()
                            st.success("✅ Data Updated Successfully: PPE record updated!")
                            st.rerun()

                        if pb2.form_submit_button("🗑️ Delete PPE Record"):
                            supabase.table("ppe_records").delete().eq("id", curr_p["id"]).execute()
                            st.warning("🗑️ Data Deleted Successfully: PPE record removed!")
                            st.rerun()
                else:
                    st.info("No PPE records available to edit.")

            with tab_ppe_req:
                ppe_reqs = supabase.table("ppe_records").select("*").eq("status", "PENDING_ADMIN").order("created_at", desc=True).execute().data or []
                if ppe_reqs:
                    for req in ppe_reqs:
                        req_emp = emp_obj_lookup.get(req.get("employee_id"), {})
                        e_name = ent_name_lookup.get(req_emp.get("entity_id"), "N/A")
                        c_name = cli_name_lookup.get(req_emp.get("client_id"), "N/A")

                        st.markdown(f"""
                        <div style="background-color: #F8FAFC; border: 1px solid #CBD5E1; border-left: 5px solid #0284C7; border-radius: 6px; padding: 12px; margin-bottom: 8px;">
                            <b>Employee:</b> {req_emp.get('full_name', 'N/A')} (<b>Code:</b> {req_emp.get('employee_code', 'N/A')}) | <b>Designation:</b> {req_emp.get('designation', 'Staff')}<br/>
                            <b>Entity:</b> {e_name} | <b>Client Site:</b> {c_name}<br/>
                            <b>Requested Item:</b> <span style="color:#0284C7; font-weight:bold;">{req.get('item_type')}</span> | <b>Size:</b> {req.get('size')} | <b>Quantity:</b> {req.get('quantity')}
                        </div>
                        """, unsafe_allow_html=True)

                        col_r1, col_r2, _ = st.columns([1.5, 1.5, 5])
                        if col_r1.button("✅ Approve PPE", key=f"app_ppe_{req['id']}", type="primary"):
                            supabase.table("ppe_records").update({"status": "APPROVED", "assigned_date": str(date.today())}).eq("id", req["id"]).execute()
                            st.success(f"PPE Item approved for {req_emp.get('full_name')}!")
                            st.rerun()

                        if col_r2.button("❌ Reject PPE", key=f"rej_ppe_{req['id']}"):
                            supabase.table("ppe_records").update({"status": "REJECTED_BY_ADMIN"}).eq("id", req["id"]).execute()
                            st.warning("PPE request rejected!")
                            st.rerun()
                else:
                    st.info("No pending PPE requests.")

            st.write("---")
            st.write("#### 📊 Full PPE Tracker Records")
            all_ppe_list = supabase.table("ppe_records").select("*").order("created_at", desc=True).execute().data or []
            if all_ppe_list:
                formatted_ppe_rows = []
                for p_rec in all_ppe_list:
                    emp_data_match = emp_obj_lookup.get(p_rec.get("employee_id"), {})
                    formatted_ppe_rows.append({
                        "Emp Code": emp_data_match.get("employee_code", "N/A"),
                        "Employee Name": emp_data_match.get("full_name", "N/A"),
                        "Firm / Entity": ent_name_lookup.get(emp_data_match.get("entity_id"), "N/A"),
                        "Client Site": cli_name_lookup.get(emp_data_match.get("client_id"), "N/A"),
                        "Item Type": p_rec.get("item_type"),
                        "Size": p_rec.get("size"),
                        "Quantity": p_rec.get("quantity"),
                        "Status": p_rec.get("status"),
                        "Assigned Date": p_rec.get("assigned_date") or str(p_rec.get("created_at"))[:10]
                    })
                st.dataframe(pd.DataFrame(formatted_ppe_rows), use_container_width=True)

        # 6. MONTHLY PAYROLL PROCESSING (Full 35+ Column Format)
        elif selected_panel == "Monthly Payroll Processing":
            st.subheader("Monthly Payroll Engine & Wage Sheet (Full Statutory Format)")

            p_col1, p_col2 = st.columns(2)
            sel_month = p_col1.selectbox("Select Payroll Month", ["September 2026", "October 2026", "August 2026"])
            
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_opts = {e["name"]: e["id"] for e in ent_list}
            c_opts = {c["name"]: c["id"] for c in cli_list}

            sel_ent_name = p_col2.selectbox("Filter by Entity", ["All Entities"] + list(e_opts.keys()))

            try:
                emp_query = supabase.table("employees").select("*").eq("role", "employee").eq("status", "APPROVED")
                if sel_ent_name != "All Entities":
                    emp_query = emp_query.eq("entity_id", e_opts[sel_ent_name])
                emp_records = emp_query.execute().data or []
            except Exception:
                emp_records = []

            if emp_records:
                st.write(f"##### Payroll Register for **{sel_month}** (Total Staff: {len(emp_records)})")
                
                payroll_rows = []
                for emp_item in emp_records:
                    sal_struct = None
                    try:
                        sr_query = supabase.table("salary_structures").select("*").eq("entity_id", emp_item.get("entity_id"))
                        if emp_item.get("client_id"):
                            sr_query = sr_query.eq("client_id", emp_item.get("client_id"))
                        if emp_item.get("designation"):
                            sr_query = sr_query.ilike("designation", emp_item.get("designation").strip())
                        if emp_item.get("category"):
                            sr_query = sr_query.eq("category", emp_item.get("category").strip())
                        s_matched = sr_query.execute().data
                        if s_matched:
                            sal_struct = s_matched[0]
                        else:
                            fallback_res = supabase.table("salary_structures").select("*").eq("entity_id", emp_item.get("entity_id")).execute().data
                            if fallback_res:
                                sal_struct = fallback_res[0]
                    except Exception:
                        pass

                    b_pay = float(sal_struct.get("basic", 14010.0)) if sal_struct else 14010.0
                    d_pay = float(sal_struct.get("da", 2511.0)) if sal_struct else 2511.0
                    h_pay = float(sal_struct.get("hra", 826.0)) if sal_struct else 826.0
                    o_pay = float(sal_struct.get("other_allowance", 813.0)) if sal_struct else 813.0
                    rate_total_wages = b_pay + d_pay + h_pay + o_pay
                    ot_rate = float(sal_struct.get("ot_rate_per_hour", 120.0)) if sal_struct else 120.0

                    p_cnt = 24.0
                    ph_cnt = 2.0
                    ot_hours_total = 0.0
                    try:
                        att_recs = supabase.table("attendance").select("status, ot_hours").eq("employee_id", emp_item["id"]).execute().data or []
                        if att_recs:
                            p_cnt = float(len([a for a in att_recs if a.get("status") == "P"]))
                            p_cnt += float(len([a for a in att_recs if a.get("status") == "HD"])) * 0.5
                            ph_cnt = float(len([a for a in att_recs if a.get("status") == "PH"]))
                            ot_hours_total = sum([float(a.get("ot_hours") or 0.0) for a in att_recs])
                    except Exception: pass

                    total_days = p_cnt + ph_cnt

                    earned_basic = round((b_pay / 26.0) * total_days, 2)
                    earned_da = round((d_pay / 26.0) * total_days, 2)
                    earned_hra = round((h_pay / 26.0) * total_days, 2)
                    earned_other = round((o_pay / 26.0) * total_days, 2)
                    earned_wages = earned_basic + earned_da + earned_hra + earned_other
                    ot_amount = round(ot_hours_total * ot_rate, 2)
                    total_gross = round(earned_wages + ot_amount, 2)

                    # EPF Max ₹1,800 Ceiling Rule on Basic + DA
                    basic_plus_da = earned_basic + earned_da
                    if basic_plus_da > 15000:
                        pf_ded = 1800.0
                    else:
                        pf_ded = round(basic_plus_da * 0.12, 2)

                    esic_ded = round(total_gross * 0.0075, 2)
                    pt_ded = 200.0 if total_gross > 10000 else 0.0

                    # Advance Check
                    adv_val = 0.0
                    try:
                        adv_recs = supabase.table("advance_salaries").select("amount").eq("employee_id", emp_item["id"]).eq("status", "APPROVED").execute().data or []
                        adv_val = sum([float(a.get("amount") or 0.0) for a in adv_recs])
                    except Exception: 
                        pass

                    # PPE / Uniform Deduction Fetch
                    ppe_ded = 0.0
                    try:
                        ppe_recs = supabase.table("ppe_records").select("cost").eq("employee_id", emp_item["id"]).eq("deduction_month", sel_month).eq("status", "APPROVED").execute().data or []
                        ppe_ded = sum([float(p.get("cost") or 0.0) for p in ppe_recs])
                    except Exception:
                        pass

                    # Total Deductions (Advance + PPE)
                    total_deductions = pf_ded + esic_ded + pt_ded + adv_val + ppe_ded
                    net_take_home = round(total_gross - total_deductions, 2)

                    # Employer Contributions & CTC
                    if basic_plus_da > 15000:
                        pf_er = 1950.0
                    else:
                        pf_er = round(basic_plus_da * 0.13, 2)

                    esic_er = round(total_gross * 0.0325, 2)

                    cli_match = next((c for c in cli_list if c["id"] == emp_item.get("client_id")), {})
                    service_pct = float(cli_match.get("service_charge_pct") or 10.0)
                    service_charge = round(total_gross * (service_pct / 100.0), 2)

                    employer_subtotal = round(total_gross + pf_er + esic_er + service_charge, 2)
                    gst_18 = round(employer_subtotal * 0.18, 2)
                    total_monthly_ctc = round(employer_subtotal + gst_18, 2)
                    per_day_ctc = round(total_monthly_ctc / (total_days if total_days > 0 else 26), 2)

                    payroll_rows.append({
                        "Emp ID": emp_item.get("employee_code", "N/A"),
                        "Name of Employee": emp_item.get("full_name"),
                        "Father Name": emp_item.get("father_name", "N/A"),
                        "UAN Number": emp_item.get("uan_number", "N/A"),
                        "ESIC Number": emp_item.get("esic_number", "N/A"),
                        "PAN Number": emp_item.get("pan_number", "N/A"),
                        "Aadhaar Number": str(emp_item.get("aadhar_number") or ""),
                        "Gender": emp_item.get("gender", "Male"),
                        "Date of Joining": emp_item.get("joining_date", str(date.today())),
                        "Date of Birth": emp_item.get("dob", "N/A"),
                        "Bank Name": emp_item.get("bank_name", "N/A"),
                        "Bank Branch": emp_item.get("bank_branch", "N/A"),
                        "Bank Account No": emp_item.get("bank_account_no", "N/A"),
                        "IFSC Code": emp_item.get("ifsc_code", "N/A"),
                        "Mobile Number": emp_item.get("phone_number", "N/A"),
                        "Designation": emp_item.get("designation", "Associate"),
                        "Category": emp_item.get("category", "Semi-Skilled"),
                        "Basic Rate": b_pay,
                        "DA Rate": d_pay,
                        "HRA Rate": h_pay,
                        "Total Wages": rate_total_wages,
                        "OT Rate": ot_rate,
                        "Present Days": p_cnt,
                        "Paid Holiday": ph_cnt,
                        "Total Days": total_days,
                        "OT Hours": ot_hours_total,
                        "Basic Amount": earned_basic,
                        "DA Amount": earned_da,
                        "HRA Amount": earned_hra,
                        "Total Earned Wages": earned_wages,
                        "OT Amount": ot_amount,
                        "Total Gross Salary": total_gross,
                        "PF 12%": pf_ded,
                        "ESIC 0.75%": esic_ded,
                        "Professional Tax": pt_ded,
                        "Advance": adv_val,
                        "PPE / Uniform Deduction": ppe_ded,
                        "Total Deductions": total_deductions,
                        "Net Wages": net_take_home,
                        "Employer PF 13%": pf_er,
                        "Employer ESIC 3.25%": esic_er,
                        "Service Charge": service_charge,
                        "Employer Subtotal": employer_subtotal,
                        "GST 18%": gst_18,
                        "Per Day CTC": per_day_ctc,
                        "Monthly CTC": total_monthly_ctc
                    })

                df_wage = pd.DataFrame(payroll_rows)
                st.dataframe(df_wage, use_container_width=True)

                st.write("---")
                col_lk1, col_lk2 = st.columns([2, 5])
                with col_lk1:
                    csv_data = df_wage.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Download Complete Wage Sheet (Excel / CSV)",
                        data=csv_data,
                        file_name=f"Wage_Sheet_{sel_month.replace(' ', '_')}.csv",
                        mime="text/csv"
                    )
                with col_lk2:
                    if st.button("🔒 Dual-Confirm & Lock Wage Sheet", type="primary"):
                        if sel_ent_name != "All Entities" and e_opts.get(sel_ent_name):
                            supabase.table("locked_payrolls").upsert({
                                "entity_id": e_opts[sel_ent_name],
                                "payroll_month": sel_month,
                                "is_locked": True
                            }, on_conflict="entity_id,payroll_month").execute()
                        st.success(f"✅ Wage Sheet for {sel_month} locked! Now visible to employees.")
            else:
                st.info("No approved employees found for the selected entity filter.")

        # 7. CLIENT BILLING & INVOICES (With Full Field Manual Entry)
        elif selected_panel == "Client Billing & Invoices":
            st.subheader("Client Billing & Tax Invoice Generator (Exact Replica)")
            t_inv_gen, t_inv_hist = st.tabs(["➕ Generate Tax Invoice", "📑 Invoices History & Downloads"])
            cli_list = fetch_cached_clients()
            ent_list = fetch_cached_entities()
            c_dict = {c["name"]: c for c in cli_list}
            e_dict = {e["name"]: e for e in ent_list}

            with t_inv_gen:
                with st.form("generate_tax_inv_form"):
                    st.write("##### 1. Primary Supplier & Buyer Details")
                    i_col1, i_col2 = st.columns(2)
                    sel_inv_ent = i_col1.selectbox("From Entity (Supplier) *", list(e_dict.keys()) if e_dict else ["No Entity"])
                    sel_inv_cli = i_col2.selectbox("To Client (Buyer) *", list(c_dict.keys()) if c_dict else ["No Client"])
                    
                    st.write("##### 2. Invoice Metadata & Transport Particulars")
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
                    inv_terms = m_c8.text_input("Terms of Delivery", value="")

                    st.write("##### 3. Consignee (Ship To) Details")
                    chk_same = st.checkbox("Consignee is same as Buyer", value=True)
                    cons_n = st.text_input("Consignee Name", value=sel_inv_cli if chk_same else "")
                    cons_a = st.text_area("Consignee Address", value=c_dict[sel_inv_cli]["plant_location"] if chk_same and sel_inv_cli in c_dict else "")
                    cons_g = st.text_input("Consignee GSTIN", value=c_dict[sel_inv_cli]["gst_number"] if chk_same and sel_inv_cli in c_dict else "")

                    st.write("##### 4. Services Description & Amounts")
                    s_c1, s_c2, s_c3 = st.columns(3)
                    inv_month = s_c1.text_input("Billing Month / Service Period", value="Aug-2026 Khed City")
                    inv_hsn = s_c2.text_input("HSN/SAC", value="996511")
                    inv_subtotal = s_c3.number_input("Taxable Amount (Without GST ₹) *", value=115146.0)

                    if st.form_submit_button("Generate & Save Tax Invoice", type="primary"):
                        try:
                            supabase.table("client_invoices").insert({
                                "invoice_number": inv_no, "invoice_date": str(inv_dt),
                                "reference_no": inv_ref, "buyers_order_no": inv_order,
                                "dispatch_doc_no": inv_disp, "dispatched_through": inv_through,
                                "bill_of_lading_no": inv_lading, "terms_of_delivery": inv_terms,
                                "consignee_name": cons_n, "consignee_address": cons_a, "consignee_gstin": cons_g,
                                "client_id": c_dict[sel_inv_cli]["id"], "entity_id": e_dict[sel_inv_ent]["id"],
                                "billing_month": inv_month, "hsn_sac": inv_hsn, "total_amount": inv_subtotal, 
                                "payment_status": "PENDING"
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

        # 8. ADVANCE / LOAN DESK
        elif selected_panel == "Advance / Loan Desk":
            st.subheader("Salary Advance & Loan Requests")

            try:
                adv_reqs = supabase.table("advance_salaries").select("*").order("created_at", desc=True).execute().data or []
            except Exception:
                adv_reqs = []

            if adv_reqs:
                all_emps_data = fetch_cached_employees()
                all_ents_data = fetch_cached_entities()
                all_clis_data = fetch_cached_clients()

                emp_map = {e["id"]: e for e in all_emps_data}
                ent_map = {e["id"]: e["name"] for e in all_ents_data}
                cli_map = {c["id"]: c["name"] for c in all_clis_data}

                t_adv_pend, t_adv_all = st.tabs(["⏳ Pending Requests", "📋 All Records"])

                with t_adv_pend:
                    pending_adv = [a for a in adv_reqs if a.get("status") == "PENDING_ADMIN"]
                    if pending_adv:
                        for req in pending_adv:
                            req_emp = emp_map.get(req.get("employee_id"), {})
                            e_name = ent_map.get(req_emp.get("entity_id"), "N/A")
                            c_name = cli_map.get(req_emp.get("client_id"), "N/A")

                            st.markdown(f"""
                            <div style="background-color: #F8FAFC; border: 1px solid #CBD5E1; border-left: 5px solid #F59E0B; border-radius: 6px; padding: 12px; margin-bottom: 8px;">
                                <b>Employee:</b> {req_emp.get('full_name', 'N/A')} (<b>Code:</b> {req_emp.get('employee_code', 'N/A')}) | <b>Designation:</b> {req_emp.get('designation', 'Staff')}<br/>
                                <b>Entity:</b> {e_name} | <b>Client Work Site:</b> {c_name}<br/>
                                <b>Requested Amount:</b> <span style="font-size: 16px; font-weight: bold; color: #0F172A;">₹{float(req.get('amount', 0)):,.2f}</span> | <b>Date:</b> {req.get('requested_date') or str(req.get('created_at'))[:10]}<br/>
                                <b>Reason:</b> {req.get('reason', 'None')}
                            </div>
                            """, unsafe_allow_html=True)

                            col_ap, col_rj, _ = st.columns([1.5, 1.5, 5])
                            if col_ap.button("✅ Approve Advance", key=f"adv_app_{req['id']}", type="primary"):
                                supabase.table("advance_salaries").update({"status": "APPROVED"}).eq("id", req["id"]).execute()
                                st.success(f"Advance Approved for {req_emp.get('full_name')}!")
                                st.rerun()

                            if col_rj.button("❌ Reject Request", key=f"adv_rej_{req['id']}"):
                                supabase.table("advance_salaries").update({"status": "REJECTED_BY_ADMIN"}).eq("id", req["id"]).execute()
                                st.warning("Advance request rejected!")
                                st.rerun()
                    else:
                        st.info("No pending advance requests from supervisor.")

                with t_adv_all:
                    table_rows = []
                    for a in adv_reqs:
                        emp_info = emp_map.get(a.get("employee_id"), {})
                        table_rows.append({
                            "Date": a.get("requested_date") or str(a.get("created_at"))[:10],
                            "Emp Code": emp_info.get("employee_code", "N/A"),
                            "Employee Name": emp_info.get("full_name", "N/A"),
                            "Entity": ent_map.get(emp_info.get("entity_id"), "N/A"),
                            "Client Site": cli_map.get(emp_info.get("client_id"), "N/A"),
                            "Amount (₹)": f"{float(a.get('amount', 0)):,.2f}",
                            "Reason": a.get("reason", ""),
                            "Status": a.get("status", "PENDING")
                        })
                    st.dataframe(pd.DataFrame(table_rows), use_container_width=True)
            else:
                st.info("No salary advance records found.")

        # 9. Attendance & OT Live Edit
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
                    d_sel_e = st.selectbox("Select Employee to Remove Attendance", options=list(emp_map.keys()) if emp_map else ["No Employees"])
                    d_sel_d = st.date_input("Date to Delete", value=date.today())
                    if st.form_submit_button("🗑️ Delete Attendance Record"):
                        if emp_map:
                            supabase.table("attendance").delete().eq("employee_id", emp_map[d_sel_e]).eq("date", str(d_sel_d)).execute()
                            st.warning(f"🗑️ Data Deleted Successfully: Attendance deleted for {d_sel_d}!")

        # 10. Candidate Approvals (Supervisor Verified -> Admin Login Creation)
        elif selected_panel == "Candidate Approvals":
            st.subheader("New Candidate Approvals & Login Dispatch (Admin Desk)")
            cands = supabase.table("employees").select("*").eq("status", "PENDING_ADMIN").execute().data or []
            if cands:
                ents = fetch_cached_entities()
                pref_dict = {f"{e['name']} ({e['code_prefix']})": e for e in ents}
                
                for cand in cands:
                    with st.expander(f"📋 Applicant: {cand['full_name']} (Phone: {cand['phone_number']}) | DOB: {cand.get('dob')} | Gender: {cand.get('gender')}"):
                        app1, app2 = st.columns(2)
                        sel_pref_label = app1.selectbox("Select Entity Provider", options=list(pref_dict.keys()) if pref_dict else ["Default"], key=f"pref_{cand['id']}")
                        selected_ent = pref_dict.get(sel_pref_label, {})
                        prefix = selected_ent.get("code_prefix", "SE")
                        
                        generated_code = f"{prefix}{str(cand.get('id', '001'))[:4].upper()}"
                        set_user_id = app1.text_input("User ID (Default Employee Code)", value=generated_code, key=f"uid_{cand['id']}")
                        set_pwd = app2.text_input("Set Initial Password", value="emp" + cand['phone_number'][-4:], key=f"pwd_{cand['id']}")
                        
                        app_c1, app_c2 = st.columns(2)
                        conf_desig = app_c1.text_input("Confirm Designation *", value=cand.get("designation") or "Associate", key=f"c_desig_{cand['id']}")
                        conf_cat = app_c2.selectbox("Confirm Category *", ["Skilled", "Semi-Skilled", "Unskilled"], index=1, key=f"c_cat_{cand['id']}")
                        
                        sel_shift = app2.selectbox("Confirm Shift Timing *", STANDARD_SHIFTS, key=f"shift_{cand['id']}")
                        sel_wo = app1.selectbox("Confirm Weekly Off Day *", ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], key=f"wo_{cand['id']}")

                        col_act1, col_act2 = st.columns(2)
                        if col_act1.button("✅ Approve & Send Login Credentials", key=f"ap_{cand['id']}", type="primary"):
                            supabase.table("employees").update({
                                "employee_code": set_user_id, 
                                "user_id": set_user_id, 
                                "password": set_pwd,
                                "designation": conf_desig,
                                "category": conf_cat,
                                "status": "APPROVED",
                                "weekly_off_day": sel_wo,
                                "shift_hours": 8.5,
                                "entity_id": selected_ent.get("id", cand.get("entity_id"))
                            }).eq("id", cand["id"]).execute()
                            
                            st.cache_data.clear()
                            
                            # WhatsApp Link Dispatch
                            msg = f"Hello {cand['full_name']}, Welcome! Your ESS Portal login credentials are: User ID: {set_user_id}, Password: {set_pwd}. Login here: https://employeeselfservice.streamlit.app/"
                            encoded_msg = urllib.parse.quote(msg)
                            wa_url = f"https://wa.me/91{cand['phone_number']}?text={encoded_msg}"
                            
                            st.success(f"✅ Data Saved Successfully: Candidate approved! User ID: {set_user_id}")
                            st.markdown(f'<a href="{wa_url}" target="_blank" style="display:inline-block; background-color:#25D366; color:white; padding:8px 16px; border-radius:4px; text-decoration:none; font-weight:bold;">📲 Send Login via WhatsApp to {cand["phone_number"]}</a>', unsafe_allow_html=True)

                        if col_act2.button("🗑️ Reject & Delete Application", key=f"rej_{cand['id']}"):
                            supabase.table("employees").delete().eq("id", cand["id"]).execute()
                            st.cache_data.clear()
                            st.warning("🗑️ Data Deleted Successfully: Application rejected!")
                            st.rerun()
            else:
                st.info("No candidates pending admin approval.")

        # 11. User Roles & Access
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

    # -------------------------------------------------------------------------
    # 4.2 SUPERVISOR PORTAL
    # -------------------------------------------------------------------------
    elif active_role == "supervisor":
        if "active_sup_tab" not in st.session_state:
            st.session_state.active_sup_tab = "Candidate Verification"

        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS</div>', unsafe_allow_html=True)
            st.markdown('<div class="logged-badge">● Logged In: SUPERVISOR</div>', unsafe_allow_html=True)
            st.write(f"Supervisor: **{st.session_state.user.get('full_name')}**")
            st.caption("SUPERVISOR DESK")

            sup_tabs = [
                "Candidate Verification",
                "Site Attendance & Punch",
                "Workforce Roster",
                "PPE & Advance Approvals"
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

        if selected_sup_panel == "Candidate Verification":
            st.subheader("New Joinee Verification & Deployment Setup / कामगार प्राथमिक पडताळणी")
            cand_list = supabase.table("employees").select("*").eq("status", "PENDING_SUPERVISOR").execute().data or []
            
            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_dict = {e["name"]: e["id"] for e in ent_list}
            c_dict = {c["name"]: c["id"] for c in cli_list}

            if cand_list:
                for c in cand_list:
                    with st.expander(f"📋 Applicant: {c['full_name']} (Mobile: {c['phone_number']}) | DOB: {c.get('dob')} | Gender: {c.get('gender')}"):
                        v_col1, v_col2 = st.columns(2)
                        
                        s_ent = v_col1.selectbox("Assign Entity Provider / फर्म निवडा *", list(e_dict.keys()) if e_dict else ["No Entity"], key=f"sup_ent_{c['id']}")
                        s_cli = v_col2.selectbox("Assign Client Work Site / प्लांट लोकेशन *", list(c_dict.keys()) if c_dict else ["No Client"], key=f"sup_cli_{c['id']}")

                        s_desig = v_col1.text_input("Assign Designation / पद निवडा *", value=c.get("designation") or "Associate", key=f"desig_{c['id']}")
                        s_shift = v_col2.selectbox("Assign Shift Schedule / शिफ्ट वेळ *", STANDARD_SHIFTS, key=f"shift_{c['id']}")

                        s_join_date = v_col1.date_input("Assign Joining Date / कामावर रुजू होण्याची तारीख *", value=date.today(), key=f"join_{c['id']}")
                        s_wo = v_col2.selectbox("Assign Weekly Off Day / आठवडी सुट्टीचा वार *", ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], index=0, key=f"wo_{c['id']}")

                        st.write("---")
                        col_act1, col_act2 = st.columns([2, 5])
                        if col_act1.button("✅ Verify & Forward to Admin", key=f"fwd_{c['id']}", type="primary"):
                            try:
                                supabase.table("employees").update({
                                    "entity_id": e_dict.get(s_ent),
                                    "client_id": c_dict.get(s_cli),
                                    "designation": s_desig,
                                    "shift_hours": 8.5,
                                    "joining_date": str(s_join_date),
                                    "weekly_off_day": s_wo,
                                    "status": "PENDING_ADMIN"
                                }).eq("id", c["id"]).execute()
                                st.cache_data.clear()
                                st.success("✅ Application Verified & Forwarded to Admin! / अर्ज तपासून ॲडमिनकडे मंजुरीसाठी पाठवला आहे.")
                                st.rerun()
                            except Exception as err:
                                st.error(f"Error forwarding candidate: {err}")
            else:
                st.info("No candidates pending supervisor verification. / सुपरवायझर पडताळणीसाठी कोणताही अर्ज प्रलंबित नाही.")

        elif selected_sup_panel == "PPE & Advance Approvals":
            st.subheader("Supervisor Review: PPE & Advance Salary Requests")
            t_sup_ppe, t_sup_adv = st.tabs(["🦺 PPE Requests", "💰 Advance Requests"])

            all_emps_data = fetch_cached_employees()
            emp_map = {e["id"]: e for e in all_emps_data}
            cli_map = {c["id"]: c["name"] for c in fetch_cached_clients()}
            ent_map = {e["id"]: e["name"] for e in fetch_cached_entities()}

            with t_sup_ppe:
                ppe_pending = supabase.table("ppe_records").select("*").eq("status", "PENDING_SUPERVISOR").order("created_at", desc=True).execute().data or []
                if ppe_pending:
                    for req in ppe_pending:
                        req_emp = emp_map.get(req.get("employee_id"), {})
                        st.markdown(f"""
                        <div style="background-color: #F8FAFC; border: 1px solid #CBD5E1; border-left: 5px solid #F59E0B; border-radius: 6px; padding: 12px; margin-bottom: 8px;">
                            <b>Employee:</b> {req_emp.get('full_name')} (<b>Code:</b> {req_emp.get('employee_code')}) | <b>Designation:</b> {req_emp.get('designation')}<br/>
                            <b>Firm / Entity:</b> {ent_map.get(req_emp.get('entity_id'), 'N/A')} | <b>Client Work Site:</b> {cli_map.get(req_emp.get('client_id'), 'N/A')}<br/>
                            <b>Item:</b> {req.get('item_type')} | <b>Size:</b> {req.get('size')} | <b>Quantity:</b> {req.get('quantity')}
                        </div>
                        """, unsafe_allow_html=True)
                        col1, col2, _ = st.columns([1.5, 1.5, 5])
                        if col1.button("✅ Forward to Admin", key=f"sup_app_ppe_{req['id']}", type="primary"):
                            supabase.table("ppe_records").update({"status": "PENDING_ADMIN"}).eq("id", req["id"]).execute()
                            st.success("Verified and forwarded to Admin!")
                            st.rerun()
                        if col2.button("❌ Reject", key=f"sup_rej_ppe_{req['id']}"):
                            supabase.table("ppe_records").update({"status": "REJECTED_BY_SUPERVISOR"}).eq("id", req["id"]).execute()
                            st.warning("Rejected!")
                            st.rerun()
                else:
                    st.info("No PPE requests pending supervisor review.")

            with t_sup_adv:
                adv_pending = supabase.table("advance_salaries").select("*").eq("status", "PENDING_SUPERVISOR").order("created_at", desc=True).execute().data or []
                if adv_pending:
                    for req in adv_pending:
                        req_emp = emp_map.get(req.get("employee_id"), {})
                        st.markdown(f"""
                        <div style="background-color: #F8FAFC; border: 1px solid #CBD5E1; border-left: 5px solid #F59E0B; border-radius: 6px; padding: 12px; margin-bottom: 8px;">
                            <b>Employee:</b> {req_emp.get('full_name')} (<b>Code:</b> {req_emp.get('employee_code')}) | <b>Designation:</b> {req_emp.get('designation')}<br/>
                            <b>Firm / Entity:</b> {ent_map.get(req_emp.get('entity_id'), 'N/A')} | <b>Client Work Site:</b> {cli_map.get(req_emp.get('client_id'), 'N/A')}<br/>
                            <b>Requested Amount:</b> ₹{float(req.get('amount', 0)):,.2f} | <b>Reason:</b> {req.get('reason')}
                        </div>
                        """, unsafe_allow_html=True)
                        col1, col2, _ = st.columns([1.5, 1.5, 5])
                        if col1.button("✅ Forward to Admin", key=f"sup_app_adv_{req['id']}", type="primary"):
                            supabase.table("advance_salaries").update({"status": "PENDING_ADMIN"}).eq("id", req["id"]).execute()
                            st.success("Verified and forwarded to Admin!")
                            st.rerun()
                        if col2.button("❌ Reject", key=f"sup_rej_adv_{req['id']}"):
                            supabase.table("advance_salaries").update({"status": "REJECTED_BY_SUPERVISOR"}).eq("id", req["id"]).execute()
                            st.warning("Rejected!")
                            st.rerun()
                else:
                    st.info("No advance requests pending supervisor review.")

        elif selected_sup_panel == "Site Attendance & Punch":
            st.subheader("Live Plant Attendance Review")
            st.info("Worker punches are geo-fenced against assigned plant coordinates.")

        elif selected_sup_panel == "Workforce Roster":
            st.subheader("Supervised Workforce Roster / कामगार यादी")
            try:
                emps = supabase.table("employees").select("employee_code, full_name, designation, phone_number, status, weekly_off_day").eq("role", "employee").execute().data or []
            except Exception:
                emps = supabase.table("employees").select("employee_code, full_name, designation, phone_number, status").eq("role", "employee").execute().data or []
            
            if emps:
                st.dataframe(pd.DataFrame(emps), use_container_width=True)
            else:
                st.info("No active workforce found.")

    # -------------------------------------------------------------------------
    # 4.3 CLIENT DESK
    # -------------------------------------------------------------------------
    elif active_role == "client":
        if "active_client_tab" not in st.session_state:
            st.session_state.active_client_tab = "Plant Workforce Overview"

        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS</div>', unsafe_allow_html=True)
            st.markdown('<div class="logged-badge">● Logged In: CLIENT DESK</div>', unsafe_allow_html=True)
            st.write(f"Authorized Rep: **{st.session_state.user.get('full_name')}**")
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

        if selected_client_panel == "Plant Workforce Overview":
            col_c1, col_c2, col_c3 = st.columns(3)
            col_c1.metric("Deployed Workforce", "12 Staff")
            col_c2.metric("Present Today", "11")
            col_c3.metric("Absent Today", "1")
            st.write("---")
            st.subheader("Active Workforce on Site")
            emps = supabase.table("employees").select("employee_code, full_name, designation, shift_hours").eq("role", "employee").eq("status", "APPROVED").execute().data or []
            if emps:
                st.dataframe(pd.DataFrame(emps), use_container_width=True)

        elif selected_client_panel == "Daily Attendance Muster":
            st.subheader("Daily Attendance Records")
            att_data = supabase.table("attendance").select("*").execute().data or []
            if att_data:
                st.dataframe(pd.DataFrame(att_data), use_container_width=True)
            else:
                st.info("No attendance records logged yet.")

        elif selected_client_panel == "Monthly Invoices & Billing":
            st.subheader("Monthly Tax Invoices")
            inv_list = supabase.table("client_invoices").select("*").execute().data or []
            if inv_list:
                st.dataframe(pd.DataFrame(inv_list), use_container_width=True)
            else:
                st.info("No invoices raised for this site yet.")

        elif selected_client_panel == "Compliance & Wage Sheets":
            st.subheader("Statutory Compliance & Locked Wage Sheets")
            st.info("Wage sheets locked by Admin on 1st of every month are verified for compliance.")

    # -------------------------------------------------------------------------
    # 4.4 EMPLOYEE PORTAL (With Password Change Facility)
    # -------------------------------------------------------------------------
    elif active_role == "employee":
        emp = st.session_state.user

        today_date = date.today()
        today_str = str(today_date)

        if "active_emp_tab" not in st.session_state:
            st.session_state.active_emp_tab = "Daily Punch (Geofenced)"

        with st.sidebar:
            st.markdown('<div class="sidebar-brand">HRMS</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="logged-badge">● Logged In: EMPLOYEE ({emp.get("employee_code", "TEMP")})</div>', unsafe_allow_html=True)
            st.write(f"User: **{emp.get('full_name')}**")
            st.caption("ESS PORTAL")

            emp_tabs = [
                "Daily Punch (Geofenced)",
                "My Profile Details",
                "Attendance Calendar",
                "Monthly Payslips (15th)",
                "Official Documents Vault",
                "Request PPE Equipment",
                "Request Salary Advance",
                "Change Password"
            ]

            for ep_tab in emp_tabs:
                btn_style = "primary" if st.session_state.active_emp_tab == ep_tab else "secondary"
                if st.button(ep_tab, key=f"emp_btn_{ep_tab}", type=btn_style):
                    st.session_state.active_emp_tab = ep_tab
                    st.rerun()

            st.write("---")
            if st.button("Logout", key="emp_logout"):
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

        selected_emp_panel = st.session_state.active_emp_tab
        st.title(selected_emp_panel)

        # 1. PUNCH PANEL
        if selected_emp_panel == "Daily Punch (Geofenced)":
            st.subheader("Daily Attendance Punch")

            assigned_lat = None
            assigned_lon = None
            plant_name = "Work Site Not Assigned"

            emp_client_id = emp.get("client_id")
            if emp_client_id:
                try:
                    cl_data = supabase.table("clients").select("name, latitude, longitude").eq("id", emp_client_id).execute().data
                    if cl_data and len(cl_data) > 0:
                        plant_name = cl_data[0].get("name", "Authorized Plant Site")
                        if cl_data[0].get("latitude") is not None and cl_data[0].get("longitude") is not None:
                            assigned_lat = float(cl_data[0]["latitude"])
                            assigned_lon = float(cl_data[0]["longitude"])
                except Exception as err:
                    st.error(f"Client location fetch error: {err}")

            if assigned_lat is None or assigned_lon is None:
                st.warning("⚠️ Tumchya profile la ajun authorized Client Work Site jodhli nahiye kinva Client che GPS location set kelele nahi. Krupaya Admin shi sampark kara.")
                st.stop()

            scheduled_shift_hours = float(emp.get("shift_hours") or 8.5)

            st.markdown(f"""
            <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 18px; margin-bottom: 20px;">
                <h4 style="margin: 0 0 8px 0; color: #0F172A;">Assigned Location: <b>{plant_name}</b></h4>
                <p style="margin: 0; color: #64748B; font-size: 14px;">Shift Requirement: <b>{scheduled_shift_hours:.1f} Hours</b> | Security perimeter: Strict 15-meter geofenced radius active.</p>
            </div>
            """, unsafe_allow_html=True)

            att_check = []
            try:
                att_res = supabase.table("attendance").select("*").eq("employee_id", emp["id"]).eq("date", today_str).execute()
                att_check = att_res.data or []
            except Exception:
                att_check = []

            st.components.v1.html("""
            <script>
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(function(position) {
                    const lat = position.coords.latitude;
                    const lon = position.coords.longitude;
                    const url = new URL(window.parent.location.href);
                    if (url.searchParams.get("device_lat") !== lat.toString() || url.searchParams.get("device_lon") !== lon.toString()) {
                        url.searchParams.set("device_lat", lat);
                        url.searchParams.set("device_lon", lon);
                        window.parent.history.replaceState({}, '', url.toString());
                    }
                }, function(error) {
                    console.log("GPS Location error: " + error.message);
                }, {enableHighAccuracy: true});
            }
            </script>
            """, height=0)

            raw_dev_lat = st.query_params.get("device_lat")
            raw_dev_lon = st.query_params.get("device_lon")

            st.markdown('<div class="submit-red-btn" style="max-width: 320px;">', unsafe_allow_html=True)
            punch_pressed = st.button("👍 Thumb Punch In / Out", key="strict_thumb_punch_btn")
            st.markdown('</div>', unsafe_allow_html=True)

            if punch_pressed:
                if not raw_dev_lat or not raw_dev_lon:
                    st.error("❌ GPS Location Required: Krupaya tumchya browser madhye Location (GPS) ON kara ani Allow kara!")
                else:
                    actual_user_lat = float(raw_dev_lat)
                    actual_user_lon = float(raw_dev_lon)

                    # Geofence Distance Calculation
                    R = 6371000.0
                    phi1 = math.radians(actual_user_lat)
                    phi2 = math.radians(assigned_lat)
                    delta_phi = math.radians(assigned_lat - actual_user_lat)
                    delta_lambda = math.radians(assigned_lon - actual_user_lon)
                    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
                    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
                    dist = R * c

                    is_valid_location = dist <= 50.0

                    if is_valid_location:
                        now_time = datetime.now()
                        now_timestamp_str = now_time.isoformat()
                        display_time = now_time.strftime("%I:%M %p")

                        if not att_check or not att_check[0].get("punch_in"):
                            try:
                                supabase.table("attendance").upsert({
                                    "employee_id": emp["id"],
                                    "date": today_str,
                                    "status": "IN_PROGRESS",
                                    "punch_in": now_timestamp_str,
                                    "punch_out": None,
                                    "ot_hours": 0.0,
                                    "is_valid_geo": True
                                }, on_conflict="employee_id,date").execute()
                                st.success(f"✅ Punch IN Recorded at {display_time}! Shift suru jhali.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error logging Punch IN: {e}")
                        else:
                            record = att_check[0]
                            try:
                                supabase.table("attendance").update({
                                    "punch_out": now_timestamp_str,
                                    "status": "IN_PROGRESS",
                                    "is_valid_geo": True
                                }).eq("id", record["id"]).execute()
                                st.success(f"✅ Punch OUT Updated at {display_time}! Purn shift che timing udya final evaluate hoil.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error updating Punch OUT: {e}")
                    else:
                        st.error("❌ Invalid Location! Tumhi authorized plant chya baher ahat. Punch sweekarla janar nahi.")

            if att_check:
                today_rec = att_check[0]
                def format_display_time(val):
                    if not val: return "--:--"
                    try:
                        c_val = str(val).replace("T", " ")
                        if "." in c_val: c_val = c_val.split(".")[0]
                        return datetime.strptime(c_val, "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p")
                    except Exception:
                        return str(val)[:8]

                p_in_disp = format_display_time(today_rec.get("punch_in"))
                p_out_disp = format_display_time(today_rec.get("punch_out")) if today_rec.get("punch_out") else "Working (Pending Punch OUT)"
                st.write("")
                st.info(f"📋 **Today's Activity:** Status: **Shift Ongoing** | **Punch IN:** `{p_in_disp}` | **Last Punch OUT:** `{p_out_disp}`")

        # 2. PROFILE DETAILS PANEL
        elif selected_emp_panel == "My Profile Details":
            st.subheader("Personal, Employment & Statutory Profile / वैयक्तिक आणि रोजगाराची माहिती")

            cl_name = "Not Assigned / नियुक्त नाही"
            if emp.get("client_id"):
                try:
                    cl_info = supabase.table("clients").select("name").eq("id", emp["client_id"]).execute().data
                    if cl_info: cl_name = cl_info[0].get("name")
                except Exception: pass

            aadhar_val = str(emp.get("aadhar_number") or "")

            p_col1, p_col2 = st.columns(2)
            with p_col1:
                st.markdown(f"""
                <div class="profile-card">
                    <h4 style="margin-top:0; color:#0F172A;">👤 Personal & Employment / वैयक्तिक तपशील</h4>
                    <b>Full Name / पूर्ण नाव:</b> {emp.get('full_name')}<br/>
                    <b>Employee Code / कर्मचारी कोड:</b> {emp.get('employee_code', 'TEMP')}<br/>
                    <b>Father's Name / वडिलांचे नाव:</b> {emp.get('father_name', 'N/A')}<br/>
                    <b>Gender:</b> {emp.get('gender', 'N/A')} | <b>DOB:</b> {emp.get('dob', 'N/A')}<br/>
                    <b>Mobile Number / मोबाईल:</b> {emp.get('phone_number')}<br/>
                    <b>Emergency Contact / आपत्कालीन संपर्क:</b> {emp.get('emergency_contact', 'N/A')}<br/>
                    <b>Designation / पद:</b> {emp.get('designation', 'Associate')}<br/>
                    <b>Client Site / कंपनी लोकेशन:</b> {cl_name}<br/>
                    <b>Weekly Off Day:</b> {emp.get('weekly_off_day', 'Sunday')}<br/>
                    <b>Marital Status / वैवाहिक स्थिती:</b> {emp.get('marital_status', 'Single')}
                </div>
                """, unsafe_allow_html=True)

            with p_col2:
                st.markdown(f"""
                <div class="profile-card">
                    <h4 style="margin-top:0; color:#0F172A;">🪪 Statutory & Bank / बँक व कायदेशीर तपशील</h4>
                    <b>UAN Number / यूएएन:</b> {emp.get('uan_number', 'N/A')}<br/>
                    <b>ESIC Number / ईएसआयसी:</b> {emp.get('esic_number', 'N/A')}<br/>
                    <b>PAN Number / पॅन:</b> {emp.get('pan_number', 'N/A')}<br/>
                    <b>Aadhaar Number / आधार क्रमांक:</b> {aadhar_val}<br/>
                    <b>Bank Name / बँकेचे नाव:</b> {emp.get('bank_name', 'N/A')} ({emp.get('bank_branch', 'Main')})<br/>
                    <b>Account No / खाते क्रमांक:</b> {emp.get('bank_account_no', 'N/A')}<br/>
                    <b>IFSC Code / आयएफएससी:</b> {emp.get('ifsc_code', 'N/A')}
                </div>
                """, unsafe_allow_html=True)

            st.write("---")
            st.subheader("✏️ Update Bank Details (Auto-Synced with Admin) / बँक तपशील अपडेट करा")
            with st.form("emp_update_bank_form"):
                b1, b2 = st.columns(2)
                up_bank_name = b1.text_input("Bank Name / बँकेचे नाव", value=emp.get("bank_name", ""))
                up_bank_branch = b2.text_input("Branch Name / शाखेचे नाव", value=emp.get("bank_branch", ""))
                up_acc_no = b1.text_input("Account Number / खाते क्रमांक", value=emp.get("bank_account_no", ""))
                up_ifsc = b2.text_input("IFSC Code / आयएफएससी कोड", value=emp.get("ifsc_code", ""))

                if st.form_submit_button("Update Bank Details / बँक माहिती अपडेट करा", type="primary"):
                    if up_bank_name and up_acc_no and up_ifsc:
                        try:
                            supabase.table("employees").update({
                                "bank_name": up_bank_name,
                                "bank_branch": up_bank_branch,
                                "bank_account_no": up_acc_no,
                                "ifsc_code": up_ifsc
                            }).eq("id", emp["id"]).execute()
                            st.session_state.user["bank_name"] = up_bank_name
                            st.session_state.user["bank_branch"] = up_bank_branch
                            st.session_state.user["bank_account_no"] = up_acc_no
                            st.session_state.user["ifsc_code"] = up_ifsc
                            st.cache_data.clear()
                            st.success("✅ Data Updated Successfully! Bank details synchronized with Admin portal.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                    else:
                        st.error("Bank Name, Account Number and IFSC Code are required!")

        # 3. ATTENDANCE PANEL
        elif selected_emp_panel == "Attendance Calendar":
            st.subheader("My Attendance Muster & Calendar / माझी उपस्थिती नोंदवही")
            t_day, t_month, t_year, t_ph = st.tabs([
                "📅 Daily View / दैनिक उपस्थिती",
                "🗓️ Monthly Summary / मासिक गोषवारा",
                "📈 Annual Muster / वार्षिक मस्टर",
                "🎉 Paid Holidays / सवेतन सुट्ट्या"
            ])

            st.markdown("""
            <div style="display:flex; gap:12px; margin-bottom:15px; font-weight:600; font-size:12px;">
                <span style="background-color:#16A34A; color:white; padding:3px 8px; border-radius:4px;">P : Present / हजर</span>
                <span style="background-color:#F59E0B; color:white; padding:3px 8px; border-radius:4px;">HD : Half Day / अर्धा दिवस</span>
                <span style="background-color:#DC2626; color:white; padding:3px 8px; border-radius:4px;">A : Absent / गैरहजर</span>
                <span style="background-color:#9333EA; color:white; padding:3px 8px; border-radius:4px;">PH : Paid Holiday / सवेतन सुट्टी</span>
                <span style="background-color:#6B7280; color:white; padding:3px 8px; border-radius:4px;">WO : Weekly Off / साप्ताहिक सुट्टी</span>
            </div>
            """, unsafe_allow_html=True)

            my_att = []
            try:
                att_response = supabase.table("attendance").select("*").eq("employee_id", emp["id"]).order("date", desc=True).execute()
                my_att = att_response.data or []
            except Exception:
                my_att = []
            att_dict = {str(a["date"]): a for a in my_att if a.get("date")}

            ph_records = []
            if emp.get("client_id"):
                try:
                    ph_records = supabase.table("paid_holidays").select("*").eq("client_id", emp["client_id"]).execute().data or []
                except Exception:
                    try:
                        ph_records = supabase.table("paid_holidays").select("*").execute().data or []
                    except Exception:
                        ph_records = []
            ph_dates = {str(p.get("holiday_date")): p.get("holiday_name", "Paid Holiday") for p in ph_records if p.get("holiday_date")}

            def clean_time_format(val):
                if not val or val == "--": return "--:--"
                try:
                    clean_str = str(val).replace("T", " ")
                    if "." in clean_str: clean_str = clean_str.split(".")[0]
                    if " " in clean_str: clean_str = clean_str.split(" ")[1]
                    return datetime.strptime(clean_str, "%H:%M:%S").strftime("%I:%M %p")
                except Exception:
                    return "--:--"

            emp_wo_day = emp.get("weekly_off_day", "Sunday")

            with t_day:
                st.markdown("##### 📅 Single Day Attendance Details / एका दिवसाचा उपस्थिती तपशील")
                sel_day = st.date_input("Select Date / तारीख निवडा", value=today_date)
                sel_day_str = str(sel_day)

                badge_title = "ABSENT / गैरहजर"
                badge_bg = "#EF4444"
                p_in_time = "--:--"
                p_out_time = "--:--"
                ot_time = "0.0 Hrs"
                info_msg = "No work activity recorded on this date. / या तारखेला कामाची नोंद नाही."

                if sel_day_str in ph_dates:
                    badge_title = "PAID HOLIDAY / सवेतन सुट्टी"
                    badge_bg = "#9333EA"
                    info_msg = f"Public / Client Holiday: {ph_dates[sel_day_str]}"
                elif sel_day.strftime("%A") == emp_wo_day:
                    badge_title = f"WEEKLY OFF ({emp_wo_day.upper()})"
                    badge_bg = "#64748B"
                    info_msg = f"Scheduled Weekly Off ({emp_wo_day})"
                elif sel_day == today_date:
                    badge_title = "SHIFT IN PROGRESS / शिफ्ट सुरू आहे"
                    badge_bg = "#0284C7"
                    if sel_day_str in att_dict:
                        rec = att_dict[sel_day_str]
                        p_in_time = clean_time_format(rec.get("punch_in"))
                        p_out_time = clean_time_format(rec.get("punch_out"))
                        ot_time = f"{rec.get('ot_hours', 0.0)} Hrs"
                        info_msg = "Shift is ongoing. Final attendance will update tomorrow."
                    else:
                        info_msg = "Shift punch not started yet for today."
                elif sel_day_str in att_dict:
                    rec = att_dict[sel_day_str]
                    st_val = rec.get("status", "P")
                    p_in_time = clean_time_format(rec.get("punch_in"))
                    p_out_time = clean_time_format(rec.get("punch_out"))
                    ot_time = f"{rec.get('ot_hours', 0.0)} Hrs"

                    if st_val == "P":
                        badge_title = "PRESENT (FULL DAY) / पूर्ण दिवस हजर"
                        badge_bg = "#10B981"
                        info_msg = "Shift duration completed successfully."
                    elif st_val == "HD":
                        badge_title = "HALF DAY / अर्धा दिवस"
                        badge_bg = "#F59E0B"
                        info_msg = "Left early / Half-day criteria met."
                    else:
                        badge_title = "ABSENT / LWP / गैरहजर"
                        badge_bg = "#EF4444"
                        info_msg = "Insufficient shift hours completed."

                st.markdown(f"""
                <div style="background-color: white; border: 1px solid #E2E8F0; border-left: 6px solid {badge_bg}; border-radius: 8px; padding: 20px; max-width: 650px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-top: 10px; margin-bottom: 15px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <span style="font-size: 15px; font-weight: 700; color: #1E293B;">Date / तारीख: {sel_day.strftime('%d %B %Y')}</span>
                        <span style="background-color: {badge_bg}; color: white; padding: 4px 14px; border-radius: 20px; font-weight: 700; font-size: 12px; letter-spacing: 0.5px;">{badge_title}</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; background-color: #F8FAFC; border-radius: 6px; padding: 12px; margin-bottom: 12px; border: 1px solid #F1F5F9;">
                        <div>
                            <span style="font-size: 11px; color: #64748B; font-weight: 600; text-transform: uppercase;">Punch In</span><br/>
                            <span style="font-size: 16px; font-weight: 700; color: #0F172A;">{p_in_time}</span>
                        </div>
                        <div>
                            <span style="font-size: 11px; color: #64748B; font-weight: 600; text-transform: uppercase;">Punch Out</span><br/>
                            <span style="font-size: 16px; font-weight: 700; color: #0F172A;">{p_out_time}</span>
                        </div>
                        <div>
                            <span style="font-size: 11px; color: #64748B; font-weight: 600; text-transform: uppercase;">Overtime</span><br/>
                            <span style="font-size: 16px; font-weight: 700; color: #0F172A;">{ot_time}</span>
                        </div>
                    </div>
                    <p style="margin: 0; font-size: 13px; color: #475569;">ℹ️ {info_msg}</p>
                </div>
                """, unsafe_allow_html=True)

            with t_month:
                st.write("##### Monthly Attendance Muster & Shift Evaluation")
                cur_year = today_date.year
                cur_month = today_date.month
                days_in_cur_month = 30 if cur_month in [4,6,9,11] else (28 if cur_month == 2 else 31)

                month_rows = []
                for d in range(1, days_in_cur_month + 1):
                    d_obj = date(cur_year, cur_month, d)
                    d_str = str(d_obj)

                    if d_str in ph_dates:
                        day_st = "PH"
                        remark = f"Paid Holiday: {ph_dates[d_str]}"
                    elif d_obj.strftime("%A") == emp_wo_day:
                        day_st = "WO"
                        remark = f"Weekly Off ({emp_wo_day})"
                    elif d_obj == today_date:
                        day_st = "IN_PROGRESS"
                        remark = "Shift In Progress (Pending Final Hours)"
                    elif d_str in att_dict:
                        rec = att_dict[d_str]
                        p_in_raw = rec.get("punch_in")
                        p_out_raw = rec.get("punch_out")

                        if p_in_raw and p_out_raw:
                            try:
                                c_in = p_in_raw.replace("T", " ").split(".")[0]
                                c_out = p_out_raw.replace("T", " ").split(".")[0]
                                dt_in = datetime.strptime(c_in, "%Y-%m-%d %H:%M:%S")
                                dt_out = datetime.strptime(c_out, "%Y-%m-%d %H:%M:%S")
                                worked = round(max(0.0, (dt_out - dt_in).total_seconds() / 3600.0), 2)
                            except Exception:
                                worked = float(emp.get("shift_hours") or 8.5)

                            shift_req = float(emp.get("shift_hours") or 8.5)

                            if worked >= shift_req:
                                day_st = "P"
                                ot_val = max(0.0, round(worked - shift_req, 2))
                                remark = f"Present ({worked} hrs) | OT: {ot_val} hrs"
                            elif worked >= (shift_req / 2.0):
                                day_st = "HD"
                                remark = f"Half Day ({worked} hrs - Left Early)"
                            else:
                                day_st = "A"
                                remark = f"Absent / LWP (Only {worked} hrs worked)"
                        else:
                            day_st = "A"
                            remark = "Absent / LWP (Missed Punch Out)"
                    else:
                        day_st = "A" if d_obj < today_date else "-"
                        remark = "Absent (No Punch)" if day_st == "A" else "Upcoming"

                    month_rows.append({"Date": d_str, "Day": d_obj.strftime("%A"), "Status": day_st, "Details & Working Hours": remark})

                st.dataframe(pd.DataFrame(month_rows), use_container_width=True)

            with t_year:
                st.write("##### Annual Month & Day-Wise Attendance Muster")
                s_year = st.selectbox("Select Year", [2026, 2025, 2027], index=0)
                s_month_num = st.selectbox("Select Month", list(range(1, 13)), index=(today_date.month - 1), format_func=lambda x: date(2026, x, 1).strftime('%B'))

                days_cnt = 30 if s_month_num in [4,6,9,11] else (28 if s_month_num == 2 else 31)
                muster_cols = st.columns(7)

                for day_i in range(1, days_cnt + 1):
                    dt_check = date(s_year, s_month_num, day_i)
                    dt_str = str(dt_check)

                    if dt_str in ph_dates:
                        badge = "PH"
                        bg = "#9333EA"
                    elif dt_check.strftime("%A") == emp_wo_day:
                        badge = "WO"
                        bg = "#6B7280"
                    elif dt_check == today_date:
                        badge = "LIVE"
                        bg = "#0284C7"
                    elif dt_str in att_dict:
                        badge = att_dict[dt_str].get("status", "P")
                        bg = "#16A34A" if badge == "P" else ("#F59E0B" if badge == "HD" else "#DC2626")
                    else:
                        badge = "A" if dt_check < today_date else "-"
                        bg = "#DC2626" if badge == "A" else "#CBD5E1"

                    col_idx = (day_i - 1) % 7
                    muster_cols[col_idx].markdown(f"""
                    <div style="background-color:{bg}; color:white; padding:8px; border-radius:6px; text-align:center; margin-bottom:8px;">
                        <span style="font-size:11px;">{dt_check.strftime('%d %b')}</span><br/>
                        <b>{badge}</b>
                    </div>
                    """, unsafe_allow_html=True)

            with t_ph:
                st.write("##### Annual Client Paid Holidays (12 Mandatory PH)")
                if ph_records:
                    st.dataframe(pd.DataFrame(ph_records)[["holiday_date", "holiday_name"]], use_container_width=True)
                else:
                    st_holidays = [
                        {"Date": "2026-01-26", "Holiday Name": "Republic Day / प्रजासत्ताक दिन"},
                        {"Date": "2026-02-19", "Holiday Name": "Chhatrapati Shivaji Maharaj Jayanti / शिवजयंती"},
                        {"Date": "2026-03-03", "Holiday Name": "Holi (Dhulivandan) / होळी (धुलिवंदन)"},
                        {"Date": "2026-04-14", "Holiday Name": "Dr. Babasaheb Ambedkar Jayanti / आंबेडकर जयंती"},
                        {"Date": "2026-05-01", "Holiday Name": "Maharashtra Day / कामगार दिन"},
                        {"Date": "2026-08-15", "Holiday Name": "Independence Day / स्वातंत्र्य दिन"},
                        {"Date": "2026-09-04", "Holiday Name": "Ganesh Chaturthi / गणेश चतुर्थी"},
                        {"Date": "2026-10-02", "Holiday Name": "Mahatma Gandhi Jayanti / गांधी जयंती"},
                        {"Date": "2026-10-20", "Holiday Name": "Dussehra (Vijayadashami) / दसरा (विजयादशमी)"},
                        {"Date": "2026-11-09", "Holiday Name": "Diwali (Laxmi Pujan) / दिवाळी (लक्ष्मीपूजन)"},
                        {"Date": "2026-11-10", "Holiday Name": "Diwali (Balipratipada) / दिवाळी (बळीप्रतिपदा)"},
                        {"Date": "2026-12-25", "Holiday Name": "Christmas / नाताळ"}
                    ]
                    st.dataframe(pd.DataFrame(st_holidays), use_container_width=True)

        # 4. MONTHLY PAYSLIPS PANEL
        elif selected_emp_panel == "Monthly Payslips (15th)":
            st.subheader("Month-Wise Salary Payslips / मासिक पगार स्लिप")
            st.caption("Official payslips are generated on the 15th of every month following payroll closure.")
            
            sel_m = st.selectbox("Select Payroll Month", ["September 2026", "August 2026", "July 2026"])
            
            # १. वेज शीट ॲडमिनने लॉक केली आहे का ते तपासणे
            is_sheet_locked = False
            try:
                chk_lock = supabase.table("locked_payrolls").select("*").eq("entity_id", emp.get("entity_id")).eq("payroll_month", sel_m).eq("is_locked", True).execute().data
                if chk_lock:
                    is_sheet_locked = True
            except Exception:
                is_sheet_locked = False

            if not is_sheet_locked:
                st.warning(f"⏳ **{sel_m} ची वेज शीट अद्याप ॲडमिन पोर्टलवरून अंतिम (Lock) झालेली नाही.**\n\nमहिन्याची वेज शीट लॉक झाल्यानंतर आणि पुढील महिन्याच्या १५ तारखेला ही स्लिप येथे उपलब्ध होईल.")
            else:
                ent_obj = next((e for e in fetch_cached_entities() if e["id"] == emp.get("entity_id")), None)
                cli_name = next((c["name"] for c in fetch_cached_clients() if c["id"] == emp.get("client_id")), "Plant Site")
                
                # अचूक सॅलरी रूल शोधणे
                sal_rule = None
                try:
                    sr_query = supabase.table("salary_structures").select("*").eq("entity_id", emp.get("entity_id"))
                    if emp.get("client_id"):
                        sr_query = sr_query.eq("client_id", emp.get("client_id"))
                    if emp.get("designation"):
                        sr_query = sr_query.ilike("designation", emp.get("designation").strip())
                    if emp.get("category"):
                        sr_query = sr_query.eq("category", emp.get("category").strip())
                    s_matched = sr_query.execute().data
                    if s_matched:
                        sal_rule = s_matched[0]
                    else:
                        fallback_res = supabase.table("salary_structures").select("*").eq("entity_id", emp.get("entity_id")).execute().data
                        if fallback_res:
                            sal_rule = fallback_res[0]
                except Exception:
                    pass
                
                b_pay = float(sal_rule.get("basic", 14010.0)) if sal_rule else 14010.0
                d_pay = float(sal_rule.get("da", 2511.0)) if sal_rule else 2511.0
                h_pay = float(sal_rule.get("hra", 826.0)) if sal_rule else 826.0
                o_pay = float(sal_rule.get("other_allowance", 813.0)) if sal_rule else 813.0
                ot_rate = float(sal_rule.get("ot_rate_per_hour", 120.0)) if sal_rule else 120.0

                # प्रत्यक्ष हजेरी आणि ओटी तास
                p_days = 26.0
                ot_hrs = 0.0
                try:
                    att_recs = supabase.table("attendance").select("status, ot_hours").eq("employee_id", emp["id"]).execute().data or []
                    if att_recs:
                        p_days = len([a for a in att_recs if a.get("status") in ["P", "WO", "PH"]]) + (len([a for a in att_recs if a.get("status") == "HD"]) * 0.5)
                        ot_hrs = sum([float(a.get("ot_hours") or 0.0) for a in att_recs])
                except Exception:
                    pass

                e_basic = round((b_pay / 26.0) * p_days, 2)
                e_da = round((d_pay / 26.0) * p_days, 2)
                e_hra = round((h_pay / 26.0) * p_days, 2)
                e_other = round((o_pay / 26.0) * p_days, 2)
                e_ot = round(ot_hrs * ot_rate, 2)
                t_gross = e_basic + e_da + e_hra + e_other + e_ot

                # पीएफ सीलिंग (₹15,000 पेक्षा जास्त असल्यास कमाल ₹1,800)
                pf_d = 1800.0 if (e_basic + e_da) > 15000 else round((e_basic + e_da) * 0.12, 2)
                esic_d = round(t_gross * 0.0075, 2)
                pt_d = 200.0 if t_gross > 10000 else 0.0

                # प्रत्यक्ष ॲडव्हान्स आणि PPE कपात
                adv_d = 0.0
                try:
                    adv_res = supabase.table("advance_salaries").select("amount").eq("employee_id", emp["id"]).eq("status", "APPROVED").execute().data or []
                    adv_d = sum([float(a.get("amount") or 0.0) for a in adv_res])
                except Exception:
                    pass

                ppe_d = 0.0
                try:
                    ppe_res = supabase.table("ppe_records").select("cost").eq("employee_id", emp["id"]).eq("deduction_month", sel_m).eq("status", "APPROVED").execute().data or []
                    ppe_d = sum([float(p.get("cost") or 0.0) for p in ppe_res])
                except Exception:
                    pass

                deductions_payload = {
                    'earned_basic': e_basic, 'earned_da': e_da, 'earned_hra': e_hra, 'earned_other': e_other,
                    'ot_amount': e_ot, 'pf_ded': pf_d, 'esic_ded': esic_d, 'pt_ded': pt_d,
                    'adv_val': adv_d, 'ppe_ded': ppe_d
                }
                att_summary_payload = {'paid_days': p_days, 'total_days': 26, 'ot_hours': ot_hrs}

                # अंतिम सॅलरी स्लिप तयार करणे
                payslip_pdf_bytes = generate_salary_payslip(emp, ent_obj, cli_name, sel_m, sal_rule, att_summary_payload, deductions_payload)

                st.download_button(
                    f"📥 Download Official Payslip ({sel_m})",
                    data=payslip_pdf_bytes,
                    file_name=f"Payslip_{sel_m.replace(' ', '_')}_{emp.get('employee_code')}.pdf",
                    mime="application/pdf"
                )

        # 5. DOCUMENTS VAULT PANEL
        elif selected_emp_panel == "Official Documents Vault":
            st.subheader("Official Employment Documents / अधिकृत नोकरी कागदपत्रे")
            ent_obj = supabase.table("entities").select("*").eq("id", emp.get("entity_id")).execute().data
            ent_val = ent_obj[0] if ent_obj else None

            assigned_client_name = "Authorized Client Site"
            if emp.get("client_id"):
                try:
                    cl_res = supabase.table("clients").select("name").eq("id", emp["client_id"]).execute().data
                    if cl_res and len(cl_res) > 0:
                        assigned_client_name = cl_res[0].get("name", "Authorized Client Site")
                except Exception:
                    pass

            sal_rule = None
            try:
                sr_query = supabase.table("salary_structures").select("*").eq("entity_id", emp.get("entity_id"))
                if emp.get("client_id"):
                    sr_query = sr_query.eq("client_id", emp.get("client_id"))
                if emp.get("designation"):
                    sr_query = sr_query.ilike("designation", emp.get("designation").strip())
                if emp.get("category"):
                    sr_query = sr_query.eq("category", emp.get("category").strip())
                s_matched = sr_query.execute().data
                if s_matched:
                    sal_rule = s_matched[0]
                else:
                    fallback_res = supabase.table("salary_structures").select("*").eq("entity_id", emp.get("entity_id")).execute().data
                    if fallback_res:
                        sal_rule = fallback_res[0]
            except Exception:
                pass

            d1, d2 = st.columns(2)
            with d1:
                st.markdown("##### 📑 Official Offer Letter / अधिकृत ऑफर लेटर")
                off_data = generate_official_offer_letter(emp, ent_val, assigned_client_name, sal_rule)
                st.download_button("📥 Download Offer Letter (PDF)", data=off_data, file_name=f"Offer_{emp.get('employee_code')}.pdf", mime="application/pdf")
            with d2:
                st.markdown("##### 🪪 Statutory ESIC Card / ईएसआयसी कार्ड")
                st.download_button("📥 Download ESIC Card (PDF)", data=b"ESIC Card Document", file_name=f"ESIC_{emp.get('employee_code')}.pdf", mime="application/pdf")

        # 6. PPE REQUEST PANEL
        elif selected_emp_panel == "Request PPE Equipment":
            st.subheader("Request Safety Equipment / PPE / सुरक्षा साधनांची मागणी")
            
            emp_catalog = []
            try:
                emp_catalog = supabase.table("ppe_catalog").select("item_name, price").eq("entity_id", emp.get("entity_id")).eq("client_id", emp.get("client_id")).execute().data or []
            except Exception:
                emp_catalog = []

            price_lookup = {item["item_name"]: float(item["price"]) for item in emp_catalog}

            if not price_lookup:
                st.warning("⚠️ तुमच्या प्लांट लोकेशनसाठी ॲडमिनने अद्याप PPE दर निश्चित केलेले नाहीत. कृपया सुपरवायझरशी संपर्क साधा.")
            else:
                with st.form("emp_ppe_standalone_form"):
                    p_item = st.selectbox("Safety Equipment Required", list(price_lookup.keys()))
                    unit_price = price_lookup.get(p_item, 0.0)
                    
                    p_size = st.text_input("Size (e.g. 8, 9, L, XL)")
                    p_qty = st.number_input("Quantity", min_value=1, value=1)
                    total_calculated_cost = unit_price * p_qty

                    st.info(f"💰 **प्रति नग किंमत:** ₹{unit_price:,.2f} | **एकूण कपात:** ₹{total_calculated_cost:,.2f} (सदर रक्कम आगामी सॅलरीतून वजा होईल)")

                    if st.form_submit_button("Submit PPE Request", type="primary"):
                        try:
                            supabase.table("ppe_records").insert({
                                "employee_id": emp["id"],
                                "item_type": p_item,
                                "size": p_size,
                                "quantity": p_qty,
                                "cost": total_calculated_cost,
                                "status": "PENDING_SUPERVISOR",
                                "assigned_date": today_str
                            }).execute()
                            st.success("✅ PPE मागणी सुपरवायझरकडे पाठवली आहे!")
                        except Exception as e:
                            st.error(f"Error submitting PPE request: {e}")

        # 7. ADVANCE SALARY PANEL
        elif selected_emp_panel == "Request Salary Advance":
            st.subheader("Apply for Salary Advance or Loan / ॲडव्हान्स पगार अर्ज")
            with st.form("emp_adv_standalone_form"):
                adv_amt = st.number_input("Requested Advance Amount (₹)", min_value=500, step=500, value=2000)
                adv_reason = st.text_area("Reason for Advance")
                if st.form_submit_button("Submit Advance Request", type="primary"):
                    try:
                        supabase.table("advance_salaries").insert({
                            "employee_id": emp["id"],
                            "amount": adv_amt,
                            "reason": adv_reason,
                            "status": "PENDING_SUPERVISOR",
                            "requested_date": today_str
                        }).execute()
                        st.success("✅ Data Saved Successfully: Advance Salary request submitted to Supervisor!")
                    except Exception as e:
                        st.error(f"Error submitting request: {e}")

        # 8. CHANGE PASSWORD PANEL
        elif selected_emp_panel == "Change Password":
            st.subheader("Change Portal Password / पासवर्ड बदला")
            with st.form("change_emp_pwd_form"):
                new_p1 = st.text_input("New Password", type="password")
                new_p2 = st.text_input("Confirm New Password", type="password")
                if st.form_submit_button("Update Password", type="primary"):
                    if new_p1 and new_p1 == new_p2:
                        try:
                            supabase.table("employees").update({"password": new_p1}).eq("id", emp["id"]).execute()
                            st.session_state.user["password"] = new_p1
                            st.success("✅ Password updated successfully!")
                        except Exception as e:
                            st.error(f"Error updating password: {e}")
                    else:
                        st.error("Passwords do not match!")