"""
chat.py
Maneja el chat conversacional del agente con contexto de bitácoras.
Lee los archivos .md relevantes y llama a Claude API para responder.
"""

import re
import threading
from pathlib import Path
from datetime import datetime, timedelta

from utils import cargar_config
from cliente_ia import get_cliente


SYSTEM_PROMPT = """Eres el asistente personal de trabajo de {nombre_usuario}. Tu rol es ayudarlo
a entender, resumir y analizar su jornada laboral con criterio profesional.

INFORMACIÓN DISPONIBLE
Tienes acceso a:
1. <bitacoras>: registro automático de las actividades de los últimos
   {dias_contexto} días, con duración, herramientas, proyectos detectados,
   notas estructuradas (@decision, @tarea, @acuerdo, etc.) y wikilinks.
2. <contexto_referencia>: archivos curados manualmente por {nombre_usuario}:
   - <objetos>: tablas, vistas y objetos del trabajo con sus descripciones.
   - <personas>: personas del entorno laboral (jefes, pares, contrapartes).
   - <diccionario_datos>: conceptos, siglas y términos del dominio.
   - <proyectos_relevantes>: descripción oficial de los proyectos que aparecen
     en las bitácoras del período.
   Usa estos archivos como fuente de verdad sobre QUÉ son los objetos, QUIÉN
   es cada persona y QUÉ significan los conceptos cuando aparezcan en las
   bitácoras.

CÓMO RESPONDER
- Responde siempre en español, de forma concisa, directa y profesional.
- Cuando menciones tiempos, sé específico: "2h 30min en SQL en Proyecto X".
- Cuando uses términos del diccionario, personas o proyectos, hazlo con
  precisión (no inventes descripciones; usa las del contexto).
- Para resúmenes, usa Markdown con secciones claras, viñetas y negritas
  donde aporten lectura rápida.
- Si la información disponible no alcanza para responder, dilo explícitamente
  en una línea — no inventes ni rellenes.
- Si {nombre_usuario} pregunta por algo que aparece en bitácoras pero no está
  en los archivos de referencia, responde con lo que ves en bitácora y
  sugiere registrarlo (@objeto, @diccionario, @persona) si parece útil.

TONO
Profesional pero cercano. Eres parte del flujo de trabajo, no un chatbot
genérico. Asume que {nombre_usuario} sabe de qué habla; no expliques lo
obvio salvo que lo pida.
"""

PROMPT_RESUMEN_DIA = """Genera un resumen ejecutivo de la jornada de hoy basado en la bitácora.
Estructura el resumen así:

## 📋 Resumen del día — {fecha}

### ⏱ Tiempo por categoría
(lista cada categoría con tiempo total)

### 🎯 Principales actividades
(lista las 3-5 actividades más relevantes)

### 📌 Notas y capturas destacadas
(si hay notas manuales o capturas, inclúyelas)

### 💡 Observaciones
(patrones, trabajo pendiente o continuidad detectada)
"""

PROMPT_RESUMEN_SEMANA = """Genera un resumen ejecutivo de la semana laboral basado en las bitácoras disponibles.
Estructura el resumen así:

## 📊 Resumen semanal — {rango_fechas}

### ⏱ Tiempo total por categoría
(lista cada categoría con tiempo total acumulado)

### 🚀 Avance por proyecto
(para cada proyecto activo, describe qué se avanzó)

### 📅 Distribución por día
(tabla resumen de actividades por día)

### 💡 Observaciones generales
(patrones de trabajo, proyectos sin actividad, recomendaciones)
"""


def _leer_bitacoras(dias: int) -> str:
    """Lee las bitácoras de los últimos N días y las concatena."""
    config = cargar_config()
    ruta_base = Path(config["ruta_base"]) / "bitacoras"

    if not ruta_base.exists():
        return "No se encontraron bitácoras."

    contenido = ""
    for i in range(dias):
        fecha = datetime.now() - timedelta(days=i)
        nombre = f"bitacora_{fecha.strftime('%Y-%m-%d')}.md"
        archivo = ruta_base / nombre
        if archivo.exists():
            contenido += f"\n\n{'='*50}\n"
            contenido += f"# Bitácora {fecha.strftime('%Y-%m-%d')}\n"
            contenido += archivo.read_text(encoding="utf-8")

    return contenido if contenido else "No se encontraron bitácoras en el período indicado."


# ===========================================================================
# Contexto de referencia: archivos editables + descripciones de proyectos
# ===========================================================================
# Adicional a las bitácoras, el chat siempre carga como contexto:
#   - bitacoras/objetos.md          (siempre, completo)
#   - bitacoras/personas.md         (siempre, completo)
#   - bitacoras/diccionario_datos.md (siempre, completo)
#   - Descripciones (config.proyectos[].palabras_clave) de los proyectos
#     que aparecen referenciados en las bitácoras del período.
# ---------------------------------------------------------------------------

