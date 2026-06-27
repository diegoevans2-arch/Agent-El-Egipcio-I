---
date: 2026-06-02
tags: [el-egypcio, clasificacion, prompt-engineering, proyectos, gantt]
status: done
type: nota-tecnica
project: El Egypcio
author: El Egypcio
---

# 🎯 Versiones de Prompt de Clasificación de Proyectos

> Archivo de referencia para el campo **Prompt de clasificación de proyectos**
> en las configuraciones del agente.
>
> Para cambiar de versión: ve a ⚙️ Configuraciones → 🎯 Prompt de clasificación
> de proyectos → borra el contenido actual → pega la versión deseada → Guardar.
> Para volver al default: presiona el botón ↺ Restaurar default.

---

## Tabla resumen

| Nivel | Nombre | Cuándo usarlo | Riesgo principal |
|---|---|---|---|
| 1 | **Estricto** *(default)* | Proyectos bien definidos con objetivos específicos | Subclasificación (mucho "ninguno") |
| 2 | **Moderado** | Uso general, proyectos activos con buenas descripciones | Equilibrado |
| 3 | **Flexible** | Proyectos con descripciones incompletas u objetivos difusos | Sobreclasificación (falsos positivos) |
| 4 | **Por herramienta exclusiva** | Proyectos con herramientas o sistemas únicos (ej: smartcampus) | Clasificación por proxy de herramienta |
| 5 | **Anti-transversal** | Todo se hace en las mismas herramientas (SQL, DBeaver, Python para varios proyectos) | Más exigente en contenido; puede subclasificar |
| 6 | **Debug / con razonamiento** | Diagnosticar por qué el agente clasifica como clasifica | ⚠️ Requiere ajuste de código (ver nota) |

---

## Placeholders obligatorios

Todos los templates incluyen estos 4 placeholders. No eliminarlos.

| Placeholder | Qué inserta el agente |
|---|---|
| `{titulo_ventana}` | Título de la ventana detectada (máx. 120 chars) |
| `{descripcion_actividad}` | Descripción generada por el LLM de visión (máx. 300 chars) |
| `{lista_proyectos}` | Bloque con nombre, descripción y objetivos de cada proyecto activo |
| `{lista_nombres}` | Lista de nombres válidos como respuesta (`"Proyecto A" \| "Proyecto B"`) |

---

## Nivel 1 — Estricto *(default)*

**Filosofía:** clasificar solo cuando hay evidencia clara y directa. Las herramientas genéricas (DBeaver, SQL, Python) no son suficientes por sí solas. Prefiere "ninguno" antes que un match dudoso.

**Cuándo usarlo:** proyectos con objetivos bien definidos y actividades claramente diferenciadas entre sí. Es el punto de partida recomendado.

**Efectos esperados:** menos horas clasificadas en total, pero las que se clasifican son confiables.

```
Tienes esta actividad laboral detectada en pantalla:

Ventana activa: {titulo_ventana}
Descripción de la actividad: {descripcion_actividad}

Estos son los proyectos activos del usuario, cada uno con su descripción
general y sus objetivos específicos:

{lista_proyectos}

TAREA: Determina a qué proyecto pertenece la actividad detectada.

CRITERIO DE DECISIÓN (estricto):
- La actividad debe contribuir directamente a los OBJETIVOS ESPECÍFICOS
  de un proyecto. La sola coincidencia de tecnologías, herramientas o
  palabras genéricas NO es suficiente para clasificar.
- Si la actividad NO contribuye claramente a los objetivos de ningún
  proyecto, responde "ninguno". Es preferible "ninguno" antes que un
  match dudoso.
- Si la actividad encaja parcialmente con varios proyectos, elige el
  que mejor cumpla los objetivos específicos.

RESPUESTA: SOLO el nombre exacto del proyecto de la lista ({lista_nombres})
o la palabra "ninguno". Sin explicaciones, sin comillas, sin markdown.
```

---

## Nivel 2 — Moderado

**Filosofía:** la actividad debe tener una relación razonable con los objetivos del proyecto, no necesariamente directa. Si una herramienta es usada predominantemente en un proyecto, puede ser señal válida. Ante empate entre dos proyectos, gana el que tenga mayor coincidencia de contenido específico (nombres de tablas, módulos, sistemas, personas).

