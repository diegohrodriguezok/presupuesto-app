import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, timedelta
import plotly.express as px
import time
from fpdf import FPDF
import base64
import pytz
import uuid
import bcrypt

# ==========================================
# 1. CONFIGURACIÓN Y CONSTANTES
# ==========================================
st.set_page_config(
    page_title="Area Arqueros ERP", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="🏹"
)

# Constantes de Negocio
SEDES = ["Sede C1", "Sede Saa"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
TALLES = ["10", "12", "14", "XS", "S", "M", "L", "XL"]
GRUPOS_GEN = ["Infantil", "Prejuvenil", "Juvenil", "Adulto", "Senior", "Amateur"]

# Esquema de Columnas Requeridas (Para evitar KeyErrors)
REQUIRED_COLS = {
    "socios": ['id', 'fecha_alta', 'nombre', 'apellido', 'dni', 'fecha_nacimiento', 'tutor', 'whatsapp', 'email', 'sede', 'plan', 'notas', 'vendedor', 'activo', 'talle', 'grupo', 'peso', 'altura'],
    "pagos": ['id', 'fecha_pago', 'id_socio', 'nombre_socio', 'monto', 'concepto', 'metodo', 'comentarios', 'estado', 'usuario_registro', 'mes_cobrado'],
    "entrenamientos_plantilla": ['id', 'sede', 'dia', 'horario', 'grupo', 'entrenador_asignado', 'cupo_max'],
    "inscripciones": ['id', 'id_socio', 'nombre_alumno', 'id_entrenamiento', 'detalle'],
    "asistencias": ['fecha', 'hora', 'id_socio', 'nombre_alumno', 'sede', 'grupo_turno', 'estado', 'nota'],
    "usuarios": ['id_usuario', 'user', 'pass_hash', 'rol', 'nombre_completo', 'sedes_acceso', 'activo'],
    "config": ['clave', 'valor'],
    "tarifas": ['concepto', 'valor'],
    "logs": ['fecha', 'usuario', 'id_ref', 'accion', 'detalle']
}

# --- CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; color: #212529; }
    .stButton>button { border-radius: 6px; height: 40px; font-weight: 600; border: none; background-color: #1f2c56; color: white !important; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .stButton>button:hover { background-color: #2c3e50; box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
    div[data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700; color: #1f2c56; }
    .stTabs [data-baseweb="tab"] { height: 45px; background-color: #ffffff; color: #555555; border-radius: 8px; border: 1px solid #e0e0e0; }
    .stTabs [aria-selected="true"] { background-color: #1f2c56 !important; color: #ffffff !important; }
    .student-card { padding: 15px; background-color: white; border-radius: 8px; border: 1px solid #e0e0e0; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .status-active { color: #28a745; font-weight: bold; }
    .status-inactive { color: #dc3545; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. MOTOR DE BASE DE DATOS (BLINDADO)
# ==========================================
@st.cache_resource
def get_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("BaseDatos_ClubArqueros")
    except Exception as e:
        st.error(f"❌ Error crítico de conexión con Google: {e}")
        st.stop()

def get_df(sheet_name):
    """Lee una hoja y asegura que tenga las columnas mínimas para no romperse."""
    try:
        client = get_client()
        # Intentar abrir la hoja, si no existe, devolver DF vacío seguro
        try:
            ws = client.worksheet(sheet_name)
            data = ws.get_all_records()
            df = pd.DataFrame(data)
        except gspread.WorksheetNotFound:
            return pd.DataFrame(columns=REQUIRED_COLS.get(sheet_name, []))
            
        if not df.empty:
            # Normalizar nombres de columnas (minúsculas y sin espacios)
            df.columns = df.columns.str.strip().str.lower()
            
            # Rellenar columnas faltantes con valores vacíos para evitar KeyErrors
            if sheet_name in REQUIRED_COLS:
                for col in REQUIRED_COLS[sheet_name]:
                    if col not in df.columns:
                        df[col] = "" 
        return df
    except Exception:
        return pd.DataFrame(columns=REQUIRED_COLS.get(sheet_name, []))

def save_row(sheet_name, data):
    """Guarda una fila al final de la hoja."""
    try:
        ws = get_client().worksheet(sheet_name)
        ws.append_row(data)
        return True
    except: return False

def save_rows_bulk(sheet_name, data_list):
    """Guarda múltiples filas."""
    try:
        ws = get_client().worksheet(sheet_name)
        ws.append_rows(data_list)
        return True
    except: return False

def update_cell_value(sheet_name, id_val, col_idx, new_val):
    """Actualiza una celda buscando por ID (columna 1)."""
    try:
        ws = get_client().worksheet(sheet_name)
        cell = ws.find(str(id_val))
        ws.update_cell(cell.row, col_idx, new_val)
        return True
    except: return False

# --- UTILIDADES ---
def get_now_ar():
    try: return datetime.now(pytz.timezone('America/Argentina/Buenos_Aires'))
    except: return datetime.now()

def get_today_ar(): return get_now_ar().date()
def generate_id(): return int(f"{int(time.time())}{uuid.uuid4().int % 1000}")

# ==========================================
# 3. SEGURIDAD Y SESIÓN
# ==========================================
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None, "view_profile_id": None, "cobro_alumno_id": None})

def check_password(password, hashed):
    try: return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except: return False

def login_page():
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.markdown("## 🔐 Acceso al Sistema")
        with st.form("login"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar"):
                # 1. Intentar DB Real
                df_users = get_df("usuarios")
                logged = False
                if not df_users.empty and 'user' in df_users.columns:
                    user_match = df_users[df_users['user'] == u]
                    if not user_match.empty:
                        stored_hash = user_match.iloc[0]['pass_hash']
                        if check_password(p, stored_hash):
                             st.session_state.update({"auth": True, "user": user_match.iloc[0]['nombre_completo'], "rol": user_match.iloc[0]['rol']})
                             logged = True
                             st.rerun()
                
                # 2. Fallback Secrets (Emergencia)
                if not logged:
                    try:
                        S_USERS = st.secrets["users"]
                        if u in S_USERS and str(S_USERS[u]["p"]) == p:
                             st.session_state.update({"auth": True, "user": u, "rol": S_USERS[u]["r"]})
                             st.warning("⚠️ Usando credenciales de emergencia.")
                             time.sleep(1); st.rerun()
                        else: st.error("Credenciales incorrectas.")
                    except: st.error("Error de autenticación.")

if not st.session_state["auth"]:
    login_page()
    st.stop()

# ==========================================
# 4. INTERFAZ PRINCIPAL
# ==========================================
user, rol = st.session_state["user"], st.session_state["rol"]

with st.sidebar:
    try: st.image("logo.png", width=200)
    except: st.header("🛡️ CLUB ARQUEROS")
    st.info(f"Hola, **{user}** ({rol})")
    
    menu = ["Dashboard"]
    if rol in ["Administrador", "Profesor"]: menu.extend(["Alumnos", "Asistencia", "Entrenamientos"])
    if rol in ["Administrador", "Contador"]: menu.extend(["Contabilidad", "Configuración"])
    if rol == "Administrador": menu.append("Diagnóstico") # Herramienta de reparación
    
    nav = st.radio("Ir a:", menu)
    st.divider()
    if st.button("Cerrar Sesión"):
        st.session_state.clear()
        st.rerun()

# ==========================================
# 5. MÓDULOS
# ==========================================

# --- DASHBOARD ---
if nav == "Dashboard":
    st.title("📊 Tablero de Comando")
    df_soc = get_df("socios")
    df_pag = get_df("pagos")
    df_asi = get_df("asistencias")
    
    c1, c2, c3 = st.columns(3)
    activos = len(df_soc[df_soc['activo']==1]) if not df_soc.empty else 0
    c1.metric("Alumnos Activos", activos)
    
    ingresos = 0
    if not df_pag.empty:
        # Filtro de mes actual seguro
        hoy = get_today_ar()
        df_pag['dt'] = pd.to_datetime(df_pag['fecha_pago'], errors='coerce')
        mes_actual = df_pag[ (df_pag['dt'].dt.month == hoy.month) & (df_pag['dt'].dt.year == hoy.year) & (df_pag['estado'] == 'Confirmado') ]
        ingresos = pd.to_numeric(mes_actual['monto'], errors='coerce').sum()
    c2.metric("Ingresos Mes", f"${ingresos:,.0f}")
    
    asistencias_hoy = 0
    if not df_asi.empty:
        asistencias_hoy = len(df_asi[df_asi['fecha'] == str(get_today_ar())])
    c3.metric("Presentes Hoy", asistencias_hoy)

# --- ALUMNOS ---
elif nav == "Alumnos":
    # VISTA 1: LISTADO
    if st.session_state["view_profile_id"] is None:
        st.title("👥 Gestión de Alumnos")
        
        tab1, tab2 = st.tabs(["📂 Directorio", "➕ Nuevo Alumno"])
        
        with tab1:
            df = get_df("socios")
            if not df.empty:
                # Filtros
                c1, c2 = st.columns([3, 1])
                search = c1.text_input("🔍 Buscar por Nombre o DNI", placeholder="Escribe para buscar...")
                filtro_act = c2.selectbox("Estado", ["Activos", "Todos", "Inactivos"])
                
                # Lógica de Filtrado
                mask = pd.Series([True] * len(df))
                if filtro_act == "Activos": mask = mask & (df['activo'] == 1)
                if filtro_act == "Inactivos": mask = mask & (df['activo'] == 0)
                if search:
                    mask = mask & df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
                
                df_show = df[mask]
                st.caption(f"Mostrando {len(df_show)} alumnos")
                
                # Renderizado de Tarjetas
                for idx, row in df_show.head(50).iterrows():
                    with st.container():
                        col_txt, col_btn = st.columns([5, 1])
                        status = "🟢" if row['activo'] == 1 else "🔴"
                        # Diseño de tarjeta
                        info_text = f"**{row['nombre']} {row['apellido']}** | DNI: {row['dni']} | {row.get('sede', '-')}"
                        col_txt.markdown(f"{status} {info_text}")
                        
                        # Botón de acción
                        if col_btn.button("Ver Ficha", key=f"btn_{row['id']}"):
                            st.session_state["view_profile_id"] = row['id']
                            st.rerun()
                        st.divider()
            else:
                st.info("No hay alumnos cargados en el sistema.")

        with tab2:
            st.subheader("Inscripción Completa")
            with st.form("new_student"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nombre")
                ape = c2.text_input("Apellido")
                dni = c1.text_input("DNI")
                nac = c2.date_input("Fecha Nacimiento", date(2000,1,1))
                
                st.markdown("---")
                c3, c4 = st.columns(2)
                sede = c3.selectbox("Sede", SEDES)
                # Cargar tarifas para el select
                df_t = get_df("tarifas")
                planes = df_t['concepto'].tolist() if not df_t.empty else ["General"]
                plan = c4.selectbox("Plan", planes)
                
                grupo = c3.selectbox("Categoría", GRUPOS_GEN)
                talle = c4.selectbox("Talle", TALLES)
                
                st.markdown("---")
                email = st.text_input("Email")
                wsp = st.text_input("WhatsApp")
                tutor = st.text_input("Tutor / Responsable")
                
                c5, c6 = st.columns(2)
                peso = c5.number_input("Peso", 0.0)
                alt = c6.number_input("Altura", 0)
                
                if st.form_submit_button("💾 Guardar Alumno"):
                    if nom and ape and dni:
                        uid = generate_id()
                        # Orden estricto según REQUIRED_COLS['socios']
                        # id, fecha, nom, ape, dni, nac, tutor, wsp, email, sede, plan, notas, vend, act, talle, grupo, peso, alt
                        row = [
                            uid, str(get_today_ar()), nom, ape, dni, str(nac),
                            tutor, wsp, email, sede, plan, "", user, 1, talle, grupo, peso, alt
                        ]
                        if save_row("socios", row):
                            st.success("Alumno creado correctamente.")
                            time.sleep(1); st.rerun()
                        else: st.error("Error al guardar en Google Sheets.")
                    else: st.warning("Faltan datos obligatorios.")

    # VISTA 2: PERFIL DETALLADO
    else:
        uid = st.session_state["view_profile_id"]
        df = get_df("socios")
        # Verificar si existe
        p_data = df[df['id'] == uid]
        
        if not p_data.empty:
            p = p_data.iloc[0]
            
            if st.button("⬅️ Volver al Listado"):
                st.session_state["view_profile_id"] = None
                st.rerun()
            
            st.title(f"{p['nombre']} {p['apellido']}")
            st.caption(f"DNI: {p['dni']} | ID: {uid}")
            
            t1, t2, t3 = st.tabs(["✏️ Datos & Ficha", "📅 Historial", "💳 Pagos"])
            
            with t1:
                if rol == "Administrador":
                    with st.form("edit_student"):
                        c1, c2 = st.columns(2)
                        n_nom = c1.text_input("Nombre", p['nombre'])
                        n_ape = c2.text_input("Apellido", p['apellido'])
                        n_dni = c1.text_input("DNI", p['dni'])
                        n_email = c2.text_input("Email", p.get('email', ''))
                        n_wsp = c1.text_input("WhatsApp", p.get('whatsapp', ''))
                        n_plan = c2.selectbox("Plan", planes, index=planes.index(p['plan']) if p['plan'] in planes else 0)
                        n_act = st.checkbox("Alumno Activo", value=True if p['activo']==1 else False)
                        n_notas = st.text_area("Notas Internas", p.get('notas', ''))
                        
                        if st.form_submit_button("Guardar Cambios"):
                            # Actualizar campos específicos usando update_cell_value por seguridad
                            # Buscamos la fila
                            ws = get_client().worksheet("socios")
                            cell = ws.find(str(uid))
                            r = cell.row
                            # Actualizamos columnas clave (ajustar índices según orden real)
                            ws.update_cell(r, 3, n_nom) # Nombre
                            ws.update_cell(r, 4, n_ape) # Apellido
                            ws.update_cell(r, 5, n_dni) # DNI
                            ws.update_cell(r, 8, n_wsp) # Wsp
                            ws.update_cell(r, 9, n_email) # Email
                            ws.update_cell(r, 11, n_plan) # Plan
                            ws.update_cell(r, 12, n_notas) # Notas
                            ws.update_cell(r, 14, 1 if n_act else 0) # Activo
                            
                            st.success("Perfil actualizado.")
                            time.sleep(1); st.rerun()
                else:
                    st.info("Modo Lectura (Solo Admin puede editar)")
                    st.write(f"**Plan:** {p.get('plan')}")
                    st.write(f"**Sede:** {p.get('sede')}")

            with t2:
                # Asistencias
                df_a = get_df("asistencias")
                if not df_a.empty:
                    mis_a = df_a[df_a['id_socio'] == uid]
                    st.metric("Total Clases", len(mis_a))
                    st.dataframe(mis_a[['fecha', 'sede', 'grupo_turno', 'estado']], use_container_width=True)
                else: st.info("Sin historial de asistencia.")
            
            with t3:
                # Pagos
                df_p = get_df("pagos")
                if not df_p.empty:
                    mis_p = df_p[df_p['id_socio'] == uid]
                    st.dataframe(mis_p[['fecha_pago', 'monto', 'concepto', 'mes_cobrado', 'estado']], use_container_width=True)
                else: st.info("Sin historial de pagos.")
        else:
            st.error("Error: Alumno no encontrado en la base de datos.")
            if st.button("Volver"):
                st.session_state["view_profile_id"] = None
                st.rerun()

# === CONTABILIDAD (SIMPLIFICADA Y SEGURA) ===
elif nav == "Contabilidad":
    st.title("📒 Finanzas")
    
    tab_pay, tab_auto = st.tabs(["💰 Registrar Pago", "⚙️ Generación Masiva"])
    
    with tab_pay:
        df_soc = get_df("socios")
        if not df_soc.empty:
            activos = df_soc[df_soc['activo'] == 1]
            # Selector de alumno
            alu_sel = st.selectbox("Seleccionar Alumno", activos['id'].astype(str) + " - " + activos['nombre'] + " " + activos['apellido'])
            uid_pay = int(alu_sel.split(" - ")[0])
            
            with st.form("new_pay"):
                c1, c2 = st.columns(2)
                # Conceptos
                df_tar = get_df("tarifas")
                conceptos = df_tar['concepto'].tolist() if not df_tar.empty else ["Cuota"]
                conc = c1.selectbox("Concepto", conceptos)
                
                # Precio sugerido
                price = 0.0
                if not df_tar.empty:
                    match = df_tar[df_tar['concepto'] == conc]
                    if not match.empty: 
                         try: price = float(str(match.iloc[0]['valor']).replace('$',''))
                         except: pass
                
                monto = c2.number_input("Monto", value=price)
                metodo = st.selectbox("Medio", ["Efectivo", "Transferencia", "MP"])
                mes = st.selectbox("Mes Correspondiente", MESES)
                
                if st.form_submit_button("Registrar Pago"):
                    # id, fecha, id_soc, nom, monto, conc, met, coment, estado, user, mes
                    row = [generate_id(), str(get_today_ar()), uid_pay, alu_sel.split("-")[1], monto, conc, metodo, "", "Confirmado", user, mes]
                    save_row("pagos", row)
                    st.success("Pago registrado.")
    
    with tab_auto:
        st.info("Esta herramienta genera las deudas pendientes para el mes actual.")
        if st.button("🔍 Buscar Deudores y Generar Cuotas"):
            # Lógica simplificada para evitar loops infinitos
            # 1. Obtener activos
            # 2. Chequear quién no tiene pago 'Cuota' este mes
            # 3. Generar
            st.warning("Funcionalidad en mantenimiento para evitar duplicados.")

# === ASISTENCIA ===
elif nav == "Asistencia":
    st.title("✅ Asistencia")
    # Versión estable: Selección manual simple
    c1, c2 = st.columns(2)
    sede = c1.selectbox("Sede", SEDES)
    grupo = c2.selectbox("Grupo", GRUPOS_GEN)
    
    df_s = get_df("socios")
    if not df_s.empty:
        # Filtro
        lista = df_s[ (df_s['sede']==sede) & (df_s['grupo']==grupo) & (df_s['activo']==1) ]
        
        if not lista.empty:
            with st.form("take_att"):
                st.write(f"Alumnos en **{sede} - {grupo}**")
                checks = {}
                cols = st.columns(3)
                for i, (idx, row) in enumerate(lista.iterrows()):
                    checks[row['id']] = cols[i%3].checkbox(f"{row['nombre']} {row['apellido']}", key=row['id'])
                
                if st.form_submit_button("Guardar"):
                    cnt = 0
                    for uid, p in checks.items():
                        if p:
                            nom = lista[lista['id']==uid].iloc[0]['nombre']
                            save_row("asistencias", [str(get_today_ar()), datetime.now().strftime("%H:%M"), uid, nom, sede, grupo, "Presente", ""])
                            cnt += 1
                    st.success(f"{cnt} presentes guardados.")
        else:
            st.warning("No hay alumnos en este grupo.")

# === ENTRENAMIENTOS ===
elif nav == "Entrenamientos":
    st.title("⚽ Configuración de Grupos")
    st.info("Módulo en construcción. Use la sección 'Asistencia' para tomar lista por ahora.")

# === DIAGNÓSTICO (NUEVO) ===
elif nav == "Diagnóstico":
    st.title("🔧 Diagnóstico del Sistema")
    st.info("Use esto si ve errores raros o faltan datos.")
    
    col_sheets = ["socios", "pagos", "usuarios", "tarifas", "entrenamientos_plantilla"]
    for sheet in col_sheets:
        df = get_df(sheet)
        st.write(f"**Hoja: {sheet}** - {len(df)} filas")
        st.text(f"Columnas detectadas: {list(df.columns)}")
        if df.empty:
            st.error(f"⚠️ La hoja '{sheet}' está vacía o no se pudo leer.")
