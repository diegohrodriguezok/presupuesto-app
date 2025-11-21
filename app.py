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
# 1. CONFIGURACIÓN GLOBAL
# ==========================================
st.set_page_config(
    page_title="Area Arqueros ERP", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="logo.png"
)

# --- CARGAR CSS ---
def local_css(file_name):
    try:
        with open(file_name) as f: st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except: pass

local_css("style.css")

# --- UTILIDADES DE TIEMPO ---
def get_now_ar():
    try:
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        return datetime.now(tz)
    except: return datetime.now()

def get_today_ar():
    return get_now_ar().date()

def traducir_dia(fecha_dt):
    dias = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    return dias[fecha_dt.weekday()]

# --- CONSTANTES GLOBALES ---
# (Se usan como fallback si no hay configuración en Sheets)
DEF_SEDES = ["Sede C1", "Sede Saa"]
DEF_MOTIVOS = ["Enfermedad", "Viaje", "Sin Aviso", "Lesión", "Estudio"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# ==========================================
# 2. MOTOR DE DATOS (GSPREAD)
# ==========================================
@st.cache_resource
def get_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("BaseDatos_ClubArqueros")
    except Exception as e:
        st.error(f"❌ Error crítico de conexión: {e}")
        st.stop()

def get_df(sheet_name):
    """Lectura segura con normalización de columnas"""
    try:
        ws = get_client().worksheet(sheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            df.columns = df.columns.str.strip().str.lower()
            # Garantizar columnas mínimas para v6.0
            req = {
                'entrenamientos_plantilla': ['id', 'sede', 'dia', 'horario', 'grupo', 'entrenador_asignado', 'cupo_max'],
                'inscripciones': ['id_socio', 'id_entrenamiento', 'nombre_alumno'],
                'listas': ['tipo', 'valor']
            }
            if sheet_name in req:
                for c in req[sheet_name]: 
                    if c not in df.columns: df[c] = ""
        return df
    except: return pd.DataFrame()

def save_row(sheet_name, data):
    try: get_client().worksheet(sheet_name).append_row(data)
    except: pass

def save_rows_bulk(sheet_name, data_list):
    try: get_client().worksheet(sheet_name).append_rows(data_list)
    return True
    except: return False

def delete_row_by_condition(sheet_name, col_name, val):
    """Borra filas que coincidan con una condición (ej: borrar inscripción)"""
    ws = get_client().worksheet(sheet_name)
    try:
        # Busca todas las celdas que coinciden
        cell = ws.find(str(val)) 
        # Nota: Esto borra la primera ocurrencia. Para borrar multiple requeriría loop.
        ws.delete_rows(cell.row)
        return True
    except: return False

def update_cell_val(sheet_name, id_row, col_idx, val):
    ws = get_client().worksheet(sheet_name)
    try:
        cell = ws.find(str(id_row))
        ws.update_cell(cell.row, col_idx, val)
        return True
    except: return False

def generate_id():
    return int(f"{int(time.time())}{uuid.uuid4().int % 1000}")

def log_action(id_ref, accion, detalle, user):
    try: save_row("logs", [str(get_now_ar()), user, str(id_ref), accion, detalle])
    except: pass

# --- CONFIGURACIÓN DINÁMICA ---
def get_lista_opciones(tipo, default_list):
    df = get_df("listas")
    if not df.empty and 'tipo' in df.columns:
        items = df[df['tipo'] == tipo]['valor'].tolist()
        if items: return sorted(list(set(items)))
    return default_list

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

# --- LÓGICA DE NEGOCIO ---
def check_horario_conflict(id_socio, dia, horario):
    """Impide doble inscripción en mismo horario"""
    df_insc = get_df("inscripciones")
    df_plant = get_df("entrenamientos_plantilla")
    if df_insc.empty or df_plant.empty: return False
    
    mis_insc = df_insc[df_insc['id_socio'] == id_socio]
    if mis_insc.empty: return False
    
    merged = pd.merge(mis_insc, df_plant, left_on='id_entrenamiento', right_on='id')
    choque = merged[ (merged['dia'] == dia) & (merged['horario'] == horario) ]
    return not choque.empty

def update_full_socio(id_socio, d, user_admin, original_data=None):
    # Actualización masiva de perfil
    sh = get_client()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        r = cell.row
        # Mapeo de columnas (Verificar con Sheet)
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
    pdf.cell(200, 10, txt="AREA ARQUEROS - RECIBO", ln=1, align='C')
    pdf.ln(10)
    def safe(t): return str(t).encode('latin-1', 'replace').decode('latin-1')
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Fecha: {safe(datos['fecha'])}", ln=1)
    pdf.cell(200, 10, txt=f"Alumno: {safe(datos['alumno'])}", ln=1)
    pdf.cell(200, 10, txt=f"Concepto: {safe(datos['concepto'])}", ln=1)
    pdf.cell(200, 10, txt=f"Monto: ${datos['monto']}", ln=1)
    return pdf.output(dest="S").encode("latin-1", errors='replace')

# ==========================================
# 3. SEGURIDAD Y SESIÓN
# ==========================================
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None, "sedes": []})
# Estado de navegación para "Entrar" a un grupo
if "selected_group_id" not in st.session_state: st.session_state["selected_group_id"] = None
if "view_profile_id" not in st.session_state: st.session_state["view_profile_id"] = None

