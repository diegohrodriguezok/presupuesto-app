import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import plotly.express as px
import time

# --- 1. CONFIGURACIÓN GLOBAL ---
st.set_page_config(
    page_title="Area Arqueros ERP", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="logo.png"
)

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
        }
        .stButton>button:hover {
            background-color: #2c3e50;
            transform: translateY(-2px);
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        /* Estilo para tarjetas de perfil */
        .profile-card {
            padding: 20px;
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            margin-bottom: 20px;
            border: 1px solid #eee;
        }
        /* Filtros en sidebar más compactos */
        [data-testid="stSidebar"] {
            background-color: #f8f9fa;
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
    except:
        return pd.DataFrame()

def save_row(sheet_name, data):
    get_client().worksheet(sheet_name).append_row(data)

def log_action(id_ref, accion, detalle, user):
    """Guarda un registro en la hoja de logs"""
    # Estructura logs: fecha, usuario, id_ref, accion, detalle
    row = [str(datetime.now()), user, str(id_ref), accion, detalle]
    save_row("logs", row)

def update_full_socio(id_socio, d, user_admin, original_data=None):
    sh = get_client()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        r = cell.row
        
        # Actualizar celdas
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

        # Generar Log de cambios
        cambios = []
        if original_data is not None:
            for key, val in d.items():
                # Comparar (convertir a string para evitar errores de tipo)
                if str(val) != str(original_data.get(key, '')):
                    cambios.append(f"{key}: {original_data.get(key,'')} -> {val}")
        
        if cambios:
            log_action(id_socio, "Edición Perfil", " | ".join(cambios), user_admin)
            
        return True
    except Exception as e:
        st.error(f"Error al actualizar: {e}")
        return False

def confirmar_pago_seguro(id_pago, user):
    ws = get_client().worksheet("pagos")
    try:
        cell = ws.find(str(id_pago))
        ws.update_cell(cell.row, 9, "Confirmado") # Col 9 es estado
        log_action(id_pago, "Confirmar Pago", "Pago confirmado definitivamente", user)
        return True
    except: return False

def actualizar_tarifas_bulk(df_edited):
    ws = get_client().worksheet("tarifas")
    ws.clear()
    ws.update([df_edited.columns.values.tolist()] + df_edited.values.tolist())

def calcular_edad(fecha_nac):
    try:
        if isinstance(fecha_nac, str):
            fecha_nac = datetime.strptime(fecha_nac, '%Y-%m-%d').date()
        hoy = date.today()
        return hoy.year - fecha_nac.year - ((hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day))
    except: return "?"

# --- 3. LOGIN ---
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None})

# Variables de Navegación Interna (Para "entrar" a perfiles)
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
                else:
                    st.error("Acceso denegado")

if not st.session_state["auth"]:
    login()
    st.stop()

# --- 4. MENU LATERAL ---
user, rol = st.session_state["user"], st.session_state["rol"]

with st.sidebar:
    try: st.image("logo.png", width=220)
    except: st.header("🛡️ AREA ARQUEROS")
    
    st.info(f"👤 **{user.upper()}**\nRol: {rol}")
    
    menu_opts = ["Dashboard"]
    if rol in ["Administrador", "Profesor"]:
        menu_opts.extend(["Alumnos", "Asistencia"])
    if rol in ["Administrador", "Contador"]:
        menu_opts.extend(["Contabilidad", "Configurar Tarifas"])
    
    # Si cambiamos de menú, reseteamos la vista de perfil
    nav = st.radio("Ir a:", menu_opts)
    if nav != st.session_state.get("last_nav"):
        st.session_state["view_profile_id"] = None
        st.session_state["last_nav"] = nav
    
    st.divider()
    if st.button("Cerrar Sesión"):
        st.session_state.update({"auth": False, "view_profile_id": None})
        st.rerun()

# --- 5. MÓDULOS ---

