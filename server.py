import uuid
import os
import sqlite3
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Crear carpetas
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

# CORS para que la web pueda hacer fetch()
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


# -------- VALIDAR TOKEN ----------
def auth_user(token: str = Form(...)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        data = cursor.fetchone()
        if not data:
            raise HTTPException(status_code=403, detail="Token inválido")
        return data[0]


# -------- CREAR TOKEN (admin) --------
@app.post("/create_token")
def create_token(username: str = Form(...)):
    new_token = str(uuid.uuid4())
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, token) VALUES (?, ?)", (username, new_token))
        conn.commit()
    return {"username": username, "token": new_token}


# -------- AUTH DISCORD (Login/Register) --------
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


# -------- SUBIR ARCHIVO --------
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), user: str = Depends(auth_user)):
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

    return {
        "success": True,
        "filename_original": file.filename,
        "file_id": saved_name,
        "download_url": f"/download/{saved_name}"
    }


# -------- LISTAR ARCHIVOS DEL USUARIO --------
@app.post("/my_files")
def list_files(token: str = Form(...)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(403, "Token inválido")
        username = row[0]

        cursor.execute("SELECT id, filename, stored_as FROM files WHERE owner=?", (username,))
        files = cursor.fetchall()

    return {
        "owner": username,
        "files": [{"id": f[0], "name": f[1], "stored": f[2]} for f in files]
    }


# -------- DESCARGAR --------
@app.get("/download/{file_id}")
def download(file_id: str):
    path = os.path.join(UPLOAD_DIR, file_id)
    if not os.path.exists(path):
        raise HTTPException(404, "Archivo no existe")
    # Mantener el nombre original en la descarga
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM files WHERE stored_as=?", (file_id,))
        row = cursor.fetchone()
        original_name = row[0] if row else file_id
    return FileResponse(path, filename=original_name)


# -------- ESTABLECER CONTRASEÑA --------
@app.post("/set_password")
def set_password(file_id: str = Form(...), password: str = Form(...), token: str = Form(...)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(403, "Token inválido")
        username = row[0]

        cursor.execute("SELECT stored_as FROM files WHERE stored_as=? AND owner=?", (file_id, username))
        if not cursor.fetchone():
            raise HTTPException(404, "Archivo no encontrado o no tienes permisos")

        try:
            cursor.execute("ALTER TABLE files ADD COLUMN password TEXT")
        except sqlite3.OperationalError:
            pass

        cursor.execute("UPDATE files SET password=? WHERE stored_as=?", (password, file_id))
        conn.commit()

    return {"success": True}


# -------- ELIMINAR ARCHIVO --------
@app.post("/delete")
def delete_file(file_id: str = Form(...), token: str = Form(...)):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE token=?", (token,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(403, "Token inválido")
        username = row[0]

        cursor.execute("SELECT stored_as FROM files WHERE stored_as=? AND owner=?", (file_id, username))
        file_row = cursor.fetchone()
        if not file_row:
            raise HTTPException(404, "No tienes permisos para borrar este archivo")

        stored_file = file_row[0]
        path = os.path.join(UPLOAD_DIR, stored_file)

        if os.path.exists(path):
            os.remove(path)

        cursor.execute("DELETE FROM files WHERE stored_as=?", (stored_file,))
        conn.commit()

    return {"success": True, "deleted": stored_file}
