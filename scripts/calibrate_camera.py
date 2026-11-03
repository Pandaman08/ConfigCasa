#!/usr/bin/env python3
"""Calibra intrínsecos con fotos de tablero y emite calibration.json de CasaLab."""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", type=Path, help="carpeta con fotos nítidas del mismo tablero")
    parser.add_argument("--columns", type=int, default=9, help="esquinas internas horizontales")
    parser.add_argument("--rows", type=int, default=6, help="esquinas internas verticales")
    parser.add_argument("--square-mm", type=float, default=25, help="lado de una celda en milímetros")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "calibration.json")
    parser.add_argument("--marker-size", type=float, default=.08, help="lado del marcador ArUco en metros")
    args = parser.parse_args()
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("Falta OpenCV: instala requirements-vision.txt", file=sys.stderr)
        return 2
    if args.columns < 3 or args.rows < 3 or args.square_mm <= 0:
        parser.error("el tablero requiere al menos 3 × 3 esquinas y un tamaño positivo")
    files = [p for p in args.images.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    if len(files) < 8:
        print("Se requieren al menos 8 fotografías del tablero en distintas posiciones y ángulos.", file=sys.stderr)
        return 2
    pattern = (args.columns, args.rows)
    object_points = np.zeros((args.columns * args.rows, 3), np.float32)
    object_points[:, :2] = np.mgrid[0:args.columns, 0:args.rows].T.reshape(-1, 2) * (args.square_mm / 1000.0)
    object_sets, image_sets = [], []
    frame_size = None
    for file in files:
        image = cv2.imread(str(file))
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        size = (gray.shape[1], gray.shape[0])
        if frame_size is None:
            frame_size = size
        elif frame_size != size:
            print(f"Tamaño distinto en {file.name}: {size}, se esperaba {frame_size}", file=sys.stderr)
            return 2
        found, corners = cv2.findChessboardCorners(gray, pattern, None)
        if not found:
            print(f"Tablero no detectado: {file.name}")
            continue
        refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, .001))
        object_sets.append(object_points.copy())
        image_sets.append(refined)
    if len(image_sets) < 8:
        print(f"Solo se detectaron {len(image_sets)} tableros válidos; agrega más imágenes.", file=sys.stderr)
        return 2
    rms, matrix, distortion, _, _ = cv2.calibrateCamera(object_sets, image_sets, frame_size, None, None)
    width, height = frame_size
    result = {
        "fx": float(matrix[0, 0]), "fy": float(matrix[1, 1]),
        "cx": float(matrix[0, 2]), "cy": float(matrix[1, 2]),
        "marker_size": args.marker_size, "source": "calibración de tablero",
        "image_width": width, "image_height": height,
        "rms_reprojection_error_px": float(rms),
        "distortion": [float(v) for v in distortion.reshape(-1)],
    }
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Calibración guardada: {args.output} · {len(image_sets)} imágenes · RMS {rms:.3f} px · {width} × {height}")
    print("El puente usa coeficientes intrínsecos y aplica distorsión cero; la distorsión se informa para revisión.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
