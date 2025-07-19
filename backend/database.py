import sqlite3

DATABASE = 'supermercado.db'

def criar_banco():
    # Conecta ao banco de dados (cria o arquivo se não existir)
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Apaga as tabelas se já existirem para um novo começo limpo (cuidado ao usar em produção)
    cursor.execute("DROP TABLE IF EXISTS precos_historicos")
    cursor.execute("DROP TABLE IF EXISTS produtos")
    cursor.execute("DROP TABLE IF EXISTS categorias")
    cursor.execute("DROP TABLE IF EXISTS supermercados")

    # Cria as tabelas
    cursor.execute("""
    CREATE TABLE supermercados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        id_categoria INTEGER,
        FOREIGN KEY (id_categoria) REFERENCES categorias (id)
    )
    """)

    cursor.execute("""
    CREATE TABLE precos_historicos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_produto INTEGER,
        id_supermercado INTEGER,
        valor REAL NOT NULL,
        unidade TEXT,
        data_validade TEXT,
        observacoes TEXT,
        data_registro DATE DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id_produto) REFERENCES produtos (id),
        FOREIGN KEY (id_supermercado) REFERENCES supermercados (id)
    )
    """)

    print("Banco de dados e tabelas criados com sucesso.")
    conn.commit()
    conn.close()

# Executa a função para criar o banco quando o script for chamado
if __name__ == '__main__':
    criar_banco()