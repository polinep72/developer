# --- API: обновление названия товара ---
@bp.route('/api/product/<int:product_id>/name', methods=['PUT'])
@login_required
def api_update_product_name(product_id: int):
    """API для обновления названия товара (только для владельца товара)"""
    conn = get_db_connection_webapp()
    if not conn:
        return {"success": False, "error": "Ошибка подключения к БД"}, 500
    
    try:
        data = request.get_json()
        new_name = data.get('name', '').strip()
        
        if not new_name:
            return {"success": False, "error": "Название не может быть пустым"}, 400
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Проверяем, что товар принадлежит текущему пользователю
            cur.execute("""
                SELECT id, name FROM products 
                WHERE id = %s AND user_id = %s AND COALESCE(is_active, TRUE) = TRUE
            """, (product_id, current_user.id))
            
            product = cur.fetchone()
            if not product:
                return {"success": False, "error": "Товар не найден или у вас нет прав на его редактирование"}, 404
            
            # Обновляем название
            cur.execute("""
                UPDATE products 
                SET name = %s, updated_at = NOW() 
                WHERE id = %s
            """, (new_name, product_id))
            
            conn.commit()
            current_app.logger.info(f"Пользователь {current_user.id} обновил название товара {product_id}: '{product['name']}' -> '{new_name}'")
            
            return {"success": True, "new_name": new_name}
            
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Ошибка обновления названия товара {product_id}: {e}", exc_info=True)
        return {"success": False, "error": "Ошибка при обновлении названия"}, 500
    finally:
        conn.close()
