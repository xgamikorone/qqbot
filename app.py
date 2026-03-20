from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
import shutil
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法（GET、POST、PUT等）
    allow_headers=["*"],  # 允许所有头部
)

@app.get("/download/{filename}")
async def download_file(filename: str):

    if not os.path.exists(filename):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        filename,
        filename=filename,
        media_type="application/octet-stream"
    )