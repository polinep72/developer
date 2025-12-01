import logging
import os
import platform
import subprocess
from datetime import date, timedelta, datetime
from typing import List, Optional, Dict, Any, cast

from fastapi import FastAPI, HTTPException, Request, Depends, Response, status, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from io import BytesIO

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('uvicorn.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from .services.heatmap import get_heatmap_payload
from .services.dashboard import (
    get_dashboard_initial,
    prepare_dashboard_payload,
    get_dashboard_dataframe,
)
from .services.equipment import (
    get_equipment_types,
    get_gosregister,
    get_equipment_by_type,
    get_stats,
    get_calibration_certificates,
    add_si_to_equipment,
    add_io_to_equipment,
    add_vo_to_equipment,
    add_gosregister,
)
from .services.bookings import (
    get_categories as get_booking_categories,
    get_equipment_by_category as get_booking_equipment_options,
    get_available_slots as get_booking_slots,
    create_booking as create_booking_record,
    get_user_bookings,
    get_all_bookings,
    cancel_booking,
    export_bookings_csv,
    get_calendar_overview,
)
from .services.export_excel import (
    export_dashboard_excel,
    export_equipment_excel,
    export_bookings_excel as export_bookings_excel_func,
)
from .services.export_pdf import (
    export_dashboard_pdf,
    export_equipment_pdf,
    export_bookings_pdf,
)
from .services import auth as auth_service
from .services import users as users_service

# Импорт middleware безопасности
from .middleware.security import SecurityHeadersMiddleware, setup_cors
from .services.rate_limit import limiter, auth_rate_limit, api_rate_limit

app = FastAPI(title="WSB Portal")

# Настройка rate limiting
app.state.limiter = limiter
from slowapi.errors import RateLimitExceeded
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=429,
        content={"detail": "Превышен лимит запросов. Попробуйте позже."}
    )
)

# Настройка CORS и security headers
setup_cors(app)
app.add_middleware(SecurityHeadersMiddleware)

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

AUTH_COOKIE_NAME = "wsb_access"

# Планировщик для периодических задач (напоминания о начале работы)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = BackgroundScheduler()

def send_booking_reminders_job():
    """Задача для отправки напоминаний о начале работы"""
    try:
        from .services.booking_reminders import send_booking_start_reminders
        result = send_booking_start_reminders(minutes_before=15)
        logger.info(f"Задача отправки напоминаний выполнена: {result}")
    except Exception as exc:
        logger.error(f"Ошибка в задаче отправки напоминаний: {exc}")

# Запускаем задачу каждую минуту
scheduler.add_job(
    send_booking_reminders_job,
    trigger=IntervalTrigger(minutes=1),
    id='send_booking_reminders',
    name='Отправка напоминаний о начале работы',
    replace_existing=True
)

def stop_previous_instances(port: int = 8090):
    """Остановить все предыдущие экземпляры сервера на указанном порту"""
    try:
        if platform.system() == "Windows":
            # Для Windows используем netstat и taskkill
            # Находим процессы, слушающие порт
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            
            pids_to_kill = set()
            for line in result.stdout.split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            pid = int(parts[-1])
                            pids_to_kill.add(pid)
                        except (ValueError, IndexError):
                            continue
            
            # Останавливаем найденные процессы
            for pid in pids_to_kill:
                try:
                    # Проверяем, что это действительно Python процесс
                    check_result = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="ignore"
                    )
                    if "python" in check_result.stdout.lower():
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True,
                            stderr=subprocess.DEVNULL
                        )
                        logger.info(f"Остановлен предыдущий процесс сервера (PID: {pid})")
                except Exception as e:
                    logger.warning(f"Не удалось остановить процесс {pid}: {e}")
            
            if pids_to_kill:
                logger.info(f"Остановлено {len(pids_to_kill)} предыдущих экземпляров сервера")
            else:
                logger.info("Предыдущие экземпляры сервера не найдены")
        else:
            # Для Linux/Mac используем lsof и kill
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        subprocess.run(
                            ["kill", "-9", pid],
                            capture_output=True,
                            stderr=subprocess.DEVNULL
                        )
                        logger.info(f"Остановлен предыдущий процесс сервера (PID: {pid})")
                    except Exception as e:
                        logger.warning(f"Не удалось остановить процесс {pid}: {e}")
                logger.info(f"Остановлено {len(pids)} предыдущих экземпляров сервера")
            else:
                logger.info("Предыдущие экземпляры сервера не найдены")
                
    except Exception as e:
        logger.warning(f"Ошибка при остановке предыдущих экземпляров: {e}")


