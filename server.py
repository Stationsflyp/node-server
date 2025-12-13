import uuid
import os
import sqlite3
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# ---------------- CONFIG ----------------
UPLOAD_DIR = "uploads"
DB_NAME = "database.db"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

# CORS (producción)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://oxcyshopcloud.netlify.app",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- DATABASE ----------------
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            token TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            stored_as TEXT,
            owner TEXT,
            password TEXT
        )
        """)

        conn.commit()

init_db()

# ---------------- AUTH ----------------
def auth_user(token: str = Form(...)):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(403, "Token inválido")
        return row[0]

# ---------------- CREATE TOKEN ----------------
@app.post("/create_token")
def create_token(username: str = Form(...)):
    token = str(uuid.uuid4())
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (username, token) VALUES (?, ?)",
            (username, token)
        )
        conn.commit()
    return {"username": username, "token": token}

# ---------------- DISCORD AUTH ----------------
@app.post("/auth_discord")
def auth_discord(username: str = Form(...)):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM users WHERE username=?", (username,))
        row = cursor.fetchone()

        if row:
            return {"username": username, "token": row[0]}

        token = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO users (username, token) VALUES (?, ?)",
            (username, token)
        )
        conn.commit()
        return {"username": username, "token": token}

# ---------------- UPLOAD ----------------
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: str = Depends(auth_user)
):
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    file_id = f"{uuid.uuid4()}.{ext}"
    path = os.path.join(UPLOAD_DIR, file_id)

    with open(path, "wb") as f:
        f.write(await file.read())

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO files (filename, stored_as, owner) VALUES (?, ?, ?)",
            (file.filename, file_id, user)
        )
        conn.commit()

    return {
        "success": True,
        "file_id": file_id,
        "download_url": f"/download/{file_id}"
    }

# ---------------- LIST FILES ----------------
@app.post("/my_files")
def my_files(token: str = Form(...)):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(403, "Token inválido")

        cursor.execute(
            "SELECT id, filename, stored_as FROM files WHERE owner=?",
            (user[0],)
        )
        files = cursor.fetchall()

    return {"files": [
        {"id": f[0], "name": f[1], "file_id": f[2]} for f in files
    ]}

# ---------------- DOWNLOAD ----------------
@app.get("/download/{file_id}")
def download(file_id: str, password: str = None):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT filename, password FROM files WHERE stored_as=?",
            (file_id,)
        )
        row = cursor.fetchone()

    if not row:
        raise HTTPException(404, "Archivo no existe")

    if row[1] and row[1] != password:
        raise HTTPException(403, "Contraseña incorrecta")

    path = os.path.join(UPLOAD_DIR, file_id)
    return FileResponse(path, filename=row[0])

# ---------------- SET PASSWORD ----------------
@app.post("/set_password")
def set_password(
    file_id: str = Form(...),
    password: str = Form(...),
    token: str = Form(...)
):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(403, "Token inválido")

        cursor.execute(
            "UPDATE files SET password=? WHERE stored_as=? AND owner=?",
            (password, file_id, user[0])
        )
        conn.commit()

    return {"success": True}

# ---------------- DELETE ----------------
@app.post("/delete")
def delete_file(file_id: str = Form(...), token: str = Form(...)):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(403, "Token inválido")

        cursor.execute(
            "SELECT stored_as FROM files WHERE stored_as=? AND owner=?",
            (file_id, user[0])
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Sin permisos")

        path = os.path.join(UPLOAD_DIR, file_id)
        if os.path.exists(path):
            os.remove(path)

        cursor.execute("DELETE FROM files WHERE stored_as=?", (file_id,))
        conn.commit()

    return {"success": True}
