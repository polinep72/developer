import pandas as pd
import sqlite3
import os

def analyze_excel_file():
    """Анализирует Excel файл и определяет структуру данных"""
    excel_file = "ПЕРЕЧЕНЬ СИ и ИО.xlsx"
    
    if not os.path.exists(excel_file):
        print(f"Файл {excel_file} не найден!")
        return
    
    try:
        # Получаем список всех листов
        excel_data = pd.ExcelFile(excel_file)
        sheet_names = excel_data.sheet_names
        
        print(f"Найдено листов: {len(sheet_names)}")
        print(f"Названия листов: {sheet_names}")
        
        # Анализируем каждый лист
        for sheet_name in sheet_names:
            print(f"\n--- Анализ листа: {sheet_name} ---")
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            print(f"Размер данных: {df.shape[0]} строк, {df.shape[1]} столбцов")
            print(f"Столбцы: {list(df.columns)}")
            
            # Показываем первые несколько строк
            print("Первые 3 строки:")
            print(df.head(3).to_string())
            
            # Проверяем типы данных
            print(f"\nТипы данных:")
            for col in df.columns:
                non_null_count = df[col].count()
                print(f"  {col}: {df[col].dtype} (непустых значений: {non_null_count})")
    
    except Exception as e:
        print(f"Ошибка при анализе файла: {e}")

if __name__ == "__main__":
    analyze_excel_file()
