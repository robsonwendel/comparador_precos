// Aguarda o HTML ser completamente carregado para executar o script
document.addEventListener('DOMContentLoaded', () => {
    // URL base da API do backend
    const apiBaseUrl = 'https://comparador-api.onrender.com/api';

    // Seleciona os elementos do HTML que serão manipulados
    const buscaInput = document.getElementById('buscaProduto');
    const dataInput = document.getElementById('filtroData');
    const supermercadoSelect = document.getElementById('filtroSupermercado');
    const categoriaSelect = document.getElementById('filtroCategoria');
    const tabelaBody = document.getElementById('ofertasTabelaBody');

    // Elementos do Modal (popup) do gráfico
    const modal = document.getElementById('graficoModal');
    const closeBtn = document.querySelector('.close-btn');
    const graficoTitulo = document.getElementById('graficoTitulo');
    const ctx = document.getElementById('graficoPrecos').getContext('2d');
    let precoChart = null; // Variável para armazenar a instância do gráfico e destruí-la depois

    /**
     * Define a data de hoje como valor padrão para o filtro de data.
     */
    function setDefaultDate() {
        const hoje = new Date();
        const ano = hoje.getFullYear();
        const mes = String(hoje.getMonth() + 1).padStart(2, '0');
        const dia = String(hoje.getDate()).padStart(2, '0');
        dataInput.value = `${ano}-${mes}-${dia}`;
    }

    /**
     * Busca os supermercados e categorias no backend e preenche os menus <select>.
     */
    async function carregarFiltros() {
        try {
            const response = await fetch(`${apiBaseUrl}/filtros`);
            const data = await response.json();

            data.supermercados.forEach(item => {
                const option = new Option(item.nome, item.id);
                supermercadoSelect.add(option);
            });

            data.categorias.forEach(item => {
                const option = new Option(item.nome, item.id);
                categoriaSelect.add(option);
            });
        } catch (error) {
            console.error('Erro ao carregar filtros:', error);
        }
    }

    /**
     * Busca as ofertas no backend com base nos filtros selecionados e exibe na tabela.
     */
    async function carregarOfertas() {
        const busca = buscaInput.value;
        const supermercadoId = supermercadoSelect.value;
        const categoriaId = categoriaSelect.value;
        const dataSelecionada = dataInput.value;

        const url = new URL(`${apiBaseUrl}/ofertas`);
        if (dataSelecionada) url.searchParams.append('data', dataSelecionada);
        if (busca) url.searchParams.append('busca', busca);
        if (supermercadoId) url.searchParams.append('supermercado', supermercadoId);
        if (categoriaId) url.searchParams.append('categoria', categoriaId);
        
        try {
            const response = await fetch(url);
            const ofertas = await response.json();

            tabelaBody.innerHTML = '';

            if (ofertas.length === 0) {
                tabelaBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Nenhuma oferta encontrada para os filtros selecionados.</td></tr>';
                return;
            }

            ofertas.forEach(oferta => {
                const row = tabelaBody.insertRow();
                const valorFormatado = `R$ ${oferta.valor.toFixed(2).replace('.', ',')} ${oferta.unidade || ''}`;
                
                row.innerHTML = `
                    <td>${oferta.produto_nome} ${oferta.observacoes ? `(${oferta.observacoes})` : ''}</td>
                    <td>${valorFormatado}</td>
                    <td>${oferta.supermercado_nome}</td>
                    <td>${oferta.categoria_nome}</td>
                    <td><button class="btn-historico" data-produto-id="${oferta.id_produto}" data-produto-nome="${oferta.produto_nome}">Ver Histórico</button></td>
                `;
            });
        } catch (error) {
            console.error('Erro ao carregar ofertas:', error);
            tabelaBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Erro ao carregar dados do servidor.</td></tr>';
        }
    }

    /**
     * Busca o histórico de um produto e exibe o gráfico no modal.
     * @param {string} produtoId - O ID do produto a ser consultado.
     * @param {string} produtoNome - O nome do produto para o título do gráfico.
     */
    async function mostrarGrafico(produtoId, produtoNome) {
        try {
            const response = await fetch(`${apiBaseUrl}/produto/${produtoId}/historico`);
            const historico = await response.json();
            
            // Prepara os dados para o gráfico
            const labels = historico.map(item => new Date(item.data_registro).toLocaleDateString('pt-BR', {timeZone: 'UTC'}));
            const data = historico.map(item => item.valor);

            graficoTitulo.textContent = `Histórico de Preços - ${produtoNome}`;

            if (precoChart) {
                precoChart.destroy();
            }

            precoChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Preço (R$)',
                        data: data,
                        borderColor: '#007bff',
                        backgroundColor: 'rgba(0, 123, 255, 0.1)',
                        fill: true,
                        tension: 0.1
                    }]
                },
                options: {
                    // Configuração do tooltip para mostrar detalhes.
                    plugins: {
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    // 'context.dataIndex' é a posição do ponto de dados
                                    const fullDataPoint = historico[context.dataIndex];
                                    const supermercado = fullDataPoint.supermercado_nome;
                                    
                                    const precoLabel = `Preço: ${new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(context.parsed.y)}`;
                                    const supermercadoLabel = `Supermercado: ${supermercado}`;

                                    // Retorna um array de strings para criar um tooltip com várias linhas
                                    return [precoLabel, supermercadoLabel];
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: false,
                            ticks: { callback: value => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value) }
                        }
                    }
                }
            });

            modal.style.display = 'block';
        } catch (error) {
            console.error('Erro ao buscar histórico:', error);
        }
    }

    // --- CONFIGURAÇÃO DOS EVENTOS ---
    buscaInput.addEventListener('input', carregarOfertas);
    dataInput.addEventListener('change', carregarOfertas);
    supermercadoSelect.addEventListener('change', carregarOfertas);
    categoriaSelect.addEventListener('change', carregarOfertas);
    
    tabelaBody.addEventListener('click', (event) => {
        if (event.target && event.target.classList.contains('btn-historico')) {
            const produtoId = event.target.dataset.produtoId;
            const produtoNome = event.target.dataset.produtoNome;
            mostrarGrafico(produtoId, produtoNome);
        }
    });

    closeBtn.onclick = () => modal.style.display = 'none';
    window.onclick = (event) => {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    }

    // --- CARGA INICIAL ---
    setDefaultDate();
    carregarFiltros();
    carregarOfertas();
});
