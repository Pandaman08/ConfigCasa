# CasaLab

Aplicación local para prototipar viviendas paramétricas, guardar versiones y visualizar el diseño desde Ubuntu o Android. El proyecto trabaja sin Node.js ni paquetes Python obligatorios. Las funciones de IA en la nube, OpenCV/ArUco y la app Android son opcionales.

## Ejecutar

Requiere Python 3.10 o posterior.

```bash
python3 server.py
```

Abre <http://127.0.0.1:8000>. El servidor se enlaza solo a loopback y escucha también el puente WebSocket de cámara en `127.0.0.1:8001`. La base `data/casalab.sqlite3` se crea al iniciar.

## Estructura modular

- `backend/`: servidor HTTP, puente de cámara y paquete `domain/` para validación geométrica e interpretación de requisitos.
- `frontend/`: página y recursos separados en `assets/css/` y `assets/js/`.
- `android-camera/`: aplicación Android CameraX independiente.
- `scripts/`: calibración y conexión ADB.
- `data/`: base SQLite y calibración generadas en ejecución.
- `docs/`: arquitectura, viabilidad y manual.

`python3 server.py` permanece como punto de entrada compatible; la implementación está en `backend/server.py`.

## Capacidades implementadas

- Generación de volúmenes 3D paramétricos a partir de requisitos: terreno, niveles, salas, dormitorios, baños, muros, escaleras, cochera, jardín, ventanas y mobiliario sencillo.
- Edición de dimensiones por selección, cambios acotados mediante texto, materiales, deshacer/rehacer y validación de límites/solapes entre habitaciones.
- Recorrido en primera persona con WASD/flechas y controles táctiles; giroscopio cuando navegador y permiso lo permiten.
- Vista estereoscópica preliminar con dos perspectivas; se informa que se necesita un visor pasivo para una experiencia binocular cómoda.
- Registro, inicio de sesión, roles cliente/diseñador/administrador, proyectos por propietario y versiones inmutables en SQLite.
- Ficha preliminar en TXT; se identifica como no constructiva y sin presupuesto de obra calculado.
- App Android auxiliar CameraX: cámara frontal/trasera, frames JPEG 640 × 480 y 12 FPS objetivo, transmitidos por WebSocket con cola de último frame.
- Puente WebSocket host a navegador; estado ADB/cámara/FPS y superposición de volúmenes cuando se detecta pose ArUco.
- Calibración intrínseca manual, conversión de resolución y uso de coeficientes de distorsión; script de calibración con tablero.
- Interpretación con API de OpenAI configurable y Structured Outputs JSON Schema si existe una clave válida. Sin clave o si el proveedor falla, funciona el extractor local de reglas y la interfaz lo indica.

## Funciones que requieren preparar el equipo

1. **IA remota:** configura `OPENAI_API_KEY`, `OPENAI_MODEL` y opcionalmente `OPENAI_RESPONSES_URL` en el entorno antes de iniciar el servidor. La clave permanece en el servidor. Sin configuración, el sistema usa reglas locales. OpenAI documenta respuestas estructuradas mediante JSON Schema en la [guía de Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
2. **Visión/ArUco:** `python3 -m pip install -r requirements-vision.txt`. Si la distribución no ofrece rueda para tu Python, usa un entorno con Python compatible (por ejemplo, 3.12). Sin `opencv-contrib-python-headless`, se recibe video pero no se afirma seguimiento espacial.
3. **Android:** abre [android-camera/](./android-camera) con Android Studio, sincroniza Gradle e instala `app`. CameraX 1.6.2 es la versión estable consultada en [AndroidX Camera release notes](https://developer.android.com/jetpack/androidx/releases/camera). Este workspace no incluye Android SDK ni Gradle wrapper, así que la compilación debe hacerse en Android Studio con SDK 35 y JDK 17.
4. **USB:** conecta y desbloquea el móvil, activa depuración USB y acepta el diálogo RSA. Con el servidor iniciado, ejecuta `python3 scripts/connect_android.py`; el script configura ADB reverse para 8000 y 8001. En el teléfono abre `http://127.0.0.1:8000` y la app CasaLab Camera.
5. **Calibración:** toma al menos ocho fotos del mismo tablero de ajedrez a 640 × 480, con posiciones y ángulos diferentes, y ejecuta `python3 scripts/calibrate_camera.py ./fotos-tablero`. El script crea `calibration.json`; reinicia el servidor. La interfaz permite introducir intrínsecos manuales y el tamaño real del marcador.

## Verificación local

```bash
python3 -m unittest -v test_server
python3 -m py_compile server.py backend/server.py backend/camera_bridge.py backend/domain/geometry.py backend/domain/requirements.py test_server.py scripts/connect_android.py scripts/calibrate_camera.py
node --check frontend/assets/js/app.js
```

Los tests unitarios cubren parsing offline y validación de geometría. La captura por USB/AR debe validarse con un teléfono y un marcador impresos; no hay evidencia de FPS/latencia del dispositivo en este entorno.

## Documentación

- [FASE1_VIABILIDAD.md](./docs/FASE1_VIABILIDAD.md): análisis, actores, modelo de datos y decisiones iniciales.
- [ARQUITECTURA.md](./docs/ARQUITECTURA.md): componentes, API, persistencia, seguridad y límites técnicos.
- [MANUAL_USUARIO.md](./docs/MANUAL_USUARIO.md): flujo de uso y preparación de Android/AR.

## Límites conocidos

Es un prototipo funcional, no un sistema empresarial listo para clientes reales. Usa Python `http.server` y SQLite, no FastAPI/PostgreSQL; la vista 3D usa Canvas 2D con proyección de volúmenes, no Three.js/GLB; las habitaciones son una propuesta geométrica y requieren revisión de un diseñador; no hay cómputo de presupuesto profesional, planos constructivos, auditoría ni pruebas de accesibilidad. La API local no se debe publicar en red compartida. La app Android y el seguimiento físico no se han compilado/medido en este equipo por falta del SDK, Gradle y teléfono autorizado.
