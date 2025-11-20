import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date

# --- 1. CONFIGURACIÓN VISUAL Y ESTILOS ---
st.set_page_config(
    page_title="Sistema de Gestión - Area Arqueros", 
    layout="wide", 
    page_icon="",
    initial_sidebar_state="expanded"
)

# CSS personalizado para dar aspecto profesional
st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1 {color: #1f2c56;}
    h2 {color: #2e4053;}
    .stMetric {
        background-color: #ffffff;
        border: 1px solid #e6e6e6;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    /* Alertas personalizadas */
    .deuda-box {
        padding: 15px;
        background-color: #ffcccc;
        color: #990000;
        border-radius: 5px;
        border-left: 5px solid #cc0000;
        margin-bottom: 10px;
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
        # Abre la hoja de cálculo por su nombre exacto
        return client.open("BaseDatos_ClubArqueros") 
    except Exception as e:
        st.error(f"❌ Error crítico de conexión: {e}")
        st.stop()

def get_data(sheet_name):
    """Lee datos de una hoja y devuelve un DataFrame"""
    sh = get_connection()
    try:
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame() # Retorna vacío si la hoja no existe

def add_row(sheet_name, row_data):
    """Agrega una fila nueva al final de la hoja"""
    sh = get_connection()
    worksheet = sh.worksheet(sheet_name)
    worksheet.append_row(row_data)

# --- 3. SISTEMA DE LOGIN Y SEGURIDAD ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

def login_screen():
    st.markdown("<h1 style='text-align: center;'>🏹 Area Arqueros</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Acceso al Sistema</h3>", unsafe_allow_html=True)
    
    # CREDENCIALES (Usuario : Contraseña)
    # Puedes cambiar las contraseñas aquí
    USERS = {
        "admin": {"pass": "admin2024", "rol": "Administrador"},
        "profe": {"pass": "entrenador", "rol": "Profesor"},
        "conta": {"pass": "finanzas", "rol": "Contador"}
    }
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            user = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("INGRESAR", use_container_width=True)
            
            if submit:
                if user in USERS and USERS[user]["pass"] == password:
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = user
                    st.session_state["rol"] = USERS[user]["rol"]
                    st.rerun()
                else:
                    st.error("❌ Acceso denegado.")

def logout():
    st.session_state["logged_in"] = False
    st.session_state["user"] = None
    st.session_state["rol"] = None
    st.rerun()

# Bloqueo de seguridad: Si no está logueado, muestra login y detiene todo
if not st.session_state["logged_in"]:
    login_screen()
    st.stop()

# --- 4. BARRA LATERAL Y NAVEGACIÓN ---
rol = st.session_state["rol"]
user = st.session_state["user"]

st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2558/2558944.png", width=80) # Icono genérico de arquero
st.sidebar.title(f"Hola, {user.title()}")
st.sidebar.caption(f"Rol: {rol}")

if st.sidebar.button("🔒 Cerrar Sesión"):
    logout()

st.sidebar.markdown("---")

# Definir qué puede ver cada rol
menu_options = ["Inicio / Dashboard"]

if rol in ["Administrador", "Profesor"]:
    menu_options.extend(["Nuevo Socio", "Registrar Asistencia", "Gestión de Socios"])

if rol in ["Administrador", "Contador"]:
    menu_options.extend(["Caja: Ingresos", "Caja: Gastos"])

seleccion = st.sidebar.radio("Ir a:", menu_options)

# Constantes del Negocio
SEDES = ["Sede C1", "Sede Saa"]
TURNOS = ["17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"]
TALLES = ["10", "12", "14", "XS", "S", "M", "L", "XL"]

# --- 5. DESARROLLO DE MÓDULOS ---

# === MÓDULO 1: DASHBOARD ===
if seleccion == "Inicio / Dashboard":
    st.title("📊 Panel de Control")
    
    # Cargar datos
    df_pagos = get_data("pagos")
    df_gastos = get_data("gastos")
    df_socios = get_data("socios")
    
    # Cálculos Financieros
    ingresos = 0
    egresos = 0
    
    if not df_pagos.empty:
        # Convertir a números y sumar (si hay errores, los pone en 0)
        ingresos = pd.to_numeric(df_pagos['monto'], errors='coerce').fillna(0).sum()
        
    if not df_gastos.empty:
        egresos = pd.to_numeric(df_gastos['monto'], errors='coerce').fillna(0).sum()
        
    balance = ingresos - egresos
    
    # Mostrar KPIs
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Ingresos", f"${ingresos:,.0f}", delta="Histórico")
    kpi2.metric("Total Gastos", f"${egresos:,.0f}", delta="-Salidas", delta_color="inverse")
    kpi3.metric("Flujo de Caja (Ganancia)", f"${balance:,.0f}", delta_color="normal" if balance > 0 else "inverse")
    
    st.markdown("---")
    
    # ALERTA DE DEUDORES
    st.subheader("🔔 Estado de Cuotas del Mes")
    
    hoy = date.today()
    
    # Lógica: Solo avisar si es después del día 10
    if hoy.day >= 10:
        if not df_socios.empty and not df_pagos.empty:
            # 1. Buscamos pagos de ESTE mes y año que sean "Cuota"
            df_pagos['fecha_pago'] = pd.to_datetime(df_pagos['fecha_pago'], errors='coerce')
            pagos_este_mes = df_pagos[
                (df_pagos['fecha_pago'].dt.month == hoy.month) & 
                (df_pagos['fecha_pago'].dt.year == hoy.year) & 
                (df_pagos['concepto'].astype(str).str.contains("Cuota", case=False))
            ]
            
            ids_pagaron = pagos_este_mes['id_socio'].unique()
            
            # 2. Filtramos socios Activos que NO estén en la lista de pagos
            deudores = df_socios[
                (df_socios['activo'] == 1) & 
                (~df_socios['id'].isin(ids_pagaron))
            ]
            
            if not deudores.empty:
                st.markdown(f"""
                <div class="deuda-box">
                    <strong>⚠️ ALERTA DE DEUDA:</strong> Pasado el día 10, hay <strong>{len(deudores)} alumnos</strong> que no han registrado el pago de la cuota.
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("Ver Lista de Deudores"):
                    st.dataframe(deudores[['nombre', 'apellido', 'sede', 'whatsapp']], use_container_width=True)
            else:
                st.success("✅ ¡Excelente! Todos los alumnos activos están al día.")
    else:
        st.info(f"ℹ️ Las alertas de morosidad se activarán automáticamente el día 10. Hoy es {hoy.day}.")

# === MÓDULO 2: NUEVO SOCIO ===
elif seleccion == "Nuevo Socio":
    st.title("📝 Alta de Alumno")
    
    with st.form("alta_form"):
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Nombre")
        apellido = c1.text_input("Apellido")
        dni = c1.text_input("DNI (Sin puntos)")
        
        # Fecha nacimiento: Limitada desde 2010
        nacimiento = c2.date_input("Fecha de Nacimiento", min_value=date(2010, 1, 1), max_value=date.today())
        
        c3, c4 = st.columns(2)
        sede = c3.selectbox("Sede de Entrenamiento", SEDES)
        talle = c4.selectbox("Talle de Camiseta", TALLES)
        
        c5, c6 = st.columns(2)
        whatsapp = c5.text_input("WhatsApp de Contacto")
        email = c6.text_input("Email")
        
        if st.form_submit_button("Guardar Ficha"):
            if nombre and apellido:
                new_id = int(datetime.now().timestamp())
                # Orden exacto para Google Sheets (incluyendo el nuevo campo TALLE al final)
                # id, fecha_alta, nombre, apellido, dni, nac, tutor, wsp, email, sede, plan, notas, vendedor, activo, talle
                row = [
                    new_id, str(date.today()), nombre, apellido, dni, str(nacimiento), 
                    "", whatsapp, email, sede, "", "", st.session_state["user"], 1, talle
                ]
                add_row("socios", row)
                st.success(f"✅ Alumno {nombre} {apellido} cargado correctamente.")
            else:
                st.error("Falta el nombre o apellido.")

# === MÓDULO 3: CAJA INGRESOS ===
elif seleccion == "Caja: Ingresos":
    st.title("💰 Registrar Cobro")
    
    df_socios = get_data("socios")
    if not df_socios.empty:
        # Crear lista para buscador
        df_socios['display'] = df_socios['id'].astype(str) + " - " + df_socios['nombre'] + " " + df_socios['apellido']
        lista_alumnos = df_socios['display'].tolist()
        
        elegido = st.selectbox("Buscar Alumno", lista_alumnos)
        
        # Extraer datos del seleccionado
        id_sel = int(elegido.split(" - ")[0])
        nombre_sel = elegido.split(" - ")[1]
        
        # Chequeo rápido de deuda
        st.info(f"Registrando cobro para: **{nombre_sel}**")
        
        with st.form("cobro_form"):
            col1, col2 = st.columns(2)
            monto = col1.number_input("Monto Recibido ($)", step=100)
            concepto = col2.selectbox("Concepto", ["Cuota Mensual", "Matrícula", "Indumentaria", "Torneo", "Otro"])
            
            metodo = st.selectbox("Forma de Pago", ["Efectivo", "Transferencia", "MercadoPago"])
            nota = st.text_input("Observación (Opcional)")
            
            if st.form_submit_button("Confirmar Ingreso"):
                # id, fecha, id_socio, nombre, monto, concepto, metodo, comentario
                row = [int(datetime.now().timestamp()), str(date.today()), id_sel, nombre_sel, monto, concepto, metodo, nota]
                add_row("pagos", row)
                st.balloons()
                st.success("✅ Pago registrado con éxito.")

# === MÓDULO 4: CAJA GASTOS ===
elif seleccion == "Caja: Gastos":
    st.title("💸 Registrar Gasto (Salida)")
    st.warning("⚠️ Esta acción descontará dinero de la caja.")
    
    with st.form("gasto_form"):
        fecha = st.date_input("Fecha del Gasto", date.today())
        monto = st.number_input("Monto ($)", min_value=0.0)
        categoria = st.selectbox("Categoría", ["Alquiler Cancha", "Material Deportivo", "Sueldos", "Mantenimiento", "Publicidad", "Impuestos", "Otros"])
        detalle = st.text_input("Detalle (Ej: Compra de 10 conos)")
        
        if st.form_submit_button("Registrar Salida"):
            # id, fecha, monto, categoria, comentario
            row = [int(datetime.now().timestamp()), str(fecha), monto, categoria, detalle]
            add_row("gastos", row)
            st.success("✅ Gasto registrado.")
            
    # Historial breve
    st.markdown("### Últimos 5 Gastos")
    df_gastos = get_data("gastos")
    if not df_gastos.empty:
        st.dataframe(df_gastos.tail(5), use_container_width=True)

# === MÓDULO 5: ASISTENCIA ===
elif seleccion == "Registrar Asistencia":
    st.title("✅ Control de Asistencia")
    
    c1, c2 = st.columns(2)
    sede = c1.selectbox("Sede", SEDES)
    turno = c2.selectbox("Turno", TURNOS)
    
    df_socios = get_data("socios")
    
    if not df_socios.empty:
        # Filtrar por sede
        socios_sede = df_socios[df_socios['sede'] == sede]
        
        if not socios_sede.empty:
            st.write(f"Alumnos en **{sede}**:")
            
            with st.form("asist_form"):
                # Crear checkboxes dinámicos
                estados = {}
                # Usamos columnas para que no sea una lista eterna hacia abajo
                cols = st.columns(3)
                for i, (index, row) in enumerate(socios_sede.iterrows()):
                    columna_actual = cols[i % 3]
                    estados[row['id']] = columna_actual.checkbox(f"{row['nombre']} {row['apellido']}", key=row['id'])
                
                if st.form_submit_button("Guardar Asistencia"):
                    contador = 0
                    for uid, presente in estados.items():
                        if presente:
                            nom = socios_sede.loc[socios_sede['id'] == uid, 'nombre'].values[0]
                            ape = socios_sede.loc[socios_sede['id'] == uid, 'apellido'].values[0]
                            # fecha, hora, id, nombre, sede, turno, estado
                            row = [str(date.today()), datetime.now().strftime("%H:%M"), uid, f"{nom} {ape}", sede, turno, "Presente"]
                            add_row("asistencias", row)
                            contador += 1
                    
                    st.success(f"✅ Se guardaron {contador} presentes.")
        else:
            st.warning("No hay alumnos registrados en esta sede.")

# === MÓDULO 6: GESTIÓN SOCIOS ===
elif seleccion == "Gestión de Socios":
    st.title("👥 Base de Datos")
    
    df = get_data("socios")
    if not df.empty:
        busqueda = st.text_input("🔍 Buscar por Nombre, Apellido o DNI")
        
        if busqueda:
            # Filtro insensible a mayúsculas
            mask = df.astype(str).apply(lambda x: x.str.contains(busqueda, case=False)).any(axis=1)
            df_filtrado = df[mask]
            st.dataframe(df_filtrado)
        else:
            st.dataframe(df)

