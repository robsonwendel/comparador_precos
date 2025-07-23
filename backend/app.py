import os
import re
import unicodedata
from datetime import datetime, date
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

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
    
    try:
        # --- LÓGICA DE IMPORTAÇÃO OTIMIZADA ---

        # 1. Pré-carregar dados existentes para evitar queries dentro do loop
        cursor.execute("SELECT nome, id FROM supermercados")
        supermercados_map = {row['nome']: row['id'] for row in cursor.fetchall()}
        
        cursor.execute("SELECT nome, id FROM categorias")
        categorias_map = {row['nome']: row['id'] for row in cursor.fetchall()}

        cursor.execute("SELECT nome, id_categoria, id FROM produtos")
        produtos_map = {(row['nome'], row['id_categoria']): row['id'] for row in cursor.fetchall()}

        # Listas para guardar novos itens e dados de preços
        novos_supermercados = set()
        novas_categorias = set()
        dados_precos_para_inserir = []

        # 2. Processar cada linha em memória
        for linha in dados_brutos.strip().split('\n'):
            if not linha.strip() or '\t' not in linha: continue
            colunas = linha.split('\t')
            if len(colunas) < 5: continue
            data_validade_raw, nome_supermercado, nome_produto_raw, valor_raw, nome_categoria = [c.strip() for c in colunas]

            if nome_supermercado not in supermercados_map:
                novos_supermercados.add(nome_supermercado)
            if nome_categoria not in categorias_map:
                novas_categorias.add(nome_categoria)

            # (A lógica de limpeza de dados continua a mesma)
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

            # Adiciona os dados de preço a uma lista para inserção em massa mais tarde
            for data_valida in datas_processadas:
                dados_precos_para_inserir.append({
                    "nome_supermercado": nome_supermercado,
                    "nome_categoria": nome_categoria,
                    "nome_produto": nome_produto,
                    "valor": valor_final,
                    "unidade": unidade,
                    "data_validade": data_valida,
                    "observacoes": observacoes
                })

        # 3. Inserir novos supermercados e categorias em massa (se houver)
        if novos_supermercados:
            execute_values(cursor, "INSERT INTO supermercados (nome) VALUES %s ON CONFLICT (nome) DO NOTHING", [(s,) for s in novos_supermercados])
            cursor.execute("SELECT nome, id FROM supermercados")
            supermercados_map = {row['nome']: row['id'] for row in cursor.fetchall()}
        
        if novas_categorias:
            execute_values(cursor, "INSERT INTO categorias (nome) VALUES %s ON CONFLICT (nome) DO NOTHING", [(c,) for c in novas_categorias])
            cursor.execute("SELECT nome, id FROM categorias")
            categorias_map = {row['nome']: row['id'] for row in cursor.fetchall()}

        # 4. Identificar e inserir novos produtos em massa
        novos_produtos = set()
        for preco in dados_precos_para_inserir:
            id_categoria = categorias_map.get(preco['nome_categoria'])
            if id_categoria and (preco['nome_produto'], id_categoria) not in produtos_map:
                novos_produtos.add((preco['nome_produto'], id_categoria))
        
        if novos_produtos:
            execute_values(cursor, "INSERT INTO produtos (nome, id_categoria) VALUES %s", list(novos_produtos))
            cursor.execute("SELECT nome, id_categoria, id FROM produtos")
            produtos_map = {(row['nome'], row['id_categoria']): row['id'] for row in cursor.fetchall()}

        # 5. Apagar e inserir preços em massa (a operação mais importante)
        if dados_precos_para_inserir:
            # Primeiro, apaga todos os registos que serão substituídos
            delete_tuples = []
            for preco in dados_precos_para_inserir:
                id_supermercado = supermercados_map.get(preco['nome_supermercado'])
                id_categoria = categorias_map.get(preco['nome_categoria'])
                id_produto = produtos_map.get((preco['nome_produto'], id_categoria))
                if id_produto and id_supermercado:
                    delete_tuples.append((id_produto, id_supermercado, preco['data_validade']))
            
            if delete_tuples:
                execute_values(cursor, "DELETE FROM precos_historicos WHERE (id_produto, id_supermercado, data_validade) IN %s", delete_tuples)

            # Agora, insere os novos registos
            insert_tuples = []
            for preco in dados_precos_para_inserir:
                id_supermercado = supermercados_map.get(preco['nome_supermercado'])
                id_categoria = categorias_map.get(preco['nome_categoria'])
                id_produto = produtos_map.get((preco['nome_produto'], id_categoria))
                if id_produto and id_supermercado:
                    insert_tuples.append((id_produto, id_supermercado, preco['valor'], preco['unidade'], preco['data_validade'], preco['observacoes']))

            if insert_tuples:
                execute_values(cursor, "INSERT INTO precos_historicos (id_produto, id_supermercado, valor, unidade, data_validade, observacoes) VALUES %s", insert_tuples)

        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"Erro ao importar: {e}")
        return jsonify({"status": "error", "message": f"Erro no servidor: {e}"}), 500
    finally:
        cursor.close()
        conn.close()
        
    return jsonify({"status": "success", "message": f"{len(dados_precos_para_inserir)} registros de ofertas processados com sucesso!"}), 200

# O resto das rotas continua igual
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
