"""
cliente_ia.py
Capa de abstracción para múltiples proveedores de IA.
Unifica Claude (Anthropic), OpenAI y Gemini bajo una misma interfaz.

Uso típico:
    from cliente_ia import ClienteIA, set_cliente, get_cliente

    # Inicialización (en agente.py después del login)
    cliente = ClienteIA(proveedor="claude", api_key="sk-ant-...", modelo="claude-sonnet-4-6")
    cliente.validar_key()      # Valida que la key funcione
    set_cliente(cliente)       # Lo deja disponible globalmente

    # En cualquier otro módulo
    cliente = get_cliente()
    texto = cliente.analizar_imagen(prompt, imagen_b64)
    texto = cliente.chat(system, mensajes, max_tokens=1000)
    texto = cliente.clasificar(prompt)  # Usa modelo barato/rápido
"""

import base64
from typing import Optional


# ---------------------------------------------------------------------------
# Modelos por defecto y modelos rápidos (para clasificación)
# ---------------------------------------------------------------------------

MODELOS_PRINCIPALES = {
    "claude": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-3.1-pro-preview"
}

MODELOS_RAPIDOS = {
    "claude": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash"
}

# Modelos disponibles por proveedor (para selector en configuraciones)
MODELOS_DISPONIBLES = {
    "claude": [
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001"
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4"
    ],
    "gemini": [
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-flash"
    ]
}

PROVEEDORES = {
    "claude": {"nombre": "Claude (Anthropic)", "icono": "🟠"},
    "openai": {"nombre": "OpenAI (ChatGPT)",   "icono": "🟢"},
    "gemini": {"nombre": "Gemini (Google)",    "icono": "🔵"}
}


# ---------------------------------------------------------------------------
# Cliente unificado
# ---------------------------------------------------------------------------

