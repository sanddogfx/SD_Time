# PyInstaller spec for SD Time — build with:  .\build.ps1   (or: pyinstaller packaging\sd_time.spec)
# One-folder build: Qt stays as separate DLLs (fast start, and LGPL-friendly: the Qt
# libraries can be replaced by the user).
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
VERSION_FILE = os.path.join(ROOT, "build", "version_info.txt")   # written by build.ps1

# Qt modules the app doesn't use; keeps the build small.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtWebSockets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtHttpServer", "PySide6.QtNfc",
    "tkinter", "unittest", "pymupdf", "fitz",
]

a = Analysis(
    [os.path.join(ROOT, "SD_Time.pyw")],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, "assets", "logo.svg"), "assets"),
        (os.path.join(ROOT, "assets", "logo_small.svg"), "assets"),
        (os.path.join(ROOT, "assets", "logo.ico"), "assets"),
        (os.path.join(ROOT, "assets", "ui"), os.path.join("assets", "ui")),
    ],
    hiddenimports=["PySide6.QtSvg"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SD Time",
    icon=os.path.join(ROOT, "assets", "logo.ico"),
    version=VERSION_FILE if os.path.exists(VERSION_FILE) else None,
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SD Time", upx=False)
