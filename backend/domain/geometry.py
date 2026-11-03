"""Reglas de validación geométrica del modelo paramétrico."""
import math

def validate_model(model):
    issues = []
    if not isinstance(model, dict):
        return ["El diseño debe ser un objeto JSON"]
    width, length = model.get("width"), model.get("length")
    if not isinstance(width, (int, float)) or not math.isfinite(width) or not 4 <= width <= 50:
        issues.append("El ancho del terreno debe estar entre 4 y 50 m")
    if not isinstance(length, (int, float)) or not math.isfinite(length) or not 4 <= length <= 80:
        issues.append("El largo del terreno debe estar entre 4 y 80 m")
    components = model.get("components", [])
    if not isinstance(components, list) or len(components) > 500:
        return issues + ["La lista de componentes no es válida"]
    ids = set()
    for c in components:
        if not isinstance(c, dict):
            issues.append("Hay un componente con formato inválido")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not cid or cid in ids:
            issues.append("Cada componente debe tener un ID único")
        ids.add(cid)
        valid_dimensions = True
        for key in ("x", "z", "w", "d", "h", "y"):
            v = c.get(key, 0)
            if not isinstance(v, (int, float)) or not math.isfinite(v) or not -100 <= v <= 100:
                issues.append(f"Componente {cid or '?'}: medida {key} inválida")
                valid_dimensions = False
                break
        if not valid_dimensions:
            continue
        if c.get("w", 0) <= 0 or c.get("d", 0) <= 0 or c.get("h", 0) < 0:
            issues.append(f"Componente {cid or '?'}: ancho y fondo deben ser positivos; altura no negativa")
            continue
        if isinstance(width, (int, float)) and isinstance(length, (int, float)):
            if c.get("x", 0) < -width / 2 - .001 or c.get("x", 0) + c.get("w", 0) > width / 2 + .001:
                issues.append(f"{c.get('name', cid)} excede los límites laterales del terreno")
            if c.get("z", 0) < -length / 2 - .001 or c.get("z", 0) + c.get("d", 0) > length / 2 + .001:
                issues.append(f"{c.get('name', cid)} excede los límites longitudinales del terreno")
    rooms = [c for c in components if isinstance(c, dict) and c.get("type") == "room" and all(isinstance(c.get(k, 0), (int, float)) and math.isfinite(c.get(k, 0)) for k in ("x", "z", "w", "d", "y"))] if isinstance(components, list) else []
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            if abs(a.get("y", 0) - b.get("y", 0)) < .2:
                overlap_x = min(a.get("x", 0) + a.get("w", 0), b.get("x", 0) + b.get("w", 0)) - max(a.get("x", 0), b.get("x", 0))
                overlap_z = min(a.get("z", 0) + a.get("d", 0), b.get("z", 0) + b.get("d", 0)) - max(a.get("z", 0), b.get("z", 0))
                if overlap_x > .02 and overlap_z > .02:
                    issues.append(f"Las habitaciones {a.get('name', a.get('id'))} y {b.get('name', b.get('id'))} se superponen")
    return list(dict.fromkeys(issues))
