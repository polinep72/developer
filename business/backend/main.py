"""
Главный файл FastAPI приложения для системы расчета себестоимости
"""
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.database import engine, Base, get_db
from sqlalchemy.orm import Session, joinedload
from typing import List
import io
from openpyxl import Workbook

from app.auth_jwt import get_current_user
from app.routers import products, calculations, coefficients, labor_costs, protocols, warehouse_integration, elements, bom_options, auth, db_materials, works
from app.models import Элемент

# ВАЖНО: существующая warehouse БД управляется отдельно (migration/DDL),
# поэтому auto-create таблиц здесь отключаем, чтобы не создавать "ошибочные" таблицы.

app = FastAPI(
    title="Система расчета себестоимости и ценообразования",
    description="Веб-портал для расчета калькуляции себестоимости продукции",
    version="0.3.9"
)

# Настройка CORS для работы с frontend (локально и по LAN)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8095",
        "http://127.0.0.1:8095",
        "http://localhost:8082",
        "http://127.0.0.1:8082",
        "http://192.168.1.139:8082",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(auth.router, prefix="/api/auth", tags=["Аутентификация (warehouse.users)"])
app.include_router(elements.router, prefix="/api/elements", tags=["Элементы (нормализованные)"])
app.include_router(products.router, prefix="/api/products", tags=["Изделия (обратная совместимость)"])
app.include_router(calculations.router, prefix="/api/calculations", tags=["Калькуляции"])
app.include_router(coefficients.router, prefix="/api/coefficients", tags=["Коэффициенты"])
app.include_router(labor_costs.router, prefix="/api/labor-costs", tags=["Трудозатраты"])
app.include_router(works.router, prefix="/api/works", tags=["Справочник работ"])
app.include_router(protocols.router, prefix="/api/protocols", tags=["Протоколы цены"])
app.include_router(warehouse_integration.router, prefix="/api/warehouse", tags=["Интеграция со складом"])
app.include_router(bom_options.router, prefix="/api/bom-options", tags=["BOM: выбор типа и модели"])
app.include_router(db_materials.router, prefix="/api/db", tags=["БД: кристаллы, корпуса, крышки"])

# Отключаем редирект по trailing slash: иначе 307 ведёт на Location без порта (http://host/api/works/)
# и браузер уходит на порт 80, получая "страница не найдена"
app.router.redirect_slashes = False


@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "Система расчета себестоимости и ценообразования",
        "version": "0.3.9",
        "status": "running"
    }


@app.get("/api/health")
async def health_check():
    """Проверка здоровья системы"""
    return {"status": "healthy"}


@app.get("/api/elements-export")
def export_elements_to_excel_root(
    ids: List[int] = Query(..., alias="ids"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Экспорт выбранных элементов в Excel (обёртка над логикой из routers.elements),
    вынесенная на отдельный путь, чтобы избежать конфликтов с /api/elements/{id}.
    """
    elements_q = (
        db.query(Элемент)
        .options(joinedload(Элемент.тип))
        .filter(Элемент.id.in_(ids))
    )
    elements = elements_q.all()
    if not elements:
        raise HTTPException(status_code=404, detail="Элементы не найдены")

    # Ленивая загрузка CalculationService, чтобы не плодить зависимостей при импорте
    from app.services.calculation_service import CalculationService

    service = CalculationService(db)

    wb = Workbook()
    summary_ws = wb.active
    summary_ws.title = "Общая"

    headers = [
        "ID",
        "Тип",
        "Обозначение",
        "Наименование",
        "Цена продажи, руб.",
        "Себестоимость, руб.",
        "Ед. изм.",
        "Активен",
    ]
    summary_ws.append(headers)

    for el in elements:
        try:
            cost = service.calculate_element_cost(el.id, True)
            total_cost = float(cost["итоговая_себестоимость"])
        except Exception:
            total_cost = None

        type_name = el.тип.название if el.тип else ""

        row = [
            el.id,
            type_name,
            el.обозначение,
            el.наименование,
            float(el.цена) if el.цена is not None else None,
            total_cost,
            getattr(el, "единица_измерения", None) or "шт",
            "Да" if getattr(el, "активен", True) else "Нет",
        ]

        summary_ws.append(row)

        ws = wb.create_sheet(title=str(el.обозначение)[:31])
        ws.append(headers)
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = "elements_export.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
