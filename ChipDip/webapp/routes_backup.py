# webapp/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
import psycopg2
from psycopg2.extras import RealDictCursor
# Используем модуль database из парсера для некоторых операций
from chipdip_parser import database as db_parser_module
from datetime import datetime, timedelta

# Если формы используются:
# from .forms import AddProductForm

bp = Blueprint('main', __name__)  # Создаем Blueprint


def get_db_connection_webapp():
    """ Получает соединение с БД, используя конфигурацию Flask app """
    db_config = current_app.config['DB_CONFIG']
    try:
        conn = psycopg2.connect(**db_config)
        # current_app.logger.info("DB connection successful for webapp.") # Логирование Flask
        return conn
    except psycopg2.Error as e:
        # current_app.logger.error(f"DB connection error for webapp: {e}")
        flash(f"Ошибка подключения к базе данных: {e}", "error")
        return None


@bp.route('/')
def index():
    # Главная страница с кнопками действий. Списки товаров отображаются на отдельных страницах
    return render_template('index.html')


# Страница со всеми товарами для гостей и авторизованных пользователей
@bp.route('/products')
def all_products():
    conn = get_db_connection_webapp()
    products_data = []
    search_query = request.args.get('q', '').strip()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if search_query:
                    cur.execute("""
                        SELECT DISTINCT ON (p.url)
                            p.id, p.name, p.internal_sku, p.url, p.current_price, p.last_checked_at,
                            p.user_id,
                            CASE
                                WHEN (SELECT COUNT(*) FROM products p2 WHERE p2.url = p.url AND p2.is_active = TRUE) > 1
                                THEN 'Множественные пользователи'
                                ELSE u.username
                            END as added_by,
                            (SELECT sh.stock_level
                             FROM stock_history sh
                             WHERE sh.product_id = p.id
                             ORDER BY sh.check_timestamp DESC
                             LIMIT 1) as latest_stock
                        FROM products p
                        LEFT JOIN users u ON p.user_id = u.id
                        WHERE p.is_active = TRUE
                          AND LOWER(p.name) LIKE LOWER(%s)
                        ORDER BY p.url, p.id ASC;
                    """, (f"%{search_query}%",))
                else:
                    cur.execute("""
                        SELECT DISTINCT ON (p.url)
                            p.id, p.name, p.internal_sku, p.url, p.current_price, p.last_checked_at,
                            p.user_id, 
                            CASE 
                                WHEN (SELECT COUNT(*) FROM products p2 WHERE p2.url = p.url AND p2.is_active = TRUE) > 1 
                                THEN 'Множественные пользователи'
                                ELSE u.username 
                            END as added_by,
                            (SELECT sh.stock_level 
                             FROM stock_history sh 
                             WHERE sh.product_id = p.id 
                             ORDER BY sh.check_timestamp DESC 
                             LIMIT 1) as latest_stock
                        FROM products p
                        LEFT JOIN users u ON p.user_id = u.id
                        WHERE p.is_active = TRUE
                        ORDER BY p.url, p.id ASC;
                    """)
                products_data = cur.fetchall()
        except psycopg2.Error as e:
            flash(f"Ошибка при загрузке данных: {e}", "error")
        finally:
            conn.close()
    return render_template('products_all.html', products=products_data, q=search_query)


