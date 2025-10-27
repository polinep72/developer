from database import execute_query

def check_user_registered(user_id: int) -> bool:
    """Проверяет, зарегистрирован ли пользователь и не заблокирован ли он"""
    query = """
        SELECT 1 FROM users 
        WHERE users_id = %s 
        AND is_blocked = FALSE
    """
    return bool(execute_query(query, (user_id,)))

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    query = "SELECT is_admin FROM users WHERE users_id = %s"
    result = execute_query(query, (user_id,))
    return result and result[0][0]

def is_user_blocked(user_id: int) -> bool:
    """Проверяет, заблокирован ли пользователь"""
    query = "SELECT is_blocked FROM users WHERE users_id = %s"
    result = execute_query(query, (user_id,))
    return result and result[0][0]