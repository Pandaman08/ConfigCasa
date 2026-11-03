package org.casalab.camera

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.os.Bundle
import android.util.Size
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : ComponentActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val client by lazy { OkHttpClient.Builder().readTimeout(0, TimeUnit.MILLISECONDS).build() }
    private val running = AtomicBoolean(false)
    private var socket: WebSocket? = null
    private var preview: PreviewView? = null
    private var status: TextView? = null
    private var cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA
    private var lastFrameAt = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 20, 20, 12) }
        val title = TextView(this).apply { text = "CasaLab Camera · puente USB"; textSize = 20f }
        val host = EditText(this).apply {
            hint = "Host del servidor (default: 127.0.0.1)"
            setText("127.0.0.1")
            singleLine = true
        }
        preview = PreviewView(this).apply { implementationMode = PreviewView.ImplementationMode.COMPATIBLE }
        status = TextView(this).apply { text = "Desconectado"; gravity = Gravity.CENTER_VERTICAL }
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val connect = Button(this).apply { text = "Conectar cámara" }
        val flip = Button(this).apply { text = "Cambiar cámara" }
        row.addView(connect, LinearLayout.LayoutParams(0, -2, 1f)); row.addView(flip, LinearLayout.LayoutParams(0, -2, 1f))
        root.addView(title); root.addView(host); root.addView(preview, LinearLayout.LayoutParams(-1, 0, 1f)); root.addView(status); root.addView(row)
        setContentView(root)

        connect.setOnClickListener {
            val address = host.text.toString().trim().ifBlank { "127.0.0.1" }
            if (running.get()) stopStreaming() else startStreaming(address)
        }
        flip.setOnClickListener {
            cameraSelector = if (cameraSelector == CameraSelector.DEFAULT_BACK_CAMERA) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA
            if (running.get()) bindCamera()
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), 41)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 41 && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) status?.text = "Permiso concedido. Pulsa Conectar cámara."
        else if (requestCode == 41) status?.text = "Permiso de cámara denegado."
    }

    private fun startStreaming(host: String) {
        running.set(true)
        status?.text = "Conectando a ws://$host:8001/camera …"
        val request = Request.Builder().url("ws://$host:8001/camera").build()
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
                runOnUiThread { status?.text = "Conectado · transmitiendo JPEG 640×480"; bindCamera() }
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                running.set(false)
                runOnUiThread { status?.text = "Error de conexión: ${t.localizedMessage ?: "sin respuesta"}" }
            }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                running.set(false); runOnUiThread { status?.text = "Desconectado" }
            }
        })
    }

    private fun bindCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            try {
                val provider = providerFuture.get()
                val previewUseCase = androidx.camera.core.Preview.Builder().build().also { it.setSurfaceProvider(preview?.surfaceProvider) }
                val analysis = ImageAnalysis.Builder().setTargetResolution(Size(640, 480))
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
                analysis.setAnalyzer(executor) { image -> analyze(image) }
                provider.unbindAll()
                provider.bindToLifecycle(this, cameraSelector, previewUseCase, analysis)
            } catch (e: Exception) { runOnUiThread { status?.text = "No se pudo iniciar la cámara: ${e.message}" } }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun analyze(image: ImageProxy) {
        try {
            val now = System.currentTimeMillis()
            if (now - lastFrameAt < 83L || !running.get()) return
            lastFrameAt = now
            val nv21 = yuvToNv21(image)
            val output = ByteArrayOutputStream()
            YuvImage(nv21, ImageFormat.NV21, image.width, image.height, null)
                .compressToJpeg(Rect(0, 0, image.width, image.height), 70, output)
            socket?.send(ByteString.of(*output.toByteArray()))
        } catch (_: Exception) { /* drop a malformed frame; the next fresh frame is used */ }
        finally { image.close() }
    }

    private fun yuvToNv21(image: ImageProxy): ByteArray {
        val width = image.width; val height = image.height
        val out = ByteArray(width * height * 3 / 2)
        val y = image.planes[0]; val u = image.planes[1]; val v = image.planes[2]
        var pos = 0
        for (row in 0 until height) for (col in 0 until width) {
            out[pos++] = y.buffer.get(row * y.rowStride + col * y.pixelStride)
        }
        val chromaHeight = height / 2; val chromaWidth = width / 2
        for (row in 0 until chromaHeight) for (col in 0 until chromaWidth) {
            val vi = row * v.rowStride + col * v.pixelStride
            val ui = row * u.rowStride + col * u.pixelStride
            out[pos++] = v.buffer.get(vi); out[pos++] = u.buffer.get(ui)
        }
        return out
    }

    private fun stopStreaming() {
        running.set(false); socket?.close(1000, "user stopped"); socket = null
        ProcessCameraProvider.getInstance(this).get().unbindAll()
        status?.text = "Desconectado"
    }

    override fun onDestroy() {
        running.set(false); socket?.close(1000, "activity closed"); client.dispatcher.executorService.shutdown()
        executor.shutdown(); super.onDestroy()
    }
}
