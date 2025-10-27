#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор SECRET_KEY для Flask приложения
"""

import secrets
import string

def generate_secret_key(length=32):
    """Генерирует безопасный SECRET_KEY для Flask"""
    # Используем буквы, цифры и специальные символы
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    secret_key = ''.join(secrets.choice(characters) for _ in range(length))
    return secret_key

def generate_hex_key(length=32):
    """Генерирует SECRET_KEY в hex формате"""
    return secrets.token_hex(length)

if __name__ == "__main__":
    print("🔐 ГЕНЕРАТОР SECRET_KEY ДЛЯ FLASK")
    print("=" * 40)
    
    print("\n1. Секретный ключ (смешанный):")
    key1 = generate_secret_key(32)
    print(f"SECRET_KEY={key1}")
    
    print("\n2. Секретный ключ (hex):")
    key2 = generate_hex_key(32)
    print(f"SECRET_KEY={key2}")
    
    print("\n3. UUID4 (альтернатива):")
    import uuid
    key3 = str(uuid.uuid4()).replace('-', '')
    print(f"SECRET_KEY={key3}")
    
    print("\n📋 ИНСТРУКЦИЯ:")
    print("1. Скопируйте один из ключей выше")
    print("2. Вставьте в файл .env вместо 'your-secret-key-here'")
    print("3. НЕ ДЕЛИТЕСЬ этим ключом с другими!")
    print("4. Храните .env файл в безопасности")
    
    print("\n⚠️  ВАЖНО:")
    print("- Каждое приложение должно иметь УНИКАЛЬНЫЙ ключ")
    print("- НЕ используйте ключи из примеров в продакшене")
    print("- Регулярно меняйте ключи в продакшене")
