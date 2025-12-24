#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки всех зависимостей перед Docker сборкой
"""

import sys

def test_imports():
    """Проверка импортов всех необходимых библиотек"""
    errors = []
    
    print("Проверка импортов...")
    
    # Стандартные библиотеки
    try:
        import os
        import subprocess
        import tempfile
        import zipfile
        import multiprocessing
        import shutil
        from concurrent.futures import ThreadPoolExecutor, as_completed
        print("[OK] Стандартные библиотеки Python")
    except ImportError as e:
        errors.append(f"[ERROR] Стандартные библиотеки: {e}")
    
    # Streamlit
    try:
        import streamlit as st
        print("[OK] streamlit")
    except ImportError as e:
        errors.append(f"[ERROR] streamlit: {e}")
    
    # Torch (опционально, для marker-pdf)
    try:
        import torch
        print("[OK] torch")
    except ImportError as e:
        print(f"[WARN] torch (опционально): {e}")
    
    # Markdown
    try:
        import markdown
        print("[OK] markdown")
    except ImportError as e:
        errors.append(f"[ERROR] markdown: {e}")
    
    # WeasyPrint
    try:
        from weasyprint import HTML
        print("[OK] weasyprint")
    except ImportError as e:
        errors.append(f"[ERROR] weasyprint: {e}")
    
    # Проверка marker-pdf (команда должна быть доступна)
    try:
        import subprocess
        result = subprocess.run(['marker_single', '--help'], 
                              capture_output=True, 
                              timeout=5)
        print("[OK] marker-pdf (команда marker_single доступна)")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"[WARN] marker-pdf: команда marker_single не найдена (может быть недоступна без установки)")
    
    if errors:
        print("\n[ERROR] Обнаружены ошибки:")
        for error in errors:
            print(f"  {error}")
        return False
    else:
        print("\n[OK] Все критичные зависимости установлены!")
        return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)

