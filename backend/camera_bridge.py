"""Puente WebSocket local para frames JPEG desde Android y clientes web.

Android se conecta como /camera tras ejecutar `adb reverse tcp:8001 tcp:8001`.
Los clientes del navegador se conectan como /view. OpenCV contrib es opcional;
si falta, se muestra video y se informa que el marcador no se está rastreando.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socketserver
import struct
import threading
import time

MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
LOCK = threading.RLock()
VIEWERS: set[object] = set()
STATUS = {"connected": False, "tracking": False, "message": "Esperando la app Android CameraX", "fps": 0, "pose": None, "frame": None}
CALIBRATION = {"fx": None, "fy": None, "cx": None, "cy": None, "marker_size": 0.08, "source": "aproximada", "image_width": 640, "image_height": 480, "distortion": []}
CV_ERROR = None
try:
    import cv2
    import numpy as np
    if not hasattr(cv2, "aruco"):
        raise ImportError("Instala opencv-contrib-python para habilitar ArUco")
except Exception as exc:  # opcional en equipos sin dependencias de visión
    cv2 = np = None
    CV_ERROR = str(exc)

_last_pose = None
_last_frame_times = []
_last_tracked = 0.0


def ws_send(sock, payload, opcode=1, lock=None):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    n = len(payload)
    head = bytes([0x80 | opcode]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack("!H", n) if n < 65536 else bytes([127]) + struct.pack("!Q", n))
    try:
        if lock:
            with lock:
                sock.sendall(head + payload)
        else:
            sock.sendall(head + payload)
        return True
    except OSError:
        return False


def ws_read(sock):
    def take(n):
        out = bytearray()
        while len(out) < n:
            part = sock.recv(n - len(out))
            if not part:
                raise ConnectionError
            out.extend(part)
        return bytes(out)
    b1, b2 = take(2)
    opcode = b1 & 0x0f
    size = b2 & 0x7f
    if size == 126:
        size = struct.unpack("!H", take(2))[0]
    elif size == 127:
        size = struct.unpack("!Q", take(8))[0]
    if size > 2_000_000:
        raise ValueError("Frame demasiado grande")
    mask = take(4) if b2 & 0x80 else None
    payload = take(size)
    if mask:
        payload = bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
    return opcode, payload


def detect(jpeg):
    global _last_pose, _last_tracked
    if cv2 is None:
        return {"tracking": False, "message": "Video recibido; instala opencv-contrib-python para seguimiento ArUco", "pose": None}
    try:
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return {"tracking": False, "message": "Frame JPEG inválido", "pose": None}
        h, w = frame.shape[:2]
        cal_w, cal_h = CALIBRATION.get("image_width") or w, CALIBRATION.get("image_height") or h
        sx, sy = w / cal_w, h / cal_h
        fx = float(CALIBRATION["fx"] or os.environ.get("AR_FX", w * 1.05)) * sx
        fy = float(CALIBRATION["fy"] or os.environ.get("AR_FY", w * 1.05)) * sy
        cx = (float(CALIBRATION["cx"] if CALIBRATION["cx"] is not None else os.environ.get("AR_CX", w / 2)) + .5) * sx - .5
        cy = (float(CALIBRATION["cy"] if CALIBRATION["cy"] is not None else os.environ.get("AR_CY", h / 2)) + .5) * sy - .5
        marker_size = float(CALIBRATION["marker_size"] or os.environ.get("AR_MARKER_METERS", "0.08"))
        matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float32)
        distortion = CALIBRATION.get("distortion") or [0, 0, 0, 0, 0]
        dist = np.array(distortion, dtype=np.float32).reshape(-1, 1)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        if hasattr(cv2.aruco, "ArucoDetector"):
            detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
            corners, ids, _ = detector.detectMarkers(frame)
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(frame, dictionary)
        if ids is None or len(ids) == 0:
            # Hold a recent pose very briefly to hide one-frame detector jitter.
            if _last_pose and time.monotonic() - _last_tracked < .18:
                return {"tracking": True, "stale": True, "message": "Seguimiento recuperándose", "pose": _last_pose, "frame": [w, h]}
            _last_pose = None
            return {"tracking": False, "message": "Marcador no detectado", "pose": None, "frame": [w, h]}
        rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(corners, marker_size, matrix, dist)
        # Select the largest visible marker and smooth translation/orientation.
        idx = max(range(len(corners)), key=lambda i: cv2.contourArea(corners[i][0]))
        rvec = rvecs[idx][0].reshape(-1).astype(float)
        tvec = tvecs[idx][0].reshape(-1).astype(float)
        pose = {"rvec": rvec.tolist(), "tvec": tvec.tolist(), "fx": fx, "fy": fy, "cx": cx, "cy": cy, "markerSize": marker_size, "markerId": int(ids[idx][0])}
        if _last_pose:
            alpha = .38
            pose["tvec"] = [(1-alpha)*a + alpha*b for a, b in zip(_last_pose["tvec"], pose["tvec"])]
            # Axis-angle interpolation is approximate, adequate for prototype smoothing.
            pose["rvec"] = [(1-alpha)*a + alpha*b for a, b in zip(_last_pose["rvec"], pose["rvec"])]
        _last_pose, _last_tracked = pose, time.monotonic()
        area = cv2.contourArea(corners[idx][0])
        return {"tracking": True, "stale": False, "message": f"ArUco {pose['markerId']} detectado · área {int(area)} px² · calibración {CALIBRATION['source']}", "pose": pose, "frame": [w, h]}
    except Exception as exc:
        return {"tracking": False, "message": f"Error de seguimiento: {exc}", "pose": None}


def broadcast(data, opcode=1):
    with LOCK:
        stale = []
        for sock, send_lock in list(VIEWERS):
            if not ws_send(sock, data, opcode, send_lock):
                stale.append((sock, send_lock))
        for item in stale:
            VIEWERS.discard(item)


class CameraHandler(socketserver.BaseRequestHandler):
    def handle(self):
        global STATUS, _last_frame_times
        sock = self.request
        is_camera = False
        try:
            request = b""
            while b"\r\n\r\n" not in request and len(request) < 8192:
                chunk = sock.recv(1024)
                if not chunk:
                    return
                request += chunk
            headers = request.decode("latin1").split("\r\n")
            path = headers[0].split(" ")[1]
            is_camera = path == "/camera"
            parsed = dict(line.split(":", 1) for line in headers[1:] if ":" in line)
            key = next((v.strip() for k, v in parsed.items() if k.lower() == "sec-websocket-key"), None)
            if not key or path not in ("/camera", "/view"):
                sock.sendall(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
                return
            accept = base64.b64encode(hashlib.sha1((key + MAGIC).encode()).digest()).decode()
            sock.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + accept + "\r\n\r\n").encode())
            if path == "/view":
                sock.settimeout(None)
                send_lock = threading.Lock()
                with LOCK:
                    VIEWERS.add((sock, send_lock))
                    status = json.dumps({"kind": "status", **STATUS}, ensure_ascii=False)
                ws_send(sock, status, lock=send_lock)
                while True:
                    op, _ = ws_read(sock)
                    if op == 8:
                        break
                    if op == 9:
                        ws_send(sock, b"", opcode=10, lock=send_lock)
            else:
                with LOCK:
                    STATUS = {**STATUS, "connected": True, "message": "Android transmite video", "fps": 0}
                broadcast(json.dumps({"kind": "status", **STATUS}, ensure_ascii=False))
                sock.settimeout(4)
                while True:
                    op, payload = ws_read(sock)
                    if op == 8:
                        break
                    if op == 9:
                        ws_send(sock, payload, opcode=10)
                        continue
                    if op != 2:
                        continue
                    state = detect(payload)
                    now = time.monotonic()
                    _last_frame_times = [t for t in _last_frame_times if now - t < 2] + [now]
                    state.update({"kind": "status", "connected": True, "fps": round(len(_last_frame_times) / 2, 1)})
                    with LOCK:
                        STATUS = state
                    broadcast(payload, opcode=2)
                    broadcast(json.dumps(state, ensure_ascii=False))
        except (OSError, ConnectionError, ValueError, UnicodeDecodeError):
            pass
        finally:
            with LOCK:
                VIEWERS.difference_update(x for x in VIEWERS if x[0] is sock)
                if is_camera:
                    STATUS = {**STATUS, "connected": False, "tracking": False, "message": "Teléfono desconectado", "pose": None}
                    broadcast(json.dumps({"kind": "status", **STATUS}, ensure_ascii=False))


class ReusableServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_camera_bridge():
    server = ReusableServer(("127.0.0.1", 8001), CameraHandler)
    threading.Thread(target=server.serve_forever, name="camera-bridge", daemon=True).start()
    return server
