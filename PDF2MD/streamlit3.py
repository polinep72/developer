import os
import subprocess
import streamlit as st
import torch
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
import shutil
import markdown
from xhtml2pdf import pisa
from io import BytesIO

# Интерфейс Streamlit
st.title("PDF ↔ MD Converter")
st.markdown("---")

# Описание приложения
with st.expander("ℹ️ О приложении", expanded=False):
    st.markdown("""
    **PDF ↔ MD Converter** - инструмент для двунаправленной конвертации документов:
    
    - **PDF → MD**: Конвертация PDF документов в формат Markdown с сохранением структуры, изображений и таблиц
    - **MD → PDF**: Конвертация Markdown файлов в PDF с красивым форматированием
    
    **Поддерживаемые форматы:**
    - Отдельные файлы (PDF или MD)
    - ZIP архивы с множеством файлов
    
    **Особенности:**
    - Многопоточная обработка для ускорения работы
    - Автоматическое создание архива с результатами
    - Сохранение структуры папок и медиа-файлов
    """)

# Выбор направления конвертации
st.markdown("### Выберите направление конвертации")
conversion_direction = st.radio("Направление конвертации:", ("PDF → MD", "MD → PDF"), index=0, horizontal=True, label_visibility="collapsed")

# Информация о выбранном направлении
if conversion_direction == "PDF → MD":
    st.info("📄 **PDF → MD**: Загрузите PDF файлы для конвертации в Markdown. Поддерживаются изображения, таблицы и структурированный текст.")
else:
    st.info("📝 **MD → PDF**: Загрузите Markdown файлы для конвертации в PDF. Поддерживаются все стандартные элементы Markdown (заголовки, списки, таблицы, код, изображения).")

# Проверяем наличие CUDA
#cuda_available = torch.cuda.is_available()
cuda_available = 0

st.markdown("---")
st.markdown("### Настройки обработки")

# Определяем количество потоков
max_workers = multiprocessing.cpu_count()
workers = st.slider("Количество потоков", 1, max_workers, 2, 
                   help="Увеличьте количество потоков для ускорения обработки нескольких файлов")

mode = st.radio("Режим загрузки:", ("Файлы", "ZIP"), index=0, horizontal=True,
                help="Выберите загрузку отдельных файлов или ZIP архива")

# Если CUDA есть, показываем переключатель
if cuda_available:
    device = st.radio("Выберите устройство:", ("GPU", "CPU"), index=0,horizontal=True)
    os.environ["CUDA_VISIBLE_DEVICES"] = "0" if device == "GPU" else ""
else:
    st.write("CUDA-совместимая видеокарта не найдена. Используется CPU.")
    device = "CPU"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

st.markdown("---")
st.markdown("### Загрузка файлов")

# Загрузка файлов
with st.form("upload_form", clear_on_submit=True):
    if conversion_direction == "PDF → MD":
        if mode == "Файлы":   
            uploaded_files = st.file_uploader(
                "Перетащите PDF-файлы или нажмите для выбора", 
                type="pdf", 
                accept_multiple_files=True,
                help="Можно загрузить несколько PDF файлов одновременно"
            )
            process_button = st.form_submit_button("🔄 Преобразовать PDF → MD", use_container_width=True)
        else:
            uploaded_files = st.file_uploader(
                "Перетащите ZIP-файл с PDF документами", 
                type="zip", 
                accept_multiple_files=False,
                help="ZIP архив должен содержать PDF файлы"
            )
            process_button = st.form_submit_button("🔄 Преобразовать архив PDF → MD", use_container_width=True)
    else:  # MD → PDF
        if mode == "Файлы":
            uploaded_files = st.file_uploader(
                "Перетащите MD-файлы или нажмите для выбора", 
                type="md", 
                accept_multiple_files=True,
                help="Можно загрузить несколько Markdown файлов одновременно"
            )
            process_button = st.form_submit_button("🔄 Преобразовать MD → PDF", use_container_width=True)
        else:
            uploaded_files = st.file_uploader(
                "Перетащите ZIP-файл с MD документами", 
                type="zip", 
                accept_multiple_files=False,
                help="ZIP архив должен содержать Markdown файлы"
            )
            process_button = st.form_submit_button("🔄 Преобразовать архив MD → PDF", use_container_width=True)

# Функция обработки одного PDF в MD
def process_single_pdf(pdf_path, output_dir):
    try:
        basename = os.path.splitext(os.path.basename(pdf_path))[0]
        output_subdir = os.path.join(output_dir, basename)
        os.makedirs(output_subdir, exist_ok=True)
        
        command = f'marker_single "{pdf_path}" --output_dir "{output_subdir}"'
        subprocess.run(command, check=True, shell=True)

        # Создаем папку data и перемещаем файлы
        data_folder = os.path.join(output_subdir, "data")
        os.makedirs(data_folder, exist_ok=True)

        output_folder = os.path.join(output_subdir, basename)
        if not os.path.exists(output_folder):
            return (basename, False, "Папка результатов не найдена")

        for filename in os.listdir(output_folder):
            src_path = os.path.join(output_folder, filename)
            if os.path.isfile(src_path) and not filename.lower().endswith(".md"):
                shutil.move(src_path, os.path.join(data_folder, filename))

        # Обновляем ссылки в md-файле
        md_file = os.path.join(output_folder, f"{basename}.md")
        if os.path.exists(md_file):
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
            updated_content = content.replace("](./", "](./data/")
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(updated_content)
            shutil.move(md_file, os.path.join(output_subdir, f"{basename}.md"))

        return (basename, True, "Обработан")
    except subprocess.CalledProcessError as e:
        return (basename, False, f"Ошибка выполнения команды: {str(e)}")
    except Exception as e:
        return (basename, False, f"Ошибка: {str(e)}")

