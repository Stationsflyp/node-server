import uuid
import os
import sqlite3
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Tu IP pública y puerto
PUBLIC_IP = "64.181.220.231"
PORT = 8000

# Carpeta de uploads
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- BASE DE DATOS ----------
def init_db():
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            token TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            stored_as TEXT,
            owner TEXT
        )
        """)
        conn.commit()

init_db()

# ---------- AUTENTICACIÓN ----------
def auth_user(token: str = Form(...)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(403, "Token inválido")
        return row[0]

@app.post("/auth_discord")
def auth_discord(username: str = Form(...)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM users WHERE username=?", (username,))
        row = cursor.fetchone()
        if row:
            return {"username": username, "token": row[0]}
        new_token = str(uuid.uuid4())
        cursor.execute("INSERT INTO users (username, token) VALUES (?, ?)", (username, new_token))
        conn.commit()
        return {"username": username, "token": new_token}

# ---------- SUBIR ARCHIVO ----------
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), token: str = Form(...)):
    # Validar usuario
    user = auth_user(token)

    ext = file.filename.split(".")[-1]
    file_id = str(uuid.uuid4())
    saved_name = f"{file_id}.{ext}"
    path = os.path.join(UPLOAD_DIR, saved_name)

    with open(path, "wb") as f:
        f.write(await file.read())

    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO files (filename, stored_as, owner) VALUES (?, ?, ?)",
            (file.filename, saved_name, user)
        )
        conn.commit()

    download_url = f"http://{PUBLIC_IP}:{PORT}/download/{saved_name}"
    return {"success": True, "filename_original": file.filename, "file_id": saved_name, "download_url": download_url}

# ---------- LISTAR ARCHIVOS ----------
@app.post("/my_files")
def list_files(token: str = Form(...)):
    user = auth_user(token)
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, stored_as FROM files WHERE owner=?", (user,))
        files = cursor.fetchall()
    return {"files": [{"id": f[0], "name": f[1], "stored": f[2]} for f in files]}

# ---------- DESCARGAR ----------
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

# ---------- ELIMINAR ----------
@app.post("/delete")
def delete_file(file_id: str = Form(...), token: str = Form(...)):
    user = auth_user(token)
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT stored_as FROM files WHERE stored_as=? AND owner=?", (file_id, user))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Archivo no encontrado o sin permisos")

        cursor.execute("DELETE FROM files WHERE stored_as=?", (file_id,))
        conn.commit()

    path = os.path.join(UPLOAD_DIR, file_id)
    if os.path.exists(path):
        os.remove(path)

    return {"success": True, "deleted": file_id}
