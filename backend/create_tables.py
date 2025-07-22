import os
import psycopg2

# Tenta ler o URL da base de dados a partir da variável de ambiente
DATABASE_URL = os.environ.get('DATABASE_URL_EXT')

if not DATABASE_URL:
    print("Erro: A variável de ambiente DATABASE_URL_EXT não foi definida.")
    print("Por favor, execute o comando 'set' ou 'export' antes de correr este script.")
else:
    # As queries de criação de tabelas para PostgreSQL
    commands = (
        """
        DROP TABLE IF EXISTS precos_historicos CASCADE;
        DROP TABLE IF EXISTS produtos CASCADE;
        DROP TABLE IF EXISTS categorias CASCADE;
        DROP TABLE IF EXISTS supermercados CASCADE;
        """,
        """
        CREATE TABLE supermercados (
            id SERIAL PRIMARY KEY,
            nome TEXT UNIQUE NOT NULL
        );
        """,
        """
        CREATE TABLE categorias (
            id SERIAL PRIMARY KEY,
            nome TEXT UNIQUE NOT NULL
        );
        """,
        """
        CREATE TABLE produtos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            id_categoria INTEGER,
            FOREIGN KEY (id_categoria) REFERENCES categorias (id)
        );
        """,
        """
        CREATE TABLE precos_historicos (
            id SERIAL PRIMARY KEY,
            id_produto INTEGER,
            id_supermercado INTEGER,
            valor REAL NOT NULL,
            unidade TEXT,
            data_validade DATE,
            observacoes TEXT,
            data_registro DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (id_produto) REFERENCES produtos (id),
            FOREIGN KEY (id_supermercado) REFERENCES supermercados (id)
        );
        """
    )

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Executa cada comando
        for command in commands:
            cur.execute(command)
        # Fecha a comunicação e guarda as alterações
        cur.close()
        conn.commit()
        print("Tabelas criadas com sucesso no PostgreSQL!")
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()
