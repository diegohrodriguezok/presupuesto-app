import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import time

# --- 1. CONFIGURACIÓN VISUAL Y ESTILOS ---
st.set_page_config(
    page_title="Sistema de Gestión - Area Arqueros", 
    layout="wide", 
    page_icon="🏹",
    initial_sidebar_state="expanded"
)

# CSS Profesional
st.markdown("""
    <style>
    .main {background-color: #f4f6f9;}
    h1 {color: #1f2c56; font-family: 'Helvetica', sans-serif;}
    .stButton>button {
        width: 100%; 
        border-radius: 5px;
        font-weight: bold;
    }
    .success-box {padding: 1rem; background-color: #d4edda; border-radius: 5px; color: #155724; margin-bottom: 10px;}
    .warning-box {padding: 1rem; background-color: #fff3cd; border-radius: 5px; color: #856404; margin-bottom: 10px;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXIÓN ROBUSTA A GOOGLE SHEETS ---
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

# Función optimizada para leer datos (cacheada por 5 segundos para velocidad)
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

def update_socio_status(id_socio, nuevo_estado, nuevo_plan=None, nueva_sede=None):
    """Función avanzada para editar datos de un socio existente"""
    sh = get_connection()
    ws = sh.worksheet("socios")
    
    # Buscar la celda que contiene el ID
    try:
        cell = ws.find(str(id_socio))
        # Activo es la columna 14 (N), Sede es 10 (J), Plan es 11 (K)
        # Nota: gspread usa coordenadas (fila, columna) empezando en 1
        
        # Actualizar Estado (Activo/Inactivo)
        ws.update_cell(cell.row, 14, nuevo_estado) 
        
        if nueva_sede:
             ws.update_cell(cell.row, 10, nueva_sede)
             
        if nuevo_plan:
             ws.update_cell(cell.row, 11, nuevo_plan)
             
        return True
    except Exception as e:
        st.error(f"Error al actualizar: {e}")
        return False

# --- 3. CONSTANTES DEL NEGOCIO (Fácil de editar) ---
SEDES = ["Sede C1", "Sede Saa"]
TURNOS = ["17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"]
TALLES = ["10", "12", "14", "XS", "S", "M", "L", "XL"]
PLANES = ["1 vez x semana", "2 veces x semana", "3 veces x semana", "Libre"]

# --- 4. SISTEMA DE LOGIN ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

def login_screen():
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🏹 Acceso</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            user = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Entrar")
            
            # CREDENCIALES
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
    st.session_state["user"] = None
    st.session_state["rol"] = None
    st.rerun()

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()

# --- 5. BARRA LATERAL ---
rol = st.session_state["rol"]
user = st.session_state["user"]

st.sidebar.title(f"👤 {user.upper()}")
st.sidebar.markdown(f"**Rol:** {rol}")
if st.sidebar.button("Cerrar Sesión"):
    logout()
st.sidebar.markdown("---")

menu_options = ["Dashboard"]
if rol in ["Administrador", "Profesor"]:
    menu_options.extend(["Nuevo Socio", "Registrar Asistencia", "Gestión de Socios"])
if rol in ["Administrador", "Contador"]:
    menu_options.extend(["Caja: Ingresos", "Caja: Gastos"])

seleccion = st.sidebar.radio("Navegación", menu_options)

# --- 6. MÓDULOS ---

# === DASHBOARD ===
if seleccion == "Dashboard":
    st.title("📊 Tablero de Control")
    
    df_pagos = get_data("pagos")
    df_gastos = get_data("gastos")
    df_socios = get_data("socios")
    
    # Cálculos
    ingresos = pd.to_numeric(df_pagos['monto'], errors='coerce').fillna(0).sum() if not df_pagos.empty else 0
    egresos = pd.to_numeric(df_gastos['monto'], errors='coerce').fillna(0).sum() if not df_gastos.empty else 0
    balance = ingresos - egresos
    
    activos = len(df_socios[df_socios['activo'] == 1]) if not df_socios.empty else 0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alumnos Activos", activos)
    c2.metric("Ingresos", f"${ingresos:,.0f}")
    c3.metric("Gastos", f"${egresos:,.0f}")
    c4.metric("Caja Actual", f"${balance:,.0f}", delta_color="normal")

    st.markdown("---")
    
    # Alerta de Deudores Inteligente
    if date.today().day >= 10:
        st.subheader("⚠️ Alumnos pendientes de pago (Mes Actual)")
        if not df_socios.empty and not df_pagos.empty:
            # Filtros
            df_pagos['fecha_pago'] = pd.to_datetime(df_pagos['fecha_pago'], errors='coerce')
            pagos_mes = df_pagos[
                (df_pagos['fecha_pago'].dt.month == date.today().month) & 
                (df_pagos['fecha_pago'].dt.year == date.today().year) & 
                (df_pagos['concepto'].astype(str).str.contains("Cuota", case=False))
            ]
            pagaron = pagos_mes['id_socio'].unique()
            # Socios Activos que NO pagaron
            deudores = df_socios[(df_socios['activo'] == 1) & (~df_socios['id'].isin(pagaron))]
            
            if not deudores.empty:
                st.dataframe(deudores[['nombre', 'apellido', 'sede', 'whatsapp']], use_container_width=True)
            else:
                st.success("Todos al día 🎉")
    else:
        st.info(f"Las alertas de deuda se activan el día 10. (Faltan {10 - date.today().day} días)")

# === NUEVO SOCIO (CON VALIDACIÓN DE DUPLICADOS) ===
elif seleccion == "Nuevo Socio":
    st.title("📝 Alta de Alumno")
    
    # Cargar socios existentes para verificar duplicados
    df_existentes = get_data("socios")
    lista_dnis = df_existentes['dni'].astype(str).tolist() if not df_existentes.empty else []

    with st.form("alta"):
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Nombre")
        apellido = c1.text_input("Apellido")
        dni = c1.text_input("DNI (Sin puntos)")
        
        c3, c4 = st.columns(2)
        nacimiento = c3.date_input("Nacimiento", min_value=date(2010,1,1), max_value=date.today())
        sede = c4.selectbox("Sede", SEDES)
        
        c5, c6 = st.columns(2)
        talle = c5.selectbox("Talle", TALLES)
        plan = c6.selectbox("Plan Entrenamiento", PLANES)
        
        c7, c8 = st.columns(2)
        wsp = c7.text_input("WhatsApp")
        email = c8.text_input("Email")
        
        if st.form_submit_button("Guardar Ficha"):
            # 1. VALIDACIÓN: Campos obligatorios
            if not nombre or not apellido or not dni:
                st.error("❌ Nombre, Apellido y DNI son obligatorios.")
            # 2. VALIDACIÓN: Duplicados
            elif dni in lista_dnis:
                st.error(f"❌ ERROR: El DNI {dni} ya está registrado en el sistema.")
            else:
                # Si pasa las validaciones, guardamos
                new_id = int(datetime.now().timestamp())
                # Orden Columnas: id, fecha, nombre, apellido, dni, nac, tutor, wsp, email, sede, plan, notas, vendedor, activo, talle
                row = [new_id, str(date.today()), nombre, apellido, dni, str(nacimiento), "", wsp, email, sede, plan, "", st.session_state["user"], 1, talle]
                add_row("socios", row)
                st.success("✅ Alumno registrado correctamente.")
                time.sleep(1) # Pausa para que se vea el mensaje
                st.rerun()

# === GESTIÓN DE SOCIOS (EDICIÓN Y BAJA) ===
elif seleccion == "Gestión de Socios":
    st.title("👥 Directorio y Edición")
    
    df = get_data("socios")
    if not df.empty:
        # Buscador
        texto = st.text_input("🔍 Buscar Alumno")
        if texto:
            mask = df.astype(str).apply(lambda x: x.str.contains(texto, case=False)).any(axis=1)
            df = df[mask]
        
        st.dataframe(df[['id', 'nombre', 'apellido', 'sede', 'activo', 'plan', 'dni']], use_container_width=True)
        
        st.markdown("---")
        st.subheader("✏️ Editar / Dar de Baja")
        
        # Selector de alumno para editar
        lista_opciones = df.apply(lambda x: f"{x['id']} - {x['nombre']} {x['apellido']} ({'Activo' if x['activo']==1 else 'Inactivo'})", axis=1)
        seleccionado = st.selectbox("Seleccionar Alumno para modificar:", lista_opciones)
        
        if seleccionado:
            id_edit = int(seleccionado.split(" - ")[0])
            
            # Formulario de edición
            with st.form("form_edicion"):
                c1, c2, c3 = st.columns(3)
                
                # Obtener estado actual (aproximado)
                nuevo_estado = c1.selectbox("Estado", [1, 0], format_func=lambda x: "✅ Activo" if x==1 else "❌ Inactivo (Baja)")
                nueva_sede = c2.selectbox("Cambiar Sede", SEDES)
                nuevo_plan = c3.selectbox("Cambiar Plan", PLANES)
                
                if st.form_submit_button("Aplicar Cambios"):
                    exito = update_socio_status(id_edit, nuevo_estado, nuevo_plan, nueva_sede)
                    if exito:
                        st.success("Cambios aplicados en la nube. Recargando...")
                        time.sleep(2)
                        st.rerun()
    else:
        st.info("No hay socios cargados.")

# === CAJA INGRESOS ===
elif seleccion == "Caja: Ingresos":
    st.title("💰 Registrar Cobro")
    df_socios = get_data("socios")
    
    if not df_socios.empty:
        # Solo mostramos activos para cobrar
        activos = df_socios[df_socios['activo'] == 1]
        lista = activos.apply(lambda x: f"{x['id']} - {x['nombre']} {x['apellido']}", axis=1)
        
        elegido = st.selectbox("Alumno", lista)
        id_sel = int(elegido.split(" - ")[0])
        
        with st.form("cobro"):
            c1, c2 = st.columns(2)
            monto = c1.number_input("Monto ($)", step=100, min_value=0)
            concepto = c2.selectbox("Concepto", ["Cuota Mensual", "Matrícula", "Indumentaria", "Torneo"])
            metodo = st.selectbox("Medio Pago", ["Efectivo", "Transferencia", "MercadoPago"])
            obs = st.text_input("Observación")
            
            if st.form_submit_button("Registrar"):
                row = [int(datetime.now().timestamp()), str(date.today()), id_sel, elegido.split(" - ")[1], monto, concepto, metodo, obs]
                add_row("pagos", row)
                st.success("Pago guardado.")

# === CAJA GASTOS ===
elif seleccion == "Caja: Gastos":
    st.title("💸 Registrar Salida")
    with st.form("gasto"):
        fecha = st.date_input("Fecha", date.today())
        monto = st.number_input("Monto ($)", min_value=0.0)
        cat = st.selectbox("Categoría", ["Alquiler Cancha", "Materiales", "Sueldos", "Impuestos", "Otros"])
        desc = st.text_input("Descripción")
        if st.form_submit_button("Registrar Gasto"):
            add_row("gastos", [int(datetime.now().timestamp()), str(fecha), monto, cat, desc])
            st.success("Gasto registrado.")
            
    st.dataframe(get_data("gastos").tail(5))

# === ASISTENCIA ===
elif seleccion == "Registrar Asistencia":
    st.title("✅ Tomar Lista")
    c1, c2 = st.columns(2)
    sede = c1.selectbox("Sede", SEDES)
    turno = c2.selectbox("Turno", TURNOS)
    
    df = get_data("socios")
    if not df.empty:
        # Solo socios ACTIVOS de esa SEDE
        filtro = df[(df['sede'] == sede) & (df['activo'] == 1)]
        
        if not filtro.empty:
            with st.form("lista"):
                st.write(f"Alumnos Activos en {sede}:")
                cols = st.columns(3)
                checks = {}
                for i, (idx, row) in enumerate(filtro.iterrows()):
                    checks[row['id']] = cols[i%3].checkbox(f"{row['nombre']} {row['apellido']}", key=row['id'])
                
                if st.form_submit_button("Guardar Presentes"):
                    cnt = 0
                    for uid, present in checks.items():
                        if present:
                            # Buscar nombre para guardar en asistencia (ahorra lecturas futuras)
                            nom = filtro.loc[filtro['id']==uid, 'nombre'].values[0]
                            ape = filtro.loc[filtro['id']==uid, 'apellido'].values[0]
                            add_row("asistencias", [str(date.today()), datetime.now().strftime("%H:%M"), uid, f"{nom} {ape}", sede, turno, "Presente"])
                            cnt += 1
                    st.success(f"✅ {cnt} presentes guardados.")
        else:
            st.warning("No hay alumnos activos en esta sede.")