class ClienteIA:
    """
    Cliente unificado para Claude, OpenAI y Gemini.
    Expone métodos uniformes independiente del proveedor.
    """

    def __init__(self, proveedor: str, api_key: str, modelo: Optional[str] = None):
        if proveedor not in PROVEEDORES:
            raise ValueError(f"Proveedor desconocido: {proveedor}")
        if not api_key or not api_key.strip():
            raise ValueError("API key vacía")

        self.proveedor = proveedor
        self.api_key   = api_key.strip()
        self.modelo    = modelo or MODELOS_PRINCIPALES[proveedor]
        self.modelo_rapido = MODELOS_RAPIDOS[proveedor]

        self._sdk = None  # Se inicializa lazy en el primer uso
        self._inicializar_sdk()

    def _inicializar_sdk(self):
        """Importa e inicializa el SDK del proveedor seleccionado."""
        if self.proveedor == "claude":
            try:
                import anthropic
            except ImportError:
                raise ImportError("Instala: pip install anthropic")
            self._sdk = anthropic.Anthropic(api_key=self.api_key)

        elif self.proveedor == "openai":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("Instala: pip install openai")
            self._sdk = OpenAI(api_key=self.api_key)

        elif self.proveedor == "gemini":
            try:
                from google import genai
            except ImportError:
                try:
                    import google.generativeai as genai
                except ImportError:
                    raise ImportError("Instala: pip install google-generativeai")
            # API moderna unificada (google-genai) — fallback al SDK clásico
            self._sdk = genai
            try:
                self._cliente_gemini = genai.Client(api_key=self.api_key)
            except AttributeError:
                # SDK antiguo
                genai.configure(api_key=self.api_key)
                self._cliente_gemini = None

    # ------------------------------------------------------------------
    # Helpers FinOps: extracción de tokens según proveedor
    # ------------------------------------------------------------------
    def _extraer_tokens_claude(self, respuesta) -> tuple:
        """Extrae (input, output) tokens de una respuesta del SDK de Anthropic."""
        try:
            usage = getattr(respuesta, "usage", None)
            if usage is None:
                return (0, 0)
            return (
                int(getattr(usage, "input_tokens", 0) or 0),
                int(getattr(usage, "output_tokens", 0) or 0),
            )
        except Exception:
            return (0, 0)

    def _extraer_tokens_openai(self, respuesta) -> tuple:
        """Extrae (input, output) tokens de una respuesta del SDK de OpenAI."""
        try:
            usage = getattr(respuesta, "usage", None)
            if usage is None:
                return (0, 0)
            return (
                int(getattr(usage, "prompt_tokens", 0) or 0),
                int(getattr(usage, "completion_tokens", 0) or 0),
            )
        except Exception:
            return (0, 0)

    def _extraer_tokens_gemini(self, respuesta) -> tuple:
        """
        Extrae (input, output) tokens de una respuesta de Gemini.
        Tanto el SDK moderno (google-genai) como el clásico exponen
        `usage_metadata` con prompt_token_count / candidates_token_count.
        """
        try:
            metadata = getattr(respuesta, "usage_metadata", None)
            if metadata is None:
                return (0, 0)
            return (
                int(getattr(metadata, "prompt_token_count", 0) or 0),
                int(getattr(metadata, "candidates_token_count", 0) or 0),
            )
        except Exception:
            return (0, 0)

    def _registrar_uso_seguro(self, tipo_operacion: Optional[str],
                              modelo: str, tokens_input: int, tokens_output: int):
        """
        Llama a finops.registrar_uso de forma segura: cualquier excepción es
        capturada y logueada, para que el monitoreo NUNCA rompa el flujo
        principal del agente.

        Si tipo_operacion es None, no se registra (caso de retro-compat para
        llamadas externas que no especifiquen tipo).
        """
        if not tipo_operacion:
            return
        try:
            # Import diferido para evitar dependencia circular y permitir que
            # cliente_ia.py funcione incluso si finops.py no está disponible.
            import finops
            finops.registrar_uso(
                tipo=tipo_operacion,
                modelo=modelo,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
            )
        except Exception as e:
            print(f"[ClienteIA] FinOps registro silenciado: {e}")

    # ------------------------------------------------------------------
    # Validación de key
    # ------------------------------------------------------------------
    def validar_key(self) -> tuple[bool, str]:
        """
        Hace un mini-llamado para validar que la key funcione.
        Retorna (True, "OK") o (False, "mensaje de error").
        Se registra en FinOps como tipo "validacion_key".
        """
        tokens_in, tokens_out = 0, 0
        try:
            if self.proveedor == "claude":
                respuesta = self._sdk.messages.create(
                    model=self.modelo_rapido,
                    max_tokens=5,
                    messages=[{"role": "user", "content": "hi"}]
                )
                tokens_in, tokens_out = self._extraer_tokens_claude(respuesta)
            elif self.proveedor == "openai":
                respuesta = self._sdk.chat.completions.create(
                    model=self.modelo_rapido,
                    max_tokens=5,
                    messages=[{"role": "user", "content": "hi"}]
                )
                tokens_in, tokens_out = self._extraer_tokens_openai(respuesta)
            elif self.proveedor == "gemini":
                if self._cliente_gemini is not None:
                    respuesta = self._cliente_gemini.models.generate_content(
                        model=self.modelo_rapido,
                        contents="hi"
                    )
                    tokens_in, tokens_out = self._extraer_tokens_gemini(respuesta)
                else:
                    modelo = self._sdk.GenerativeModel(self.modelo_rapido)
                    respuesta = modelo.generate_content("hi")
                    tokens_in, tokens_out = self._extraer_tokens_gemini(respuesta)
            return (True, "OK")
        except Exception as e:
            return (False, str(e))
        finally:
            self._registrar_uso_seguro(
                "validacion_key", self.modelo_rapido, tokens_in, tokens_out
            )

    # ------------------------------------------------------------------
    # Análisis de imagen (Vision)
    # ------------------------------------------------------------------
    def analizar_imagen(self, prompt: str, imagen_b64: str,
                        max_tokens: int = 300,
                        tipo_operacion: Optional[str] = None) -> str:
        """
        Envía una imagen + prompt y retorna la respuesta textual.
        imagen_b64: imagen en base64 (sin prefijo data:).

        tipo_operacion: etiqueta FinOps (ej. "captura_actividad",
        "captura_reunion"). Si se omite, no se registra en el monitor.
        """
        tokens_in, tokens_out = 0, 0
        try:
            if self.proveedor == "claude":
                respuesta = self._sdk.messages.create(
                    model=self.modelo,
                    max_tokens=max_tokens,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": imagen_b64
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }]
                )
                tokens_in, tokens_out = self._extraer_tokens_claude(respuesta)
                return respuesta.content[0].text.strip()

            elif self.proveedor == "openai":
                respuesta = self._sdk.chat.completions.create(
                    model=self.modelo,
                    max_tokens=max_tokens,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{imagen_b64}"
                                }
                            }
                        ]
                    }]
                )
                tokens_in, tokens_out = self._extraer_tokens_openai(respuesta)
                return respuesta.choices[0].message.content.strip()

            elif self.proveedor == "gemini":
                imagen_bytes = base64.b64decode(imagen_b64)
                if self._cliente_gemini is not None:
                    from google.genai import types
                    respuesta = self._cliente_gemini.models.generate_content(
                        model=self.modelo,
                        contents=[
                            types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg"),
                            prompt
                        ],
                        config=types.GenerateContentConfig(max_output_tokens=max_tokens)
                    )
                    tokens_in, tokens_out = self._extraer_tokens_gemini(respuesta)
                    return respuesta.text.strip()
                else:
                    # SDK clásico
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(imagen_bytes))
                    modelo = self._sdk.GenerativeModel(self.modelo)
                    respuesta = modelo.generate_content([prompt, img])
                    tokens_in, tokens_out = self._extraer_tokens_gemini(respuesta)
                    return respuesta.text.strip()
        finally:
            # Se registra incluso si hubo excepción (con tokens=0). Eso
            # permite ver en FinOps que hubo intentos fallidos.
            self._registrar_uso_seguro(tipo_operacion, self.modelo, tokens_in, tokens_out)

    # ------------------------------------------------------------------
    # Chat conversacional
    # ------------------------------------------------------------------
    def chat(self, system: str, mensajes: list, max_tokens: int = 1000,
             tipo_operacion: Optional[str] = None) -> str:
        """
        Conversación multi-turno.
        mensajes: lista de {role: "user"/"assistant", content: str}

        tipo_operacion: etiqueta FinOps (ej. "chat_usuario", "resumen_dia",
        "resumen_semana"). Si se omite, no se registra en el monitor.
        """
        tokens_in, tokens_out = 0, 0
        try:
            if self.proveedor == "claude":
                respuesta = self._sdk.messages.create(
                    model=self.modelo,
                    max_tokens=max_tokens,
                    system=system,
                    messages=mensajes
                )
                tokens_in, tokens_out = self._extraer_tokens_claude(respuesta)
                return respuesta.content[0].text.strip()

            elif self.proveedor == "openai":
                mensajes_openai = [{"role": "system", "content": system}] + mensajes
                respuesta = self._sdk.chat.completions.create(
                    model=self.modelo,
                    max_tokens=max_tokens,
                    messages=mensajes_openai
                )
                tokens_in, tokens_out = self._extraer_tokens_openai(respuesta)
                return respuesta.choices[0].message.content.strip()

            elif self.proveedor == "gemini":
                # Gemini concatena system al primer mensaje user
                contenido = f"{system}\n\n"
                for m in mensajes:
                    rol = "Usuario" if m["role"] == "user" else "Asistente"
                    contenido += f"{rol}: {m['content']}\n\n"
                contenido += "Asistente:"

                if self._cliente_gemini is not None:
                    from google.genai import types
                    respuesta = self._cliente_gemini.models.generate_content(
                        model=self.modelo,
                        contents=contenido,
                        config=types.GenerateContentConfig(max_output_tokens=max_tokens)
                    )
                    tokens_in, tokens_out = self._extraer_tokens_gemini(respuesta)
                    return respuesta.text.strip()
                else:
                    modelo = self._sdk.GenerativeModel(self.modelo)
                    respuesta = modelo.generate_content(contenido)
                    tokens_in, tokens_out = self._extraer_tokens_gemini(respuesta)
                    return respuesta.text.strip()
        finally:
            self._registrar_uso_seguro(tipo_operacion, self.modelo, tokens_in, tokens_out)

    # ------------------------------------------------------------------
    # Clasificación rápida (modelo barato)
    # ------------------------------------------------------------------
    def clasificar(self, prompt: str, max_tokens: int = 30,
                   tipo_operacion: Optional[str] = None,
                   temperature: Optional[float] = None) -> str:
        """
        Tarea rápida y barata: usa el modelo rápido del proveedor.
        Ideal para clasificar actividades.

        Args:
            prompt: el prompt completo a enviar al LLM.
            max_tokens: tope de tokens de respuesta.
            tipo_operacion: etiqueta FinOps (típicamente "clasificacion_proyecto").
            temperature: temperatura de muestreo (0.0–1.0). Si es None, se usa
                el default del proveedor. Valores bajos (0.0–0.2) favorecen
                clasificación determinista; valores altos introducen variación.

        El registro FinOps usa self.modelo_rapido, no self.modelo.
        """
        # Clamp defensivo: la temperatura debe estar en [0.0, 1.0]
        if temperature is not None:
            temperature = max(0.0, min(1.0, float(temperature)))

        tokens_in, tokens_out = 0, 0
        try:
            if self.proveedor == "claude":
                kwargs = {
                    "model": self.modelo_rapido,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if temperature is not None:
                    kwargs["temperature"] = temperature
                respuesta = self._sdk.messages.create(**kwargs)
                tokens_in, tokens_out = self._extraer_tokens_claude(respuesta)
                return respuesta.content[0].text.strip()

            elif self.proveedor == "openai":
                kwargs = {
                    "model": self.modelo_rapido,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if temperature is not None:
                    kwargs["temperature"] = temperature
                respuesta = self._sdk.chat.completions.create(**kwargs)
                tokens_in, tokens_out = self._extraer_tokens_openai(respuesta)
                return respuesta.choices[0].message.content.strip()

            elif self.proveedor == "gemini":
                if self._cliente_gemini is not None:
                    from google.genai import types
                    config_kwargs = {"max_output_tokens": max_tokens}
                    if temperature is not None:
                        config_kwargs["temperature"] = temperature
                    respuesta = self._cliente_gemini.models.generate_content(
                        model=self.modelo_rapido,
                        contents=prompt,
                        config=types.GenerateContentConfig(**config_kwargs)
                    )
                    tokens_in, tokens_out = self._extraer_tokens_gemini(respuesta)
                    return respuesta.text.strip()
                else:
                    modelo = self._sdk.GenerativeModel(self.modelo_rapido)
                    if temperature is not None:
                        respuesta = modelo.generate_content(
                            prompt,
                            generation_config={"temperature": temperature}
                        )
                    else:
                        respuesta = modelo.generate_content(prompt)
                    tokens_in, tokens_out = self._extraer_tokens_gemini(respuesta)
                    return respuesta.text.strip()
        finally:
            # IMPORTANTE: registramos el modelo_rapido, no self.modelo
            self._registrar_uso_seguro(
                tipo_operacion, self.modelo_rapido, tokens_in, tokens_out
            )


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_cliente_global: Optional[ClienteIA] = None


def set_cliente(cliente: ClienteIA):
    """Establece el cliente global compartido por todos los módulos."""
    global _cliente_global
    _cliente_global = cliente
    print(f"[ClienteIA] Cliente activo: {cliente.proveedor} | modelo: {cliente.modelo}")


def get_cliente() -> ClienteIA:
    """Retorna el cliente global. Lanza error si no está inicializado."""
    if _cliente_global is None:
        raise RuntimeError(
            "Cliente IA no inicializado. "
            "Asegúrate de pasar por el popup de login al iniciar el agente."
        )
    return _cliente_global


def hay_cliente_activo() -> bool:
    """True si hay un cliente válido inicializado."""
    return _cliente_global is not None
