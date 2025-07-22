import os
import re
import unicodedata
from datetime import datetime, date
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Lê a URL da base de dados a partir das variáveis de ambiente do Render
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """Cria e retorna uma conexão com a base de dados PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

@app.route('/api/importar', methods=['POST'])
def importar_dados():
    dados_brutos = request.get_data(as_text=True)
    if not dados_brutos:
        return jsonify({"status": "error", "message": "Nenhum dado enviado."}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    registros_importados = 0
    try:
        for linha in dados_brutos.strip().split('\n'):
            if not linha.strip() or '\t' not in linha: continue
            colunas = linha.split('\t')
            if len(colunas) < 5: continue
            data_validade_raw, nome_supermercado, nome_produto_raw, valor_raw, nome_categoria = [c.strip() for c in colunas]
            
            datas_processadas = []
            try:
                partes_data = data_validade_raw.split('/')
                mes_ano_str = f"{partes_data[1]}/{partes_data[2]}"
                dias_str = partes_data[0]
                if '-' in dias_str:
                    inicio, fim = map(int, dias_str.split('-'))
                    for dia in range(inicio, fim + 1):
                        datas_processadas.append(datetime.strptime(f"{dia}/{mes_ano_str}", '%d/%m/%Y').date())
                else:
                    datas_processadas.append(datetime.strptime(data_validade_raw, '%d/%m/%Y').date())
            except (ValueError, IndexError): continue
            
            valor_match = re.search(r'[\d.,]+', valor_raw)
            if not valor_match: continue
            valor_numerico_str = valor_match.group().replace('.', '').replace(',', '.')
            valor_final = float(valor_numerico_str)
            unidade = re.sub(r'R\$\s*[\d.,]+', '', valor_raw).strip()
            obs_match = re.search(r'\((.*?)\)', nome_produto_raw)
            observacoes = obs_match.group(1) if obs_match else None
            nome_produto = re.sub(r'\s*\(.*?\)\s*', '', nome_produto_raw).strip()

            cursor.execute("INSERT INTO supermercados (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING", (nome_supermercado,))
            cursor.execute("SELECT id FROM supermercados WHERE nome = %s", (nome_supermercado,))
            id_supermercado = cursor.fetchone()['id']
            
            cursor.execute("INSERT INTO categorias (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING", (nome_categoria,))
            cursor.execute("SELECT id FROM categorias WHERE nome = %s", (nome_categoria,))
            id_categoria = cursor.fetchone()['id']
            
            cursor.execute("SELECT id FROM produtos WHERE nome = %s AND id_categoria = %s", (nome_produto, id_categoria))
            produto_existente = cursor.fetchone()
            if produto_existente:
                id_produto = produto_existente['id']
            else:
                cursor.execute("INSERT INTO produtos (nome, id_categoria) VALUES (%s, %s) RETURNING id", (nome_produto, id_categoria))
                id_produto = cursor.fetchone()['id']

            for data_valida in datas_processadas:
                cursor.execute("DELETE FROM precos_historicos WHERE id_produto = %s AND id_supermercado = %s AND data_validade = %s", (id_produto, id_supermercado, data_valida))
                cursor.execute("INSERT INTO precos_historicos (id_produto, id_supermercado, valor, unidade, data_validade, observacoes) VALUES (%s, %s, %s, %s, %s, %s)", (id_produto, id_supermercado, valor_final, unidade, data_valida, observacoes))
            
            registros_importados += len(datas_processadas)
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Erro ao importar: {e}")
        return jsonify({"status": "error", "message": f"Erro no servidor: {e}"}), 500
    finally:
        cursor.close()
        conn.close()
        
    return jsonify({"status": "success", "message": f"{registros_importados} registros de ofertas processados com sucesso!"}), 200

@app.route('/api/filtros', methods=['GET'])
def get_filtros():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT id, nome FROM supermercados ORDER BY nome')
    supermercados = cursor.fetchall()
    cursor.execute('SELECT id, nome FROM categorias ORDER BY nome')
    categorias = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({'supermercados': supermercados, 'categorias': categorias})

@app.route('/api/ofertas', methods=['GET'])
def get_ofertas():
    data_selecionada = request.args.get('data') or date.today().strftime('%Y-%m-%d')
    busca = request.args.get('busca', '')
    supermercado_id = request.args.get('supermercado', '')
    categoria_id = request.args.get('categoria', '')
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # No PostgreSQL, a forma correta de ignorar acentos é com a extensão unaccent.
    # Como alternativa simples, usaremos ILIKE para ignorar maiúsculas/minúsculas.
    # Para uma busca sem acentos real, a extensão unaccent seria necessária na base de dados.
    
    query = "SELECT p.nome as produto_nome, ph.valor, ph.unidade, ph.observacoes, ph.id_produto, s.nome as supermercado_nome, c.nome as categoria_nome FROM precos_historicos ph JOIN produtos p ON ph.id_produto = p.id JOIN supermercados s ON ph.id_supermercado = s.id JOIN categorias c ON p.id_categoria = c.id WHERE ph.data_validade = %s"
    params = [data_selecionada]

    if busca:
        query += " AND p.nome ILIKE %s"
        params.append(f'%{busca}%')
    if supermercado_id:
        query += " AND s.id = %s"
        params.append(supermercado_id)
    if categoria_id:
        query += " AND c.id = %s"
        params.append(categoria_id)
    
    query += " ORDER BY p.nome"
    cursor.execute(query, tuple(params))
    ofertas = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return jsonify(ofertas)

@app.route('/api/produto/<int:id_produto>/historico', methods=['GET'])
def get_historico_produto(id_produto):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT ph.valor, ph.data_registro, s.nome AS supermercado_nome FROM precos_historicos ph JOIN supermercados s ON ph.id_supermercado = s.id WHERE ph.id_produto = %s ORDER BY ph.data_registro", (id_produto,))
    historico = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(historico)

@app.route('/api/produtos-em-oferta', methods=['GET'])
def get_produtos_em_oferta():
    data_hoje = date.today()
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = """
        SELECT p.id, p.nome, ph.valor, s.nome as supermercado_nome
        FROM precos_historicos ph
        JOIN produtos p ON ph.id_produto = p.id
        JOIN supermercados s ON ph.id_supermercado = s.id
        WHERE ph.data_validade = %s AND ph.valor = (
            SELECT MIN(ph2.valor)
            FROM precos_historicos ph2
            WHERE ph2.id_produto = ph.id_produto AND ph2.data_validade = %s
        )
        GROUP BY p.id, p.nome, ph.valor, s.nome
        ORDER BY p.nome
    """
    cursor.execute(query, (data_hoje, data_hoje))
    produtos = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(produtos)

@app.route('/api/produto/todas-ofertas-hoje', methods=['GET'])
def get_todas_ofertas_hoje():
    id_produto = request.args.get('id', type=int)
    if not id_produto:
        return jsonify({"error": "ID do produto é obrigatório"}), 400
    data_hoje = date.today()
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT ph.valor, s.nome as supermercado_nome FROM precos_historicos ph JOIN supermercados s ON ph.id_supermercado = s.id WHERE ph.id_produto = %s AND ph.data_validade = %s ORDER BY ph.valor ASC", (id_produto, data_hoje))
    ofertas = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(ofertas)

if __name__ == '__main__':
    app.run(debug=True)
