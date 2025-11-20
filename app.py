import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, timedelta
import time

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(
    page_title="Sistema de Gestión", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# CSS ADAPTABLE (Respeta el modo oscuro/claro del usuario)
st.markdown("""
    <style>
        /* Tipografía profesional */
        h1, h2, h3 {
            font-family: 'Helvetica', sans-serif;
        }
        
        /* Métricas con borde sutil que se ve bien en ambos modos */
        .stMetric {
            padding: 15px;
            border-radius: 10px;
            border: 1px solid rgba(128, 128, 128, 0.2);
        }

        /* Botones personalizados (Color corporativo) */
        .stButton>button {
            border-radius: 5px;
            font-weight: bold;
            border: none;
            background-color: #1f2c56; /* Azul oscuro corporativo */
            color: white;
        }
        .stButton>button:hover {
            background-color: #2c3e50;
            color: white;
        }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXIÓN A GOOGLE SHEETS ---
@st.cache_resource
def get_connection():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("BaseDatos_ClubArqueros") 
    except Exception as e:
        st.error(f"❌ Error crítico de conexión: {e}")
        st.stop()

def get_data(sheet_name):
    sh = get_connection()
    try:
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()

def add_row(sheet_name, row_data):
    sh = get_connection()
    worksheet = sh.worksheet(sheet_name)
    worksheet.append_row(row_data)

def update_full_socio(id_socio, datos_actualizados):
    """Función exclusiva de Admin para editar socio completo"""
    sh = get_connection()
    ws = sh.worksheet("socios")
    try:
        cell = ws.find(str(id_socio))
        row_num = cell.row
        
        # Actualiza celdas específicas
        ws.update_cell(row_num, 3, datos_actualizados['nombre'])
        ws.update_cell(row_num, 4, datos_actualizados['apellido'])
        ws.update_cell(row_num, 5, datos_actualizados['dni'])
        ws.update_cell(row_num, 6, str(datos_actualizados['nacimiento']))
        ws.update_cell(row_num, 10, datos_actualizados['sede'])
        ws.update_cell(row_num, 11, datos_actualizados['plan'])
        ws.update_cell(row_num, 14, datos_actualizados['activo'])
        ws.update_cell(row_num, 15, datos_actualizados['talle'])
        ws.update_cell(row_num, 16, datos_actualizados['grupo'])
        return True
    except Exception as e:
        st.error(f"Error al actualizar: {e}")
        return False

# --- 3. CONSTANTES ---
SEDES = ["Sede C1", "Sede Saa"]
TURNOS = ["17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"]
TALLES = ["10", "12", "14", "XS", "S", "M", "L", "XL"]
PLANES = ["1 vez x semana", "2 veces x semana", "3 veces x semana", "Libre"]
GRUPOS = ["Grupo Inicial", "Grupo Intermedio", "Grupo Avanzado", "Grupo Arqueras", "Sin Grupo"]

# --- 4. LOGIN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

def login_screen():
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>🔐 Ingreso</h2>", unsafe_allow_html=True)
        with st.form("login"):
            user = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Entrar")
            
            USERS = {
                "admin": {"pass": "admin2024", "rol": "Administrador"},
                "profe": {"pass": "entrenador", "rol": "Profesor"},
                "conta": {"pass": "finanzas", "rol": "Contador"}
            }
            
            if submit:
                if user in USERS and USERS[user]["pass"] == password:
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = user
                    st.session_state["rol"] = USERS[user]["rol"]
                    st.rerun()
                else:
                    st.error("Datos incorrectos")

def logout():
    st.session_state["logged_in"] = False
    st.rerun()

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()

# --- 5. BARRA LATERAL ---
rol = st.session_state["rol"]
user = st.session_state["user"]

try:
    st.sidebar.image("logo.png", use_container_width=True)
except:
    st.sidebar.markdown("### 🛡️ AREA ARQUEROS")

st.sidebar.caption(f"Usuario: {user.upper()} | Rol: {rol}")
if st.sidebar.button("Salir"):
    logout()
st.sidebar.markdown("---")

menu = ["Dashboard"]
if rol in ["Administrador", "Profesor"]:
    menu.extend(["Asistencia", "Nuevo Alumno", "Gestión Alumnos"])
if rol in ["Administrador", "Contador"]:
    menu.append("Contabilidad")

seleccion = st.sidebar.radio("Menú", menu)

# --- 6. DESARROLLO DE MÓDULOS ---

# === DASHBOARD ===
if seleccion == "Dashboard":
    st.title("📊 Estadísticas")
    
    # Filtro de Fechas
    c1, c2 = st.columns(2)
    fecha_inicio = c1.date_input("Desde", date.today().replace(day=1))
    fecha_fin = c2.date_input("Hasta", date.today())
    
    df_pagos = get_data("pagos")
    df_gastos = get_data("gastos")
    
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

# === CONTABILIDAD ===
elif seleccion == "Contabilidad":
    st.title("📒 Contabilidad")
    tab1, tab2 = st.tabs(["📥 Ingresos", "📤 Gastos"])
    
    with tab1:
        df_socios = get_data("socios")
        if not df_socios.empty:
            activos = df_socios[df_socios['activo'] == 1]
            lista = activos.apply(lambda x: f"{x['id']} - {x['nombre']} {x['apellido']}", axis=1)
            elegido = st.selectbox("Alumno", lista)
            id_sel = int(elegido.split(" - ")[0])
            
            with st.form("cobro"):
                c1, c2 = st.columns(2)
                monto = c1.number_input("Monto", step=100, min_value=0)
                concepto = c2.selectbox("Concepto", ["Cuota Mensual", "Matrícula", "Indumentaria", "Torneo"])
                metodo = st.selectbox("Medio", ["Efectivo", "Transferencia", "MercadoPago"])
                obs = st.text_input("Nota")
                if st.form_submit_button("Registrar Cobro"):
                    row = [int(datetime.now().timestamp()), str(date.today()), id_sel, elegido.split(" - ")[1], monto, concepto, metodo, obs]
                    add_row("pagos", row)
                    st.success("Guardado.")

    with tab2:
        with st.form("gasto"):
            fecha = st.date_input("Fecha", date.today())
            monto = st.number_input("Monto", min_value=0.0)
            cat = st.selectbox("Categoría", ["Alquiler", "Materiales", "Sueldos", "Otros"])
            desc = st.text_input("Detalle")
            if st.form_submit_button("Registrar Gasto"):
                add_row("gastos", [int(datetime.now().timestamp()), str(fecha), monto, cat, desc])
                st.success("Gasto guardado.")

# === NUEVO ALUMNO ===
elif seleccion == "Nuevo Alumno":
    st.title("📝 Alta Alumno")
    with st.form("alta"):
        c1, c2 = st.columns(2)
        nom = c1.text_input("Nombre")
        ape = c2.text_input("Apellido")
        c3, c4 = st.columns(2)
        dni = c3.text_input("DNI")
        nac = c4.date_input("Nacimiento", min_value=date(2010,1,1))
        c5, c6 = st.columns(2)
        sede = c5.selectbox("Sede", SEDES)
        grupo = c6.selectbox("Grupo", GRUPOS)
        c7, c8 = st.columns(2)
        talle = c7.selectbox("Talle", TALLES)
        plan = c8.selectbox("Plan", PLANES)
        wsp = st.text_input("WhatsApp")
        
        if st.form_submit_button("Guardar"):
            if nom and ape and dni:
                uid = int(datetime.now().timestamp())
                # id, fecha, nom, ape, dni, nac, tutor, wsp, email, sede, plan, notas, vendedor, activo, talle, grupo
                row = [uid, str(date.today()), nom, ape, dni, str(nac), "", wsp, "", sede, plan, "", user, 1, talle, grupo]
                add_row("socios", row)
                st.success("Guardado.")

# === ASISTENCIA ===
elif seleccion == "Asistencia":
    st.title("✅ Tomar Lista")
    c1, c2 = st.columns(2)
    sede_sel = c1.selectbox("Sede", SEDES)
    grupo_sel = c2.selectbox("Grupo", GRUPOS)
    turno = st.selectbox("Turno", TURNOS)
    
    df = get_data("socios")
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
                            add_row("asistencias", [str(date.today()), datetime.now().strftime("%H:%M"), uid, f"{n} {a}", sede_sel, turno, "Presente"])
                            cnt+=1
                    st.success(f"{cnt} presentes.")
        else:
            st.info("Sin alumnos en este grupo/sede.")

# === GESTIÓN ===
elif seleccion == "Gestión Alumnos":
    st.title("👥 Alumnos")
    df = get_data("socios")
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
                    n_sede = st.selectbox("Sede", SEDES, index=SEDES.index(curr['sede']) if curr['sede'] in SEDES else 0)
                    n_grupo = st.selectbox("Grupo", GRUPOS, index=GRUPOS.index(curr['grupo']) if curr['grupo'] in GRUPOS else 0)
                    n_act = st.selectbox("Estado", [1,0], index=0 if curr['activo']==1 else 1)
                    # (Agrega el resto de campos si lo necesitas)
                    # Recuperamos los campos que no editamos para no romper la fila:
                    # nac, talle, plan
                    
                    if st.form_submit_button("Guardar Cambios"):
                        # Construimos diccionario completo
                        datos = {
                            "nombre": n_nom, "apellido": n_ape, "dni": n_dni,
                            "nacimiento": curr['fecha_nacimiento'], # Mantenemos original si no se editó
                            "sede": n_sede, "plan": curr['frecuencia'], 
                            "activo": n_act, "talle": curr['talle'], "grupo": n_grupo
                        }
                        update_full_socio(uid, datos)
                        st.success("Actualizado.")
                        time.sleep(1)
                        st.rerun()
