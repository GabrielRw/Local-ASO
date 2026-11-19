# PyInstaller spec for the server bundled inside the Tauri app.
# Build: uv run --with pyinstaller pyinstaller --noconfirm --distpath desktop/build \
#        --workpath desktop/build/pyinstaller desktop/aso-server.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

datas = []
# Alembic loads revision scripts from disk and the dashboard serves its built assets
# through importlib.resources, so both ship as files next to the package.
datas += collect_data_files("local_aso_tracker", include_py_files=True, subdir="migrations")
datas += collect_data_files("local_aso_tracker", subdir="web/static")
datas += collect_data_files("local_aso_tracker", subdir="services/data")
for distribution in ("mcp", "uvicorn", "pydantic", "typer", "rich", "httpx", "alembic", "sqlalchemy"):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        pass

hiddenimports = []
hiddenimports += collect_submodules("local_aso_tracker", filter=lambda name: ".migrations" not in name)
hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["sqlalchemy.dialects.sqlite"]

a = Analysis(
    ["server_entry.py"],
    pathex=["../src"],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "mypy", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aso-server",
    console=True,
    strip=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="aso-server")
