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
    page_icon="🏹"
)

st.markdown("""
    <style>
        .stButton>button {
            border-radius: 6px;
            height: 45px;
            font-weight: 600;
            border: 1px solid rgba(255,255,255,0.1);
            background-color: #1f2c56;
            color: white;
            transition: all 0.3s;
        }
        .stButton>button:hover {
            background-color: #2c3e50;
            border-color: white;
            color: #ffffff;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.6rem !important;
            font-weight: 700;
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

def update_full_socio(id_socio, d):
    """Actualiza TODOS los datos del alumno en sus columnas correspondientes"""
    sh = get_client()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        r = cell.row
        # Mapeo estricto de columnas (Verificar orden en Google Sheets)
        ws.update_cell(r, 3, d['nombre'])
        ws.update_cell(r, 4, d['apellido'])
        ws.update_cell(r, 5, d['dni'])
        ws.update_cell(r, 6, str(d['nacimiento']))
        ws.update_cell(r, 7, d['tutor'])    # Col 7
        ws.update_cell(r, 8, d['whatsapp']) # Col 8
        ws.update_cell(r, 9, d['email'])    # Col 9
        ws.update_cell(r, 10, d['sede'])
        ws.update_cell(r, 11, d['plan'])
        ws.update_cell(r, 12, d['notas'])
        # Col 13 es vendedor (no se edita usualmente)
        ws.update_cell(r, 14, d['activo'])
        ws.update_cell(r, 15, d['talle'])
        ws.update_cell(r, 16, d['grupo'])
        ws.update_cell(r, 17, d['peso'])    # Col 17
        ws.update_cell(r, 18, d['altura'])  # Col 18
        return True
    except Exception as e:
        st.error(f"Error al actualizar: {e}")
        return False

def confirmar_pago_seguro(id_pago):
    # Asume columna 9 para estado en hoja pagos
    ws = get_client().worksheet("pagos")
    try:
        cell = ws.find(str(id_pago))
        ws.update_cell(cell.row, 9, "Confirmado")
        return True
    except: return False

def actualizar_tarifas_bulk(df_edited):
    ws = get_client().worksheet("tarifas")
    ws.clear()
    ws.update([df_edited.columns.values.tolist()] + df_edited.values.tolist())

def calcular_edad(fecha_nac):
    hoy = date.today()
    return hoy.year - fecha_nac.year - ((hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day))

# --- 3. LOGIN ---
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None})

def login():
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.markdown("<h2 style='text-align: center;'>🔐 Area Arqueros</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar", use_container_width=True):
                CREDS = {
                    "admin": {"p": "admin2024", "r": "Administrador"},
                    "profe": {"p": "entrenador", "r": "Profesor"},
                    "conta": {"p": "finanzas", "r": "Contador"}
                }
                if u in CREDS and CREDS[u]["p"] == p:
                    st.session_state.update({"auth": True, "user": u, "rol": CREDS[u]["r"]})
                    st.rerun()
                else:
                    st.error("Error de acceso")

if not st.session_state["auth"]:
    login()
    st.stop()

# --- 4. MENÚ PRINCIPAL ---
user, rol = st.session_state["user"], st.session_state["rol"]

with st.sidebar:
    try:
        st.image("logo.png", use_container_width=True)
    except:
        st.header("🛡️ AREA ARQUEROS")
    
    st.info(f"👤 **{user.upper()}**\nRol: {rol}")
    
    menu_opts = ["Dashboard"]
    if rol in ["Administrador", "Profesor"]:
        menu_opts.extend(["Alumnos", "Asistencia"]) # Se unificó Perfil y Nuevo
    if rol in ["Administrador", "Contador"]:
        menu_opts.extend(["Contabilidad", "Configurar Tarifas"])
    
    nav = st.radio("Navegación", menu_opts)
    st.divider()
    if st.button("Cerrar Sesión"):
        st.session_state.update({"auth": False})
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
                fig2 = px.bar(counts, x=view_mode, y='cantidad', title=f"Presentes: {len(today_data)}")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Sin registros hoy.")

# === ALUMNOS (UNIFICADO) ===
elif nav == "Alumnos":
    st.title("👥 Gestión de Alumnos")
    
    tab_perfil, tab_nuevo = st.tabs(["📂 Directorio & Perfil", "➕ Nuevo Alumno"])
    
    # --- PESTAÑA 1: BUSCADOR Y PERFIL ---
    with tab_perfil:
        df = get_df("socios")
        if not df.empty:
            df['label'] = df['id'].astype(str) + " | " + df['nombre'] + " " + df['apellido']
            sel = st.selectbox("🔍 Buscar Alumno:", df['label'])
            
            if sel:
                uid = int(sel.split(" | ")[0])
                p = df[df['id'] == uid].iloc[0]
                
                # Header Info
                try:
                    f_nac = datetime.strptime(p['fecha_nacimiento'], '%Y-%m-%d').date()
                    edad = calcular_edad(f_nac)
                except: edad = "?"
                
                h1, h2 = st.columns([1, 4])
                with h1: st.markdown("# 👤")
                with h2:
                    st.markdown(f"## {p['nombre']} {p['apellido']}")
                    st.caption(f"DNI: {p['dni']} | Edad: {edad}")
                    tags = f"**Plan:** {p['plan']} | **Sede:** {p['sede']} | **Grupo:** {p.get('grupo','-')}"
                    if p['activo'] == 1: st.success(tags)
                    else: st.error(f"BAJA - {tags}")

                sub_t1, sub_t2 = st.tabs(["📋 Ficha Completa", "📈 Historial"])
                
                with sub_t1:
                    # EDICIÓN COMPLETA
                    if rol == "Administrador":
                        with st.form("edit_full"):
                            st.subheader("Editar Datos")
                            e1, e2 = st.columns(2)
                            n_nom = e1.text_input("Nombre", p['nombre'])
                            n_ape = e2.text_input("Apellido", p['apellido'])
                            
                            e3, e4 = st.columns(2)
                            n_dni = e3.text_input("DNI", p['dni'])
                            f_origen = f_nac if isinstance(f_nac, date) else date(2000,1,1)
                            n_nac = e4.date_input("Nacimiento", f_origen)
                            
                            e5, e6 = st.columns(2)
                            n_tutor = e5.text_input("Tutor", p.get('tutor', ''))
                            n_wsp = e6.text_input("WhatsApp", p.get('whatsapp', ''))
                            
                            e7, e8 = st.columns(2)
                            n_email = e7.text_input("Email", p.get('email', ''))
                            n_sede = e8.selectbox("Sede", ["Sede C1", "Sede Saa"], index=0 if p['sede']=="Sede C1" else 1)
                            
                            e9, e10, e11 = st.columns(3)
                            n_peso = e9.number_input("Peso", value=float(p.get('peso', 0) or 0))
                            n_alt = e10.number_input("Altura", value=int(p.get('altura', 0) or 0))
                            n_talle = e11.text_input("Talle", p.get('talle', ''))

                            df_tar = get_df("tarifas")
                            planes_list = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                            curr_idx = planes_list.index(p['plan']) if p['plan'] in planes_list else 0
                            
                            e12, e13 = st.columns(2)
                            n_plan = e12.selectbox("Plan", planes_list, index=curr_idx)
                            n_grupo = e13.selectbox("Grupo", ["Inicial", "Intermedio", "Avanzado", "Arqueras", "Sin Grupo"], index=0)
                            
                            n_notas = st.text_area("Notas", p.get('notas', ''))
                            n_activo = st.checkbox("Alumno Activo", value=True if p['activo']==1 else False)

                            if st.form_submit_button("💾 Guardar Cambios"):
                                d_upd = {
                                    'nombre': n_nom, 'apellido': n_ape, 'dni': n_dni,
                                    'nacimiento': n_nac, 'tutor': n_tutor, 'whatsapp': n_wsp,
                                    'email': n_email, 'sede': n_sede, 'peso': n_peso, 'altura': n_alt,
                                    'talle': n_talle, 'plan': n_plan, 'grupo': n_grupo,
                                    'notas': n_notas, 'activo': 1 if n_activo else 0
                                }
                                if update_full_socio(uid, d_upd):
                                    st.success("Datos actualizados correctamente.")
                                    time.sleep(1)
                                    st.rerun()
                    else:
                        # VISTA SOLO LECTURA
                        c_a, c_b = st.columns(2)
                        c_a.write(f"**Tutor:** {p.get('tutor','-')}")
                        c_a.write(f"**Email:** {p.get('email','-')}")
                        c_b.write(f"**WhatsApp:** {p.get('whatsapp','-')}")
                        c_b.write(f"**Físico:** {p.get('peso','-')}kg / {p.get('altura','-')}cm")
                        st.text_area("Notas", p.get('notas',''), disabled=True)
                
                with sub_t2:
                    df_asist = get_df("asistencias")
                    if not df_asist.empty:
                        mias = df_asist[df_asist['id_socio'] == uid]
                        st.dataframe(mias[['fecha', 'sede']].tail(10), use_container_width=True)

    # --- PESTAÑA 2: NUEVO ALUMNO (COMPLETO) ---
    with tab_nuevo:
        st.subheader("📝 Alta de Nuevo Alumno")
        with st.form("alta_full"):
            st.markdown("##### 1. Datos Personales")
            c1, c2 = st.columns(2)
            nom = c1.text_input("Nombre")
            ape = c2.text_input("Apellido")
            
            c3, c4 = st.columns(2)
            dni = c3.text_input("DNI")
            nac = c4.date_input("Fecha Nacimiento", min_value=date(1980,1,1), max_value=date.today())
            st.caption(f"Edad: {calcular_edad(nac)} años")
            
            c5, c6 = st.columns(2)
            peso = c5.number_input("Peso (kg)", min_value=0.0)
            altura = c6.number_input("Altura (cm)", min_value=0)
            
            st.markdown("##### 2. Contacto y Responsable")
            tutor = st.text_input("Tutor / Responsable")
            c7, c8 = st.columns(2)
            wsp = c7.text_input("WhatsApp")
            email = c8.text_input("Email")
            
            st.markdown("##### 3. Datos Institucionales")
            c9, c10 = st.columns(2)
            sede = c9.selectbox("Sede", ["Sede C1", "Sede Saa"])
            grupo = c10.selectbox("Grupo", ["Inicial", "Intermedio", "Avanzado", "Arqueras", "Sin Grupo"])
            
            df_tar = get_df("tarifas")
            planes = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
            
            c11, c12 = st.columns(2)
            plan = c11.selectbox("Plan", planes)
            talle = c12.selectbox("Talle", ["10", "12", "14", "XS", "S", "M", "L", "XL"])
            
            st.markdown("---")
            if st.form_submit_button("💾 Crear Legajo"):
                if nom and ape and dni:
                    uid = int(datetime.now().timestamp())
                    # 18 CAMPOS EN ORDEN
                    row = [
                        uid, str(date.today()), nom, ape, dni, str(nac),
                        tutor, wsp, email, sede, plan, "", user, 1,
                        talle, grupo, peso, altura
                    ]
                    save_row("socios", row)
                    st.success("Alumno registrado correctamente.")
                else:
                    st.error("Faltan datos obligatorios (Nombre, Apellido, DNI).")

# === ASISTENCIA ===
elif nav == "Asistencia":
    st.title("✅ Tomar Lista")
    c1, c2 = st.columns(2)
    sede_sel = c1.selectbox("Sede", ["Sede C1", "Sede Saa"])
    grupo_sel = c2.selectbox("Grupo", ["Inicial", "Intermedio", "Avanzado", "Arqueras"])
    
    df = get_df("socios")
    if not df.empty and 'grupo' in df.columns:
        filtro = df[(df['sede'] == sede_sel) & (df['grupo'] == grupo_sel) & (df['activo'] == 1)]
        if not filtro.empty:
            with st.form("lista"):
                st.write(f"Alumnos: {len(filtro)}")
                cols = st.columns(3)
                checks = {}
                for i, (idx, r) in enumerate(filtro.iterrows()):
                    checks[r['id']] = cols[i%3].checkbox(f"{r['nombre']} {r['apellido']}", key=r['id'])
                if st.form_submit_button("Guardar Presentes"):
                    cnt = 0
                    for uid, p in checks.items():
                        if p:
                            n = filtro.loc[filtro['id']==uid, 'nombre'].values[0]
                            a = filtro.loc[filtro['id']==uid, 'apellido'].values[0]
                            row = [str(date.today()), datetime.now().strftime("%H:%M"), uid, f"{n} {a}", sede_sel, grupo_sel, "Presente"]
                            save_row("asistencias", row)
                            cnt+=1
                    st.success(f"{cnt} presentes guardados.")
        else:
            st.warning("Sin alumnos en este grupo.")

# === CONTABILIDAD ===
elif nav == "Contabilidad":
    st.title("📒 Finanzas")
    df_tar = get_df("tarifas")
    tarifas_opts = df_tar['concepto'].tolist() if not df_tar.empty else []
    
    tb1, tb2 = st.tabs(["💰 Ingresos", "✅ Auditoría"])
    
    with tb1:
        df_s = get_df("socios")
        if not df_s.empty:
            activos = df_s[df_s['activo']==1]
            sel_alu = st.selectbox("Alumno", activos['id'].astype(str) + " - " + activos['nombre'] + " " + activos['apellido'])
            
            with st.form("cobro"):
                c1, c2 = st.columns(2)
                concepto = c1.selectbox("Concepto", tarifas_opts + ["Otro"])
                precio = 0.0
                if not df_tar.empty and concepto in tarifas_opts:
                    try: precio = float(df_tar[df_tar['concepto']==concepto]['valor'].values[0])
                    except: pass
                monto = c2.number_input("Monto", value=precio, step=100.0)
                metodo = st.selectbox("Medio", ["Efectivo", "Transferencia", "MercadoPago"])
                
                if st.form_submit_button("Registrar"):
                    row = [int(datetime.now().timestamp()), str(date.today()), int(sel_alu.split(" - ")[0]), sel_alu.split(" - ")[1], monto, concepto, metodo, "", "Pendiente", user]
                    save_row("pagos", row)
                    st.success("Pago registrado (Pendiente)")

    with tb2:
        if rol in ["Administrador", "Contador"]:
            df_p = get_df("pagos")
            if not df_p.empty and "estado" in df_p.columns:
                pend = df_p[df_p['estado'] == "Pendiente"]
                if not pend.empty:
                    st.dataframe(pend[['fecha_pago', 'nombre_socio', 'monto', 'usuario_registro']])
                    pid = st.selectbox("ID a confirmar", pend['id'])
                    if st.button("Confirmar Pago"):
                        confirmar_pago_seguro(pid)
                        st.success("Confirmado")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.info("No hay pagos pendientes.")
        else:
            st.error("Acceso restringido.")

# === CONFIGURAR TARIFAS ===
elif nav == "Configurar Tarifas":
    st.title("⚙️ Tarifas")
    df = get_df("tarifas")
    if df.empty: df = pd.DataFrame({"concepto": ["Cuota"], "valor": [15000]})
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if st.button("Guardar Cambios"):
        actualizar_tarifas_bulk(edited)
        st.success("Guardado")
