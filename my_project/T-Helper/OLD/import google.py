import asyncio
import os
import logging
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.router import Router
from aiogram.exceptions import TelegramConflictError
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VAULT_PATH = "Z:/50_obsidian/vault"

# Инициализация qa_chain как None по умолчанию
qa_chain = None

# Функция загрузки документов и создания базы знаний
def load_documents():
    global qa_chain
    try:
        # Загрузка .md файлов с указанием кодировки UTF-8
        md_loader = DirectoryLoader(
            VAULT_PATH,
            glob="**/*.md",
            loader_cls=lambda path: TextLoader(path, encoding="utf-8"),
            recursive=True
        )
        md_docs = md_loader.load()

        # Загрузка .pdf файлов
        pdf_loader = DirectoryLoader(
            VAULT_PATH,
            glob="**/*.pdf",
            loader_cls=PyPDFLoader,
            recursive=True
        )
        pdf_docs = pdf_loader.load()

        # Объединяем все документы
        docs = md_docs + pdf_docs

        # Разбиваем документы на части
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)
        for split in splits:
            split.metadata["source"] = os.path.relpath(split.metadata["source"], VAULT_PATH)

        # Создаём векторное хранилище
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=GOOGLE_API_KEY)
        vectorstore = FAISS.from_documents(splits, embeddings)

        # Настраиваем LLM с промптом
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key=GOOGLE_API_KEY)
        prompt_template = PromptTemplate(
            input_variables=["context", "question"],
            template="Отвечай только на основе предоставленного контекста: {context}. Вопрос: {question}. Не добавляй внешние ссылки."
        )
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=vectorstore.as_retriever(),
            return_source_documents=True,
            chain_type_kwargs={"prompt": prompt_template}
        )
        logger.info("База знаний успешно загружена (включая .md и .pdf)")
        return qa_chain
    except Exception as e:
        logger.error(f"Ошибка при загрузке документов: {e}")
        qa_chain = None  # Устанавливаем None при ошибке
        return None

# Инициализация qa_chain при старте
try:
    qa_chain = load_documents()
except Exception as e:
    logger.error(f"Не удалось инициализировать qa_chain при старте: {e}")

# Обновление базы знаний при изменении файлов
class FileChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith((".md", ".pdf")):
            logger.info(f"Файл {event.src_path} изменен, обновляю базу знаний...")
            global qa_chain
            qa_chain = load_documents()

observer = Observer()
observer.schedule(FileChangeHandler(), path=VAULT_PATH, recursive=True)
observer.start()

# Инициализация FastAPI
app = FastAPI()
app.mount("/static", StaticFiles(directory="c:/Soft_IPK/T-Helper/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

@app.post("/query", response_class=HTMLResponse)
async def query_assistant(query: str = Form(...)):
    logger.info(f"Получен запрос через веб: {query}")
    if qa_chain is None:
        return "<p>Ошибка: база знаний не инициализирована. Проверьте логи для деталей.</p>"
    try:
        result = await asyncio.to_thread(qa_chain, {"query": query})
        logger.info(f"Ответ для веб: {result}")
        response = result["result"]
        sources = [doc.metadata["source"] for doc in result["source_documents"]]
        sources_str = ", ".join(set(sources))
        full_response = f"{response}\n\n**Источники:** {sources_str}"
        return f"<p>{full_response}</p>"
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")
        return f"<p>Произошла ошибка при обработке запроса: {str(e)}</p>"

# Инициализация Telegram-бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot=bot)
router = Router()

@router.message()
async def handle_message(message: types.Message):
    query = message.text
    logger.info(f"Получен запрос в Telegram: {query}")
    if qa_chain is None:
        await message.reply("Ошибка: база знаний не инициализирована. Проверьте логи для деталей.")
        return
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

dp.include_router(router)

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