"""Interpretación de requisitos de vivienda, local o mediante proveedor."""
from __future__ import annotations
import json
import os
import re
import urllib.error
import urllib.request

def local_interpret(text):
    """Extracción offline acotada; las dimensiones se validan antes de crear geometría."""
    t = text.lower()
    def first(pattern, default):
        match = re.search(pattern, t)
        return int(match.group(1)) if match else default
    lot = re.search(r"(\d+(?:\.\d+)?)\s*(?:m\s*)?(?:×|x|por)\s*(\d+(?:\.\d+)?)", t)
    return {
        "name": "Casa personalizada",
        "width": min(30, max(6, float(lot.group(1)) if lot else 10)),
        "length": min(40, max(8, float(lot.group(2)) if lot else 20)),
        "floors": min(3, max(1, first(r"(\d+)\s*(?:pisos|niveles)", 2 if re.search(r"dos\s+(?:pisos|niveles)", t) else 1))),
        "bedrooms": min(10, max(1, first(r"(\d+)\s*(?:dormitorios|dormitorio|habitaciones|habitaci[oó]n)", 3))),
        "baths": min(8, max(1, first(r"(\d+)\s*baños?", 2))),
        "style": "moderno" if "modern" in t else "contemporáneo",
        "budget": None,
        "questions": [],
        "source": "reglas locales",
    }


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "name": {"type": "string"}, "width": {"type": "number"}, "length": {"type": "number"},
        "floors": {"type": "integer"}, "bedrooms": {"type": "integer"}, "baths": {"type": "integer"},
        "style": {"type": "string"}, "budget": {"type": ["number", "null"]},
        "questions": {"type": "array", "items": {"type": "string"}},
    }, "required": ["name", "width", "length", "floors", "bedrooms", "baths", "style", "budget", "questions"]
}


def interpret(text):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return local_interpret(text)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    try:
        endpoint = os.environ.get("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses")
        payload = {
            "model": model,
            "instructions": "Extrae requisitos de vivienda. No diseñes planos constructivos. Devuelve solo datos según el esquema; usa unidades métricas. Si faltan datos, añade preguntas breves.",
            "input": text[:8000],
            "text": {"format": {"type": "json_schema", "name": "housing_requirements", "strict": True, "schema": SCHEMA}},
        }
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=35) as response:
            result = json.loads(response.read(1_000_000))
        if result.get("status") != "completed":
            raise ValueError("El proveedor de IA no completó la respuesta")
        output = next((c.get("text") for item in result.get("output", []) if item.get("type") == "message" for c in item.get("content", []) if c.get("type") == "output_text"), None)
        if not output:
            raise ValueError("La IA no devolvió requisitos estructurados")
        data = json.loads(output)
        for key_name, low, high in (("width", 4, 50), ("length", 4, 80), ("floors", 1, 3), ("bedrooms", 1, 10), ("baths", 1, 8)):
            if not isinstance(data.get(key_name), (int, float)) or not low <= data[key_name] <= high:
                raise ValueError(f"La IA propuso un valor fuera de rango para {key_name}")
        data["source"] = "OpenAI · " + model
        return data
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        # La propuesta se mantiene disponible cuando falte una clave válida o red.
        data = local_interpret(text)
        data["source"] = "reglas locales (proveedor IA no disponible)"
        return data
