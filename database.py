import sqlite3
import os

DATABASE_FILE = "clientes.db"

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # Permite acessar os dados por nome da coluna
    return conn

def init_db():
    """Inicializa o banco de dados e cria a tabela de clientes se ela não existir."""
    if os.path.exists(DATABASE_FILE):
        return # Banco de dados já existe

    print("Inicializando o banco de dados pela primeira vez...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            razao_social TEXT NOT NULL,
            endereco TEXT,
            bairro TEXT,
            cidade TEXT,
            uf TEXT,
            cep TEXT,
            cnpj TEXT UNIQUE,
            inscricao_estadual TEXT,
            telefone TEXT,
            contato TEXT,
            email TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("Banco de dados 'clientes.db' criado com sucesso.")

def add_client(cliente_data):
    """Adiciona um novo cliente ao banco de dados."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO clientes (razao_social, endereco, bairro, cidade, uf, cep, cnpj, inscricao_estadual, telefone, contato, email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            cliente_data['razao_social'], cliente_data['endereco'], cliente_data['bairro'],
            cliente_data['cidade'], cliente_data['uf'], cliente_data['cep'],
            cliente_data['cnpj'], cliente_data['inscricao_estadual'], cliente_data['telefone'],
            cliente_data['contato'], cliente_data['email']
        ))
        conn.commit()
        print(f"Cliente '{cliente_data['razao_social']}' adicionado com sucesso.")
        return True
    except sqlite3.IntegrityError:
        print(f"Erro: Cliente com CNPJ '{cliente_data['cnpj']}' já existe.")
        return False
    finally:
        conn.close()

def get_all_clients():
    """Retorna uma lista de todos os clientes cadastrados."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, razao_social FROM clientes ORDER BY razao_social ASC")
    clientes = cursor.fetchall()
    conn.close()
    return clientes

def get_client_by_id(client_id):
    """Busca e retorna os dados completos de um cliente pelo seu ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE id = ?", (client_id,))
    cliente = cursor.fetchone()
    conn.close()
    return cliente

