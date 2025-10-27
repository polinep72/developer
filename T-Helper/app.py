import asyncio
import os
import logging
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramConflictError
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Настройка логирования
logging.basicConfig(level=logging.INFO, filename="app.log", filemode="a",
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VAULT_PATH = "Z:/50_obsidian/vault"  # Укажите путь, доступный в контейнере

# Проверка переменных
if not GOOGLE_API_KEY or not TELEGRAM_TOKEN:
    logger.error("GOOGLE_API_KEY или TELEGRAM_TOKEN не заданы в .env")
    raise ValueError("Необходимые переменные окружения отсутствуют")

# Функция загрузки документов и создания базы знаний
def load_documents():
    try:
        loader = DirectoryLoader(VAULT_PATH, glob="**/*.md", recursive=True)
        docs = loader.load()
        if not docs:
            logger.warning(f"В папке {VAULT_PATH} нет .md файлов")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)
        for split in splits:
            split.metadata["source"] = os.path.relpath(split.metadata["source"], VAULT_PATH)
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=GOOGLE_API_KEY)
        vectorstore = FAISS.from_documents(splits, embeddings)
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key=GOOGLE_API_KEY)
        qa_chain = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=vectorstore.as_retriever(), return_source_documents=True)
        logger.info("База знаний успешно загружена")
        return qa_chain
    except Exception as e:
        logger.error(f"Ошибка при загрузке документов: {e}")
        raise

qa_chain = load_documents()

# Обновление базы знаний при изменении файлов
class FileChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(".md"):
            logger.info(f"Файл {event.src_path} изменен, обновляю базу знаний...")
            global qa_chain
            try:
                qa_chain = load_documents()
            except Exception as e:
                logger.error(f"Не удалось обновить базу знаний: {e}")

observer = Observer()
observer.schedule(FileChangeHandler(), path=VAULT_PATH, recursive=True)
observer.start()

# Инициализация FastAPI
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_home():
    try:
        with open("static/index.html", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("Файл static/index.html не найден")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера: файл index.html отсутствует")

@app.post("/query", response_class=HTMLResponse)
async def query_assistant(query: str = Form(...)):
    logger.info(f"Получен запрос через веб: {query}")
    try:
        result = await asyncio.to_thread(qa_chain, {"query": query})
        response = result["result"]
        sources = [doc.metadata["source"] for doc in result["source_documents"]]
        sources_str = ", ".join(set(sources))
        full_response = f"{response}\n\n**Источники:** {sources_str}"
        logger.info(f"Ответ для веб: {full_response}")
        return f"<p>{full_response}</p>"
    except Exception as e:
        logger.error(f"Ошибка в /query: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки запроса: {str(e)}")

# Инициализация Telegram-бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot=bot)

@dp.message()
async def handle_message(message: types.Message):
    query = message.text
    logger.info(f"Получен запрос в Telegram: {query}")
    try:
        result = await asyncio.to_thread(qa_chain, {"query": query})
        response = result["result"]
        sources = [doc.metadata["source"] for doc in result["source_documents"]]
        sources_str = ", ".join(set(sources))
        full_response = f"{response}\n\n**Источники:** {sources_str}"
        await message.reply(full_response)
        logger.info(f"Ответ отправлен в Telegram: {full_response}")
    except Exception as e:
        await message.reply("Произошла ошибка при обработке запроса.")
        logger.error(f"Ошибка в Telegram: {e}")

# Асинхронная функция для запуска polling с обработкой конфликтов
async def start_telegram_polling():
    retry_count = 0
    max_retries = 5
    while retry_count < max_retries:
        try:
            logger.info("Запуск Telegram-бота...")
            await dp.start_polling(bot)
            break
        except TelegramConflictError as e:
            retry_count += 1
            logger.warning(f"Конфликт Telegram API: {e}. Попытка {retry_count}/{max_retries}")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Ошибка при запуске Telegram-бота: {e}")
            break
    if retry_count >= max_retries:
        logger.error("Не удалось запустить Telegram-бот из-за повторяющихся конфликтов.")

# Запуск FastAPI и Telegram-бота
async def main():
    telegram_task = asyncio.create_task(start_telegram_polling())
    config = uvicorn.Config(app, host="0.0.0.0", port=8091, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()
    await telegram_task

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Программа остановлена пользователем")
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")
    finally:
        observer.stop()
        observer.join()