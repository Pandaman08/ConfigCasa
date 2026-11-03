# Fase 1: viabilidad y plan de implementación

## Estado actualizado de la entrega (3 de noviembre de 2026)

Este documento empezó como análisis y plan. El workspace ahora contiene un prototipo web ejecutable con parser local y proveedor OpenAI opcional, geometría paramétrica en Canvas, validación, edición, autenticación por roles, proyectos/versiones en SQLite, recorrido, vista estereoscópica preliminar y un puente WebSocket preparado para Android/ArUco. Hay una app CameraX configurada y una actividad Kotlin que envía frames JPEG; no se ha podido compilar ni probar en un teléfono en este entorno.

Los puntos del plan que siguen pendientes son: migrar a FastAPI/PostgreSQL, usar un motor 3D real como Three.js, ampliar edición arquitectónica y exportación, calcular presupuestos/planos con datos confiables, y validar físicamente cámara USB, calibración, AR y rendimiento con dispositivo real. Los cinco tests unitarios actuales cubren parser offline y validaciones geométricas, no aceptación integral.

## Resumen ejecutivo

El producto es viable como aplicación incremental. La generación de geometría paramétrica, edición de componentes, recorrido 3D, persistencia local y una vista móvil funcionan en un navegador moderno sin hardware especializado. La generación por lenguaje natural puede empezar con un intérprete local de reglas y evolucionar a un proveedor LLM configurable; toda salida debe convertirse a operaciones tipadas y validarse antes de modificar el modelo.

La parte más incierta es obtener la cámara trasera de Android por USB. Android no publica automáticamente su cámara como dispositivo webcam del host al conectar el cable. Para un prototipo robusto conviene una aplicación auxiliar Android basada en CameraX, conectada al backend por ADB port forwarding y WebRTC/HTTP. `scrcpy` transmite la pantalla Android y no debe tratarse como una API de cámara. Como alternativa de demostración, el navegador puede pedir permiso para una webcam disponible en Ubuntu; eso no equivale al flujo USB requerido.

## Viabilidad por capacidad

| Capacidad | Viabilidad | Condiciones / alternativa |
|---|---|---|
| Vivienda 3D editable | Directa | Geometría paramétrica en Three.js; mantener medidas en metros y componentes identificables. |
| Interpretar texto y cambiar componentes | Directa en modo acotado | Parser de reglas para MVP; LLM opcional después, con esquema, validación geométrica y vista previa. |
| Recorrido 3D en PC y móvil | Directa | Controles teclado/táctiles; giroscopio opcional sujeto a permisos del navegador. |
| Vista estereoscópica | Directa como presentación | No sustituye un visor; sin visor pasivo no hay inmersión estereoscópica cómoda. |
| Cámara del móvil sobre USB | Condicional | Requiere app Android auxiliar, depuración USB autorizada y puente local. No asumir que ADB o scrcpy entregan una webcam. |
| AR con marcador | Viable con calibración | Captura de cámara, parámetros intrínsecos y detector ArUco/AprilTag; la pose se pierde cuando el marcador sale de cuadro. |
| ARCore | Condicional al dispositivo | Solo teléfonos certificados con Google Play Services for AR; integración nativa Android recomendada. |
| Persistencia y proyectos | Directa | SQLite para prototipo local; PostgreSQL para despliegue multiusuario. |
| Login/roles y seguridad empresarial | Viable por etapas | Autenticación con hash de contraseñas, sesiones y autorización en servidor; no guardar credenciales en frontend. |
| Planos y presupuesto | Viable como estimación | Reglas y catálogo parametrizados; rotular como preliminar, no como documento constructivo ni cotización final. |

## Arquitectura propuesta

1. **Web objetivo:** React, TypeScript, Vite y Three.js para la UI y el modelo editable. **Prototipo actual:** HTML/CSS/JavaScript sin bundler y Canvas 2D con proyección axonométrica.
2. **API objetivo:** Python, FastAPI y Pydantic; WebSocket para actualizaciones. SQLAlchemy con SQLite local y PostgreSQL al desplegar. **Prototipo actual:** `http.server` de Python, SQLite directo y un puente WebSocket independiente.
3. **Modelo del proyecto:** JSON versionado, unidades en metros, habitaciones/componentes con IDs estables y operaciones explícitas (añadir, mover, cambiar dimensiones/material).
4. **IA:** proveedor intercambiable detrás de una interfaz; salida JSON validada. Nunca ejecutar código ni aceptar geometría del LLM sin límites y comprobaciones.
5. **AR USB:** app Android CameraX -> conexión local reenviada por ADB -> servicio de video; OpenCV en backend detecta marcador y estima pose; visor compone cámara y escena. Añadir calibración por dispositivo y estado de tracking.
6. **VR:** recorrido convencional como modo base. Giroscopio si está permitido; modo estereoscópico opcional. WebXR solo como mejora, dado que requiere contexto seguro y el soporte del navegador/dispositivo varía.
7. **Persistencia y despliegue:** SQLite en desarrollo; migración a PostgreSQL y Docker Compose cuando estén instalados los componentes. Proyectos guardan requisitos, diseño y versiones.

