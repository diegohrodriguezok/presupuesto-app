import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, timedelta
import time

# --- 1. CONFIGURACIÓN VISUAL Y ESTILOS ---
st.set_page_config(
    page_title="Sistema de Gestión", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# CSS para forzar modo claro y estilos limpios
st.markdown("""
    <style>
        /* Forzar fondo blanco y texto oscuro */
        .stApp {
            background-color: #ffffff;
            color: #000000;
        }
        [data-testid="stSidebar"] {
            background-color: #f8f9fa;
        }
        h1, h2, h3 {
            color: #1f2c56;
            font-family: 'Helvetica', sans-serif;
        }
        .stMetric {
            background-color: #f0f2f6;
            border: 1px solid #e1e4e8;
            padding: 15px;
            border-radius: 10px;
        }
        /* Botones primarios */
        .stButton>button {
            border-radius: 5px;
            font-weight: bold;
            border: none;
            background-color: #1f2c56;
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
        
        # Mapeo de columnas (A=1, B=2...) basado en tu estructura
        # 3:Nombre, 4:Apellido, 5:DNI, 6:Nacimiento, 10:Sede, 11:Plan, 14:Activo, 15:Talle, 16:Grupo
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
# Grupos definidos para asignar alumnos
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

# SECCIÓN LOGO: Muestra imagen si existe, sino texto
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

# === DASHBOARD (HISTÓRICO Y FLEXIBLE) ===
if seleccion == "Dashboard":
    st.title("📊 Estadísticas Históricas")
    
    # Filtro de Fechas Flexible
    col_d1, col_d2 = st.columns(2)
    fecha_inicio = col_d1.date_input("Desde", date.today().replace(day=1))
    fecha_fin = col_d2.date_input("Hasta", date.today())
    
    df_pagos = get_data("pagos")
    df_gastos = get_data("gastos")
    df_socios = get_data("socios")
    
    # Filtrar DataFrames por fecha
    if not df_pagos.empty:
        df_pagos['fecha_pago'] = pd.to_datetime(df_pagos['fecha_pago'], errors='coerce').dt.date
        pagos_filt = df_pagos[(df_pagos['fecha_pago'] >= fecha_inicio) & (df_pagos['fecha_pago'] <= fecha_fin)]
        ingresos = pd.to_numeric(pagos_filt['monto'], errors='coerce').fillna(0).sum()
    else:
        ingresos = 0
        
    if not df_gastos.empty:
        df_gastos['fecha'] = pd.to_datetime(df_gastos['fecha'], errors='coerce').dt.date
        gastos_filt = df_gastos[(df_gastos['fecha'] >= fecha_inicio) & (df_gastos['fecha'] <= fecha_fin)]
        egresos = pd.to_numeric(gastos_filt['monto'], errors='coerce').fillna(0).sum()
    else:
        egresos = 0
        
    balance = ingresos - egresos
    
    # Mostrar KPIs
    k1, k2, k3 = st.columns(3)
    k1.metric("Ingresos (Período)", f"${ingresos:,.0f}")
    k2.metric("Gastos (Período)", f"${egresos:,.0f}")
    k3.metric("Resultado Neto", f"${balance:,.0f}", delta_color="normal")
    
    st.markdown("---")
    st.subheader("Evolución")
    
    if ingresos > 0 or egresos > 0:
        # Gráfico simple de barras comparativo
        datos_grafico = pd.DataFrame({
            "Tipo": ["Ingresos", "Gastos"],
            "Monto": [ingresos, egresos]
        })
        st.bar_chart(datos_grafico, x="Tipo", y="Monto", color=["#1f2c56", "#cc0000"])
    else:
        st.info("No hay datos en este rango de fechas.")

# === CONTABILIDAD (UNIFICADA) ===
elif seleccion == "Contabilidad":
    st.title("📒 Contabilidad y Caja")
    
    tab1, tab2 = st.tabs(["📥 INGRESOS", "📤 GASTOS"])
    
    # --- PESTAÑA INGRESOS ---
    with tab1:
        st.subheader("Registrar Cobro")
        df_socios = get_data("socios")
        if not df_socios.empty:
            activos = df_socios[df_socios['activo'] == 1]
            lista = activos.apply(lambda x: f"{x['id']} - {x['nombre']} {x['apellido']}", axis=1)
            elegido = st.selectbox("Alumno", lista, key="sel_cobro")
            id_sel = int(elegido.split(" - ")[0])
            
            with st.form("cobro"):
                c1, c2 = st.columns(2)
                monto = c1.number_input("Monto ($)", step=100, min_value=0)
                concepto = c2.selectbox("Concepto", ["Cuota Mensual", "Matrícula", "Indumentaria", "Torneo"])
                metodo = st.selectbox("Medio Pago", ["Efectivo", "Transferencia", "MercadoPago"])
                obs = st.text_input("Observación")
                if st.form_submit_button("✅ Confirmar Ingreso"):
                    row = [int(datetime.now().timestamp()), str(date.today()), id_sel, elegido.split(" - ")[1], monto, concepto, metodo, obs]
                    add_row("pagos", row)
                    st.success("Pago registrado.")
    
    # --- PESTAÑA GASTOS ---
    with tab2:
        st.subheader("Registrar Salida")
        with st.form("gasto"):
            fecha = st.date_input("Fecha", date.today())
            monto = st.number_input("Monto ($)", min_value=0.0)
            cat = st.selectbox("Categoría", ["Alquiler Cancha", "Materiales", "Sueldos", "Impuestos", "Otros"])
            desc = st.text_input("Descripción")
            if st.form_submit_button("🚨 Registrar Gasto"):
                add_row("gastos", [int(datetime.now().timestamp()), str(fecha), monto, cat, desc])
                st.success("Gasto registrado.")

# === NUEVO ALUMNO (CON GRUPO) ===
elif seleccion == "Nuevo Alumno":
    st.title("📝 Alta de Alumno")
    
    with st.form("alta"):
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Nombre")
        apellido = c1.text_input("Apellido")
        
        c3, c4 = st.columns(2)
        dni = c3.text_input("DNI")
        nacimiento = c4.date_input("Nacimiento", min_value=date(2010,1,1))
        
        c5, c6 = st.columns(2)
        sede = c5.selectbox("Sede", SEDES)
        grupo = c6.selectbox("Asignar Grupo", GRUPOS)
        
        c7, c8 = st.columns(2)
        talle = c7.selectbox("Talle", TALLES)
        plan = c8.selectbox("Plan", PLANES)
        
        c9, c10 = st.columns(2)
        wsp = c9.text_input("WhatsApp")
        email = c10.text_input("Email")
        
        if st.form_submit_button("Guardar Ficha"):
            if nombre and apellido and dni:
                new_id = int(datetime.now().timestamp())
                # Orden: id, fecha, nom, ape, dni, nac, tutor, wsp, email, sede, plan, notas, vendedor, activo, talle, grupo
                row = [new_id, str(date.today()), nombre, apellido, dni, str(nacimiento), "", wsp, email, sede, plan, "", st.session_state["user"], 1, talle, grupo]
                add_row("socios", row)
                st.success("✅ Alumno registrado.")
            else:
                st.error("Faltan datos obligatorios.")

# === ASISTENCIA (POR GRUPOS) ===
elif seleccion == "Asistencia":
    st.title("✅ Asistencia por Grupos")
    
    c1, c2 = st.columns(2)
    sede_sel = c1.selectbox("Sede", SEDES)
    grupo_sel = c2.selectbox("Seleccionar Grupo", GRUPOS)
    turno_sel = st.selectbox("Turno Horario", TURNOS)
    
    df = get_data("socios")
    
    if not df.empty:
        # Filtro Doble: Sede + Grupo
        if "grupo" in df.columns:
            filtro = df[(df['sede'] == sede_sel) & (df['activo'] == 1) & (df['grupo'] == grupo_sel)]
        else:
            st.error("⚠️ Falta la columna 'grupo' en Google Sheets.")
            filtro = pd.DataFrame()

        if not filtro.empty:
            st.write(f"Mostrando alumnos de: **{grupo_sel}** en **{sede_sel}**")
            
            with st.form("lista_grupo"):
                cols = st.columns(3)
                checks = {}
                for i, (idx, row) in enumerate(filtro.iterrows()):
                    checks[row['id']] = cols[i%3].checkbox(f"{row['nombre']} {row['apellido']}", key=row['id'])
                
                if st.form_submit_button("💾 Guardar Presentes"):
                    cnt = 0
                    for uid, present in checks.items():
                        if present:
                            nom = filtro.loc[filtro['id']==uid, 'nombre'].values[0]
                            ape = filtro.loc[filtro['id']==uid, 'apellido'].values[0]
                            add_row("asistencias", [str(date.today()), datetime.now().strftime("%H:%M"), uid, f"{nom} {ape}", sede_sel, turno_sel, "Presente"])
                            cnt += 1
                    st.success(f"✅ Asistencia guardada para {cnt} alumnos.")
        else:
            st.info("No se encontraron alumnos en este Grupo y Sede.")

# === GESTIÓN ALUMNOS (EDICIÓN ADMIN) ===
elif seleccion == "Gestión Alumnos":
    st.title("👥 Directorio de Alumnos")
    
    df = get_data("socios")
    if not df.empty:
        st.dataframe(df[['nombre', 'apellido', 'sede', 'grupo', 'activo', 'plan', 'talle']], use_container_width=True)
        
        # Solo el ADMIN puede editar
        if rol == "Administrador":
            st.markdown("---")
            st.subheader("🛠️ Panel de Edición (Exclusivo Admin)")
            
            opciones = df.apply(lambda x: f"{x['id']} - {x['nombre']} {x['apellido']}", axis=1)
            sel_edit = st.selectbox("Seleccionar Alumno para Editar", opciones)
            
            if sel_edit:
                id_edit = int(sel_edit.split(" - ")[0])
                # Recuperar datos actuales del alumno
                alumno_actual = df[df['id'] == id_edit].iloc[0]
                
                with st.form("edit_full"):
                    st.caption(f"Editando ID: {id_edit} (No modificable)")
                    e1, e2 = st.columns(2)
                    n_nom = e1.text_input("Nombre", value=alumno_actual['nombre'])
                    n_ape = e2.text_input("Apellido", value=alumno_actual['apellido'])
                    
                    e3, e4 = st.columns(2)
                    n_dni = e3.text_input("DNI", value=alumno_actual['dni'])
                    # Manejo seguro de fecha
                    try:
                        fecha_orig = datetime.strptime(str(alumno_actual['fecha_nacimiento']), "%Y-%m-%d").date()
                    except:
                        fecha_orig = date(2010,1,1)
                    n_nac = e4.date_input("Nacimiento", value=fecha_orig)
                    
                    e5, e6, e7 = st.columns(3)
                    n_sede = e5.selectbox("Sede", SEDES, index=SEDES.index(alumno_actual['sede']) if alumno_actual['sede'] in SEDES else 0)
                    n_grupo = e6.selectbox("Grupo", GRUPOS, index=GRUPOS.index(alumno_actual['grupo']) if 'grupo' in alumno_actual and alumno_actual['grupo'] in GRUPOS else 0)
                    n_talle = e7.selectbox("Talle", TALLES, index=TALLES.index(str(alumno_actual['talle'])) if str(alumno_actual['talle']) in TALLES else 0)
                    
                    e8, e9 = st.columns(2)
                    n_plan = e8.selectbox("Plan", PLANES, index=PLANES.index(alumno_actual['frecuencia']) if alumno_actual['frecuencia'] in PLANES else 0)
                    n_activo = e9.selectbox("Estado", [1, 0], format_func=lambda x: "Activo" if x==1 else "Inactivo", index=0 if alumno_actual['activo']==1 else 1)
                    
                    if st.form_submit_button("💾 Guardar Cambios Completos"):
                        datos = {
                            "nombre": n_nom, "apellido": n_ape, "dni": n_dni, 
                            "nacimiento": n_nac, "sede": n_sede, "grupo": n_grupo, 
                            "talle": n_talle, "plan": n_plan, "activo": n_activo
                        }
                        if update_full_socio(id_edit, datos):
                            st.success("Datos actualizados correctamente.")
                            time.sleep(1.5)
                            st.rerun()
        else:
            st.info("🔒 La edición de datos está restringida solo al Administrador.")
