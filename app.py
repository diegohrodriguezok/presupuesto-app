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
import uuid # Para IDs únicos y seguros

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

# --- CSS PREMIUM ---
st.markdown("""
    <style>
        /* Estilos Generales */
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
        .info-label {
            font-size: 0.85rem; color: #666; margin-bottom: 5px; display: block;
        }
        .highlight-data {
            background-color: #e3f2fd; padding: 5px 10px; border-radius: 5px; color: #0d47a1; font-weight: bold;
        }
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
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

def save_row(sheet_name, data):
    try: get_client().worksheet(sheet_name).append_row(data)
    except: pass

def generate_id():
    """Genera un ID único seguro basado en tiempo y aleatoriedad"""
    # Combina timestamp con una parte aleatoria corta para evitar colisiones
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
    try:
        ws = sh.worksheet("config")
    except:
        ws = sh.add_worksheet("config", 100, 2)
        ws.append_row(["clave", "valor"])
    
    try:
        cell = ws.find(key)
        ws.update_cell(cell.row, 2, str(value))
    except:
        ws.append_row([key, str(value)])
    return True

def update_full_socio(id_socio, d, user_admin, original_data=None):
    sh = get_client()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        r = cell.row
        # Mapeo estricto
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
                if str(v) != str(original_data.get(k, '')):
                    cambios.append(f"{k}: {v}")
        if cambios: log_action(id_socio, "Edición Perfil", " | ".join(cambios), user_admin)
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False

def update_plan_socio(id_socio, nuevo_plan):
    sh = get_client()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        ws.update_cell(cell.row, 11, nuevo_plan) 
        return True
    except: return False

def registrar_pago_existente(id_pago, metodo, user_cobrador, nuevo_monto=None, nuevo_concepto=None, nota_conciliacion=""):
    ws = get_client().worksheet("pagos")
    try:
        cell = ws.find(str(id_pago))
        r = cell.row
        ws.update_cell(r, 2, str(get_today_ar())) 
        ws.update_cell(r, 7, metodo)
        ws.update_cell(r, 8, nota_conciliacion) 
        ws.update_cell(r, 9, "Confirmado")
        ws.update_cell(r, 10, user_cobrador)
        
        if nuevo_monto: ws.update_cell(r, 5, nuevo_monto)
        if nuevo_concepto: ws.update_cell(r, 6, nuevo_concepto)
            
        log_action(id_pago, "Cobro Deuda", f"Cobrado por {user_cobrador}. Nota: {nota_conciliacion}", user_cobrador)
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

# --- 3. LOGIN ---
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None})
if "view_profile_id" not in st.session_state: st.session_state["view_profile_id"] = None
if "cobro_alumno_id" not in st.session_state: st.session_state["cobro_alumno_id"] = None
if "cobro_monto_manual" not in st.session_state: st.session_state["cobro_monto_manual"] = 0.0

def login():
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        try: st.image("logo.png", width=150)
        except: st.markdown("<h2 style='text-align: center;'>🔐 Area Arqueros</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar"):
                CREDS = {
                    "admin": {"p": "admin2024", "r": "Administrador"},
                    "profe": {"p": "entrenador", "r": "Profesor"},
                    "conta": {"p": "finanzas", "r": "Contador"}
                }
                if u in CREDS and CREDS[u]["p"] == p:
                    st.session_state.update({"auth": True, "user": u, "rol": CREDS[u]["r"]})
                    st.rerun()
                else:
                    st.error("Datos incorrectos")

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
        menu_opts.extend(["Alumnos", "Asistencia"])
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

# --- CONSTANTES GLOBALES ---
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
    
    st.markdown("---")
    
    if ingresos > 0 or egresos > 0:
        datos = pd.DataFrame({"Concepto": ["Ingresos", "Gastos"], "Monto": [ingresos, egresos]})
        st.bar_chart(datos, x="Concepto", y="Monto")
    else:
        st.info("No hay movimientos en este rango de fechas.")

# === CONTABILIDAD ===
elif nav == "Contabilidad":
    st.title("📒 Contabilidad")
    
    with st.sidebar:
        st.markdown("### 🔍 Filtros")
        f_sede = st.multiselect("Sede", ["Sede C1", "Sede Saa"], default=["Sede C1", "Sede Saa"])
        f_mes = st.selectbox("Mes", ["Todos"] + MESES)
        f_rango1 = st.date_input("Desde", date(date.today().year, 1, 1))
        f_rango2 = st.date_input("Hasta", date.today())
        
    tab_cuotas, tab_ocasional, tab_rep = st.tabs(["📋 Gestión de Pagos", "🛍️ Ocasionales", "📊 Caja & Reportes"])
    
    # --- TAB 1: LISTA INTERACTIVA Y COBRO ---
    with tab_cuotas:
        # Recoger configuración de fechas
        dia_corte = int(get_config_value("dia_corte", 19))
        
        # Calcular fecha/mes sugerido para generación
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

        st.caption(f"📅 Período Sugerido: **{mes_completo_target}** (Corte: día {dia_corte})")

        # 1. SI HAY ALGUIEN SELECCIONADO PARA COBRAR
        if st.session_state["cobro_alumno_id"] is not None:
            uid = st.session_state["cobro_alumno_id"]
            df_soc = get_df("socios")
            df_tar = get_df("tarifas")
            df_pag = get_df("pagos") # Para buscar último pago
            
            alumno = df_soc[df_soc['id'] == uid].iloc[0]
            
            # Buscar último mes abonado
            ultimo_mes_pago = "Ninguno"
            if not df_pag.empty and 'mes_cobrado' in df_pag.columns:
                pagos_alumno = df_pag[(df_pag['id_socio'] == uid) & (df_pag['estado'] == 'Confirmado')]
                if not pagos_alumno.empty:
                    # Ordenar y tomar el último (simple aproximación textual o por ID)
                    ultimo_mes_pago = pagos_alumno.iloc[-1]['mes_cobrado']

            col_h1, col_h2 = st.columns([4,1])
            col_h1.subheader(f"Cobrar a: {alumno['nombre']} {alumno['apellido']}")
            if col_h2.button("❌ Cancelar"):
                st.session_state["cobro_alumno_id"] = None
                st.rerun()
            
            st.markdown(f"""
            <div style="background-color:#e3f2fd; padding:10px; border-radius:5px; border-left:5px solid #2196f3; margin-bottom:15px;">
                <span style="font-weight:bold; color:#0d47a1;">📋 Plan Actual: {alumno.get('plan', 'Sin Plan')}</span><br>
                <span style="font-size:0.9em; color:#555;">🗓️ Último mes abonado: <b>{ultimo_mes_pago}</b></span>
            </div>
            """, unsafe_allow_html=True)
            
            # Lógica de Precios
            tarifas_list = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
            idx_plan = tarifas_list.index(alumno['plan']) if alumno.get('plan') in tarifas_list else 0
            
            # FORMULARIO DINÁMICO
            c1, c2 = st.columns(2)
            concepto = c1.selectbox("Concepto / Tarifa", tarifas_list, index=idx_plan, key="sel_concepto_cobro")
            
            precio_sugerido = 0.0
            if not df_tar.empty:
                match = df_tar[df_tar['concepto'] == concepto]
                if not match.empty:
                    try: precio_sugerido = float(str(match.iloc[0]['valor']).replace('$','').replace('.',''))
                    except: pass
            
            monto = c2.number_input("Monto a Cobrar ($)", value=precio_sugerido, step=100.0)
            
            c3, c4 = st.columns(2)
            metodo = c3.selectbox("Medio de Pago", ["Efectivo", "Transferencia", "MercadoPago"])
            
            # Mes sugerido pre-seleccionado
            mes_pago_sel = c4.selectbox("Mes Correspondiente", [f"{m} {year_target}" for m in MESES] + [f"{m} {year_target-1}" for m in MESES], index=target_idx)
            
            nota_conciliacion = st.text_area("Nota de Conciliación", placeholder="Detalles del pago...")
            
            col_chk, col_btn = st.columns([2, 1])
            conciliar_auto = col_chk.checkbox("Confirmar/Conciliar Automáticamente", value=True)
            
            if col_btn.button("✅ REGISTRAR PAGO", type="primary", use_container_width=True):
                if concepto != alumno.get('plan'):
                    update_plan_socio(uid, concepto)
                
                estado_pago = "Confirmado" if conciliar_auto else "Pendiente"
                
                row = [
                    generate_id(), str(get_today_ar()), 
                    uid, f"{alumno['nombre']} {alumno['apellido']}", 
                    monto, concepto, metodo, nota_conciliacion, 
                    estado_pago, user, mes_pago_sel
                ]
                save_row("pagos", row)
                
                st.success("Pago registrado.")
                
                datos_pdf = {
                    "fecha": str(get_today_ar()), "alumno": f"{alumno['nombre']} {alumno['apellido']}",
                    "monto": monto, "concepto": concepto, "metodo": metodo, "mes": mes_pago_sel, "nota": nota_conciliacion
                }
                pdf_bytes = generar_pdf(datos_pdf)
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Recibo.pdf" style="text-decoration:none;"><button style="background-color:#2196F3;color:white;border:none;padding:10px;border-radius:5px;cursor:pointer;width:100%;">📄 Descargar Recibo PDF</button></a>'
                st.markdown(href, unsafe_allow_html=True)
                
                time.sleep(4)
                st.session_state["cobro_alumno_id"] = None
                st.rerun()

        else:
            # 2. VISTA DE LISTA
            st.subheader("📋 Listado de Alumnos para Cobro")
            
            col_search, col_rows = st.columns([3, 1])
            search_term = col_search.text_input("🔍 Buscar Alumno (Nombre o DNI)")
            rows_per_page = col_rows.selectbox("Filas", [25, 50, 100], index=0)
            
            df_soc = get_df("socios")
            df_pag = get_df("pagos")
            
            if not df_soc.empty:
                df_show = df_soc[df_soc['activo'] == 1]
                if search_term:
                    df_show = df_show[df_show.astype(str).apply(lambda x: x.str.contains(search_term, case=False)).any(axis=1)]
                
                total_rows = len(df_show)
                total_pages = (total_rows // rows_per_page) + 1 if rows_per_page > 0 else 1
                
                if total_pages > 1: page = st.number_input("Página", 1, total_pages, 1)
                else: page = 1
                
                start_idx = (page - 1) * rows_per_page
                end_idx = start_idx + rows_per_page
                subset = df_show.iloc[start_idx:end_idx]
                
                cols = st.columns([3, 2, 2, 2])
                cols[0].markdown("**Alumno**")
                cols[1].markdown("**Sede**")
                cols[2].markdown(f"**Estado ({mes_completo_target})**")
                cols[3].markdown("**Acción**")
                st.markdown("---")
                
                for idx, row in subset.iterrows():
                    estado_mes = "❓"
                    deuda_id = None
                    if not df_pag.empty and 'mes_cobrado' in df_pag.columns:
                        # Filtro lógico por MES COBRADO (no por fecha de pago)
                        pago_mes = df_pag[(df_pag['id_socio'] == row['id']) & (df_pag['mes_cobrado'] == mes_completo_target)]
                        
                        if not pago_mes.empty:
                            if "Confirmado" in pago_mes['estado'].values:
                                estado_mes = "✅ Pagó"
                            else:
                                estado_mes = "🔴 Debe"
                                deuda_id = pago_mes[pago_mes['estado']=="Pendiente"].iloc[0]['id']

                    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                    with c1: st.write(f"**{row['nombre']} {row['apellido']}**")
                    with c2: st.caption(f"{row['sede']}")
                    with c3: 
                        if "✅" in estado_mes: st.success(estado_mes)
                        elif "🔴" in estado_mes: st.error(estado_mes)
                        else: st.caption("Sin Generar")
                    with c4:
                        lbl = "💸 Pagar Deuda" if deuda_id else "💲 Cobrar Nuevo"
                        if st.button(lbl, key=f"btn_pay_{row['id']}", type="primary" if deuda_id else "secondary", use_container_width=True):
                            st.session_state["cobro_alumno_id"] = row['id']
                            st.rerun()
                    st.divider()
            else:
                st.info("No hay alumnos activos.")

    # --- PESTAÑA 2: OCASIONALES ---
    with tab_ocasional:
        st.subheader("🛍️ Cobro Ocasional")
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
                    row = [
                        generate_id(), str(get_today_ar()), 
                        int(sel.split(" - ")[0]), sel.split(" - ")[1], 
                        monto, concepto, metodo, nota, 
                        "Confirmado", user, "-"
                    ]
                    save_row("pagos", row)
                    st.success("Registrado.")

    with tab_rep:
        st.markdown("### 📅 Caja Diaria (Hoy)")
        df_p = get_df("pagos")
        if not df_p.empty:
            today = str(get_today_ar())
            caja_hoy = df_p[(df_p['fecha_pago'] == today) & (df_p['estado'] == 'Confirmado')]
            if not caja_hoy.empty:
                total_hoy = pd.to_numeric(caja_hoy['monto'], errors='coerce').sum()
                efectivo = caja_hoy[caja_hoy['metodo']=="Efectivo"]['monto'].sum() if "Efectivo" in caja_hoy['metodo'].values else 0
                digital = total_hoy - efectivo
                col_c1, col_c2, col_c3 = st.columns(3)
                col_c1.markdown(f"<div class='caja-box'><h3>Total Hoy</h3><h2>${total_hoy:,.0f}</h2></div>", unsafe_allow_html=True)
                col_c2.metric("💵 Efectivo", f"${efectivo:,.0f}")
                col_c3.metric("💳 Digital", f"${digital:,.0f}")
                st.dataframe(caja_hoy[['nombre_socio', 'monto', 'metodo', 'concepto']], use_container_width=True)
            else: st.info("Sin movimientos.")
        
        st.divider()
        if not df_p.empty:
            df_p['fecha_dt'] = pd.to_datetime(df_p['fecha_pago'], errors='coerce').dt.date
            mask = (df_p['fecha_dt'] >= f_rango1) & (df_p['fecha_dt'] <= f_rango2) & (df_p['estado'] == 'Confirmado')
            if f_mes != "Todos" and 'mes_cobrado' in df_p.columns: mask = mask & (df_p['mes_cobrado'] == f_mes)
            df_final = df_p[mask]
            total = pd.to_numeric(df_final['monto'], errors='coerce').sum()
            st.metric("Total Filtrado", f"${total:,.0f}")
            st.dataframe(df_final, use_container_width=True)

# === NUEVO ALUMNO ===
elif nav == "Nuevo Alumno":
    st.title("📝 Alta Alumno")
    with st.form("alta"):
        c1, c2 = st.columns(2)
        nom = c1.text_input("Nombre")
        ape = c2.text_input("Apellido")
        c3, c4 = st.columns(2)
        dni = c3.text_input("DNI")
        nac = c4.date_input("Nacimiento", min_value=date(1980,1,1))
        
        SEDES_OPT = ["Sede C1", "Sede Saa"]
        GRUPOS_OPT = ["Inicial", "Intermedio", "Avanzado", "Arqueras", "Sin Grupo"]
        
        c5, c6 = st.columns(2)
        sede = c5.selectbox("Sede", SEDES_OPT)
        grupo = c6.selectbox("Grupo", GRUPOS_OPT)
        
        df_tar = get_df("tarifas")
        lista_planes = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
        
        c7, c8 = st.columns(2)
        talle = c7.selectbox("Talle", TALLES)
        plan = c8.selectbox("Plan", lista_planes)
        wsp = st.text_input("WhatsApp")
        
        if st.form_submit_button("Guardar"):
            if nom and ape and dni:
                uid = generate_id()
                row = [uid, str(get_today_ar()), nom, ape, dni, str(nac), "", wsp, "", sede, plan, "", user, 1, talle, grupo]
                save_row("socios", row)
                st.success("Guardado.")
            else:
                st.error("Faltan datos obligatorios")

# === ASISTENCIA ===
elif nav == "Asistencia":
    st.title("✅ Tomar Lista")
    c1, c2 = st.columns(2)
    sede_sel = c1.selectbox("Sede", ["Sede C1", "Sede Saa"])
    grupo_sel = c2.selectbox("Grupo", ["Inicial", "Intermedio", "Avanzado", "Arqueras", "Sin Grupo"])
    turno = st.selectbox("Turno", ["17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"])
    
    df = get_df("socios")
    if not df.empty and "grupo" in df.columns:
        filtro = df[(df['sede'] == sede_sel) & (df['grupo'] == grupo_sel) & (df['activo'] == 1)]
        if not filtro.empty:
            with st.form("lista"):
                cols = st.columns(3)
                checks = {}
                for i, (idx, r) in enumerate(filtro.iterrows()):
                    checks[r['id']] = cols[i%3].checkbox(f"{r['nombre']} {r['apellido']}", key=r['id'])
                if st.form_submit_button("Guardar"):
                    cnt = 0
                    for uid, pres in checks.items():
                        if pres:
                            n = filtro.loc[filtro['id']==uid, 'nombre'].values[0]
                            a = filtro.loc[filtro['id']==uid, 'apellido'].values[0]
                            row = [str(get_today_ar()), datetime.now().strftime("%H:%M"), uid, f"{n} {a}", sede_sel, turno, "Presente"]
                            save_row("asistencias", row)
                            cnt+=1
                    st.success(f"{cnt} presentes.")
        else:
            st.info("Sin alumnos en este grupo/sede.")

# === GESTIÓN ===
elif nav == "Gestión Alumnos":
    st.title("👥 Alumnos")
    df = get_df("socios")
    if not df.empty:
        st.dataframe(df[['nombre', 'apellido', 'grupo', 'activo']], use_container_width=True)
        
        if rol == "Administrador":
            st.markdown("---")
            st.subheader("Edición (Admin)")
            sel = st.selectbox("Editar a:", df.apply(lambda x: f"{x['id']} - {x['nombre']}", axis=1))
            if sel:
                uid = int(sel.split(" - ")[0])
                curr = df[df['id'] == uid].iloc[0]
                with st.form("edit"):
                    n_nom = st.text_input("Nombre", curr['nombre'])
                    n_ape = st.text_input("Apellido", curr['apellido'])
                    n_dni = st.text_input("DNI", curr['dni'])
                    n_sede = st.selectbox("Sede", ["Sede C1", "Sede Saa"], index=0 if curr['sede'] == "Sede C1" else 1)
                    n_grupo = st.selectbox("Grupo", ["Inicial", "Intermedio", "Avanzado", "Arqueras", "Sin Grupo"], index=0)
                    n_act = st.selectbox("Estado", [1,0], index=0 if curr['activo']==1 else 1)
                    
                    if st.form_submit_button("Guardar Cambios"):
                        datos = {
                            "nombre": n_nom, "apellido": n_ape, "dni": n_dni,
                            "nacimiento": curr['fecha_nacimiento'],
                            "sede": n_sede, "plan": curr['frecuencia'], 
                            "activo": n_act, "talle": curr['talle'], "grupo": n_grupo
                        }
                        update_full_socio(uid, datos, user)
                        st.success("Actualizado.")
                        time.sleep(1)
                        st.rerun()

# === CONFIGURACIÓN ===
elif nav == "Configuración":
    st.title("⚙️ Configuración del Sistema")
    
    tab_gen, tab_tar = st.tabs(["🔧 General", "💲 Tarifas"])
    
    with tab_gen:
        st.subheader("Parámetros de Facturación")
        dia_corte_actual = int(get_config_value("dia_corte", 19))
        dia_venc_actual = int(get_config_value("dia_vencimiento", 10))
        
        c1, c2 = st.columns(2)
        nuevo_dia_corte = c1.slider("Día de Corte (Generación Automática)", 1, 28, dia_corte_actual, help="Día del mes a partir del cual el sistema sugiere generar las cuotas del mes siguiente.")
        nuevo_dia_venc = c2.slider("Día de Vencimiento de Cuota", 1, 28, dia_venc_actual, help="Día límite para el pago de la cuota antes de considerarse vencida.")
        
        if st.button("💾 Guardar Configuración General"):
            set_config_value("dia_corte", nuevo_dia_corte)
            set_config_value("dia_vencimiento", nuevo_dia_venc)
            st.success(f"Configuración actualizada.")
            time.sleep(1)
            st.rerun()
            
    with tab_tar:
        st.subheader("Lista de Precios")
        df = get_df("tarifas")
        edited = st.data_editor(df, num_rows="dynamic")
        if st.button("Guardar Tarifas"):
            actualizar_tarifas_bulk(edited)
            st.success("Tarifas guardadas")

