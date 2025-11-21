import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import plotly.express as px
import time
from fpdf import FPDF
import base64
import pytz # Librería para zona horaria

# --- 1. CONFIGURACIÓN GLOBAL ---
st.set_page_config(
    page_title="Area Arqueros ERP", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="logo.png"
)

# --- FUNCIONES DE TIEMPO ARGENTINA (UTC-3) ---
def get_now_ar():
    """Devuelve la fecha y hora actual en Argentina"""
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    return datetime.now(tz)

def get_today_ar():
    """Devuelve solo la fecha actual en Argentina"""
    return get_now_ar().date()

# --- CSS PREMIUM MEJORADO ---
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
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .stButton>button:hover {
            background-color: #2c3e50;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            transform: translateY(-2px);
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.6rem !important;
            font-weight: 700;
            color: #1f2c56;
        }
        /* Pestañas */
        .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; padding-bottom: 10px; }
        .stTabs [data-baseweb="tab"] {
            height: 45px; background-color: #ffffff; color: #555555;
            border-radius: 8px; border: 1px solid #e0e0e0; padding: 0 20px; font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
            background-color: #1f2c56 !important; color: #ffffff !important;
            border: none; box-shadow: 0 4px 6px rgba(31, 44, 86, 0.25);
        }
        /* Caja Diaria - VISIBILIDAD MEJORADA */
        .caja-box {
            background-color: #e8f5e9; 
            padding: 20px; 
            border-radius: 10px;
            border-left: 6px solid #2e7d32; 
            margin-bottom: 20px;
            color: #1b5e20; /* Texto verde muy oscuro para contraste */
        }
        .caja-box h3 { margin: 0; font-size: 1rem; color: #2e7d32; }
        .caja-box h2 { margin: 5px 0 0 0; font-size: 2rem; font-weight: 800; color: #1b5e20; }
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
    except: return pd.DataFrame()

def save_row(sheet_name, data):
    get_client().worksheet(sheet_name).append_row(data)

def log_action(id_ref, accion, detalle, user):
    try:
        # Usamos hora Argentina para el log
        row = [str(get_now_ar()), user, str(id_ref), accion, detalle]
        save_row("logs", row)
    except: pass

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
                if str(v) != str(original_data.get(k, '')):
                    cambios.append(f"{k}: {v}")
        if cambios: log_action(id_socio, "Edición Perfil", " | ".join(cambios), user_admin)
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False

def confirmar_pago_seguro(id_pago, user):
    ws = get_client().worksheet("pagos")
    try:
        cell = ws.find(str(id_pago))
        ws.update_cell(cell.row, 9, "Confirmado")
        log_action(id_pago, "Confirmar Pago", "Pago Validado", user)
        return True
    except: return False

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

# --- GENERADOR DE PDF (RECIBO) ---
def generar_pdf(datos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Encabezado
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="AREA ARQUEROS - COMPROBANTE DE PAGO", ln=1, align='C')
    pdf.ln(10)
    
    # Datos
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Fecha: {datos['fecha']}", ln=1)
    pdf.cell(200, 10, txt=f"Alumno: {datos['alumno']}", ln=1)
    pdf.cell(200, 10, txt=f"Concepto: {datos['concepto']}", ln=1)
    pdf.cell(200, 10, txt=f"Medio de Pago: {datos['metodo']}", ln=1)
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=f"TOTAL ABONADO: ${datos['monto']}", ln=1, align='C')
    
    pdf.ln(20)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt="Gracias por formar parte de Area Arqueros.", ln=1, align='C')
    
    return pdf.output(dest="S").encode("latin-1")

# --- 3. LOGIN ---
if "auth" not in st.session_state:
    st.session_state.update({"auth": False, "user": None, "rol": None})
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
                else: st.error("Acceso denegado")

if not st.session_state["auth"]:
    login()
    st.stop()