@app.on_event("startup")
async def startup_event():
    """Запуск планировщика при старте приложения"""
    # Останавливаем предыдущие экземпляры сервера
    stop_previous_instances(port=8090)
    
    scheduler.start()
    logger.info("Планировщик напоминаний запущен")

@app.on_event("shutdown")
async def shutdown_event():
    """Остановка планировщика при остановке приложения"""
    scheduler.shutdown()
    logger.info("Планировщик напоминаний остановлен")


class DashboardRequest(BaseModel):
    equipment: List[str]
    start_date: date
    end_date: date
    target_load: float = Field(default=8, gt=0)


class LoginRequest(BaseModel):
    login: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    login: str


class ResetPasswordConfirm(BaseModel):
    token: str
    new_password: str


class UserProfileUpdateRequest(BaseModel):
    first_name: str = Field(min_length=1, description="Имя, Отчество")
    last_name: str = Field(min_length=1, description="Фамилия")
    phone: Optional[str] = Field(default=None, description="Номер телефона")
    email: Optional[str] = Field(default=None, description="Корпоративный email")


class NotificationSettingsRequest(BaseModel):
    email_notifications: bool = True
    sms_notifications: bool = False


class RegisterRequest(BaseModel):
    telegram_id: int = Field(gt=0, description="Telegram ID пользователя")
    first_name: str = Field(min_length=1, description="Имя, Отчество")
    last_name: str = Field(min_length=1, description="Фамилия")
    phone: str = Field(min_length=1, description="Номер телефона")
    email: Optional[str] = Field(None, description="Корпоративный e-mail")
    password: str = Field(min_length=6, description="Пароль (минимум 6 символов)")


class BookingCreateRequest(BaseModel):
    equipment_id: int = Field(gt=0)
    date: date
    start_time: str
    duration_minutes: int = Field(gt=0)


class UserResponse(BaseModel):
    id: int
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    is_admin: bool


def set_auth_cookie(response: Response, token: str):
    max_age = auth_service.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=max_age,
    )


def clear_auth_cookie(response: Response):
    response.delete_cookie(AUTH_COOKIE_NAME)


def get_token_from_request(request: Request) -> str | None:
    return request.cookies.get(AUTH_COOKIE_NAME)


def get_optional_user(request: Request) -> Optional[Dict[str, Any]]:
    """Получить пользователя, если он авторизован, иначе None"""
    token = get_token_from_request(request)
    if not token:
        return None
    try:
        payload = auth_service.decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        return auth_service.get_user_by_id(user_id)
    except Exception:
        return None


def get_current_user(request: Request) -> Dict[str, Any]:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    try:
        payload = auth_service.decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный токен")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен недействителен")
    user = auth_service.get_user_by_id(int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return auth_service.sanitize_user(user)


def require_admin_user(current_user=Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return current_user


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, selected_date: str | None = None):
    today = date.today()
    target_date = today
    if selected_date:
        try:
            target_date = date.fromisoformat(selected_date)
        except ValueError:
            pass

    history_date = today - timedelta(days=1)
    if history_date < date(2000, 1, 1):
        history_date = today

    heatmap_data = get_heatmap_payload(target_date)
    history_heatmap_data = get_heatmap_payload(history_date)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "selected_date": heatmap_data.get("date", target_date.strftime("%Y-%m-%d")),
            "heatmap_json": heatmap_data.get("figure_json"),
            "heatmap_error": heatmap_data.get("error"),
            "heatmap_summary": heatmap_data.get("summary") or {},
            "history_heatmap_json": history_heatmap_data.get("figure_json"),
            "history_heatmap_error": history_heatmap_data.get("error"),
            "today": today.strftime("%Y-%m-%d"),
            "history_selected_date": history_heatmap_data.get(
                "date", history_date.strftime("%Y-%m-%d")
            ),
        },
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/api/heatmap", response_class=JSONResponse)
async def api_heatmap(selected_date: str):
    try:
        target_date = date.fromisoformat(selected_date)
    except ValueError:
        return JSONResponse({"error": "Некорректная дата"}, status_code=400)

    payload = get_heatmap_payload(target_date)
    status = 200 if not payload.get("error") else 500
    return JSONResponse(payload, status_code=status)