# Функция обработки одного MD в PDF
def process_single_md(md_path, output_dir):
    try:
        basename = os.path.splitext(os.path.basename(md_path))[0]
        output_subdir = os.path.join(output_dir, basename)
        os.makedirs(output_subdir, exist_ok=True)
        
        # Читаем MD файл
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        
        # Конвертируем MD в HTML
        html_content = markdown.markdown(md_content, extensions=['extra', 'codehilite', 'tables', 'toc'])
        
        # Добавляем базовые стили для улучшения внешнего вида PDF
        html_with_styles = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    color: #333;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    color: #2c3e50;
                    margin-top: 1.5em;
                    margin-bottom: 0.5em;
                }}
                code {{
                    background-color: #f4f4f4;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: 'Courier New', monospace;
                }}
                pre {{
                    background-color: #f4f4f4;
                    padding: 15px;
                    border-radius: 5px;
                    overflow-x: auto;
                }}
                pre code {{
                    background-color: transparent;
                    padding: 0;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 1em 0;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #4CAF50;
                    color: white;
                }}
                img {{
                    max-width: 100%;
                    height: auto;
                }}
                a {{
                    color: #3498db;
                    text-decoration: none;
                }}
                blockquote {{
                    border-left: 4px solid #3498db;
                    margin: 1em 0;
                    padding-left: 1em;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        # Конвертируем HTML в PDF
        pdf_path = os.path.join(output_subdir, f"{basename}.pdf")
        result_file = open(pdf_path, "w+b")
        pisa_status = pisa.CreatePDF(
            BytesIO(html_with_styles.encode("utf-8")),
            dest=result_file
        )
        result_file.close()
        
        if pisa_status.err:
            return (basename, False, f"Ошибка создания PDF: {pisa_status.err}")
        
        return (basename, True, "Обработан")
    except Exception as e:
        return (basename, False, f"Ошибка: {str(e)}")

# Обработчик
if uploaded_files and process_button:
    with tempfile.TemporaryDirectory() as temp_dir:
        results = []
        file_paths = []

        if mode == "Файлы":
            for uploaded_file in uploaded_files:
                temp_file_path = os.path.join(temp_dir, uploaded_file.name)
                with open(temp_file_path, "wb") as f:
                    f.write(uploaded_file.read())
                file_paths.append(temp_file_path)
        else:  # ZIP режим
            zip_path = os.path.join(temp_dir, "uploaded.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_files.read())
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Ищем файлы нужного типа
            file_extension = ".pdf" if conversion_direction == "PDF → MD" else ".md"
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(file_extension):
                        file_paths.append(os.path.join(root, file))

        if not file_paths:
            file_extension = ".pdf" if conversion_direction == "PDF → MD" else ".md"
            st.error(f"Не найдено файлов для обработки ({file_extension})")
        else:
            # Многопоточная обработка
            with ThreadPoolExecutor(max_workers=workers) as executor:
                if conversion_direction == "PDF → MD":
                    futures = {executor.submit(process_single_pdf, file_path, os.path.dirname(file_path)): file_path for file_path in file_paths}
                else:  # MD → PDF
                    futures = {executor.submit(process_single_md, file_path, os.path.dirname(file_path)): file_path for file_path in file_paths}
                
                progress_bar = st.progress(0)
                total_files = len(file_paths)

                st.markdown("---")
                st.markdown("### Результаты обработки")
                
                # Контейнеры для результатов
                success_container = st.container()
                error_container = st.container()
                
                success_count = 0
                error_count = 0
                
                for i, future in enumerate(as_completed(futures), start=1):
                    try:
                        result = future.result()
                        results.append(result)
                        if result[1]:
                            success_count += 1
                            with success_container:
                                st.success(f"✅ **{result[0]}** — успешно обработан")
                        else:
                            error_count += 1
                            with error_container:
                                st.error(f"❌ **{result[0]}** — {result[2]}")
                    except Exception as e:
                        error_count += 1
                        with error_container:
                            st.error(f"❌ Ошибка обработки файла: {str(e)}")
                    progress_bar.progress(i / total_files)
                progress_bar.empty()
                
                # Итоговая статистика
                if success_count > 0 or error_count > 0:
                    st.markdown("---")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Успешно обработано", success_count)
                    with col2:
                        st.metric("Ошибок", error_count)

            # Архивация результатов с сохранением структуры папок
            zip_path = os.path.join(temp_dir, "results.zip")
            skip_extensions = [".pdf", ".zip"] if conversion_direction == "PDF → MD" else [".md", ".zip"]
            
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        # Пропускаем исходные файлы и загруженный архив
                        should_skip = any(file.endswith(ext) for ext in skip_extensions)
                        if should_skip and root == temp_dir:
                            continue
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, arcname)

            # Скачивание архива
            st.markdown("---")
            st.markdown("### Скачать результаты")
            with open(zip_path, "rb") as f:
                st.download_button(
                    "📥 Скачать архив с результатами", 
                    f, 
                    "results.zip", 
                    "application/zip",
                    use_container_width=True,
                    help="Архив содержит все обработанные файлы с сохранением структуры папок"
                )
