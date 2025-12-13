import uuid
import os
import sqlite3
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

PUBLIC_IP = "64.181.220.231"
PORT = 8000
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------- DB -----------
def init_db():
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                token TEXT UNIQUE
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

# ----------- Auth -----------
def auth_user(token: str = Form(...)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(403, "Token inválido")
        return row[0]  # devuelve el username asociado al token

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

# ----------- Upload -----------
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), username: str = Depends(auth_user)):
    ext = file.filename.split(".")[-1]
    file_id = str(uuid.uuid4())
    saved_name = f"{file_id}.{ext}"
    path = os.path.join(UPLOAD_DIR, saved_name)

    # Guardar archivo
    with open(path, "wb") as f:
        f.write(await file.read())

    # Guardar info en DB
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO files (filename, stored_as, owner) VALUES (?, ?, ?)",
            (file.filename, saved_name, username)
        )
        conn.commit()

    download_url = f"http://{PUBLIC_IP}:{PORT}/download/{saved_name}"
    return {"success": True, "filename_original": file.filename, "file_id": saved_name, "download_url": download_url}

# ----------- List files -----------
@app.post("/my_files")
def list_files(username: str = Depends(auth_user)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, stored_as FROM files WHERE owner=?", (username,))
        files = cursor.fetchall()
    return {"files": [{"id": f[0], "name": f[1], "stored": f[2]} for f in files]}

# ----------- Download -----------
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

# ----------- Delete -----------
@app.post("/delete")
def delete_file(file_id: str = Form(...), username: str = Depends(auth_user)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT stored_as FROM files WHERE stored_as=? AND owner=?", (file_id, username))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Archivo no encontrado o sin permisos")

        cursor.execute("DELETE FROM files WHERE stored_as=?", (file_id,))
        conn.commit()

    path = os.path.join(UPLOAD_DIR, file_id)
    if os.path.exists(path):
        os.remove(path)

    return {"success": True, "deleted": file_id}
