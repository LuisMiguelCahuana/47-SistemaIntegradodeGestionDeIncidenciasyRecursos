
import streamlit as st
import gspread
import unicodedata
import re

from google.oauth2.service_account import Credentials
from datetime import datetime

# =====================================================
# CONFIGURACIÓN GENERAL
# =====================================================

st.set_page_config(
    page_title="SIGIR | Gestión de Recursos",
    page_icon="📋",
    layout="wide"
)

SPREADSHEET_ID = "1AJ94Nrvlg7T4994K3qD_gD7dv6JZ563hJSf8hvPhOTA"
PADRON_VEHICULOS_ID = "1osj3Usp1MhN0U97r7E4W2tYXNa9kmmNDtQRE6MkAQ_U"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# =====================================================
# ESTILO
# =====================================================

st.markdown("""
<style>
    .main-title {
        font-size: 30px;
        font-weight: 800;
        color: #163A5F;
        margin-bottom: 0;
    }
    .subtitle {
        color: #64748b;
        font-size: 14px;
        margin-bottom: 25px;
    }
    div.stButton > button[kind="primaryFormSubmit"] {
        background-color: #163A5F;
        color: white;
        border-radius: 8px;
        height: 45px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# =====================================================
# CONEXIÓN CON GOOGLE SHEETS
# =====================================================

@st.cache_resource
def conectar_google_sheets():

    credentials = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES
    )

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    return spreadsheet


try:
    spreadsheet = conectar_google_sheets()
    conexion_ok = True

except Exception as e:
    conexion_ok = False
    st.error("No se pudo conectar con Google Sheets.")
    st.error(f"Detalle: {e}")


# =====================================================
# PADRÓN MAESTRO DE VEHÍCULOS
# =====================================================

@st.cache_data(ttl=300)
def cargar_padron_vehiculos():
    """
    Lee el primer tab del padrón externo.
    Columnas requeridas: CENTRO DE COSTOS, PLACA, UUNN, CONTRATO.
    Se actualiza en caché cada 5 minutos.
    """
    credenciales = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES
    )
    cliente_padron = gspread.authorize(credenciales)
    archivo_padron = cliente_padron.open_by_key(PADRON_VEHICULOS_ID)
    pestana = archivo_padron.get_worksheet(0)

    registros = pestana.get_all_records()

    requeridas = {
        "CENTRODECOSTOS": "CENTRO DE COSTOS",
        "PLACA": "PLACA",
        "UUNN": "UUNN",
        "CONTRATO": "CONTRATO"
    }

    salida = []
    for registro in registros:
        normalizados = {
            normalizar_clave(k): str(v).strip()
            for k, v in registro.items()
        }

        faltantes = [
            nombre for clave, nombre in requeridas.items()
            if not normalizados.get(clave)
        ]

        # Ignorar filas completamente vacías; reportar filas parciales después.
        if all(not str(v).strip() for v in registro.values()):
            continue

        if faltantes:
            continue

        salida.append({
            "CENTRO DE COSTOS": normalizados["CENTRODECOSTOS"],
            "PLACA": normalizados["PLACA"].upper(),
            "UUNN": normalizados["UUNN"].upper(),
            "CONTRATO": normalizados["CONTRATO"]
        })

    if not salida:
        raise ValueError(
            "No se encontraron vehículos. Verifica que la primera pestaña "
            "tenga las columnas CENTRO DE COSTOS, PLACA, UUNN y CONTRATO."
        )

    return salida


def normalizar_clave(valor):
    valor = str(valor).strip().upper()
    valor = unicodedata.normalize("NFD", valor)
    valor = "".join(
        caracter for caracter in valor
        if unicodedata.category(caracter) != "Mn"
    )
    return re.sub(r"[^A-Z0-9]", "", valor)


# =====================================================
# FUNCIONES GENERALES
# =====================================================

def normalizar(texto):

    texto = str(texto).strip().upper()

    texto = unicodedata.normalize("NFD", texto)

    texto = "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )

    return re.sub(r"[^A-Z0-9]", "", texto)


def guardar_registro(nombre_hoja, encabezados, datos):

    try:

        hoja = spreadsheet.worksheet(nombre_hoja)

        # Leer encabezados existentes
        encabezados_hoja = hoja.row_values(1)

        # Si la primera fila está vacía, crear encabezados
        if not encabezados_hoja:

            hoja.append_row(
                encabezados,
                value_input_option="USER_ENTERED"
            )

            encabezados_hoja = encabezados

        # Relacionar los encabezados con los datos
        datos_normalizados = {
            normalizar(k): v for k, v in datos.items()
        }

        # Alias para variaciones de escritura
        alias = {
            "FECHAINCORPRACIONDELNUEVOPERSONAL":
                "FECHAINCORPORACIONDELNUEVOPERSONAL",
            "MATERIALEQUIPOYHERRAMIENTA":
                "MATERIALEQUIPOYHERRAMIENTA",
            "MATERIALEQUPOYHERRAMIENTA":
                "MATERIALEQUIPOYHERRAMIENTA"
        }

        encabezados_normalizados = []

        for encabezado in encabezados_hoja:

            clave = normalizar(encabezado)
            clave = alias.get(clave, clave)

            encabezados_normalizados.append(clave)

        # Validar que estén todos los campos esperados
        faltantes = [
            normalizar(campo)
            for campo in encabezados
            if normalizar(campo) not in encabezados_normalizados
        ]

        if faltantes:

            raise ValueError(
                "Los encabezados de Google Sheets no coinciden "
                "con los campos del formulario. Revisa la primera fila."
            )

        # Construir fila respetando el orden real de la hoja
        nueva_fila = []

        for encabezado in encabezados_normalizados:

            valor = datos_normalizados.get(encabezado, "")

            nueva_fila.append(valor)

        # Guardar registro
        hoja.append_row(
            nueva_fila,
            value_input_option="USER_ENTERED"
        )

        return True, "Registro guardado correctamente."

    except Exception as e:

        return False, str(e)


def fecha_texto(fecha):

    if fecha is None:
        return ""

    return fecha.strftime("%d/%m/%Y")



# =====================================================
# ACTUALIZACIÓN DE REGISTROS YA REPORTADOS
# =====================================================

def buscar_columna(encabezados, nombre):
    """Devuelve el índice (base 1) de una columna por nombre normalizado."""
    objetivo = normalizar(nombre)
    for indice, encabezado in enumerate(encabezados, start=1):
        if normalizar(encabezado) == objetivo:
            return indice
    raise ValueError(f"No se encontró la columna: {nombre}")


def convertir_fecha_existente(valor):
    """Convierte fechas guardadas como texto a date; devuelve None si está vacío."""
    if not valor:
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(valor).strip(), formato).date()
        except ValueError:
            pass
    return None


def actualizar_celda(hoja, encabezados, fila, columna, valor):
    """Actualiza una celda existente sin crear una fila nueva."""
    col = buscar_columna(encabezados, columna)
    hoja.update_cell(fila, col, valor)


def interfaz_actualizar_registros():
    st.subheader("📝 Actualizar incidencias reportadas")

    # Mensaje persistente: se muestra después de refrescar la lista de pendientes.
    if st.session_state.get("mensaje_actualizacion_sigir"):
        st.success(st.session_state.pop("mensaje_actualizacion_sigir"))

    st.info(
        "Selecciona una incidencia pendiente para registrar su incorporación, "
        "reposición o reparación. Esta opción modifica la fila existente; "
        "no crea un registro duplicado."
    )

    tipo = st.selectbox(
        "Selecciona el tipo de recurso",
        ["Personal", "Vehículo", "Material"]
    )

    configuracion = {
        "Personal": {
            "hoja": "Personal",
            "fecha": "FECHA_INCORPRACION / NUEVO PERSONAL",
            "fecha_label": "Fecha de incorporación del nuevo personal",
            "inicio": "FECHA_SALIDA",
            "identificadores": [
                "CONTRATO", "PERSONAL", "CARGO", "TIPO_INCIDENCIA",
                "FECHA_SALIDA", "ESTADO"
            ]
        },
        "Vehículo": {
            "hoja": "Vehiculo",
            "fecha": "FECHA_REPOSICION",
            "fecha_label": "Fecha de reposición / retorno a servicio",
            "inicio": "FECHA_REPORTE",
            "identificadores": [
                "CONTRATO", "UUNN", "PLACA", "TIPO_INCIDENCIA",
                "FECHA_REPORTE", "ESTADO"
            ]
        },
        "Material": {
            "hoja": "Material",
            "fecha": "FECHA_REPOSICION",
            "fecha_label": "Fecha de reposición / atención",
            "inicio": "FECHA_INICIO",
            "identificadores": [
                "CONTRATO", "UUNN", "MATERIAL/EQUIPO Y HERRAMIENTA",
                "CANTIDAD_FALTANTE", "FECHA_INICIO", "ESTADO"
            ]
        }
    }

    cfg = configuracion[tipo]

    try:
        hoja = spreadsheet.worksheet(cfg["hoja"])
        valores = hoja.get_all_values()

        if not valores or len(valores) < 2:
            st.warning("Esta pestaña todavía no contiene registros.")
            return

        encabezados = valores[0]
        encabezados_norm = [normalizar(x) for x in encabezados]

        idx_estado = buscar_columna(encabezados, "ESTADO") - 1
        filas_pendientes = []

        for numero_fila, fila in enumerate(valores[1:], start=2):
            estado_actual = fila[idx_estado].strip().upper() if idx_estado < len(fila) else ""
            if estado_actual == "PENDIENTE":
                filas_pendientes.append((numero_fila, fila))

        if not filas_pendientes:
            st.success("No hay incidencias pendientes en este módulo.")
            return

        def etiqueta_registro(item):
            numero_fila, fila = item
            datos_fila = {
                encabezados_norm[i]: fila[i] if i < len(fila) else ""
                for i in range(len(encabezados_norm))
            }
            partes = [f"Fila {numero_fila}"]
            for campo in cfg["identificadores"]:
                valor = datos_fila.get(normalizar(campo), "")
                if valor:
                    partes.append(f"{campo}: {valor}")
            return " | ".join(partes)

        seleccionado = st.selectbox(
            "Selecciona la incidencia pendiente que deseas actualizar",
            filas_pendientes,
            format_func=etiqueta_registro
        )

        numero_fila, fila_seleccionada = seleccionado
        datos_fila = {
            encabezados_norm[i]: fila_seleccionada[i] if i < len(fila_seleccionada) else ""
            for i in range(len(encabezados_norm))
        }

        st.caption(f"Registro seleccionado: fila {numero_fila} de la pestaña {cfg['hoja']}.")

        fecha_guardada = datos_fila.get(normalizar(cfg["fecha"]), "")
        fecha_actual = convertir_fecha_existente(fecha_guardada)
        estado_actual = datos_fila.get(normalizar("ESTADO"), "PENDIENTE").upper()
        observacion_actual = datos_fila.get(normalizar("OBSERVACIONES"), "")

        with st.form("form_actualizar_incidencia"):
            st.markdown("**Datos de cierre de la incidencia**")
            st.caption(
                "Puedes registrar la fecha real en que ocurrió la incorporación, "
                "reparación o reposición, aunque estés actualizando el sistema días después."
            )

            # Fecha y estado en una sola fila.
            col_fecha, col_estado = st.columns([2, 1])

            with col_fecha:
                nueva_fecha = st.date_input(
                    f"{cfg['fecha_label']} (selecciona la fecha real)",
                    value=fecha_actual or datetime.now().date(),
                    format="DD/MM/YYYY",
                    help=(
                        "Selecciona la fecha efectiva del evento. "
                        "Puedes elegir una fecha pasada si la actualización se registra después."
                    )
                )

            with col_estado:
                nuevo_estado = st.selectbox(
                    "Estado",
                    ["PENDIENTE", "REPUESTO"],
                    index=1 if estado_actual == "REPUESTO" else 0
                )

            nuevas_observaciones = st.text_area(
                "Observaciones / acciones realizadas",
                value=observacion_actual,
                placeholder="Ej. Se incorporó un nuevo técnico / se asignó otra camioneta / se recibieron los materiales."
            )

            confirmar = st.form_submit_button(
                "💾 ACTUALIZAR REGISTRO",
                use_container_width=True
            )

            if confirmar:
                if nuevo_estado == "REPUESTO" and nueva_fecha is None:
                    st.warning(
                        "Para marcar la incidencia como REPUESTO, "
                        "debes registrar la fecha de incorporación o reposición."
                    )
                else:
                    try:
                        if nuevo_estado == "REPUESTO":
                            actualizar_celda(
                                hoja, encabezados, numero_fila,
                                cfg["fecha"], fecha_texto(nueva_fecha)
                            )

                        actualizar_celda(
                            hoja, encabezados, numero_fila,
                            "ESTADO", nuevo_estado
                        )

                        # Registrar también cuándo se digitó la actualización.
                        # Esta columna se agrega al final si todavía no existe.
                        encabezados_actuales = hoja.row_values(1)
                        try:
                            col_fecha_actualizacion = buscar_columna(
                                encabezados_actuales, "FECHA_ACTUALIZACION"
                            )
                        except ValueError:
                            col_fecha_actualizacion = len(encabezados_actuales) + 1
                            if col_fecha_actualizacion > hoja.col_count:
                                hoja.add_cols(col_fecha_actualizacion - hoja.col_count)
                            hoja.update_cell(1, col_fecha_actualizacion, "FECHA_ACTUALIZACION")

                        hoja.update_cell(
                            numero_fila,
                            col_fecha_actualizacion,
                            datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        )

                        actualizar_celda(
                            hoja, encabezados, numero_fila,
                            "OBSERVACIONES", nuevas_observaciones.strip()
                        )

                        st.session_state["mensaje_actualizacion_sigir"] = (
                            "¡Actualización realizada correctamente! "
                            "La fecha real, el estado y las observaciones se guardaron en Google Sheets."
                        )
                        st.rerun()

                    except Exception as error:
                        st.error(f"No se pudo actualizar el registro: {error}")

    except Exception as error:
        st.error(f"No se pudo consultar la pestaña {cfg['hoja']}: {error}")


# =====================================================
# ENCABEZADOS DE LAS TRES HOJAS
# =====================================================

HEADERS_PERSONAL = [
    "CONTRATO",
    "DENOMINACION",
    "UUNN/SSEE",
    "PERSONAL",
    "DNI",
    "CARGO",
    "TIPO_INCIDENCIA",
    "FECHA_SALIDA",
    "FECHA_INCORPRACION / NUEVO PERSONAL",
    "ESTADO",
    "OBSERVACIONES"
]

HEADERS_VEHICULO = [
    "CONTRATO",
    "UUNN",
    "PLACA",
    "TIPO_INCIDENCIA",
    "DESCRIPCION",
    "FECHA_REPORTE",
    "FECHA_REPOSICION",
    "ESTADO",
    "OBSERVACIONES"
]

HEADERS_MATERIAL = [
    "CONTRATO",
    "UUNN",
    "MATERIAL/EQUIPO Y HERRAMIENTA",
    "TIPO_INCIDENCIA",
    "CANTIDAD_FALTANTE",
    "FECHA_INICIO",
    "FECHA_REPOSICION",
    "ESTADO",
    "OBSERVACIONES"
]


# =====================================================
# CABECERA DE LA APLICACIÓN
# =====================================================

st.markdown(
    '<p class="main-title">SIGIR</p>',
    unsafe_allow_html=True
)

st.markdown(
    '<p class="subtitle">'
    'SISTEMA INTEGRADO DE GESTIÓN DE INCIDENCIAS Y RECURSOS'
    '</p>',
    unsafe_allow_html=True
)

st.divider()

# =====================================================
# MENÚ DE NAVEGACIÓN
# =====================================================

modulo = st.sidebar.radio(
    "SELECCIONAR FORMULARIO",
    [
        "👤 Personal",
        "🚗 Vehículos",
        "📦 Materiales",
        "📝 Actualizar registros"
    ]
)

st.sidebar.divider()

st.sidebar.markdown("### SIGIR")
st.sidebar.caption("Registro de incidencias y disponibilidad de recursos.")
st.sidebar.caption("Versión 1.0")

# =====================================================
# ACTUALIZAR REGISTROS EXISTENTES
# =====================================================

if modulo == "📝 Actualizar registros":

    if conexion_ok:
        interfaz_actualizar_registros()

# =====================================================
# FORMULARIO 1: PERSONAL
# =====================================================

elif modulo == "👤 Personal":

    st.subheader("👤 Registro de incidencias de personal")

    st.info(
        "Registra renuncias, vacaciones, licencias, "
        "descansos médicos y otras incidencias."
    )

    with st.form("form_personal", clear_on_submit=True):

        col1, col2 = st.columns(2)

        with col1:

            contrato = st.text_input(
                "Contrato *",
                placeholder="Ej. GR-022-2023/ELECTO"
            )

            denominacion = st.text_input(
                "Denominación *",
                placeholder="Ej. EBAR"
            )

            uunn = st.selectbox(
                "UUNN/SSEE *",
                [
                    "HUANCAYO",
                    "PASCO",
                    "TARMA",
                    "LA MERCED",
                    "SATIPO",
                    "OTRO"
                ]
            )

            personal = st.text_input(
                "Nombre del personal *"
            )

            dni = st.text_input(
                "DNI",
                max_chars=8
            )

        with col2:

            cargo = st.text_input(
                "Cargo *"
            )

            tipo_incidencia = st.selectbox(
                "Tipo de incidencia *",
                [
                    "RENUNCIA",
                    "CESE",
                    "VACACIONES",
                    "LICENCIA",
                    "DESCANSO MEDICO",
                    "PERMISO",
                    "FALTA",
                    "OTRO"
                ]
            )

            fecha_salida = st.date_input(
                "Fecha de salida *",
                format="DD/MM/YYYY"
            )

            # La fecha de incorporación se registra posteriormente
            # desde el módulo "Actualizar registros".
            fecha_incorporacion = None

            estado = st.selectbox(
                "Estado *",
                [
                    "PENDIENTE",
                    "REPUESTO"
                ]
            )

        observaciones = st.text_area(
            "Observaciones",
            placeholder="Ingrese detalles adicionales..."
        )

        guardar = st.form_submit_button(
            "💾 GUARDAR REGISTRO",
            use_container_width=True
        )

        if guardar:

            if not all([
                contrato.strip(),
                denominacion.strip(),
                personal.strip(),
                cargo.strip()
            ]):

                st.warning(
                    "Completa los campos obligatorios."
                )

            elif dni and (
                not dni.isdigit() or len(dni) != 8
            ):

                st.warning("El DNI debe contener 8 dígitos.")

            elif (
                fecha_incorporacion is not None
                and fecha_incorporacion < fecha_salida
            ):

                st.warning(
                    "La fecha de incorporación no puede "
                    "ser anterior a la fecha de salida."
                )

            elif estado == "REPUESTO":
                st.warning(
                    "Registra inicialmente la incidencia como PENDIENTE. "
                    "Cuando se incorpore el reemplazo, utiliza 'Actualizar registros' "
                    "para colocar la fecha real y cambiar el estado a REPUESTO."
                )

            elif conexion_ok:

                datos = {
                    "CONTRATO": contrato.strip(),
                    "DENOMINACION": denominacion.strip(),
                    "UUNN/SSEE": uunn,
                    "PERSONAL": personal.strip().upper(),
                    "DNI": dni,
                    "CARGO": cargo.strip().upper(),
                    "TIPO_INCIDENCIA": tipo_incidencia,
                    "FECHA_SALIDA": fecha_texto(fecha_salida),
                    "FECHA_INCORPRACION / NUEVO PERSONAL":
                        fecha_texto(fecha_incorporacion),
                    "ESTADO": estado,
                    "OBSERVACIONES": observaciones.strip()
                }

                ok, mensaje = guardar_registro(
                    "Personal",
                    HEADERS_PERSONAL,
                    datos
                )

                if ok:
                    st.success("✅ " + mensaje)
                    st.balloons()
                else:
                    st.error(mensaje)


# =====================================================
# FORMULARIO 2: VEHÍCULOS
# =====================================================

elif modulo == "🚗 Vehículos":

    st.subheader("🚗 Registro de incidencias de vehículos")

    st.info(
        "El contrato, la UUNN y la placa se seleccionan desde el padrón maestro "
        "de vehículos. Los datos se actualizan automáticamente desde Google Sheets."
    )

    try:
        padron = cargar_padron_vehiculos()

        contratos_disponibles = sorted({
            fila["CONTRATO"] for fila in padron if fila["CONTRATO"]
        })

        if not contratos_disponibles:
            st.warning("El padrón no contiene contratos disponibles.")
            st.stop()

        # Filtros dependientes en una sola fila
        col_contrato, col_uunn, col_placa = st.columns(3)

        with col_contrato:
            contrato = st.selectbox(
                "Contrato *",
                contratos_disponibles,
                key="vehiculo_contrato"
            )

        registros_contrato = [
            fila for fila in padron
            if fila["CONTRATO"] == contrato
        ]

        uunn_disponibles = sorted({
            fila["UUNN"] for fila in registros_contrato if fila["UUNN"]
        })

        with col_uunn:
            uunn = st.selectbox(
                "UUNN *",
                uunn_disponibles,
                key="vehiculo_uunn"
            )

        registros_unidad = [
            fila for fila in registros_contrato
            if fila["UUNN"] == uunn
        ]

        placas_disponibles = sorted({
            fila["PLACA"] for fila in registros_unidad if fila["PLACA"]
        })

        with col_placa:
            placa = st.selectbox(
                "Placa del vehículo *",
                placas_disponibles,
                key="vehiculo_placa"
            )

        fila_vehiculo = next(
            (
                fila for fila in registros_unidad
                if fila["PLACA"] == placa
            ),
            {}
        )

        if fila_vehiculo.get("CENTRO DE COSTOS"):
            st.caption(
                f"Centro de costos asociado: {fila_vehiculo['CENTRO DE COSTOS']}"
            )

        with st.form("form_vehiculo", clear_on_submit=True):

            # Tipo de incidencia y fecha de reporte en una fila
            col_tipo, col_fecha = st.columns(2)

            with col_tipo:
                tipo_incidencia = st.selectbox(
                    "Tipo de incidencia *",
                    [
                        "FALLA MECANICA",
                        "ACCIDENTE",
                        "MANTENIMIENTO PREVENTIVO",
                        "MANTENIMIENTO CORRECTIVO",
                        "DOCUMENTACION",
                        "OTRO"
                    ]
                )

            with col_fecha:
                fecha_reporte = st.date_input(
                    "Fecha de reporte *",
                    format="DD/MM/YYYY"
                )

            # Descripción y estado en una misma fila
            col_descripcion, col_estado = st.columns([2, 1])

            with col_descripcion:
                descripcion = st.text_area(
                    "Descripción de la incidencia *",
                    placeholder="Describa la falla o incidencia...",
                    height=120
                )

            with col_estado:
                estado = st.selectbox(
                    "Estado *",
                    [
                        "PENDIENTE",
                        "REPUESTO"
                    ]
                )

            observaciones = st.text_area(
                "Observaciones",
                placeholder="Ej. Se asignó otra camioneta..."
            )

            guardar = st.form_submit_button(
                "💾 GUARDAR REGISTRO",
                use_container_width=True
            )

            if guardar:

                if not descripcion.strip():
                    st.warning("Completa la descripción de la incidencia.")

                elif conexion_ok:

                    datos = {
                        "CONTRATO": contrato,
                        "UUNN": uunn,
                        "PLACA": placa,
                        "TIPO_INCIDENCIA": tipo_incidencia,
                        "DESCRIPCION": descripcion.strip(),
                        "FECHA_REPORTE": fecha_texto(fecha_reporte),
                        "FECHA_REPOSICION": "",
                        "ESTADO": estado,
                        "OBSERVACIONES": observaciones.strip()
                    }

                    ok, mensaje = guardar_registro(
                        "Vehiculo",
                        HEADERS_VEHICULO,
                        datos
                    )

                    if ok:
                        st.success("✅ " + mensaje)
                        st.balloons()
                    else:
                        st.error(mensaje)

    except Exception as e:
        st.error(
            "No se pudo cargar el padrón de vehículos. "
            "Verifica que el archivo esté compartido con la cuenta de servicio "
            "configurada en Streamlit Secrets."
        )
        st.caption(f"Detalle técnico: {e}")


# =====================================================
# FORMULARIO 3: MATERIALES
# =====================================================

elif modulo == "📦 Materiales":

    st.subheader("📦 Registro de materiales, equipos y herramientas")

    st.info(
        "Registra faltantes, deterioros, averías "
        "y solicitudes de reposición."
    )

    with st.form("form_material", clear_on_submit=True):

        col1, col2 = st.columns(2)

        with col1:

            contrato = st.text_input(
                "Contrato *"
            )

            uunn = st.selectbox(
                "UUNN *",
                [
                    "HUANCAYO",
                    "PASCO",
                    "TARMA",
                    "LA MERCED",
                    "SATIPO",
                    "OTRO"
                ]
            )

            material = st.text_input(
                "Material, equipo o herramienta *",
                placeholder="Ej. Medidor monofásico"
            )

            tipo_incidencia = st.selectbox(
                "Tipo de incidencia *",
                [
                    "FALTANTE",
                    "DESGASTE",
                    "DETERIORO",
                    "AVERIA",
                    "PERDIDA",
                    "ROBO",
                    "OTRO"
                ]
            )

        with col2:

            cantidad = st.number_input(
                "Cantidad faltante *",
                min_value=1,
                step=1,
                value=1
            )

            fecha_inicio = st.date_input(
                "Fecha de inicio *",
                format="DD/MM/YYYY"
            )

            # La fecha de reposición se registra posteriormente
            # desde el módulo "Actualizar registros".
            fecha_reposicion = None

            estado = st.selectbox(
                "Estado *",
                [
                    "PENDIENTE",
                    "REPUESTO"
                ]
            )

        observaciones = st.text_area(
            "Observaciones",
            placeholder="Ej. Se recibieron 20 unidades..."
        )

        guardar = st.form_submit_button(
            "💾 GUARDAR REGISTRO",
            use_container_width=True
        )

        if guardar:

            if not all([
                contrato.strip(),
                material.strip()
            ]):

                st.warning(
                    "Completa los campos obligatorios."
                )

            elif estado == "REPUESTO":
                st.warning(
                    "Registra inicialmente la incidencia como PENDIENTE. "
                    "Cuando recibas el material, utiliza 'Actualizar registros' "
                    "para colocar la fecha real y cambiar el estado a REPUESTO."
                )

            elif conexion_ok:

                datos = {
                    "CONTRATO": contrato.strip(),
                    "UUNN": uunn,
                    "MATERIAL/EQUIPO Y HERRAMIENTA":
                        material.strip().upper(),
                    "TIPO_INCIDENCIA": tipo_incidencia,
                    "CANTIDAD_FALTANTE": int(cantidad),
                    "FECHA_INICIO": fecha_texto(fecha_inicio),
                    "FECHA_REPOSICION": fecha_texto(fecha_reposicion),
                    "ESTADO": estado,
                    "OBSERVACIONES": observaciones.strip()
                }

                ok, mensaje = guardar_registro(
                    "Material",
                    HEADERS_MATERIAL,
                    datos
                )

                if ok:
                    st.success("✅ " + mensaje)
                    st.balloons()
                else:
                    st.error(mensaje)


# =====================================================
# PIE DE PÁGINA
# =====================================================

st.divider()

st.caption(
    "SIGIR | Sistema Integrado de Gestión de Incidencias "
    "y Recursos | Versión 1.0"
)

st.caption(
    "Registro centralizado de personal, vehículos, "
    "materiales, equipos y herramientas."
)