# Regex para detectar wikilinks de proyecto en bitácoras:
#   🔗 **Proyecto:** [[slug|Nombre Proyecto]]
_RE_PROYECTO_EN_BITACORA = re.compile(
    r"🔗\s+\*\*Proyecto:\*\*\s+\[\[[^|\]]+\|([^\]]+)\]\]"
)


def _extraer_proyectos_mencionados(contenido_bitacoras: str) -> list:
    """
    Recorre el contenido concatenado de bitácoras y retorna la lista única
    de nombres de proyecto que aparecen referenciados.

    Mantiene el orden de primera aparición (más recientes primero, dado
    que _leer_bitacoras itera desde hoy hacia atrás).
    """
    if not contenido_bitacoras:
        return []

    nombres = []
    vistos = set()
    for m in _RE_PROYECTO_EN_BITACORA.finditer(contenido_bitacoras):
        nombre = m.group(1).strip()
        clave = nombre.lower()
        if clave and clave not in vistos:
            vistos.add(clave)
            nombres.append(nombre)
    return nombres


def _leer_archivo_referencia(ruta: Path) -> str:
    """
    Lee un archivo de referencia. Si no existe o está vacío, retorna un
    placeholder explícito para que el LLM sepa que no hay datos.
    """
    if not ruta.exists():
        return "_(sin entradas registradas aún)_"
    try:
        contenido = ruta.read_text(encoding="utf-8").strip()
    except Exception:
        return "_(error al leer archivo)_"
    return contenido if contenido else "_(sin entradas registradas aún)_"


def _construir_bloque_proyectos_relevantes(nombres_proyectos: list, config: dict) -> str:
    """
    Para cada proyecto mencionado en bitácoras, busca su descripción en
    config.proyectos[].palabras_clave y arma un bloque markdown.

    Si un proyecto está en bitácoras pero no en config (raro, pero posible),
    se omite silenciosamente.
    """
    if not nombres_proyectos:
        return "_(sin proyectos referenciados en las bitácoras del período)_"

    proyectos_config = config.get("proyectos", []) or []
    # Index por nombre case-insensitive para matching robusto
    indice = {p.get("nombre", "").strip().lower(): p for p in proyectos_config
              if p.get("nombre")}

    lineas = []
    for nombre in nombres_proyectos:
        proy = indice.get(nombre.lower())
        if not proy:
            continue
        descripcion = (proy.get("palabras_clave") or "").strip()
        estado = (proy.get("estado") or "").strip()
        lineas.append(f"## {nombre}")
        if estado:
            lineas.append(f"_Estado: {estado}_")
        lineas.append("")
        if descripcion:
            lineas.append(descripcion)
        else:
            lineas.append("_(sin descripción registrada en config)_")
        lineas.append("")

    if not lineas:
        return "_(proyectos mencionados sin descripción en config)_"

    return "\n".join(lineas).rstrip()


def _construir_contexto_referencia(contenido_bitacoras: str) -> str:
    """
    Construye el bloque <contexto_referencia> con:
      - objetos.md, personas.md, diccionario_datos.md (siempre completos)
      - Descripciones de proyectos mencionados en las bitácoras del período

    Retorna un string XML-like con secciones etiquetadas para que el LLM
    diferencie cada bloque.
    """
    config = cargar_config()
    ruta_base = Path(config["ruta_base"]) / "bitacoras"

    objetos = _leer_archivo_referencia(ruta_base / "objetos.md")
    personas = _leer_archivo_referencia(ruta_base / "personas.md")
    diccionario = _leer_archivo_referencia(ruta_base / "diccionario_datos.md")

    nombres_proyectos = _extraer_proyectos_mencionados(contenido_bitacoras)
    bloque_proyectos = _construir_bloque_proyectos_relevantes(
        nombres_proyectos, config
    )

    bloque = (
        "<contexto_referencia>\n"
        "<objetos>\n"
        f"{objetos}\n"
        "</objetos>\n\n"
        "<personas>\n"
        f"{personas}\n"
        "</personas>\n\n"
        "<diccionario_datos>\n"
        f"{diccionario}\n"
        "</diccionario_datos>\n\n"
        "<proyectos_relevantes>\n"
        f"{bloque_proyectos}\n"
        "</proyectos_relevantes>\n"
        "</contexto_referencia>"
    )

    # Log informativo (útil para depurar y verificar que se está cargando bien)
    n_proy = len(nombres_proyectos)
    print(
        f"[Chat] Contexto referencia: objetos + personas + diccionario "
        f"+ {n_proy} proyecto(s) ({', '.join(nombres_proyectos) if nombres_proyectos else '—'})"
    )

    return bloque


