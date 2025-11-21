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
import bcrypt

# ==========================================
# 1. CONFIGURACIÓN GLOBAL Y ESTILOS
# ==========================================
st.set_page_config(
    page_title="Area Arqueros ERP", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="logo.png"
)

# --- CARGAR CSS EXTERNO ---
def local_css(file_name):
    try:
        with open(file_name) as f: st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except: pass

local_css("style.css")

# --- FUNCIONES DE TIEMPO ARGENTINA (UTC-3) ---
def get_now_ar():
    try:
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        return datetime.now(tz)
    except:
        return datetime.now()

def get_today_ar():
    return get_now_ar().date()

def traducir_dia(fecha_dt):
    dias = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    return dias[fecha_dt.weekday()]

# --- CONSTANTES DEL SISTEMA ---
SEDES = ["Sede C1", "Sede Saa"]
GRUPOS_GEN = ["Infantil", "Prejuvenil", "Juvenil", "Adulto", "Senior", "Amateur"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
TALLES = ["10", "12", "14", "XS", "S", "M", "L", "XL"]
DEF_MOTIVOS = ["Enfermedad", "Viaje", "Sin Aviso", "Lesión", "Estudio"]

# ==========================================
# 2. MOTOR DE BASE DE DATOS
# ==========================================
@st.cache_resource
def get_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds).open("BaseDatos_ClubArqueros")
    except Exception as e:
        st.error(f"❌ Error crítico de conexión: {e}")
        st.stop()

def get_df(sheet_name):
    """Lectura robusta de datos con normalización"""
    try:
        ws = get_client().worksheet(sheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            # Normalizar nombres de columnas
            df.columns = df.columns.str.strip().str.lower()
            
            # Definición de columnas requeridas para evitar KeyError
            cols_required = {
                'socios': ['id', 'nombre', 'apellido', 'dni', 'sede', 'grupo', 'plan', 'activo', 'email', 'whatsapp', 'talle', 'peso', 'altura', 'tutor', 'notas', 'fecha_nacimiento'],
                'pagos': ['id', 'id_socio', 'monto', 'mes_cobrado', 'estado', 'concepto', 'fecha_pago', 'metodo', 'nombre_socio'],
                'entrenamientos_plantilla': ['id', 'sede', 'dia', 'horario', 'grupo', 'entrenador_asignado', 'cupo_max'],
                'inscripciones': ['id_socio', 'id_entrenamiento', 'nombre_alumno'],
                'usuarios': ['user', 'pass_hash', 'rol', 'nombre_completo', 'sedes_acceso', 'activo'],
                'listas': ['tipo', 'valor'],
                'tarifas': ['concepto', 'valor'],
                'logs': ['fecha', 'usuario', 'id_ref', 'accion', 'detalle'],
                'config': ['clave', 'valor']
            }
            
            if sheet_name in cols_required:
                for col in cols_required[sheet_name]:
                    if col not in df.columns:
                        df[col] = ""
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

def update_cell_value(sheet_name, id_val, col_idx, new_val):
    """Actualiza una celda buscando por ID (columna 1)"""
    try:
        ws = get_client().worksheet(sheet_name)
        cell = ws.find(str(id_val))
        ws.update_cell(cell.row, col_idx, new_val)
        return True
    except: return False

def generate_id():
    return int(f"{int(time.time())}{uuid.uuid4().int % 1000}")

def log_action(id_ref, accion, detalle, user):
    try:
        row = [str(get_now_ar()), user, str(id_ref), accion, detalle]
        save_row("logs", row)
    except: pass

# ==========================================
# 3. LÓGICA DE NEGOCIO
# ==========================================

def get_lista_opciones(tipo, default_list):
    """Obtiene listas dinámicas desde la hoja 'listas'"""
    df = get_df("listas")
    if not df.empty and 'tipo' in df.columns:
        items = df[df['tipo'] == tipo]['valor'].tolist()
        if items: return sorted(list(set(items))) # Eliminar duplicados
    return default_list

def check_horario_conflict(id_socio, dia, horario):
    """Evita inscripciones dobles en el mismo horario"""
    df_insc = get_df("inscripciones")
    df_plant = get_df("entrenamientos_plantilla")
    
    if df_insc.empty or df_plant.empty: return False
    
    # Mis inscripciones
    mis_insc = df_insc[df_insc['id_socio'] == id_socio]
    if mis_insc.empty: return False
    
    # Cruzar
    merged = pd.merge(mis_insc, df_plant, left_on='id_entrenamiento', right_on='id')
    choque = merged[ (merged['dia'] == dia) & (merged['horario'] == horario) ]
    
    return not choque.empty

def update_full_socio(id_socio, d, user_admin, original_data=None):
    sh = get_client()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        r = cell.row
        # Mapeo estricto de columnas (Ajustar si cambian en sheet)
        # 1:id, 2:fecha_alta
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
        # 13: vendedor
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
    
    def safe_txt(txt): return str(txt).encode('latin-1', 'replace').decode('latin-1')
    
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Fecha: {safe_txt(datos['fecha'])}", ln=1)
    pdf.cell(200, 10, txt=f"Alumno: {safe_txt(datos['alumno'])}", ln=1)
    pdf.cell(200, 10, txt=f"Concepto: {safe_txt(datos['concepto'])}", ln=1)
    pdf.cell(200, 10, txt=f"Mes: {safe_txt(datos.get('mes', '-'))}", ln=1)
    pdf.cell(200, 10, txt=f"Medio de Pago: {safe_txt(datos['metodo'])}", ln=1)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=f"TOTAL ABONADO: ${datos['monto']}", ln=1, align='C')
    if datos.get('nota'):
        pdf.ln(5)
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(200, 10, txt=f"Nota: {safe_txt(datos['nota'])}", ln=1, align='C')
    pdf.ln(15)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt="Gracias por formar parte de Area Arqueros.", ln=1, align='C')
    return pdf.output(dest="S").encode("latin-1", errors='replace')

