import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import plotly.express as px
import time

# --- 1. CONFIGURACIÓN GLOBAL Y ESTILOS ---
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
        .audit-log {
            font-size: 0.8rem;
            color: #666;
            border-top: 1px solid #eee;
            padding-top: 5px;
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
        st.error(f"❌ Error crítico de conexión: {e}")
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
    ws = get_client().worksheet(sheet_name)
    try:
        cell = ws.find(str(id_row))
        ws.update_cell(cell.row, col_idx, value)
        return True
    except:
        return False

def confirmar_pago_seguro(id_pago):
    # Asumiendo columna 9 es 'estado'
    return update_cell_logic("pagos", id_pago, 9, "Confirmado")

def actualizar_tarifas_bulk(df_edited):
    ws = get_client().worksheet("tarifas")
    ws.clear()
    ws.update([df_edited.columns.values.tolist()] + df_edited.values.tolist())

def calcular_edad(fecha_nac):
    hoy = date.today()
    return hoy.year - fecha_nac.year - ((hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day))

# --- 3. SEGURIDAD (LOGIN) ---
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None})

def login():
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
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
                    st.error("Acceso denegado")

if not st.session_state["auth"]:
    login()
    st.stop()

# --- 4. UI PRINCIPAL ---
user, rol = st.session_state["user"], st.session_state["rol"]

with st.sidebar:
    try:
        st.image("logo.png", use_container_width=True)
    except:
        st.header("🛡️ AREA ARQUEROS")
    
    st.info(f"👤 **{user.upper()}**\nRol: {rol}")
    
    menu_opts = ["Dashboard"]
    if rol in ["Administrador", "Profesor"]:
        menu_opts.extend(["Perfil Alumno", "Asistencia", "Nuevo Alumno"])
    if rol in ["Administrador", "Contador"]:
        menu_opts.extend(["Contabilidad", "Configurar Tarifas"])
    
    nav = st.radio("Navegación", menu_opts)
    st.divider()
    if st.button("Cerrar Sesión"):
        st.session_state.update({"auth": False})
        st.rerun()

# --- 5. MÓDULOS FUNCIONALES ---

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

# === PERFIL 360 ===
elif nav == "Perfil Alumno":
    st.title("👤 Perfil 360°")
    df = get_df("socios")
    if not df.empty:
        df['label'] = df['id'].astype(str) + " | " + df['nombre'] + " " + df['apellido']
        sel = st.selectbox("Buscar Alumno:", df['label'])
        
        if sel:
            uid = int(sel.split(" | ")[0])
            p = df[df['id'] == uid].iloc[0]
            
            # Cálculo de edad al vuelo
            try:
                f_nac = datetime.strptime(p['fecha_nacimiento'], '%Y-%m-%d').date()
                edad_actual = calcular_edad(f_nac)
            except:
                edad_actual = "?"

            h1, h2 = st.columns([1, 4])
            with h1: st.markdown("# 👤")
            with h2:
                st.markdown(f"## {p['nombre']} {p['apellido']}")
                st.caption(f"ID: {uid} | DNI: {p['dni']} | Edad: {edad_actual} años")
                st.success(f"**Plan:** {p['plan']} | **Sede:** {p['sede']} | **Grupo:** {p.get('grupo','-')}")

            t1, t2, t3 = st.tabs(["📝 Ficha Médica & Datos", "📈 Rendimiento", "📞 Contacto"])
            
            with t1:
                c_bio1, c_bio2 = st.columns(2)
                c_bio1.write(f"**Peso:** {p.get('peso', '-')} kg")
                c_bio2.write(f"**Altura:** {p.get('altura', '-')} cm")
                st.markdown("---")
                st.write(f"**Tutor/Responsable:** {p.get('tutor', '-')}")
                
                prev_notes = p.get('notas', '')
                new_notes = st.text_area("Notas Internas / Médicas:", prev_notes)
                if new_notes != prev_notes and st.button("Actualizar Nota"):
                    update_cell_logic("socios", uid, 12, new_notes)
                    st.success("Nota guardada")
            
            with t2:
                df_asist = get_df("asistencias")
                if not df_asist.empty:
                    my_asist = df_asist[df_asist['id_socio'] == uid]
                    st.metric("Total Asistencias", len(my_asist))
                    st.dataframe(my_asist[['fecha', 'sede']].tail(5), use_container_width=True)
            
            with t3:
                st.write(f"📧 {p.get('email', '-')}")
                st.write(f"📱 {p.get('whatsapp', '-')}")

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
                # Precio sugerido
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
        st.subheader("Confirmación de Pagos")
        if rol in ["Administrador", "Contador"]:
            df_p = get_df("pagos")
            if not df_p.empty and "estado" in df_p.columns:
                pend = df_p[df_p['estado'] == "Pendiente"]
                if not pend.empty:
                    st.dataframe(pend[['fecha_pago', 'nombre_socio', 'monto']])
                    pid = st.selectbox("ID a confirmar", pend['id'])
                    if st.button("Confirmar Pago"):
                        confirmar_pago_seguro(pid)
                        st.success("Confirmado")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.info("No hay pagos pendientes.")
            else:
                st.warning("Falta columna 'estado' en hoja pagos.")
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