**Cuándo usarlo:** uso general cuando los proyectos están bien descritos y tienen objetivos razonablemente distintos entre sí. Buen punto intermedio para el día a día.

**Efectos esperados:** más clasificaciones que el estricto, con una tasa de falsos positivos aceptable.

```
Tienes esta actividad laboral detectada en pantalla:

Ventana activa: {titulo_ventana}
Descripción de la actividad: {descripcion_actividad}

Estos son los proyectos activos del usuario, cada uno con su descripción
general y sus objetivos específicos:

{lista_proyectos}

TAREA: Determina a qué proyecto pertenece la actividad detectada.

CRITERIO DE DECISIÓN (moderado):
- La actividad debe tener una relación razonable con los OBJETIVOS
  ESPECÍFICOS de un proyecto. No se requiere coincidencia exacta, pero
  sí una conexión clara con el trabajo descrito en los objetivos.
- Si una herramienta o sistema específico (no genérico) aparece solo en
  un proyecto, su presencia en la actividad es señal válida para clasificar.
- Si la actividad encaja con varios proyectos, desempata por el contenido
  específico: nombres de tablas, módulos, sistemas, personas o tareas
  que aparezcan en la descripción de la actividad.
- Si la actividad es completamente genérica o no tiene relación con ningún
  proyecto, responde "ninguno".

RESPUESTA: SOLO el nombre exacto del proyecto de la lista ({lista_nombres})
o la palabra "ninguno". Sin explicaciones, sin comillas, sin markdown.
```

---

## Nivel 3 — Flexible

**Filosofía:** si la actividad tiene cualquier conexión con el área temática, las tecnologías o el contexto de un proyecto, clasifica. Solo responde "ninguno" si la actividad es claramente ajena a todos los proyectos. Útil cuando las descripciones de proyectos son incompletas y se prefiere clasificar más que omitir.

**Cuándo usarlo:** proyectos en etapa inicial con objetivos todavía vagos, o cuando después de correr el nivel estricto notas que demasiadas actividades genuinas quedan sin clasificar.

**Efectos esperados:** máximo de horas clasificadas; requiere revisión manual periódica para detectar sobreclasificaciones.

```
Tienes esta actividad laboral detectada en pantalla:

Ventana activa: {titulo_ventana}
Descripción de la actividad: {descripcion_actividad}

Estos son los proyectos activos del usuario, cada uno con su descripción
general y sus objetivos específicos:

{lista_proyectos}

TAREA: Determina a qué proyecto pertenece la actividad detectada.

CRITERIO DE DECISIÓN (flexible):
- Clasifica si la actividad tiene cualquier conexión con el área temática,
  las tecnologías, los sistemas o el contexto de un proyecto, aunque la
  relación no sea directa con sus objetivos específicos.
- Si la actividad encaja con varios proyectos, elige el que tenga mayor
  afinidad general (más elementos coincidentes en conjunto: tecnologías,
  módulos, personas, área de trabajo).
- Solo responde "ninguno" si la actividad claramente no tiene relación
  alguna con ningún proyecto activo (ej: actividad personal, ocio,
  tarea completamente ajena al dominio de los proyectos).

RESPUESTA: SOLO el nombre exacto del proyecto de la lista ({lista_nombres})
o la palabra "ninguno". Sin explicaciones, sin comillas, sin markdown.
```

---

## Nivel 4 — Por herramienta exclusiva

**Filosofía:** primero verifica si la ventana activa corresponde a una herramienta o sistema que solo existe en un proyecto específico. Si es así, clasifica directamente. Si no, aplica criterio moderado. Útil cuando algunos proyectos tienen herramientas únicas (ej: smartcampus solo existe en Módulo Laboratorios).

**Cuándo usarlo:** cuando tienes un proyecto con una herramienta o sistema muy específico que no se usa en ningún otro proyecto activo.

**Efectos esperados:** clasificación rápida y precisa para proyectos con herramientas únicas; moderada para el resto.