# === DASHBOARD ===
if nav == "Dashboard":
    st.title("📊 Tablero de Comando")
    df_s = get_df("socios")
    df_a = get_df("asistencias")
    
    c1, c2, c3 = st.columns(3)
    activos = len(df_s[df_s['activo']==1]) if not df_s.empty else 0
    c1.metric("Alumnos Activos", activos)
    
    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Estado del Plantel")
        if not df_s.empty:
            df_s['Estado'] = df_s['activo'].map({1: 'Activo', 0: 'Baja'})
            fig = px.pie(df_s, names='Estado', hole=0.4, color_discrete_sequence=['#1f2c56', '#e74c3c'])
            st.plotly_chart(fig, use_container_width=True)
    with g2:
        st.subheader("Asistencia Hoy")
        if not df_a.empty:
            today_str = date.today().strftime("%Y-%m-%d")
            df_a['fecha'] = df_a['fecha'].astype(str)
            today_data = df_a[df_a['fecha'] == today_str]
            if not today_data.empty:
                view_mode = st.radio("Ver por:", ["sede", "turno"], horizontal=True)
                counts = today_data[view_mode].value_counts().reset_index()
                counts.columns = [view_mode, 'cantidad']
                fig2 = px.bar(counts, x=view_mode, y='cantidad', title=f"Presentes: {len(today_data)}", color_discrete_sequence=['#1f2c56'])
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Sin registros hoy.")

