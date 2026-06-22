"""Lotus Inventory Management — Web Application."""
import io
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth import (
    COOKIE_NAME,
    create_session_token,
    get_current_user,
    get_optional_user,
    permission_matrix,
    require_permission,
)
from config import BRANDING_DIR, HOST, PORT
from database import (
    PERMISSIONS,
    branding_with_logo,
    create_user,
    delete_user,
    get_user_by_username,
    init_db,
    list_users,
    set_logo_filename,
    update_branding,
    update_user,
    verify_password,
)
from engine import (
    APP_VERSION,
    TEMPLATES,
    export_history_bytes,
    parse_blocked_df,
    parse_rank_df,
    process_inventory,
    template_excel_bytes,
)

app = FastAPI(title="Lotus Inventory Management", version=APP_VERSION)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/branding", StaticFiles(directory=BRANDING_DIR), name="branding")


@app.on_event("startup")
def startup():
    init_db()


class LoginBody(BaseModel):
    username: str
    password: str


class UserCreateBody(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=4, max_length=100)
    is_admin: bool = False
    permissions: list[str] = []


class UserUpdateBody(BaseModel):
    password: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    permissions: list[str] | None = None


class BrandingBody(BaseModel):
    app_title: str | None = None
    app_tagline: str | None = None
    accent_color: str | None = None
    footer_text: str | None = None


def _page(path: str) -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / path).read_text(encoding="utf-8"))


@app.get("/login", response_class=HTMLResponse)
async def login_page(user=Depends(get_optional_user)):
    if user:
        return RedirectResponse("/", status_code=302)
    return _page("login.html")


@app.get("/", response_class=HTMLResponse)
async def index(user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    return _page("index.html")


@app.post("/api/auth/login")
async def login(body: LoginBody):
    row = get_user_by_username(body.username.strip())
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account is disabled")
    token = create_session_token(row["id"])
    response = Response(content='{"ok":true}', media_type="application/json")
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=86400,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
async def logout():
    response = Response(content='{"ok":true}', media_type="application/json")
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@app.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    return {
        "user": user,
        "permissions_catalog": permission_matrix(),
        "branding": branding_with_logo(),
        "version": APP_VERSION,
    }


@app.get("/api/branding")
async def public_branding():
    return branding_with_logo()


@app.get("/api/admin/users")
async def admin_list_users(user=Depends(require_permission("users_manage"))):
    return {"users": list_users(), "permissions": PERMISSIONS}


@app.post("/api/admin/users")
async def admin_create_user(body: UserCreateBody, user=Depends(require_permission("users_manage"))):
    try:
        created = create_user(body.username.strip(), body.password, body.is_admin, body.permissions)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Username already exists") from exc
    return created


@app.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, body: UserUpdateBody, user=Depends(require_permission("users_manage"))):
    updated = update_user(user_id, body.password, body.is_active, body.is_admin, body.permissions)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, user=Depends(require_permission("users_manage"))):
    if not delete_user(user_id, user["id"]):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    return {"ok": True}


@app.put("/api/admin/branding")
async def admin_update_branding(body: BrandingBody, user=Depends(require_permission("branding"))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return update_branding(payload)


@app.post("/api/admin/branding/logo")
async def admin_upload_logo(
    logo: UploadFile = File(...),
    user=Depends(require_permission("branding")),
):
    ext = Path(logo.filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
        raise HTTPException(status_code=400, detail="Logo must be PNG, JPG, WEBP, or SVG")
    filename = f"logo{ext}"
    dest = BRANDING_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(logo.file, f)
    set_logo_filename(filename)
    return branding_with_logo()


@app.get("/api/templates/{name}")
async def download_template(name: str, user=Depends(require_permission("templates"))):
    if name not in TEMPLATES:
        raise HTTPException(status_code=404, detail="Template not found")
    content = template_excel_bytes(name)
    filename = f"{name.replace('_', ' ').title()}_Template.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/history")
async def download_history(user=Depends(require_permission("history"))):
    content = export_history_bytes()
    if content is None:
        raise HTTPException(status_code=404, detail="No history available")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Lotus_Inventory_History.xlsx"'},
    )


async def _read_excel(upload: UploadFile | None) -> pd.DataFrame | None:
    if upload is None or not upload.filename:
        return None
    data = await upload.read()
    return pd.read_excel(io.BytesIO(data))


@app.post("/api/process")
async def run_engine(
    main_file: UploadFile = File(...),
    targets_file: UploadFile = File(...),
    rank_file: UploadFile = File(...),
    avoid_zero_file: UploadFile = File(...),
    purchase_targets_file: UploadFile | None = File(None),
    blocked_file: UploadFile | None = File(None),
    blocked_os_file: UploadFile | None = File(None),
    similar_file: UploadFile | None = File(None),
    zero_overstock: str = Form("true"),
    sto_threshold: int = Form(180),
    user=Depends(require_permission("engine_run")),
):
    include_zero_overstock = zero_overstock.lower() in ("true", "1", "yes", "on")
    try:
        main_df = await _read_excel(main_file)
        targets_df = await _read_excel(targets_file)
        avoid_zero_df = await _read_excel(avoid_zero_file)
        rank_df = await _read_excel(rank_file)
        rank_data = parse_rank_df(rank_df) if rank_df is not None else {}

        purchase_targets_df = await _read_excel(purchase_targets_file)
        similar_df = await _read_excel(similar_file)

        blocked_items, blocked_branches = set(), set()
        if blocked_file and blocked_file.filename:
            blocked_df = await _read_excel(blocked_file)
            if blocked_df is not None:
                blocked_items, blocked_branches = parse_blocked_df(blocked_df)

        blocked_os_items, blocked_os_branches = set(), set()
        if blocked_os_file and blocked_os_file.filename:
            blocked_os_df = await _read_excel(blocked_os_file)
            if blocked_os_df is not None:
                blocked_os_items, blocked_os_branches = parse_blocked_df(blocked_os_df)

        result = process_inventory(
            main_df=main_df,
            targets_df=targets_df,
            purchase_targets_df=purchase_targets_df,
            rank_data=rank_data,
            avoid_zero_df=avoid_zero_df,
            similar_df=similar_df,
            blocked_items=blocked_items,
            blocked_branches=blocked_branches,
            blocked_os_items=blocked_os_items,
            blocked_os_branches=blocked_os_branches,
            zero_overstock=include_zero_overstock,
            sto_threshold=sto_threshold,
        )

        filename = f"Lotus_Inventory_Decision_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return Response(
            content=result,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Processing error: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=HOST, port=PORT, reload=False)
