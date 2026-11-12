import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Abre una conexion nueva a Postgres usando DATABASE_URL."""
    return psycopg2.connect(os.environ["DATABASE_URL"])
