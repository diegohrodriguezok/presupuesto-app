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
        }
        .stButton>button:hover {
            background-color: #2c3e50;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.6rem !important;
            font-weight: 700;
            color: #1f2c56;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            background-color: transparent;
            padding-bottom: 10px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 45px;
            white-space: pre-wrap;
            background-color: #ffffff;
            color: #555555;
            border-radius: 10px;
            border: 1px solid #e0e0e0;
            padding: 0 20px;
            font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
            background-color: #1f2c56 !important;
            color: #ffffff !important;
            border: none;
            box-shadow: 0 4px 6px rgba(31, 44, 86, 0.25);
        }
    </style>
    """, unsafe_allow_html=True)

# --- 2. LÓGICA DE NEGOCIO ---

CATEGORIAS = ["Infantil", "Prejuvenil", "Juvenil", "Adulto", "Senior"]
NIVELES = ["Nivel 1", "Nivel 2"]

CONFIG_SEDES = {
    "Sede C1": {
        "17:00": CATEGORIAS,
        "18:00": CATEGORIAS,
        "19:00": CATEGORIAS
    },
    "Sede Saa": {
        "18:00": ["Infantil", "Prejuvenil", "Juvenil"],
        "19:00": ["Juvenil", "Adulto", "Senior"]
    }
}

# --- 3. GESTOR DE CONEXIÓN ---
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

def update_cell_logic(sheet_name, id_row, col_idx, value):
    """Actualiza una celda específica buscando por ID"""
    ws = get_client().worksheet(sheet_name)
    try:
        cell = ws.find(str(id_row))
        ws.update_cell(cell.row, col_idx, value)
        return True
    except:
        return False

def update_full_socio(id_socio, d):
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
        return True
    except Exception as e:
        st.error(f"Error al actualizar: {e}")
        return False

def confirmar_pago_seguro(id_pago):
    return update_cell_logic("pagos", id_pago, 9, "Confirmado")

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

# --- 4. LOGIN ---
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None})

def login():
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        try: st.image("logo.png", width=150)
        except: st.markdown("<h2 style='text-align: center;'>🔐 Area Arqueros</h2>", unsafe_allow_html=True)
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
                    st.error("Acceso denegado")

if not st.session_state["auth"]:
    login()
    st.stop()

# --- 5. UI PRINCIPAL ---
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
    
    nav = st.radio("Navegación", menu_opts)
    st.divider()
    if st.button("Cerrar Sesión"):
        st.session_state.update({"auth": False})
        st.rerun()

# --- 6. MÓDULOS ---

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
                fig2 = px.bar(counts, x=view_mode, y='cantidad', title=f"Total: {len(today_data)}", color_discrete_sequence=['#1f2c56'])
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Sin registros hoy.")

elif nav == "Alumnos":
    st.title("👥 Gestión de Alumnos")
    tab_perfil, tab_nuevo = st.tabs(["📂 Directorio & Perfil", "➕ Nuevo Alumno"])
    
    with tab_perfil:
        df = get_df("socios")
        if not df.empty:
            df['label'] = df['id'].astype(str) + " | " + df['nombre'] + " " + df['apellido']
            sel = st.selectbox("🔍 Buscar Alumno:", df['label'])
            
            if sel:
                uid = int(sel.split(" | ")[0])
                p = df[df['id'] == uid].iloc[0]
                
                try:
                    f_nac_str = str(p.get('fecha_nacimiento', ''))
                    f_nac = datetime.strptime(f_nac_str, '%Y-%m-%d').date()
                    edad = calcular_edad(f_nac)
                except: edad = "?"
                
                h1, h2 = st.columns([1, 4])
                with h1: st.markdown("# 👤")
                with h2:
                    st.markdown(f"## {p['nombre']} {p['apellido']}")
                    tags = f"**Sede:** {p['sede']} | **Grupo:** {p.get('grupo','-')} | **Plan Actual:** {p.get('plan','-')}"
                    if p.get('activo', 0) == 1: st.success(tags)
                    else: st.error(f"BAJA - {tags}")

                sub_t1, sub_t2 = st.tabs(["📋 Ficha Completa", "📈 Historial"])
                
                with sub_t1:
                    if rol == "Administrador":
                        with st.form("edit_full"):
                            st.subheader("Datos Personales")
                            e1, e2 = st.columns(2)
                            n_nom = e1.text_input("Nombre", p['nombre'])
                            n_ape = e2.text_input("Apellido", p['apellido'])
                            
                            e3, e4 = st.columns(2)
                            n_dni = e3.text_input("DNI", p['dni'])
                            f_origen = f_nac if isinstance(f_nac, date) else date(2000,1,1)
                            n_nac = e4.date_input("Nacimiento", f_origen)
                            
                            st.subheader("Clasificación Deportiva")
                            grupo_actual_str = p.get('grupo', 'Sin Asignar')
                            cat_actual, niv_actual = "Infantil", "Nivel 1"
                            if " - " in grupo_actual_str:
                                parts = grupo_actual_str.split(" - ")
                                if parts[0] in CATEGORIAS: cat_actual = parts[0]
                                if len(parts)>1 and parts[1] in NIVELES: niv_actual = parts[1]

                            e5, e6, e7 = st.columns(3)
                            n_sede = e5.selectbox("Sede", list(CONFIG_SEDES.keys()), index=list(CONFIG_SEDES.keys()).index(p['sede']) if p['sede'] in CONFIG_SEDES else 0)
                            n_cat = e6.selectbox("Categoría", CATEGORIAS, index=CATEGORIAS.index(cat_actual) if cat_actual in CATEGORIAS else 0)
                            n_niv = e7.selectbox("Nivel", NIVELES, index=NIVELES.index(niv_actual) if niv_actual in NIVELES else 0)
                            
                            st.subheader("Datos Físicos & Contacto")
                            c_f1, c_f2, c_f3 = st.columns(3)
                            n_peso = c_f1.number_input("Peso", value=float(p.get('peso', 0) or 0))
                            n_alt = c_f2.number_input("Altura", value=int(p.get('altura', 0) or 0))
                            n_talle = c_f3.text_input("Talle", p.get('talle', ''))
                            
                            c_c1, c_c2, c_c3 = st.columns(3)
                            n_tutor = c_c1.text_input("Tutor", p.get('tutor', ''))
                            n_wsp = c_c2.text_input("WhatsApp", p.get('whatsapp', ''))
                            n_email = c_c3.text_input("Email", p.get('email', ''))

                            # SECCIÓN PLANES (SINCRONIZADA)
                            df_tar = get_df("tarifas")
                            planes_list = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
                            
                            # Pre-seleccionar el plan que tiene en su ficha (actualizado por pagos)
                            curr_plan_idx = 0
                            if p.get('plan') in planes_list:
                                curr_plan_idx = planes_list.index(p['plan'])
                                
                            n_plan = st.selectbox("Plan (Actualiza en Próximo Pago)", planes_list, index=curr_plan_idx)
                            
                            n_notas = st.text_area("Notas Internas", p.get('notas', ''))
                            n_activo = st.checkbox("Alumno Activo", value=True if p.get('activo', 0)==1 else False)

                            if st.form_submit_button("💾 Guardar Cambios"):
                                grupo_final = f"{n_cat} - {n_niv}"
                                d_upd = {
                                    'nombre': n_nom, 'apellido': n_ape, 'dni': n_dni,
                                    'nacimiento': n_nac, 'tutor': n_tutor, 'whatsapp': n_wsp,
                                    'email': n_email, 'sede': n_sede, 'peso': n_peso, 'altura': n_alt,
                                    'talle': n_talle, 'plan': n_plan, 
                                    'grupo': grupo_final,
                                    'notas': n_notas, 'activo': 1 if n_activo else 0
                                }
                                if update_full_socio(uid, d_upd):
                                    st.success(f"Actualizado: {n_nom} | Plan: {n_plan}")
                                    time.sleep(1)
                                    st.rerun()
                    else:
                        st.info("Modo Lectura")
                        st.write(f"Plan Actual: {p.get('plan','-')}")
                
                with sub_t2:
                    df_asist = get_df("asistencias")
                    if not df_asist.empty:
                        mias = df_asist[df_asist['id_socio'] == uid]
                        st.dataframe(mias[['fecha', 'sede', 'turno']].tail(10), use_container_width=True)

    with tab_nuevo:
        st.subheader("📝 Alta de Nuevo Alumno")
        with st.form("alta_full"):
            st.markdown("##### 1. Datos Deportivos (Clasificación)")
            c1, c2, c3 = st.columns(3)
            n_sede = c1.selectbox("Sede", list(CONFIG_SEDES.keys()))
            n_cat = c2.selectbox("Categoría", CATEGORIAS)
            n_niv = c3.selectbox("Nivel", NIVELES)
            
            st.markdown("##### 2. Datos Personales")
            c_p1, c_p2 = st.columns(2)
            nom = c_p1.text_input("Nombre")
            ape = c_p2.text_input("Apellido")
            dni = st.text_input("DNI")
            nac = st.date_input("Fecha Nacimiento", min_value=date(1980,1,1))
            
            c_f1, c_f2 = st.columns(2)
            peso = c_f1.number_input("Peso (kg)", min_value=0.0)
            altura = c_f2.number_input("Altura (cm)", min_value=0)
            
            st.markdown("##### 3. Contacto")
            tutor = st.text_input("Tutor / Responsable")
            c_c1, c_c2 = st.columns(2)
            wsp = c_c1.text_input("WhatsApp")
            email = c_c2.text_input("Email")
            
            c_ex1, c_ex2 = st.columns(2)
            plan = c_ex1.selectbox("Plan Facturación", get_df("tarifas")['concepto'].tolist() if not get_df("tarifas").empty else ["General"])
            talle = c_ex2.selectbox("Talle", ["10", "12", "14", "XS", "S", "M", "L", "XL"])
            
            if st.form_submit_button("💾 Crear Legajo"):
                if nom and ape and dni:
                    uid = int(datetime.now().timestamp())
                    grupo_final = f"{n_cat} - {n_niv}"
                    row = [
                        uid, str(date.today()), nom, ape, dni, str(nac),
                        tutor, wsp, email, n_sede, plan, "", user, 1,
                        talle, grupo_final, peso, altura
                    ]
                    save_row("socios", row)
                    st.success(f"Alumno registrado en {grupo_final} ({n_sede})")
                else:
                    st.error("Datos faltantes.")

elif nav == "Asistencia":
    st.title("✅ Tomar Asistencia Inteligente")
    sede_sel = st.selectbox("📍 Seleccionar Sede", list(CONFIG_SEDES.keys()))
    horarios_disponibles = list(CONFIG_SEDES[sede_sel].keys())
    hora_sel = st.selectbox("🕒 Seleccionar Horario", horarios_disponibles)
    categorias_validas = CONFIG_SEDES[sede_sel][hora_sel]
    cat_sel = st.selectbox("⚽ Seleccionar Categoría", categorias_validas)
    niv_sel = st.selectbox("📶 Seleccionar Nivel", NIVELES)
    
    df = get_df("socios")
    if not df.empty and 'grupo' in df.columns:
        grupo_objetivo = f"{cat_sel} - {niv_sel}"
        filtro = df[(df['sede'] == sede_sel) & (df['activo'] == 1) & (df['grupo'] == grupo_objetivo)]
        
        st.markdown("---")
        st.subheader(f"Lista: {grupo_objetivo}")
        
        if not filtro.empty:
            with st.form("lista_asist"):
                cols = st.columns(3)
                checks = {}
                for i, (idx, r) in enumerate(filtro.iterrows()):
                    checks[r['id']] = cols[i%3].checkbox(f"{r['nombre']} {r['apellido']}", key=r['id'])
                
                if st.form_submit_button("💾 Guardar Presentes"):
                    cnt = 0
                    for uid, p in checks.items():
                        if p:
                            n = filtro.loc[filtro['id']==uid, 'nombre'].values[0]
                            a = filtro.loc[filtro['id']==uid, 'apellido'].values[0]
                            row = [str(date.today()), datetime.now().strftime("%H:%M"), uid, f"{n} {a}", sede_sel, hora_sel, "Presente"]
                            save_row("asistencias", row)
                            cnt+=1
                    st.success(f"✅ {cnt} alumnos presentes guardados.")
        else:
            st.warning(f"No hay alumnos en {grupo_objetivo} (Sede: {sede_sel}).")

elif nav == "Contabilidad":
    st.title("📒 Finanzas")
    df_tar = get_df("tarifas")
    tarifas_opts = df_tar['concepto'].tolist() if not df_tar.empty else []
    
    tb1, tb2 = st.tabs(["💰 Ingresos", "✅ Auditoría"])
    with tb1:
        df_s = get_df("socios")
        if not df_s.empty:
            activos = df_s[df_s['activo']==1]
            lista_s = activos.apply(lambda x: f"{x['id']} - {x['nombre']} {x['apellido']}", axis=1)
            sel_alu = st.selectbox("Seleccionar Alumno", lista_s)
            
            if sel_alu:
                id_pay = int(sel_alu.split(" - ")[0])
                
                # 1. LÓGICA INTELIGENTE: Obtener el plan actual del alumno desde la base
                alumno_data = activos[activos['id'] == id_pay].iloc[0]
                plan_actual_alumno = alumno_data.get('plan', '')
                
                # Pre-seleccionar el índice del plan en el dropdown
                idx_concepto = 0
                if plan_actual_alumno in tarifas_opts:
                    idx_concepto = tarifas_opts.index(plan_actual_alumno)
                
                with st.form("cobro"):
                    c1, c2 = st.columns(2)
                    # El selectbox arranca por defecto en el plan del alumno
                    concepto = c1.selectbox("Concepto", tarifas_opts + ["Otro"], index=idx_concepto)
                    
                    precio = 0.0
                    if not df_tar.empty and concepto in tarifas_opts:
                        try: precio = float(df_tar[df_tar['concepto']==concepto]['valor'].values[0])
                        except: pass
                    monto = c2.number_input("Monto", value=precio, step=100.0)
                    metodo = st.selectbox("Medio", ["Efectivo", "Transferencia", "MercadoPago"])
                    
                    if st.form_submit_button("Registrar"):
                        # 2. LÓGICA DE ACTUALIZACIÓN: Si paga un plan, se actualiza su perfil
                        if concepto in tarifas_opts and concepto != "Otro":
                            update_cell_logic("socios", id_pay, 11, concepto) # Col 11 es 'plan'
                            
                        row = [int(datetime.now().timestamp()), str(date.today()), id_pay, sel_alu.split(" - ")[1], monto, concepto, metodo, "", "Pendiente", user]
                        save_row("pagos", row)
                        st.success(f"Registrado. Perfil actualizado a: {concepto}")

    with tb2:
        if rol in ["Administrador", "Contador"]:
            df_p = get_df("pagos")
            if not df_p.empty and "estado" in df_p.columns:
                pend = df_p[df_p['estado'] == "Pendiente"]
                if not pend.empty:
                    st.dataframe(pend[['fecha_pago', 'nombre_socio', 'monto', 'usuario_registro']])
                    pid = st.selectbox("ID Pago", pend['id'])
                    if st.button("Confirmar"):
                        confirmar_pago_seguro(pid)
                        st.success("Confirmado")
                        time.sleep(1); st.rerun()
                else: st.info("Sin pendientes.")
        else: st.error("Acceso denegado")

elif nav == "Configurar Tarifas":
    st.title("⚙️ Tarifas")
    df = get_df("tarifas")
    if df.empty: df = pd.DataFrame({"concepto": ["Cuota"], "valor": [15000]})
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if st.button("Guardar"):
        actualizar_tarifas_bulk(edited)
        st.success("Guardado")
