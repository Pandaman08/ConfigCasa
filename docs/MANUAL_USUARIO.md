# Manual de usuario

## 1. Iniciar y crear una cuenta

1. En Ubuntu abre una terminal en la carpeta del proyecto y ejecuta `python3 server.py`.
2. En Chrome/Chromium abre `http://127.0.0.1:8000`.
3. Pulsa **Iniciar sesión → Crear cuenta**. La primera cuenta recibe rol administrador; las siguientes reciben rol cliente.
4. Si eres administrador, abre **Proyectos / versiones → Gestionar usuarios y roles** para asignar diseñador o administrador.

Sin iniciar sesión puedes generar y editar en el navegador, pero el guardado en el servidor necesita una cuenta. El guardado local del navegador sigue disponible.

## 2. Generar y ajustar una vivienda

1. Describe terreno, niveles, estilo, dormitorios y baños en el panel izquierdo.
2. Elige estilo y, si tienes una cifra propia, ingresa presupuesto aproximado en soles.
3. Pulsa **Generar propuesta**. Si hay proveedor configurado, se muestran requisitos extraídos por IA estructurada; si el proveedor no está disponible, la interfaz indica que usó reglas locales.
4. Arrastra sobre la maqueta para girarla; usa `+` y `−` para zoom.
5. Haz clic en un volumen. Sus dimensiones aparecen en **Elemento seleccionado**; aplica ancho y fondo y revisa que el estado siga en verde.
6. Escribe una modificación breve en el panel izquierdo. El prototipo entiende instrucciones como ampliar sala/cocina, añadir isla, ampliar jardín, cambiar fachada, añadir ventana o baño. Cada cambio aplica a componentes identificados y pasa validación antes de conservarse.
7. Usa deshacer/rehacer para navegar los cambios. Cambiar terreno reconstruye la distribución inicial.
8. Pulsa **Guardar** para añadir un snapshot; **Proyectos / versiones** permite cargar proyectos y versiones anteriores.
9. Pulsa **Exportar ficha** para descargar TXT preliminar.

## 3. Recorrido y visualización móvil

- **Recorrido:** pulsa la pestaña y muévete con WASD/flechas. En pantalla táctil hay controles de dirección; arrastrar cambia la mirada. Este recorrido es una maqueta interior simplificada, no un walkthrough BIM completo.
- **Móvil VR:** muestra dos perspectivas separadas. Activa el botón `◎` para solicitar orientación del teléfono si el navegador la soporta. Una pantalla dividida sin visor pasivo no sustituye gafas VR.
- **Abrir web en Android por USB:** con el servidor local activo, `python3 scripts/connect_android.py` ejecuta `adb reverse tcp:8000 tcp:8000`. Abre `http://127.0.0.1:8000` en Chrome Android. Para orientación, concede el permiso que solicita el navegador.

## 4. Cámara USB y AR con marcador

### Preparar el teléfono

1. Instala y abre `android-camera` desde Android Studio; permite acceso a cámara.
2. Activa **Opciones de desarrollador → Depuración USB**, conecta un cable de datos y acepta la autorización RSA.
3. Ejecuta `python3 scripts/connect_android.py`. Si hay varios dispositivos, usa `--serial SERIAL`.
4. En CasaLab abre **Cámara / AR → Abrir vista del teléfono**.
5. En el teléfono abre **CasaLab Camera** y pulsa **Iniciar cámara trasera**. Cambia frontal/trasera solo si lo necesitas.
6. La aplicación recibe JPEG a 640 × 480 y objetivo de 12 FPS. La medida real depende del teléfono y del host.

### Activar el seguimiento

1. Instala OpenCV contrib con `python3 -m pip install -r requirements-vision.txt` y reinicia el servidor.
2. Desde el panel de calibración, abre el marcador ArUco 4×4 ID 0. Imprímelo cuadrado a 8 × 8 cm, sin redimensionar, y ponlo plano.
3. Calibra la cámara con al menos ocho fotos de tablero; usa `python3 scripts/calibrate_camera.py CARPETA_FOTOS`. El archivo generado debe corresponder a 640 × 480 o escala los intrínsecos con la resolución correcta.
4. Reinicia el servidor después de crear `data/calibration.json`. La fuente de pose aplica los coeficientes intrínsecos/distorsión almacenados.
5. Mantén el marcador dentro del cuadro. El panel indica si se detecta, FPS y estado de pérdida. Al taparse el marcador desaparece el overlay: no hay seguimiento inercial ni oclusión de profundidad.

La alternativa **Usar cámara disponible en esta PC** solo muestra una fuente de cámara que ofrezca el navegador; no equivale al USB Android ni activa seguimiento por marcador.

## 5. Configurar IA opcional

Exporta una clave válida en `OPENAI_API_KEY`, fija `OPENAI_MODEL` y luego inicia el servidor. No pegues la clave en la página ni en el repositorio. Los requisitos se piden en un esquema JSON restringido; ante error de API se conserva la generación con reglas locales. Las modificaciones geométricas las valida el motor local y no se ejecuta código producido por el modelo.

## 6. Diagnóstico

- **ADB dice unauthorized:** desbloquea Android, confirma el diálogo RSA y vuelve a ejecutar el script.
- **ADB no encuentra equipo:** revisa cable de datos, depuración USB y `adb devices -l`.
- **No se abre la vista :8001:** confirma que el servidor está ejecutándose y repite `scripts/connect_android.py`.
- **Se ve video y no aparece maqueta:** revisa `vision_dependency` en `/api/health`; instala OpenCV contrib, imprime el ID 0 exacto y guarda calibración.
- **El modelo sale inestable:** revisa que el marcador sea plano, ocupe un área visible y el tamaño impreso coincida con el tamaño real configurado.
- **Error OpenAI:** quita o reemplaza la clave inválida; la app cae a reglas locales e informa su procedencia.

## Limitaciones

La salida no es plano constructivo, cálculo estructural ni presupuesto de contratista. El prototipo no incluye correo de recuperación, MFA, despliegue multiusuario remoto, sincronización cloud, exportación GLB, edición de cada pared por arrastre ni pruebas de rendimiento en teléfono real.