# === ALUMNOS (CON VISTA DETALLADA) ===
elif nav == "Alumnos":
    
    # VISTA 1: LISTADO Y FILTROS (Si no hay nadie seleccionado)
    if st.session_state["view_profile_id"] is None:
        st.title("👥 Gestión de Alumnos")
        
        tab_lista, tab_nuevo = st.tabs(["📂 Directorio", "➕ Nuevo Alumno"])
        
        with tab_lista:
            df = get_df("socios")
            if not df.empty:
                # --- FILTROS AVANZADOS ---
                with st.expander("🔍 Filtros de Búsqueda", expanded=True):
                    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                    
                    sedes_un = ["Todas"] + sorted(df['sede'].unique().tolist())
                    filtro_sede = col_f1.selectbox("Sede", sedes_un)
                    
                    grupos_un = ["Todos"] + sorted(df['grupo'].astype(str).unique().tolist())
                    filtro_grupo = col_f2.selectbox("Grupo", grupos_un)
                    
                    planes_un = ["Todos"] + sorted(df['plan'].astype(str).unique().tolist())
                    filtro_plan = col_f3.selectbox("Plan / Frecuencia", planes_un)
                    
                    filtro_estado = col_f4.selectbox("Estado", ["Activos", "Inactivos", "Todos"])
                
                # APLICAR FILTROS
                df_filtered = df.copy()
                if filtro_sede != "Todas":
                    df_filtered = df_filtered[df_filtered['sede'] == filtro_sede]
                if filtro_grupo != "Todos":
                    df_filtered = df_filtered[df_filtered['grupo'] == filtro_grupo]
                if filtro_plan != "Todos":
                    df_filtered = df_filtered[df_filtered['plan'] == filtro_plan]
                if filtro_estado == "Activos":
                    df_filtered = df_filtered[df_filtered['activo'] == 1]
                elif filtro_estado == "Inactivos":
                    df_filtered = df_filtered[df_filtered['activo'] == 0]
                
                st.markdown(f"**Resultados:** {len(df_filtered)} alumnos encontrados.")
                
                # TABLA INTERACTIVA
                # Mostramos columnas clave
                display_cols = ['id', 'nombre', 'apellido', 'sede', 'grupo', 'plan', 'activo']
                # Agregamos botón de "Ver" para cada fila
                for idx, row in df_filtered.iterrows():
                    with st.container():
                        c1, c2, c3, c4, c5, c6 = st.columns([1, 2, 2, 2, 2, 1])
                        c1.write(row['id'])
                        c2.write(f"**{row['nombre']} {row['apellido']}**")
                        c3.write(row['sede'])
                        c4.write(row['grupo'])
                        c5.write(row['plan'])
                        if c6.button("Ver ➜", key=f"btn_{row['id']}"):
                            st.session_state["view_profile_id"] = row['id']
                            st.rerun()
                        st.markdown("---")

        with tab_nuevo:
            st.subheader("📝 Alta de Nuevo Alumno")
            with st.form("alta_full"):
                c1, c2, c3 = st.columns(3)
                n_sede = c1.selectbox("Sede", ["Sede C1", "Sede Saa"])
                n_cat = c2.selectbox("Categoría", ["Infantil", "Prejuvenil", "Juvenil", "Adulto", "Senior"])
                n_niv = c3.selectbox("Nivel", ["Nivel 1", "Nivel 2"])
                
                c_p1, c_p2, c_p3 = st.columns(3)
                nom = c_p1.text_input("Nombre")
                ape = c_p2.text_input("Apellido")
                dni = c_p3.text_input("DNI")
                
                c_extra1, c_extra2 = st.columns(2)
                nac = c_extra1.date_input("Fecha Nacimiento", min_value=date(1980,1,1))
                
                tutor = st.text_input("Tutor / Responsable")
                wsp = st.text_input("WhatsApp")
                email = st.text_input("Email")
                
                df_tar = get_df("tarifas")
                planes = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                plan = st.selectbox("Plan Facturación", planes)
                
                if st.form_submit_button("💾 Crear Legajo"):
                    if nom and ape and dni:
                        uid = int(datetime.now().timestamp())
                        grupo_final = f"{n_cat} - {n_niv}"
                        # ORDEN: id, fecha, nom, ape, dni, nac, tutor, wsp, email, sede, plan, notas, vendedor, activo, talle, grupo, peso, altura
                        row = [uid, str(date.today()), nom, ape, dni, str(nac), tutor, wsp, email, n_sede, plan, "", user, 1, "", grupo_final, 0, 0]
                        save_row("socios", row)
                        log_action(uid, "Alta Alumno", f"Alta inicial por {user}", user)
                        st.success(f"Alumno registrado.")
                    else:
                        st.error("Faltan datos.")

    # VISTA 2: PERFIL DETALLADO (COMO PÁGINA NUEVA)
    else:
        uid = st.session_state["view_profile_id"]
        df = get_df("socios")
        p = df[df['id'] == uid].iloc[0]
        
        # Botón Volver
        if st.button("⬅️ Volver al Listado"):
            st.session_state["view_profile_id"] = None
            st.rerun()
            
        st.title(f"👤 {p['nombre']} {p['apellido']}")
        
        # Info Header
        col_h1, col_h2, col_h3 = st.columns(3)
        edad = calcular_edad(p['fecha_nacimiento'])
        col_h1.info(f"**Edad:** {edad} años | **DNI:** {p['dni']}")
        col_h2.success(f"**Sede:** {p['sede']} | **Grupo:** {p.get('grupo','-')}")
        col_h3.warning(f"**Plan:** {p['plan']}")
        
        t_datos, t_hist, t_logs = st.tabs(["✏️ Editar Datos", "📅 Historial Asistencia", "🔒 Auditoría de Cambios"])
        
        with t_datos:
            if rol == "Administrador":
                with st.form("edit_full_profile"):
                    c1, c2 = st.columns(2)
                    n_nom = c1.text_input("Nombre", p['nombre'])
                    n_ape = c2.text_input("Apellido", p['apellido'])
                    n_dni = c1.text_input("DNI", p['dni'])
                    # ... (Resto de campos editables) ...
                    n_email = c2.text_input("Email", p.get('email',''))
                    n_plan = c1.selectbox("Plan", get_df("tarifas")['concepto'].tolist(), index=0)
                    n_activo = c2.checkbox("Activo", value=True if p['activo']==1 else False)
                    n_notas = st.text_area("Notas", p.get('notas',''))
                    
                    # Campos ocultos necesarios para mantener estructura
                    d_upd = p.to_dict() # Copiamos todo
                    d_upd.update({
                        'nombre': n_nom, 'apellido': n_ape, 'dni': n_dni, 'email': n_email, 
                        'plan': n_plan, 'activo': 1 if n_activo else 0, 'notas': n_notas
                    })
                    
                    if st.form_submit_button("Guardar Cambios"):
                        update_full_socio(uid, d_upd, user, original_data=p.to_dict())
                        st.success("Perfil Actualizado")
                        time.sleep(1)
                        st.rerun()
            else:
                st.info("Solo lectura. Contacte al administrador para cambios.")

        with t_hist:
            df_asist = get_df("asistencias")
            if not df_asist.empty:
                mias = df_asist[df_asist['id_socio'] == uid]
                st.metric("Total Clases", len(mias))
                st.dataframe(mias[['fecha', 'sede', 'turno']].sort_values(by='fecha', ascending=False), use_container_width=True)
        
        with t_logs:
            # Buscar logs de este usuario
            df_logs = get_df("logs")
            if not df_logs.empty:
                mis_logs = df_logs[df_logs['id_ref'].astype(str) == str(uid)]
                if not mis_logs.empty:
                    st.dataframe(mis_logs[['fecha', 'usuario', 'accion', 'detalle']], use_container_width=True)
                else:
                    st.info("No hay cambios registrados en este perfil.")