```
Tienes esta actividad laboral detectada en pantalla:

Ventana activa: {titulo_ventana}
Descripción de la actividad: {descripcion_actividad}

Estos son los proyectos activos del usuario, cada uno con su descripción
general y sus objetivos específicos:

{lista_proyectos}

TAREA: Determina a qué proyecto pertenece la actividad detectada.

CRITERIO DE DECISIÓN (por herramienta exclusiva):
PASO 1 — Herramienta exclusiva:
  Verifica si la ventana activa o la descripción menciona un sistema,
  plataforma o módulo que aparece ÚNICAMENTE en uno de los proyectos
  (no en los demás). Si encuentras esa herramienta exclusiva, clasifica
  directamente en ese proyecto sin evaluar más.

PASO 2 — Si no hay herramienta exclusiva, aplica criterio moderado:
  - La actividad debe tener una relación razonable con los OBJETIVOS
    ESPECÍFICOS del proyecto.
  - Ante empate entre proyectos, desempata por contenido específico:
    nombres de tablas, módulos, personas o tareas concretas.
  - Si no hay relación clara con ningún proyecto, responde "ninguno".

RESPUESTA: SOLO el nombre exacto del proyecto de la lista ({lista_nombres})
o la palabra "ninguno". Sin explicaciones, sin comillas, sin markdown.
```

---

## Nivel 5 — Anti-transversal

**Filosofía:** diseñado para entornos donde las mismas herramientas se usan en todos los proyectos (DBeaver, SQL, Python, Jupyter). En ese contexto, la herramienta es irrelevante para clasificar — lo que importa es el CONTENIDO: nombres de tablas, módulos, sistemas, personas o términos de dominio mencionados en la actividad. Si el contenido no es suficientemente específico, prefiere "ninguno".

**Cuándo usarlo:** cuando detectas que el agente clasifica mal porque "está en DBeaver haciendo SQL" matchea con varios proyectos. También útil cuando los proyectos comparten el mismo stack tecnológico completo.

**Efectos esperados:** clasificaciones más precisas en entornos transversales; puede generar más "ninguno" que el moderado para actividades ambiguas.

```
Tienes esta actividad laboral detectada en pantalla:

Ventana activa: {titulo_ventana}
Descripción de la actividad: {descripcion_actividad}

Estos son los proyectos activos del usuario, cada uno con su descripción
general y sus objetivos específicos:

{lista_proyectos}

TAREA: Determina a qué proyecto pertenece la actividad detectada.

CRITERIO DE DECISIÓN (anti-transversal):
REGLA PRINCIPAL: Las herramientas genéricas (SQL, DBeaver, Python, Jupyter,
Excel, Power BI) son IRRELEVANTES para clasificar porque se usan en todos
los proyectos. NO uses la herramienta como criterio de decisión.

CLASIFICAR ÚNICAMENTE si la descripción de la actividad menciona
EXPLÍCITAMENTE alguno de los siguientes elementos de un proyecto específico:
  - Nombres de tablas, vistas o módulos del sistema
  - Nombres de sistemas o plataformas específicas del proyecto
  - Nombres de personas involucradas en el proyecto
  - Términos de dominio o entregables únicos del proyecto

Si la descripción es genérica ("hizo una query", "revisó datos", "abrió
un notebook") sin mencionar contenido específico de ningún proyecto,
responde "ninguno".

Si hay coincidencia de contenido con varios proyectos, elige el que
tenga mayor número de elementos específicos coincidentes.

RESPUESTA: SOLO el nombre exacto del proyecto de la lista ({lista_nombres})
o la palabra "ninguno". Sin explicaciones, sin comillas, sin markdown.
```

---

## Nivel 6 — Debug / con razonamiento

> ⚠️ **Este template requiere un ajuste menor en el código.**
>
> El agente actualmente espera solo el nombre del proyecto o "ninguno" como
> respuesta. Este template pide al LLM que responda en el formato:
> `PROYECTO: <nombre> | RAZÓN: <una línea>`
>
> Para que funcione, hay que modificar `clasificar_actividad()` en `gantt.py`
> para parsear la respuesta con un split en `|` y extraer solo la parte
> `PROYECTO:`. Sin ese cambio, el agente no reconocerá el nombre del proyecto
> en la respuesta y clasificará todo como "ninguno".
>
> **Uso recomendado:** activarlo temporalmente (sin el ajuste de código) para
> leer los logs de consola del agente y entender por qué clasifica como clasifica.
> Una vez diagnosticado el problema, volver al nivel que corresponda.

