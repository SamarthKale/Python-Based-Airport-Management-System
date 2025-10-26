import mysql.connector
from mysql.connector import errorcode

# ============================================
# Database connection configuration
# IMPORTANT: Replace 'your_mysql_password' with your actual MySQL password
# ============================================
config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Swami@2006', # <-- IMPORTANT: CHANGE THIS
    'database': 'airline_pro_db_v2',
    'autocommit': True,
    'buffered': True # Added to prevent 'Unread result' errors in Flask
}

# =iolation (D)
# This function will be called by Flask to get a new connection from the pool
def get_db_connection():
    """
    Establishes a new database connection using the config.
    """
    try:
        conn = mysql.connector.connect(**config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        return None
