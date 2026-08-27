import os
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

class Config:
    DB_HOST = 'localhost'
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_NAME = os.getenv('DB_NAME')