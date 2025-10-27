import asyncio
import os
from dotenv import load_dotenv
import langchain_community
from langchain_community.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.vectorstores import FAISS
from langchain.chains import RetrievalQA
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from aiogram import Bot, Dispatcher, types
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Загрузка переменных окружения
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VAULT_PATH = "Z:/50_obsidian//vault"  # Путь к документации в контейнере


# Функция для загрузки документов и изображений
def load_documents_and_images():
    # Рекурсивная загрузка .md файлов
    loader = DirectoryLoader(VAULT_PATH, glob="**/*.md", recursive=True)
    docs = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)

    # Сохранение относительных путей к файлам в метаданных
    for split in splits:
        split.metadata["source"] = os.path.relpath(split.metadata["source"], VAULT_PATH)

    # Загрузка .jpg файлов и связывание с .md файлами по папкам
    image_dict = {}
    for root, _, files in os.walk(VAULT_PATH):
        for file in files:
            if file.endswith(".jpg"):
                folder = os.path.relpath(root, VAULT_PATH)
                image_path = os.path.join(folder, file)
                image_dict.setdefault(folder, []).append(image_path)

    # Добавление информации об изображениях в метаданные документов
    for split in splits:
        folder = os.path.dirname(split.metadata["source"])
        if folder in image_dict:
            split.metadata["images"] = image_dict[folder]
        else:
            split.metadata["images"] = []

    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=GOOGLE_API_KEY)
    vectorstore = FAISS.from_documents(splits, embeddings)
    llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=GOOGLE_API_KEY)
    qa_chain = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=vectorstore.as_retriever(),
                                           return_source_documents=True)
    return qa_chain, image_dict


qa_chain, image_dict = load_documents_and_images()


# Обновление базы знаний при изменении файлов
class FileChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(".md") or event.src_path.endswith(".jpg"):
            print(f"Файл {event.src_path} изменен, обновляю базу знаний...")
            global qa_chain, image_dict
            qa_chain, image_dict = load_documents_and_images()


observer = Observer()
observer.schedule(FileChangeHandler(), path=VAULT_PATH, recursive=True)
observer.start()

# Инициализация FastAPI
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/query", response_class=HTMLResponse)
async def query_assistant(query: str = Form(...)):
    result = await asyncio.to_thread(qa_chain, {"query": query})
    response = result["result"]
    sources = [doc.metadata["source"] for doc in result["source_documents"]]
    images = set()
    for doc in result["source_documents"]:
        images.update(doc.metadata.get("images", []))
    sources_str = ", ".join(set(sources))
    images_str = ", ".join(images) if images else "Нет изображений"
    full_response = f"{response}\n\n**Источники:** {sources_str}\n\n**Изображения:** {images_str}"
    return f"<p>{full_response}</p>"


# Инициализация Telegram-бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)


@dp.message_handler()
async def handle_message(message: types.Message):
    query = message.text
    result = await asyncio.to_thread(qa_chain, {"query": query})
    response = result["result"]
    sources = [doc.metadata["source"] for doc in result["source_documents"]]
    images = set()
    for doc in result["source_documents"]:
        images.update(doc.metadata.get("images", []))
    sources_str = ", ".join(set(sources))
    images_str = ", ".join(images) if images else "Нет изображений"
    full_response = f"{response}\n\n**Источники:** {sources_str}\n\n**Изображения:** {images_str}"
    await message.reply(full_response)


# Запуск FastAPI и Telegram-бота
async def main():
    polling_task = asyncio.create_task(dp.start_polling())
    config = uvicorn.Config(app, host="0.0.0.0", port=8091, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())