# --- INICIALIZACIÓN DE PLANTILLA (C1/SAA) ---
def inicializar_cronograma_realista():
    data_list = []
    # --- C1 ---
    grupos_c1 = ["Infantil 1", "Prejuvenil 1", "Juvenil 1", "Juvenil 2"]
    for d in ["Lunes", "Viernes"]:
        for h in ["18:00 - 19:00", "19:00 - 20:00"]:
            for g in grupos_c1: data_list.append([generate_id(), "Sede C1", d, h, g, "Sin Asignar", 10]); time.sleep(0.001)
    for g in ["Infantil 1", "Prejuvenil 1"]: data_list.append([generate_id(), "Sede C1", "Miércoles", "17:00 - 18:00", g, "Sin Asignar", 10]); time.sleep(0.001)
    for h in ["18:00 - 19:00", "19:00 - 20:00"]:
        for g in grupos_c1: data_list.append([generate_id(), "Sede C1", "Miércoles", h, g, "Sin Asignar", 10]); time.sleep(0.001)
    # --- SAA ---
    dias_saa = ["Lunes", "Miércoles", "Jueves"]
    gr_saa_18 = ["Infantil 1", "Infantil 2", "Prejuvenil 1", "Prejuvenil 2", "Juvenil 1", "Juvenil 2"]
    gr_saa_19 = ["Juvenil 1", "Juvenil 2", "Amateur 1", "Amateur 2", "Senior 1", "Senior 2"]
    for d in dias_saa:
        for g in gr_saa_18: data_list.append([generate_id(), "Sede Saa", d, "18:00 - 19:00", g, "Sin Asignar", 10]); time.sleep(0.001)
        for g in gr_saa_19: data_list.append([generate_id(), "Sede Saa", d, "19:00 - 20:00", g, "Sin Asignar", 10]); time.sleep(0.001)
    save_rows_bulk("entrenamientos_plantilla", data_list)

# ==========================================
# 4. AUTENTICACIÓN Y SESIÓN
# ==========================================
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None, "sedes": []})
if "view_profile_id" not in st.session_state: st.session_state["view_profile_id"] = None
if "cobro_alumno_id" not in st.session_state: st.session_state["cobro_alumno_id"] = None