## MVP y límites de alcance

El primer incremento demostrable debe permitir crear un proyecto de vivienda desde texto, producir geometría 3D editable con dimensiones legibles, ajustar al menos habitaciones/materiales, deshacer/rehacer, guardar versiones y recorrer la escena desde PC/móvil. Debe presentar estado de conexión/cámara sin simular detección USB. El soporte de cámara USB y AR se incorpora cuando exista una app Android auxiliar probada con el teléfono real. Mientras tanto, cualquier cámara accesible al navegador sirve únicamente para validar composición visual manual, no seguimiento AR.

### Actores y casos de uso

- **Cliente:** crear proyecto, describir vivienda, revisar propuesta, solicitar cambios, explorar, guardar y exportar ficha preliminar.
- **Diseñador:** ajustar geometría/materiales, corregir restricciones, comparar versiones y compartir una propuesta.
- **Administrador:** gestionar usuarios, roles, catálogo y parámetros de costes.
- **Sistema:** validar terreno y colisiones, versionar cambios, detectar la pérdida de cámara/marcador y exponer diagnósticos claros.

### Modelo de datos inicial

- `User(id, email, password_hash, role)`
- `Project(id, owner_id, name, requirements_json, created_at, updated_at)`
- `DesignVersion(id, project_id, sequence, model_json, change_summary, created_at)`
- `Component(id, type, level, dimensions, position, material, properties)`
- `Operation(id, project_id, version_id, kind, target_ids, parameters, source, created_at)`

El modelo serializado conserva IDs y unidades. Las versiones son inmutables; cada edición genera una versión nueva y el historial de operaciones hace posible auditar cambios y soportar undo/redo.

## Riesgos, dependencias y mitigaciones

- **Modelo de teléfono desconocido:** verificar fabricante/modelo/Android, cámara y compatibilidad ARCore antes de prometer ARCore; mantener modo marcador y modo 3D como fallback.
- **Acceso a cámara USB:** prototipar CameraX + ADB forwarding temprano; separar captura, transporte y tracking para poder cambiar el puente.
- **Calibración/estabilidad:** calibrar cada cámara y resolución; filtrar pose suavemente; mostrar confianza y estado de pérdida del marcador.
- **Latencia y calor móvil:** adaptar resolución/FPS y nivel de detalle; medir en el dispositivo real antes de fijar objetivos.
- **IA cambia geometría inválida:** operaciones tipadas, límites del terreno, detección de solapes y previsualización antes de confirmar.
- **Seguridad y privacidad:** consentimiento explícito para cámara, API local con autenticación cuando se exponga en red, no registrar video y proteger secretos en servidor.
- **Prototipo offline:** fijar dependencias y preparar documentación de instalación; no depender de servicios externos para el recorrido paramétrico básico.

## Fases de implementación y aceptación

1. Viabilidad, actores, arquitectura, riesgos y modelo de datos (este documento).
2. Aplicación base, proyectos, persistencia y autenticación/roles.
3. Geometría paramétrica, navegación y validación de modelo.
4. Interpretación estructurada de generación/modificación e historial.
5. App CameraX, puente USB y métricas de captura. Fuente Android escrita; faltan compilación e integración física.
6. Marcador, calibración, estimación de pose y composición AR. Código opcional OpenCV/ArUco y superposición disponibles; falta validar detección/calibración con cámara y marcador reales.
7. Recorrido móvil, orientación opcional y estereoscopía.
8. Materiales, ficha preliminar y exportación.
9. Pruebas automatizadas y de aceptación con teléfono y marcador reales.
10. Manual, documentación API, despliegue y limitaciones.

Para considerar aceptados los puntos USB/AR se requiere una demostración física con teléfono Android, autorización ADB, cámara trasera, marcador impreso y seguimiento medido. No se deben declarar aprobados mediante simulación o webcam de PC.

## Referencias técnicas consultadas

- Android Developers, [selección de biblioteca de cámara](https://developer.android.com/media/camera/choose-camera-library): CameraX como API de alto nivel con soporte amplio.
- Google, [dispositivos compatibles con ARCore](https://developers.google.com/ar/devices): la compatibilidad es certificada por modelo según cámara, sensores y rendimiento.
- MDN, [WebXR Device API](https://developer.mozilla.org/en-US/docs/Web/API/WebXR_Device_API): disponibilidad limitada y requisito de contexto seguro.
- OpenCV, [módulo ArUco](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html): detección de marcadores y estimación de pose con parámetros de cámara.

## Entorno observado al iniciar

- Ubuntu/Linux, Python 3.14 y ADB/scrcpy disponibles.
- Node.js 22 disponible, pero `npm` no está instalado.
- No hay frontend/backend preexistente, base de datos ni dependencias Python del stack propuestas.
- No se ha identificado ni probado el modelo Android; no se dispone de resultados reales de FPS, latencia o seguimiento.

Por tanto, la primera entrega debe ser un prototipo local ejecutable con dependencias mínimas y declarar explícitamente qué capacidades de cámara/AR quedan pendientes de hardware real.
