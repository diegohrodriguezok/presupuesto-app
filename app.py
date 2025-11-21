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

# --- CONSTANTES DE MESES ---
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# --- CSS PREMIUM ---
st.markdown("""
    <style>
        .stButton>button {
            border-radius: 6px;
            height: 45px;
            font-weight: 600;
            border: none;
            background-color: #1f2c56;
            color: white !important;
            transition: all 0.3s;
            width: 100%;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .stButton>button:hover {
            background-color: #2c3e50;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            transform: translateY(-2px);
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

def log_action(id_ref, accion, detalle, user):
    try:
        row = [str(get_now_ar()), user, str(id_ref), accion, detalle]
        save_row("logs", row)
    except: pass

# --- FUNCIONES DE CONFIGURACIÓN ---
def get_config_value(key, default_val):
    """Obtiene un valor de configuración de la hoja 'config'"""
    df = get_df("config")
    if not df.empty and 'clave' in df.columns and 'valor' in df.columns:
        res = df[df['clave'] == key]
        if not res.empty:
            return res.iloc[0]['valor']
    return default_val

def set_config_value(key, value):
    """Guarda o actualiza una configuración"""
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

def registrar_pago_existente(id_pago, metodo, user_cobrador, nuevo_monto=None, nuevo_concepto=None):
    ws = get_client().worksheet("pagos")
    try:
        cell = ws.find(str(id_pago))
        r = cell.row
        ws.update_cell(r, 2, str(get_today_ar())) 
        ws.update_cell(r, 7, metodo)
        ws.update_cell(r, 9, "Confirmado")
        ws.update_cell(r, 10, user_cobrador)
        if nuevo_monto: ws.update_cell(r, 5, nuevo_monto)
        if nuevo_concepto: ws.update_cell(r, 6, nuevo_concepto)
        log_action(id_pago, "Cobro Deuda", f"Cobrado por {user_cobrador}", user_cobrador)
        return True
    except: return False

def confirmar_pago_seguro(id_pago, user):
    ws = get_client().worksheet("pagos")
    try:
        cell = ws.find(str(id_pago))
        ws.update_cell(cell.row, 9, "Confirmado")
        log_action(id_pago, "Confirmar Pago", "Pago Validado", user)
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
    pdf.ln(20)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt="Gracias por formar parte de Area Arqueros.", ln=1, align='C')
    return pdf.output(dest="S").encode("latin-1")

# --- 3. LOGIN ---
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None})
if "view_profile_id" not in st.session_state:
    st.session_state["view_profile_id"] = None

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
                else: st.error("Acceso denegado")

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
        menu_opts.extend(["Contabilidad", "Configuración"]) # Cambio de Nombre
    
    nav = st.radio("Navegación", menu_opts)
    if nav != st.session_state.get("last_nav"):
        st.session_state["view_profile_id"] = None
        st.session_state["last_nav"] = nav
    st.divider()
    if st.button("Cerrar Sesión"):
        st.session_state.update({"auth": False, "view_profile_id": None})
        st.rerun()

# --- 5. MÓDULOS ---

if nav == "Dashboard":
    st.title("📊 Tablero de Comando")
    st.caption(f"Fecha del Sistema (AR): {get_today_ar().strftime('%d/%m/%Y')}")
    
    df_s = get_df("socios")
    df_a = get_df("asistencias")
    df_p = get_df("pagos")
    
    k1, k2, k3, k4 = st.columns(4)
    
    activos = len(df_s[df_s['activo']==1]) if not df_s.empty else 0
    k1.metric("👥 Plantel Activo", activos)
    
    presentes_hoy = 0
    today_str = get_today_ar().strftime("%Y-%m-%d")
    if not df_a.empty:
        df_a['fecha'] = df_a['fecha'].astype(str)
        presentes_hoy = len(df_a[df_a['fecha'] == today_str])
    k2.metric("✅ Asistencia Hoy", presentes_hoy)
    
    ingresos_mes = 0
    mes_actual = get_today_ar().month
    if not df_p.empty:
        df_p['dt'] = pd.to_datetime(df_p['fecha_pago'], errors='coerce')
        pagos_mes = df_p[ (df_p['dt'].dt.month == mes_actual) & (df_p['estado'] == 'Confirmado') ]
        ingresos_mes = pd.to_numeric(pagos_mes['monto'], errors='coerce').sum()
    k3.metric("💰 Ingresos (Mes)", f"${ingresos_mes:,.0f}")
    
    deudores_count = 0
    if not df_p.empty:
        deudas_pend = df_p[ (df_p['dt'].dt.month == mes_actual) & (df_p['estado'] == 'Pendiente') ]
        deudores_count = len(deudas_pend)
    k4.metric("⚠️ Pendientes Pago", deudores_count, delta_color="inverse")

    st.markdown("---")
    c_g1, c_g2 = st.columns([2, 1])
    with c_g1:
        st.markdown("### 📅 Tendencia de Asistencia")
        if not df_a.empty:
            fecha_limite = get_today_ar() - timedelta(days=7)
            df_a['dt_obj'] = pd.to_datetime(df_a['fecha'], errors='coerce').dt.date
            recientes = df_a[df_a['dt_obj'] >= fecha_limite]
            if not recientes.empty:
                daily_att = recientes.groupby('fecha')['id_socio'].count().reset_index()
                fig_line = px.bar(daily_att, x='fecha', y='id_socio', text='id_socio', template="plotly_dark",
                                  color_discrete_sequence=['#4ea8de'], title="Últimos 7 días")
                st.plotly_chart(fig_line, use_container_width=True)
            else: st.info("No hay datos recientes.")
        else: st.info("Sin datos de asistencia.")

    with c_g2:
        st.markdown("### 📍 Sedes")
        if not df_s.empty:
            activos_df = df_s[df_s['activo']==1]
            dist_sede = activos_df['sede'].value_counts().reset_index()
            fig_donut = px.pie(dist_sede, values='count', names='sede', hole=0.6, template="plotly_dark",
                               color_discrete_sequence=px.colors.qualitative.Pastel, title="Distribución")
            st.plotly_chart(fig_donut, use_container_width=True)

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
                    f_grupo = c2.selectbox("Grupo", ["Todos"] + sorted(df['grupo'].astype(str).unique().tolist()))
                    f_plan = c3.selectbox("Plan", ["Todos"] + sorted(df['plan'].astype(str).unique().tolist()))
                    f_act = c4.selectbox("Estado", ["Activos", "Inactivos", "Todos"])
                
                df_fil = df.copy()
                if f_sede != "Todas": df_fil = df_fil[df_fil['sede'] == f_sede]
                if f_grupo != "Todos": df_fil = df_fil[df_fil['grupo'] == f_grupo]
                if f_plan != "Todos": df_fil = df_fil[df_fil['plan'] == f_plan]
                if f_act == "Activos": df_fil = df_fil[df_fil['activo'] == 1]
                elif f_act == "Inactivos": df_fil = df_fil[df_fil['activo'] == 0]
                
                st.caption(f"Resultados: {len(df_fil)}")
                
                for idx, row in df_fil.iterrows():
                    with st.container():
                        k1, k2, k3, k4, k5 = st.columns([3, 2, 2, 2, 1])
                        k1.markdown(f"**{row['nombre']} {row['apellido']}**")
                        k2.caption(row['sede'])
                        k3.caption(row.get('grupo', '-'))
                        k4.caption(row['plan'])
                        if k5.button("Ver ➜", key=f"v_{row['id']}"):
                            st.session_state["view_profile_id"] = row['id']
                            st.rerun()
                        st.divider()

        with tab_new:
            st.subheader("Alta Rápida")
            with st.form("alta_rapida"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nombre")
                ape = c2.text_input("Apellido")
                dni = c1.text_input("DNI")
                nac = c2.date_input("Nacimiento", min_value=date(1980,1,1))
                sede = st.selectbox("Sede", ["Sede C1", "Sede Saa"])
                grupo = st.selectbox("Grupo", ["Infantil", "Juvenil", "Adulto"])
                if st.form_submit_button("Guardar"):
                    if nom and ape:
                        uid = int(datetime.now().timestamp())
                        row = [uid, str(get_today_ar()), nom, ape, dni, str(nac), "", "", "", sede, "General", "", user, 1, "", grupo, 0, 0]
                        save_row("socios", row)
                        log_action(uid, "Alta Alumno", "Alta desde sistema", user)
                        st.success("Guardado")
    
    else:
        uid = st.session_state["view_profile_id"]
        df = get_df("socios")
        p = df[df['id'] == uid].iloc[0]
        
        if st.button("⬅️ Volver al Directorio"):
            st.session_state["view_profile_id"] = None
            st.rerun()
            
        st.title(f"👤 {p['nombre']} {p['apellido']}")
        
        if p.get('whatsapp'):
            tel = str(p['whatsapp']).replace('+', '').replace(' ', '')
            msg_pago = f"Hola {p['nombre']}, te recordamos que tu cuota vence pronto. Saludos Area Arqueros."
            link_wa = f"https://wa.me/{tel}?text={msg_pago.replace(' ', '%20')}"
            st.link_button("📱 Enviar Recordatorio", link_wa)
        
        c_h1, c_h2, c_h3 = st.columns(3)
        edad = calcular_edad(p['fecha_nacimiento'])
        c_h1.info(f"**DNI:** {p['dni']} | **Edad:** {edad}")
        c_h2.success(f"**Plan:** {p.get('plan','-')} | **Sede:** {p['sede']}")
        c_h3.warning(f"**Grupo:** {p.get('grupo','-')}")
        
        t_data, t_hist, t_log = st.tabs(["✏️ Datos Personales", "📅 Asistencias", "🔒 Auditoría"])
        
        with t_data:
            if rol == "Administrador":
                with st.form("edit_p"):
                    e1, e2 = st.columns(2)
                    n_nom = e1.text_input("Nombre", p['nombre'])
                    n_ape = e2.text_input("Apellido", p['apellido'])
                    n_dni = e1.text_input("DNI", p['dni'])
                    
                    df_tar = get_df("tarifas")
                    planes_list = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                    curr_idx = planes_list.index(p['plan']) if p['plan'] in planes_list else 0
                    n_plan = e2.selectbox("Plan", planes_list, index=curr_idx)
                    
                    n_notas = st.text_area("Notas", p.get('notas',''))
                    n_act = st.checkbox("Activo", value=True if p['activo']==1 else False)
                    if st.form_submit_button("Guardar Cambios"):
                        d_upd = p.to_dict()
                        d_upd.update({'nombre': n_nom, 'apellido': n_ape, 'dni': n_dni, 'plan': n_plan, 'notas': n_notas, 'activo': 1 if n_act else 0})
                        update_full_socio(uid, d_upd, user, original_data=p.to_dict())
                        st.success("Actualizado")
                        time.sleep(1); st.rerun()
            else: st.info("Modo Lectura")

        with t_hist:
            df_a = get_df("asistencias")
            if not df_a.empty:
                mis_a = df_a[df_a['id_socio'] == uid]
                st.metric("Total Clases", len(mis_a))
                st.dataframe(mis_a[['fecha', 'sede', 'turno']].sort_values('fecha', ascending=False), use_container_width=True)

        with t_log:
            df_l = get_df("logs")
            if not df_l.empty and 'id_ref' in df_l.columns:
                mis_l = df_l[df_l['id_ref'].astype(str) == str(uid)]
                if not mis_l.empty: st.dataframe(mis_l[['fecha', 'usuario', 'accion', 'detalle']], use_container_width=True)
                else: st.info("Sin registros.")
            else: st.info("Hoja de logs vacía.")

elif nav == "Asistencia":
    st.title("✅ Tomar Asistencia")
    c1, c2 = st.columns(2)
    sede_sel = c1.selectbox("Sede", ["Sede C1", "Sede Saa"])
    grupo_sel = c2.selectbox("Grupo", ["Infantil", "Juvenil", "Adulto"])
    df = get_df("socios")
    if not df.empty and 'grupo' in df.columns:
        filtro = df[(df['sede'] == sede_sel) & (df['grupo'] == grupo_sel) & (df['activo'] == 1)]
        if not filtro.empty:
            with st.form("lista"):
                cols = st.columns(3)
                checks = {}
                for i, (idx, r) in enumerate(filtro.iterrows()):
                    checks[r['id']] = cols[i%3].checkbox(f"{r['nombre']} {r['apellido']}", key=r['id'])
                if st.form_submit_button("Guardar"):
                    cnt = 0
                    for uid, p in checks.items():
                        if p:
                            n = filtro.loc[filtro['id']==uid, 'nombre'].values[0]
                            a = filtro.loc[filtro['id']==uid, 'apellido'].values[0]
                            row = [str(get_today_ar()), datetime.now().strftime("%H:%M"), uid, f"{n} {a}", sede_sel, grupo_sel, "Presente"]
                            save_row("asistencias", row)
                            cnt+=1
                    st.success(f"{cnt} presentes.")
        else: st.warning("Sin alumnos.")

elif nav == "Contabilidad":
    st.title("📒 Contabilidad")
    
    with st.sidebar:
        st.markdown("### 🔍 Filtros")
        f_sede = st.multiselect("Sede", ["Sede C1", "Sede Saa"], default=["Sede C1", "Sede Saa"])
        f_mes = st.selectbox("Mes", ["Todos"] + MESES)
        f_rango1 = st.date_input("Desde", date(date.today().year, 1, 1))
        f_rango2 = st.date_input("Hasta", date.today())
        
    tab_cuotas, tab_ocasional, tab_rep = st.tabs(["📋 Gestión de Cuotas", "🛍️ Ocasionales", "📊 Caja & Reportes"])
    
    with tab_cuotas:
        # --- LÓGICA INTELIGENTE DE DÍA DE CORTE ---
        # Recuperar día de corte desde Configuración (Default: 19)
        try:
            dia_corte = int(get_config_value("dia_corte", 19))
        except: dia_corte = 19
        
        hoy_ar = get_today_ar()
        dia_actual = hoy_ar.day
        mes_actual_idx = hoy_ar.month - 1
        
        if dia_actual >= dia_corte:
            target_idx = (mes_actual_idx + 1) % 12
            year_target = hoy_ar.year + 1 if mes_actual_idx == 11 else hoy_ar.year
        else:
            target_idx = mes_actual_idx
            year_target = hoy_ar.year
            
        mes_target = MESES[target_idx]
        
        st.info(f"🗓️ Período Sugerido: **{mes_target} {year_target}** (Día de corte configurado: {dia_corte})")
        
        col_gen, col_cob = st.columns(2)
        df_pag = get_df("pagos")
        df_soc = get_df("socios")
        df_tar = get_df("tarifas")
        tarifas_list = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
        
        with col_gen:
            st.markdown(f"#### ⚠️ Falta Generar ({mes_target})")
            pagaron_target = []
            if not df_pag.empty and 'mes_cobrado' in df_pag.columns:
                pagos_filt = df_pag[ (df_pag['mes_cobrado'] == mes_target) & (df_pag['concepto'].astype(str).str.contains("Cuota")) ]
                pagaron_target = pagos_filt['id_socio'].unique()
            
            pendientes_gen = pd.DataFrame()
            if not df_soc.empty:
                pendientes_gen = df_soc[ (df_soc['activo']==1) & (~df_soc['id'].isin(pagaron_target)) ]
            
            if not pendientes_gen.empty:
                opciones_directo = pendientes_gen.apply(lambda x: f"{x['id']} - {x['nombre']} {x['apellido']} ({x['plan']})", axis=1)
                sel_directo = st.selectbox("Seleccionar para Cobro Directo", ["-- Seleccionar --"] + opciones_directo.tolist())
                
                if sel_directo != "-- Seleccionar --":
                    id_dir = int(sel_directo.split(" - ")[0])
                    p_data = pendientes_gen[pendientes_gen['id']==id_dir].iloc[0]
                    
                    st.info(f"Cobrando a **{p_data['nombre']}** mes **{mes_target}**")
                    with st.form("form_cobro_directo"):
                        precio_sug = 0.0
                        if not df_tar.empty and p_data['plan'] in tarifas_list:
                            try: precio_sug = float(df_tar[df_tar['concepto']==p_data['plan']]['valor'].values[0])
                            except: pass
                        
                        c_f1, c_f2 = st.columns(2)
                        n_concepto = c_f1.selectbox("Plan/Tarifa", tarifas_list, index=tarifas_list.index(p_data['plan']) if p_data['plan'] in tarifas_list else 0)
                        n_monto = c_f2.number_input("Monto", value=precio_sug, step=100.0)
                        n_metodo = st.selectbox("Medio Pago", ["Efectivo", "Transferencia", "MercadoPago"])
                        
                        if st.form_submit_button("✅ Registrar Pago y Actualizar Perfil"):
                            if n_concepto != p_data['plan']:
                                update_plan_socio(id_dir, n_concepto)
                            
                            row = [
                                int(datetime.now().timestamp()), str(get_today_ar()), 
                                id_dir, f"{p_data['nombre']} {p_data['apellido']}", 
                                n_monto, n_concepto, n_metodo, "Cobro Directo", 
                                "Confirmado", user, mes_target
                            ]
                            save_row("pagos", row)
                            st.success("Pago registrado.")
                            time.sleep(1); st.rerun()
                
                st.markdown("---")
                if st.button(f"🚀 Generar Deuda Pendiente ({len(pendientes_gen)} alumnos)"):
                    count = 0
                    for idx, row_s in pendientes_gen.iterrows():
                        precio = 15000 
                        if not df_tar.empty and row_s['plan'] in df_tar['concepto'].values:
                            precio = df_tar[df_tar['concepto']==row_s['plan']]['valor'].values[0]
                        
                        row_p = [
                            int(datetime.now().timestamp())+count, str(get_today_ar()), 
                            row_s['id'], f"{row_s['nombre']} {row_s['apellido']}", 
                            precio, row_s['plan'], "Pendiente", f"Plan: {row_s['plan']}", 
                            "Pendiente", "Sistema Auto", mes_target
                        ]
                        save_row("pagos", row_p)
                        count+=1
                    st.success(f"Generadas {count} deudas.")
                    time.sleep(1); st.rerun()
            else: st.success("Todos al día.")

        with col_cob:
            st.markdown("#### 💰 Deudas Generadas")
            deudas_pend = pd.DataFrame()
            if not df_pag.empty and "estado" in df_pag.columns:
                deudas_pend = df_pag[df_pag['estado'] == "Pendiente"]
            
            if not deudas_pend.empty:
                opciones_pago = deudas_pend.apply(lambda x: f"{x['mes_cobrado']} - {x['nombre_socio']} (${x['monto']})", axis=1)
                sel_deuda = st.selectbox("Seleccionar Deuda", opciones_pago)
                
                if sel_deuda:
                    idx_sel = opciones_pago.values.tolist().index(sel_deuda)
                    dato_pago = deudas_pend.iloc[idx_sel]
                    
                    st.info(f"**{dato_pago['concepto']}** ({dato_pago['mes_cobrado']})")
                    with st.form("form_cobro_deuda"):
                        c_edit1, c_edit2 = st.columns(2)
                        new_conc = c_edit1.selectbox("Tarifa", tarifas_list, index=tarifas_list.index(dato_pago['concepto']) if dato_pago['concepto'] in tarifas_list else 0)
                        new_mont = c_edit2.number_input("Monto", value=float(dato_pago['monto']))
                        new_met = st.selectbox("Medio", ["Efectivo", "Transferencia", "MercadoPago"])
                        
                        if st.form_submit_button("✅ Confirmar Pago"):
                            if new_conc != dato_pago['concepto']:
                                update_plan_socio(dato_pago['id_socio'], new_conc)
                            
                            if registrar_pago_existente(dato_pago['id'], new_met, user, new_mont, new_conc):
                                st.success("Cobrado.")
                                datos_pdf = {
                                    "fecha": str(get_today_ar()), "alumno": dato_pago['nombre_socio'],
                                    "monto": new_mont, "concepto": new_conc, "metodo": new_met, "mes": dato_pago['mes_cobrado']
                                }
                                pdf_bytes = generar_pdf(datos_pdf)
                                b64 = base64.b64encode(pdf_bytes).decode()
                                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Recibo.pdf" style="text-decoration:none;"><button style="background-color:#2196F3;color:white;border:none;padding:5px;border-radius:5px;">📄 Recibo PDF</button></a>'
                                st.markdown(href, unsafe_allow_html=True)
                                time.sleep(3); st.rerun()
            else: st.info("No hay deudas.")

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
                if st.form_submit_button("Registrar"):
                    row = [
                        int(datetime.now().timestamp()), str(get_today_ar()), 
                        int(sel.split(" - ")[0]), sel.split(" - ")[1], 
                        monto, concepto, metodo, "Ocasional", 
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

elif nav == "Configuración":
    st.title("⚙️ Configuración del Sistema")
    
    tab_gen, tab_tar = st.tabs(["🔧 General", "💲 Tarifas"])
    
    with tab_gen:
        st.subheader("Parámetros de Facturación")
        dia_actual = int(get_config_value("dia_corte", 19))
        nuevo_dia = st.slider("Día de Corte (Generación de Cuota)", 1, 28, dia_actual)
        if st.button("Guardar Configuración General"):
            set_config_value("dia_corte", nuevo_dia)
            st.success(f"Día de corte actualizado a: {nuevo_dia}")
            
    with tab_tar:
        st.subheader("Lista de Precios")
        df = get_df("tarifas")
        edited = st.data_editor(df, num_rows="dynamic")
        if st.button("Guardar Tarifas"):
            actualizar_tarifas_bulk(edited)
            st.success("Tarifas guardadas")
