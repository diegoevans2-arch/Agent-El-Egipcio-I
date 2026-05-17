# 📖 Manual de Funcionamiento — El Egypcio

> Agente LLM de documentación automática de jornada laboral para Obsidian.
> Versión: 2.0 · Plataforma: Windows 10/11 · Python 3.10+

---

## Tabla de contenidos

1. [Requisitos del sistema](#1-requisitos-del-sistema)
2. [Instalación](#2-instalación)
3. [Configuración inicial](#3-configuración-inicial)
4. [Inicio del agente](#4-inicio-del-agente)
5. [Interfaz principal](#5-interfaz-principal)
6. [Detección automática de actividad](#6-detección-automática-de-actividad)
7. [Notas manuales y prefijos estructurados](#7-notas-manuales-y-prefijos-estructurados)
8. [Capturas manuales](#8-capturas-manuales)
9. [Gestión de proyectos](#9-gestión-de-proyectos)
10. [Gantt de proyectos](#10-gantt-de-proyectos)
11. [Chat conversacional](#11-chat-conversacional)
12. [Archivos de referencia y archivos agregados de task](#12-archivos-de-referencia-y-archivos-agregados-de-task)
13. [Snippets de código](#13-snippets-de-código)
14. [FinOps — Monitor de gasto de API](#14-finops--monitor-de-gasto-de-api)
15. [Temas visuales (skins)](#15-temas-visuales-skins)
16. [Configuraciones](#16-configuraciones)
17. [Estructura de archivos generados](#17-estructura-de-archivos-generados)
18. [Solución de problemas](#18-solución-de-problemas)

---

## 1. Requisitos del sistema

### Hardware

- Sistema operativo: **Windows 10 o 11**
- Al menos un monitor conectado (soporta multi-monitor)
- Conexión a internet (para las APIs de IA)

### Software

- **Python 3.10** o superior
- **Obsidian** instalado (para visualizar las bitácoras, gantts y grafo)
- Una **API key** de al menos uno de los proveedores soportados:
  - Claude (Anthropic): https://console.anthropic.com/
  - OpenAI (ChatGPT): https://platform.openai.com/
  - Gemini (Google): https://aistudio.google.com/

### Dependencias Python

Instalación completa (los tres proveedores):

```bash
pip install PyQt5 Pillow mss pywin32 psutil anthropic openai google-generativeai
```

Instalación mínima según proveedor:

```bash
# Solo Claude
pip install PyQt5 Pillow mss pywin32 psutil anthropic

# Solo OpenAI
pip install PyQt5 Pillow mss pywin32 psutil openai

# Solo Gemini
pip install PyQt5 Pillow mss pywin32 psutil google-generativeai
```

| Librería | Función |
|---|---|
| PyQt5 | Interfaz gráfica del agente |
| Pillow | Procesamiento de capturas de pantalla |
| mss | Captura multi-monitor |
| pywin32 | Detección de ventana activa (win32gui, win32process) |
| psutil | Identificación de procesos del sistema |
| anthropic / openai / google-generativeai | SDK del proveedor de IA elegido |

---

## 2. Instalación

1. **Clonar o descargar** el repositorio:

```bash
git clone https://github.com/TU_USUARIO/el-egypcio.git
cd el-egypcio
```

2. **Instalar dependencias**:

```bash
pip install -r requirements.txt
```

3. **Configurar** `config.json` (ver sección siguiente).

4. **Crear la carpeta `assets/`** con los iconos de la aplicación (opcional):
   - `assets/agente.ico` → icono de la barra de tareas de Windows
   - `assets/ventana.ico` → icono de la ventana, popups y system tray

   Si no están presentes, el agente arranca igualmente con iconos por defecto.

---

## 3. Configuración inicial

El archivo `config.json` es el centro de configuración del agente. Al clonar el repositorio viene vacío y listo para completar. Los campos mínimos que debes configurar antes del primer uso:

### Campos obligatorios

| Campo | Qué poner |
|---|---|
| `nombre_usuario` | Tu nombre (aparece en el prompt del chat y en las bitácoras) |
| `ruta_base` | Ruta absoluta a tu vault de Obsidian. Ejemplo: `"C:/Users/TuNombre/MiVault"`. Si lo dejas vacío, usa la carpeta del agente |

### API keys

Las API keys se configuran desde el popup de login al iniciar el agente, o directamente en `config.json`:

```json
"ia_api_keys": {
    "claude": "sk-ant-...",
    "openai": "sk-...",
    "gemini": "AIza..."
}
```

Solo necesitas la key del proveedor que vayas a usar.

### Campos opcionales recomendados

| Campo | Descripción | Default |
|---|---|---|
| `personas_conocidas` | Lista de personas de tu entorno laboral para wikilinks automáticos | `[]` |
| `palabras_clave_laborales_browser` | Keywords que identifican contenido laboral en el browser | Ver defaults en config |
| `dominios_laborales` | Dominios cuyas URLs serán registradas en las bitácoras | Ver defaults en config |
| `dias_contexto_chat` | Cuántos días de bitácoras inyectar como contexto al chat | `7` |

---

## 4. Inicio del agente

```bash
python agente.py
```

### Flujo de arranque

1. **Migración automática**: si tu `config.json` tiene el formato antiguo (una sola API key), se migra automáticamente al formato multi-proveedor.

2. **Popup de login**: aparece una ventana donde seleccionas el proveedor de IA, ingresas (o confirmas) tu API key, y presionas **Conectar**. El agente valida la key haciendo un mini-llamado a la API.

3. **Verificación de ruta base**: si la ruta configurada no existe, el agente muestra un error y se detiene.

4. **Ventana principal**: si todo está correcto, se abre la interfaz del agente y comienza la detección automática de actividad.

5. **Alertas de inactividad**: al iniciar, el agente revisa si hay proyectos activos sin actividad en los últimos N días y muestra las alertas en el chat.

### Detener el agente

- Desde el **system tray** (icono en la barra de tareas): clic derecho → "Cerrar agente"
- Desde la terminal: `Ctrl+C`

Al cerrar, el agente guarda la bitácora del día con frontmatter YAML calculado y cierra limpiamente el monitor de ventanas.

---

## 5. Interfaz principal

La ventana del agente tiene las siguientes secciones, de arriba a abajo:

### Barra superior

| Elemento | Función |
|---|---|
| 🟢 Estado | Indica si el agente está activo, pausado o con error |
| Hora | Reloj actualizado cada segundo |
| 📌 Anclar | Mantiene la ventana siempre visible (always on top) |
| 🖥 Monitor | Selecciona qué monitor físico capturar (1, 2, ... o todos) |
| ⚙ Configuraciones | Abre el popup de configuraciones completas |

### Panel de actividad actual

Muestra la ventana activa detectada, la categoría asignada por el LLM (SQL, Python, Dashboard, Reunión, etc.) y el tiempo acumulado en esa ventana.

### Registro de hoy

Log scrolleable con todas las actividades detectadas durante el día, en orden cronológico. Este panel es redimensionable arrastrando su borde inferior.

### Campo de notas rápidas

Permite agregar notas a la actividad actual. Soporta prefijos estructurados con autocompletado al escribir `@` (ver sección 7).

### Botones de acción

| Botón | Función |
|---|---|
| 📷 Capturar | Toma una captura manual con opción de agregar nota |
| ⏸ Pausar / ▶ Reanudar | Pausa o reanuda la detección automática |
| 📋 Bitácora | Abre la bitácora del día en Obsidian |
| 📊 Gantt | Abre el diagrama Gantt global en Obsidian |
| 🗂 Gestionar proyectos | Abre el popup de gestión de proyectos |

### Chat conversacional

Se expande al presionar **💬 Consultar al agente**. Incluye campo de entrada, historial, y botones rápidos para resúmenes del día y la semana (ver sección 11).

### System tray

Al minimizar, el agente se oculta en la barra de tareas de Windows. Desde el icono del tray puedes restaurar la ventana o cerrar el agente.

---

## 6. Detección automática de actividad

El agente monitorea tu pantalla cada segundo usando un sistema híbrido:

### ¿Cómo detecta qué estás haciendo?

1. **Obtiene la ventana activa** usando `win32gui` y el proceso asociado con `psutil`.

2. **Clasifica la ventana** con lógica híbrida:
   - **Apps de escritorio** (DBeaver, Excel, VS Code, etc.): se compara el nombre del proceso `.exe` contra la `lista_blanca_procesos`.
   - **Browsers y apps UWP** (Chrome, Edge, Teams nuevo, etc.): se revisa el título de la ventana contra las `palabras_clave_laborales_browser` y `keywords_bloqueadas_browser`.
   - **Lista negra**: procesos en `lista_negra_procesos` siempre se ignoran (Spotify, WhatsApp, etc.).

3. **Espera estabilidad**: la ventana debe mantenerse activa durante N segundos continuos (configurable en `captura.estabilidad_segundos`, default: 5) antes de disparar una captura. Esto evita registrar cambios fugaces de ventana.

4. **Filtro de monitor**: si tienes multi-monitor configurado, solo registra ventanas cuyo centro esté en el monitor seleccionado.

5. **Toma screenshot**: captura la pantalla y la envía al LLM con visión para que describa la actividad.

6. **Escribe en la bitácora**: genera una entrada Markdown con la descripción, categoría, herramienta, duración, wikilinks automáticos y URLs laborales detectadas.

### Modo reunión

Si el título de la ventana contiene alguna de las `palabras_clave_reunion` (teams, zoom, meet, etc.), el agente entra en modo reunión: toma recapturas periódicas (configurable en `captura.intervalo_reunion_segundos`, default: 120) para detectar si se está proyectando contenido.

---

## 7. Notas manuales y prefijos estructurados

Desde el campo de notas rápidas puedes escribir texto libre que se agrega a la entrada actual en la bitácora. Si usas un prefijo `@`, la nota se clasifica automáticamente:

| Prefijo | Tipo de nota | Ejemplo | Archivo agregado |
|---|---|---|---|
| `@decision:` | Decisión tomada | `@decision: Usaremos la vista materializada` | `decisiones.md` |
| `@tarea:` | Tarea pendiente | `@tarea: Agregar filtro por sede al reporte` | `tareas.md` |
| `@acuerdo:` | Acuerdo de reunión | `@acuerdo: Entrega del dashboard el viernes` | `acuerdos.md` |
| `@idea:` | Idea o propuesta | `@idea: Automatizar la carga diaria con un cron` | `ideas.md` |
| `@bloqueado:` | Bloqueo o impedimento | `@bloqueado: Falta acceso a la tabla de docentes` | `bloqueados.md` |
| `@ticket:` | Referencia a ticket | `@ticket: JIRA-1234 — ajustar campo de fecha` | `tickets.md` |
| `@pendiente:` | Recordatorio | `@pendiente: Revisar query con el equipo` | `pendientes.md` |
| `@objeto:` | Registra un objeto de trabajo | `@objeto: vw_matriculas - vista de matrículas` | `objetos.md` (upsert) |
| `@diccionario:` | Registra un concepto | `@diccionario: SIES - Sistema de Información` | `diccionario_datos.md` (upsert) |
| `@persona:` | Registra una persona | `@persona: María López - líder funcional` | `personas.md` (upsert) |

### Archivos agregados por tipo de task

Cada vez que escribes una nota con uno de los prefijos de los 7 primeros tipos (`@decision`, `@tarea`, `@acuerdo`, `@idea`, `@bloqueado`, `@ticket`, `@pendiente`), además de aparecer en la bitácora del día, la entrada se acumula en el archivo agregado correspondiente.

Estos archivos tienen formato **cronológico por día**:

```markdown
---
tipo: registro-tareas
ultima_actualizacion: 2026-05-16
tags: [registro, tarea]
---

# ⏳ Tareas

> Registro cronológico de tareas detectadas en bitácoras.

---

## 2026-05-16
- ⏳ revisar query Maestro Mallas — [[bitacora_2026-05-16]]
- ⏳ subir reporte a SharePoint — [[bitacora_2026-05-16]]

## 2026-05-15
- ⏳ validar datos con Pablo — [[bitacora_2026-05-15]]
```

El día más reciente queda arriba (orden cronológico inverso). Cada entrada incluye un wikilink a la bitácora donde fue registrada. **No hay upsert**: cada `@tarea` que escribes es una entrada nueva, aunque el texto sea similar a una previa.

### Archivos de referencia (upsert)

Los prefijos `@objeto:`, `@diccionario:` y `@persona:` escriben en archivos de referencia con upsert por nombre: si registras el mismo objeto con descripción nueva, se actualiza, no se duplica. Ver sección 12.

El autocompletado se activa al escribir `@` en el campo de notas.

---

## 8. Capturas manuales

El botón **📷 Capturar** toma una captura de pantalla inmediata, independiente del ciclo automático. El flujo es:

1. Se toma el screenshot y se guarda en alta calidad (PNG) en `bitacoras/imagenes/`.
2. Aparece un popup donde puedes agregar una nota descriptiva (opcional).
3. El screenshot se envía al LLM para análisis (en un hilo separado, sin bloquear la UI).
4. Se escribe la entrada en la bitácora con un wikilink a la imagen (`![[imagenes/captura_YYYY-MM-DD_HH-MM-SS.png]]`).

Las capturas manuales son útiles para documentar estados puntuales que el ciclo automático podría no captar.

---

## 9. Gestión de proyectos

Desde el botón **🗂 Gestionar proyectos** se abre un popup donde puedes:

### Crear proyecto

- **Nombre**: nombre del proyecto (se usa como identificador).
- **Descripción**: palabras clave y descripción que el LLM usa para clasificar actividades automáticamente. Mientras más descriptiva, mejor la clasificación.

### Editar proyecto

Modifica el nombre, la descripción o el estado de un proyecto existente.

### Cerrar proyecto

Cambia el estado a "cerrado" y registra la fecha de cierre automáticamente. Los proyectos cerrados aparecen atenuados en la lista con un ícono 🔒.

### Reactivar proyecto

Un proyecto cerrado puede volver a estado "activo". Al reactivar, la fecha de cierre se limpia.

### Abrir en Obsidian

Cada proyecto tiene un botón para abrir su archivo `.md` directamente en Obsidian.

### Migrar bitácoras antiguas

El botón **🔁 Migrar bitácoras antiguas** procesa todas las bitácoras existentes, clasifica cada entrada contra los proyectos activos usando el LLM, y reconstruye los archivos `.md` de proyectos y el Gantt desde cero. Útil cuando defines proyectos después de haber acumulado bitácoras.

---

## 10. Gantt de proyectos

Cada vez que una entrada tiene más de 2 minutos de duración, un modelo rápido del LLM la clasifica automáticamente contra los proyectos activos.

### Gantt global

El archivo `bitacoras/gantt_proyectos.md` contiene un diagrama Mermaid con todos los proyectos, sus rangos de actividad y el tiempo acumulado. Se regenera automáticamente tras cada entrada clasificada.

### Gantt individual

Cada proyecto tiene su propio diagrama Mermaid dentro de su archivo `.md` en `bitacoras/proyectos/`.

### Alertas de inactividad

Al iniciar el agente, se revisa si hay proyectos activos sin actividad en los últimos N días (configurable en `alertas.inactividad_dias`, default: 3). Las alertas aparecen en el chat automáticamente.

---

## 11. Chat conversacional

El chat integrado permite hacerle preguntas al agente sobre tu jornada laboral. El LLM recibe como contexto:

- Las bitácoras de los últimos N días (configurable en `dias_contexto_chat`).
- Los archivos de referencia: `objetos.md`, `personas.md`, `diccionario_datos.md`.
- Las descripciones de los proyectos mencionados en las bitácoras del período.
- **Carga condicional de archivos agregados de task** según keywords de la pregunta (ver más abajo).

### Carga condicional de archivos de task

Si tu pregunta menciona keywords relacionadas con un tipo de task, el agente carga ese archivo completo como contexto adicional. Esto optimiza tokens: solo se trae lo necesario.

| Pregunta | Archivo cargado |
|---|---|
| "¿qué pendientes tengo?" | `pendientes.md` |
| "muéstrame las tareas" | `tareas.md` |
| "¿qué decidí esta semana?" | `decisiones.md` |
| "ideas y acuerdos" | `ideas.md` + `acuerdos.md` |
| "¿hay algún bloqueo?" | `bloqueados.md` |
| "revisemos los tickets" | `tickets.md` |
| "resúmeme el día" | Ninguno (solo bitácoras + referencias estáticas) |

El matching es tolerante a tildes y mayúsculas. Usa word-boundaries para no confundir palabras parecidas (por ejemplo, "ideal" no activa "idea"). Los **resúmenes diarios y semanales** nunca activan carga condicional (no aplica ahí).

### Ejemplos de preguntas

- "¿Cuánto tiempo dediqué a SQL esta semana?"
- "Resúmeme la reunión del martes"
- "¿En qué proyectos trabajé ayer?"
- "¿Qué decisiones tomé esta semana?"

### Botones rápidos

| Botón | Función |
|---|---|
| 📋 Resumen hoy | Genera un resumen ejecutivo del día con tiempo por categoría, actividades principales y observaciones |
| 📊 Resumen semana | Genera un resumen semanal con avance por proyecto y distribución por día |
| 🗑 Limpiar | Limpia el historial de la conversación actual |

Los resúmenes generados se guardan automáticamente en la bitácora del día.

### Contexto fresco

El contexto (bitácoras + archivos de referencia + archivos de task si aplica) se relee en cada turno de conversación, así el LLM siempre ve la versión más actualizada. El historial de chat guarda solo las preguntas limpias (sin el contexto), evitando acumular bitácoras viejas.

### System prompt personalizable

El prompt del sistema se puede editar desde Configuraciones. Soporta las variables `{nombre_usuario}` y `{dias_contexto}` que se sustituyen automáticamente. Si se deja vacío, se usa el prompt por defecto.

---

## 12. Archivos de referencia y archivos agregados de task

El agente mantiene **dos tipos** de archivos derivados de tus notas estructuradas, con comportamiento distinto.

### 12.1 Archivos de referencia (upsert por nombre)

Archivos curados manualmente que el agente usa como fuente de verdad. Se crean y actualizan usando los prefijos `@objeto:`, `@diccionario:` y `@persona:` desde el campo de notas.

| Archivo | Prefijo | Contenido |
|---|---|---|
| `bitacoras/objetos.md` | `@objeto:` | Tablas, vistas, archivos y objetos del trabajo |
| `bitacoras/diccionario_datos.md` | `@diccionario:` | Conceptos, siglas y términos del dominio |
| `bitacoras/personas.md` | `@persona:` | Personas del entorno laboral |

**Comportamiento de upsert**:
- Si el nombre **no existe** → se agrega como nueva entrada.
- Si ya **existe con nueva descripción** → se actualiza.
- Si ya **existe sin descripción nueva** → se preserva sin cambios.

Las entradas se ordenan alfabéticamente dentro de cada archivo. Estos archivos se cargan **siempre** como contexto del chat.

### 12.2 Archivos agregados de task (cronológicos, sin upsert)

Archivos que acumulan cronológicamente todas las notas con prefijos de task. Una nueva entrada nunca reemplaza una previa, se suma como línea independiente.

| Archivo | Prefijo |
|---|---|
| `bitacoras/decisiones.md` | `@decision:` |
| `bitacoras/tareas.md` | `@tarea:` |
| `bitacoras/acuerdos.md` | `@acuerdo:` |
| `bitacoras/ideas.md` | `@idea:` |
| `bitacoras/bloqueados.md` | `@bloqueado:` |
| `bitacoras/tickets.md` | `@ticket:` |
| `bitacoras/pendientes.md` | `@pendiente:` |

**Formato**:

```markdown
---
tipo: registro-decisiones
ultima_actualizacion: 2026-05-16
tags: [registro, decision]
---

# ✅ Decisiones

> Registro cronológico de decisiones detectadas en bitácoras.

---

## 2026-05-16
- ✅ Usar Banner9 como fuente principal — [[bitacora_2026-05-16]]
- ✅ Migrar reportes a Power BI — [[bitacora_2026-05-16]]

## 2026-05-15
- ✅ Cambiar arquitectura del Maestro — [[bitacora_2026-05-15]]
```

- El día más reciente queda **arriba** (orden cronológico inverso).
- Dentro de cada día las entradas van en orden de inserción.
- Cada entrada tiene un wikilink a la bitácora origen.
- **No hay upsert**: registros con texto similar se acumulan, no se deduplican.

Estos archivos se cargan en el chat **solo cuando la pregunta del usuario los menciona por keyword** (ver sección 11).

---

## 13. Snippets de código

Cuando escribes una nota que contiene código (mínimo 2 líneas), el agente detecta automáticamente el lenguaje y extrae el código a un archivo separado.

### Lenguajes soportados

SQL, Python, Bash, JavaScript, JSON y YAML.

### ¿Qué genera?

- Un archivo `.md` en `bitacoras/snippets/` con frontmatter (fecha, lenguaje, proyecto, fuentes, personas).
- Un wikilink en la bitácora del día apuntando al snippet.
- Un wikilink en el MOC del proyecto (si la actividad se clasificó en un proyecto).

### ¿Cuándo NO se extrae?

- Si la nota tiene solo 1 línea.
- Si el texto ya empieza con triple backtick (el usuario formateó manualmente).

---

## 14. FinOps — Monitor de gasto de API

El módulo **FinOps** está integrado en el popup de Configuraciones. Muestra el consumo de tokens y costo USD acumulado por cada llamada al LLM, separado por tipo de operación.

### ¿Qué se muestra?

- **Tarjetas Hoy / Este mes** con costo USD, número de llamadas y tokens totales.
- **Desglose por tipo de operación** con barras de porcentaje:
  - 📸 Captura actividad (análisis de ventana activa con Vision)
  - 🎥 Captura reunión (análisis durante modo reunión)
  - 🎯 Clasificación de proyecto (modelo rápido del LLM)
  - 💬 Chat usuario (preguntas al chat)
  - 📋 Resumen día / Resumen semana (botones rápidos del chat)
- **Modelo activo** y precios por millón de tokens (input/output).
- **Fecha de última actualización** de los precios hardcoded.
- **Gráfico de 5 días** para ver tendencia.

### ¿Cómo se calcula?

Cada llamada al LLM se intercepta en `cliente_ia.py` y se registra automáticamente:
1. Se extraen los tokens de input/output del response de la API.
2. Se calcula el costo según el modelo usado y los precios configurados.
3. Se persiste **agregado por día** en `bitacoras/finops_data.json` (no se guarda cada llamada individual; solo el total diario por tipo).

### Override de precios

Los precios vienen hardcoded en `finops.py` con la última actualización al momento de la versión. Si los precios cambian, puedes overridearlos sin tocar código, en `config.json`:

```json
"finops": {
    "precios_override": {
        "claude-sonnet-4-6": [3.00, 15.00],
        "gemini-2.5-flash": [0.075, 0.30]
    }
}
```

Los valores son `[precio_input_por_millón_tokens, precio_output_por_millón_tokens]` en USD.

### Botones del módulo

| Botón | Función |
|---|---|
| 🔄 Refrescar | Vuelve a cargar los datos desde `finops_data.json` |
| 🗑 Limpiar histórico | Borra TODO el histórico de uso (con confirmación, irreversible) |

### Tolerancia a fallos

FinOps nunca rompe el flujo principal del agente: si algo falla al registrar (archivo corrupto, modelo desconocido, etc.), la llamada al LLM continúa normalmente. Los errores se logean en consola y se ignoran silenciosamente.

---

## 15. Temas visuales (skins)

El agente soporta 5 temas visuales (skins) cambiables desde Configuraciones, con vista previa en vivo antes de guardar.

### Temas disponibles

| Tema | Tipo | Uso recomendado |
|---|---|---|
| 🌙 Catppuccin Mocha | Oscuro azulado | Default — uso normal |
| 🌿 Catppuccin Latte | Claro azulado | Trabajo de día con luz natural |
| 🧛 Dracula | Oscuro violeta | Sesiones largas de programación |
| 🌊 Nord | Oscuro frío | Estética minimalista escandinava |
| ⚡ Alto contraste | Negro puro + verde fosforescente | Accesibilidad / fatiga visual |

### Cómo cambiar el tema

1. Abrir Configuraciones (⚙).
2. Bajar hasta la sección **🎨 Tema visual**.
3. Elegir un tema del combo.
4. Presionar **👁 Vista previa** para verlo aplicado en vivo a la ventana principal y al popup.
5. Si te gusta, presionar **✅ Guardar cambios**. Si no, **Cancelar** restaura el tema anterior.

### Persistencia

El tema activo se guarda en `config.json` → `tema_visual` con uno de estos valores: `mocha`, `latte`, `dracula`, `nord`, `alto_contraste`. Al arrancar el agente se carga ese tema automáticamente.

### Aplicación en caliente

El cambio de tema se aplica en caliente a:
- La ventana principal del agente.
- El popup de configuraciones (que es donde lo eliges).

Otros popups que estén abiertos al momento mantendrán el tema anterior; al cerrarlos y abrirlos de nuevo tomarán el tema activo.

---

## 16. Configuraciones

El popup de **Configuraciones** (botón ⚙) permite editar todo sin tocar JSON:

### Detección de actividad

| Campo | Descripción |
|---|---|
| Lista blanca de procesos | Ejecutables `.exe` que el agente registra (uno por línea) |
| Lista negra de procesos | Ejecutables que siempre se ignoran |
| Keywords laborales (browser) | Palabras en el título que identifican contenido laboral en browsers |
| Keywords bloqueadas (browser) | Palabras que bloquean el registro en browsers (entretenimiento) |
| Personas conocidas | Nombres completos para wikilinks automáticos (uno por línea) |

### Chat y alertas

| Campo | Descripción |
|---|---|
| Días de contexto | Cuántos días de bitácoras se inyectan al chat |
| Días de alerta inactividad | Umbral para alertas de proyectos sin actividad |

### IA

| Campo | Descripción |
|---|---|
| System prompt | Prompt personalizable del asistente (con variables `{nombre_usuario}` y `{dias_contexto}`) |
| Modelo IA | Selector del modelo para el proveedor activo |

### FinOps (consumo de API)

Ver sección 14. Aquí se visualiza el módulo de monitoreo (no es editable, salvo "Limpiar histórico").

### Tema visual

Ver sección 15. Selector de skin con botón de vista previa.

### Aplicación de cambios

Los cambios en listas, contexto, prompt y tema se aplican **en caliente** (sin reiniciar). El modelo IA también se aplica en caliente si el cliente está activo.

---

## 17. Estructura de archivos generados

Dentro de tu `ruta_base` (vault de Obsidian), el agente genera:

```
bitacoras/
├── bitacora_2026-05-10.md          # Bitácora diaria
├── bitacora_2026-05-11.md
├── ...
├── gantt_proyectos.md              # Gantt global Mermaid
├── gantt_data.json                 # Datos crudos del Gantt
├── finops_data.json                # Datos crudos de FinOps (agregados por día)
│
├── objetos.md                      # Referencia (@objeto:) — upsert por nombre
├── personas.md                     # Referencia (@persona:) — upsert por nombre
├── diccionario_datos.md            # Referencia (@diccionario:) — upsert por nombre
│
├── decisiones.md                   # Archivos agregados por tipo de task
├── tareas.md                       # (cronológicos, agrupados por día,
├── acuerdos.md                     #  con wikilinks a la bitácora origen,
├── ideas.md                        #  sin upsert)
├── bloqueados.md
├── tickets.md
├── pendientes.md
│
├── proyectos/                      # Un .md por proyecto (MOCs)
│   ├── Mi_Proyecto.md
│   └── Otro_Proyecto.md
│
├── snippets/                       # Código extraído automáticamente
│   ├── 2026-05-10_14-30-00_sql.md
│   └── 2026-05-11_09-15-22_python.md
│
└── imagenes/                       # Capturas manuales (PNG)
    ├── captura_2026-05-10_16-45-00.png
    └── captura_2026-05-11_10-20-30.png
```

### Bitácora diaria

Cada bitácora tiene:

- **Frontmatter YAML** con metadata calculada localmente al cierre del día (fecha, total de capturas, herramientas usadas, categorías detectadas, personas mencionadas, proyectos del día).
- **Entradas por actividad** con hora, categoría, herramienta, descripción, duración, wikilinks y tags.
- **Notas manuales** intercaladas según el momento en que se escribieron.
- **URLs laborales** detectadas en cada captura.

### MOC de proyecto

Cada proyecto tiene:

- **Frontmatter ampliado** con métricas (horas totales, capturas, reuniones, snippets, personas, herramientas).
- **Diagrama Gantt individual** en Mermaid.
- **Sección de snippets** relacionados con wikilinks.
- **Sección de resumen** con indicadores de actividad.
- **Entradas agrupadas por día** con wikilinks a las bitácoras.

### Archivos agregados de task

Cronológicos por día, formato descrito en sección 12.2.

### finops_data.json

Archivo JSON con la estructura:

```json
{
  "version": 1,
  "registros_por_dia": {
    "2026-05-16": {
      "captura_actividad": {
        "llamadas": 89,
        "tokens_input": 137000,
        "tokens_output": 16800,
        "costo_usd": 0.663,
        "modelos": {"claude-sonnet-4-6": 89}
      }
    }
  }
}
```

---

## 18. Solución de problemas

### El agente no arranca

- Verifica que Python 3.10+ esté instalado: `python --version`
- Verifica que las dependencias estén instaladas: `pip list | grep PyQt5`
- Revisa que `config.json` exista en la misma carpeta que `agente.py`

### Error al conectar con la API

- Verifica que tu API key sea válida y tenga créditos disponibles.
- Revisa tu conexión a internet.
- El popup de login muestra el error exacto que retorna la API.

### No detecta mi aplicación

- Verifica que el proceso `.exe` esté en `lista_blanca_procesos` (ver Configuraciones).
- Para apps de browser, verifica que haya alguna keyword relevante en `palabras_clave_laborales_browser`.
- El agente solo registra ventanas que permanecen activas al menos `estabilidad_segundos` (default: 5).

### La bitácora no se abre en Obsidian

- Verifica que `ruta_base` apunte a la raíz de tu vault de Obsidian.
- Verifica que Obsidian esté instalado y que las rutas `ruta_obsidian_1` / `ruta_obsidian_2` sean correctas (o déjalas vacías para autodetección).

### El Gantt no clasifica actividades

- Verifica que tengas al menos un proyecto con estado "activo".
- Las entradas de menos de 2 minutos no se clasifican.
- La descripción del proyecto (`palabras_clave`) ayuda al LLM a clasificar mejor; mientras más descriptiva, más preciso el matching.

### El agente consume mucha API

- Cada cambio de ventana estable dispara una llamada al LLM con visión (modelo principal).
- Cada clasificación de proyecto usa el modelo rápido/barato del proveedor.
- Puedes aumentar `estabilidad_segundos` para reducir capturas.
- En modo reunión, puedes aumentar `intervalo_reunion_segundos`.

### Multi-monitor no funciona correctamente

- Verifica el selector de monitor (botón 🖥 en la barra superior).
- Monitor `1` = monitor principal, `2` = segundo monitor, `-1` = todos.
- El agente filtra por la posición del centro de la ventana activa.

---

> **El Egypcio** — Escribe el pasado. Ejecuta el futuro.
