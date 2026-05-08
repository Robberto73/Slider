"""
Kimi PPTD Agent — веб-сервис для генерации презентаций.
FastAPI + подключаемые агенты (локальная LLM / GigaChat).
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import threading
from fastapi import BackgroundTasks
from pydantic import BaseModel

from converter import KimiPptdConverter, convert_project_to_pptx
from agent import create_agent

# ═══════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════
BASE_DIR = Path(__file__).parent

app = FastAPI(title="Kimi PPTD Agent", version="2.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

PROJECTS_DIR = BASE_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

ICONS_DIR = BASE_DIR / "icons"

DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "local")
LOCAL_LLM_URL = os.environ.get("LOCAL_LLM_URL", "http://localhost:5000/v1")


class PresentationRequest(BaseModel):
    topic: str
    slides_count: int = 7
    style: str = "dark"
    language: str = "ru"
    tone: str = "professional"
    include_charts: bool = True
    include_icons: bool = True
    model_type: str = DEFAULT_MODEL


# ═══════════════════════════════════════════════════════════
# СТРАНИЦЫ
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request = request,
        name = "index.html",
        context= {"title": "Генерация презентации"})


@app.get("/converter", response_class=HTMLResponse)
async def converter_page(request: Request):
    return templates.TemplateResponse(
        request = request,
        name = "converter.html",
        context = {"title": "Конвертер PPTD → PPTX"})


# ═══════════════════════════════════════════════════════════
# API ГЕНЕРАЦИИ
# ═══════════════════════════════════════════════════════════

@app.post("/api/generate")
async def generate_presentation(request: PresentationRequest, background_tasks: BackgroundTasks):
    project_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    proj_dir = PROJECTS_DIR / project_id
    proj_dir.mkdir(exist_ok=True)

    # Сохраняем метаданные
    meta = {
        "topic": request.topic,
        "slides_count": request.slides_count,
        "style": request.style,
        "language": request.language,
        "tone": request.tone,
        "include_charts": request.include_charts,
        "include_icons": request.include_icons,
        "model_type": request.model_type,
        "status": "generating",
        "progress": 0,
        "message": "Инициализация...",
        "created": datetime.now().isoformat(),
    }
    with open(proj_dir / "meta.json", 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    try:
        # Создаём агента
        agent = create_agent(
            request.model_type,
            local_base_url=LOCAL_LLM_URL,
            icons_dir=ICONS_DIR
        )

        # Генерируем проект (.pptd и .page)
        agent.generate(
            topic=request.topic,
            slides_count=request.slides_count,
            style=request.style,
            language=request.language,
            include_charts=request.include_charts,
            include_icons=request.include_icons,
            output_dir=proj_dir
        )

        # Конвертируем в PPTX
        output_pptx = proj_dir / f"{project_id}.pptx"
        converter = KimiPptdConverter(icons_base_dir=ICONS_DIR)
        converter.convert(str(proj_dir), str(output_pptx))

        # Обновляем статус
        meta["status"] = "completed"
        meta["converted"] = datetime.now().isoformat()
        with open(proj_dir / "meta.json", 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return JSONResponse({
            "status": "completed",
            "message": "Презентация готова",
            "project_id": project_id,
            "download_url": f"/api/download/{project_id}",
        })
    except Exception as e:
        meta["status"] = "error"
        meta["error"] = str(e)
        with open(proj_dir / "meta.json", 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        raise HTTPException(500, detail=str(e))


@app.get("/api/generate-status/{project_id}")
async def generate_status(project_id: str):
    proj_dir = PROJECTS_DIR / project_id
    if not proj_dir.exists():
        raise HTTPException(404, "Проект не найден")

    meta_path = proj_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "Метаданные не найдены")

    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    has_pptx = (proj_dir / f"{project_id}.pptx").exists()
    return JSONResponse({
        "project_id": project_id,
        "status": meta.get("status", "unknown"),
        "progress": meta.get("progress", 0),
        "has_pptx": has_pptx,
        "download_url": f"/api/download/{project_id}" if has_pptx else None,
    })


# ═══════════════════════════════════════════════════════════
# API КОНВЕРТАЦИИ
# ═══════════════════════════════════════════════════════════

@app.post("/api/convert")
async def convert_uploaded_zip(file: UploadFile = File(...)):
    if not file.filename.endswith('.zip'):
        raise HTTPException(400, "Только ZIP-архивы")

    # Сохраняем загруженный архив
    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    try:
        content = await file.read()
        tmp_zip.write(content)
        tmp_zip.close()

        conv_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        conv_dir = PROJECTS_DIR / conv_id
        conv_dir.mkdir(exist_ok=True)

        output_path = conv_dir / f"{conv_id}.pptx"
        convert_project_to_pptx(
            zip_path=Path(tmp_zip.name),
            output_path=output_path,
            icons_base_dir=str(ICONS_DIR)
        )

        return JSONResponse({
            "status": "success",
            "download_url": f"/api/download/{conv_id}",
            "preview_url": "#"
        })
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        os.unlink(tmp_zip.name)


@app.post("/api/convert/{project_id}")
async def convert_existing_project(project_id: str):
    proj_dir = PROJECTS_DIR / project_id
    if not proj_dir.exists():
        raise HTTPException(404, "Проект не найден")

    pptd_files = list(proj_dir.glob("*.pptd"))
    pages_dir = proj_dir / "pages"
    if not pptd_files or not pages_dir.exists():
        raise HTTPException(400, "Проект не содержит .pptd или pages/")

    try:
        output_path = proj_dir / f"{project_id}.pptx"
        converter = KimiPptdConverter(icons_base_dir=ICONS_DIR)
        converter.convert(str(proj_dir), str(output_path))
        return JSONResponse({
            "status": "success",
            "download_url": f"/api/download/{project_id}",
        })
    except Exception as e:
        raise HTTPException(500, f"Ошибка конвертации: {str(e)}")


@app.get("/api/download/{project_id}")
async def download_project(project_id: str):
    proj_dir = PROJECTS_DIR / project_id
    if not proj_dir.exists():
        raise HTTPException(404, "Проект не найден")

    pptx_files = list(proj_dir.glob("*.pptx"))
    if not pptx_files:
        raise HTTPException(404, "PPTX не найден")

    return FileResponse(
        pptx_files[0],
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=pptx_files[0].name
    )


# ═══════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ API
# ═══════════════════════════════════════════════════════════

@app.get("/api/icons/search")
async def search_icons(q: str = "", limit: int = 50):
    from icon_manager import IconLibrary
    lib = IconLibrary(ICONS_DIR)
    variants = lib.search(q)
    results = []
    for v in variants[:limit]:
        results.append({
            "name": v.name,
            "style": v.style,
            "flat": v.is_flat,
            "path": str(v.path.relative_to(ICONS_DIR))
        })
    return JSONResponse({"query": q, "count": len(results), "icons": results})


@app.get("/api/icons/categories")
async def icon_categories():
    from icon_manager import IconLibrary
    lib = IconLibrary(ICONS_DIR)
    cats = lib.list_all_categories()
    return JSONResponse(cats)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0"}


@app.post("/api/improve-page/{project_id}/{page_name}")
async def improve_page(project_id: str, page_name: str, instruction: str = Form(...)):
    proj_dir = PROJECTS_DIR / project_id
    if not proj_dir.exists():
        raise HTTPException(404, "Проект не найден")

    # Получаем агента с настройками по умолчанию (можно из конфига)
    agent = create_agent(
        DEFAULT_MODEL,
        local_base_url=LOCAL_LLM_URL,
        icons_dir=ICONS_DIR
    )
    try:
        improved = agent.improve_page(proj_dir, page_name, instruction)
        return JSONResponse({
            "status": "success",
            "message": f"Страница {page_name} улучшена",
            "improved_yaml": improved
        })
    except Exception as e:
        raise HTTPException(500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)