@bp.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        name = request.form.get('name')  # Это будет internal_sku
        url = request.form.get('url')

        # Простая валидация
        if not name or not url:
            flash('Артикул (Name) и Ссылка (URL) обязательны!', 'error')
            return render_template('add_product.html', name=name, url=url)
        if not url.startswith(('http://', 'https://')):
            flash('URL должен начинаться с http:// или https://', 'error')
            return render_template('add_product.html', name=name, url=url)

        conn = get_db_connection_webapp()
        if conn:
            try:
                with conn.cursor() as cur:
                    # Проверяем, есть ли уже активный товар с таким URL у текущего пользователя
                    cur.execute("SELECT id, is_active FROM products WHERE url = %s AND user_id = %s", (url, current_user.id))
                    existing_product = cur.fetchone()
                    
                    if existing_product:
                        if existing_product[1]:  # is_active = True
                            flash(f"Вы уже добавили товар с URL '{url}'.", "warning")
                        else:
                            # Товар существует у пользователя, но неактивен - активируем его
                            cur.execute(
                                "UPDATE products SET name = %s, internal_sku = %s, is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                                (name, name, existing_product[0])
                            )
                            conn.commit()
                            flash(f"Товар '{name}' успешно восстановлен!", "success")
                            return redirect(url_for('main.my_products'))
                    else:
                        # Используем name из формы как internal_sku, а также как начальное имя товара
                        cur.execute(
                            "INSERT INTO products (name, internal_sku, url, is_active, user_id) VALUES (%s, %s, %s, %s, %s)",
                            (name, name, url, True, current_user.id)
                        )
                        conn.commit()
                        flash(f"Товар '{name}' успешно добавлен!", "success")
                        return redirect(url_for('main.my_products'))  # Перенаправляем в ЛК
            except psycopg2.Error as e:
                conn.rollback()
                flash(f"Ошибка при добавлении товара в БД: {e}", "error")
            finally:
                conn.close()
        else:
            flash("Не удалось подключиться к БД для добавления товара.", "error")

        return render_template('add_product.html', name=name,
                               url=url)  # Возвращаем на форму с данными, если была ошибка

    return render_template('add_product.html')


# Можно добавить маршрут для просмотра истории конкретного товара
@bp.route('/product/<int:product_id>/history')
def product_history(product_id):
    conn = get_db_connection_webapp()
    history_data = []
    product_info = None
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name, url FROM products WHERE id = %s", (product_id,))
                product_info = cur.fetchone()
                if product_info:
                    cur.execute("""
                        SELECT check_timestamp, stock_level, price, raw_text, status, error_message
                        FROM stock_history
                        WHERE product_id = %s
                        ORDER BY check_timestamp DESC
                        LIMIT 100; -- Ограничиваем для производительности
                    """, (product_id,))
                    history_data = cur.fetchall()
                else:
                    flash("Товар не найден.", "error")
                    return redirect(url_for('main.index'))
        except psycopg2.Error as e:
            flash(f"Ошибка при загрузке истории товара: {e}", "error")
        finally:
            conn.close()
    return render_template('product_history.html', product=product_info, history=history_data)

# Личный кабинет - товары пользователя
@bp.route('/my_products')
@login_required
def my_products():
    conn = get_db_connection_webapp()
    products_data = []
    search_query = request.args.get('q', '').strip()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if search_query:
                    cur.execute("""
                        SELECT 
                            p.id, p.name, p.internal_sku, p.url, p.current_price, p.last_checked_at, p.is_active,
                            (SELECT sh.stock_level 
                             FROM stock_history sh 
                             WHERE sh.product_id = p.id 
                             ORDER BY sh.check_timestamp DESC 
                             LIMIT 1) as latest_stock
                        FROM products p
                        WHERE p.user_id = %s
                          AND LOWER(p.name) LIKE LOWER(%s)
                        ORDER BY p.is_active DESC, p.name ASC;
                    """, (current_user.id, f"%{search_query}%"))
                else:
                    cur.execute("""
                        SELECT 
                            p.id, p.name, p.internal_sku, p.url, p.current_price, p.last_checked_at, p.is_active,
                            (SELECT sh.stock_level 
                             FROM stock_history sh 
                             WHERE sh.product_id = p.id 
                             ORDER BY sh.check_timestamp DESC 
                             LIMIT 1) as latest_stock
                        FROM products p
                        WHERE p.user_id = %s
                        ORDER BY p.is_active DESC, p.name ASC;
                    """, (current_user.id,))
                products_data = cur.fetchall()
        except psycopg2.Error as e:
            flash(f"Ошибка при загрузке данных: {e}", "error")
        finally:
            conn.close()
    return render_template('my_products.html', products=products_data, q=search_query)