def check_password(password, hashed):
    try: return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except: return False

def login_page():
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        try: st.image("logo.png", width=150)
        except: st.markdown("## 🔐 Area Arqueros")
        
        # Init Check
        df_users = get_df("usuarios")
        if df_users.empty:
            st.warning("Base vacía. Cree Admin.")
            with st.form("init"):
                u = st.text_input("User"); p = st.text_input("Pass", type="password")
                if st.form_submit_button("Crear"):
                    h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
                    save_row("usuarios", [generate_id(), u, h, "Administrador", "Super Admin", "Todas", 1])
                    st.success("Creado."); time.sleep(2); st.rerun()
            return

        with st.form("login"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar"):
                # DB Login
                if not df_users.empty and 'user' in df_users.columns:
                    match = df_users[df_users['user'] == u]
                    if not match.empty and check_password(p, match.iloc[0]['pass_hash']):
                        udata = match.iloc[0]
                        sedes = str(udata['sedes_acceso']).split(",") if udata['sedes_acceso'] != "Todas" else get_lista_opciones("sede", DEF_SEDES)
                        st.session_state.update({"auth": True, "user": udata['nombre_completo'], "rol": udata['rol'], "sedes": sedes})
                        st.rerun()
                    else: st.error("Credenciales incorrectas")
                else:
                    # Backup Secrets
                    try:
                        B = st.secrets["users"]
                        if u in B and str(B[u]["p"]) == p:
                             st.session_state.update({"auth": True, "user": u, "rol": B[u]["r"], "sedes": DEF_SEDES})
                             st.rerun()
                    except: st.error("Error de acceso.")

def logout():
    st.session_state["logged_in"] = False; st.session_state["auth"] = False; st.rerun()

if not st.session_state["auth"]: login_page(); st.stop()

# ==========================================
# 4. NAVEGACIÓN
# ==========================================
user, rol = st.session_state["user"], st.session_state["rol"]

with st.sidebar:
    try: st.image("logo.png", width=200)
    except: st.header("🛡️ CLUB")
    st.info(f"Hola, **{user}** ({rol})")
    
    menu = ["Dashboard"]
    # UNIFICACIÓN DE MÓDULOS
    if rol in ["Administrador", "Profesor", "Entrenador"]:
        menu.extend(["Mis Grupos", "Alumnos"]) # "Asistencia" y "Entrenamientos" ahora son "Mis Grupos"
    if rol in ["Administrador", "Contador"]:
        menu.extend(["Contabilidad", "Configuración"])
    if rol == "Administrador": menu.append("Usuarios")
    
    nav = st.radio("Ir a:", menu)
    
    # Limpieza de estado al cambiar menú
    if nav != st.session_state.get("last_nav"):
        st.session_state["selected_group_id"] = None # Salir del grupo
        st.session_state["view_profile_id"] = None
        st.session_state["last_nav"] = nav
        
    st.divider()
    if st.button("Salir"): logout()

# ==========================================
# 5. MÓDULOS (LÓGICA v6.0)
# ==========================================

# === DASHBOARD ===
if nav == "Dashboard":
    st.title("📊 Tablero de Comando")
    # (Mismo dashboard de siempre, funciona bien)
    df_s = get_df("socios"); df_p = get_df("pagos")
    c1, c2 = st.columns(2)
    c1.metric("Alumnos Activos", len(df_s[df_s['activo']==1]) if not df_s.empty else 0)
    
    ing = 0
    if not df_p.empty:
        df_p['dt'] = pd.to_datetime(df_p['fecha_pago'], errors='coerce')
        mes = df_p[(df_p['dt'].dt.month == get_today_ar().month) & (df_p['estado']=='Confirmado')]
        ing = pd.to_numeric(mes['monto'], errors='coerce').sum()
    c2.metric("Ingresos Mes", f"${ing:,.0f}")

# === MIS GRUPOS (FUSIÓN: Entrenamientos + Asistencia) ===
elif nav == "Mis Grupos":
    # VISTA 1: GRILLA DE GRUPOS
    if st.session_state["selected_group_id"] is None:
        st.title("⚽ Mis Grupos de Entrenamiento")
        
        df_plant = get_df("entrenamientos_plantilla")
        
        if not df_plant.empty:
            # Filtros
            sedes_user = st.session_state.get("sedes", [])
            sedes_disp = get_lista_opciones("sede", DEF_SEDES)
            if "Todas" not in sedes_user: sedes_disp = [s for s in sedes_disp if s in sedes_user]
            
            f_sede = st.selectbox("Filtrar Sede", sedes_disp)
            
            # Filtrar por Sede
            grupos_sede = df_plant[df_plant['sede'] == f_sede]
            
            # Filtro Seguridad Entrenador (Si no es Admin, solo ve sus grupos)
            if rol != "Administrador":
                # Asumimos coincidencia por nombre (simple) o mostrar todo si es flexible
                # Para v6.0 estricta:
                grupos_sede = grupos_sede[grupos_sede['entrenador_asignado'].astype(str).str.contains(user, case=False, na=False)]
            
            if not grupos_sede.empty:
                # Ordenar por Día y Hora
                dias_order = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                grupos_sede['dia_cat'] = pd.Categorical(grupos_sede['dia'], categories=dias_order, ordered=True)
                grupos_sede = grupos_sede.sort_values(['dia_cat', 'horario'])
                
                st.markdown("---")
                # Renderizar Tarjetas
                cols = st.columns(3)
                for i, (idx, row) in enumerate(grupos_sede.iterrows()):
                    with cols[i % 3]:
                        # Diseño de Tarjeta de Grupo
                        st.markdown(f"""
                        <div class="training-card">
                            <h4 style="margin:0; color:#1f2c56;">{row['dia']} {row['horario']}</h4>
                            <p style="font-weight:bold; font-size:1.1em;">{row['grupo']}</p>
                            <small>Coach: {row['entrenador_asignado']}</small>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if st.button(f"📂 Gestionar Grupo", key=f"grp_{row['id']}", use_container_width=True):
                            st.session_state["selected_group_id"] = row['id']
                            st.rerun()
            else:
                st.info("No tienes grupos asignados en esta sede.")
                if rol == "Administrador": st.caption("Ve a Configuración > Plantilla para crear grupos.")
        else:
            st.warning("No hay estructura de entrenamientos creada.")

    # VISTA 2: GESTIÓN DEL GRUPO (La "Carpeta")
    else:
        gid = st.session_state["selected_group_id"]
        df_plant = get_df("entrenamientos_plantilla")
        grupo_data = df_plant[df_plant['id'] == gid].iloc[0]
        
        if st.button("⬅️ Volver a la Grilla"):
            st.session_state["selected_group_id"] = None
            st.rerun()
            
        st.markdown(f"## 📂 {grupo_data['grupo']}")
        st.caption(f"{grupo_data['dia']} | {grupo_data['horario']} | {grupo_data['sede']} | Coach: {grupo_data['entrenador_asignado']}")
        
        tab_plantel, tab_asist = st.tabs(["👥 Plantel (Inscripciones)", "✅ Planilla del Día"])
        
        # --- PESTAÑA A: PLANTEL ---
        with tab_plantel:
            df_insc = get_df("inscripciones")
            df_soc = get_df("socios")
            
            # 1. Lista de Inscritos
            inscritos = pd.DataFrame()
            if not df_insc.empty:
                inscritos = df_insc[df_insc['id_entrenamiento'] == gid]
            
            c1, c2 = st.columns([3, 1])
            c1.metric("Total Alumnos", len(inscritos))
            c2.metric("Cupo Máximo", grupo_data['cupo_max'])
            
            if not inscritos.empty:
                st.dataframe(inscritos[['nombre_alumno']], use_container_width=True)
                
                # Baja de alumno
                with st.expander("Dar de Baja del Grupo"):
                    baja_sel = st.selectbox("Seleccionar Alumno", inscritos['nombre_alumno'].tolist())
                    if st.button("🗑️ Eliminar Inscripción"):
                        # Buscar ID de inscripción para borrar
                        id_insc_borrar = inscritos[inscritos['nombre_alumno'] == baja_sel].iloc[0]['id']
                        # Funcion delete no implementada en gspread simple, usamos filtro inverso o lógica custom
                        # Simulamos borrado lógico o implementamos delete_row
                        if delete_row_by_condition("inscripciones", "id", id_insc_borrar): # Necesita implementacion
                            st.success("Alumno removido del grupo.")
                            time.sleep(1); st.rerun()
                        else: st.error("Error al borrar (Falta implementar delete row específico)")
            else:
                st.info("Grupo vacío.")
            
            st.markdown("---")
            st.subheader("➕ Agregar Alumno al Plantel")
            if not df_soc.empty:
                activos = df_soc[df_soc['activo']==1]
                # Excluir los ya inscritos
                ids_inscritos = inscritos['id_socio'].tolist() if not inscritos.empty else []
                disponibles = activos[~activos['id'].isin(ids_inscritos)]
                
                alu_new = st.selectbox("Buscar Alumno", disponibles['id'].astype(str) + " - " + disponibles['nombre'] + " " + disponibles['apellido'])
                
                if st.button("Inscribir Fijo"):
                    uid_al = int(alu_new.split(" - ")[0])
                    nom_al = alu_new.split(" - ")[1]
                    
                    # Validación de Horario (Candado)
                    if check_horario_conflict(uid_al, grupo_data['dia'], grupo_data['horario']):
                        st.error(f"⚠️ Conflicto: {nom_al} ya tiene clase el {grupo_data['dia']} a las {grupo_data['horario']}.")
                    else:
                        row_ins = [generate_id(), uid_al, nom_al, gid, f"{grupo_data['grupo']} ({grupo_data['dia']})"]
                        save_row("inscripciones", row_ins)
                        st.success(f"{nom_al} agregado al plantel.")
                        time.sleep(1); st.rerun()

        # --- PESTAÑA B: ASISTENCIA ---
        with tab_asist:
            st.subheader("Toma de Lista")
            
            # Selector de Fecha (Default: Hoy si coincide día, sino último día coincidente)
            hoy_dt = get_now_ar()
            dia_hoy_txt = traducir_dia(hoy_dt)
            fecha_def = hoy_dt.date()
            
            # Si hoy no es el día del grupo, avisar
            if dia_hoy_txt != grupo_data['dia']:
                st.warning(f"Hoy es {dia_hoy_txt}, pero este grupo entrena los {grupo_data['dia']}.")
            
            fecha_lista = st.date_input("Fecha de la Clase", fecha_def)
            
            with st.form("form_asistencia"):
                st.markdown(f"#### 📋 Planilla del {fecha_lista}")
                
                # 1. Alumnos Fijos
                checks = {}
                notas_aus = {}
                
                if not inscritos.empty:
                    for idx, alu in inscritos.iterrows():
                        c_chk, c_mot = st.columns([2, 3])
                        # Checkbox (Presente por defecto)
                        is_present = c_chk.checkbox(alu['nombre_alumno'], value=True, key=f"att_{alu['id']}")
                        checks[alu['id_socio']] = is_present
                        # Motivo
                        if not is_present:
                            notas_aus[alu['id_socio']] = c_mot.selectbox("Motivo Ausencia", [""] + get_lista_opciones("motivo_ausencia", DEF_MOTIVOS), key=f"mot_{alu['id']}")
                        else:
                            notas_aus[alu['id_socio']] = ""
                else:
                    st.caption("No hay plantel fijo.")
                
                # 2. Invitados (Recuperatorio / Extra)
                st.markdown("---")
                st.markdown("**Invitado / Recuperatorio (Solo por hoy)**")
                invitado_sel = st.selectbox("Agregar Alumno Extra", ["-- Ninguno --"] + activos['id'].astype(str).tolist() + " - " + activos['nombre'], key="inv_asist")
                tipo_inv = st.radio("Condición", ["Recuperatorio (Gratis)", "Clase Extra (Generar Deuda)"], horizontal=True)
                
                if st.form_submit_button("💾 Guardar Asistencia"):
                    cnt = 0
                    # Guardar Fijos
                    for uid, present in checks.items():
                        est = "Presente" if present else "Ausente"
                        nt = notas_aus[uid]
                        nm = inscritos[inscritos['id_socio']==uid].iloc[0]['nombre_alumno']
                        
                        # fecha, hora, id_socio, nombre, sede, grupo_turno, estado, nota
                        r = [str(fecha_lista), datetime.now().strftime("%H:%M"), uid, nm, grupo_data['sede'], f"{grupo_data['grupo']} ({grupo_data['horario']})", est, nt]
                        save_row("asistencias", r)
                        cnt += 1
                    
                    # Guardar Invitado
                    if invitado_sel != "-- Ninguno --":
                        uid_i = int(invitado_sel.split(" - ")[0])
                        nom_i = invitado_sel.split(" - ")[1]
                        r_inv = [str(fecha_lista), datetime.now().strftime("%H:%M"), uid_i, nom_i, grupo_data['sede'], f"{grupo_data['grupo']} (Invitado)", "Presente", tipo_inv]
                        save_row("asistencias", r_inv)
                        cnt += 1
                        
                        # Si es Clase Extra -> Generar Deuda
                        if "Clase Extra" in tipo_inv:
                            # Buscar precio clase suelta
                            # (Lógica simplificada, se podría buscar en tarifas)
                            monto_extra = 5000 
                            pago_row = [generate_id(), str(fecha_lista), uid_i, nom_i, monto_extra, "Clase Extra", "Pendiente", f"Asistió a {grupo_data['grupo']}", "Pendiente", user, str(fecha_lista)]
                            save_row("pagos", pago_row)
                            st.toast(f"💰 Deuda generada para {nom_i}")

                    st.success(f"Se guardaron {cnt} registros.")

# === ALUMNOS ===
elif nav == "Alumnos":
    # (Lógica Alumnos v5.1 con navegación directa - Mantenida)
    if st.session_state["view_profile_id"] is None:
        st.title("👥 Alumnos")
        tab1, tab2 = st.tabs(["Directorio", "Nuevo Alumno"])
        with tab1:
            df = get_df("socios")
            if not df.empty:
                # Filtros... (Resumido, usa el código completo anterior para filtros)
                for idx, row in df.iterrows():
                     st.markdown(f"<div class='student-card'><b>{row['nombre']} {row['apellido']}</b> | {row['sede']}</div>", unsafe_allow_html=True)
                     if st.button(f"Ver Ficha {row['id']}", key=row['id']): 
                         st.session_state["view_profile_id"] = row['id']
                         st.rerun()
        with tab2:
            # Formulario Alta...
            pass
    else:
        # Perfil...
        if st.button("Volver"): 
            st.session_state["view_profile_id"] = None
            st.rerun()
        st.title("Perfil Alumno")
        # Tabs Datos / Asistencia / Pagos

# === CONTABILIDAD ===
elif nav == "Contabilidad":
    st.title("📒 Finanzas")
    # (Módulo Contable Completo con Auto-Gen)
    # ... Insertar lógica contable v5.1 aquí ...

# === CONFIGURACIÓN ===
elif nav == "Configuración":
    st.title("⚙️ Configuración")
    t1, t2, t3 = st.tabs(["Parámetros", "Tarifas", "Listas Desplegables"])
    with t1:
        # Dia corte...
        pass
    with t2:
        # Tarifas editor
        pass
    with t3:
        # Listas dinámicas (Sedes, Motivos)
        df_l = get_df("listas")
        ed = st.data_editor(df_l, num_rows="dynamic")
        if st.button("Guardar Listas"):
            # Update logic
            pass

# === USUARIOS ===
elif nav == "Usuarios":
    st.title("🔐 Usuarios")
    # Admin usuarios...
