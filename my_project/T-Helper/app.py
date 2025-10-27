import asyncio
import os
import logging
import locale
import warnings
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, UnstructuredMarkdownLoader
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
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Настройка локалей и фильтрация предупреждений
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")

# Загрузка секретов
if os.path.exists('/run/secrets/google_api_key'):
    with open('/run/secrets/google_api_key', 'r') as f:
        GOOGLE_API_KEY = f.read().strip()
    with open('/run/secrets/telegram_token', 'r') as f:
        TELEGRAM_TOKEN = f.read().strip()
else:
    load_dotenv()
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Конфигурация приложения
VAULT_PATH = "/vault"
NETWORK_PATH = os.getenv("NETWORK_PATH")
NETWORK_USER = os.getenv("NETWORK_USER")
NETWORK_PASS = os.getenv("NETWORK_PASS")
EXCLUDED_FILES = {'??? ????????.md', '?????????????? ????????.md'}

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def mount_network_drive():
    """Монтирование сетевого хранилища с обработкой ошибок"""
    try:
        vault_path = Path(VAULT_PATH)
        vault_path.mkdir(parents=True, exist_ok=True)

        if not any(vault_path.iterdir()):
            cmd = [
                "mount",
                "-t", "cifs",
                NETWORK_PATH,
                str(vault_path),
                "-o",
                f"username={NETWORK_USER},password={NETWORK_PASS},vers=3.0,uid=1000,gid=1000,file_mode=0777,dir_mode=0777,noperm,iocharset=utf8"
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"Mount error: {result.stderr}")
            logger.info("Сетевой диск успешно смонтирован")

    except Exception as e:
        logger.error(f"Ошибка монтирования: {str(e)}")
        raise


def load_documents():
    """Загрузка и обработка документов с улучшенной обработкой ошибок"""
    global qa_chain
    try:
        mount_network_drive()
        vault_path = Path(VAULT_PATH).resolve()
        logger.info(f"Начало обработки документов в: {vault_path}")

        # Загрузка Markdown
        md_docs = []
        for md_file in vault_path.rglob("*.md"):
            if md_file.name in EXCLUDED_FILES:
                continue
            try:
                loader = UnstructuredMarkdownLoader(str(md_file), mode="elements")
                md_docs.extend(loader.load())
                logger.debug(f"Успешно загружен: {md_file.name}")
            except Exception as e:
                logger.error(f"Ошибка загрузки {md_file}: {str(e)}")
                continue

        # Загрузка PDF
        pdf_docs = []
        for pdf_file in vault_path.rglob("*.pdf"):
            try:
                loader = PyPDFLoader(str(pdf_file))
                pdf_docs.extend(loader.load())
                logger.debug(f"Успешно загружен: {pdf_file.name}")
            except Exception as e:
                logger.error(f"Ошибка загрузки {pdf_file}: {str(e)}")
                continue

        # Обработка документов
        docs = md_docs + pdf_docs
        if not docs:
            logger.warning("Нет документов для обработки")
            return None

        # Разделение текста
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )
        splits = text_splitter.split_documents(docs)

        # Инициализация моделей
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=GOOGLE_API_KEY
        )

        vectorstore = FAISS.from_documents(splits, embeddings)

        # Настройка цепочки QA
        llm = ChatGoogleGenerativeAI(
            model="gemini-pro",
            temperature=0.3,
            google_api_key=GOOGLE_API_KEY
        )

        qa_chain = RetrievalQA.from_chain_type(
            llm,
            retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
            return_source_documents=True,
            chain_type_kwargs={
                "prompt": PromptTemplate(
                    template="""
                    Анализируй вопрос и предоставь ответ на основе контекста.
                    Контекст: {context}
                    Вопрос: {question}
                    Если ответа нет в контексте - ответь "Информация не найдена".
                    Ответ:
                    """,
                    input_variables=["context", "question"],
                )
            }
        )
        logger.info("База знаний успешно инициализирована")
        return qa_chain

    except Exception as e:
        logger.error(f"Критическая ошибка при загрузке документов: {str(e)}")
        return None


# Инициализация при запуске
try:
    qa_chain = load_documents()
except Exception as e:
    logger.error(f"Ошибка инициализации: {str(e)}")
    qa_chain = None


# Система наблюдения за файлами
class VaultFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith((".md", ".pdf")):
            logger.info(f"Обнаружено изменение: {event.src_path}")
            global qa_chain
            try:
                qa_chain = load_documents()
                logger.info("База знаний успешно обновлена")
            except Exception as e:
                logger.error(f"Ошибка обновления: {str(e)}")


if Path(VAULT_PATH).exists():
    observer = Observer()
    observer.schedule(VaultFileHandler(), VAULT_PATH, recursive=True)
    observer.start()
    logger.info("Система наблюдения за файлами активирована")
else:
    logger.error("Директория vault недоступна")

# Инициализация FastAPI
app = FastAPI(title="AI Tech Assistant")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <body>
            <form action="/query" method="post">
                <input type="text" name="query" placeholder="Ваш вопрос">
                <button type="submit">Спросить</button>
            </form>
        </body>
    </html>
    """


@app.post("/query")
async def handle_query(query: str = Form(...)):
    if not qa_chain:
        return {"error": "Система не инициализирована"}

    try:
        result = await asyncio.to_thread(qa_chain.invoke, {"query": query})
        sources = list({doc.metadata["source"] for doc in result["source_documents"]})
        return {
            "answer": result["result"],
            "sources": sources
        }
    except Exception as e:
        logger.error(f"Ошибка запроса: {str(e)}")
        return {"error": "Ошибка обработки запроса"}


# Инициализация Telegram бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
router = Router()


@router.message()
async def telegram_handler(message: types.Message):
    if not qa_chain:
        await message.answer("Система не инициализирована")
        return

    try:
        result = await asyncio.to_thread(qa_chain.invoke, {"query": message.text})
        sources = "\n".join({f"• {Path(doc.metadata['source']).name}"
                             for doc in result["source_documents"]})
        response = f"{result['result']}\n\nИсточники:\n{sources}"
        await message.answer(response)
    except Exception as e:
        logger.error(f"Ошибка Telegram: {str(e)}")
        await message.answer("Произошла ошибка обработки")


dp.include_router(router)


async def run_services():
    await asyncio.gather(
        dp.start_polling(bot),
        uvicorn.Server(
            uvicorn.Config(
                app,
                host="0.0.0.0",
                port=8091,
                log_level="info"
            )
        ).serve()
    )


if __name__ == "__main__":
    try:
        asyncio.run(run_services())
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Приложение остановлено")
    finally:
        observer.join()