**Filosofía:** aplica criterio moderado, pero además de responder el nombre del proyecto, devuelve una línea de razonamiento. Útil exclusivamente para diagnosticar clasificaciones inesperadas.

**Cuándo usarlo:** cuando el agente clasifica de forma inesperada y quieres entender la causa sin ejecutar el código en modo debug.

```
Tienes esta actividad laboral detectada en pantalla:

Ventana activa: {titulo_ventana}
Descripción de la actividad: {descripcion_actividad}

Estos son los proyectos activos del usuario, cada uno con su descripción
general y sus objetivos específicos:

{lista_proyectos}

TAREA: Determina a qué proyecto pertenece la actividad detectada.

CRITERIO DE DECISIÓN (moderado con razonamiento):
- La actividad debe tener una relación razonable con los OBJETIVOS
  ESPECÍFICOS de un proyecto.
- Si una herramienta o sistema específico (no genérico) aparece solo en
  un proyecto, su presencia es señal válida para clasificar.
- Si encaja con varios proyectos, desempata por contenido específico.
- Si no hay relación clara, clasifica como "ninguno".

RESPUESTA: Responde ÚNICAMENTE en este formato exacto (en una sola línea):
PROYECTO: <nombre exacto de la lista o "ninguno"> | RAZÓN: <una línea explicando por qué>

Ejemplo de respuesta válida:
PROYECTO: Módulo Laboratorios | RAZÓN: La descripción menciona equipamiento y smartcampus, herramienta exclusiva de ese proyecto.

Nombres válidos para el campo PROYECTO: {lista_nombres} o "ninguno".
Sin saltos de línea adicionales, sin markdown.
```

---

## Guía de selección rápida

```
¿Los proyectos tienen objetivos bien definidos y distintos entre sí?
    └─ Sí → empieza con Nivel 1 (Estricto)
           └─ ¿Demasiadas actividades quedan sin clasificar? → sube a Nivel 2 (Moderado)

¿Todos tus proyectos usan las mismas herramientas (SQL, Python, DBeaver)?
    └─ Sí → usa Nivel 5 (Anti-transversal)

¿Algún proyecto tiene una herramienta o sistema único (solo ese proyecto lo usa)?
    └─ Sí → usa Nivel 4 (Por herramienta exclusiva)

¿Los proyectos son nuevos y las descripciones están incompletas?
    └─ Sí → usa Nivel 3 (Flexible) mientras rellenas los objetivos

¿El agente está clasificando mal y no entiendes por qué?
    └─ Usa Nivel 6 (Debug) temporalmente para leer los logs
```

---

# 🖼️ Versiones de Prompt de Análisis de Imágenes

> Esta sección es paralela a la de clasificación de proyectos, pero aplica a
> los **prompts de análisis de imágenes**: los que el LLM usa para describir
> qué se ve en cada captura de pantalla.
>
> Hay **dos prompts independientes**, configurables por separado en
> ⚙️ Configuraciones:
> - **Actividad**: para capturas de trabajo normal (no reunión).
> - **Reunión**: para capturas durante reuniones virtuales.

---

## Diferencia entre los dos prompts

| Aspecto | Prompt de Actividad | Prompt de Reunión |
|---|---|---|
| Cuándo se usa | Ventana de trabajo normal | Ventana detectada como reunión (Teams/Zoom/Meet) |
| Qué busca | Describir la tarea y la herramienta | Detectar si se proyecta contenido laboral |
| JSON esperado | `actividad`, `categoria`, `herramienta`, `urls` | `hay_proyeccion`, `descripcion`, `tipo_contenido`, `urls` |
| Caso especial | — | Devuelve `SIN_PROYECCION` si solo hay cámaras |

> ⚠️ **No cambies la estructura del JSON de salida.** El código parsea esos
> campos exactos. Si modificas los nombres de los campos (ej. cambias
> `actividad` por `tarea`), el parser fallará y la entrada quedará como
> "Actividad detectada (sin detalle)". Puedes cambiar las **instrucciones**,
> el **tono** y el **nivel de detalle**, pero conserva los campos del JSON.

