# Importações necessárias
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import re
from datetime import datetime, date

# Inicializa a aplicação Flask e habilita o CORS
app = Flask(__name__)
CORS(app)

DATABASE = 'supermercado.db'

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/importar', methods=['POST'])
def importar_dados():
    dados_brutos = request.get_data(as_text=True)
    if not dados_brutos:
        return jsonify({"status": "error", "message": "Nenhum dado enviado."}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
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
                        data_obj = datetime.strptime(f"{dia}/{mes_ano_str}", '%d/%m/%Y')
                        datas_processadas.append(data_obj.strftime('%Y-%m-%d'))
                else:
                    data_obj = datetime.strptime(data_validade_raw, '%d/%m/%Y')
                    datas_processadas.append(data_obj.strftime('%Y-%m-%d'))
            except (ValueError, IndexError): continue
            valor_match = re.search(r'[\d.,]+', valor_raw)
            if not valor_match: continue
            valor_numerico_str = valor_match.group().replace('.', '').replace(',', '.')
            valor_final = float(valor_numerico_str)
            unidade = re.sub(r'R\$\s*[\d.,]+', '', valor_raw).strip()
            obs_match = re.search(r'\((.*?)\)', nome_produto_raw)
            observacoes = obs_match.group(1) if obs_match else None
            nome_produto = re.sub(r'\s*\(.*?\)\s*', '', nome_produto_raw).strip()
            cursor.execute("INSERT OR IGNORE INTO supermercados (nome) VALUES (?)", (nome_supermercado,))
            id_supermercado = cursor.execute("SELECT id FROM supermercados WHERE nome = ?", (nome_supermercado,)).fetchone()['id']
            cursor.execute("INSERT OR IGNORE INTO categorias (nome) VALUES (?)", (nome_categoria,))
            id_categoria = cursor.execute("SELECT id FROM categorias WHERE nome = ?", (nome_categoria,)).fetchone()['id']
            produto_existente = cursor.execute("SELECT id FROM produtos WHERE nome = ? AND id_categoria = ?", (nome_produto, id_categoria)).fetchone()
            id_produto = produto_existente['id'] if produto_existente else cursor.execute("INSERT INTO produtos (nome, id_categoria) VALUES (?, ?)", (nome_produto, id_categoria)).lastrowid
            for data_valida in datas_processadas:
                cursor.execute("DELETE FROM precos_historicos WHERE id_produto = ? AND id_supermercado = ? AND data_validade = ?", (id_produto, id_supermercado, data_valida))
                cursor.execute("INSERT INTO precos_historicos (id_produto, id_supermercado, valor, unidade, data_validade, observacoes) VALUES (?, ?, ?, ?, ?, ?)", (id_produto, id_supermercado, valor_final, unidade, data_valida, observacoes))
            registros_importados += len(datas_processadas)
        conn.commit()
        return jsonify({"status": "success", "message": f"{registros_importados} registros de ofertas processados com sucesso!"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": f"Erro no servidor: {e}"}), 500
    finally:
        conn.close()

@app.route('/api/filtros', methods=['GET'])
def get_filtros():
    conn = get_db_connection()
    supermercados = conn.execute('SELECT id, nome FROM supermercados ORDER BY nome').fetchall()
    categorias = conn.execute('SELECT id, nome FROM categorias ORDER BY nome').fetchall()
    conn.close()
    return jsonify({'supermercados': [dict(row) for row in supermercados], 'categorias': [dict(row) for row in categorias]})

@app.route('/api/ofertas', methods=['GET'])
def get_ofertas():
    data_selecionada = request.args.get('data') or date.today().strftime('%Y-%m-%d')
    busca = request.args.get('busca', '')
    supermercado_id = request.args.get('supermercado', '')
    categoria_id = request.args.get('categoria', '')
    conn = get_db_connection()
    query = "SELECT p.nome as produto_nome, ph.valor, ph.unidade, ph.observacoes, ph.id_produto, s.nome as supermercado_nome, c.nome as categoria_nome FROM precos_historicos ph JOIN produtos p ON ph.id_produto = p.id JOIN supermercados s ON ph.id_supermercado = s.id JOIN categorias c ON p.id_categoria = c.id WHERE ph.data_validade = ?"
    params = [data_selecionada]
    if busca:
        query += " AND p.nome LIKE ?"
        params.append(f'%{busca}%')
    if supermercado_id:
        query += " AND s.id = ?"
        params.append(supermercado_id)
    if categoria_id:
        query += " AND c.id = ?"
        params.append(categoria_id)
    query += " ORDER BY p.nome"
    ofertas = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(row) for row in ofertas])

# --- ROTA CORRIGIDA ---
@app.route('/api/produto/<int:id_produto>/historico', methods=['GET'])
def get_historico_produto(id_produto):
    """
    Retorna o histórico de preços de um produto, incluindo o nome do supermercado.
    Esta versão aceita o ID do produto diretamente no URL.
    """
    conn = get_db_connection()
    historico = conn.execute("""
        SELECT
            ph.valor,
            ph.data_registro,
            s.nome AS supermercado_nome
        FROM precos_historicos ph
        JOIN supermercados s ON ph.id_supermercado = s.id
        WHERE ph.id_produto = ?
        ORDER BY ph.data_registro
    """, (id_produto,)).fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in historico])

@app.route('/api/produtos-em-oferta', methods=['GET'])
def get_produtos_em_oferta():
    data_hoje = date.today().strftime('%Y-%m-%d')
    conn = get_db_connection()
    produtos = conn.execute("SELECT p.id, p.nome, ph.valor, s.nome as supermercado_nome FROM precos_historicos ph JOIN produtos p ON ph.id_produto = p.id JOIN supermercados s ON ph.id_supermercado = s.id WHERE ph.data_validade = ? AND ph.valor = (SELECT MIN(ph2.valor) FROM precos_historicos ph2 WHERE ph2.id_produto = ph.id_produto AND ph2.data_validade = ?) GROUP BY p.id ORDER BY p.nome", (data_hoje, data_hoje)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in produtos])

@app.route('/api/produto/todas-ofertas-hoje', methods=['GET'])
def get_todas_ofertas_hoje():
    id_produto = request.args.get('id', type=int)
    if not id_produto:
        return jsonify({"error": "ID do produto é obrigatório"}), 400
    data_hoje = date.today().strftime('%Y-%m-%d')
    conn = get_db_connection()
    ofertas = conn.execute("SELECT ph.valor, s.nome as supermercado_nome FROM precos_historicos ph JOIN supermercados s ON ph.id_supermercado = s.id WHERE ph.id_produto = ? AND ph.data_validade = ? ORDER BY ph.valor ASC", (id_produto, data_hoje)).fetchall()
    conn.close()
    if ofertas:
        return jsonify([dict(row) for row in ofertas])
    else:
        return jsonify([])

if __name__ == '__main__':
    app.run(debug=True)