# === NUEVO ALUMNO (CORREGIDO) ===
elif nav == "Nuevo Alumno":
    st.title("📝 Ficha de Inscripción")
    st.info("Complete todos los campos para generar el legajo digital.")
    
    with st.form("alta"):
        st.subheader("1. Datos Personales")
        c1, c2 = st.columns(2)
        nom = c1.text_input("Nombre")
        ape = c2.text_input("Apellido")
        
        c3, c4 = st.columns(2)
        dni = c3.text_input("DNI")
        # Fecha de nacimiento con rango amplio
        nac = c4.date_input("Fecha de Nacimiento", min_value=date(1980,1,1), max_value=date.today())
        
        # Cálculo visual de edad
        edad_calc = calcular_edad(nac)
        st.caption(f"🎂 Edad calculada: **{edad_calc} años**")
        
        c_fis1, c_fis2 = st.columns(2)
        peso = c_fis1.number_input("Peso (kg) - Opcional", min_value=0.0, format="%.1f")
        altura = c_fis2.number_input("Altura (cm) - Opcional", min_value=0, format="%d")

        st.subheader("2. Datos de Contacto y Responsable")
        tutor = st.text_input("Nombre del Tutor / Responsable (Si es menor)")
        c5, c6 = st.columns(2)
        wsp = c5.text_input("WhatsApp")
        email = c6.text_input("Email")

        st.subheader("3. Datos del Club")
        c7, c8 = st.columns(2)
        sede = c7.selectbox("Sede", ["Sede C1", "Sede Saa"])
        grupo = c8.selectbox("Grupo", ["Inicial", "Intermedio", "Avanzado", "Arqueras", "Sin Grupo"])
        
        df_tar = get_df("tarifas")
        planes = df_tar['concepto'].tolist() if not df_tar.empty else ["General"]
        
        c9, c10 = st.columns(2)
        talle = c9.selectbox("Talle", ["10", "12", "14", "XS", "S", "M", "L", "XL"])
        plan = c10.selectbox("Plan", planes)
        
        st.markdown("---")

        if st.form_submit_button("💾 Crear Legajo Digital"):
            if nom and ape and dni:
                uid = int(datetime.now().timestamp())
                # Estructura FINAL de columnas en Sheets (18 columnas):
                # 1.id, 2.fecha, 3.nom, 4.ape, 5.dni, 6.nac, 7.TUTOR, 8.wsp, 9.email, 10.sede, 11.plan, 12.notas, 13.vendedor, 14.activo, 15.talle, 16.grupo, 17.PESO, 18.ALTURA
                row = [
                    uid, 
                    str(date.today()), 
                    nom, 
                    ape, 
                    dni, 
                    str(nac), 
                    tutor, # Columna 7
                    wsp, 
                    email, # Columna 9
                    sede, 
                    plan, 
                    "", # Notas vacías
                    user, 
                    1, 
                    talle, 
                    grupo,
                    peso,   # Columna 17
                    altura  # Columna 18
                ]
                save_row("socios", row)
                st.success(f"✅ Alumno {nom} {ape} registrado exitosamente.")
                st.balloons()
            else:
                st.error("❌ Nombre, Apellido y DNI son obligatorios.")

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
                if st.form_submit_button("Guardar"):
                    cnt = 0
                    for uid, p in checks.items():
                        if p:
                            n = filtro.loc[filtro['id']==uid, 'nombre'].values[0]
                            a = filtro.loc[filtro['id']==uid, 'apellido'].values[0]
                            row = [str(date.today()), datetime.now().strftime("%H:%M"), uid, f"{n} {a}", sede_sel, grupo_sel, "Presente"]
                            save_row("asistencias", row)
                            cnt+=1
                    st.success(f"{cnt} presentes.")
        else:
            st.warning("Sin alumnos en este grupo.")