# Страница статистики/графиков (заглушка)
@bp.route('/stats')
def stats():
    # Передаем список товаров для селектора на странице статистики
    conn = get_db_connection_webapp()
    products_list = []
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, name, internal_sku
                    FROM products
                    WHERE is_active = TRUE
                    ORDER BY name ASC
                    LIMIT 500
                """)
                products_list = cur.fetchall()
        except psycopg2.Error:
            products_list = []
        finally:
            conn.close()
    return render_template('stats.html', products=products_list)


# --- API: сводная статистика ---
@bp.route('/api/stats/overview')
def api_stats_overview():
    conn = get_db_connection_webapp()
    data = {
        "total_products": 0,
        "active_products": 0,
        "unique_urls": 0,
        "users_count": 0,
        "checks_24h": 0
    }
    if not conn:
        return data
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM products")
            data["total_products"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM products WHERE is_active = TRUE")
            data["active_products"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT url) FROM products WHERE is_active = TRUE")
            data["unique_urls"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
            data["users_count"] = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*)
                FROM stock_history
                WHERE check_timestamp >= NOW() - INTERVAL '24 hours'
            """)
            data["checks_24h"] = cur.fetchone()[0]
    finally:
        conn.close()
    return data


# --- API: временной ряд по товару ---
@bp.route('/api/stats/product/<int:product_id>/series')
def api_stats_product_series(product_id: int):
    conn = get_db_connection_webapp()
    if not conn:
        return {"points": []}
    points = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT to_char(check_timestamp, 'YYYY-MM-DD HH24:MI') AS ts,
                       stock_level,
                       price
                FROM stock_history
                WHERE product_id = %s
                ORDER BY check_timestamp ASC
                LIMIT 500
                """,
                (product_id,)
            )
            for row in cur.fetchall():
                points.append({
                    "ts": row["ts"],
                    "stock": row["stock_level"],
                    "price": float(row["price"]) if row["price"] is not None else None
                })
    finally:
        conn.close()
    return {"points": points}


# --- API: продажи по убыванию остатков за интервал ---
@bp.route('/api/stats/sales')
def api_stats_sales():
    # Параметры интервала
    date_from_str = request.args.get('from')
    date_to_str = request.args.get('to')
    now_dt = datetime.now()
    if not date_to_str:
        date_to = now_dt
    else:
        # Разрешаем формат YYYY-MM-DD
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            return {"error": "Неверный формат 'to' (используйте YYYY-MM-DD)"}, 400
    if not date_from_str:
        date_from = now_dt - timedelta(days=7)
    else:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
        except ValueError:
            return {"error": "Неверный формат 'from' (используйте YYYY-MM-DD)"}, 400

    # Гарантия: from < to
    if date_from >= date_to:
        return {"error": "Параметр 'from' должен быть раньше 'to'"}, 400

    conn = get_db_connection_webapp()
    if not conn:
        return {"items": []}
    items = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                WITH sh AS (
                  SELECT
                    p.id AS product_id,
                    p.name,
                    p.internal_sku,
                    sh.check_timestamp,
                    sh.stock_level,
                    LAG(sh.stock_level) OVER (PARTITION BY sh.product_id ORDER BY sh.check_timestamp) AS prev_stock
                  FROM stock_history sh
                  JOIN products p ON p.id = sh.product_id
                  WHERE COALESCE(p.is_active, TRUE) = TRUE
                    AND sh.stock_level IS NOT NULL
                ),
                sales_calc AS (
                  SELECT
                    product_id,
                    name,
                    internal_sku,
                    check_timestamp,
                    stock_level,
                    prev_stock,
                    -- Рассчитываем продажи только если текущий остаток меньше предыдущего
                    -- (исключаем пополнения склада)
                    CASE 
                      WHEN prev_stock IS NOT NULL AND stock_level < prev_stock 
                      THEN prev_stock - stock_level
                      ELSE 0
                    END AS sold_qty
                  FROM sh
                  WHERE check_timestamp >= %s AND check_timestamp < %s
                )
                SELECT
                  product_id,
                  name,
                  internal_sku,
                  SUM(sold_qty)::bigint AS sold_qty
                FROM sales_calc
                GROUP BY product_id, name, internal_sku
                HAVING SUM(sold_qty) > 0
                ORDER BY sold_qty DESC, name ASC
                LIMIT 100
                """,
                (date_from, date_to)
            )
            rows = cur.fetchall()
            for r in rows:
                items.append({
                    "product_id": r["product_id"],
                    "name": r["name"],
                    "internal_sku": r["internal_sku"],
                    "sold_qty": int(r["sold_qty"]) if r["sold_qty"] is not None else 0
                })
    finally:
        conn.close()
    return {"items": items, "from": date_from.strftime('%Y-%m-%d'), "to": (date_to - timedelta(days=1)).strftime('%Y-%m-%d')}


