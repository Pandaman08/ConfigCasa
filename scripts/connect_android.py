#!/usr/bin/env python3
"""Autoriza el enlace USB del teléfono a las rutas locales de CasaLab."""
import argparse
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="serial ADB cuando haya más de un dispositivo")
    args = parser.parse_args()
    adb = shutil.which("adb")
    if not adb:
        print("No se encontró adb. Instala Android platform-tools.", file=sys.stderr)
        return 2
    result = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True, timeout=5)
    rows = [line.split() for line in result.stdout.splitlines()[1:] if line.strip()]
    ready = [row for row in rows if len(row) >= 2 and row[1] == "device"]
    unauthorized = [row for row in rows if len(row) >= 2 and row[1] == "unauthorized"]
    if args.serial:
        ready = [row for row in ready if row[0] == args.serial]
    elif len(ready) > 1:
        print("Hay varios Android autorizados. Elige uno con --serial:")
        print(result.stdout)
        return 2
    if not ready:
        print(result.stdout.strip() or "No hay dispositivos ADB")
        if unauthorized:
            print("Desbloquea Android y acepta el diálogo de depuración USB.")
        else:
            print("Comprueba cable de datos, depuración USB y autorización ADB.")
        return 1
    serial = ready[0][0]
    for port in (8000, 8001):
        reverse = subprocess.run([adb, "-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}"], capture_output=True, text=True, timeout=5)
        if reverse.returncode:
            print(reverse.stderr.strip() or f"No se pudo reenviar el puerto {port}", file=sys.stderr)
            return reverse.returncode
    print(f"Android conectado ({serial}). En el móvil abre http://127.0.0.1:8000")
    print("En esa página el modo móvil y el botón de orientación usan la app web local.")
    print("Abre CasaLab Camera y pulsa Iniciar cámara para enviar video a :8001.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