# --- 4. MENÚ PRINCIPAL ---
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
    st.caption(f"Fecha del Sistema: {get_today_ar().strftime('%d/%m/%Y')}")
    
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
            today_str = get_today_ar().strftime("%Y-%m-%d")
            df_a['fecha'] = df_a['fecha'].astype(str)
            today_data = df_a[df_a['fecha'] == today_str]
            if not today_data.empty:
                view_mode = st.radio("Agrupar por:", ["sede", "turno"], horizontal=True)
                counts = today_data[view_mode].value_counts().reset_index()
                counts.columns = [view_mode, 'cantidad']
                fig2 = px.bar(counts, x=view_mode, y='cantidad', title=f"Total: {len(today_data)}", color_discrete_sequence=['#1f2c56'])
                st.plotly_chart(fig2, use_container_width=True)
            else: st.info("Sin registros hoy.")

# === ALUMNOS ===
elif nav == "Alumnos":
    if st.session_state["view_profile_id"] is None:
        st.title("👥 Gestión de Alumnos")
        tab_dir, tab_new = st.tabs(["📂 Directorio", "➕ Nuevo Alumno"])
        
        with tab_dir:
            df = get_df("socios")
            if not df.empty:
                with st.expander("🔍 Filtros de Búsqueda", expanded=True):
                    c1, c2, c3, c4 = st.columns(4)
                    f_sede = c1.selectbox("Sede", ["Todas"] + sorted(df['sede'].astype(str).unique().tolist()))
                    f_grupo = c2.selectbox("Grupo", ["Todos"] + sorted(df['grupo'].astype(str).unique().tolist()))
                    f_plan = c3.selectbox("Plan", ["Todos"] + sorted(df['plan'].astype(str).unique().tolist()))
                    f_act = c4.selectbox("Estado", ["Activos", "Inactivos", "Todos"])
                
                df_fil = df.copy()
                if f_sede != "Todas": df_fil = df_fil[df_fil['sede'] == f_sede]
                if f_grupo != "Todos": df_fil = df_fil[df_fil['grupo'] == f_grupo]
                if f_plan != "Todos": df_fil = df_fil[df_fil['plan'] == f_plan]
                if f_act == "Activos": df_fil = df_fil[df_fil['activo'] == 1]
                elif f_act == "Inactivos": df_fil = df_fil[df_fil['activo'] == 0]
                
                st.caption(f"Resultados: {len(df_fil)}")
                
                for idx, row in df_fil.iterrows():
                    with st.container():
                        k1, k2, k3, k4, k5 = st.columns([3, 2, 2, 2, 1])
                        k1.markdown(f"**{row['nombre']} {row['apellido']}**")
                        k2.caption(row['sede'])
                        k3.caption(row.get('grupo', '-'))
                        k4.caption(row['plan'])
                        if k5.button("Ver ➜", key=f"v_{row['id']}"):
                            st.session_state["view_profile_id"] = row['id']
                            st.rerun()
                        st.divider()

        with tab_new:
            st.subheader("Alta Rápida")
            with st.form("alta_rapida"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nombre")
                ape = c2.text_input("Apellido")
                dni = c1.text_input("DNI")
                nac = c2.date_input("Nacimiento", min_value=date(1980,1,1))
                sede = st.selectbox("Sede", ["Sede C1", "Sede Saa"])
                grupo = st.selectbox("Grupo", ["Infantil", "Juvenil", "Adulto"])
                if st.form_submit_button("Guardar"):
                    if nom and ape:
                        uid = int(datetime.now().timestamp())
                        # ID, Fecha, Nom, Ape, DNI, Nac, Tutor, Wsp, Email, Sede, Plan, Notas, Vend, Act, Talle, Grupo, Peso, Alt
                        row = [uid, str(get_today_ar()), nom, ape, dni, str(nac), "", "", "", sede, "General", "", user, 1, "", grupo, 0, 0]
                        save_row("socios", row)
                        log_action(uid, "Alta Alumno", "Alta desde sistema", user)
                        st.success("Guardado")
    
    else:
        # VISTA PERFIL DETALLADO
        uid = st.session_state["view_profile_id"]
        df = get_df("socios")
        p = df[df['id'] == uid].iloc[0]
        
        if st.button("⬅️ Volver al Directorio"):
            st.session_state["view_profile_id"] = None
            st.rerun()
            
        st.title(f"👤 {p['nombre']} {p['apellido']}")
        
        if p.get('whatsapp'):
            tel = str(p['whatsapp']).replace('+', '').replace(' ', '')
            msg_pago = f"Hola {p['nombre']}, te recordamos que tu cuota vence pronto. Saludos Area Arqueros."
            link_wa = f"https://wa.me/{tel}?text={msg_pago.replace(' ', '%20')}"
            st.link_button("📱 Enviar Recordatorio de Pago", link_wa)
        
        c_h1, c_h2, c_h3 = st.columns(3)
        edad = calcular_edad(p['fecha_nacimiento'])
        c_h1.info(f"**DNI:** {p['dni']} | **Edad:** {edad}")
        c_h2.success(f"**Plan:** {p.get('plan','-')} | **Sede:** {p['sede']}")
        c_h3.warning(f"**Grupo:** {p.get('grupo','-')}")
        
        t_data, t_hist, t_log = st.tabs(["✏️ Datos Personales", "📅 Asistencias", "🔒 Auditoría"])
        
        with t_data:
            if rol == "Administrador":
                with st.form("edit_p"):
                    e1, e2 = st.columns(2)
                    n_nom = e1.text_input("Nombre", p['nombre'])
                    n_ape = e2.text_input("Apellido", p['apellido'])
                    n_dni = e1.text_input("DNI", p['dni'])
                    n_plan = e2.text_input("Plan", p['plan'])
                    n_notas = st.text_area("Notas", p.get('notas',''))
                    n_act = st.checkbox("Activo", value=True if p['activo']==1 else False)
                    if st.form_submit_button("Guardar Cambios"):
                        d_upd = p.to_dict()
                        d_upd.update({'nombre': n_nom, 'apellido': n_ape, 'dni': n_dni, 'plan': n_plan, 'notas': n_notas, 'activo': 1 if n_act else 0})
                        update_full_socio(uid, d_upd, user, original_data=p.to_dict())
                        st.success("Actualizado")
                        time.sleep(1); st.rerun()
            else: st.info("Modo Lectura")

        with t_hist:
            df_a = get_df("asistencias")
            if not df_a.empty:
                mis_a = df_a[df_a['id_socio'] == uid]
                st.metric("Total Clases", len(mis_a))
                st.dataframe(mis_a[['fecha', 'sede', 'turno']].sort_values('fecha', ascending=False), use_container_width=True)

        with t_log:
            df_l = get_df("logs")
            if not df_l.empty:
                mis_l = df_l[df_l['id_ref'].astype(str) == str(uid)]
                st.dataframe(mis_l[['fecha', 'usuario', 'accion', 'detalle']], use_container_width=True)

# === ASISTENCIA ===
elif nav == "Asistencia":
    st.title("✅ Tomar Asistencia")
    st.info("Sistema de Asistencia Operativo")

# === CONTABILIDAD ===
elif nav == "Contabilidad":
    st.title("📒 Contabilidad")
    
    # SIDEBAR FILTROS
    with st.sidebar:
        st.markdown("### 🔍 Filtros Contables")
        f_sede = st.multiselect("Sede", ["Sede C1", "Sede Saa"], default=["Sede C1", "Sede Saa"])
        f_mes = st.selectbox("Mes Abonado", ["Todos", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        f_rango1 = st.date_input("Fecha Desde", date(date.today().year, 1, 1))
        f_rango2 = st.date_input("Fecha Hasta", date.today())
        
    tab_in, tab_gen, tab_rep = st.tabs(["💰 Registrar & Confirmar", "🔄 Generación Masiva", "📊 Caja Diaria & Reportes"])
    
    with tab_in:
        st.subheader("Nuevo Ingreso")
        df_s = get_df("socios")
        if not df_s.empty:
            activos = df_s[df_s['activo']==1]
            # AQUI ESTÁ LA CORRECCIÓN DEL NOMBRE + APELLIDO
            sel = st.selectbox("Alumno", activos['id'].astype(str) + " - " + activos['nombre'] + " " + activos['apellido'])
            
            if "pago_exitoso" not in st.session_state: st.session_state.pago_exitoso = None

            with st.form("pay"):
                c1, c2 = st.columns(2)
                monto = c1.number_input("Monto", step=100)
                mes_pago = c2.selectbox("Mes que abona", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
                concepto = st.selectbox("Concepto", ["Cuota", "Matrícula", "Otros"])
                metodo = st.selectbox("Medio", ["Efectivo", "Transferencia", "MercadoPago"])
                
                if st.form_submit_button("Registrar"):
                    row = [int(datetime.now().timestamp()), str(get_today_ar()), int(sel.split(" - ")[0]), sel.split(" - ")[1], monto, concepto, metodo, "", "Pendiente", user, mes_pago]
                    save_row("pagos", row)
                    st.session_state.pago_exitoso = {
                        "fecha": str(get_today_ar()), "alumno": sel.split(" - ")[1],
                        "monto": monto, "concepto": concepto, "metodo": metodo
                    }
                    st.rerun()

            if st.session_state.pago_exitoso:
                st.success("✅ Pago Registrado Correctamente")
                datos_pdf = st.session_state.pago_exitoso
                pdf_bytes = generar_pdf(datos_pdf)
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Recibo_{datos_pdf["alumno"]}.pdf" style="text-decoration:none;"><button style="background-color:#2196F3;color:white;border:none;padding:10px;border-radius:5px;cursor:pointer;width:100%;font-weight:bold;">📄 Descargar Recibo PDF</button></a>'
                st.markdown(href, unsafe_allow_html=True)
                msg_recibo = f"*RECIBO DE PAGO - AREA ARQUEROS*\nFecha: {datos_pdf['fecha']}\nAlumno: {datos_pdf['alumno']}\nConcepto: {datos_pdf['concepto']}\nMonto: ${datos_pdf['monto']}\n\n¡Gracias!"
                st.text_area("Copiar para WhatsApp:", value=msg_recibo, height=150)
                if st.button("Cerrar Recibo"):
                    st.session_state.pago_exitoso = None
                    st.rerun()

    # --- GENERACIÓN MASIVA AUTOMÁTICA (SIN BOTÓN) ---
    with tab_gen:
        st.subheader("⚡ Deudores del Mes Actual")
        # Lógica automática de visualización
        df_pag = get_df("pagos")
        df_tar = get_df("tarifas") 
        
        # Filtros
        mes_actual_idx = get_today_ar().month - 1
        meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        mes_actual_nombre = meses[mes_actual_idx]
        
        pagaron_ids = []
        if not df_pag.empty:
            df_pag['dt'] = pd.to_datetime(df_pag['fecha_pago'], errors='coerce')
            # Usamos la fecha de Argentina para comparar
            hoy_ar = get_today_ar()
            pagos_mes = df_pag[ (df_pag['dt'].dt.month == hoy_ar.month) & (df_pag['concepto'].astype(str).str.contains("Cuota")) ]
            pagaron_ids = pagos_mes['id_socio'].unique()
        
        # Solo mostramos activos que no pagaron
        pendientes = df_s[ (df_s['activo']==1) & (~df_s['id'].isin(pagaron_ids)) ]
        
        if not pendientes.empty:
            st.warning(f"⚠️ Hay {len(pendientes)} alumnos sin pago de cuota en **{mes_actual_nombre}**.")
            st.dataframe(pendientes[['nombre', 'apellido', 'plan', 'sede']], use_container_width=True)
            
            # Botón de acción manual para escribir en DB
            if st.button("🚀 Generar Deuda para Todos (Pendiente)"):
                count = 0
                for idx, row_s in pendientes.iterrows():
                    precio = 15000 
                    if not df_tar.empty and row_s['plan'] in df_tar['concepto'].values:
                        precio = df_tar[df_tar['concepto']==row_s['plan']]['valor'].values[0]
                    
                    row_p = [
                        int(datetime.now().timestamp())+count, str(get_today_ar()), 
                        row_s['id'], f"{row_s['nombre']} {row_s['apellido']}", 
                        precio, "Cuota Mensual", "Pendiente", f"Plan: {row_s['plan']}", 
                        "Pendiente", "Sistema Auto", mes_actual_nombre
                    ]
                    save_row("pagos", row_p)
                    count+=1
                st.success(f"Se generaron {count} deudas pendientes.")
                time.sleep(2)
                st.rerun()
        else:
            st.success("🎉 ¡Excelente! Todos los alumnos activos están al día este mes.")

    with tab_rep:
        # CAJA DIARIA
        st.markdown("### 📅 Caja Diaria (Hoy)")
        df_p = get_df("pagos")
        if not df_p.empty:
            today = str(get_today_ar())
            caja_hoy = df_p[df_p['fecha_pago'] == today]
            
            if not caja_hoy.empty:
                total_hoy = pd.to_numeric(caja_hoy['monto'], errors='coerce').sum()
                efectivo = caja_hoy[caja_hoy['metodo']=="Efectivo"]['monto'].sum() if "Efectivo" in caja_hoy['metodo'].values else 0
                digital = total_hoy - efectivo
                
                # CAJA VISIBLE (Texto oscuro)
                col_c1, col_c2, col_c3 = st.columns(3)
                col_c1.markdown(f"<div class='caja-box'><h3>Total Hoy</h3><h2>${total_hoy:,.0f}</h2></div>", unsafe_allow_html=True)
                col_c2.metric("💵 Efectivo", f"${efectivo:,.0f}")
                col_c3.metric("💳 Digital", f"${digital:,.0f}")
                
                st.dataframe(caja_hoy[['nombre_socio', 'monto', 'metodo', 'concepto']])
            else:
                st.info("No hubo movimientos hoy.")
        
        st.divider()
        
        # REPORTES FILTRADOS
        if not df_p.empty:
            df_p['fecha_dt'] = pd.to_datetime(df_p['fecha_pago'], errors='coerce').dt.date
            mask = (df_p['fecha_dt'] >= f_rango1) & (df_p['fecha_dt'] <= f_rango2)
            if f_mes != "Todos" and 'mes_cobrado' in df_p.columns: mask = mask & (df_p['mes_cobrado'] == f_mes)
            df_final = df_p[mask]
            
            total = pd.to_numeric(df_final['monto'], errors='coerce').sum()
            st.metric("Total Recaudado (Filtrado)", f"${total:,.0f}")
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                fig1 = px.pie(df_final, values='monto', names='concepto', hole=0.4, title="Por Concepto")
                st.plotly_chart(fig1, use_container_width=True)
            with col_g2:
                daily = df_final.groupby('fecha_pago')['monto'].sum().reset_index()
                fig2 = px.bar(daily, x='fecha_pago', y='monto', title="Evolución")
                st.plotly_chart(fig2, use_container_width=True)
            st.dataframe(df_final, use_container_width=True)

elif nav == "Configurar Tarifas":
    st.title("⚙️ Tarifas")
    df = get_df("tarifas")
    edited = st.data_editor(df, num_rows="dynamic")
    if st.button("Guardar"):
        actualizar_tarifas_bulk(edited)
        st.success("Guardado")
