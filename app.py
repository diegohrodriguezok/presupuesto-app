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

# --- UTILIDADES ---
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
DEF_SEDES = ["Sede C1", "Sede Saa"]
DEF_MOTIVOS = ["Enfermedad", "Viaje", "Sin Aviso", "Lesión", "Estudio"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
TALLES = ["10", "12", "14", "XS", "S", "M", "L", "XL"]
GRUPOS_GEN = ["Infantil", "Prejuvenil", "Juvenil", "Adulto", "Senior", "Amateur"]

# ==========================================
# 2. MOTOR DE DATOS
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
    """Lectura segura con normalización"""
    try:
        ws = get_client().worksheet(sheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            df.columns = df.columns.str.strip().str.lower()
            req = {
                'entrenamientos_plantilla': ['id', 'sede', 'dia', 'horario', 'grupo', 'entrenador_asignado', 'cupo_max'],
                'inscripciones': ['id_socio', 'id_entrenamiento', 'nombre_alumno'],
                'listas': ['tipo', 'valor'],
                'usuarios': ['user', 'pass_hash', 'rol', 'nombre_completo', 'sedes_acceso', 'activo'],
                'socios': ['id', 'nombre', 'apellido', 'dni', 'sede', 'grupo', 'plan', 'activo'],
                'pagos': ['id', 'id_socio', 'monto', 'mes_cobrado', 'estado']
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
    try: 
        get_client().worksheet(sheet_name).append_rows(data_list)
        return True
    except: return False

def delete_row_by_condition(sheet_name, col_name, val):
    ws = get_client().worksheet(sheet_name)
    try:
        cell = ws.find(str(val)) 
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

# --- CONFIGURACIÓN ---
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
    df_insc = get_df("inscripciones")
    df_plant = get_df("entrenamientos_plantilla")
    if df_insc.empty or df_plant.empty: return False
    
    mis_insc = df_insc[df_insc['id_socio'] == str(id_socio)]
    if mis_insc.empty: return False
    
    merged = pd.merge(mis_insc, df_plant, left_on='id_entrenamiento', right_on='id')
    choque = merged[ (merged['dia'] == dia) & (merged['horario'] == horario) ]
    return not choque.empty

def update_full_socio(id_socio, d, user_admin, original_data=None):
    sh = get_client()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        r = cell.row
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
    return update_cell_val("socios", id_socio, 11, nuevo_plan)

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
    return update_cell_val("pagos", id_pago, 9, "Confirmado")

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
    st.session_state.update({"auth": False, "user": None, "rol": None})
if "view_profile_id" not in st.session_state: st.session_state["view_profile_id"] = None
if "cobro_alumno_id" not in st.session_state: st.session_state["cobro_alumno_id"] = None
if "selected_group_id" not in st.session_state: st.session_state["selected_group_id"] = None

def check_password(password, hashed):
    try: return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except: return False

def crear_usuario_real(user, password, rol, nombre, sedes):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    row = [generate_id(), user, hashed, rol, nombre, sedes, 1]
    save_row("usuarios", row)
    return True

def login_page():
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        try: st.image("logo.png", width=150)
        except: st.markdown("## 🔐 Area Arqueros")
        df_users = get_df("usuarios")
        if df_users.empty:
            st.warning("Base vacía. Cree Admin.")
            with st.form("init"):
                u = st.text_input("User"); p = st.text_input("Pass", type="password")
                if st.form_submit_button("Crear"):
                    crear_usuario_real(u, p, "Administrador", "Super Admin", "Todas")
                    st.success("Creado."); time.sleep(2); st.rerun()
            return

        with st.form("login"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar"):
                login_ok = False
                if not df_users.empty and 'user' in df_users.columns:
                    match = df_users[df_users['user'] == u]
                    if not match.empty and check_password(p, match.iloc[0]['pass_hash']):
                        udata = match.iloc[0]
                        s = str(udata['sedes_acceso']).split(",") if udata['sedes_acceso'] != "Todas" else get_lista_opciones("sede", DEF_SEDES)
                        st.session_state.update({"auth": True, "user": udata['nombre_completo'], "rol": udata['rol'], "sedes": s})
                        login_ok = True; st.rerun()
                
                if not login_ok:
                    try:
                        B = st.secrets["users"]
                        if u in B and str(B[u]["p"]) == p:
                             st.session_state.update({"auth": True, "user": u, "rol": B[u]["r"], "sedes": DEF_SEDES})
                             st.rerun()
                        else: st.error("Datos incorrectos")
                    except: st.error("Error de acceso")

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
    st.info(f"👤 **{user}**\nRol: {rol}")
    
    menu = ["Dashboard"]
    if rol in ["Administrador", "Profesor", "Entrenador"]:
        menu.extend(["Mis Grupos", "Alumnos"])
    if rol in ["Administrador", "Contador"]:
        menu.extend(["Contabilidad", "Configuración"])
    if rol == "Administrador": menu.append("Usuarios")
    
    nav = st.radio("Navegación", menu)
    if nav != st.session_state.get("last_nav"):
        st.session_state["selected_group_id"] = None
        st.session_state["view_profile_id"] = None
        st.session_state["cobro_alumno_id"] = None
        st.session_state["last_nav"] = nav
    st.divider()
    if st.button("Cerrar Sesión"): logout()

# ==========================================
# 5. MÓDULOS
# ==========================================

# === DASHBOARD ===
if nav == "Dashboard":
    st.title("📊 Estadísticas")
    c1, c2 = st.columns(2)
    fecha_inicio = c1.date_input("Desde", date.today().replace(day=1))
    fecha_fin = c2.date_input("Hasta", date.today())
    
    df_pagos = get_df("pagos")
    df_gastos = get_df("gastos")
    df_s = get_df("socios")
    
    ing = 0; egr = 0
    if not df_pagos.empty:
        df_pagos['dt'] = pd.to_datetime(df_pagos['fecha_pago'], errors='coerce').dt.date
        ing = pd.to_numeric(df_pagos[(df_pagos['dt']>=fecha_inicio)&(df_pagos['dt']<=fecha_fin)]['monto'], errors='coerce').fillna(0).sum()
    if not df_gastos.empty:
        df_gastos['dt'] = pd.to_datetime(df_gastos['fecha'], errors='coerce').dt.date
        egr = pd.to_numeric(df_gastos[(df_gastos['dt']>=fecha_inicio)&(df_gastos['dt']<=fecha_fin)]['monto'], errors='coerce').fillna(0).sum()
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Ingresos", f"${ing:,.0f}")
    k2.metric("Gastos", f"${egr:,.0f}")
    k3.metric("Neto", f"${ing-egr:,.0f}")

# === MIS GRUPOS ===
elif nav == "Mis Grupos":
    if st.session_state["selected_group_id"] is None:
        st.title("⚽ Mis Grupos")
        df_plant = get_df("entrenamientos_plantilla")
        if not df_plant.empty:
            sedes_user = st.session_state.get("sedes", [])
            all_s = get_lista_opciones("sede", DEF_SEDES)
            disp = all_s if "Todas" in sedes_user else sedes_user
            
            f_sede = st.selectbox("Filtrar Sede", disp)
            grupos = df_plant[df_plant['sede'] == f_sede]
            
            if rol != "Administrador":
                grupos = grupos[grupos['entrenador_asignado'].astype(str).str.contains(user, case=False, na=False)]
            
            if not grupos.empty:
                cols = st.columns(3)
                for i, (idx, row) in enumerate(grupos.iterrows()):
                    with cols[i%3]:
                        st.markdown(f"""
                        <div class="training-card">
                            <b>{row['dia']} {row['horario']}</b><br>{row['grupo']}
                        </div>""", unsafe_allow_html=True)
                        if st.button(f"Gestionar", key=f"g_{row['id']}_{i}", use_container_width=True):
                            st.session_state["selected_group_id"] = row['id']; st.rerun()
            else: st.info("No tienes grupos aquí.")
    else:
        gid = st.session_state["selected_group_id"]
        df_plant = get_df("entrenamientos_plantilla")
        if not df_plant.empty and str(gid) in df_plant['id'].astype(str).values:
            grp = df_plant[df_plant['id'] == str(gid)].iloc[0]
            
            if st.button("⬅️ Volver"): st.session_state["selected_group_id"]=None; st.rerun()
            st.title(f"{grp['grupo']} ({grp['dia']})")
            
            t_plantel, t_asist = st.tabs(["👥 Plantel", "✅ Planilla"])
            
            with t_plantel:
                df_insc = get_df("inscripciones")
                df_soc = get_df("socios")
                inscritos = df_insc[df_insc['id_entrenamiento'] == str(gid)] if not df_insc.empty else pd.DataFrame()
                
                st.metric("Alumnos", len(inscritos))
                if not inscritos.empty:
                    for idx, r in inscritos.iterrows():
                        c1, c2 = st.columns([4,1])
                        c1.write(r['nombre_alumno'])
                        if c2.button("Baja", key=f"b_{r['id']}"):
                             delete_row_by_condition("inscripciones", "id", r['id'])
                             st.success("Baja OK"); time.sleep(0.5); st.rerun()
                
                st.divider()
                if not df_soc.empty:
                    act = df_soc[df_soc['activo']==1]
                    ya = inscritos['id_socio'].tolist() if not inscritos.empty else []
                    disp = act[~act['id'].isin(ya)]
                    if not disp.empty:
                        alu = st.selectbox("Inscribir", disp['id'].astype(str) + " - " + disp['nombre'] + " " + disp['apellido'])
                        if st.button("Agregar"):
                            uid = int(alu.split(" - ")[0]); nom = alu.split(" - ")[2] 
                            if not check_horario_conflict(uid, grp['dia'], grp['horario']):
                                save_row("inscripciones", [generate_id(), uid, nom, gid, ""])
                                st.success("Agregado"); time.sleep(1); st.rerun()
                            else: st.error("Conflicto Horario")

            with t_asist:
                hoy = get_today_ar()
                f_sel = st.date_input("Fecha", hoy)
                
                with st.form("asis"):
                    st.write(f"Planilla del {f_sel}")
                    checks = {}
                    notas = {}
                    if not inscritos.empty:
                        for idx, r in inscritos.iterrows():
                            c1, c2 = st.columns([1,2])
                            checks[r['id_socio']] = c1.checkbox(r['nombre_alumno'], True, key=f"chk_{r['id_socio']}")
                            if not checks[r['id_socio']]:
                                notas[r['id_socio']] = c2.selectbox("Motivo", get_lista_opciones("motivo_ausencia", DEF_MOTIVOS), key=f"m_{r['id_socio']}")
                            else: notas[r['id_socio']] = ""
                    
                    st.markdown("---")
                    inv = None
                    if not df_soc.empty:
                        act = df_soc[df_soc['activo']==1]
                        inv_sel = st.selectbox("Invitado", ["--"] + act['id'].astype(str).tolist() + " - " + act['nombre'])
                        tipo = st.radio("Tipo", ["Recuperatorio", "Extra"])
                        if inv_sel != "--": inv = inv_sel

                    if st.form_submit_button("Guardar"):
                        cnt = 0
                        for uid, p in checks.items():
                            est = "Presente" if p else "Ausente"
                            n = notas.get(uid, "")
                            nom = inscritos[inscritos['id_socio']==str(uid)].iloc[0]['nombre_alumno']
                            save_row("asistencias", [str(f_sel), datetime.now().strftime("%H:%M"), uid, nom, grp['sede'], grp['grupo'], est, n])
                            cnt+=1
                        
                        if inv:
                            uid_i = int(inv.split(" - ")[0]); nom_i = inv.split(" - ")[1]
                            save_row("asistencias", [str(f_sel), datetime.now().strftime("%H:%M"), uid_i, nom_i, grp['sede'], grp['grupo'], "Presente", f"Invitado: {tipo}"])
                            cnt+=1
                            if "Extra" in tipo:
                                save_row("pagos", [generate_id(), str(f_sel), uid_i, nom_i, 5000, "Clase Extra", "Pendiente", "", "Pendiente", user, str(f_sel)])
                                st.toast("Deuda generada.")
                        st.success(f"{cnt} guardados")
        else:
            st.error("Grupo no encontrado.")
            if st.button("Volver"): st.session_state["selected_group_id"]=None; st.rerun()

# === ALUMNOS ===
elif nav == "Alumnos":
    if st.session_state["view_profile_id"] is None:
        st.title("👥 Gestión de Alumnos")
        tab_dir, tab_new = st.tabs(["📂 Directorio", "➕ Nuevo Alumno"])
        
        with tab_dir:
            df = get_df("socios")
            if not df.empty:
                with st.expander("🔍 Filtros", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    f_sede = c1.selectbox("Sede", ["Todas"] + get_lista_opciones("sede", DEF_SEDES))
                    f_act = c2.selectbox("Estado", ["Activos", "Inactivos", "Todos"])
                    search = c3.text_input("Buscar (Nombre/DNI)")
                
                df_fil = df.copy()
                if f_sede != "Todas": df_fil = df_fil[df_fil['sede'] == f_sede]
                if f_act == "Activos": df_fil = df_fil[df_fil['activo'] == 1]
                elif f_act == "Inactivos": df_fil = df_fil[df_fil['activo'] == 0]
                if search: df_fil = df_fil[df_fil.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
                
                st.caption(f"Resultados: {len(df_fil)}")
                rows = 20
                pag = st.number_input("Página", 1, (len(df_fil)//rows)+1, 1)
                start = (pag-1)*rows
                for idx, row in df_fil.iloc[start:start+rows].iterrows():
                    status = "🟢" if row['activo']==1 else "🔴"
                    label = f"{status} {row['nombre']} {row['apellido']} | DNI: {row['dni']} | {row['sede']} | Plan: {row.get('plan','-')}"
                    if st.button(label, key=f"r_{row['id']}_{idx}", use_container_width=True):
                        st.session_state["view_profile_id"] = row['id']
                        st.rerun()
        
        with tab_new:
            st.subheader("Alta Completa")
            with st.form("alta"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nombre")
                ape = c2.text_input("Apellido")
                dni = c1.text_input("DNI")
                nac = c2.date_input("Nacimiento", date(2000,1,1))
                sede = st.selectbox("Sede", get_lista_opciones("sede", DEF_SEDES))
                grupo = st.selectbox("Categoría", GRUPOS_GEN)
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
                        row = [uid, str(get_today_ar()), nom, ape, dni, str(nac), tutor, wsp, email, sede, plan, "", user, 1, talle, grupo, peso, alt]
                        save_row("socios", row)
                        st.success("Guardado")
    else:
        uid = st.session_state["view_profile_id"]
        df = get_df("socios")
        if not df.empty:
            p_data = df[df['id'] == str(uid)]
            if not p_data.empty:
                p = p_data.iloc[0]
                if st.button("⬅️ Volver"): 
                    st.session_state["view_profile_id"]=None
                    st.rerun()
                
                st.title(f"👤 {p['nombre']} {p['apellido']}")
                
                # --- PESTAÑAS DEL PERFIL UNIFICADO ---
                t1, t2, t3, t4 = st.tabs(["✏️ Datos", "⚽ Mis Grupos", "📅 Asistencia", "💳 Pagos"])
                
                with t1:
                    if rol == "Administrador":
                        with st.form("edit"):
                            c1,c2 = st.columns(2)
                            n_nom = c1.text_input("Nombre", p['nombre'])
                            n_ape = c2.text_input("Apellido", p['apellido'])
                            n_dni = c1.text_input("DNI", p['dni'])
                            n_sede = c2.selectbox("Sede", get_lista_opciones("sede", DEF_SEDES), index=0)
                            df_tar = get_df("tarifas")
                            pl = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                            idx = pl.index(p['plan']) if p['plan'] in pl else 0
                            n_plan = st.selectbox("Plan", pl, index=idx)
                            n_tutor = st.text_input("Tutor", p.get('tutor',''))
                            n_wsp = st.text_input("Wsp", p.get('whatsapp',''))
                            n_email = st.text_input("Email", p.get('email',''))
                            n_talle = st.text_input("Talle", p.get('talle',''))
                            c3, c4 = st.columns(2)
                            n_peso = c3.number_input("Peso", value=float(p.get('peso') or 0))
                            n_alt = c4.number_input("Altura", value=int(p.get('altura') or 0))
                            n_notas = st.text_area("Notas", p.get('notas',''))
                            n_act = st.checkbox("Activo", value=True if p['activo']==1 else False)
                            
                            if st.form_submit_button("Guardar"):
                                d = {
                                    'nombre': n_nom, 'apellido': n_ape, 'dni': n_dni, 'sede': n_sede, 'plan': n_plan, 'activo': 1 if n_act else 0,
                                    'email': n_email, 'whatsapp': n_wsp, 'talle': n_talle, 'tutor': n_tutor, 'notas': n_notas,
                                    'nacimiento': p.get('fecha_nacimiento',''), 'peso': n_peso, 'altura': n_alt, 'grupo': p.get('grupo','')
                                }
                                update_full_socio(uid, d, user, p.to_dict())
                                st.success("Ok"); time.sleep(1); st.rerun()
                    else: st.info("Solo lectura")
                
                # --- NUEVA PESTAÑA: GESTIÓN DE GRUPOS DESDE EL PERFIL ---
                with t2:
                    st.subheader("Grupos de Entrenamiento")
                    df_insc = get_df("inscripciones")
                    df_plant = get_df("entrenamientos_plantilla")
                    
                    # 1. Ver Inscripciones Actuales
                    mis_insc = df_insc[df_insc['id_socio'] == str(uid)] if not df_insc.empty else pd.DataFrame()
                    
                    if not mis_insc.empty:
                        st.write("Actualmente inscrito en:")
                        for idx, row_ins in mis_insc.iterrows():
                            # Buscar detalle del grupo
                            grp_name = "Grupo Desconocido"
                            if not df_plant.empty:
                                grp_match = df_plant[df_plant['id'] == str(row_ins['id_entrenamiento'])]
                                if not grp_match.empty:
                                    g = grp_match.iloc[0]
                                    grp_name = f"{g['dia']} {g['horario']} - {g['grupo']} ({g['sede']})"
                            
                            c_txt, c_del = st.columns([4,1])
                            c_txt.info(grp_name)
                            if c_del.button("Dar de Baja", key=f"del_ins_{row_ins['id']}"):
                                delete_row_by_condition("inscripciones", "id", row_ins['id'])
                                st.success("Baja Exitosa")
                                time.sleep(0.5); st.rerun()
                    else:
                        st.info("No está inscrito en ningún grupo.")
                    
                    st.divider()
                    
                    # 2. Inscribir en Nuevo Grupo
                    st.markdown("#### ➕ Inscribir en Nuevo Grupo")
                    if not df_plant.empty:
                        # Filtros para encontrar grupo
                        c1, c2 = st.columns(2)
                        f_sede_ins = c1.selectbox("Sede", get_lista_opciones("sede", DEF_SEDES), key="prof_ins_sede")
                        f_dia_ins = c2.selectbox("Día", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"], key="prof_ins_dia")
                        
                        grupos_disp = df_plant[(df_plant['sede'] == f_sede_ins) & (df_plant['dia'] == f_dia_ins)]
                        
                        if not grupos_disp.empty:
                            # Crear lista legible con cupos
                            opciones_grp = []
                            ids_grp = []
                            for i, g in grupos_disp.iterrows():
                                ocupados = len(df_insc[df_insc['id_entrenamiento'] == str(g['id'])]) if not df_insc.empty else 0
                                libres = int(g['cupo_max']) - ocupados
                                texto = f"{g['horario']} - {g['grupo']} (Libres: {libres})"
                                opciones_grp.append(texto)
                                ids_grp.append(g['id'])
                            
                            sel_grp_txt = st.selectbox("Seleccionar Grupo", opciones_grp)
                            idx_sel = opciones_grp.index(sel_grp_txt)
                            id_grp_sel = ids_grp[idx_sel]
                            
                            # Obtener datos del grupo seleccionado para validar horario
                            grp_sel_data = grupos_disp[grupos_disp['id'] == str(id_grp_sel)].iloc[0]
                            
                            if st.button("Confirmar Inscripción"):
                                # Validar Conflicto
                                if check_horario_conflict(uid, grp_sel_data['dia'], grp_sel_data['horario']):
                                    st.error("⚠️ Conflicto: El alumno ya tiene clase en ese horario.")
                                else:
                                    # Validar Cupo
                                    ocupados = len(df_insc[df_insc['id_entrenamiento'] == str(id_grp_sel)]) if not df_insc.empty else 0
                                    if ocupados < int(grp_sel_data['cupo_max']):
                                        save_row("inscripciones", [generate_id(), uid, f"{p['nombre']} {p['apellido']}", id_grp_sel, ""])
                                        st.success("Inscrito correctamente.")
                                        time.sleep(1); st.rerun()
                                    else:
                                        st.error("🚫 Grupo Lleno.")
                        else:
                            st.warning("No hay grupos disponibles con esos filtros.")
                
                with t3:
                    df_a = get_df("asistencias")
                    if not df_a.empty:
                        mis_a = df_a[df_a['id_socio'] == str(uid)]
                        if not mis_a.empty:
                            mis_a['dt'] = pd.to_datetime(mis_a['fecha'], errors='coerce')
                            mis_a['Dia'] = mis_a['dt'].dt.day_name()
                            fig = px.pie(mis_a, names='Dia', title='Días de Entreno')
                            st.plotly_chart(fig, use_container_width=True)
                            st.dataframe(mis_a[['fecha', 'sede', 'grupo_turno', 'estado', 'nota']], use_container_width=True)
                        else: st.info("Sin datos.")
                
                with t4:
                    df_p = get_df("pagos")
                    if not df_p.empty:
                        mis_p = df_p[df_p['id_socio']==str(uid)]
                        if not mis_p.empty: st.dataframe(mis_p, use_container_width=True)

# === CONTABILIDAD ===
elif nav == "Contabilidad":
    st.title("📒 Contabilidad")
    with st.sidebar:
        st.markdown("### Filtros")
        f_sede = st.multiselect("Sede", DEF_SEDES, default=DEF_SEDES)
        f_mes = st.selectbox("Mes", ["Todos"] + MESES)
    
    tab_cuotas, tab_ocasional, tab_rep = st.tabs(["📋 Gestión", "🛍️ Ocasional", "📊 Caja"])
    
    with tab_cuotas:
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
        
        # Auto-Gen
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
                if save_rows_bulk("pagos", filas):
                    st.success(f"Auto-Generadas {len(filas)} cuotas."); time.sleep(1); st.rerun()

        # Cobro
        if st.session_state["cobro_alumno_id"]:
            uid = st.session_state["cobro_alumno_id"]
            alu = df_soc[df_soc['id']==str(uid)].iloc[0]
            st.subheader(f"Cobrar a: {alu['nombre']}")
            if st.button("Cancelar"): st.session_state["cobro_alumno_id"]=None; st.rerun()
            
            df_tar = get_df("tarifas")
            lst = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
            
            c1, c2 = st.columns(2)
            conc = c1.selectbox("Concepto", lst)
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
                chk = df_pag[(df_pag['id_socio']==str(uid)) & (df_pag['mes_cobrado']==mes_p) & (df_pag['estado']=='Pendiente')]
                if not chk.empty: deuda_id = chk.iloc[0]['id']
            
            if st.button("PAGAR", type="primary", use_container_width=True):
                if conc != alu['plan']: update_plan_socio(uid, conc)
                st_pago = "Confirmado" if conf else "Pendiente"
                
                if deuda_id: registrar_pago_existente(deuda_id, met, user, st_pago, mon, conc, nota)
                else: save_row("pagos", [generate_id(), str(get_today_ar()), uid, f"{alu['nombre']} {alu['apellido']}", mon, conc, met, nota, st_pago, user, mes_p])
                
                st.success("Listo")
                d_pdf = {"fecha":str(get_today_ar()), "alumno":f"{alu['nombre']} {alu['apellido']}", "monto":mon, "concepto":conc, "metodo":met, "mes":mes_p, "nota":nota}
                pdf_b = generar_pdf(d_pdf)
                b64 = base64.b64encode(pdf_b).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Recibo.pdf"><button>Descargar Recibo</button></a>'
                st.markdown(href, unsafe_allow_html=True)
                time.sleep(3); st.session_state["cobro_alumno_id"]=None; st.rerun()

        else:
            st.subheader("Listado de Cobro")
            col_s, col_r = st.columns([3,1])
            search = col_s.text_input("Buscar")
            rows = col_r.selectbox("Filas", [25, 50])
            
            if not df_soc.empty:
                df_show = df_soc[df_soc['activo']==1]
                if search: df_show = df_show[df_show.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
                
                subset = df_show.head(rows)
                cols = st.columns([3, 2, 2, 2])
                cols[0].markdown("**Alumno**"); cols[1].markdown("**Sede**"); cols[2].markdown(f"**{mes_target}**"); cols[3].markdown("**Acción**")
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
            r = st.selectbox("Rol", ["Administrador", "Entrenador"])
            s = st.multiselect("Sedes", DEF_SEDES)
            if st.form_submit_button("Crear"):
                h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
                save_row("usuarios", [generate_id(), u, h, r, n, ",".join(s), 1])
                st.success("Creado")
    else: st.error("Restringido")