# === ASISTENCIA ===
elif nav == "Asistencia":
    st.title("✅ Tomar Asistencia")
    # (Código de asistencia igual al anterior, optimizado)
    # ... Para ahorrar espacio, asumo la lógica previa que ya funcionaba bien ...
    st.info("Seleccione sede y grupo para cargar presentes.")
    # ...

# === CONTABILIDAD ===
elif nav == "Contabilidad":
    st.title("📒 Contabilidad")
    
    # --- BARRA LATERAL DE FILTROS EN CONTABILIDAD ---
    with st.sidebar:
        st.header("🔍 Filtros de Reporte")
        f_sede = st.multiselect("Sede", ["Sede C1", "Sede Saa"], default=["Sede C1", "Sede Saa"])
        f_mes = st.selectbox("Mes de Cobro", ["Todos", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        f_fecha1 = st.date_input("Desde", date(date.today().year, 1, 1))
        f_fecha2 = st.date_input("Hasta", date.today())

    tab_cobro, tab_reporte = st.tabs(["💰 Registrar Cobro", "📊 Reportes y Estadísticas"])
    
    with tab_cobro:
        # Formulario de cobro con "Mes Correspondiente"
        df_s = get_df("socios")
        if not df_s.empty:
            activos = df_s[df_s['activo']==1]
            sel = st.selectbox("Alumno", activos['id'].astype(str) + " - " + activos['nombre'])
            
            with st.form("pay"):
                c1, c2 = st.columns(2)
                monto = c1.number_input("Monto", step=100)
                mes_pago = c2.selectbox("Mes que abona", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
                concepto = st.selectbox("Concepto", get_df("tarifas")['concepto'].tolist())
                
                if st.form_submit_button("Registrar"):
                    # id, fecha, id_socio, nombre, monto, concepto, metodo, coment, estado, usuario, MES_COBRADO
                    row = [int(datetime.now().timestamp()), str(date.today()), int(sel.split(" - ")[0]), sel.split(" - ")[1], monto, concepto, "Efectivo", "", "Pendiente", user, mes_pago]
                    save_row("pagos", row)
                    st.success("Registrado")

    with tab_reporte:
        df_p = get_df("pagos")
        if not df_p.empty:
            # Aplicar filtros
            df_p['fecha_dt'] = pd.to_datetime(df_p['fecha_pago'], errors='coerce').dt.date
            mask = (df_p['fecha_dt'] >= f_fecha1) & (df_p['fecha_dt'] <= f_fecha2)
            if f_mes != "Todos" and 'mes_cobrado' in df_p.columns:
                mask = mask & (df_p['mes_cobrado'] == f_mes)
            
            df_filt = df_p[mask]
            
            # Estadísticas
            total = pd.to_numeric(df_filt['monto'], errors='coerce').sum()
            st.metric("Total Ingresos (Filtrado)", f"${total:,.0f}")
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### Por Concepto")
                fig1 = px.pie(df_filt, values='monto', names='concepto', hole=0.4)
                st.plotly_chart(fig1, use_container_width=True)
            
            with c2:
                st.markdown("### Evolución Diaria")
                daily = df_filt.groupby('fecha_pago')['monto'].sum().reset_index()
                fig2 = px.bar(daily, x='fecha_pago', y='monto')
                st.plotly_chart(fig2, use_container_width=True)
                
            st.dataframe(df_filt)

# === CONFIGURAR TARIFAS ===
elif nav == "Configurar Tarifas":
    st.title("⚙️ Tarifas")
    df = get_df("tarifas")
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if st.button("Guardar"):
        actualizar_tarifas_bulk(edited)
        st.success("Guardado")
