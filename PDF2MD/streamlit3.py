import os
import subprocess
import streamlit as st
import torch
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
import shutil

# Интерфейс Streamlit
st.title("PDF Converter")

# Проверяем наличие CUDA
#cuda_available = torch.cuda.is_available()
cuda_available = 0

# Определяем количество потоков
max_workers = multiprocessing.cpu_count()
workers = st.slider("Количество потоков", 1, max_workers, 2)

mode = st.radio("Выберите режим, несколько pdf или архив:", ("PDF", "ZIP"), index=0,horizontal=True)

# Если CUDA есть, показываем переключатель
if cuda_available:
    device = st.radio("Выберите устройство:", ("GPU", "CPU"), index=0,horizontal=True)
    os.environ["CUDA_VISIBLE_DEVICES"] = "0" if device == "GPU" else ""
else:
    st.write("CUDA-совместимая видеокарта не найдена. Используется CPU.")
    device = "CPU"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

# Загрузка файлов
with st.form("upload_form", clear_on_submit=True):
    if mode == "PDF":   
        uploaded_files = st.file_uploader("Перетащите PDF-файлы", type="pdf", accept_multiple_files=True)
        process_button = st.form_submit_button("Преобразовать")
    else:
        uploaded_files = st.file_uploader("Перетащите ZIP-файл", type="zip", accept_multiple_files=False)
        process_button = st.form_submit_button("Преобразовать архив")

# Функция обработки одного PDF
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

# Обработчик
if uploaded_files and process_button:
    with tempfile.TemporaryDirectory() as temp_dir:
        results = []

        if mode == "PDF":
            pdf_paths = []
            for uploaded_file in uploaded_files:
                temp_pdf_path = os.path.join(temp_dir, uploaded_file.name)
                with open(temp_pdf_path, "wb") as f:
                    f.write(uploaded_file.read())
                pdf_paths.append(temp_pdf_path)
        else:
            zip_path = os.path.join(temp_dir, "uploaded.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_files.read())
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            pdf_paths = []
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(".pdf"):
                        pdf_paths.append(os.path.join(root, file))

        # Многопоточная обработка
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_single_pdf, pdf_path, os.path.dirname(pdf_path) ): pdf_path for pdf_path in pdf_paths}
            progress_bar = st.progress(0)
            total_files = len(pdf_paths)

            for i, future in enumerate(as_completed(futures), start=1):
                try:
                    result = future.result()
                    results.append(result)
                    if result[1]:
                        st.write(f"✅ {result[0]} обработан")
                    else:
                        st.error(f"❌ {result[0]} — {result[2]}")
                except Exception as e:
                    st.error(f"❌ Ошибка обработки файла: {str(e)}")
                progress_bar.progress(i / total_files)
            progress_bar.empty()

        # Архивация результатов с сохранением структуры папок
        zip_path = os.path.join(temp_dir, "results.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(".pdf") or file.endswith(".zip"):
                        continue  # Пропускаем исходные PDF и загруженный архив
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)

        # Скачивание архива
        with open(zip_path, "rb") as f:
            st.download_button("Скачать архив", f, "results.zip", "application/zip")
