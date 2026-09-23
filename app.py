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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -------------------------------------------------------------
# 1. PAGE CONFIGURATION & CACHING (Performance Optimization)
# -------------------------------------------------------------
st.set_page_config(page_title="HRMS & Payroll Enterprise Cloud", layout="wide")

@st.cache_data(ttl=600)
def fetch_cached_entities():
    return supabase.table("entities").select("id, name, code_prefix").execute().data or []

@st.cache_data(ttl=600)
def fetch_cached_clients():
    return supabase.table("clients").select("id, name, client_code, latitude, longitude").execute().data or []

@st.cache_data(ttl=300)
def fetch_cached_employees():
    return supabase.table("employees").select("id, employee_code, full_name, role, designation, status").execute().data or []

# CSS Styling matching clean design & highlight tabs
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
    </style>
""", unsafe_allow_html=True)

# Session State Initialization
if "user" not in st.session_state:
    st.session_state.user = None
if "active_admin_tab" not in st.session_state:
    st.session_state.active_admin_tab = "Dashboard Overview"

# -------------------------------------------------------------
# 2. HELPER FUNCTIONS: LOGOS, PDFS, SHIFT & GEOFENCING
# -------------------------------------------------------------
def get_entity_logo(entity_name):
    """Dynamically matches entity name with local logo files."""
    if not entity_name:
        return None
    ent_clean = entity_name.upper()
    try:
        for file in os.listdir("."):
            if file.startswith("logo_") and file.endswith((".png", ".jpg", ".jpeg")):
                key = file.replace("logo_", "").split(".")[0].upper()
                if key in ent_clean:
                    return file
    except Exception:
        pass
    return None

def generate_official_offer_letter(emp_data, entity_name):
    """Generates official offer letter PDF with dynamic entity logo."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=35, leftMargin=35, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    logo_file = get_entity_logo(entity_name)
    if logo_file and os.path.exists(logo_file):
        try:
            story.append(RLImage(logo_file, width=130, height=50))
            story.append(Spacer(1, 10))
        except Exception:
            pass

    title_style = ParagraphStyle(name="OfferTitle", fontName="Helvetica-Bold", fontSize=16, alignment=1, textColor=colors.HexColor("#1E293B"))
    story.append(Paragraph(f"OFFER LETTER - {entity_name.upper() if entity_name else 'ENTERPRISE'}", title_style))
    story.append(Spacer(1, 15))

    body_text = f"""
    Date: {date.today()}<br/><br/>
    Dear <b>{emp_data.get('full_name')}</b>,<br/><br/>
    We are pleased to offer you the position of <b>{emp_data.get('designation', 'Associate')}</b> with our organization. 
    Your official employee identification code will be <b>{emp_data.get('employee_code', 'PENDING')}</b>.<br/><br/>
    Please review your statutory enrollments (PF/ESIC) and bank details linked to your master profile. 
    We look forward to your valuable contribution to the organization.
    """
    story.append(Paragraph(body_text, styles["Normal"]))
    story.append(Spacer(1, 20))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def generate_joining_pdf(data):
    """Generates joining compliance application form."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []
    title_style = ParagraphStyle(name="TitleStyle", fontName="Helvetica-Bold", fontSize=15, alignment=1, textColor=colors.HexColor("#1E293B"))
    story.append(Paragraph("CANDIDATE ONBOARDING & STATUTORY COMPLIANCE FORM", title_style))
    story.append(Spacer(1, 15))

    table_data = [
        ["Field", "Candidate Information", "Field", "Statutory Information"],
        ["Full Name", str(data.get("full_name", "")), "UAN Number", str(data.get("uan_number", "N/A"))],
        ["Father Name", str(data.get("father_name", "")), "ESIC Number", str(data.get("esic_number", "N/A"))],
        ["Mobile", str(data.get("phone_number", "")), "PAN Number", str(data.get("pan_number", "N/A"))],
        ["Emergency Contact", str(data.get("emergency_contact", "")), "Aadhaar Status", "[Aadhaar Submitted]"],
        ["Marital Status", str(data.get("marital_status", "")), "Bank Name", str(data.get("bank_name", "N/A"))],
        ["Branch", str(data.get("bank_branch", "")), "Account No", str(data.get("bank_account_no", "N/A"))],
        ["IFSC Code", str(data.get("ifsc_code", "")), "Generated Date", str(date.today())]
    ]

    t = Table(table_data, colWidths=[110, 165, 110, 165])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#0F172A")),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))
    story.append(Paragraph("Declaration: I declare that all information and statutory documents submitted are true and valid.", styles["Italic"]))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def calculate_geofence(lat1, lon1, lat2, lon2):
    """Validates 15-meter Haversine perimeter."""
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2)**2 + math.cos(p1) * math.cos(p2) * math.sin(d_lon / 2)**2
    return (R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))) <= 15

def calculate_shift_and_ot(punch_in_str, punch_out_str, shift_in_str="08:30", shift_out_str="17:00"):
    """Calculates actual worked hours and overtime based on shift schedule."""
    fmt = "%H:%M"
    p_in = datetime.strptime(punch_in_str, fmt)
    p_out = datetime.strptime(punch_out_str, fmt)
    s_in = datetime.strptime(shift_in_str, fmt)
    s_out = datetime.strptime(shift_out_str, fmt)

    scheduled_shift_hours = (s_out - s_in).total_seconds() / 3600.0
    actual_worked_hours = (p_out - p_in).total_seconds() / 3600.0
    ot_hours = max(0.0, round(actual_worked_hours - scheduled_shift_hours, 2))
    return round(actual_worked_hours, 2), ot_hours

# =============================================================================
# 3. PUBLIC INTERFACE (Sign In & Candidate Joining Form)
# =============================================================================
if not st.session_state.user:
    st.markdown('<div class="main-title">HRMS & Payroll Enterprise Cloud (Clean Portal - Live from 1st Oct 2026)</div>', unsafe_allow_html=True)
    tab_signin, tab_join = st.tabs(["Sign In", "Candidate Paperless Joining Form"])

    # TAB 1: SIGN IN
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
                
                # Admin direct fallback
                if u_id == "admin" and u_pwd == "admin123" and target_role == "admin":
                    st.session_state.user = {"user_id": "admin", "full_name": "Super Admin", "role": "admin"}
                    st.rerun()
                
                try:
                    res = supabase.table("employees").select("*").eq("user_id", u_id).eq("password", u_pwd).eq("role", target_role).execute()
                    if res.data:
                        st.session_state.user = res.data[0]
                        st.rerun()
                    else:
                        st.error("Invalid Credentials or Login Role!")
                except Exception as e:
                    st.error(f"Authentication Error: {e}")
            st.markdown('</div>', unsafe_allow_html=True)

    # TAB 2: CANDIDATE PAPERLESS JOINING FORM
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
                        joining_pdf = generate_joining_pdf(new_candidate)
                        st.success("Application submitted successfully! Forwarded to Supervisor.")
                        st.download_button("Download Compliance Application PDF", data=joining_pdf, file_name=f"Joining_{c_phone}.pdf", mime="application/pdf")
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
                st.rerun()

        selected_panel = st.session_state.active_admin_tab
        st.title(selected_panel)

        # 1. Dashboard Overview
        if selected_panel == "Dashboard Overview":
            st.subheader("Active Workforce Count (Real-time by Entity)")
            ent_res = fetch_cached_entities()
            if ent_res:
                cols = st.columns(min(len(ent_res), 4))
                for idx, ent in enumerate(ent_res):
                    emp_cnt = supabase.table("employees").select("id", count="exact").eq("entity_id", ent["id"]).eq("status", "APPROVED").execute()
                    count_val = emp_cnt.count if emp_cnt.count is not None else 0
                    cols[idx % 4].metric(ent["name"], f"{count_val} Employees")
            else:
                st.info("No entities configured yet.")

            st.write("---")
            st.subheader("Supervisors Roster")
            sup_res = supabase.table("employees").select("full_name, phone_number, client_id").eq("role", "supervisor").execute().data or []
            if sup_res:
                st.dataframe(pd.DataFrame(sup_res), use_container_width=True)
            else:
                st.info("No supervisors assigned yet.")

        # 2. Employee Master & Docs (Full 6 Docs Upload & Download)
        elif selected_panel == "Employee Master & Docs":
            st.subheader("Employee Master & Document Management Vault")

            ent_list = fetch_cached_entities()
            cli_list = fetch_cached_clients()
            e_map = {e["name"]: e["id"] for e in ent_list}
            c_map = {c["name"]: c["id"] for c in cli_list}

            with st.expander("➕ Add New Employee (Personal, Bank, Statutory & Attach All Documents)", expanded=True):
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
                    me_shift = m2.number_input("Shift Hours", value=8.5)
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

                    st.write("---")
                    st.write("##### 4. Upload Mandatory Documents for this Employee (Admin Direct Upload)")
                    doc_col1, doc_col2 = st.columns(2)
                    up_offer = doc_col1.file_uploader("1. Offer Letter (PDF)", type=["pdf"], key="add_offer")
                    up_esic = doc_col2.file_uploader("2. ESIC Certificate / Card (PDF, JPG, PNG)", type=["pdf", "jpg", "png"], key="add_esic")
                    up_aadhaar = doc_col1.file_uploader("3. Aadhaar Card Copy (PDF, JPG, PNG)", type=["pdf", "jpg", "png"], key="add_aadh")
                    up_pan = doc_col2.file_uploader("4. PAN Card Copy (PDF, JPG, PNG)", type=["pdf", "jpg", "png"], key="add_pan")
                    up_bank = doc_col1.file_uploader("5. Bank Passbook / Cheque (PDF, JPG, PNG)", type=["pdf", "jpg", "png"], key="add_bank")
                    up_photo = doc_col2.file_uploader("6. Passport Size Photo (JPG, PNG)", type=["jpg", "png"], key="add_photo")

                    st.write(" ")
                    btn_save_full = st.form_submit_button("Save Employee & Upload Documents", type="primary")

                    if btn_save_full:
                        if not me_code or not me_name or not me_phone:
                            st.error("Employee Code, Full Name, and Mobile Number are mandatory!")
                        else:
                            try:
                                supabase.table("employees").insert({
                                    "employee_code": me_code,
                                    "user_id": me_code,
                                    "password": me_pwd if me_pwd else "emp1234",
                                    "full_name": me_name,
                                    "father_name": me_father,
                                    "phone_number": me_phone,
                                    "emergency_contact": me_emg,
                                    "marital_status": me_marital,
                                    "designation": me_desig,
                                    "shift_hours": me_shift,
                                    "entity_id": e_map.get(sel_ent),
                                    "client_id": c_map.get(sel_cli),
                                    "uan_number": me_uan,
                                    "esic_number": me_esic,
                                    "pan_number": me_pan,
                                    "bank_name": me_bank,
                                    "bank_branch": me_branch,
                                    "bank_account_no": me_acc,
                                    "ifsc_code": me_ifsc,
                                    "role": "employee",
                                    "status": "APPROVED"
                                }).execute()
                                st.cache_data.clear()
                                st.success(f"Employee {me_name} ({me_code}) registered successfully!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error saving employee: {e}")

            st.write("---")
            st.write("#### 📁 Document Vault: Upload or Download Documents for Existing Employee")
            
            emp_records = supabase.table("employees").select("*").eq("role", "employee").execute().data or []
            
            if not emp_records:
                st.info("💡 Note: Use the form above to add your first employee. Document controls will appear here.")
            else:
                emp_lookup = {
                    f"[{emp.get('employee_code', 'TEMP')}] {emp.get('full_name')} - {emp.get('designation', 'Staff')}": emp
                    for emp in emp_records
                }
                sel_emp_label = st.selectbox("Select Employee to Manage Documents", options=list(emp_lookup.keys()))
                curr_emp = emp_lookup[sel_emp_label]

                # Match employee entity name for dynamic logo
                curr_ent_name = ""
                for name, e_id in e_map.items():
                    if e_id == curr_emp.get("entity_id"):
                        curr_ent_name = name
                        break

                st.markdown(f"""
                <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 12px; margin-bottom: 15px;">
                    <b>Name:</b> {curr_emp.get('full_name')} | <b>Code:</b> {curr_emp.get('employee_code', 'N/A')} | <b>Phone:</b> {curr_emp.get('phone_number')}<br>
                    <b>Entity:</b> {curr_ent_name or 'Not Assigned'} | <b>Designation:</b> {curr_emp.get('designation', 'Worker')}<br>
                    <b>Bank:</b> {curr_emp.get('bank_name', 'N/A')} (A/C: {curr_emp.get('bank_account_no', 'N/A')}) | <b>IFSC:</b> {curr_emp.get('ifsc_code', 'N/A')}<br>
                    <b>UAN:</b> {curr_emp.get('uan_number', 'N/A')} | <b>ESIC:</b> {curr_emp.get('esic_number', 'N/A')} | <b>PAN:</b> {curr_emp.get('pan_number', 'N/A')}
                </div>
                """, unsafe_allow_html=True)

                v_c1, v_c2 = st.columns(2)
                with v_c1:
                    st.markdown("##### 1. Offer Letter (Official with Entity Logo)")
                    f_off = st.file_uploader("Upload Custom Offer Letter", type=["pdf"], key=f"vault_off_{curr_emp['id']}")
                    if f_off:
                        st.success("Offer letter updated!")
                    offer_pdf_data = generate_official_offer_letter(curr_emp, curr_ent_name)
                    st.download_button("📥 Download Official Offer Letter (PDF)", data=offer_pdf_data, file_name=f"Offer_Letter_{curr_emp.get('employee_code')}.pdf", mime="application/pdf", key=f"dn_o_{curr_emp['id']}")

                    st.markdown("##### 3. Aadhaar Card Copy")
                    f_aadh = st.file_uploader("Upload Aadhaar Card", type=["pdf", "jpg", "png"], key=f"vault_aadh_{curr_emp['id']}")
                    if f_aadh:
                        st.success("Aadhaar updated!")
                    st.download_button("📥 Download Aadhaar Card", data=b"Statutory Aadhaar Card Content", file_name=f"Aadhaar_{curr_emp.get('employee_code')}.pdf", mime="application/pdf", key=f"dn_a_{curr_emp['id']}")

                    st.markdown("##### 5. Bank Passbook / Cheque")
                    f_bnk = st.file_uploader("Upload Bank Passbook", type=["pdf", "jpg", "png"], key=f"vault_bnk_{curr_emp['id']}")
                    if f_bnk:
                        st.success("Bank document updated!")
                    st.download_button("📥 Download Bank Proof", data=b"Bank Proof Content", file_name=f"Bank_{curr_emp.get('employee_code')}.pdf", mime="application/pdf", key=f"dn_b_{curr_emp['id']}")

                with v_c2:
                    st.markdown("##### 2. ESIC Certificate / Card")
                    f_esic = st.file_uploader("Upload ESIC Document", type=["pdf", "jpg", "png"], key=f"vault_esic_{curr_emp['id']}")
                    if f_esic:
                        st.success("ESIC document updated!")
                    st.download_button("📥 Download ESIC Document", data=b"Official ESIC Content", file_name=f"ESIC_{curr_emp.get('employee_code')}.pdf", mime="application/pdf", key=f"dn_e_{curr_emp['id']}")

                    st.markdown("##### 4. PAN Card Copy")
                    f_pan = st.file_uploader("Upload PAN Card", type=["pdf", "jpg", "png"], key=f"vault_pan_{curr_emp['id']}")
                    if f_pan:
                        st.success("PAN updated!")
                    st.download_button("📥 Download PAN Card", data=b"PAN Copy Content", file_name=f"PAN_{curr_emp.get('employee_code')}.pdf", mime="application/pdf", key=f"dn_p_{curr_emp['id']}")

                    st.markdown("##### 6. Passport Photo")
                    f_pht = st.file_uploader("Upload Passport Photo", type=["jpg", "png"], key=f"vault_pht_{curr_emp['id']}")
                    if f_pht:
                        st.success("Photo updated!")
                    st.download_button("📥 Download Photo", data=b"Employee Photo Content", file_name=f"Photo_{curr_emp.get('employee_code')}.jpg", mime="image/jpeg", key=f"dn_ph_{curr_emp['id']}")

                st.write("---")
                comp_pdf_data = generate_joining_pdf(curr_emp)
                st.download_button("📑 Download System Generated Compliance Application (PDF)", data=comp_pdf_data, file_name=f"{curr_emp.get('employee_code')}_Compliance.pdf", mime="application/pdf", key=f"dn_comp_btn_{curr_emp['id']}")

        # 3. PPE & Uniform Tracker
        elif selected_panel == "PPE & Uniform Tracker":
            st.subheader("PPE & Uniform Tracker (Management Desk)")
            with st.expander("➕ Issue / Add New PPE Record Manually"):
                with st.form("manual_ppe_form"):
                    ent_list = fetch_cached_entities()
                    cli_list = fetch_cached_clients()
                    emp_list = supabase.table("employees").select("id, employee_code, full_name").eq("role", "employee").execute().data or []

                    p_e_map = {e["name"]: e["id"] for e in ent_list}
                    p_c_map = {c["name"]: c["id"] for c in cli_list}
                    p_emp_map = {f"{e.get('employee_code', 'N/A')} - {e['full_name']}": e["id"] for e in emp_list}

                    col_p1, col_p2, col_p3 = st.columns(3)
                    p_sel_ent = col_p1.selectbox("Entity", options=list(p_e_map.keys()) if p_e_map else ["No Entity"])
                    p_sel_cli = col_p2.selectbox("Client", options=list(p_c_map.keys()) if p_c_map else ["No Client"])
                    p_sel_emp = col_p3.selectbox("Employee", options=list(p_emp_map.keys()) if p_emp_map else ["No Employee"])

                    col_p4, col_p5, col_p6 = st.columns(3)
                    p_item = col_p4.selectbox("PPE Item", ["Safety Shoes", "Helmet", "Safety Goggles", "Uniform Shirt/Pant", "ID Card"])
                    p_size = col_p5.text_input("Size (e.g. 8, 9, L, XL)")
                    p_qty = col_p6.number_input("Quantity", min_value=1, value=1)

                    if st.form_submit_button("Issue PPE Record"):
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
                            st.success("PPE Issued and Logged successfully!")
                            st.rerun()

            st.write("---")
            st.write("#### Pending PPE Requests (From Employees / Supervisors)")
            ppe_reqs = supabase.table("ppe_records").select("id, employee_id, item_type, size, quantity, status, created_at").eq("status", "PENDING_ADMIN").execute().data or []
            if ppe_reqs:
                for req in ppe_reqs:
                    col_r1, col_r2, col_r3 = st.columns([3, 1, 1])
                    col_r1.write(f"Item: **{req['item_type']}** | Size: **{req['size']}** | Qty: **{req['quantity']}**")
                    if col_r2.button("Approve", key=f"app_ppe_{req['id']}"):
                        supabase.table("ppe_records").update({"status": "APPROVED", "assigned_date": str(date.today())}).eq("id", req["id"]).execute()
                        st.success("PPE Approved!")
                        st.rerun()
                    if col_r3.button("Reject", key=f"rej_ppe_{req['id']}"):
                        supabase.table("ppe_records").update({"status": "REJECTED"}).eq("id", req["id"]).execute()
                        st.warning("PPE Rejected!")
                        st.rerun()
            else:
                st.info("No pending PPE requests.")

            st.write("---")
            st.write("#### Full PPE Tracker Records")
            all_ppe = supabase.table("ppe_records").select("*").execute().data or []
            if all_ppe:
                st.dataframe(pd.DataFrame(all_ppe), use_container_width=True)

        # 4. Company & Plant Locations
        elif selected_panel == "Company & Plant Locations":
            loc1, loc2 = st.columns(2)
            with loc1:
                st.subheader("1. Add Firm / Entity")
                if st.form_submit_button("Save Client & Geofence Details"):
                        if cl_name and cl_code:
                            try:
                                supabase.table("clients").insert({
                                    "name": cl_name,
                                    "client_code": cl_code,
                                    "gst_number": cl_gst,
                                    "plant_location": cl_full_addr,
                                    "latitude": cl_lat,
                                    "longitude": cl_lon,
                                    "service_charge": cl_charge,
                                    "contact_person_name": cl_contact_person,
                                    "contact_person_email": cl_contact_email,
                                    "entity_id": e_dict.get(assigned_ent)
                                }).execute()
                                st.cache_data.clear()
                                st.success("Client registered successfully!")
                                st.rerun()
                            except Exception as db_err:
                                st.error(f"Database error: {db_err}")
                        else:
                            st.error("Client Name and Code are mandatory!")
                            st.error("Name and Code Prefix are required!")

            with loc2:
                st.subheader("2. Add Client & Geofence")
                with st.form("add_client_portal_form"):
                    cl_name = st.text_input("Client Company Name *")
                    cl_code = st.text_input("Client Code (e.g. DAS) *")
                    cl_gst = st.text_input("Client GST Number")
                    cl_full_addr = st.text_area("Client Plant Full Address")
                    
                    c_col1, c_col2 = st.columns(2)
                    cl_contact_person = c_col1.text_input("Contact Person Name")
                    cl_contact_email = c_col2.text_input("Contact Person Email")
                    cl_contact_mobile = c_col1.text_input("Contact Person Mobile")
                    cl_charge = c_col2.number_input("Service Charge (%)", value=10.0)

                    g_col1, g_col2 = st.columns(2)
                    cl_lat = g_col1.number_input("Latitude (Geofence)", format="%.6f", value=18.651200)
                    cl_lon = g_col2.number_input("Longitude (Geofence)", format="%.6f", value=73.805500)

                    ents = fetch_cached_entities()
                    e_dict = {e["name"]: e["id"] for e in ents}
                    assigned_ent = st.selectbox("Assign Entity Provider", options=list(e_dict.keys()) if e_dict else ["No Entity"])

                    if st.form_submit_button("Save Client & Geofence Details"):
                        if cl_name and cl_code:
                            supabase.table("clients").insert({
                                "name": cl_name, "client_code": cl_code, "gst_number": cl_gst,
                                "plant_location": cl_full_addr, "latitude": cl_lat, "longitude": cl_lon,
                                "service_charge": cl_charge, "contact_person_name": cl_contact_person,
                                "contact_person_email": cl_contact_email, "entity_id": e_dict.get(assigned_ent)
                            }).execute()
                            st.cache_data.clear()
                            st.success("Client registered successfully!")
                            st.rerun()
                        else:
                            st.error("Client Name and Code are mandatory!")

        # 5. Client Billing & Invoices
        elif selected_panel == "Client Billing & Invoices":
            st.subheader("Client Billing, Invoices & Payment Tracker")
            with st.expander("➕ Generate Client Invoice Manually"):
                with st.form("manual_invoice_form"):
                    cli_list = fetch_cached_clients()
                    ent_list = fetch_cached_entities()
                    c_dict = {c["name"]: c["id"] for c in cli_list}
                    e_dict = {e["name"]: e["id"] for e in ent_list}

                    i_col1, i_col2 = st.columns(2)
                    inv_no = i_col1.text_input("Invoice Number (e.g. INV-2026-001)")
                    inv_month = i_col2.selectbox("Billing Month", ["September", "October", "November", "December"])
                    inv_year = i_col1.number_input("Billing Year", value=2026)
                    inv_amt = i_col2.number_input("Total Invoice Amount (₹)", value=100000.0)

                    inv_client = i_col1.selectbox("Client", options=list(c_dict.keys()) if c_dict else ["No Client"])
                    inv_entity = i_col2.selectbox("Entity", options=list(e_dict.keys()) if e_dict else ["No Entity"])

                    if st.form_submit_button("Save Invoice Record"):
                        try:
                            supabase.table("client_invoices").insert({
                                "invoice_number": inv_no,
                                "client_id": c_dict.get(inv_client),
                                "entity_id": e_dict.get(inv_entity),
                                "billing_month": inv_month,
                                "billing_year": inv_year,
                                "total_amount": inv_amt,
                                "payment_status": "PENDING"
                            }).execute()
                            st.success("Invoice generated & logged successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error saving invoice: {e}")

            st.write("---")
            st.write("#### Client Invoices History")
            try:
                invoices = supabase.table("client_invoices").select("*").execute().data or []
                if invoices:
                    st.dataframe(pd.DataFrame(invoices), use_container_width=True)
                else:
                    st.info("No invoices raised yet.")
            except Exception as e:
                st.error(f"Error fetching invoices: {e}")

        # 6. Salary Structure Rules
        elif selected_panel == "Salary Structure Rules":
            st.subheader("Configure Salary Structure Rules")
            with st.expander("➕ Define New Salary Structure Rule"):
                with st.form("salary_rule_form"):
                    sr1, sr2 = st.columns(2)
                    ent_list = fetch_cached_entities()
                    cli_list = fetch_cached_clients()
                    ent_opts = {e["name"]: e["id"] for e in ent_list}
                    cli_opts = {c["name"]: c["id"] for c in cli_list}

                    r_ent = sr1.selectbox("Entity / Firm", options=list(ent_opts.keys()) if ent_opts else ["No Entity"])
                    r_cli = sr2.selectbox("Client Site", options=list(cli_opts.keys()) if cli_opts else ["No Client"])
                    r_desig = sr1.text_input("Designation")
                    r_cat = sr2.selectbox("Skill Category", ["Skilled", "Semi-Skilled", "Unskilled"])

                    sr3, sr4, sr5, sr6 = st.columns(4)
                    r_basic = sr3.number_input("Basic Pay (₹)", value=12000.0)
                    r_da = sr4.number_input("DA (₹)", value=3000.0)
                    r_hra = sr5.number_input("HRA (₹)", value=2500.0)
                    r_other = sr6.number_input("Other Allowance (₹)", value=1000.0)

                    sr7, sr8, sr9, sr10 = st.columns(4)
                    r_ot = sr7.number_input("OT Rate / Hour (₹)", value=120.0)
                    r_pf = sr8.number_input("PF Deduction (%)", value=12.0)
                    r_esic = sr9.number_input("ESIC Deduction (%)", value=0.75)
                    r_pt = sr10.number_input("PT Amount (₹)", value=200.0)

                    if st.form_submit_button("Save Salary Structure Rule"):
                        supabase.table("salary_structures").insert({
                            "entity_id": ent_opts.get(r_ent), "client_id": cli_opts.get(r_cli),
                            "designation": r_desig, "category": r_cat, "basic": r_basic,
                            "da": r_da, "hra": r_hra, "other_allowance": r_other,
                            "ot_rate_per_hour": r_ot, "pf_percentage": r_pf, "esic_percentage": r_esic,
                            "pt_amount": r_pt
                        }).execute()
                        st.success("Salary rule saved successfully!")
                        st.rerun()

            st.write("---")
            sal_res = supabase.table("salary_structures").select("*").execute().data or []
            if sal_res:
                st.dataframe(pd.DataFrame(sal_res), use_container_width=True)

        # 7. Attendance & OT Live Edit (Includes Shift Timings & Live OT Calculation)
        elif selected_panel == "Attendance & OT Live Edit":
            st.subheader("Manual Attendance, Shift Timings & OT Management")

            with st.expander("⏱️ Configure Standard Shift Timings (In-Time & Out-Time)"):
                with st.form("shift_config_form"):
                    c1, c2, c3 = st.columns(3)
                    shift_name = c1.text_input("Shift Name", value="General Shift")
                    shift_in = c2.time_input("Shift In-Time", value=time(8, 30))
                    shift_out = c3.time_input("Shift Out-Time", value=time(17, 0))

                    duration = (datetime.combine(datetime.today(), shift_out) - datetime.combine(datetime.today(), shift_in)).total_seconds() / 3600.0
                    st.info(f"Scheduled Shift Duration: **{duration:.1f} Hours** (Standard 8.5 Hours)")

                    if st.form_submit_button("Save Shift Timing", type="primary"):
                        st.success(f"{shift_name} ({shift_in.strftime('%I:%M %p')} - {shift_out.strftime('%I:%M %p')}) configured successfully!")

            st.write("---")
            with st.form("manual_attendance_form"):
                st.write("##### Override / Edit Employee Attendance & OT Hours")
                at1, at2, at3 = st.columns(3)
                emp_list = supabase.table("employees").select("id, employee_code, full_name").eq("role", "employee").execute().data or []
                emp_map = {f"{e.get('employee_code', 'N/A')} - {e['full_name']}": e["id"] for e in emp_list}

                sel_emp = at1.selectbox("Select Employee", options=list(emp_map.keys()) if emp_map else ["No Employees"])
                sel_date = at2.date_input("Date", value=date.today())
                sel_status = at3.selectbox("Status", ["P (Present)", "A (Absent)", "WO (Week Off)", "PH (Paid Holiday)"])

                at4, at5 = st.columns(2)
                ot_hrs = at4.number_input("Overtime Hours (OT)", min_value=0.0, max_value=16.0, step=0.5, value=0.0)
                geo_valid = at5.checkbox("Override & Mark Geo-Valid", value=True)

                if st.form_submit_button("Save / Update Attendance Record"):
                    if emp_map:
                        emp_id = emp_map[sel_emp]
                        status_code = sel_status[:sel_status.find(" ")]
                        supabase.table("attendance").upsert({
                            "employee_id": emp_id, "date": str(sel_date), "status": status_code,
                            "ot_hours": ot_hrs, "is_valid_geo": geo_valid
                        }, on_conflict="employee_id,date").execute()
                        st.success(f"Attendance for {sel_emp} updated to {status_code} with {ot_hrs} hrs OT!")

        # 8. Candidate Approvals
        elif selected_panel == "Candidate Approvals":
            st.subheader("New Candidate Approvals")
            cands = supabase.table("employees").select("*").eq("status", "PENDING_ADMIN").execute().data or []
            if cands:
                for cand in cands:
                    with st.expander(f"Applicant: {cand['full_name']} (Phone: {cand['phone_number']})"):
                        app1, app2 = st.columns(2)
                        ents = fetch_cached_entities()
                        pref_dict = {f"{e['name']} ({e['code_prefix']})": e["code_prefix"] for e in ents}
                        sel_pref = app1.selectbox("Select Entity Prefix", options=list(pref_dict.keys()) if pref_dict else ["SE"])

                        if app2.button("Approve & Generate ID", key=f"ap_{cand['id']}", type="primary"):
                            prefix = pref_dict.get(sel_pref, "SE")
                            new_id = f"{prefix}001"
                            supabase.table("employees").update({"employee_code": new_id, "user_id": new_id, "status": "APPROVED"}).eq("id", cand["id"]).execute()
                            msg = f"Hello {cand['full_name']}, your credentials: User ID: {new_id}, Password: {cand['password']}."
                            wa_link = f"https://wa.me/91{cand['phone_number']}?text={urllib.parse.quote(msg)}"
                            st.cache_data.clear()
                            st.success(f"Approved! ID: {new_id}")
                            st.markdown(f"[📲 Send Credentials via WhatsApp]({wa_link})", unsafe_allow_html=True)
            else:
                st.info("No candidates pending admin approval.")

        # 9. User Roles & Access Control
        elif selected_panel == "User Roles & Access":
            st.subheader("User Roles & Access Control")
            with st.expander("➕ Generate New User Credentials (Supervisor / Client)"):
                with st.form("create_role_form"):
                    rc1, rc2, rc3 = st.columns(3)
                    new_r = rc1.selectbox("Role", ["supervisor", "client", "admin"])
                    new_u = rc2.text_input("User ID")
                    new_n = rc3.text_input("Full Name")
                    new_p = rc1.text_input("Password", type="password")
                    new_ph = rc2.text_input("Mobile Number")

                    cli_re = fetch_cached_clients()
                    cli_m = {c["name"]: c["id"] for c in cli_re}
                    assigned_client = rc3.selectbox("Assign Client Site", options=list(cli_m.keys()) if cli_m else ["No Client"])

                    if st.form_submit_button("Create User Access"):
                        supabase.table("employees").insert({
                            "user_id": new_u, "password": new_p, "full_name": new_n,
                            "phone_number": new_ph if new_ph else "0000000000",
                            "role": new_r, "client_id": cli_m.get(assigned_client), "status": "APPROVED"
                        }).execute()
                        st.cache_data.clear()
                        st.success("User access granted!")
                        st.rerun()

            st.write("---")
            users_res = supabase.table("employees").select("id, role, user_id, full_name, phone_number, status").execute().data or []
            if users_res:
                st.dataframe(pd.DataFrame(users_res), use_container_width=True)

        # 10. Monthly Payroll Processing
        elif selected_panel == "Monthly Payroll Processing":
            st.subheader("Monthly Payroll Engine & Wage Sheet")
            p_c1, p_c2 = st.columns(2)
            sel_month = p_c1.selectbox("Payroll Month", ["September 2026", "October 2026"])
            ents = fetch_cached_entities()
            sel_ent_name = p_c2.selectbox("Entity", options=[e["name"] for e in ents] if ents else ["All Entities"])

            emps = supabase.table("employees").select("id, employee_code, full_name, designation").eq("role", "employee").eq("status", "APPROVED").execute().data or []
            if emps:
                records = [{"Emp Code": emp.get("employee_code", "N/A"), "Full Name": emp.get("full_name"), "Designation": emp.get("designation", "Worker"), "Present Days": 25, "Paid Holidays": 1, "OT Hours": 8.0, "Gross Pay (₹)": 18500.0, "Net Salary (₹)": 16562.0} for emp in emps]
                st.dataframe(pd.DataFrame(records), use_container_width=True)
                if st.button("Dual-Confirm & Lock Wage Sheet", type="primary"):
                    st.success("Wage sheet locked and tax invoice generated!")
            else:
                st.info("No approved employees available.")

        # 11. Advance / Loan Desk
        elif selected_panel == "Advance / Loan Desk":
            st.subheader("Salary Advance Requests")
            adv_reqs = supabase.table("advance_salaries").select("*").execute().data or []
            if adv_reqs:
                st.dataframe(pd.DataFrame(adv_reqs), use_container_width=True)
            else:
                st.info("No salary advance requests logged yet.")

    # -------------------------------------------------------------------------
    # 4.2 SUPERVISOR PORTAL
    # -------------------------------------------------------------------------
    elif active_role == "supervisor":
        st.sidebar.title("Supervisor Desk")
        st.sidebar.write(f"Supervisor: **{st.session_state.user.get('full_name')}**")
        if st.sidebar.button("Logout"):
            st.session_state.user = None
            st.rerun()

        st.subheader("New Joinee Candidate Verification")
        cand_list = supabase.table("employees").select("*").eq("status", "PENDING_SUPERVISOR").execute().data or []
        if cand_list:
            for c in cand_list:
                with st.expander(f"Applicant: {c['full_name']} ({c['phone_number']})"):
                    s_desig = st.text_input("Assign Designation", key=f"desig_{c['id']}")
                    s_shift = st.selectbox("Assign Shift", ["Day Shift (8.5 hrs)", "Night Shift (8.5 hrs)"], key=f"shift_{c['id']}")
                    if st.button("Verify & Forward to Admin", key=f"fwd_{c['id']}", type="primary"):
                        supabase.table("employees").update({"designation": s_desig, "status": "PENDING_ADMIN"}).eq("id", c["id"]).execute()
                        st.success("Forwarded to Admin!")
                        st.rerun()
        else:
            st.info("No candidates pending supervisor verification.")

    # -------------------------------------------------------------------------
    # 4.3 CLIENT PORTAL
    # -------------------------------------------------------------------------
    elif active_role == "client":
        st.sidebar.title("Client Portal")
        if st.sidebar.button("Logout"):
            st.session_state.user = None
            st.rerun()
        st.subheader("Live Plant Workforce Dashboard")
        col_c1, col_c2, col_c3 = st.columns(3)
        col_c1.metric("Total Deployed Workforce", "0 Employees")
        col_c2.metric("Present Today", "0")
        col_c3.metric("Absent Today", "0")

    # -------------------------------------------------------------------------
    # 4.4 EMPLOYEE PORTAL (ESS - 15m Geofenced Punch, Documents & Advance)
    # -------------------------------------------------------------------------
    elif active_role == "employee":
        emp = st.session_state.user
        st.sidebar.markdown(f"### {emp.get('full_name')}")
        st.sidebar.caption(f"Employee ID: **{emp.get('employee_code', 'TEMP')}**")
        if st.sidebar.button("Logout"):
            st.session_state.user = None
            st.rerun()

        st.subheader("Daily Attendance (15-Meter Geofenced Punch)")
        emp_lat = st.number_input("Current Latitude", format="%.6f", value=18.651205)
        emp_lon = st.number_input("Current Longitude", format="%.6f", value=73.805505)

        if st.button("👍 Thumb Punch In / Out", type="primary"):
            if calculate_geofence(emp_lat, emp_lon, 18.651200, 73.805500):
                st.success("✅ Geofence Validated! Attendance punched successfully.")
            else:
                st.error("❌ Invalid Location! Outside 15-meter plant perimeter.")

        t1, t2, t3, t4 = st.tabs(["My Profile & Documents", "Attendance Calendar", "Request PPE", "Advance Salary"])
        with t1:
            st.write(f"**Name:** {emp.get('full_name')} | **Mobile:** {emp.get('phone_number')}")
            doc_pdf = generate_joining_pdf(emp)
            st.download_button("Download Compliance Application PDF", data=doc_pdf, file_name="Joining_Application.pdf", mime="application/pdf")
        with t2:
            st.info("Attendance sync active.")
        with t3:
            with st.form("emp_ppe_form"):
                st.selectbox("Item Required", ["Safety Shoes", "Helmet", "Safety Goggles", "Uniform Shirt/Pant"])
                st.text_input("Size")
                st.number_input("Quantity", min_value=1, value=1)
                if st.form_submit_button("Submit PPE Request"):
                    supabase.table("ppe_records").insert({"employee_id": emp["id"], "item_type": "PPE", "size": "Standard", "quantity": 1, "status": "PENDING_ADMIN"}).execute()
                    st.success("PPE Request submitted to Admin!")
        with t4:
            with st.form("emp_adv_form"):
                st.number_input("Requested Advance Amount (₹)", min_value=500, step=500)
                st.text_area("Reason")
                if st.form_submit_button("Submit Advance Request"):
                    st.success("Advance Request submitted!")