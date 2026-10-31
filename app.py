
import streamlit as st
import gspread
import pandas as pd
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

# Limpiar los formularios únicamente después de guardar correctamente.
# Se ejecuta al inicio del rerun, antes de volver a crear los widgets.
_prefijos_reset = st.session_state.pop("_sigir_reset_prefijos", [])
if _prefijos_reset:
    for _clave in list(st.session_state.keys()):
        if any(_clave.startswith(_prefijo) for _prefijo in _prefijos_reset):
            st.session_state.pop(_clave, None)

_mensaje_guardado = st.session_state.pop("_sigir_mensaje_guardado", None)
if _mensaje_guardado:
    st.success(_mensaje_guardado)

SPREADSHEET_ID = "1AJ94Nrvlg7T4994K3qD_gD7dv6JZ563hJSf8hvPhOTA"
PADRON_VEHICULOS_ID = "1osj3Usp1MhN0U97r7E4W2tYXNa9kmmNDtQRE6MkAQ_U"
PADRON_PERSONAL_ID = "1OEmtvbamJhKX_TbrBYDwNIuWFlYY_U66EAUfXZ42Eys"
PADRON_MATERIALES_ID = "1v_lL4XGV5lX0JoFSavmtdg91-hSaeJwdBzLd-bin2E8"

# Archivo de Google Sheets que administra los usuarios de SIGIR.
SPREADSHEET_USUARIOS_ID = "1CnZME_yWF5rLyjOOUoh8izIk8GE3tLPoMRj8Uzgu-38"
HOJA_USUARIOS = None  # None = primera pestaña

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
    Columnas requeridas: CENTRO DE COSTOS, PLACA, UUNN, CONTRATO y SSEE (columna E).
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
        "CONTRATO": "CONTRATO",
        "SSEE": "SSEE"
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
            "CONTRATO": normalizados["CONTRATO"],
            "SSEE": normalizados["SSEE"].upper()
        })

    if not salida:
        raise ValueError(
            "No se encontraron vehículos. Verifica que la primera pestaña "
            "tenga las columnas CENTRO DE COSTOS, PLACA, UUNN, CONTRATO y SSEE."
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


@st.cache_data(ttl=300)
def cargar_padron_personal():
    """
    Lee el padrón de trabajadores desde Google Sheets.
    Se utiliza la primera pestaña y se conserva el DNI como texto
    para no perder ceros iniciales.
    """
    credenciales = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES
    )
    cliente = gspread.authorize(credenciales)
    archivo = cliente.open_by_key(PADRON_PERSONAL_ID)
    hoja = archivo.get_worksheet(0)

    valores = hoja.get_all_values()
    if not valores or len(valores) < 2:
        raise ValueError(
            "El padrón de personal no contiene encabezados y registros "
            "en la primera pestaña."
        )

    encabezados = [normalizar_clave(x) for x in valores[0]]
    requeridas = {
        "CONTRATO": "CONTRATO",
        "UUNN": "UUNN",
        "APELLIDOSYNOMBRES": "APELLIDOS Y NOMBRES",
        "LOCALIDAD": "LOCALIDAD",
        "DNI": "DNI",
        "CARGO": "CARGO"
    }

    indices = {}
    for clave, etiqueta in requeridas.items():
        if clave not in encabezados:
            raise ValueError(
                f"No se encontró la columna '{etiqueta}' en el padrón. "
                "Verifica los encabezados de la primera pestaña."
            )
        indices[clave] = encabezados.index(clave)

    salida = []
    for fila in valores[1:]:
        if not any(str(celda).strip() for celda in fila):
            continue

        def valor_columna(clave):
            indice = indices[clave]
            return str(fila[indice]).strip() if indice < len(fila) else ""

        contrato = valor_columna("CONTRATO")
        uunn = valor_columna("UUNN")
        nombre = valor_columna("APELLIDOSYNOMBRES")
        localidad = valor_columna("LOCALIDAD")
        dni = valor_columna("DNI")
        cargo = valor_columna("CARGO")

        # Omitir filas incompletas que no permitan identificar al trabajador.
        if not all([contrato, uunn, localidad, nombre, dni, cargo]):
            continue

        salida.append({
            "CONTRATO": contrato,
            "UUNN": uunn.upper(),
            "LOCALIDAD": localidad,
            "APELLIDOS Y NOMBRES": nombre,
            "DNI": dni,
            "CARGO": cargo
        })

    if not salida:
        raise ValueError(
            "No se encontraron trabajadores con CONTRATO, UUNN, "
            "APELLIDOS Y NOMBRES, LOCALIDAD, DNI y CARGO completos."
        )

    return salida


@st.cache_data(ttl=300)
def cargar_ubicaciones_padron_personal():
    """
    Lee únicamente UUNN y LOCALIDAD del padrón maestro de personal.
    Permite alimentar el formulario de Materiales aunque otras columnas
    del registro de personal estén vacías.
    """
    credenciales = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES
    )
    cliente = gspread.authorize(credenciales)
    archivo = cliente.open_by_key(PADRON_PERSONAL_ID)
    hoja = archivo.get_worksheet(0)

    valores = hoja.get_all_values()
    if not valores or len(valores) < 2:
        raise ValueError(
            "El padrón de personal no contiene encabezados y registros "
            "en la primera pestaña."
        )

    encabezados = [normalizar_clave(x) for x in valores[0]]
    requeridas = {"UUNN": "UUNN", "LOCALIDAD": "LOCALIDAD"}
    indices = {}

    for clave, etiqueta in requeridas.items():
        if clave not in encabezados:
            raise ValueError(
                f"No se encontró la columna '{etiqueta}' en el padrón de personal."
            )
        indices[clave] = encabezados.index(clave)

    salida = []
    vistos = set()

    for fila in valores[1:]:
        uunn = str(fila[indices["UUNN"]]).strip() if indices["UUNN"] < len(fila) else ""
        localidad = str(fila[indices["LOCALIDAD"]]).strip() if indices["LOCALIDAD"] < len(fila) else ""

        if not uunn or not localidad:
            continue

        clave = (uunn.upper(), localidad.upper())
        if clave in vistos:
            continue

        vistos.add(clave)
        salida.append({"UUNN": uunn.upper(), "LOCALIDAD": localidad})

    if not salida:
        raise ValueError(
            "No se encontraron valores de UUNN y LOCALIDAD en el padrón de personal."
        )

    return salida