# --- API: годовые продажи по месяцам для всех товаров ---
@bp.route('/api/stats/yearly/monthly')
def api_stats_yearly_monthly():
    """API для получения продаж по месяцам за последние 12 месяцев для всех товаров"""
    conn = get_db_connection_webapp()
    if not conn:
        return {"months": [], "products": []}
    months = []
    products = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Получаем все месяцы
            cur.execute("""
                SELECT 
                  generate_series(
                    DATE_TRUNC('month', CURRENT_DATE - INTERVAL '11 months'),
                    DATE_TRUNC('month', CURRENT_DATE),
                    INTERVAL '1 month'
                  )::date AS month_start
                ORDER BY month_start
            """)
            
            for row in cur.fetchall():
                months.append(row['month_start'].strftime('%b %Y'))
            
            # Получаем продажи по товарам и месяцам (исправленная логика)
            cur.execute("""
                WITH sh AS (
                  SELECT
                    p.id AS product_id,
                    p.name as product_name,
                    sh.check_timestamp,
                    sh.stock_level,
                    LAG(sh.stock_level) OVER (PARTITION BY sh.product_id ORDER BY sh.check_timestamp) AS prev_stock
                  FROM stock_history sh
                  JOIN products p ON p.id = sh.product_id
                  WHERE COALESCE(p.is_active, TRUE) = TRUE
                    AND sh.stock_level IS NOT NULL
                    AND sh.check_timestamp >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '11 months')
                ),
                sales_calc AS (
                  SELECT
                    product_id,
                    product_name,
                    DATE_TRUNC('month', check_timestamp) AS month_start,
                    SUM(
                      CASE 
                        WHEN prev_stock IS NOT NULL AND stock_level < prev_stock 
                        THEN prev_stock - stock_level
                        ELSE 0
                      END
                    ) AS sold_qty
                  FROM sh
                  GROUP BY product_id, product_name, DATE_TRUNC('month', check_timestamp)
                  HAVING SUM(
                    CASE 
                      WHEN prev_stock IS NOT NULL AND stock_level < prev_stock 
                      THEN prev_stock - stock_level
                      ELSE 0
                    END
                  ) > 0
                )
                SELECT 
                  product_id,
                  product_name,
                  month_start,
                  sold_qty
                FROM sales_calc
                ORDER BY product_id, month_start
            """)
            
            # Группируем данные по товарам
            product_data = {}
            for row in cur.fetchall():
                product_id = row['product_id']
                if product_id not in product_data:
                    product_data[product_id] = {
                        'id': product_id,
                        'name': row['product_name'],
                        'sales': [0] * len(months)
                    }
                
                month_name = row['month_start'].strftime('%b %Y')
                month_index = months.index(month_name)
                product_data[product_id]['sales'][month_index] = int(row['sold_qty'])
            
            products = list(product_data.values())
            
    except Exception as e:
        logger.error(f"Ошибка получения данных для годового графика: {e}", exc_info=True)
    finally:
        conn.close()
    return {"months": months, "products": products}