---

## Placeholder obligatorio

Ambos prompts de imagen tienen un único placeholder obligatorio:

| Placeholder | Qué inserta el agente |
|---|---|
| `{titulo_ventana}` | Título de la ventana que se está capturando |

Si falta, el guardado se rechaza. Si el campo se deja vacío, se usa el default.

---

## Niveles para el prompt de ACTIVIDAD

### Nivel A1 — Conciso *(default)*

Una o dos líneas. Herramienta + qué hace. Lo mínimo para una bitácora legible.

```
Estás viendo la pantalla de un profesional universitario (área de datos/analytics).
Título de la ventana activa: "{titulo_ventana}"

Describe brevemente qué tarea laboral está realizando. Sé específico pero conciso (máximo 2 líneas).
Enfócate en: ¿qué herramienta usa?, ¿qué está haciendo en ella?

Adicionalmente: si hay URLs visibles en la pantalla (barra de navegador, links abiertos, etc.),
lístalas en el campo "urls". Si no hay URLs, retorna lista vacía.

Responde SOLO con JSON válido (sin markdown, sin backticks):
{{
  "actividad": "descripción concisa de la tarea",
  "categoria": "SQL/Python/Dashboard/Reunión/Documentación/Email/Otro",
  "herramienta": "nombre de la herramienta o aplicación principal",
  "urls": ["url1", "url2"]
}}
```

### Nivel A2 — Detallado

Pide más contexto: qué tabla/archivo/dashboard concreto, qué columnas o métricas se ven. Útil si quieres bitácoras más ricas para el chat conversacional, a costa de más tokens de salida.

```
Estás viendo la pantalla de un profesional universitario (área de datos/analytics).
Título de la ventana activa: "{titulo_ventana}"

Describe con detalle qué tarea laboral está realizando (máximo 4 líneas).
Incluye, si son visibles:
- La herramienta o aplicación principal.
- El objeto de trabajo concreto: nombre de tabla, vista, archivo, dashboard o reporte.
- Elementos específicos visibles: columnas, métricas, filtros, nombres de campos.

Si hay URLs visibles (barra de navegador, links), lístalas en "urls". Si no, lista vacía.

Responde SOLO con JSON válido (sin markdown, sin backticks):
{{
  "actividad": "descripción detallada de la tarea con objetos concretos",
  "categoria": "SQL/Python/Dashboard/Reunión/Documentación/Email/Otro",
  "herramienta": "nombre de la herramienta o aplicación principal",
  "urls": ["url1", "url2"]
}}
```

### Nivel A3 — Con extracción de objetos de datos

Enfocado en capturar nombres de tablas, vistas y campos para alimentar el diccionario de datos. Pensado para flujos donde quieres detectar automáticamente qué objetos de Banner/Athena tocas.

```
Estás viendo la pantalla de un profesional universitario (área de datos/analytics).
Título de la ventana activa: "{titulo_ventana}"

Describe qué tarea laboral está realizando (máximo 3 líneas) y, sobre todo,
identifica los OBJETOS DE DATOS visibles: nombres de tablas, vistas, esquemas,
archivos de datos, o reportes que aparezcan textualmente en pantalla.

Si hay URLs visibles, lístalas en "urls". Si no, lista vacía.

Responde SOLO con JSON válido (sin markdown, sin backticks):
{{
  "actividad": "descripción de la tarea",
  "categoria": "SQL/Python/Dashboard/Reunión/Documentación/Email/Otro",
  "herramienta": "nombre de la herramienta o aplicación principal",
  "objetos_datos": ["tabla_o_vista_1", "archivo_2"],
  "urls": ["url1", "url2"]
}}
```

> ⚠️ El Nivel A3 agrega el campo `objetos_datos` al JSON. El código actual
> **no procesa** ese campo todavía (lo ignora sin romperse). Para que tenga
> efecto, habría que extender `analizar_screenshot` y `bitacora.py` para
> registrar esos objetos. Úsalo solo si vas a implementar ese procesamiento.

---

## Niveles para el prompt de REUNIÓN

### Nivel R1 — Estándar *(default)*

Detecta proyección sí/no, describe el contenido en 3 líneas, captura URLs.