def login_page():
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        try: st.image("logo.png", width=150)
        except: st.markdown("<h2 style='text-align: center;'>🔐 Area Arqueros</h2>", unsafe_allow_html=True)
        
        # 1. Check de Usuarios
        df_users = get_df("usuarios")
        
        if df_users.empty:
            st.warning("⚠️ Base de usuarios vacía. Cree el Administrador.")
            with st.form("init_admin"):
                nu = st.text_input("User Admin"); np = st.text_input("Pass", type="password")
                if st.form_submit_button("Inicializar"):
                    crear_usuario_real(nu, np, "Administrador", "Super Admin", "Todas")
                    st.success("Creado. Recargue."); time.sleep(2); st.rerun()
            return

        with st.form("login"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar"):
                login_ok = False
                # Intento DB
                if not df_users.empty and 'user' in df_users.columns:
                    match = df_users[df_users['user'] == u]
                    if not match.empty and check_password(p, match.iloc[0]['pass_hash']):
                        udata = match.iloc[0]
                        sedes_acc = str(udata['sedes_acceso']).split(",") if udata['sedes_acceso'] != "Todas" else get_lista_opciones("sede", SEDES)
                        st.session_state.update({"auth": True, "user": udata['nombre_completo'], "rol": udata['rol'], "sedes": sedes_acc})
                        login_ok = True
                        st.rerun()
                
                # Fallback Secrets
                if not login_ok:
                    try:
                        BACKUP = st.secrets["users"]
                        if u in BACKUP and str(BACKUP[u]["p"]) == p:
                             st.session_state.update({"auth": True, "user": u, "rol": BACKUP[u]["r"], "sedes": SEDES})
                             st.warning("⚠️ Modo Respaldo")
                             time.sleep(1); st.rerun()
                        else: st.error("Credenciales inválidas")
                    except: st.error("Error de acceso.")

def logout():
    st.session_state["logged_in"] = False
    st.session_state["auth"] = False
    st.rerun()

if not st.session_state["auth"]:
    login_page(); st.stop()

# ==========================================
# 5. INTERFAZ Y NAVEGACIÓN
# ==========================================
user, rol = st.session_state["user"], st.session_state["rol"]

with st.sidebar:
    try: st.image("logo.png", width=220)
    except: st.header("🛡️ AREA ARQUEROS")
    st.info(f"👤 **{user}**\nRol: {rol}")
    
    menu_opts = ["Dashboard"]
    if rol in ["Administrador", "Profesor", "Entrenador"]:
        menu_opts.extend(["Alumnos", "Entrenamientos", "Asistencia"])
    if rol in ["Administrador", "Contador"]:
        menu_opts.extend(["Contabilidad", "Configuración"])
    if rol == "Administrador":
        menu_opts.append("Usuarios")
    
    nav = st.radio("Navegación", menu_opts)
    if nav != st.session_state.get("last_nav"):
        st.session_state["view_profile_id"] = None
        st.session_state["cobro_alumno_id"] = None
        st.session_state["last_nav"] = nav
    st.divider()
    if st.button("Cerrar Sesión"): logout()

# ==========================================
# 6. MÓDULOS FUNCIONALES
# ==========================================

# === DASHBOARD ===
if nav == "Dashboard":
    st.title("📊 Tablero")
    df_s = get_df("socios")
    df_p = get_df("pagos")
    
    c1, c2 = st.columns(2)
    activos = len(df_s[df_s['activo']==1]) if not df_s.empty else 0
    c1.metric("Alumnos Activos", activos)
    
    ing = 0
    if not df_p.empty:
        df_p['dt'] = pd.to_datetime(df_p['fecha_pago'], errors='coerce')
        mes = df_p[(df_p['dt'].dt.month == get_today_ar().month) & (df_p['estado']=='Confirmado')]
        ing = pd.to_numeric(mes['monto'], errors='coerce').sum()
    c2.metric("Ingresos Mes Actual", f"${ing:,.0f}")

# === ALUMNOS ===
elif nav == "Alumnos":
    # VISTA LISTADO
    if st.session_state["view_profile_id"] is None:
        st.title("👥 Gestión de Alumnos")
        t_dir, t_new = st.tabs(["📂 Directorio", "➕ Nuevo Alumno"])
        
        with t_dir:
            df = get_df("socios")
            if not df.empty:
                with st.expander("🔍 Filtros", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    f_sede = c1.selectbox("Sede", ["Todas"] + get_lista_opciones("sede", SEDES))
                    f_act = c2.selectbox("Estado", ["Activos", "Inactivos", "Todos"])
                    search = c3.text_input("Buscar (Nombre/DNI)")
                
                df_fil = df.copy()
                if f_sede != "Todas": df_fil = df_fil[df_fil['sede'] == f_sede]
                if f_act == "Activos": df_fil = df_fil[df_fil['activo'] == 1]
                elif f_act == "Inactivos": df_fil = df_fil[df_fil['activo'] == 0]
                if search: df_fil = df_fil[df_fil.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
                
                st.caption(f"Resultados: {len(df_fil)}")
                
                rows = 20
                paginas = (len(df_fil) // rows) + 1
                pag = st.number_input("Página", 1, paginas, 1) if paginas > 1 else 1
                start = (pag-1)*rows
                
                for idx, row in df_fil.iloc[start:start+rows].iterrows():
                    icon = "🟢" if row['activo']==1 else "🔴"
                    label = f"{icon} {row['nombre']} {row['apellido']} | DNI: {row['dni']} | {row['sede']} | Plan: {row.get('plan','-')}"
                    if st.button(label, key=f"row_{row['id']}", use_container_width=True):
                        st.session_state["view_profile_id"] = row['id']
                        st.rerun()

        with t_new:
            st.subheader("Alta Completa")
            with st.form("alta"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nombre")
                ape = c2.text_input("Apellido")
                dni = c1.text_input("DNI")
                nac = c2.date_input("Nacimiento", date(2000,1,1))
                sede = st.selectbox("Sede", get_lista_opciones("sede", SEDES))
                grupo_gen = st.selectbox("Categoría", GRUPOS_GEN)
                
                df_tar = get_df("tarifas")
                planes = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                plan = st.selectbox("Plan", planes)
                talle = st.selectbox("Talle", TALLES)
                
                tutor = st.text_input("Tutor")
                wsp = st.text_input("WhatsApp")
                email = st.text_input("Email")
                c3, c4 = st.columns(2)
                peso = c3.number_input("Peso", 0.0)
                alt = c4.number_input("Altura", 0)
                
                if st.form_submit_button("Guardar"):
                    if nom and ape:
                        uid = generate_id()
                        row = [uid, str(get_today_ar()), nom, ape, dni, str(nac), tutor, wsp, email, sede, plan, "", user, 1, talle, grupo_gen, peso, alt]
                        save_row("socios", row)
                        st.success("Alumno registrado.")
                        log_action(uid, "Alta", "Nuevo Alumno", user)
                    else: st.error("Nombre y Apellido requeridos.")

    # VISTA PERFIL
    else:
        uid = st.session_state["view_profile_id"]
        df = get_df("socios")
        if not df.empty:
            p_data = df[df['id'] == uid]
            if not p_data.empty:
                p = p_data.iloc[0]
                if st.button("⬅️ Volver"): 
                    st.session_state["view_profile_id"]=None
                    st.rerun()
                
                st.title(f"👤 {p['nombre']} {p['apellido']}")
                
                t1, t2, t3 = st.tabs(["✏️ Datos", "📅 Asistencia", "💳 Pagos"])
                
                with t1:
                    if rol == "Administrador":
                        with st.form("edit"):
                            c1,c2 = st.columns(2)
                            n_nom = c1.text_input("Nombre", p['nombre'])
                            n_ape = c2.text_input("Apellido", p['apellido'])
                            n_dni = c1.text_input("DNI", p['dni'])
                            n_sede = c2.selectbox("Sede", get_lista_opciones("sede", SEDES), index=0)
                            
                            df_tar = get_df("tarifas")
                            pl = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                            idx = pl.index(p['plan']) if p['plan'] in pl else 0
                            n_plan = st.selectbox("Plan", pl, index=idx)
                            
                            n_act = st.checkbox("Activo", value=True if p['activo']==1 else False)
                            
                            # Campos adicionales
                            n_talle = c1.selectbox("Talle", TALLES, index=TALLES.index(str(p['talle'])) if str(p['talle']) in TALLES else 0)
                            n_peso = c2.number_input("Peso", value=float(p.get('peso') or 0))
                            n_alt = c1.number_input("Altura", value=int(p.get('altura') or 0))
                            n_tutor = c2.text_input("Tutor", p.get('tutor',''))
                            n_email = st.text_input("Email", p.get('email',''))
                            n_notas = st.text_area("Notas", p.get('notas',''))
                            
                            if st.form_submit_button("Guardar Cambios"):
                                d = p.to_dict()
                                d.update({
                                    'nombre': n_nom, 'apellido': n_ape, 'dni': n_dni, 'sede': n_sede, 
                                    'plan': n_plan, 'activo': 1 if n_act else 0, 'talle': n_talle,
                                    'peso': n_peso, 'altura': n_alt, 'tutor': n_tutor, 'email': n_email, 'notas': n_notas
                                })
                                update_full_socio(uid, d, user, p.to_dict())
                                st.success("Actualizado")
                                time.sleep(1); st.rerun()
                    else: st.info("Modo Lectura")
                
                with t2:
                    # Gráfico y Lista
                    df_a = get_df("asistencias")
                    if not df_a.empty:
                        mis_a = df_a[df_a['id_socio'] == uid]
                        if not mis_a.empty:
                            mis_a['dt'] = pd.to_datetime(mis_a['fecha'], errors='coerce')
                            mis_a['Dia'] = mis_a['dt'].dt.day_name()
                            fig = px.pie(mis_a, names='Dia', title='Asistencia por Día')
                            st.plotly_chart(fig, use_container_width=True)
                            st.dataframe(mis_a[['fecha', 'sede', 'grupo_turno', 'estado', 'nota']].sort_values('fecha', ascending=False), use_container_width=True)
                        else: st.info("Sin historial.")

                with t3:
                    df_p = get_df("pagos")
                    if not df_p.empty:
                        mis_p = df_p[df_p['id_socio']==uid]
                        if not mis_p.empty: st.dataframe(mis_p[['fecha_pago', 'monto', 'concepto', 'mes_cobrado', 'estado']], use_container_width=True)

# === ENTRENAMIENTOS ===
elif nav == "Entrenamientos":
    st.title("⚽ Configurar Grupos")
    t_asig, t_ver, t_adm = st.tabs(["➕ Inscribir", "📅 Cronograma", "🔧 Admin"])
    
    with t_asig:
        st.subheader("Inscripción")
        df_soc = get_df("socios")
        df_plant = get_df("entrenamientos_plantilla")
        df_insc = get_df("inscripciones")
        
        if not df_plant.empty and not df_soc.empty:
            activos = df_soc[df_soc['activo']==1]
            alu = st.selectbox("Alumno", activos['id'].astype(str) + " - " + activos['nombre'] + " " + activos['apellido'])
            uid_alu = int(alu.split(" - ")[0])
            nom_alu = alu.split(" - ")[1]
            
            c1, c2, c3 = st.columns(3)
            sede = c1.selectbox("Sede", sorted(df_plant['sede'].unique()))
            dias = df_plant[df_plant['sede']==sede]['dia'].unique()
            dia = c2.selectbox("Día", dias)
            horas = df_plant[(df_plant['sede']==sede)&(df_plant['dia']==dia)]['horario'].unique()
            hora = c3.selectbox("Horario", horas)
            
            grupos = df_plant[(df_plant['sede']==sede)&(df_plant['dia']==dia)&(df_plant['horario']==hora)]
            st.write("---")
            for idx, row in grupos.iterrows():
                inscr = len(df_insc[df_insc['id_entrenamiento']==row['id']]) if not df_insc.empty else 0
                cupo = int(row['cupo_max']) - inscr
                
                col_txt, col_btn = st.columns([4,1])
                with col_txt: st.info(f"**{row['horario']} - {row['grupo']}** | Coach: {row['entrenador_asignado']} | Cupos: {cupo}")
                with col_btn:
                    if cupo > 0:
                        if st.button("Inscribir", key=f"ins_{row['id']}"):
                            # VALIDACIÓN CONFLICTO
                            conflicto = False
                            if check_horario_conflict(uid_alu, dia, hora):
                                st.error("⚠️ Conflicto de Horario.")
                            else:
                                # Check Duplicado
                                ya = False
                                if not df_insc.empty:
                                    ya = not df_insc[(df_insc['id_socio']==uid_alu) & (df_insc['id_entrenamiento']==row['id'])].empty
                                
                                if not ya:
                                    row_ins = [generate_id(), uid_alu, nom_alu, row['id']]
                                    save_row("inscripciones", row_ins)
                                    st.success("Inscrito")
                                    time.sleep(1); st.rerun()
                                else: st.warning("Ya inscrito")
                    else: st.error("Lleno")

    with t_ver:
        st.subheader("Vista Semanal")
        df_p = get_df("entrenamientos_plantilla")
        if not df_p.empty:
            sede_v = st.selectbox("Sede Visual", sorted(df_p['sede'].unique()), key="sv")
            df_sede = df_p[df_p['sede']==sede_v]
            st.dataframe(df_sede[['dia', 'horario', 'grupo', 'entrenador_asignado']], use_container_width=True)

    with t_adm:
        if rol == "Administrador":
            if st.button("Inicializar Estructura"):
                if get_df("entrenamientos_plantilla").empty:
                    inicializar_cronograma_realista()
                    st.success("Creado")
                else: st.warning("Ya existe")

# === ASISTENCIA ===
elif nav == "Asistencia":
    st.title("✅ Tomar Lista")
    
    hoy_dt = get_now_ar()
    dia_hoy = traducir_dia(hoy_dt)
    fecha_str = str(hoy_dt.date())
    st.info(f"Fecha: **{dia_hoy} {fecha_str}**")
    
    df_plant = get_df("entrenamientos_plantilla")
    df_insc = get_df("inscripciones")
    df_soc = get_df("socios")
    
    # Filtro Sede
    sedes_user = st.session_state.get("sedes", [])
    all_sedes = get_lista_opciones("sede", SEDES)
    sedes_disp = all_sedes if "Todas" in sedes_user else sedes_user
    
    if not df_plant.empty:
        # Clases de HOY
        clases_hoy = df_plant[df_plant['dia'] == dia_hoy]
        if not clases_hoy.empty:
            sede_sel = st.selectbox("Sede", [s for s in sedes_disp if s in clases_hoy['sede'].unique()])
            clases_sede = clases_hoy[clases_hoy['sede'] == sede_sel]
            
            for idx, clase in clases_sede.iterrows():
                with st.expander(f"⏰ {clase['horario']} - {clase['grupo']} ({clase['entrenador_asignado']})", expanded=True):
                    
                    # 1. Inscritos Fijos
                    inscritos = pd.DataFrame()
                    if not df_insc.empty:
                        inscritos = df_insc[df_insc['id_entrenamiento'] == clase['id']]
                    
                    with st.form(f"asist_{clase['id']}"):
                        checks = {}
                        motivos = {}
                        
                        # Lista Fijos
                        if not inscritos.empty:
                            st.markdown("##### Alumnos Fijos")
                            for j, (ix, al) in enumerate(inscritos.iterrows()):
                                c_chk, c_mot = st.columns([2, 3])
                                checks[al['id_socio']] = c_chk.checkbox(al['nombre_alumno'], value=True, key=f"c_{clase['id']}_{al['id_socio']}")
                                motivos[al['id_socio']] = c_mot.text_input("Motivo Ausencia", key=f"m_{clase['id']}_{al['id_socio']}")
                        
                        # Invitados / Extras
                        st.markdown("##### ➕ Agregar Invitado")
                        invitado = None
                        if not df_soc.empty:
                             activos = df_soc[df_soc['activo']==1]
                             inv_sel = st.selectbox("Buscar Alumno Extra", ["-- Seleccionar --"] + activos['id'].astype(str).tolist() + " - " + activos['nombre'], key=f"inv_{clase['id']}")
                             tipo_inv = st.radio("Tipo", ["Recuperatorio", "Clase Extra"], horizontal=True, key=f"tip_{clase['id']}")
                             if inv_sel != "-- Seleccionar --": invitado = inv_sel

                        if st.form_submit_button("💾 Guardar Planilla"):
                            cnt = 0
                            # Guardar Fijos
                            for uid, present in checks.items():
                                est = "Presente" if present else "Ausente"
                                nota = "" if present else motivos[uid]
                                nom = inscritos[inscritos['id_socio']==uid].iloc[0]['nombre_alumno']
                                row = [fecha_str, datetime.now().strftime("%H:%M"), uid, nom, sede_sel, f"{clase['grupo']} ({clase['horario']})", est, nota]
                                save_row("asistencias", row)
                                cnt += 1
                            
                            # Guardar Invitado
                            if invitado:
                                uid_inv = int(invitado.split(" - ")[0])
                                nom_inv = invitado.split(" - ")[1]
                                row_inv = [fecha_str, datetime.now().strftime("%H:%M"), uid_inv, nom_inv, sede_sel, f"{clase['grupo']} ({clase['horario']})", "Presente", f"Invitado: {tipo_inv}"]
                                save_row("asistencias", row_inv)
                                cnt += 1
                            
                            st.success(f"Guardado: {cnt} registros.")
        else: st.info("No hay clases hoy.")

# === CONTABILIDAD ===
elif nav == "Contabilidad":
    st.title("📒 Contabilidad")
    
    with st.sidebar:
        st.markdown("### Filtros")
        f_sede = st.multiselect("Sede", get_lista_opciones("sede", SEDES))
        f_mes = st.selectbox("Mes", ["Todos"] + MESES)
        f_rango1 = st.date_input("Desde", date(date.today().year, 1, 1))
        f_rango2 = st.date_input("Hasta", date.today())
    
    tab_cuotas, tab_ocasional, tab_rep = st.tabs(["📋 Gestión Pagos", "🛍️ Ocasionales", "📊 Caja"])
    
    with tab_cuotas:
        # Generación Auto
        dia_corte = int(get_config_value("dia_corte", 19))
        hoy = get_today_ar()
        idx_m = hoy.month - 1
        if hoy.day >= dia_corte:
            t_idx = (idx_m + 1) % 12
            yr = hoy.year + 1 if idx_m == 11 else hoy.year
        else:
            t_idx = idx_m
            yr = hoy.year
        mes_target = f"{MESES[t_idx]} {yr}"
        st.caption(f"Período: **{mes_target}**")
        
        # (Lógica Auto-Gen)
        df_pag = get_df("pagos")
        df_soc = get_df("socios")
        df_tar = get_df("tarifas")
        
        pagos_gen = []
        if not df_pag.empty and 'mes_cobrado' in df_pag.columns:
            pagos_mes = df_pag[(df_pag['mes_cobrado'] == mes_target) & (df_pag['concepto'].astype(str).str.contains("Cuota"))]
            pagos_gen = pagos_mes['id_socio'].unique()
            
        if not df_soc.empty:
            pendientes = df_soc[(df_soc['activo']==1) & (~df_soc['id'].isin(pagos_gen))]
            if not pendientes.empty:
                filas = []
                for idx, row_s in pendientes.iterrows():
                    pr = 15000
                    if not df_tar.empty and row_s['plan'] in df_tar['concepto'].values:
                        pr = df_tar[df_tar['concepto']==row_s['plan']]['valor'].values[0]
                    row_p = [generate_id(), str(get_today_ar()), row_s['id'], f"{row_s['nombre']} {row_s['apellido']}", pr, "Cuota Mensual", "Pendiente", f"Plan: {row_s['plan']}", "Pendiente", "System", mes_target]
                    filas.append(row_p)
                if filas:
                    if save_rows_bulk("pagos", filas):
                         st.toast(f"Auto-generadas {len(filas)} cuotas.")
                         time.sleep(1); st.rerun()

        # Cobro
        if st.session_state["cobro_alumno_id"]:
            uid = st.session_state["cobro_alumno_id"]
            alu = df_soc[df_soc['id']==uid].iloc[0]
            st.subheader(f"Cobrar a: {alu['nombre']}")
            if st.button("Cancelar"): 
                st.session_state["cobro_alumno_id"]=None
                st.rerun()
            
            df_tar = get_df("tarifas")
            lst = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
            idx_p = lst.index(alu['plan']) if alu['plan'] in lst else 0
            
            c1, c2 = st.columns(2)
            conc = c1.selectbox("Concepto", lst, index=idx_p)
            pr = 0.0
            if not df_tar.empty:
                m = df_tar[df_tar['concepto']==conc]
                if not m.empty: 
                    try: pr = float(str(m.iloc[0]['valor']).replace('$',''))
                    except: pass
            mon = c2.number_input("Monto", value=pr)
            
            c3, c4 = st.columns(2)
            met = c3.selectbox("Medio", ["Efectivo", "Transferencia", "MP"])
            mes_p = c4.selectbox("Mes", [mes_target] + [f"{m} {yr}" for m in MESES])
            
            nota = st.text_input("Nota")
            conf = st.checkbox("Confirmar", value=True)
            
            deuda_id = None
            if not df_pag.empty:
                chk = df_pag[(df_pag['id_socio']==uid) & (df_pag['mes_cobrado']==mes_p) & (df_pag['estado']=='Pendiente')]
                if not chk.empty: deuda_id = chk.iloc[0]['id']
            
            if st.button("PAGAR", type="primary", use_container_width=True):
                if conc != alu['plan']: update_plan_socio(uid, conc)
                st_pago = "Confirmado" if conf else "Pendiente"
                
                if deuda_id:
                    registrar_pago_existente(deuda_id, met, user, st_pago, mon, conc, nota)
                else:
                    row = [generate_id(), str(get_today_ar()), uid, f"{alu['nombre']} {alu['apellido']}", mon, conc, met, nota, st_pago, user, mes_p]
                    save_row("pagos", row)
                
                st.success("Listo")
                d_pdf = {"fecha":str(get_today_ar()), "alumno":f"{alu['nombre']} {alu['apellido']}", "monto":mon, "concepto":conc, "metodo":met, "mes":mes_p, "nota":nota}
                pdf_b = generar_pdf(d_pdf)
                b64 = base64.b64encode(pdf_b).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Recibo.pdf"><button>Descargar Recibo</button></a>'
                st.markdown(href, unsafe_allow_html=True)
                time.sleep(3); st.session_state["cobro_alumno_id"]=None; st.rerun()

        else:
            st.subheader("Lista de Cobro")
            col_s, col_r = st.columns([3,1])
            search = col_s.text_input("Buscar")
            rows = col_r.selectbox("Filas", [25, 50])
            
            if not df_soc.empty:
                df_show = df_soc[df_soc['activo']==1]
                if search: df_show = df_show[df_show.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
                
                subset = df_show.head(rows)
                cols = st.columns([3, 2, 2, 2])
                cols[0].markdown("**Alumno**")
                cols[1].markdown("**Sede**")
                cols[2].markdown(f"**{mes_target}**")
                cols[3].markdown("**Acción**")
                st.markdown("---")
                
                for idx, row in subset.iterrows():
                    st_mes = "⚪"
                    if not df_pag.empty:
                        pm = df_pag[(df_pag['id_socio']==row['id']) & (df_pag['mes_cobrado']==mes_target)]
                        if not pm.empty:
                            if "Confirmado" in pm['estado'].values: st_mes = "✅"
                            else: st_mes = "🔴"
                    
                    c1, c2, c3, c4 = st.columns([3,2,2,2])
                    c1.write(f"{row['nombre']} {row['apellido']}")
                    c2.caption(row['sede'])
                    c3.write(st_mes)
                    if c4.button("Cobrar", key=f"pay_{row['id']}"):
                        st.session_state["cobro_alumno_id"] = row['id']
                        st.rerun()
                    st.divider()

    with tab_ocasional:
        st.info("Módulo Ocasional Activo")
    
    with tab_rep:
        st.markdown("### Caja Diaria")
        df_p = get_df("pagos")
        if not df_p.empty:
            td = str(get_today_ar())
            ch = df_p[(df_p['fecha_pago']==td) & (df_p['estado']=='Confirmado')]
            tot = pd.to_numeric(ch['monto'], errors='coerce').sum()
            st.metric("Total Hoy", f"${tot:,.0f}")
            st.dataframe(ch)

# === CONFIGURACIÓN ===
elif nav == "Configuración":
    st.title("⚙️ Configuración")
    t1, t2, t3 = st.tabs(["Parámetros", "Tarifas", "Listas"])
    
    with t1:
        d = int(get_config_value("dia_corte", 19))
        nd = st.slider("Día Corte", 1, 28, d)
        if st.button("Guardar"):
            set_config_value("dia_corte", nd)
            st.success("Guardado")
            
    with t2:
        df = get_df("tarifas")
        ed = st.data_editor(df, num_rows="dynamic")
        if st.button("Guardar Tarifas"):
            actualizar_tarifas_bulk(ed)
            st.success("Guardado")
            
    with t3:
        df = get_df("listas")
        ed = st.data_editor(df, num_rows="dynamic")
        if st.button("Guardar Listas"):
            sh = get_client(); ws = sh.worksheet("listas"); ws.clear();
            ws.update([ed.columns.values.tolist()] + ed.values.tolist())
            st.success("Guardado")

# === USUARIOS ===
elif nav == "Usuarios":
    st.title("🔐 Gestión Usuarios")
    if rol == "Administrador":
        with st.form("nu"):
            u = st.text_input("Usuario")
            p = st.text_input("Clave", type="password")
            n = st.text_input("Nombre")
            r = st.selectbox("Rol", ["Administrador", "Entrenador", "Contador"])
            s = st.multiselect("Sedes", get_lista_opciones("sede", SEDES))
            if st.form_submit_button("Crear"):
                h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
                save_row("usuarios", [generate_id(), u, h, r, n, ",".join(s), 1])
                st.success("Creado")
    else: st.error("Restringido")
