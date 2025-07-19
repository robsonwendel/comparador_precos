document.addEventListener('DOMContentLoaded', () => {
    const apiBaseUrl = 'http://127.0.0.1:5000/api';

    const searchInput = document.getElementById('produtoSearch');
    const autocompleteResults = document.getElementById('autocompleteResults');
    const resultadosContainer = document.getElementById('resultadosContainer');
    const limparListaBtn = document.getElementById('limparListaBtn');

    let produtosEmOferta = [];
    // Tenta carregar a lista de compras do localStorage ao iniciar
    let listaDeCompras = JSON.parse(localStorage.getItem('minhaListaDeCompras')) || [];

    // Carrega a lista inicial de produtos que têm ofertas válidas para hoje
    async function carregarProdutosEmOferta() {
        try {
            const response = await fetch(`${apiBaseUrl}/produtos-em-oferta`);
            produtosEmOferta = await response.json();
        } catch (error) {
            console.error('Erro ao carregar produtos em oferta:', error);
        }
    }

    // Filtra e mostra os resultados do autocomplete
    function mostrarAutocomplete(input) {
        autocompleteResults.innerHTML = '';
        if (!input) {
            autocompleteResults.style.display = 'none';
            return;
        }

        const filtrados = produtosEmOferta.filter(p => 
            p.nome.toLowerCase().includes(input.toLowerCase())
        );

        if (filtrados.length > 0) {
            filtrados.forEach(produto => {
                const div = document.createElement('div');
                div.textContent = produto.nome;
                div.addEventListener('click', () => adicionarProdutoNaLista(produto.id, produto.nome));
                autocompleteResults.appendChild(div);
            });
        } else {
            const div = document.createElement('div');
            div.textContent = 'Nenhum produto em oferta encontrado com esse nome.';
            div.classList.add('autocomplete-no-result');
            autocompleteResults.appendChild(div);
        }
        autocompleteResults.style.display = 'block';
    }

    // Adiciona um produto e todas as suas ofertas à lista de compras
    async function adicionarProdutoNaLista(produtoId, produtoNome) {
        searchInput.value = '';
        autocompleteResults.style.display = 'none';

        if (listaDeCompras.find(item => item.id === produtoId)) {
            return; // Se já existe, não faz nada
        }

        try {
            const response = await fetch(`${apiBaseUrl}/produto/todas-ofertas-hoje?id=${produtoId}`);
            const ofertas = await response.json();
            
            if (ofertas.length > 0) {
                listaDeCompras.push({
                    id: produtoId,
                    nome: produtoNome,
                    ofertas: ofertas
                });
                salvarErenderizar();
            }
        } catch (error) {
            console.error('Erro ao buscar ofertas do produto:', error);
        }
    }
    
    // Limpa toda a lista de compras
    function limparLista() {
        listaDeCompras = [];
        salvarErenderizar();
    }

    // Salva a lista no localStorage e renderiza na tela
    function salvarErenderizar() {
        localStorage.setItem('minhaListaDeCompras', JSON.stringify(listaDeCompras));
        renderizarResultados();
    }

    // Desenha as fichas dos supermercados com os produtos e totais
    function renderizarResultados() {
        resultadosContainer.innerHTML = '';

        if (listaDeCompras.length === 0) {
            resultadosContainer.innerHTML = '<p class="info-lista-vazia">Sua lista de compras está vazia. Adicione produtos para começar a comparar.</p>';
            limparListaBtn.style.display = 'none';
            return;
        }
        limparListaBtn.style.display = 'block';

        // 1. Achar todos os supermercados únicos que têm pelo menos um item da lista
        const todosSupermercados = new Set();
        listaDeCompras.forEach(produto => {
            produto.ofertas.forEach(oferta => {
                todosSupermercados.add(oferta.supermercado_nome);
            });
        });

        // 2. Para cada supermercado, criar uma ficha
        const fichasSupermercados = [];
        todosSupermercados.forEach(supermercado => {
            let totalSupermercado = 0;
            let itensEncontrados = 0;
            let listaProdutosHtml = '<ul>';

            // 3. Itera pela lista de compras do utilizador
            listaDeCompras.forEach(produtoDaLista => {
                const ofertaEncontrada = produtoDaLista.ofertas.find(o => o.supermercado_nome === supermercado);

                if (ofertaEncontrada) {
                    totalSupermercado += ofertaEncontrada.valor;
                    itensEncontrados++;
                    listaProdutosHtml += `<li>${produtoDaLista.nome} <span>R$ ${ofertaEncontrada.valor.toFixed(2).replace('.', ',')}</span></li>`;
                } else {
                    listaProdutosHtml += `<li class="item-faltando">${produtoDaLista.nome} <span>Indisponível</span></li>`;
                }
            });

            listaProdutosHtml += '</ul>';
            
            fichasSupermercados.push({
                nome: supermercado,
                total: totalSupermercado,
                completa: itensEncontrados === listaDeCompras.length,
                htmlProdutos: listaProdutosHtml,
                contagemItens: `(${itensEncontrados} de ${listaDeCompras.length} itens)`
            });
        });

        // Ordena: listas completas primeiro, depois por preço mais baixo
        fichasSupermercados.sort((a, b) => {
            if (a.completa && !b.completa) return -1;
            if (!a.completa && b.completa) return 1;
            return a.total - b.total;
        });

        // 4. Renderiza as fichas ordenadas
        fichasSupermercados.forEach(fichaData => {
            const ficha = document.createElement('div');
            ficha.className = 'supermercado-ficha';
            if (fichaData.completa) {
                ficha.classList.add('completo');
            }

            const totalHtml = `
                <div class="ficha-total ${fichaData.completa ? 'completo' : 'parcial'}">
                    <span>Total: R$ ${fichaData.total.toFixed(2).replace('.', ',')}</span>
                    <small>${fichaData.contagemItens}</small>
                </div>`;
            
            ficha.innerHTML = `
                <div class="ficha-header">
                    <h2>${fichaData.nome}</h2>
                    ${totalHtml}
                </div>
                <div class="ficha-body">
                    ${fichaData.htmlProdutos}
                </div>
            `;
            resultadosContainer.appendChild(ficha);
        });
    }

    // Event Listeners
    searchInput.addEventListener('input', () => mostrarAutocomplete(searchInput.value));
    limparListaBtn.addEventListener('click', limparLista);
    
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-container')) {
            autocompleteResults.style.display = 'none';
        }
    });

    // Carga inicial
    carregarProdutosEmOferta();
    renderizarResultados();
});