```
Estás viendo la pantalla de un profesional universitario durante una reunión virtual.
Título de la ventana: "{titulo_ventana}"

Analiza la imagen y determina:
1. ¿Se está proyectando contenido laboral? (presentación, documento, dashboard, tabla, etc.)
2. Si SÍ hay proyección: describe brevemente qué se está mostrando (máximo 3 líneas)
3. Si NO hay proyección (solo cámaras, fondo virtual, pantalla de espera): responde solo "SIN_PROYECCION"
4. URLs visibles: si hay una barra de navegador o links visibles, lista las URLs completas que aparezcan.

Responde SOLO con JSON válido (sin markdown, sin backticks):
{{
  "hay_proyeccion": true,
  "descripcion": "descripción del contenido o SIN_PROYECCION",
  "tipo_contenido": "presentación/dashboard/documento/tabla/otro/ninguno",
  "urls": ["url1", "url2"]
}}
```

### Nivel R2 — Detallado con participantes

Además de la proyección, intenta capturar el tema de la reunión y si hay nombres de participantes visibles. Útil para reuniones recurrentes donde quieres trazar quién estuvo.

```
Estás viendo la pantalla de un profesional universitario durante una reunión virtual.
Título de la ventana: "{titulo_ventana}"

Analiza la imagen y determina:
1. ¿Se está proyectando contenido laboral? (presentación, documento, dashboard, tabla, etc.)
2. Si SÍ hay proyección: describe qué se muestra (máximo 3 líneas) e indica el tema si es deducible.
3. Si NO hay proyección (solo cámaras, fondo virtual, espera): responde "SIN_PROYECCION".
4. Participantes: si hay nombres visibles en los recuadros de video, lístalos.
5. URLs visibles: lista las URLs completas que aparezcan.

Responde SOLO con JSON válido (sin markdown, sin backticks):
{{
  "hay_proyeccion": true,
  "descripcion": "descripción del contenido o SIN_PROYECCION",
  "tipo_contenido": "presentación/dashboard/documento/tabla/otro/ninguno",
  "participantes": ["nombre1", "nombre2"],
  "urls": ["url1", "url2"]
}}
```

> ⚠️ El Nivel R2 agrega el campo `participantes`. Igual que A3, el código
> actual lo ignora sin romperse; requiere procesamiento adicional para que
> tenga efecto.

### Nivel R3 — Conservador (solo proyección)

Para entornos donde la privacidad importa: NO captura participantes ni intenta leer nombres, solo evalúa si hay contenido laboral proyectado.

```
Estás viendo la pantalla de un profesional universitario durante una reunión virtual.
Título de la ventana: "{titulo_ventana}"

Analiza ÚNICAMENTE si se está proyectando contenido laboral (presentación,
documento, dashboard, tabla). NO describas a las personas ni leas nombres
de participantes.

- Si hay proyección: describe solo el contenido laboral (máximo 2 líneas).
- Si solo hay cámaras, fondos o pantalla de espera: responde "SIN_PROYECCION".

Responde SOLO con JSON válido (sin markdown, sin backticks):
{{
  "hay_proyeccion": true,
  "descripcion": "descripción del contenido laboral o SIN_PROYECCION",
  "tipo_contenido": "presentación/dashboard/documento/tabla/otro/ninguno",
  "urls": []
}}
```

---

## Guía de selección rápida (imágenes)

```
ACTIVIDAD:
¿Quieres bitácoras mínimas y baratas en tokens?
    └─ Nivel A1 (Conciso, default)
¿Quieres bitácoras ricas para consultar en el chat?
    └─ Nivel A2 (Detallado)
¿Vas a implementar detección automática de tablas/objetos?
    └─ Nivel A3 (Extracción de objetos) — requiere código adicional

REUNIÓN:
¿Caso general?
    └─ Nivel R1 (Estándar, default)
¿Quieres trazar participantes de reuniones recurrentes?
    └─ Nivel R2 (Detallado) — requiere código adicional
¿Privacidad estricta (no leer nombres de personas)?
    └─ Nivel R3 (Conservador)
```

---

*Generado para [[El Egypcio]] · Relacionado con [[gantt]] · Ver también [[proyectos]]*
