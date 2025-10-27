from os import getenv
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "user": getenv("POSTGRE_USER"),
    "password": getenv("POSTGRE_PASSWORD"),
    "dbname": getenv("POSTGRE_DBNAME"),
    "host": getenv("POSTGRE_DBHOST")
}