@app.get("/api/bookings/categories", response_class=JSONResponse)
async def api_booking_categories():
    result = get_booking_categories()
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", [])


@app.get("/api/bookings/equipment", response_class=JSONResponse)
async def api_booking_equipment(category_id: int = Query(..., gt=0)):
    result = get_booking_equipment_options(category_id)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", [])


@app.get("/api/bookings/slots", response_class=JSONResponse)
async def api_booking_slots(equipment_id: int = Query(..., gt=0), selected_date: str = Query(...)):
    try:
        target_date = date.fromisoformat(selected_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректная дата")

    result = get_booking_slots(equipment_id, target_date)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", {})


@app.post("/api/bookings", response_class=JSONResponse)
async def api_create_booking(payload: BookingCreateRequest, current_user=Depends(get_current_user)):
    result = create_booking_record(
        user_id=current_user["id"],
        equipment_id=payload.equipment_id,
        target_date=payload.date,
        start_time_str=payload.start_time,
        duration_minutes=payload.duration_minutes,
    )
    if result.get("error"):
        status_code = 409 if result.get("conflicts") else 400
        body = {"error": result["error"]}
        if result.get("conflicts"):
            body["conflicts"] = result["conflicts"]
        return JSONResponse(body, status_code=status_code)

    data = result.get("data", {})
    return {
        "message": "Бронирование создано",
        "booking_id": data.get("booking_id"),
        "start_time": data.get("start_time"),
        "end_time": data.get("end_time"),
    }


@app.get("/api/bookings/my", response_class=JSONResponse)
async def api_my_bookings(selected_date: Optional[str] = Query(None), current_user=Depends(get_current_user)):
    target_date = None
    if selected_date:
        try:
            target_date = date.fromisoformat(selected_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректная дата")
    
    result = get_user_bookings(current_user["id"], target_date)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", [])


@app.get("/api/bookings/all", response_class=JSONResponse)
async def api_all_bookings(selected_date: Optional[str] = Query(None), current_user=Depends(require_admin_user)):
    target_date = None
    if selected_date:
        try:
            target_date = date.fromisoformat(selected_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректная дата")
    
    result = get_all_bookings(target_date)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", [])


@app.post("/api/bookings/{booking_id}/cancel", response_class=JSONResponse)
async def api_cancel_booking(booking_id: int, current_user=Depends(get_current_user)):
    result = cancel_booking(booking_id, current_user["id"], current_user.get("is_admin", False))
    if result.get("error"):
        status_code = 403 if "прав" in result["error"] or "найдено" in result["error"] else 400
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result.get("data", {})


@app.get("/api/bookings/export")
async def api_export_bookings(
    selected_date: Optional[str] = Query(None),
    scope: str = Query("mine"),
    current_user=Depends(get_current_user),
):
    if not selected_date:
        raise HTTPException(status_code=400, detail="Укажите дату бронирования")
    try:
        target_date = date.fromisoformat(selected_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректная дата")

    include_all = bool(current_user.get("is_admin")) and scope == "all"
    result = export_bookings_csv(
        target_date=target_date,
        user_id=current_user["id"],
        include_all=include_all,
    )
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    filename = result.get("filename", f"bookings_{target_date.isoformat()}.csv")
    content: bytes = result.get("content", b"")
    if not content:
        content = "Дата;Время начала;Время окончания;Интервал;Длительность (ч);Оборудование;Категория;Статус\n".encode("utf-8-sig")

    return StreamingResponse(
        BytesIO(content),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/bookings/export/excel")
async def export_bookings_excel(
    selected_date: str = Query(..., description="Дата в формате YYYY-MM-DD"),
    scope: str = Query("mine", description="mine или all (только для админов)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Экспорт бронирований в Excel"""
    try:
        target_date = date.fromisoformat(selected_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректная дата")

    include_all = bool(current_user.get("is_admin")) and scope == "all"
    
    # Получаем данные через CSV функцию (она уже форматирует данные)
    result = export_bookings_csv(
        target_date=target_date,
        user_id=current_user["id"],
        include_all=include_all,
    )
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    
    # Преобразуем CSV данные в Excel
    csv_content = result.get("content", b"").decode("utf-8-sig")
    excel_content = export_bookings_excel_func(csv_content, target_date, include_all)
    filename = f"bookings_{target_date.isoformat()}.xlsx"

    return StreamingResponse(
        BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/bookings/calendar", response_class=JSONResponse)
async def get_bookings_calendar(
    year: int = Query(..., description="Год"),
    month: int = Query(..., description="Месяц (1-12)"),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """Получить данные календаря бронирований на указанный месяц"""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="Месяц должен быть от 1 до 12")
    
    user_id = current_user.get("id") if current_user else None
    # Для неавторизованных пользователей показываем все бронирования
    # Для авторизованных - только свои (если не админ)
    if current_user and not current_user.get("is_admin"):
        user_id = current_user.get("id")
    else:
        user_id = None  # Админы видят все
    
    result = get_calendar_overview(year=year, month=month, user_id=user_id)
    return result


@app.get("/api/bookings/export/pdf", response_class=StreamingResponse)
async def export_bookings_pdf_endpoint(
    selected_date: str = Query(..., description="Дата в формате YYYY-MM-DD"),
    scope: str = Query("mine", description="mine или all (только для админов)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Экспорт бронирований в PDF"""
    try:
        target_date = date.fromisoformat(selected_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректная дата")

    include_all = bool(current_user.get("is_admin")) and scope == "all"
    
    # Получаем данные через CSV функцию (она уже форматирует данные)
    result = export_bookings_csv(
        target_date=target_date,
        user_id=current_user["id"],
        include_all=include_all,
    )
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    
    # Преобразуем CSV данные в PDF
    csv_content = result.get("content", b"").decode("utf-8-sig")
    pdf_content = export_bookings_pdf(csv_content, target_date, include_all)
    filename = f"bookings_{target_date.isoformat()}.pdf"

    return StreamingResponse(
        BytesIO(pdf_content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/dashboard/export/excel", response_class=StreamingResponse)
async def export_dashboard_excel_endpoint(
    request: DashboardRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Экспорт данных дашборда в Excel"""
    from .services.dashboard import get_dashboard_dataframe, prepare_dashboard_payload
    
    if not request.equipment:
        raise HTTPException(status_code=400, detail="Не выбрано оборудование")
    
    # Получаем данные дашборда
    records = get_dashboard_dataframe(
        start_date=request.start_date,
        end_date=request.end_date,
    )
    
    if not records:
        raise HTTPException(status_code=500, detail="Нет данных для экспорта")
    
    # Подготавливаем payload
    payload = prepare_dashboard_payload(
        records=records,
        equipment=request.equipment,
        start_date=request.start_date,
        end_date=request.end_date,
        target_load=request.target_load,
    )
    
    filters = {
        "equipment": request.equipment,
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "target_load": request.target_load,
    }
    
    excel_content = export_dashboard_excel(
        payload=payload,
        filters=filters,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    
    filename = f"dashboard_{request.start_date.isoformat()}_{request.end_date.isoformat()}.xlsx"
    
    return StreamingResponse(
        BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/dashboard/export/pdf", response_class=StreamingResponse)
async def export_dashboard_pdf_endpoint(
    request: DashboardRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Экспорт данных дашборда в PDF"""
    from .services.dashboard import get_dashboard_dataframe, prepare_dashboard_payload
    
    if not request.equipment:
        raise HTTPException(status_code=400, detail="Не выбрано оборудование")
    
    # Получаем данные дашборда
    records = get_dashboard_dataframe(
        start_date=request.start_date,
        end_date=request.end_date,
    )
    
    if not records:
        raise HTTPException(status_code=500, detail="Нет данных для экспорта")
    
    # Подготавливаем payload
    payload = prepare_dashboard_payload(
        records=records,
        equipment=request.equipment,
        start_date=request.start_date,
        end_date=request.end_date,
        target_load=request.target_load,
    )
    
    filters = {
        "equipment": request.equipment,
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "target_load": request.target_load,
    }
    
    pdf_content = export_dashboard_pdf(
        payload=payload,
        filters=filters,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    
    filename = f"dashboard_{request.start_date.isoformat()}_{request.end_date.isoformat()}.pdf"
    
    return StreamingResponse(
        BytesIO(pdf_content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/dashboard/init", response_class=JSONResponse)
async def dashboard_init():
    data = get_dashboard_initial()
    if data.get("error"):
        raise HTTPException(status_code=500, detail=data["error"])
    return data


@app.post("/api/dashboard/data", response_class=JSONResponse)
async def dashboard_data(request: DashboardRequest):
    from .services.cache import get_dashboard, set_dashboard
    
    if not request.equipment:
        raise HTTPException(status_code=400, detail="Не выбрано оборудование")
    
    date_from_str = request.start_date.isoformat()
    date_to_str = request.end_date.isoformat()
    
    # Пытаемся получить из кэша
    cached = get_dashboard(date_from_str, date_to_str)
    if cached:
        return JSONResponse(cached)
    
    # Если нет в кэше - загружаем из БД
    payload = prepare_dashboard_payload(
        records=get_dashboard_dataframe(
            start_date=request.start_date,
            end_date=request.end_date,
        ),
        equipment=request.equipment,
        start_date=request.start_date,
        end_date=request.end_date,
        target_load=request.target_load,
    )
    
    # Сохраняем в кэш
    set_dashboard(date_from_str, date_to_str, payload)
    
    return JSONResponse(payload)


@app.post("/api/dashboard/advanced", response_class=JSONResponse)
async def dashboard_advanced(request: DashboardRequest):
    from .services.dashboard import get_advanced_dashboard_data
    
    data = get_advanced_dashboard_data(
        start_date=request.start_date,
        end_date=request.end_date,
        equipment=request.equipment if request.equipment else None,
    )
    
    return JSONResponse(data)


# API для модуля СИ (оборудование)
# ВАЖНО: Специфичные маршруты должны быть ПЕРЕД параметризованными!
@app.get("/api/equipment/types", response_class=JSONResponse)
async def api_equipment_types():
    result = get_equipment_types()
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", [])


@app.get("/api/equipment/gosregister", response_class=JSONResponse)
async def api_gosregister():
    result = get_gosregister()
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", [])


@app.get("/api/equipment/stats", response_class=JSONResponse)
async def api_equipment_stats():
    result = get_stats()
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", {})


@app.get("/api/equipment/test-connection", response_class=JSONResponse)
async def api_test_equipment_connection():
    """Тестовый эндпоинт для проверки подключения к БД equipment"""
    from .services.equipment import (
        _connect_equipment_db,
        EQUIPMENT_DB_NAME,
        EQUIPMENT_DB_HOST,
        EQUIPMENT_DB_USER,
        EQUIPMENT_DB_PORT,
    )
    
    conn = _connect_equipment_db()
    if not conn:
        return JSONResponse({
            "connected": False,
            "error": "Не удалось подключиться к БД equipment",
            "db_name": EQUIPMENT_DB_NAME,
            "db_host": EQUIPMENT_DB_HOST,
            "db_user": EQUIPMENT_DB_USER,
            "db_port": EQUIPMENT_DB_PORT,
        }, status_code=500)
    
    try:
        with conn.cursor() as cur:
            # Проверяем существование таблиц
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('equipment_types', 'equipment', 'gosregister', 'calibration_certificates')
                ORDER BY table_name
                """
            )
            tables = cast(List[Dict[str, Any]], cur.fetchall())
            
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                "SELECT COUNT(*) as count FROM equipment_types"
            )
            types_result = cast(Optional[Dict[str, Any]], cur.fetchone())
            
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                "SELECT type_code, type_name FROM equipment_types ORDER BY id"
            )
            types_list = cast(List[Dict[str, Any]], cur.fetchall())
            
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                "SELECT COUNT(*) as count FROM equipment"
            )
            equipment_result = cast(Optional[Dict[str, Any]], cur.fetchone())
            
        conn.close()
        return {
            "connected": True,
            "db_name": EQUIPMENT_DB_NAME,
            "db_host": EQUIPMENT_DB_HOST,
            "tables_found": [t["table_name"] for t in tables] if tables else [],
            "equipment_types_count": types_result["count"] if types_result else 0,
            "equipment_types": [{"code": t["type_code"], "name": t["type_name"]} for t in types_list] if types_list else [],
            "equipment_count": equipment_result["count"] if equipment_result else 0,
        }
    except Exception as e:
        if conn:
            conn.close()
        return JSONResponse({
            "connected": False,
            "error": str(e),
            "db_name": EQUIPMENT_DB_NAME,
            "db_host": EQUIPMENT_DB_HOST,
        }, status_code=500)


@app.get("/api/equipment/certificates/{equipment_id}", response_class=JSONResponse)
async def api_calibration_certificates(equipment_id: int):
    result = get_calibration_certificates(equipment_id)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", [])


# API для добавления оборудования
@app.post("/api/equipment/add-si", response_class=JSONResponse)
async def api_add_si(request: Request, user=Depends(require_admin_user)):
    data = await request.json()
    result = add_si_to_equipment(data)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.post("/api/equipment/add-io", response_class=JSONResponse)
async def api_add_io(request: Request, user=Depends(require_admin_user)):
    data = await request.json()
    result = add_io_to_equipment(data)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.post("/api/equipment/add-vo", response_class=JSONResponse)
async def api_add_vo(request: Request, user=Depends(require_admin_user)):
    data = await request.json()
    result = add_vo_to_equipment(data)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.post("/api/equipment/add-gosregister", response_class=JSONResponse)
async def api_add_gosregister(request: Request, user=Depends(require_admin_user)):
    data = await request.json()
    result = add_gosregister(data)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# Параметризованный маршрут должен быть ПОСЛЕДНИМ, чтобы не перехватывать специфичные маршруты
@app.get("/api/equipment/{equipment_type}", response_class=JSONResponse)
async def api_equipment_by_type(equipment_type: str):
    result = get_equipment_by_type(equipment_type)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", [])


@app.get("/api/equipment/{equipment_type}/export/excel", response_class=StreamingResponse)
async def export_equipment_excel_endpoint(equipment_type: str):
    """Экспорт данных модуля СИ в Excel"""
    result = get_equipment_by_type(equipment_type)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    
    equipment_data = result.get("data", [])
    excel_content = export_equipment_excel(equipment_data, equipment_type)
    filename = f"equipment_{equipment_type}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    return StreamingResponse(
        BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/equipment/{equipment_type}/export/pdf", response_class=StreamingResponse)
async def export_equipment_pdf_endpoint(equipment_type: str):
    """Экспорт данных модуля СИ в PDF"""
    result = get_equipment_by_type(equipment_type)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    
    equipment_data = result.get("data", [])
    pdf_content = export_equipment_pdf(equipment_data, equipment_type)
    filename = f"equipment_{equipment_type}_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return StreamingResponse(
        BytesIO(pdf_content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Аутентификация
@app.post("/auth/login", response_class=JSONResponse)
@auth_rate_limit()
async def auth_login(request: Request, payload: LoginRequest, response: Response):
    logger.info("Login attempt for '%s'", payload.login)
    user = auth_service.get_user_by_login(payload.login)
    if not user or not auth_service.verify_password(payload.password, user.get("password_hash")):
        logger.warning("Login failed for '%s'", payload.login)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")

    access_token = auth_service.create_access_token({"sub": str(user["users_id"])})
    set_auth_cookie(response, access_token)
    logger.info("Login success for user_id=%s", user["users_id"])
    return auth_service.sanitize_user(user)


@app.post("/auth/register", response_class=JSONResponse)
@auth_rate_limit()
async def auth_register(request: Request, payload: RegisterRequest):
    logger.info("Registration attempt for telegram_id=%s, phone=%s", payload.telegram_id, payload.phone)
    result = auth_service.register_user(
        telegram_id=payload.telegram_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        email=payload.email,
        password=payload.password,
    )
    if result.get("error"):
        logger.warning("Registration failed: %s", result["error"])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    
    logger.info("Registration success for telegram_id=%s", payload.telegram_id)
    return result


@app.post("/auth/logout", status_code=204)
async def auth_logout(response: Response):
    clear_auth_cookie(response)
    return Response(status_code=204)


@app.get("/auth/me", response_class=JSONResponse)
async def auth_me(user=Depends(get_current_user)):
    # Добавляем настройки уведомлений к информации о пользователе
    from .services import notifications as notifications_service
    notification_settings = notifications_service.get_user_notification_settings(user["id"])
    user_with_settings = user.copy()
    user_with_settings["notification_settings"] = notification_settings
    return user_with_settings


@app.post("/auth/change-password", response_class=JSONResponse)
async def change_password(payload: ChangePasswordRequest, user=Depends(get_current_user)):
    db_user = auth_service.get_user_by_id(user["id"])
    if not db_user or not auth_service.verify_password(payload.current_password, db_user.get("password_hash")):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")

    new_hash = auth_service.hash_password(payload.new_password)
    auth_service.update_user_password(user["id"], new_hash)
    return {"message": "Пароль успешно обновлён"}


@app.put("/auth/profile", response_class=JSONResponse)
async def update_profile(payload: UserProfileUpdateRequest, user=Depends(get_current_user)):
    result = auth_service.update_user_profile(
        user_id=user["id"],
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        email=payload.email,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/auth/notification-settings", response_class=JSONResponse)
async def get_notification_settings(user=Depends(get_current_user)):
    """Получить настройки уведомлений текущего пользователя"""
    from .services import notifications as notifications_service
    settings = notifications_service.get_user_notification_settings(user["id"])
    return settings


@app.put("/auth/notification-settings", response_class=JSONResponse)
async def update_notification_settings(payload: NotificationSettingsRequest, user=Depends(get_current_user)):
    """Обновить настройки уведомлений текущего пользователя"""
    from .services import notifications as notifications_service
    result = notifications_service.update_user_notification_settings(
        user_id=user["id"],
        email_notifications=payload.email_notifications,
        sms_notifications=payload.sms_notifications,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/auth/reset/request", response_class=JSONResponse)
@auth_rate_limit()
async def reset_request(request: Request, payload: ResetPasswordRequest):
    user = auth_service.get_user_by_login(payload.login)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    token_info = auth_service.create_reset_token(user["users_id"])
    return {
        "message": "Ссылка для восстановления сгенерирована",
        "token": token_info.get("token"),
        "expires_at": token_info.get("expires_at"),
    }


@app.post("/auth/reset/confirm", response_class=JSONResponse)
@auth_rate_limit()
async def reset_confirm(request: Request, payload: ResetPasswordConfirm):
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен быть не менее 8 символов")

    token_row = auth_service.get_reset_token(payload.token)
    if not token_row:
        raise HTTPException(status_code=400, detail="Токен не найден")
    if token_row.get("used"):
        raise HTTPException(status_code=400, detail="Токен уже использован")
    expires_at = token_row.get("expires_at")
    if expires_at and expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Срок действия токена истёк")

    new_hash = auth_service.hash_password(payload.new_password)
    auth_service.update_user_password(token_row["user_id"], new_hash)
    auth_service.mark_reset_token_used(token_row["id"])
    return {"message": "Пароль успешно обновлён"}


@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str | None = None):
    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token})


# Управление пользователями (только для админов)
class UserCreateRequest(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    password: str
    is_admin: bool = False


class UserUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_admin: Optional[bool] = None
    is_blocked: Optional[bool] = None


class UserPasswordResetRequest(BaseModel):
    new_password: str


@app.get("/api/users", response_class=JSONResponse)
async def api_get_all_users(user=Depends(require_admin_user)):
    result = users_service.get_all_users()
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result.get("data", [])


@app.get("/api/users/{user_id}", response_class=JSONResponse)
async def api_get_user(user_id: int, user=Depends(require_admin_user)):
    result = users_service.get_user_by_id(user_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result.get("data")


@app.post("/api/users", response_class=JSONResponse)
async def api_create_user(payload: UserCreateRequest, user=Depends(require_admin_user)):
    result = users_service.create_user(
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        email=payload.email,
        password=payload.password,
        is_admin=payload.is_admin,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.put("/api/users/{user_id}", response_class=JSONResponse)
async def api_update_user(user_id: int, payload: UserUpdateRequest, user=Depends(require_admin_user)):
    result = users_service.update_user(
        user_id=user_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        email=payload.email,
        is_admin=payload.is_admin,
        is_blocked=payload.is_blocked,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/users/{user_id}/reset-password", response_class=JSONResponse)
async def api_reset_user_password(user_id: int, payload: UserPasswordResetRequest, user=Depends(require_admin_user)):
    result = users_service.reset_user_password(user_id, payload.new_password)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.delete("/api/users/{user_id}", response_class=JSONResponse)
async def api_delete_user(user_id: int, user=Depends(require_admin_user)):
    result = users_service.delete_user(user_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result