@st.cache_data(ttl=300)
def cargar_padron_materiales():
    """
    Lee el padrón maestro de materiales desde Google Sheets.
    Columnas requeridas: CONTRATO, TIPO_INSPECCION, DESCRIPCION
    y UNIDAD_MEDIDA. Se actualiza en caché cada 5 minutos.
    """
    credenciales = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES
    )
    cliente = gspread.authorize(credenciales)
    archivo = cliente.open_by_key(PADRON_MATERIALES_ID)
    hoja = archivo.get_worksheet(0)

    valores = hoja.get_all_values()
    if not valores or len(valores) < 2:
        raise ValueError(
            "El padrón de materiales no contiene encabezados y registros "
            "en la primera pestaña."
        )

    encabezados = [normalizar_clave(x) for x in valores[0]]
    requeridas = {
        "CONTRATO": "CONTRATO",
        "TIPOINSPECCION": "TIPO_INSPECCION",
        "DESCRIPCION": "DESCRIPCION",
        "UNIDADMEDIDA": "UNIDAD_MEDIDA"
    }

    indices = {}
    for clave, etiqueta in requeridas.items():
        if clave not in encabezados:
            raise ValueError(
                f"No se encontró la columna '{etiqueta}' en el padrón "
                "de materiales. Verifica los encabezados de la primera pestaña."
            )
        indices[clave] = encabezados.index(clave)

    salida = []
    for fila in valores[1:]:
        if not any(str(celda).strip() for celda in fila):
            continue

        def valor_columna(clave):
            indice = indices[clave]
            return str(fila[indice]).strip() if indice < len(fila) else ""

        contrato = valor_columna("CONTRATO")
        tipo = valor_columna("TIPOINSPECCION")
        descripcion = valor_columna("DESCRIPCION")
        unidad = valor_columna("UNIDADMEDIDA")

        if not all([contrato, tipo, descripcion, unidad]):
            continue

        salida.append({
            "CONTRATO": contrato,
            "TIPO_INSPECCION": tipo,
            "DESCRIPCION": descripcion,
            "UNIDAD_MEDIDA": unidad
        })

    if not salida:
        raise ValueError(
            "No se encontraron materiales completos con CONTRATO, "
            "TIPO_INSPECCION, DESCRIPCION y UNIDAD_MEDIDA."
        )

    return salida


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


def contrato_asignado_usuario():
    """Devuelve el contrato asignado en el inicio de sesión."""
    return str(st.session_state.get("contrato_usuario", "")).strip()


def usuario_tiene_todos_los_contratos():
    return normalizar(contrato_asignado_usuario()) == "TODOS"


def usuario_puede_ver_contrato(contrato):
    """Autorización central: el usuario solo accede a su contrato asignado."""
    asignado = contrato_asignado_usuario()
    if not asignado:
        return False
    if normalizar(asignado) == "TODOS":
        return True
    return normalizar(contrato) == normalizar(asignado)


def filtrar_por_contrato_asignado(registros):
    """Filtra registros de padrones por el contrato de la sesión activa."""
    if usuario_tiene_todos_los_contratos():
        return registros
    return [
        registro for registro in registros
        if usuario_puede_ver_contrato(registro.get("CONTRATO", ""))
    ]


def normalizar_encabezado(texto):
    """Normaliza encabezados y admite la escritura EQUPO usada en la hoja Material."""
    clave = normalizar(texto)
    alias = {
        "FECHAINCORPRACIONDELNUEVOPERSONAL":
            "FECHAINCORPORACIONDELNUEVOPERSONAL",
        "MATERIALEQUPOYHERRAMIENTA":
            "MATERIALEQUIPOYHERRAMIENTA"
    }
    return alias.get(clave, clave)


def guardar_registro(nombre_hoja, encabezados, datos):

    if not verificar_permiso("REGISTRAR"):
        return False, "No tienes permiso para registrar incidencias."

    if not usuario_puede_ver_contrato(datos.get("CONTRATO", "")):
        return False, (
            "Acceso denegado: no puedes registrar información de un contrato "
            "distinto al que tienes asignado."
        )

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

        # Normalizar encabezados y datos, respetando los nombres reales de la hoja.
        datos_normalizados = {
            normalizar_encabezado(k): v for k, v in datos.items()
        }

        encabezados_normalizados = [
            normalizar_encabezado(encabezado)
            for encabezado in encabezados_hoja
        ]

        # Validar que estén todos los campos esperados.
        faltantes = [
            normalizar_encabezado(campo)
            for campo in encabezados
            if normalizar_encabezado(campo) not in encabezados_normalizados
        ]

        if faltantes:

            raise ValueError(
                "Los encabezados de Google Sheets no coinciden "
                "con los campos del formulario. Revisa la primera fila."
            )

        # Construir fila respetando el orden real de la hoja.
        # En Material, UNIDAD_MEDIDA solo se escribe en su primera aparición
        # (columna F); si existe un encabezado duplicado más adelante
        # (por ejemplo, en la columna M), esa celda queda vacía.
        nueva_fila = []
        unidad_medida_escrita = False

        for encabezado in encabezados_normalizados:

            if (
                nombre_hoja == "Material"
                and encabezado == normalizar_encabezado("UNIDAD_MEDIDA")
            ):
                if unidad_medida_escrita:
                    nueva_fila.append("")
                    continue
                unidad_medida_escrita = True

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
# LOGIN Y CONTROL DE PERMISOS
# =====================================================

PERMISOS_VALIDOS = {"CREAR", "EDITAR", "REGISTRAR", "ACTUALIZAR", "TODOS"}


@st.cache_data(ttl=60)
def obtener_usuarios():
    """Lee las cuentas habilitadas desde Google Sheets."""
    credenciales = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES
    )
    cliente = gspread.authorize(credenciales)
    archivo = cliente.open_by_key(SPREADSHEET_USUARIOS_ID)

    hoja = (
        archivo.worksheet(HOJA_USUARIOS)
        if HOJA_USUARIOS
        else archivo.sheet1
    )

    registros = hoja.get_all_records()
    usuarios = {}

    for registro in registros:
        usuario = str(registro.get("USUARIO", "")).strip()
        if not usuario:
            continue

        clave = usuario.casefold()
        usuarios[clave] = {
            "USUARIO": usuario,
            "CONTRASEÑA": str(registro.get("CONTRASEÑA", "")).strip(),
            "NOMBRE": str(registro.get("NOMBRE", "")).strip(),
            "PERMISOS": str(registro.get("PERMISOS", "")).strip().upper(),
            "ACTIVO": str(registro.get("ACTIVO", "")).strip().upper(),
            "CONTRATO": str(registro.get("CONTRATO", "")).strip()
        }

    return usuarios


def permisos_de_usuario(texto):
    permisos = {
        p.strip().upper()
        for p in str(texto).replace(";", ",").split(",")
        if p.strip()
    }

    if "TODOS" in permisos:
        return {"REGISTRAR", "ACTUALIZAR"}

    # Compatibilidad con la aplicación de referencia:
    # CREAR equivale a registrar y EDITAR equivale a actualizar.
    resultado = set()
    if "CREAR" in permisos or "REGISTRAR" in permisos:
        resultado.add("REGISTRAR")
    if "EDITAR" in permisos or "ACTUALIZAR" in permisos:
        resultado.add("ACTUALIZAR")

    return resultado