def _guardar_resumen_en_bitacora(resumen: str):
    """Agrega el resumen generado al final de la bitácora del día."""
    config = cargar_config()
    ruta_base = Path(config["ruta_base"]) / "bitacoras"
    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo = ruta_base / f"bitacora_{fecha}.md"

    if archivo.exists():
        with open(archivo, "a", encoding="utf-8") as f:
            f.write(f"\n\n---\n\n{resumen}\n")
        return True
    return False


class GestorChat:
    """
    Maneja el ciclo de conversación con contexto de bitácoras.
    Mantiene historial de mensajes para conversación multi-turno.
    """

    def __init__(self):
        self.config = cargar_config()
        self.historial = []  # Lista de {role, content}
        self.dias_contexto = self.config.get("dias_contexto_chat", 7)

    def recargar_config(self):
        """
        Recarga la configuración desde config.json.
        Útil para aplicar cambios en caliente sin reiniciar el agente.
        """
        self.config = cargar_config()
        self.dias_contexto = self.config.get("dias_contexto_chat", 7)
        prompt_custom = bool((self.config.get("system_prompt") or "").strip())
        origen_prompt = "personalizado" if prompt_custom else "default"
        print(
            f"[Chat] Config recargada — días contexto: {self.dias_contexto}, "
            f"system_prompt: {origen_prompt}"
        )

    def _construir_system(self) -> str:
        """
        Construye el system prompt que se envía al LLM.

        Resolución del prompt:
          1. Si config["system_prompt"] tiene contenido (no vacío después de
             strip), se usa ese como plantilla.
          2. Si está vacío o ausente, se usa SYSTEM_PROMPT (default del módulo).

        En ambos casos se aplica .format() para sustituir las variables
        {nombre_usuario} y {dias_contexto}. Si la plantilla del usuario
        contiene llaves mal puestas y .format() falla, se cae al default
        formateado y se loguea el error en consola para diagnóstico.

        Variables disponibles en la plantilla:
          - {nombre_usuario}: campo "nombre_usuario" del config
          - {dias_contexto}: días configurados para contexto del chat
        """
        nombre = self.config.get("nombre_usuario", "Usuario")
        dias = self.dias_contexto

        plantilla_usuario = (self.config.get("system_prompt") or "").strip()
        plantilla = plantilla_usuario if plantilla_usuario else SYSTEM_PROMPT

        try:
            return plantilla.format(
                nombre_usuario=nombre,
                dias_contexto=dias,
            )
        except (KeyError, IndexError, ValueError) as e:
            # Plantilla del usuario tiene llaves mal puestas o variables no
            # soportadas. Avisamos en consola y caemos al default.
            if plantilla_usuario:
                print(
                    f"[Chat] ⚠ Error formateando system_prompt personalizado "
                    f"({type(e).__name__}: {e}). Usando default."
                )
                try:
                    return SYSTEM_PROMPT.format(
                        nombre_usuario=nombre,
                        dias_contexto=dias,
                    )
                except Exception as e_default:
                    # Caso extremo: hasta el default falla (no debería pasar)
                    print(f"[Chat] ⚠ Default tampoco se pudo formatear: {e_default}")
                    return SYSTEM_PROMPT
            # Si era el default el que falló (caso extremo), retornamos sin formato
            print(f"[Chat] ⚠ SYSTEM_PROMPT default falló al formatear: {e}")
            return SYSTEM_PROMPT

    def _construir_contexto_bitacoras(self) -> str:
        """
        Retorna el bloque completo de contexto que se envía al LLM:
        archivos de referencia + bitácoras del período.

        El bloque de referencia (objetos, personas, diccionario, proyectos)
        se calcula a partir del contenido de las bitácoras leídas, para
        filtrar solo los proyectos efectivamente mencionados.
        """
        contenido_bitacoras = _leer_bitacoras(self.dias_contexto)
        bloque_referencia = _construir_contexto_referencia(contenido_bitacoras)

        return (
            f"{bloque_referencia}\n\n"
            f"<bitacoras>\n"
            f"{contenido_bitacoras}\n"
            f"</bitacoras>"
        )

    def responder(self, pregunta: str, callback_respuesta) -> None:
        """
        Responde una pregunta usando el contexto de bitácoras + archivos
        de referencia. Llama a callback_respuesta(texto, error) cuando termina.
        Corre en hilo separado para no bloquear la UI.

        Refresco de contexto: el contexto se vuelve a leer en CADA turno
        para que el LLM siempre vea la versión más reciente de las
        bitácoras y archivos de referencia. El contexto se inyecta antes
        de la pregunta solo en el envío al LLM; el historial guarda la
        pregunta limpia para no acumular bitácoras viejas.
        """
        def _worker():
            try:
                contexto = self._construir_contexto_bitacoras()

                # 1. Construir el mensaje que se ENVÍA al LLM en este turno
                #    (con contexto fresco antepuesto a la pregunta).
                mensaje_envio = f"{contexto}\n\nPregunta: {pregunta}"

                # 2. El historial guarda la pregunta LIMPIA (sin contexto)
                #    para que las preguntas previas no carguen bitácoras
                #    viejas. El refresco se hace en cada turno con (1).
                mensajes_envio = list(self.historial)  # copia
                mensajes_envio.append({
                    "role": "user",
                    "content": mensaje_envio
                })

                cliente = get_cliente()
                texto = cliente.chat(
                    system=self._construir_system(),
                    mensajes=mensajes_envio,
                    max_tokens=1000
                )

                # 3. Guardar en el historial la pregunta LIMPIA + respuesta,
                #    no el mensaje con contexto.
                self.historial.append({
                    "role": "user",
                    "content": pregunta
                })
                self.historial.append({
                    "role": "assistant",
                    "content": texto
                })

                callback_respuesta(texto, None)

            except Exception as e:
                callback_respuesta(None, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def generar_resumen_dia(self, callback_respuesta) -> None:
        """
        Genera resumen del día y lo guarda en la bitácora.
        Llama a callback_respuesta(texto, error) cuando termina.

        Incluye archivos de referencia (objetos, personas, diccionario)
        + descripción del/los proyecto(s) detectados en la bitácora del día.
        """
        def _worker():
            try:
                fecha = datetime.now().strftime("%d de %B de %Y")
                prompt = PROMPT_RESUMEN_DIA.format(fecha=fecha)

                # Leer solo bitácora de hoy para el resumen
                contenido_bitacoras = _leer_bitacoras(1)

                # Bloque de referencia (incluye proyectos del día)
                bloque_referencia = _construir_contexto_referencia(contenido_bitacoras)

                mensaje = (
                    f"{bloque_referencia}\n\n"
                    f"<bitacoras>\n{contenido_bitacoras}\n</bitacoras>\n\n"
                    f"{prompt}"
                )

                cliente = get_cliente()
                resumen = cliente.chat(
                    system=self._construir_system(),
                    mensajes=[{"role": "user", "content": mensaje}],
                    max_tokens=1500
                )

                # Guardar en bitácora del día
                _guardar_resumen_en_bitacora(resumen)

                # Agregar al historial del chat
                self.historial.append({"role": "user", "content": "Genera resumen del día"})
                self.historial.append({"role": "assistant", "content": resumen})

                callback_respuesta(resumen, None)

            except Exception as e:
                callback_respuesta(None, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def generar_resumen_semana(self, callback_respuesta) -> None:
        """
        Genera resumen semanal y lo guarda en la bitácora del día.
        Llama a callback_respuesta(texto, error) cuando termina.

        Incluye archivos de referencia (objetos, personas, diccionario)
        + descripción de los proyectos detectados en la semana.
        """
        def _worker():
            try:
                hoy = datetime.now()
                inicio = (hoy - timedelta(days=6)).strftime("%d/%m")
                fin = hoy.strftime("%d/%m/%Y")
                rango = f"{inicio} al {fin}"

                prompt = PROMPT_RESUMEN_SEMANA.format(rango_fechas=rango)
                contenido_bitacoras = _leer_bitacoras(7)

                # Bloque de referencia (incluye proyectos de la semana)
                bloque_referencia = _construir_contexto_referencia(contenido_bitacoras)

                mensaje = (
                    f"{bloque_referencia}\n\n"
                    f"<bitacoras>\n{contenido_bitacoras}\n</bitacoras>\n\n"
                    f"{prompt}"
                )

                cliente = get_cliente()
                resumen = cliente.chat(
                    system=self._construir_system(),
                    mensajes=[{"role": "user", "content": mensaje}],
                    max_tokens=2000
                )
                _guardar_resumen_en_bitacora(resumen)

                self.historial.append({"role": "user", "content": "Genera resumen de la semana"})
                self.historial.append({"role": "assistant", "content": resumen})

                callback_respuesta(resumen, None)

            except Exception as e:
                callback_respuesta(None, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def limpiar_historial(self):
        """Resetea el historial de conversación."""
        self.historial = []
