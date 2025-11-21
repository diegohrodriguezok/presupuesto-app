import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, timedelta
import plotly.express as px
import plotly.graph_objects as go
import time
from fpdf import FPDF
import base64
import pytz
import uuid

# --- 1. CONFIGURACIÓN GLOBAL ---
st.set_page_config(
    page_title="Area Arqueros ERP", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="logo.png"
)

# --- FUNCIONES DE TIEMPO ARGENTINA (UTC-3) ---
def get_now_ar():
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    return datetime.now(tz)

def get_today_ar():
    return get_now_ar().date()

# --- TRADUCTOR DE DÍAS ---
def traducir_dia(fecha_dt):
    dias = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    return dias[fecha_dt.weekday()]

# --- CSS PREMIUM ---
st.markdown("""
    <style>
        /* Estilos Generales */
        .stApp {
            background-color: #f8f9fa;
        }
        .stButton>button {
            border-radius: 6px;
            height: 40px;
            font-weight: 600;
            border: none;
            background-color: #1f2c56;
            color: white !important;
            transition: all 0.2s;
            width: 100%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stButton>button:hover {
            background-color: #2c3e50;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            transform: translateY(-1px);
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.6rem !important;
            font-weight: 700;
            color: #1f2c56;
        }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; padding-bottom: 10px; }
        .stTabs [data-baseweb="tab"] {
            height: 45px; background-color: #ffffff; color: #555555;
            border-radius: 8px; border: 1px solid #e0e0e0; padding: 0 20px; font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
            background-color: #1f2c56 !important; color: #ffffff !important;
            border: none; box-shadow: 0 4px 6px rgba(31, 44, 86, 0.25);
        }
        .caja-box {
            background-color: #e8f5e9; padding: 20px; border-radius: 10px;
            border-left: 6px solid #2e7d32; margin-bottom: 20px; color: #1b5e20;
        }
        .student-card {
            padding: 15px;
            background-color: white;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
            margin-bottom: 10px;
        }
        .training-card {
            background-color: #f8f9fa;
            padding: 12px;
            border-radius: 6px;
            border-left: 5px solid #1f2c56;
            border: 1px solid #eee;
            margin-bottom: 8px;
        }
        .auto-gen-box {
            background-color: #e3f2fd;
            padding: 15px;
            border-radius: 8px;
            border-left: 5px solid #2196f3;
            margin-bottom: 20px;
            animation: fadeIn 1s;
        }
        .status-vencido { color: #dc3545; font-weight: bold; }
        .status-ok { color: #28a745; font-weight: bold; }
        .status-pending { color: #ffc107; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. GESTOR DE CONEXIÓN ---
@st.cache_resource
def get_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds).open("BaseDatos_ClubArqueros")
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        st.stop()

def get_df(sheet_name):
    try:
        ws = get_client().worksheet(sheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            df.columns = df.columns.str.strip().str.lower()
        return df
    except: return pd.DataFrame()

def save_row(sheet_name, data):
    try: get_client().worksheet(sheet_name).append_row(data)
    except: pass

def save_rows_bulk(sheet_name, data_list):
    try: 
        get_client().worksheet(sheet_name).append_rows(data_list)
        return True
    except: return False

def generate_id():
    return int(f"{int(time.time())}{uuid.uuid4().int % 1000}")

def log_action(id_ref, accion, detalle, user):
    try:
        row = [str(get_now_ar()), user, str(id_ref), accion, detalle]
        save_row("logs", row)
    except: pass

# --- FUNCIONES DE CONFIGURACIÓN ---
def get_config_value(key, default_val):
    try:
        df = get_df("config")
        if not df.empty and 'clave' in df.columns:
            res = df[df['clave'] == key]
            if not res.empty: return int(res.iloc[0]['valor'])
    except: pass
    return default_val

def set_config_value(key, value):
    sh = get_client()
    try: ws = sh.worksheet("config")
    except: 
        ws = sh.add_worksheet("config", 100, 2)
        ws.append_row(["clave", "valor"])
    try:
        cell = ws.find(key)
        ws.update_cell(cell.row, 2, str(value))
    except: ws.append_row([key, str(value)])
    return True

def update_full_socio(id_socio, d, user_admin, original_data=None):
    sh = get_client()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        r = cell.row
        # Mapeo estricto de columnas
        ws.update_cell(r, 3, d['nombre'])
        ws.update_cell(r, 4, d['apellido'])
        ws.update_cell(r, 5, d['dni'])
        ws.update_cell(r, 6, str(d['nacimiento']))
        ws.update_cell(r, 7, d['tutor'])    
        ws.update_cell(r, 8, d['whatsapp']) 
        ws.update_cell(r, 9, d['email'])    
        ws.update_cell(r, 10, d['sede'])
        ws.update_cell(r, 11, d['plan'])
        ws.update_cell(r, 12, d['notas'])
        ws.update_cell(r, 14, d['activo'])
        ws.update_cell(r, 15, d['talle'])
        ws.update_cell(r, 16, d['grupo']) 
        ws.update_cell(r, 17, d['peso'])    
        ws.update_cell(r, 18, d['altura'])
        
        cambios = []
        if original_data:
            for k, v in d.items():
                if str(v) != str(original_data.get(k, '')): cambios.append(f"{k}: {v}")
        if cambios: log_action(id_socio, "Edición Perfil", " | ".join(cambios), user_admin)
        return True
    except: return False

def update_plan_socio(id_socio, nuevo_plan):
    sh = get_client()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        ws.update_cell(cell.row, 11, nuevo_plan) 
        return True
    except: return False

def registrar_pago_existente(id_pago, metodo, user_cobrador, estado_final, nuevo_monto=None, nuevo_concepto=None, nota_conciliacion=""):
    ws = get_client().worksheet("pagos")
    try:
        cell = ws.find(str(id_pago))
        r = cell.row
        ws.update_cell(r, 2, str(get_today_ar())) 
        ws.update_cell(r, 7, metodo)
        ws.update_cell(r, 8, nota_conciliacion) 
        ws.update_cell(r, 9, estado_final) 
        ws.update_cell(r, 10, user_cobrador)
        if nuevo_monto: ws.update_cell(r, 5, nuevo_monto)
        if nuevo_concepto: ws.update_cell(r, 6, nuevo_concepto)
        log_action(id_pago, "Cobro Deuda", f"Cobrado por {user_cobrador}. Estado: {estado_final}", user_cobrador)
        return True
    except: return False

def confirmar_pago_seguro(id_pago, user, nota=""):
    ws = get_client().worksheet("pagos")
    try:
        cell = ws.find(str(id_pago))
        r = cell.row
        ws.update_cell(r, 9, "Confirmado")
        if nota: ws.update_cell(r, 8, nota) 
        log_action(id_pago, "Confirmar Pago", f"Validado. Nota: {nota}", user)
        return True
    except: return False

def actualizar_tarifas_bulk(df_edited):
    ws = get_client().worksheet("tarifas")
    ws.clear()
    ws.update([df_edited.columns.values.tolist()] + df_edited.values.tolist())

def calcular_edad(fecha_nac):
    try:
        if isinstance(fecha_nac, str): fecha_nac = datetime.strptime(fecha_nac, '%Y-%m-%d').date()
        hoy = get_today_ar()
        return hoy.year - fecha_nac.year - ((hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day))
    except: return "?"

def generar_pdf(datos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="AREA ARQUEROS - COMPROBANTE", ln=1, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Fecha: {datos['fecha']}", ln=1)
    pdf.cell(200, 10, txt=f"Alumno: {datos['alumno']}", ln=1)
    pdf.cell(200, 10, txt=f"Concepto: {datos['concepto']}", ln=1)
    pdf.cell(200, 10, txt=f"Mes: {datos.get('mes', '-')}", ln=1)
    pdf.cell(200, 10, txt=f"Medio de Pago: {datos['metodo']}", ln=1)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=f"TOTAL ABONADO: ${datos['monto']}", ln=1, align='C')
    if datos.get('nota'):
        pdf.ln(5)
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(200, 10, txt=f"Nota: {datos['nota']}", ln=1, align='C')
    pdf.ln(15)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt="Gracias por formar parte de Area Arqueros.", ln=1, align='C')
    return pdf.output(dest="S").encode("latin-1")

def inicializar_cronograma_base():
    data_list = []
    # C1
    grupos_c1 = ["Infantil 1", "Prejuvenil 1", "Juvenil 1", "Juvenil 2"]
    for d in ["Lunes", "Viernes"]:
        for h in ["18:00 - 19:00", "19:00 - 20:00"]:
            for g in grupos_c1: data_list.append([generate_id(), "Sede C1", d, h, g, "Sin Asignar", 10]); time.sleep(0.001)
    for g in ["Infantil 1", "Prejuvenil 1"]: data_list.append([generate_id(), "Sede C1", "Miércoles", "17:00 - 18:00", g, "Sin Asignar", 10]); time.sleep(0.001)
    for h in ["18:00 - 19:00", "19:00 - 20:00"]:
        for g in grupos_c1: data_list.append([generate_id(), "Sede C1", "Miércoles", h, g, "Sin Asignar", 10]); time.sleep(0.001)
    # SAA
    dias_saa = ["Lunes", "Miércoles", "Jueves"]
    gr_saa_18 = ["Infantil 1", "Infantil 2", "Prejuvenil 1", "Prejuvenil 2", "Juvenil 1", "Juvenil 2"]
    gr_saa_19 = ["Juvenil 1", "Juvenil 2", "Amateur 1", "Amateur 2", "Senior 1", "Senior 2"]
    for d in dias_saa:
        for g in gr_saa_18: data_list.append([generate_id(), "Sede Saa", d, "18:00 - 19:00", g, "Sin Asignar", 10]); time.sleep(0.001)
        for g in gr_saa_19: data_list.append([generate_id(), "Sede Saa", d, "19:00 - 20:00", g, "Sin Asignar", 10]); time.sleep(0.001)
    save_rows_bulk("entrenamientos", data_list)

# --- 3. LOGIN ---
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None})
if "view_profile_id" not in st.session_state: st.session_state["view_profile_id"] = None
if "cobro_alumno_id" not in st.session_state: st.session_state["cobro_alumno_id"] = None

def login():
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        try: st.image("logo.png", width=150)
        except: st.markdown("<h2 style='text-align: center;'>🔐 Area Arqueros</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar"):
                try:
                    CREDS = st.secrets["users"]
                    if u in CREDS and str(CREDS[u]["p"]) == p:
                        st.session_state.update({"auth": True, "user": u, "rol": CREDS[u]["r"]})
                        st.rerun()
                    else: st.error("Datos incorrectos")
                except: st.error("Error en configuración de usuarios.")

def logout():
    st.session_state["logged_in"] = False
    st.rerun()

if not st.session_state["auth"]:
    login()
    st.stop()

# --- 4. MENÚ ---
user, rol = st.session_state["user"], st.session_state["rol"]

with st.sidebar:
    try: st.image("logo.png", width=220)
    except: st.header("🛡️ AREA ARQUEROS")
    st.info(f"👤 **{user.upper()}**\nRol: {rol}")
    
    menu_opts = ["Dashboard"]
    if rol in ["Administrador", "Profesor"]:
        menu_opts.extend(["Alumnos", "Entrenamientos", "Asistencia"])
    if rol in ["Administrador", "Contador"]:
        menu_opts.extend(["Contabilidad", "Configuración"])
    
    nav = st.radio("Navegación", menu_opts)
    if nav != st.session_state.get("last_nav"):
        st.session_state["view_profile_id"] = None
        st.session_state["cobro_alumno_id"] = None
        st.session_state["last_nav"] = nav
    st.divider()
    if st.button("Cerrar Sesión"):
        st.session_state.update({"auth": False, "view_profile_id": None, "cobro_alumno_id": None})
        st.rerun()

# CONSTANTES GLOBALES
SEDES = ["Sede C1", "Sede Saa"]
GRUPOS = ["Inicial", "Intermedio", "Avanzado", "Arqueras", "Sin Grupo"]
TURNOS = ["17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
TALLES = ["10", "12", "14", "XS", "S", "M", "L", "XL"]

# --- 5. MÓDULOS ---

# === DASHBOARD ===
if nav == "Dashboard":
    st.title("📊 Estadísticas")
    c1, c2 = st.columns(2)
    fecha_inicio = c1.date_input("Desde", date.today().replace(day=1))
    fecha_fin = c2.date_input("Hasta", date.today())
    
    df_pagos = get_df("pagos")
    df_gastos = get_df("gastos")
    df_s = get_df("socios")
    
    ingresos = 0
    egresos = 0
    if not df_pagos.empty:
        df_pagos['fecha_pago'] = pd.to_datetime(df_pagos['fecha_pago'], errors='coerce').dt.date
        p_filt = df_pagos[(df_pagos['fecha_pago'] >= fecha_inicio) & (df_pagos['fecha_pago'] <= fecha_fin)]
        ingresos = pd.to_numeric(p_filt['monto'], errors='coerce').fillna(0).sum()
    if not df_gastos.empty:
        df_gastos['fecha'] = pd.to_datetime(df_gastos['fecha'], errors='coerce').dt.date
        g_filt = df_gastos[(df_gastos['fecha'] >= fecha_inicio) & (df_gastos['fecha'] <= fecha_fin)]
        egresos = pd.to_numeric(g_filt['monto'], errors='coerce').fillna(0).sum()
    balance = ingresos - egresos
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Ingresos", f"${ingresos:,.0f}")
    k2.metric("Gastos", f"${egresos:,.0f}")
    k3.metric("Neto", f"${balance:,.0f}", delta_color="normal")
    
    if not df_s.empty:
        st.markdown("---")
        c_g1, c_g2 = st.columns([2,1])
        with c_g1:
            df_s['Estado'] = df_s['activo'].map({1: 'Activo', 0: 'Baja'})
            fig = px.pie(df_s, names='Estado', hole=0.4, title="Estado Alumnos", color_discrete_sequence=['#1f2c56', '#dc3545'])
            st.plotly_chart(fig, use_container_width=True)

# === ALUMNOS ===
elif nav == "Alumnos":
    if st.session_state["view_profile_id"] is None:
        st.title("👥 Gestión de Alumnos")
        tab_dir, tab_new = st.tabs(["📂 Directorio", "➕ Nuevo Alumno"])
        
        with tab_dir:
            df = get_df("socios")
            if not df.empty:
                with st.expander("🔍 Filtros de Búsqueda", expanded=True):
                    c1, c2, c3, c4 = st.columns(4)
                    f_sede = c1.selectbox("Sede", ["Todas"] + sorted(df['sede'].astype(str).unique().tolist()))
                    f_plan = c2.selectbox("Plan", ["Todos"] + sorted(df['plan'].astype(str).unique().tolist()))
                    f_grupo = c3.selectbox("Categoría", ["Todos"] + sorted(df['grupo'].astype(str).unique().tolist()))
                    f_act = c4.selectbox("Estado", ["Activos", "Inactivos", "Todos"])
                
                df_fil = df.copy()
                if f_sede != "Todas": df_fil = df_fil[df_fil['sede'] == f_sede]
                if f_plan != "Todos": df_fil = df_fil[df_fil['plan'] == f_plan]
                if f_grupo != "Todos": df_fil = df_fil[df_fil['grupo'] == f_grupo]
                if f_act == "Activos": df_fil = df_fil[df_fil['activo'] == 1]
                elif f_act == "Inactivos": df_fil = df_fil[df_fil['activo'] == 0]
                
                st.caption(f"Resultados: {len(df_fil)}")
                
                rows_per_page = 20
                total_pages = (len(df_fil) // rows_per_page) + 1
                page = st.number_input("Página", 1, total_pages, 1) if total_pages > 1 else 1
                start = (page-1)*rows_per_page
                end = start + rows_per_page
                
                for idx, row in df_fil.iloc[start:end].iterrows():
                    status_cls = "🟢" if row['activo'] == 1 else "🔴"
                    with st.container():
                        st.markdown(f"""
                        <div class="student-card">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <div>
                                    <h4 style="margin:0; color:#1f2c56;">{row['nombre']} {row['apellido']}</h4>
                                    <span style="color:#666;">DNI: {row['dni']} | {row['sede']}</span>
                                </div>
                                <div>{status_cls}</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button(f"Ver Perfil", key=f"vp_{row['id']}"):
                            st.session_state["view_profile_id"] = row['id']
                            st.rerun()
        
        with tab_new:
            st.subheader("📝 Alta de Alumno")
            with st.form("alta_full"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nombre")
                ape = c2.text_input("Apellido")
                c3, c4 = st.columns(2)
                dni = c3.text_input("DNI")
                nac = c4.date_input("Nacimiento", min_value=date(1980,1,1))
                
                c5, c6 = st.columns(2)
                peso = c5.number_input("Peso (kg)", min_value=0.0)
                altura = c6.number_input("Altura (cm)", min_value=0)
                
                c7, c8 = st.columns(2)
                tutor = c7.text_input("Tutor")
                wsp = c8.text_input("WhatsApp")
                email = st.text_input("Email")
                
                st.markdown("---")
                c9, c10 = st.columns(2)
                sede = c9.selectbox("Sede", SEDES)
                grupo = c10.selectbox("Categoría General", GRUPOS)
                
                df_tar = get_df("tarifas")
                planes_list = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                plan = st.selectbox("Plan Facturación", planes_list)
                talle = st.selectbox("Talle", TALLES)
                
                if st.form_submit_button("💾 Crear Legajo"):
                    if nom and ape and dni:
                        uid = generate_id()
                        # ORDEN EXACTO (1-18)
                        row = [uid, str(get_today_ar()), nom, ape, dni, str(nac), tutor, wsp, email, sede, plan, "", user, 1, talle, grupo, peso, altura]
                        save_row("socios", row)
                        st.success("Alumno registrado.")
                        log_action(uid, "Alta", "Nuevo Alumno", user)
                    else: st.error("Faltan datos.")

    else:
        uid = st.session_state["view_profile_id"]
        df = get_df("socios")
        if not df.empty and not df[df['id'] == uid].empty:
            p = df[df['id'] == uid].iloc[0]
            if st.button("⬅️ Volver"):
                st.session_state["view_profile_id"] = None
                st.rerun()
            st.title(f"👤 {p['nombre']} {p['apellido']}")
            if p.get('whatsapp'):
                link = f"https://wa.me/{str(p['whatsapp']).strip()}"
                st.link_button("📱 WhatsApp", link)

            t1, t2, t3 = st.tabs(["✏️ Datos", "📅 Asistencias", "🔒 Historial"])
            
            with t1:
                if rol == "Administrador":
                    with st.form("edit_p"):
                        e1, e2 = st.columns(2)
                        n_nom = e1.text_input("Nombre", p['nombre'])
                        n_ape = e2.text_input("Apellido", p['apellido'])
                        n_dni = e1.text_input("DNI", p['dni'])
                        n_sede = e2.selectbox("Sede", SEDES, index=SEDES.index(p['sede']) if p['sede'] in SEDES else 0)
                        df_tar = get_df("tarifas")
                        pl = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                        idx = pl.index(p['plan']) if p['plan'] in pl else 0
                        n_plan = st.selectbox("Plan", pl, index=idx)
                        n_notas = st.text_area("Notas", p.get('notas',''))
                        n_act = st.checkbox("Activo", value=True if p['activo']==1 else False)
                        if st.form_submit_button("Guardar Cambios"):
                            d_upd = p.to_dict()
                            d_upd.update({'nombre': n_nom, 'apellido': n_ape, 'dni': n_dni, 'sede': n_sede, 'plan': n_plan, 'notas': n_notas, 'activo': 1 if n_act else 0})
                            update_full_socio(uid, d_upd, user, original_data=p.to_dict())
                            st.success("Actualizado.")
                            time.sleep(1); st.rerun()
                else: st.info("Modo Lectura")
            
            with t2:
                df_a = get_df("asistencias")
                if not df_a.empty:
                    mis_a = df_a[df_a['id_socio'] == uid]
                    st.dataframe(mis_a, use_container_width=True)
            
            with t3:
                df_l = get_df("logs")
                if not df_l.empty and 'id_ref' in df_l.columns:
                    mis_l = df_l[df_l['id_ref'].astype(str) == str(uid)]
                    st.dataframe(mis_l, use_container_width=True)
        else:
            st.error("Alumno no encontrado.")
            if st.button("Volver"):
                st.session_state["view_profile_id"] = None
                st.rerun()

# === ENTRENAMIENTOS ===
elif nav == "Entrenamientos":
    st.title("⚽ Entrenamientos")
    tab_asig, tab_cro, tab_adm = st.tabs(["➕ Asignar", "📅 Cronograma", "🔧 Admin"])
    
    with tab_asig:
        df_soc = get_df("socios")
        df_entr = get_df("entrenamientos")
        df_insc = get_df("inscripciones")
        
        if not df_entr.empty and not df_soc.empty:
            activos = df_soc[df_soc['activo']==1]
            alu = st.selectbox("Alumno", activos['id'].astype(str) + " - " + activos['nombre'] + " " + activos['apellido'])
            uid_alu = int(alu.split(" - ")[0])
            nom_alu = alu.split(" - ")[1]
            
            c1, c2, c3 = st.columns(3)
            sede = c1.selectbox("Sede", sorted(df_entr['sede'].unique()))
            dias = df_entr[df_entr['sede']==sede]['dia'].unique()
            dia = c2.selectbox("Día", dias)
            horas = df_entr[(df_entr['sede']==sede)&(df_entr['dia']==dia)]['horario'].unique()
            hora = c3.selectbox("Horario", horas)
            
            grupos = df_entr[(df_entr['sede']==sede)&(df_entr['dia']==dia)&(df_entr['horario']==hora)]
            st.markdown("---")
            for idx, row in grupos.iterrows():
                inscr = len(df_insc[df_insc['id_entrenamiento']==row['id']]) if not df_insc.empty else 0
                cupo = int(row['cupo_max']) - inscr
                with st.container():
                    col_inf, col_btn = st.columns([4,1])
                    col_inf.markdown(f"""<div class="training-card"><b>{row['grupo']}</b> | Coach: {row['entrenador']} | Cupos: {cupo}</div>""", unsafe_allow_html=True)
                    if cupo > 0:
                        if col_btn.button("Inscribir", key=f"ins_{row['id']}"):
                            row_ins = [generate_id(), uid_alu, nom_alu, row['id'], f"{row['grupo']} ({dia})"]
                            save_row("inscripciones", row_ins)
                            st.success("Inscrito!")
                            time.sleep(1); st.rerun()
                    else: col_btn.error("Lleno")

    with tab_cro:
        st.subheader("Vista Semanal")
        df_entr = get_df("entrenamientos")
        df_insc = get_df("inscripciones")
        if not df_entr.empty:
            sede_ver = st.selectbox("Sede", sorted(df_entr['sede'].unique()), key="sede_ver")
            df_sede = df_entr[df_entr['sede'] == sede_ver]
            for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]:
                clases = df_sede[df_sede['dia'] == d]
                if not clases.empty:
                    with st.expander(f"📅 {d}"):
                        for idx, row in clases.iterrows():
                            alumnos = []
                            if not df_insc.empty:
                                alumnos = df_insc[df_insc['id_entrenamiento'] == row['id']]['nombre_alumno'].tolist()
                            st.markdown(f"**{row['horario']} - {row['grupo']}** ({len(alumnos)} inscritos)")
                            if alumnos: st.caption(", ".join(alumnos))
                            st.divider()

    with tab_adm:
        if rol == "Administrador":
            if st.button("Inicializar Cronograma Base (C1 & SAA)"):
                inicializar_cronograma_base()
                st.success("Cronograma creado.")

# === ASISTENCIA ===
elif nav == "Asistencia":
    st.title("✅ Tomar Lista")
    df_entr = get_df("entrenamientos")
    df_insc = get_df("inscripciones")
    
    if not df_entr.empty:
        c1, c2, c3 = st.columns(3)
        sede = c1.selectbox("Sede", sorted(df_entr['sede'].unique()))
        dia_hoy = traducir_dia(get_today_ar())
        dias = sorted(df_entr[df_entr['sede']==sede]['dia'].unique())
        idx_d = dias.index(dia_hoy) if dia_hoy in dias else 0
        dia = c2.selectbox("Día", dias, index=idx_d)
        horas = df_entr[(df_entr['sede']==sede)&(df_entr['dia']==dia)]['horario'].unique()
        hora = c3.selectbox("Horario", horas)
        
        grupos = df_entr[(df_entr['sede']==sede)&(df_entr['dia']==dia)&(df_entr['horario']==hora)]
        
        if not grupos.empty:
            tabs = st.tabs([g['grupo'] for i, g in grupos.iterrows()])
            for i, (idx, g) in enumerate(grupos.iterrows()):
                with tabs[i]:
                    alumnos = df_insc[df_insc['id_entrenamiento']==g['id']] if not df_insc.empty else pd.DataFrame()
                    if not alumnos.empty:
                        with st.form(f"as_{g['id']}"):
                            checks = {}
                            cols = st.columns(3)
                            for j, (ix, al) in enumerate(alumnos.iterrows()):
                                checks[al['id_socio']] = cols[j%3].checkbox(al['nombre_alumno'], key=f"ch_{al['id_socio']}_{g['id']}")
                            if st.form_submit_button("Guardar Presentes"):
                                cnt = 0
                                for uid, p in checks.items():
                                    if p:
                                        nom = alumnos[alumnos['id_socio']==uid].iloc[0]['nombre_alumno']
                                        row = [str(get_today_ar()), datetime.now().strftime("%H:%M"), uid, nom, sede, f"{dia} {hora} - {g['grupo']}", "Presente"]
                                        save_row("asistencias", row)
                                        cnt+=1
                                st.success(f"{cnt} guardados.")
                    else: st.info("Sin inscritos.")
        else: st.warning("No hay clases.")

# === CONTABILIDAD ===
elif nav == "Contabilidad":
    st.title("📒 Contabilidad")
    
    with st.sidebar:
        st.markdown("### 🔍 Filtros")
        f_sede = st.multiselect("Sede", ["Sede C1", "Sede Saa"], default=["Sede C1", "Sede Saa"])
        f_mes = st.selectbox("Mes", ["Todos"] + MESES)
        f_rango1 = st.date_input("Desde", date(date.today().year, 1, 1))
        f_rango2 = st.date_input("Hasta", date.today())
        
    tab_cuotas, tab_ocasional, tab_rep = st.tabs(["📋 Gestión Pagos", "🛍️ Ocasionales", "📊 Caja"])
    
    with tab_cuotas:
        # --- AUTOMATIZACIÓN DE GENERACIÓN DE CUOTAS ---
        dia_corte = int(get_config_value("dia_corte", 19))
        hoy_ar = get_today_ar()
        
        mes_actual_idx = hoy_ar.month - 1
        if hoy_ar.day >= dia_corte:
            target_idx = (mes_actual_idx + 1) % 12
            year_target = hoy_ar.year + 1 if mes_actual_idx == 11 else hoy_ar.year
        else:
            target_idx = mes_actual_idx
            year_target = hoy_ar.year
        mes_sugerido_txt = MESES[target_idx]
        mes_completo_target = f"{mes_sugerido_txt} {year_target}"
        st.caption(f"Período: **{mes_completo_target}**")
        
        # Lógica automática al entrar
        df_pag = get_df("pagos")
        df_soc = get_df("socios")
        df_tar = get_df("tarifas")
        
        pagos_gen = []
        if not df_pag.empty and 'mes_cobrado' in df_pag.columns:
            # Buscar CUALQUIER registro de pago/deuda para ese mes y concepto Cuota
            pagos_mes = df_pag[(df_pag['mes_cobrado'] == mes_completo_target) & (df_pag['concepto'].astype(str).str.contains("Cuota"))]
            pagos_gen = pagos_mes['id_socio'].unique()
            
        if not df_soc.empty:
            # Alumnos activos sin registro de cuota este mes
            pendientes = df_soc[(df_soc['activo']==1) & (~df_soc['id'].isin(pagos_gen))]
            
            if not pendientes.empty:
                # Ejecutar Generación
                filas_nuevas = []
                for idx, row_s in pendientes.iterrows():
                    precio = 15000
                    if not df_tar.empty and row_s['plan'] in df_tar['concepto'].values:
                        precio = df_tar[df_tar['concepto']==row_s['plan']]['valor'].values[0]
                    
                    row_p = [
                        generate_id(), str(get_today_ar()), 
                        row_s['id'], f"{row_s['nombre']} {row_s['apellido']}", 
                        precio, "Cuota Mensual", "Pendiente", f"Plan: {row_s['plan']}", 
                        "Pendiente", "Sistema Auto", mes_completo_target
                    ]
                    filas_nuevas.append(row_p)
                
                if save_rows_bulk("pagos", filas_nuevas):
                    st.markdown(f"""<div class="auto-gen-box"><h4>🔄 Sistema Automático</h4><p>Se generaron {len(filas_nuevas)} cuotas para {mes_completo_target}.</p></div>""", unsafe_allow_html=True)
                    time.sleep(2)
                    st.rerun()

        # --- GESTIÓN DE COBROS ---
        if st.session_state["cobro_alumno_id"]:
            uid = st.session_state["cobro_alumno_id"]
            # Recargar DFs
            df_pag = get_df("pagos")
            df_soc = get_df("socios")
            
            alu = df_soc[df_soc['id']==uid].iloc[0]
            st.subheader(f"Cobrando a: {alu['nombre']}")
            if st.button("Cancelar"):
                st.session_state["cobro_alumno_id"] = None
                st.rerun()
            
            # Buscar si hay deuda pendiente para el mes target
            deuda_existente_id = None
            if not df_pag.empty:
                 check = df_pag[(df_pag['id_socio']==uid) & (df_pag['mes_cobrado']==mes_completo_target) & (df_pag['estado']=='Pendiente')]
                 if not check.empty:
                     deuda_existente_id = check.iloc[0]['id']
                     st.warning(f"Se actualizará la deuda de {mes_completo_target}.")

            with st.form("pay_direct"):
                df_tar = get_df("tarifas")
                lst = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                idx_p = lst.index(alu['plan']) if alu['plan'] in lst else 0
                conc = st.selectbox("Concepto", lst, index=idx_p)
                pr = 0.0
                if not df_tar.empty:
                    m = df_tar[df_tar['concepto']==conc]
                    if not m.empty:
                        try: pr = float(str(m.iloc[0]['valor']).replace('$',''))
                        except: pass
                
                mon = st.number_input("Monto", value=pr)
                met = st.selectbox("Medio", ["Efectivo", "Transferencia", "MercadoPago"])
                mes_p = st.selectbox("Mes", [mes_completo_target] + [f"{m} {year_target}" for m in MESES])
                nota = st.text_input("Nota")
                conf = st.checkbox("Confirmar Auto", value=True)
                
                if st.form_submit_button("Pagar"):
                    if conc != alu['plan']: update_plan_socio(uid, conc)
                    st_pago = "Confirmado" if conf else "Pendiente"
                    
                    if deuda_existente_id:
                         registrar_pago_existente(deuda_existente_id, met, user, st_pago, mon, conc, nota)
                    else:
                        row = [generate_id(), str(get_today_ar()), uid, f"{alu['nombre']} {alu['apellido']}", mon, conc, met, nota, st_pago, user, mes_p]
                        save_row("pagos", row)
                    
                    st.success("Registrado")
                    d_pdf = {"fecha":str(get_today_ar()), "alumno":f"{alu['nombre']} {alu['apellido']}", "monto":mon, "concepto":conc, "metodo":met, "mes":mes_p, "nota":nota}
                    pdf_b = generar_pdf(d_pdf)
                    b64 = base64.b64encode(pdf_b).decode()
                    href = f'<a href="data:application/octet-stream;base64,{b64}" download="Recibo.pdf"><button>Descargar Recibo</button></a>'
                    st.markdown(href, unsafe_allow_html=True)
                    time.sleep(4)
                    st.session_state["cobro_alumno_id"] = None
                    st.rerun()

        else:
            st.subheader("Listado de Cobro")
            col_s, col_r = st.columns([3,1])
            search = col_s.text_input("Buscar")
            rows = col_r.selectbox("Filas", [25, 50])
            
            df_s = get_df("socios")
            # Recargar Pagos
            df_p = get_df("pagos")
            
            if not df_s.empty:
                df_show = df_s[df_s['activo']==1]
                if search:
                    df_show = df_show[df_show.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
                
                # Paginación
                total_rows = len(df_show)
                total_pages = (total_rows // rows) + 1 if rows > 0 else 1
                if total_pages > 1: page = st.number_input("Página", 1, total_pages, 1)
                else: page = 1
                start = (page - 1) * rows
                end = start + rows
                subset = df_show.iloc[start:end]
                
                # Lógica Vencimientos
                dia_venc = int(get_config_value("dia_vencimiento", 10))
                dia_hoy = get_today_ar().day
                
                cols = st.columns([3, 2, 2, 2])
                cols[0].markdown("**Alumno**")
                cols[1].markdown("**Sede**")
                cols[2].markdown(f"**Estado ({mes_completo_target})**")
                cols[3].markdown("**Acción**")
                st.markdown("---")
                
                for idx, row in subset.iterrows():
                    st_mes = "⚪ Sin Generar"
                    color_cls = ""
                    
                    if not df_p.empty and 'mes_cobrado' in df_p.columns:
                        pm = df_p[(df_p['id_socio']==row['id']) & (df_p['mes_cobrado']==mes_completo_target)]
                        if not pm.empty:
                            estado_real = pm.iloc[0]['estado']
                            if estado_real == "Confirmado":
                                st_mes = "✅ Al día"
                                color_cls = "status-ok"
                            else:
                                # Pendiente -> Chequear Vencimiento
                                if dia_hoy > dia_venc:
                                    st_mes = "🔴 VENCIDO"
                                    color_cls = "status-vencido"
                                else:
                                    st_mes = "🟡 A Tiempo"
                                    color_cls = "status-pending"
                    
                    c1, c2, c3, c4 = st.columns([3,2,1,1])
                    c1.write(f"**{row['nombre']} {row['apellido']}**")
                    c2.caption(row['sede'])
                    c3.markdown(f"<span class='{color_cls}'>{st_mes}</span>", unsafe_allow_html=True)
                    if c4.button("Cobrar", key=f"pay_{row['id']}"):
                        st.session_state["cobro_alumno_id"] = row['id']
                        st.rerun()
                    st.divider()
            else: st.info("No hay alumnos.")

    with tab_ocasional:
        st.subheader("Cobro Ocasional")
        df_s = get_df("socios")
        if not df_s.empty:
            activos = df_s[df_s['activo']==1]
            sel = st.selectbox("Alumno", activos['id'].astype(str) + " - " + activos['nombre'] + " " + activos['apellido'], key="ocasional")
            with st.form("pay_ocasional"):
                c1, c2 = st.columns(2)
                monto = c1.number_input("Monto", step=100)
                concepto = st.selectbox("Concepto", ["Matrícula", "Indumentaria", "Torneo", "Campus", "Otro"])
                metodo = st.selectbox("Medio", ["Efectivo", "Transferencia", "MercadoPago"])
                nota = st.text_input("Nota")
                if st.form_submit_button("Registrar"):
                    row = [generate_id(), str(get_today_ar()), int(sel.split(" - ")[0]), sel.split(" - ")[1], monto, concepto, metodo, nota, "Confirmado", user, "-"]
                    save_row("pagos", row)
                    st.success("Registrado.")

    with tab_rep:
        st.markdown("### Caja Diaria")
        df_p = get_df("pagos")
        if not df_p.empty:
            td = str(get_today_ar())
            ch = df_p[(df_p['fecha_pago']==td) & (df_p['estado']=='Confirmado')]
            tot = pd.to_numeric(ch['monto'], errors='coerce').sum()
            st.metric("Total Hoy", f"${tot:,.0f}")
            st.dataframe(ch)

elif nav == "Configuración":
    st.title("⚙️ Configuración")
    tab1, tab2 = st.tabs(["Parámetros", "Tarifas"])
    with tab1:
        d = int(get_config_value("dia_corte", 19))
        nd = st.slider("Día Corte", 1, 28, d)
        v = int(get_config_value("dia_vencimiento", 10))
        nv = st.slider("Día Vencimiento", 1, 28, v)
        if st.button("Guardar"):
            set_config_value("dia_corte", nd)
            set_config_value("dia_vencimiento", nv)
            st.success("Guardado")
    with tab2:
        df = get_df("tarifas")
        ed = st.data_editor(df, num_rows="dynamic")
        if st.button("Guardar Tarifas"):
            actualizar_tarifas_bulk(ed)
            st.success("Guardado")