def verificar_permiso(permiso):
    if not st.session_state.get("autenticado", False):
        return False

    permisos = st.session_state.get("permisos_usuario", set())
    return permiso.upper() in permisos


def cerrar_sesion():
    for clave in (
        "autenticado",
        "usuario",
        "nombre_usuario",
        "permisos_usuario",
        "contrato_usuario"
    ):
        st.session_state.pop(clave, None)


def mostrar_inicio_sesion():
    """Pantalla de acceso SIGIR: tarjeta única, compacta y centrada."""

    st.markdown(
        """
        <style>
        /* Centra verticalmente todo el contenido de la pantalla de acceso */
        section.main > div.block-container {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
            max-width: 100% !important;
        }

        /* Columna central */
        div[data-testid="stHorizontalBlock"] {
            align-items: center;
        }

        /* Tarjeta única del login */
        div[data-testid="stForm"] {
            width: 100%;
            max-width: 430px;
            margin: 0 auto;
            padding: 30px 32px 28px 32px;
            border: 1px solid rgba(148, 163, 184, .24);
            border-radius: 24px;
            background:
                radial-gradient(circle at 85% 0%, rgba(37,99,235,.20), transparent 38%),
                linear-gradient(145deg, #182235 0%, #101827 58%, #0d1522 100%);
            box-shadow: 0 24px 70px rgba(0,0,0,.42);
        }

        .sigir-login-brand {
            text-align: center;
            padding: 0 0 18px 0;
        }
        .sigir-login-icon {
            width: 62px;
            height: 62px;
            margin: 0 auto 14px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 19px;
            font-size: 30px;
            background: linear-gradient(135deg, #2563eb, #06b6d4);
            box-shadow: 0 10px 28px rgba(37,99,235,.28);
        }
        .sigir-login-brand h1 {
            margin: 0;
            color: #f8fafc;
            font-size: 32px;
            line-height: 1.15;
            font-weight: 850;
            letter-spacing: 2px;
        }
        .sigir-login-brand p {
            margin: 9px 0 0 0;
            color: #9fb2ca;
            font-size: 11px;
            line-height: 1.6;
            letter-spacing: 1.05px;
        }
        .sigir-login-welcome {
            text-align: center;
            color: #f1f5f9;
            font-size: 17px;
            font-weight: 650;
            margin: 2px 0 3px 0;
        }
        .sigir-login-help {
            text-align: center;
            color: #9aaac0;
            font-size: 12px;
            margin: 0 0 20px 0;
        }

        div[data-testid="stForm"] label {
            color: #e2e8f0;
            font-weight: 600;
        }
        div[data-testid="stForm"] input {
            min-height: 44px;
            border-radius: 11px;
            background: rgba(255,255,255,.07);
            border: 1px solid rgba(148,163,184,.18);
        }
        div[data-testid="stForm"] input:focus {
            border-color: #3b82f6;
            box-shadow: 0 0 0 1px #3b82f6;
        }
        div[data-testid="stForm"] button[kind="primaryFormSubmit"],
        div[data-testid="stForm"] button {
            min-height: 47px;
            border-radius: 12px;
            font-weight: 750;
            letter-spacing: .2px;
            background: linear-gradient(90deg, #2563eb, #0891b2);
            border: 0;
            color: white;
            transition: filter .2s ease, transform .2s ease;
        }
        div[data-testid="stForm"] button:hover {
            filter: brightness(1.12);
            transform: translateY(-1px);
        }

        /* En pantallas pequeñas, conservar el centrado sin recortar */
        @media (max-width: 640px) {
            section.main > div.block-container {
                min-height: 100svh;
                padding: 12px 10px !important;
            }
            div[data-testid="stForm"] {
                padding: 24px 18px 22px 18px;
                border-radius: 19px;
            }
            .sigir-login-brand h1 {
                font-size: 28px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    izquierda, centro, derecha = st.columns([1, 1.05, 1])
    with centro:
        with st.form("form_login_sigir"):
            st.markdown(
                """
                <div class="sigir-login-brand">
                    <div class="sigir-login-icon">📋</div>
                    <h1>SIGIR</h1>
                    <p>SISTEMA INTEGRADO DE GESTIÓN<br>
                    DE INCIDENCIAS Y RECURSOS</p>
                </div>
                <div class="sigir-login-welcome">Bienvenido</div>
                <div class="sigir-login-help">
                    Ingresa tus credenciales para continuar
                </div>
                """,
                unsafe_allow_html=True
            )

            usuario_ingresado = st.text_input(
                "Usuario",
                placeholder="Escribe tu usuario"
            ).strip()
            contrasena_ingresada = st.text_input(
                "Contraseña",
                type="password",
                placeholder="Escribe tu contraseña"
            )
            ingresar = st.form_submit_button(
                "🔐  INICIAR SESIÓN",
                use_container_width=True,
                type="primary"
            )

        if ingresar:
            if not usuario_ingresado or not contrasena_ingresada:
                st.warning("Ingresa tu usuario y contraseña.")
                return

            try:
                usuarios = obtener_usuarios()
                datos = usuarios.get(usuario_ingresado.casefold())

                if not datos:
                    st.error("Usuario o contraseña incorrectos.")
                    return

                if datos["ACTIVO"] not in (
                    "SI", "SÍ", "ACTIVO", "TRUE", "1"
                ):
                    st.error("Este usuario se encuentra inactivo.")
                    return

                if datos["CONTRASEÑA"] != contrasena_ingresada:
                    st.error("Usuario o contraseña incorrectos.")
                    return

                contrato_asignado = datos.get("CONTRATO", "").strip()
                if not contrato_asignado:
                    st.error(
                        "Tu usuario no tiene un contrato asignado. "
                        "Solicita al administrador que complete la columna CONTRATO "
                        "en la hoja de usuarios. Para el administrador general utiliza TODOS."
                    )
                    return

                permisos = permisos_de_usuario(datos["PERMISOS"])
                if not permisos:
                    st.error(
                        "El usuario no tiene permisos asignados. "
                        "Solicita al administrador que revise la hoja de usuarios."
                    )
                    return

                st.session_state["autenticado"] = True
                st.session_state["usuario"] = datos["USUARIO"]
                st.session_state["nombre_usuario"] = (
                    datos["NOMBRE"] or datos["USUARIO"]
                )
                st.session_state["permisos_usuario"] = permisos
                st.session_state["contrato_usuario"] = contrato_asignado
                st.rerun()

            except Exception as error:
                st.error(
                    "No se pudo validar el acceso. Verifica que la cuenta "
                    "de servicio tenga permiso de lectura sobre la hoja de usuarios."
                )
                st.caption(f"Detalle técnico: {error}")
# =====================================================
# ACTUALIZACIÓN DE REGISTROS YA REPORTADOS
# =====================================================

def buscar_columna(encabezados, nombre):
    """Devuelve el índice (base 1) de una columna por nombre normalizado."""
    objetivo = normalizar_encabezado(nombre)
    for indice, encabezado in enumerate(encabezados, start=1):
        if normalizar_encabezado(encabezado) == objetivo:
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
                "CONTRATO", "UUNN", "MATERIAL/EQUPO Y HERRAMIENTA",
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
        encabezados_norm = [normalizar_encabezado(x) for x in encabezados]

        idx_estado = buscar_columna(encabezados, "ESTADO") - 1
        filas_pendientes = []

        for numero_fila, fila in enumerate(valores[1:], start=2):
            estado_actual = fila[idx_estado].strip().upper() if idx_estado < len(fila) else ""
            if (
                estado_actual == "PENDIENTE"
                and usuario_puede_ver_contrato(
                    fila[buscar_columna(encabezados, "CONTRATO") - 1]
                    if buscar_columna(encabezados, "CONTRATO") - 1 < len(fila)
                    else ""
                )
            ):
                filas_pendientes.append((numero_fila, fila))

        if not filas_pendientes:
            st.success("No hay incidencias pendientes en este módulo.")
            return

        def obtener_valor_fila(fila, campo):
            clave = normalizar_encabezado(campo)
            indice = next(
                (i for i, encabezado in enumerate(encabezados_norm)
                 if encabezado == clave),
                None
            )
            if indice is None or indice >= len(fila):
                return ""
            return str(fila[indice]).strip()

        # Filtros rápidos en una sola fila.
        # Vehículos utiliza SSEE; Personal y Materiales utilizan Localidad.
        campo_tercer_filtro = "SSEE" if tipo == "Vehículo" else "LOCALIDAD"
        etiqueta_tercer_filtro = "SSEE" if tipo == "Vehículo" else "Localidad"

        contratos_filtro = sorted({
            obtener_valor_fila(fila, "CONTRATO")
            for _, fila in filas_pendientes
            if obtener_valor_fila(fila, "CONTRATO")
        })

        col_f_contrato, col_f_uunn, col_f_tercero = st.columns(3)

        with col_f_contrato:
            if usuario_tiene_todos_los_contratos():
                contrato_filtro = st.selectbox(
                    "Contrato",
                    ["Todos"] + contratos_filtro,
                    key=f"actualizar_contrato_{tipo}"
                )
            else:
                contrato_filtro = contrato_asignado_usuario()
                st.text_input(
                    "Contrato asignado",
                    value=contrato_filtro,
                    disabled=True,
                    key=f"actualizar_contrato_bloqueado_{tipo}"
                )

        filas_por_contrato = [
            (n, f) for n, f in filas_pendientes
            if contrato_filtro == "Todos"
            or obtener_valor_fila(f, "CONTRATO") == contrato_filtro
        ]

        uunn_filtro_opciones = sorted({
            obtener_valor_fila(f, "UUNN")
            for _, f in filas_por_contrato
            if obtener_valor_fila(f, "UUNN")
        })

        with col_f_uunn:
            uunn_filtro = st.selectbox(
                "UUNN",
                ["Todas"] + uunn_filtro_opciones,
                key=f"actualizar_uunn_{tipo}"
            )

        filas_por_uunn = [
            (n, f) for n, f in filas_por_contrato
            if uunn_filtro == "Todas"
            or obtener_valor_fila(f, "UUNN") == uunn_filtro
        ]

        tercer_filtro_opciones = sorted({
            obtener_valor_fila(f, campo_tercer_filtro)
            for _, f in filas_por_uunn
            if obtener_valor_fila(f, campo_tercer_filtro)
        })

        with col_f_tercero:
            tercer_filtro = st.selectbox(
                etiqueta_tercer_filtro,
                ["Todas"] + tercer_filtro_opciones,
                key=f"actualizar_tercer_filtro_{tipo}"
            )

        filas_filtradas = [
            (n, f) for n, f in filas_por_uunn
            if tercer_filtro == "Todas"
            or obtener_valor_fila(f, campo_tercer_filtro) == tercer_filtro
        ]

        if not filas_filtradas:
            st.info("No hay incidencias pendientes que coincidan con los filtros seleccionados.")
            return

        # Tabla seleccionable: haz clic en una fila para abrir su actualización.
        columnas_tabla = {
            "FILA": lambda f, n: n,
            "CONTRATO": lambda f, n: obtener_valor_fila(f, "CONTRATO"),
            "UUNN": lambda f, n: obtener_valor_fila(f, "UUNN"),
            etiqueta_tercer_filtro.upper(): lambda f, n: obtener_valor_fila(
                f, campo_tercer_filtro
            ),
            "RECURSO": lambda f, n: (
                obtener_valor_fila(f, "PERSONAL")
                or obtener_valor_fila(f, "PLACA")
                or obtener_valor_fila(f, "MATERIAL/EQUPO Y HERRAMIENTA")
            ),
            "INCIDENCIA": lambda f, n: obtener_valor_fila(f, "TIPO_INCIDENCIA"),
            "FECHA INICIO": lambda f, n: (
                obtener_valor_fila(f, cfg["inicio"])
            ),
            "ESTADO": lambda f, n: obtener_valor_fila(f, "ESTADO")
        }

        filas_tabla = [
            {
                nombre: funcion(fila, numero)
                for nombre, funcion in columnas_tabla.items()
            }
            for numero, fila in filas_filtradas
        ]

        st.markdown("**Incidencias pendientes — selecciona una fila para actualizar**")
        st.caption(
            f"Se muestran {len(filas_filtradas)} incidencias pendientes. "
            f"Puedes filtrar por contrato, UUNN y {etiqueta_tercer_filtro}."
        )

        seleccion_tabla = st.dataframe(
            pd.DataFrame(filas_tabla),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"tabla_incidencias_{tipo}"
        )

        filas_seleccionadas = seleccion_tabla.selection.rows
        if not filas_seleccionadas:
            st.info("Selecciona una fila de la tabla para cargar los datos de actualización.")
            return

        indice_seleccionado = filas_seleccionadas[0]
        numero_fila, fila_seleccionada = filas_filtradas[indice_seleccionado]
        datos_fila = {
            encabezados_norm[i]: fila_seleccionada[i] if i < len(fila_seleccionada) else ""
            for i in range(len(encabezados_norm))
        }

        st.caption(f"Registro seleccionado: fila {numero_fila} de la pestaña {cfg['hoja']}.")

        fecha_guardada = datos_fila.get(normalizar_encabezado(cfg["fecha"]), "")
        fecha_actual = convertir_fecha_existente(fecha_guardada)
        estado_actual = datos_fila.get(normalizar_encabezado("ESTADO"), "PENDIENTE").upper()
        observacion_actual = datos_fila.get(normalizar_encabezado("OBSERVACIONES"), "")

        with st.form("form_actualizar_incidencia"):
            st.markdown("**Datos de cierre de la incidencia**")
            st.caption(
                "Puedes registrar la fecha real en que ocurrió la incorporación, "
                "reparación o reposición, aunque estés actualizando el sistema días después."
            )

            # Se conserva la casilla para decidir si se guarda la fecha.
            # El calendario permanece visible y la fecha/estado comparten una fila.
            registrar_fecha = st.checkbox(
                f"Registrar {cfg['fecha_label'].lower()}",
                value=bool(fecha_guardada)
            )

            col_fecha, col_estado = st.columns([2, 1])

            with col_fecha:
                nueva_fecha = st.date_input(
                    f"{cfg['fecha_label']} (selecciona la fecha real)",
                    value=fecha_actual or datetime.now().date(),
                    format="DD/MM/YYYY",
                    help=(
                        "Selecciona la fecha efectiva del evento. "
                        "Puedes elegir una fecha pasada si la actualización se registra después. "
                        "La fecha solo se guardará si marcas la casilla."
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
                if not verificar_permiso("ACTUALIZAR"):
                    st.error("No tienes permiso para actualizar incidencias.")
                elif not usuario_puede_ver_contrato(
                    datos_fila.get(normalizar_encabezado("CONTRATO"), "")
                ):
                    st.error(
                        "Acceso denegado: el registro seleccionado no pertenece "
                        "al contrato asignado a tu usuario."
                    )
                elif nuevo_estado == "REPUESTO" and not registrar_fecha:
                    st.warning(
                        "Marca la casilla para guardar la fecha real antes de "
                        "cambiar el estado a REPUESTO."
                    )
                else:
                    try:
                        if registrar_fecha:
                            actualizar_celda(
                                hoja, encabezados, numero_fila,
                                cfg["fecha"], fecha_texto(nueva_fecha)
                            )

                        actualizar_celda(
                            hoja, encabezados, numero_fila,
                            "ESTADO", nuevo_estado
                        )

                        # Registrar automáticamente la fecha y hora de actualización.
                        # Si Material aún no tiene el encabezado, se agrega al final
                        # para no desplazar ni sobrescribir las columnas existentes.
                        encabezados_actuales = hoja.row_values(1)
                        try:
                            col_fecha_actualizacion = buscar_columna(
                                encabezados_actuales, "FECHA_ACTUALIZACION"
                            )
                        except ValueError:
                            col_fecha_actualizacion = len(encabezados_actuales) + 1
                            hoja.update_cell(
                                1,
                                col_fecha_actualizacion,
                                "FECHA_ACTUALIZACION"
                            )

                        hoja.update_cell(
                            numero_fila,
                            col_fecha_actualizacion,
                            datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        )

                        # OBSERVACIONES es opcional y no está en los encabezados
                        # definidos para Material.
                        if any(
                            normalizar_encabezado(x) == normalizar_encabezado("OBSERVACIONES")
                            for x in encabezados
                        ):
                            actualizar_celda(
                                hoja, encabezados, numero_fila,
                                "OBSERVACIONES", nuevas_observaciones.strip()
                            )

                        st.session_state["mensaje_actualizacion_sigir"] = (
                            "¡Actualización realizada correctamente! "
                            "La fecha de reposición y el estado se guardaron en Google Sheets."
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
    "LOCALIDAD",
    "UUNN",
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
    "SSEE",
    "PLACA",
    "TIPO_INCIDENCIA",
    "DESCRIPCION",
    "FECHA_REPORTE",
    "FECHA_REPOSICION",
    "ESTADO",
    "OBSERVACIONES",
    "FECHA_ACTUALIZACION"
]

HEADERS_MATERIAL = [
    "CONTRATO",
    "UUNN",
    "LOCALIDAD",
    "TIPO",
    "MATERIAL/EQUPO Y HERRAMIENTA",
    "UNIDAD_MEDIDA",
    "TIPO_INCIDENCIA",
    "CANTIDAD_FALTANTE",
    "FECHA_INICIO",
    "FECHA_REPOSICION",
    "ESTADO",
    "OBSERVACIONES"
]


# =====================================================
# CONTROL DE ACCESO: LOGIN OBLIGATORIO
# =====================================================

if not st.session_state.get("autenticado", False):
    mostrar_inicio_sesion()
    st.stop()


# =====================================================
# CABECERA Y SESIÓN ACTIVA
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

st.sidebar.markdown("### 👤 Sesión activa")
st.sidebar.write(st.session_state.get("nombre_usuario", ""))
st.sidebar.caption(
    f"Usuario: {st.session_state.get('usuario', '')}"
)
st.sidebar.caption(
    "Permisos: " + ", ".join(
        sorted(st.session_state.get("permisos_usuario", set()))
    )
)
st.sidebar.caption(
    "Contrato asignado: " + contrato_asignado_usuario()
)

if st.sidebar.button("🚪 CERRAR SESIÓN", use_container_width=True):
    cerrar_sesion()
    st.rerun()

st.sidebar.divider()


# =====================================================
# MENÚ SEGÚN PERMISOS DEL USUARIO
# =====================================================

opciones_menu = []

if verificar_permiso("REGISTRAR"):
    opciones_menu.extend([
        "👤 Personal",
        "🚗 Vehículos",
        "📦 Materiales"
    ])

if verificar_permiso("ACTUALIZAR"):
    opciones_menu.append("📝 Actualizar registros")

if not opciones_menu:
    st.error("Tu cuenta no tiene permisos para acceder a los módulos de SIGIR.")
    st.stop()

modulo = st.sidebar.radio(
    "SELECCIONAR FORMULARIO",
    opciones_menu
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
        "Selecciona al trabajador desde el padrón maestro. "
        "El contrato, la UUNN, el DNI y el cargo se completarán automáticamente."
    )

    # El formulario conserva los datos cuando hay errores de validación.
    # Solo se limpia después de guardar correctamente.
    if "personal_form_version" not in st.session_state:
        st.session_state["personal_form_version"] = 0

    personal_form_version = st.session_state["personal_form_version"]

    try:
        padron_personal = filtrar_por_contrato_asignado(
            cargar_padron_personal()
        )

        contratos_personal = sorted({
            fila["CONTRATO"] for fila in padron_personal
        })

        contrato_key = f"personal_padron_contrato_{personal_form_version}"
        contrato = st.selectbox(
            "Contrato *",
            ["Seleccione..."] + contratos_personal,
            key=contrato_key
        )

        registros_contrato = (
            [
                fila for fila in padron_personal
                if fila["CONTRATO"] == contrato
            ]
            if contrato != "Seleccione..." else []
        )

        uunn_disponibles = sorted({
            fila["UUNN"] for fila in registros_contrato
        })

        # La clave cambia al cambiar el contrato para reiniciar la selección dependiente.
        contrato_token = str(contratos_personal.index(contrato)) if contrato in contratos_personal else "ninguno"
        uunn_key = (
            f"personal_padron_uunn_{personal_form_version}_{contrato_token}"
        )

        col_uunn, col_nombre = st.columns(2)

        with col_uunn:
            uunn = st.selectbox(
                "UUNN/SSEE *",
                ["Seleccione..."] + uunn_disponibles,
                key=uunn_key,
                disabled=(contrato == "Seleccione...")
            )

        registros_uunn = (
            [
                fila for fila in registros_contrato
                if fila["UUNN"] == uunn
            ]
            if uunn != "Seleccione..." else []
        )

        # Se conservan índices para distinguir trabajadores con nombres iguales.
        indices_trabajadores = [
            i for i, fila in enumerate(padron_personal)
            if (
                fila["CONTRATO"] == contrato
                and fila["UUNN"] == uunn
            )
        ]

        uunn_token = str(uunn_disponibles.index(uunn)) if uunn in uunn_disponibles else "ninguna"
        nombre_key = (
            f"personal_padron_nombre_{personal_form_version}_"
            f"{contrato_token}_{uunn_token}"
        )

        def etiqueta_trabajador(indice):
            fila = padron_personal[indice]
            return f'{fila["APELLIDOS Y NOMBRES"]} | DNI: {fila["DNI"]}'

        with col_nombre:
            indice_personal = st.selectbox(
                "Nombre del personal *",
                [-1] + indices_trabajadores,
                format_func=lambda indice: (
                    "Seleccione un trabajador..."
                    if indice == -1 else etiqueta_trabajador(indice)
                ),
                key=nombre_key,
                disabled=(uunn == "Seleccione...")
            )

        trabajador_seleccionado = (
            padron_personal[indice_personal]
            if indice_personal != -1 else {}
        )

        if trabajador_seleccionado:
            st.caption(
                "Trabajador seleccionado desde el padrón maestro. "
                "El DNI y el cargo se completan automáticamente."
            )
        else:
            st.caption(
                "Primero selecciona el contrato, la UUNN y el trabajador."
            )

        contrato = trabajador_seleccionado.get("CONTRATO", "")
        uunn = trabajador_seleccionado.get("UUNN", "")
        personal = trabajador_seleccionado.get("APELLIDOS Y NOMBRES", "")
        localidad = trabajador_seleccionado.get("LOCALIDAD", "")
        dni = trabajador_seleccionado.get("DNI", "")
        cargo = trabajador_seleccionado.get("CARGO", "")

        # Clave individual para que DNI y cargo se actualicen al elegir otro trabajador.
        trabajador_token = (
            str(indice_personal) if indice_personal != -1 else "sin_seleccion"
        )

        with st.form(
            f"form_personal_{personal_form_version}",
            clear_on_submit=False
        ):

            col1, col2 = st.columns(2)

            with col1:

                st.text_input(
                    "Localidad *",
                    value=localidad,
                    key=(
                        f"personal_localidad_{personal_form_version}_"
                        f"{trabajador_token}"
                    ),
                    disabled=True
                )

                st.text_input(
                    "DNI",
                    value=dni,
                    key=(
                        f"personal_dni_{personal_form_version}_"
                        f"{trabajador_token}"
                    ),
                    disabled=True
                )

                fecha_salida = st.date_input(
                    "Fecha de salida *",
                    format="DD/MM/YYYY",
                    key=f"personal_fecha_salida_{personal_form_version}"
                )

                estado = st.selectbox(
                    "Estado *",
                    [
                        "PENDIENTE",
                        "REPUESTO"
                    ],
                    key=f"personal_estado_{personal_form_version}"
                )

            with col2:

                st.text_input(
                    "Cargo *",
                    value=cargo,
                    key=(
                        f"personal_cargo_{personal_form_version}_"
                        f"{trabajador_token}"
                    ),
                    disabled=True
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
                    ],
                    key=f"personal_tipo_incidencia_{personal_form_version}"
                )

                observaciones = st.text_area(
                    "Observaciones",
                    placeholder="Ingrese detalles adicionales...",
                    height=160,
                    key=f"personal_observaciones_{personal_form_version}"
                )

                # La fecha de incorporación se registra posteriormente
                # desde el módulo "Actualizar registros".
                fecha_incorporacion = None

            guardar = st.form_submit_button(
                "💾 GUARDAR REGISTRO",
                use_container_width=True
            )

            if guardar:

                if not all([
                    contrato.strip(),
                    uunn.strip(),
                    personal.strip(),
                    dni.strip(),
                    cargo.strip(),
                    localidad.strip()
                ]):

                    st.warning(
                        "Selecciona un trabajador del padrón para completar contrato, UUNN, localidad, nombre, DNI y cargo."
                    )

                elif not dni.isdigit() or len(dni) != 8:

                    st.warning(
                        "El DNI del trabajador seleccionado debe contener 8 dígitos. "
                        "Verifica el dato en el padrón maestro."
                    )

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
                        "LOCALIDAD": localidad,
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
                        st.session_state["mensaje_personal_guardado"] = (
                            "✅ " + mensaje
                        )
                        st.session_state["personal_form_version"] += 1
                        st.rerun()
                    else:
                        # No se modifica la versión del formulario:
                        # todos los datos ingresados permanecen visibles.
                        st.error(mensaje)

        if st.session_state.get("mensaje_personal_guardado"):
            st.success(st.session_state.pop("mensaje_personal_guardado"))

    except Exception as error:
        st.error(
            "No se pudo cargar el padrón maestro de personal desde Google Sheets."
        )
        st.caption(
            "Verifica que la cuenta de servicio configurada en Streamlit Secrets "
            "tenga acceso de lector al archivo y que la primera pestaña contenga "
            "las columnas CONTRATO, UUNN, APELLIDOS Y NOMBRES, DNI y CARGO."
        )
        try:
            correo_servicio = st.secrets["gcp_service_account"].get("client_email", "")
            if correo_servicio:
                st.info(
                    f"Comparte el Google Sheets con esta cuenta de servicio: "
                    f"{correo_servicio}"
                )
        except Exception:
            pass
        st.caption(f"Detalle técnico: {error}")
# =====================================================
# FORMULARIO 2: VEHÍCULOS
# =====================================================

elif modulo == "🚗 Vehículos":

    if "vehiculo_form_version" not in st.session_state:
        st.session_state["vehiculo_form_version"] = 0
    vehiculo_form_version = st.session_state["vehiculo_form_version"]

    st.subheader("🚗 Registro de incidencias de vehículos")

    st.info(
        "Selecciona el contrato, la UUNN, la SSEE y la placa del vehículo "
        "desde el padrón maestro de Google Sheets."
    )

    try:
        padron = filtrar_por_contrato_asignado(
            cargar_padron_vehiculos()
        )

        contratos_disponibles = sorted({
            fila["CONTRATO"] for fila in padron if fila["CONTRATO"]
        })

        if not contratos_disponibles:
            st.warning("El padrón no contiene contratos disponibles.")
            contratos_disponibles = []

        # Los cuatro filtros permanecen en una sola fila.
        col_contrato, col_uunn, col_ssee, col_placa = st.columns(4)

        with col_contrato:
            contrato = st.selectbox(
                "Seleccione contrato *",
                ["Seleccione..."] + contratos_disponibles,
                key=f"vehiculo_contrato_{vehiculo_form_version}"
            )

        registros_contrato = (
            [fila for fila in padron if fila["CONTRATO"] == contrato]
            if contrato != "Seleccione..." else []
        )

        uunn_disponibles = sorted({
            fila["UUNN"] for fila in registros_contrato if fila["UUNN"]
        })

        with col_uunn:
            uunn = st.selectbox(
                "Seleccione UUNN *",
                ["Seleccione..."] + uunn_disponibles,
                key=f"vehiculo_uunn_{vehiculo_form_version}",
                disabled=(contrato == "Seleccione...")
            )

        registros_unidad = (
            [fila for fila in registros_contrato if fila["UUNN"] == uunn]
            if uunn != "Seleccione..." else []
        )

        ssee_disponibles = sorted({
            fila["SSEE"] for fila in registros_unidad if fila["SSEE"]
        })

        with col_ssee:
            ssee = st.selectbox(
                "Seleccione SSEE *",
                ["Seleccione..."] + ssee_disponibles,
                key=f"vehiculo_ssee_{vehiculo_form_version}",
                disabled=(uunn == "Seleccione...")
            )

        registros_ssee = (
            [fila for fila in registros_unidad if fila["SSEE"] == ssee]
            if ssee != "Seleccione..." else []
        )

        placas_disponibles = sorted({
            fila["PLACA"] for fila in registros_ssee if fila["PLACA"]
        })

        with col_placa:
            placa = st.selectbox(
                "Seleccione placa del vehículo *",
                ["Seleccione..."] + placas_disponibles,
                key=f"vehiculo_placa_{vehiculo_form_version}",
                disabled=(ssee == "Seleccione...")
            )

        fila_vehiculo = next(
            (
                fila for fila in registros_ssee
                if fila["PLACA"] == placa
            ),
            {}
        )

        if fila_vehiculo.get("CENTRO DE COSTOS"):
            st.caption(
                f"Centro de costos asociado: {fila_vehiculo['CENTRO DE COSTOS']}"
            )

        # El formulario SIEMPRE permanece visible, incluso si aún no
        # se han seleccionado contrato, UUNN y placa.
        with st.form("form_vehiculo", clear_on_submit=False):

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
                    ],
                    key=f"vehiculo_tipo_incidencia_{vehiculo_form_version}"
                )

            with col_fecha:
                fecha_reporte = st.date_input(
                    "Fecha de reporte *",
                    format="DD/MM/YYYY",
                    key=f"vehiculo_fecha_reporte_{vehiculo_form_version}"
                )

            col_descripcion, col_estado = st.columns([2, 1])

            with col_descripcion:
                descripcion = st.text_area(
                    "Descripción de la incidencia *",
                    placeholder="Describa la falla o incidencia...",
                    height=120,
                    key=f"vehiculo_descripcion_{vehiculo_form_version}"
                )

            with col_estado:
                estado = st.selectbox(
                    "Estado *",
                    ["PENDIENTE", "REPUESTO"],
                    key=f"vehiculo_estado_{vehiculo_form_version}"
                )

            observaciones = st.text_area(
                "Observaciones",
                placeholder="Ej. Se asignó otra camioneta...",
                key=f"vehiculo_observaciones_{vehiculo_form_version}"
            )

            guardar = st.form_submit_button(
                "💾 GUARDAR REGISTRO",
                use_container_width=True
            )

            if guardar:

                if (
                    contrato == "Seleccione..."
                    or uunn == "Seleccione..."
                    or ssee == "Seleccione..."
                    or placa == "Seleccione..."
                ):
                    st.warning(
                        "Selecciona el contrato, la UUNN, la SSEE y la placa del vehículo "
                        "antes de guardar el registro."
                    )

                elif not descripcion.strip():
                    st.warning("Completa la descripción de la incidencia.")

                elif estado == "REPUESTO":
                    st.warning(
                        "Registra inicialmente la incidencia como PENDIENTE. "
                        "Cuando el vehículo vuelva al servicio, utiliza "
                        "'Actualizar registros' para registrar la fecha real."
                    )

                elif conexion_ok:

                    datos = {
                        "CONTRATO": contrato,
                        "UUNN": uunn,
                        "SSEE": ssee,
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
                        st.session_state["vehiculo_form_version"] += 1
                        st.session_state["_sigir_mensaje_guardado"] = (
                            "✅ " + mensaje +
                            " El formulario de Vehículos está listo para un nuevo registro."
                        )
                        st.rerun()
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

    if "material_form_version" not in st.session_state:
        st.session_state["material_form_version"] = 0
    material_form_version = st.session_state["material_form_version"]

    st.subheader("📦 Registro de materiales, equipos y herramientas")

    st.info(
        "Selecciona el contrato, el tipo y el material desde el padrón maestro "
        "de Google Sheets. La unidad de medida se completará automáticamente."
    )

    try:
        padron_materiales = filtrar_por_contrato_asignado(
            cargar_padron_materiales()
        )
        padron_personal_materiales = filtrar_por_contrato_asignado(
            cargar_padron_personal()
        )
        padron_ubicaciones = [
            {
                "CONTRATO": fila["CONTRATO"],
                "UUNN": fila["UUNN"],
                "LOCALIDAD": fila["LOCALIDAD"]
            }
            for fila in padron_personal_materiales
        ]

        contratos_materiales = sorted({
            fila["CONTRATO"] for fila in padron_materiales
        })

        # FILA 1: Contrato, UUNN y Localidad
        col_contrato, col_uunn, col_localidad = st.columns(3)

        with col_contrato:
            contrato = st.selectbox(
                "Contrato *",
                ["Seleccione..."] + contratos_materiales,
                key=f"material_contrato_{material_form_version}"
            )

        registros_contrato = (
            [
                fila for fila in padron_materiales
                if fila["CONTRATO"] == contrato
            ]
            if contrato != "Seleccione..." else []
        )

        ubicaciones_contrato = [
            fila for fila in padron_ubicaciones
            if fila["CONTRATO"] == contrato
        ] if contrato != "Seleccione..." else []

        uunn_disponibles_material = sorted({
            fila["UUNN"] for fila in ubicaciones_contrato if fila["UUNN"]
        })

        with col_uunn:
            uunn = st.selectbox(
                "UUNN *",
                ["Seleccione..."] + uunn_disponibles_material,
                key=f"material_uunn_{material_form_version}"
            )

        localidades_disponibles = sorted({
            fila["LOCALIDAD"]
            for fila in ubicaciones_contrato
            if fila["UUNN"] == uunn and fila["LOCALIDAD"]
        }) if uunn != "Seleccione..." else []

        uunn_token_material = (
            str(uunn_disponibles_material.index(uunn))
            if uunn in uunn_disponibles_material else "sin_uunn"
        )

        with col_localidad:
            localidad = st.selectbox(
                "Localidad *",
                ["Seleccione..."] + localidades_disponibles,
                key=f"material_localidad_{material_form_version}_{uunn_token_material}",
                disabled=(uunn == "Seleccione..." or not localidades_disponibles)
            )

        # FILA 2: Tipo, Material, Unidad de medida y Cantidad faltante
        tipos_disponibles = sorted({
            fila["TIPO_INSPECCION"] for fila in registros_contrato
        })
        opciones_tipo = ["Seleccione..."] + tipos_disponibles
        if "Otro" not in opciones_tipo and "OTRO" not in opciones_tipo:
            opciones_tipo.append("Otro")

        col_tipo, col_material, col_unidad, col_cantidad = st.columns(
            [1, 1.7, 0.8, 1]
        )

        with col_tipo:
            tipo_seleccionado = st.selectbox(
                "Tipo *",
                opciones_tipo,
                key=f"material_tipo_{material_form_version}",
                disabled=(contrato == "Seleccione...")
            )

        es_tipo_otro = tipo_seleccionado.strip().upper() == "OTRO"
        tipo = "OTRO" if es_tipo_otro else tipo_seleccionado

        registros_tipo = (
            [
                fila for fila in registros_contrato
                if fila["TIPO_INSPECCION"] == tipo_seleccionado
            ]
            if tipo_seleccionado != "Seleccione..." and not es_tipo_otro
            else []
        )

        if es_tipo_otro:
            with col_material:
                material = st.text_input(
                    "Material, equipo o herramienta *",
                    placeholder="Escribe el material o herramienta...",
                    key=f"material_descripcion_otro_{material_form_version}"
                ).strip()

            # Para un tipo libre no existe unidad asociada al padrón.
            # Se oculta el campo UNIDAD_MEDIDA y se guarda vacío.
            unidad_medida = ""

        else:
            descripciones_disponibles = sorted({
                fila["DESCRIPCION"] for fila in registros_tipo
            })

            with col_material:
                material = st.selectbox(
                    "Material, equipo o herramienta *",
                    ["Seleccione..."] + descripciones_disponibles,
                    key=f"material_descripcion_{material_form_version}",
                    disabled=(tipo_seleccionado == "Seleccione...")
                )

            registro_material = next(
                (
                    fila for fila in registros_tipo
                    if fila["DESCRIPCION"] == material
                ),
                {}
            )
            unidad_medida = registro_material.get("UNIDAD_MEDIDA", "")

            with col_unidad:
                st.text_input(
                    "UNIDAD_MEDIDA",
                    value=unidad_medida,
                    disabled=True,
                    key=f"material_unidad_medida_{material_form_version}_{normalizar_clave(material)}"
                )

        with col_cantidad:
            cantidad = st.number_input(
                "Cantidad faltante *",
                min_value=1,
                step=1,
                value=1,
                key=f"material_cantidad_{material_form_version}"
            )

        # FILA 3: Fecha de inicio, Tipo de incidencia y Estado
        col_fecha, col_incidencia, col_estado = st.columns([1, 1.3, 1])

        with col_fecha:
            fecha_inicio = st.date_input(
                "Fecha de inicio *",
                format="DD/MM/YYYY",
                key=f"material_fecha_inicio_{material_form_version}"
            )

        with col_incidencia:
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
                ],
                key=f"material_tipo_incidencia_{material_form_version}"
            )

        with col_estado:
            estado = st.selectbox(
                "Estado *",
                [
                    "PENDIENTE",
                    "REPUESTO"
                ],
                key=f"material_estado_{material_form_version}"
            )

        # FILA 4: Observaciones a todo el ancho
        observaciones = st.text_area(
            "Observaciones",
            placeholder="Ej. Se recibieron 20 unidades.",
            height=120,
            key=f"material_observaciones_{material_form_version}"
        )

        guardar = st.button(
            "💾 GUARDAR REGISTRO",
            use_container_width=True,
            key=f"guardar_material_{material_form_version}"
        )

        if guardar:

            if (
                contrato == "Seleccione..."
                or tipo_seleccionado == "Seleccione..."
                or not material
                or (not es_tipo_otro and material == "Seleccione...")
                or uunn == "Seleccione..."
                or localidad == "Seleccione..."
                or (not es_tipo_otro and not unidad_medida)
            ):
                st.warning(
                    "Selecciona el contrato, el tipo y el material del padrón de materiales, "
                    "así como la UUNN y la localidad del padrón de personal, antes de guardar."
                )

            elif estado == "REPUESTO":
                st.warning(
                    "Registra inicialmente la incidencia como PENDIENTE. "
                    "Cuando recibas el material, utiliza 'Actualizar registros' "
                    "para colocar la fecha real y cambiar el estado a REPUESTO."
                )

            elif conexion_ok:

                datos = {
                    "CONTRATO": contrato,
                    "UUNN": uunn,
                    "LOCALIDAD": localidad,
                    "TIPO": tipo,
                    "MATERIAL/EQUPO Y HERRAMIENTA": material.strip().upper(),
                    "UNIDAD_MEDIDA": unidad_medida,
                    "TIPO_INCIDENCIA": tipo_incidencia,
                    "CANTIDAD_FALTANTE": int(cantidad),
                    "FECHA_INICIO": fecha_texto(fecha_inicio),
                    "FECHA_REPOSICION": "",
                    "ESTADO": estado,
                    "OBSERVACIONES": observaciones.strip()
                }

                ok, mensaje = guardar_registro(
                    "Material",
                    HEADERS_MATERIAL,
                    datos
                )

                if ok:
                    st.session_state["material_form_version"] += 1
                    st.session_state["_sigir_mensaje_guardado"] = (
                        "✅ " + mensaje +
                        " El formulario de Materiales está listo para un nuevo registro."
                    )
                    st.rerun()
                else:
                    st.error(mensaje)

    except Exception as e:
        st.error(
            "No se pudo cargar el padrón maestro de materiales desde Google Sheets. "
            "Verifica que la cuenta de servicio de SIGIR tenga acceso al archivo."
        )
        st.caption(f"Detalle técnico: {e}")


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