# --- API: месячные продажи по товару ---
@bp.route('/api/stats/product/<int:product_id>/monthly')
def api_stats_product_monthly(product_id: int):
    conn = get_db_connection_webapp()
    if not conn:
        return {"points": []}
    points = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                WITH months_series AS (
                  -- Генерируем последние 12 месяцев
                  SELECT 
                    DATE_TRUNC('month', CURRENT_DATE - INTERVAL '11 months' + (generate_series(0, 11) * INTERVAL '1 month')) AS month_start
                ),
                sh AS (
                  SELECT
                    sh.check_timestamp,
                    sh.stock_level,
                    LAG(sh.stock_level) OVER (ORDER BY sh.check_timestamp) AS prev_stock
                  FROM stock_history sh
                  WHERE sh.product_id = %s
                    AND sh.stock_level IS NOT NULL
                    AND sh.check_timestamp >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '11 months')
                ),
                sales_calc AS (
                  SELECT
                    DATE_TRUNC('month', check_timestamp) AS month_start,
                    SUM(
                      CASE 
                        WHEN prev_stock IS NOT NULL AND stock_level < prev_stock 
                        THEN prev_stock - stock_level
                        ELSE 0
                      END
                    ) AS sold_qty
                  FROM sh
                  GROUP BY DATE_TRUNC('month', check_timestamp)
                  HAVING SUM(
                    CASE 
                      WHEN prev_stock IS NOT NULL AND stock_level < prev_stock 
                      THEN prev_stock - stock_level
                      ELSE 0
                    END
                  ) > 0  -- Исключаем месяцы без продаж
                )
                SELECT 
                  ms.month_start,
                  COALESCE(sc.sold_qty, 0) AS sold_qty
                FROM months_series ms
                LEFT JOIN sales_calc sc ON ms.month_start = sc.month_start
                ORDER BY ms.month_start ASC
                """,
                (product_id,)
            )
            for row in cur.fetchall():
                points.append({
                    "month": row["month_start"].strftime('%Y-%m'),
                    "sold_qty": int(row["sold_qty"]) if row["sold_qty"] is not None else 0
                })
    finally:
        conn.close()
    return {"points": points}

# Удаление товара пользователем
@bp.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    conn = get_db_connection_webapp()
    if conn:
        try:
            with conn.cursor() as cur:
                # Проверяем, принадлежит ли товар текущему пользователю
                cur.execute("SELECT id FROM products WHERE id = %s AND user_id = %s", (product_id, current_user.id))
                if not cur.fetchone():
                    flash("Товар не найден или у вас нет прав для его удаления.", "error")
                    return redirect(url_for('main.my_products'))
                
                # Удаляем товар (мягкое удаление - устанавливаем is_active = FALSE)
                cur.execute("UPDATE products SET is_active = FALSE WHERE id = %s", (product_id,))
                conn.commit()
                flash("Товар успешно удален.", "success")
        except psycopg2.Error as e:
            conn.rollback()
            flash(f"Ошибка при удалении товара: {e}", "error")
        finally:
            conn.close()
    else:
        flash("Не удалось подключиться к базе данных.", "error")
    
    return redirect(url_for('main.my_products'))

# Восстановление товара
@bp.route('/restore_product/<int:product_id>', methods=['POST'])
@login_required
def restore_product(product_id):
    conn = get_db_connection_webapp()
    if conn:
        try:
            with conn.cursor() as cur:
                # Проверяем, принадлежит ли товар текущему пользователю и неактивен ли он
                cur.execute("SELECT id FROM products WHERE id = %s AND user_id = %s AND is_active = FALSE", (product_id, current_user.id))
                if not cur.fetchone():
                    flash("Товар не найден или у вас нет прав для его восстановления.", "error")
                    return redirect(url_for('main.my_products'))
                
                # Восстанавливаем товар
                cur.execute("UPDATE products SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (product_id,))
                conn.commit()
                flash("Товар успешно восстановлен.", "success")
        except psycopg2.Error as e:
            conn.rollback()
            flash(f"Ошибка при восстановлении товара: {e}", "error")
        finally:
            conn.close()
    else:
        flash("Не удалось подключиться к базе данных.", "error")
    
    return redirect(url_for('main.my_products'))#   - - -   A P I :    U �   U  �  �   Q �     �  �   �   Q!  !  U  � ! �   - - -  
 @ b p . r o u t e ( ' / a p i / p r o d u c t / < i n t : p r o d u c t _ i d > / n a m e ' ,   m e t h o d s = [ ' P U T ' ] )  
 @ l o g i n _ r e q u i r e d  
 d e f   a p i _ u p d a t e _ p r o d u c t _ n a m e ( p r o d u c t _ i d :   i n t ) :  
         " " " A P I    � � !   U �   U  �  �   Q!    �  �   �   Q!  !  U  � ! �   ( !  U � !
 T U   � � !    �  �  � �  � !
!   �   !  U  � ! � ) " " "  
         c o n n   =   g e t _ d b _ c o n n e c t i o n _ w e b a p p ( )  
         i f   n o t   c o n n :  
                 r e t u r n   { " s u c c e s s " :   F a l s e ,   " e r r o r " :   "  [!�  Q �  T �    W U � T � !!!  �   Q!   T      " } ,   5 0 0  
          
         t r y :  
                 d a t a   =   r e q u e s t . g e t _ j s o n ( )  
                 n e w _ n a m e   =   d a t a . g e t ( ' n a m e ' ,   ' ' ) . s t r i p ( )  
                  
                 i f   n o t   n e w _ n a m e :  
                         r e t u r n   { " s u c c e s s " :   F a l s e ,   " e r r o r " :   "  \ �  �   �   Q �     �    X U �  � !    � !9 ! !
   W!S!! !9  X" } ,   4 0 0  
                  
                 w i t h   c o n n . c u r s o r ( c u r s o r _ f a c t o r y = R e a l D i c t C u r s o r )   a s   c u r :  
                         #    _! U  � !! �  X,   !! !  U  !  U  � !   W! Q  �  � �  �  �  Q!   !  �  T!S!0  �  X!S   W U � !
 �  U  � !  �  � ! 
                         c u r . e x e c u t e ( " " "  
                                 S E L E C T   i d ,   n a m e   F R O M   p r o d u c t s    
                                 W H E R E   i d   =   % s   A N D   u s e r _ i d   =   % s   A N D   C O A L E S C E ( i s _ a c t i v e ,   T R U E )   =   T R U E  
                         " " " ,   ( p r o d u c t _ i d ,   c u r r e n t _ u s e r . i d ) )  
                          
                         p r o d u c t   =   c u r . f e t c h o n e ( )  
                         i f   n o t   p r o d u c t :  
                                 r e t u r n   { " s u c c e s s " :   F a l s e ,   " e r r o r " :   "  ^ U  � !    �     �  ! � �     Q �  Q  !S    � !    � !    W! �      �    �  V U  ! �  � �  T!  Q! U  �   Q � " } ,   4 0 4  
                          
                         #    [ �   U  � ! �  X    �  �   �   Q �  
                         c u r . e x e c u t e ( " " "  
                                 U P D A T E   p r o d u c t s    
                                 S E T   n a m e   =   % s ,   u p d a t e d _ a t   =   N O W ( )    
                                 W H E R E   i d   =   % s  
                         " " " ,   ( n e w _ n a m e ,   p r o d u c t _ i d ) )  
                          
                         c o n n . c o m m i t ( )  
                         c u r r e n t _ a p p . l o g g e r . i n f o ( f "  _ U � !
 �  U  � !  �  � !
  { c u r r e n t _ u s e r . i d }    U �   U  Q �     �  �   �   Q �   !  U  � ! �   { p r o d u c t _ i d } :   ' { p r o d u c t [ ' n a m e ' ] } '   - >   ' { n e w _ n a m e } ' " )  
                          
                         r e t u r n   { " s u c c e s s " :   T r u e ,   " n e w _ n a m e " :   n e w _ n a m e }  
                          
         e x c e p t   E x c e p t i o n   a s   e :  
                 c o n n . r o l l b a c k ( )  
                 c u r r e n t _ a p p . l o g g e r . e r r o r ( f "  [!�  Q �  T �    U �   U  �  �   Q!    �  �   �   Q!  !  U  � ! �   { p r o d u c t _ i d } :   { e } " ,   e x c _ i n f o = T r u e )  
                 r e t u r n   { " s u c c e s s " :   F a l s e ,   " e r r o r " :   "  [!�  Q �  T �    W! Q   U �   U  �  �   Q Q    �  �   �   Q!" } ,   5 0 0  
         f i n a l l y :  
                 c o n n . c l o s e ( )  
 