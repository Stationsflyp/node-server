import uuid
import os
import sqlite3
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Tu IP pública y puerto
PUBLIC_IP = "64.181.220.231"
PORT = 8000

# Crear carpeta de uploads
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

# CORS para permitir peticiones desde cualquier front
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- BASE DE DATOS ----------
def init_db():
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            stored_as TEXT
        )
        """)
        conn.commit()

init_db()

# -------- SUBIR ARCHIVO --------
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), token: str = Form(...)):
    # Aquí puedes validar el token si quieres
    ext = file.filename.split(".")[-1]
    file_id = str(uuid.uuid4())
    saved_name = f"{file_id}.{ext}"
    path = os.path.join(UPLOAD_DIR, saved_name)

    with open(path, "wb") as f:
        f.write(await file.read())

    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO files (filename, stored_as) VALUES (?, ?)",
            (file.filename, saved_name)
        )
        conn.commit()

    download_url = f"http://{PUBLIC_IP}:{PORT}/download/{saved_name}"
    return {
        "success": True,
        "filename_original": file.filename,
        "file_id": saved_name,
        "download_url": download_url
    }

# -------- LISTAR ARCHIVOS --------
@app.get("/files")
def list_files():
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, stored_as FROM files")
        files = cursor.fetchall()
    return {"files": [{"id": f[0], "name": f[1], "stored": f[2]} for f in files]}

# Alias POST para compatibilidad con front (acepta token)
@app.post("/my_files")
def my_files_alias(token: str = Form(...)):
    # Opcional: validar token
    return list_files()

# -------- DESCARGAR --------
@app.get("/download/{file_id}")
def download(file_id: str):
    path = os.path.join(UPLOAD_DIR, file_id)
    if not os.path.exists(path):
        raise HTTPException(404, "Archivo no existe")

    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM files WHERE stored_as=?", (file_id,))
        row = cursor.fetchone()
        original_name = row[0] if row else file_id

    return FileResponse(path, filename=original_name)

# -------- ELIMINAR ARCHIVO --------
@app.post("/delete")
def delete_file(token: str = Form(...), file_id: str = Form(...)):
    # Opcional: validar token
    path = os.path.join(UPLOAD_DIR, file_id)
    if not os.path.exists(path):
        raise HTTPException(404, "Archivo no existe")

    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE stored_as=?", (file_id,))
        conn.commit()

    os.remove(path)
    return {"success": True, "deleted": file_id}
