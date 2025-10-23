import streamlit as st
import os
from datetime import date, datetime # --- [MODIFICADO] --- Importa 'datetime'
from gerador_funcoes import criar_pdf # Importa a função corrigida
import io
import traceback # Importado para logs

# --- [MODIFICADO] --- Importações do Google Sheets
from streamlit_gsheets import GSheetsConnection
import gspread
import pandas as pd

# --- DADOS DAS EMPRESAS (sem alteração) ---
EMPRESAS = {
    "ISOFORMA": {
        'nome': "ISOFORMA PLASTICOS INDUSTRIAIS LTDA",
        'endereco': "RODOVIA DOM GABRIEL PAULINO BUENO COUTO, SN",
        'bairro_cidade_uf': "Bairro Pinhal - Cabreúva - SP",
        'cep': "13317-204",
        'contato': "(11) 4409-0919"
    },
    "PLASTY": {
        'nome': "PLASTY COMERCIAL DE PLÁSTICOS LTDA",
        'endereco': "RUA CARLOS SILVEIRA FRANCO NETO, 77",
        'bairro_cidade_uf': "Bairro do Jacaré - Cabreúva - SP",
        'cep': "13318-000",
        'contato': "(11) 4409-0919"
    }
}

# --- [NOVO] --- Definição das colunas da planilha
# Garante que a ordem e os nomes estejam corretos.
COLUNAS_CLIENTES = [
    'id', 'razao_social', 'cnpj', 'endereco', 'bairro', 'cidade', 'uf', 
    'cep', 'inscricao_estadual', 'telefone', 'contato', 'email', 'data_cadastro'
]

# --- [MODIFICADO] --- Conexão com o Google Sheets
# Substitui o init_db()
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Falha ao conectar com o Google Sheets. Verifique seus 'Secrets'.")
    st.exception(e)
    st.stop()


# --- [NOVO] --- FUNÇÕES DE BANCO DE DADOS (Google Sheets) ---

# O @st.cache_data guarda o resultado em cache para não ler a planilha
# a cada interação do usuário, economizando tempo e cotas da API.
@st.cache_data(ttl=15) # Cache de 15 segundos
def carregar_aba(aba_nome):
    """Lê todos os dados de uma aba e retorna um DataFrame."""
    try:
        df = conn.read(worksheet=aba_nome)
        df.dropna(how="all", inplace=True) # Remove linhas totalmente vazias
        # Converte a coluna 'id' para string para consistência
        if 'id' in df.columns:
            df['id'] = df['id'].astype(str)
        return df
    except Exception as e:
        # Se a aba não existir, gsheets-connection levanta um erro
        if "WorksheetNotFound" in str(e):
            st.error(f"Aba '{aba_nome}' não encontrada na sua planilha!")
            return pd.DataFrame(columns=COLUNAS_CLIENTES) # Retorna DF vazio com colunas
        st.error(f"Erro ao carregar dados da aba '{aba_nome}': {e}")
        return pd.DataFrame(columns=COLUNAS_CLIENTES) # Retorna DF vazio

def get_all_clients():
    """Substitui a função antiga. Retorna lista de dicts."""
    df = carregar_aba("Clientes")
    if df.empty:
        return []
    # Converte o DataFrame para o formato que seu código esperava (lista de dicts)
    return df.to_dict('records')

def get_client_by_id(client_id):
    """Substitui a função antiga. Retorna um dict ou None."""
    df = carregar_aba("Clientes")
    if df.empty or 'id' not in df.columns:
        return None
    
    # Filtra o DataFrame pelo ID (que agora é string)
    cliente_df = df[df['id'] == str(client_id)]
    
    if not cliente_df.empty:
        # Retorna o primeiro (e único) cliente como um dicionário
        return cliente_df.to_dict('records')[0]
    return None

def add_client(data_dict):
    """Substitui a função antiga. Adiciona cliente no Google Sheets."""
    try:
        # 1. Autenticar com gspread (melhor para escrever)
        sa = gspread.service_account_from_dict(st.secrets["gsheets"]["service_account_info"])
        sh = sa.open_by_url(st.secrets["spreadsheet_url"])
        ws = sh.worksheet("Clientes") # Nome EXATO da aba

        # 2. Checar duplicidade de CNPJ (lógica preservada)
        try:
            # Pega o índice da coluna 'cnpj' (ex: 3)
            cnpj_col_index = COLUNAS_CLIENTES.index('cnpj') + 1
        except ValueError:
            st.error("Erro crítico: Coluna 'cnpj' não encontrada. Verifique 'COLUNAS_CLIENTES'.")
            return False
        
        cnpjs_existentes = ws.col_values(cnpj_col_index)
        if data_dict['cnpj'] in cnpjs_existentes:
            st.sidebar.error("Cliente com este CNPJ já existe.")
            return False

        # 3. Pegar próximo ID
        try:
            id_col_index = COLUNAS_CLIENTES.index('id') + 1
        except ValueError:
            st.error("Erro crítico: Coluna 'id' não encontrada. Verifique 'COLUNAS_CLIENTES'.")
            return False
            
        ids = ws.col_values(id_col_index)[1:] # [1:] pula o header
        ids_num = [int(i) for i in ids if i and i.isdigit()] # Filtra vazios e não-numéricos
        next_id = max(ids_num) + 1 if ids_num else 1
        
        # 4. Montar a linha na ordem correta
        nova_linha = []
        data_dict['id'] = next_id
        data_dict['data_cadastro'] = datetime.now().strftime("%Y-%m-%d")
        
        for coluna in COLUNAS_CLIENTES:
            # .get() é seguro, retorna "" se a chave não existir no dict
            nova_linha.append(data_dict.get(coluna, "")) 
        
        # 5. Adicionar a linha e limpar o cache
        ws.append_row(nova_linha)
        st.cache_data.clear() # Limpa o cache para recarregar os dados
        return True
    
    except gspread.exceptions.WorksheetNotFound:
        st.error("Aba 'Clientes' não foi encontrada na planilha. Não foi possível salvar.")
        return False
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets:")
        st.exception(e)
        return False

# --- FIM DAS NOVAS FUNÇÕES DE BANCO DE DADOS ---


st.set_page_config(layout="wide", page_title="Gerador de Orçamentos")
st.title("📄 Gerador de Propostas e Orçamentos")

# --- SELEÇÃO DA EMPRESA (sem alteração) ---
empresa_selecionada_nome = st.selectbox(
    "**Selecione a Empresa para o Orçamento**",
    options=list(EMPRESAS.keys())
)
st.markdown("---")


# --- BARRA LATERAL PARA GERENCIAR CLIENTES ---
# --- [MODIFICADO] ---
# O código aqui dentro é IDÊNTICO, mas agora ele chama
# as NOVAS funções (get_all_clients, get_client_by_id, add_client)
# que conversam com o Google Sheets.
st.sidebar.title("Clientes")

try:
    clientes = get_all_clients() # Chama a nova função
    
    # Criar o mapa de clientes
    cliente_map = {}
    if clientes:
        # Filtra clientes que podem não ter 'razao_social' ou 'id' (embora não devesse)
        clientes_validos = [c for c in clientes if c.get('razao_social') and c.get('id')]
        cliente_map = {f"{c['razao_social']} (ID: {c['id']})": c['id'] for c in clientes_validos}
    
    opcoes_cliente = ["- Selecione um Cliente -"] + list(cliente_map.keys())

    cliente_selecionado_str = st.sidebar.selectbox("Carregar Cliente Existente", options=opcoes_cliente)

    if cliente_selecionado_str != "- Selecione um Cliente -":
        cliente_id = cliente_map[cliente_selecionado_str]
        if 'cliente_id' not in st.session_state or st.session_state.cliente_id != cliente_id:
            st.session_state.cliente_id = cliente_id
            st.session_state.dados_cliente = get_client_by_id(cliente_id) # Chama a nova função
            st.rerun()

    with st.sidebar.expander("➕ Adicionar Novo Cliente", expanded=False):
        with st.form("new_client_form", clear_on_submit=True):
            new_cliente_data = {
                'razao_social': st.text_input("Razão Social*"),
                'cnpj': st.text_input("CNPJ*"),
                'endereco': st.text_input("Endereço"), 'bairro': st.text_input("Bairro"),
                'cidade': st.text_input("Cidade"), 'uf': st.text_input("UF"), 'cep': st.text_input("CEP"),
                'inscricao_estadual': st.text_input("Inscrição Estadual"),
                'telefone': st.text_input("Telefone"), 'contato': st.text_input("Contato"),
                'email': st.text_input("E-mail")
            }
            submitted = st.form_submit_button("Salvar Novo Cliente")
            if submitted:
                if not new_cliente_data['razao_social'] or not new_cliente_data['cnpj']:
                    st.sidebar.error("Razão Social e CNPJ são obrigatórios.")
                else:
                    if add_client(new_cliente_data): # Chama a nova função
                        st.sidebar.success("Cliente salvo!")
                        st.rerun()
                    # A msg de erro de CNPJ já é mostrada dentro da função add_client
except Exception as e:
    st.sidebar.error(f"Erro ao carregar clientes: {e}")
    traceback.print_exc() # Loga o erro completo no terminal/logs

# --- FORMULÁRIO PRINCIPAL DO ORÇAMENTO (sem alteração) ---
# Esta seção inteira funciona perfeitamente, pois ela lê os dados
# do 'st.session_state.dados_cliente', que foi preenchido
# pela nova lógica do Google Sheets.
dados_cliente_atual = st.session_state.get('dados_cliente', None)
col_dados_gerais, col_itens = st.columns(2)

with col_dados_gerais:
    st.subheader("Dados Gerais do Orçamento")
    
    col_num, col_vend = st.columns(2)
    with col_num:
        orcamento_numero = st.number_input("Orçamento N°", min_value=1, value=10)
    with col_vend:
        vendedor = st.text_input("Vendedor", value="Taty")

    st.subheader("Dados do Cliente")
    cliente = {
        'razao_social': st.text_input("Razão Social", value=dados_cliente_atual['razao_social'] if dados_cliente_atual else ''),
        'endereco': st.text_input("Endereço", value=dados_cliente_atual['endereco'] if dados_cliente_atual else ''),
        'bairro': st.text_input("Bairro", value=dados_cliente_atual['bairro'] if dados_cliente_atual else ''),
        'cidade': st.text_input("Cidade", value=dados_cliente_atual['cidade'] if dados_cliente_atual else ''),
        'uf': st.text_input("UF", value=dados_cliente_atual['uf'] if dados_cliente_atual else ''),
        'cep': st.text_input("CEP", value=dados_cliente_atual['cep'] if dados_cliente_atual else ''),
        'cnpj': st.text_input("CNPJ", value=dados_cliente_atual['cnpj'] if dados_cliente_atual else ''),
        'inscricao_estadual': st.text_input("Inscrição Estadual", value=dados_cliente_atual['inscricao_estadual'] if dados_cliente_atual else ''),
        'telefone': st.text_input("Telefone", value=dados_cliente_atual['telefone'] if dados_cliente_atual else ''),
        'contato': st.text_input("Contato", value=dados_cliente_atual['contato'] if dados_cliente_atual else ''),
        'email': st.text_input("E-mail", value=dados_cliente_atual['email'] if dados_cliente_atual else '')
    }
    
    st.subheader("Condições e Entrega")
    pagamento_condicao = st.text_input("Cond. Pagamento", value="28/35/42 ddl")
    pagamento_qtde_parcelas = st.number_input("Quantidade de Parcelas", min_value=1, value=3, step=1)
    pagamento_data_entrega = st.date_input("Data de Entrega", value=date.today())

    st.subheader("Impostos")
    impostos_icms = st.number_input("ICMS (%)", min_value=0.0, value=18.0, format="%.2f")
    impostos_ipi = st.number_input("IPI (%)", min_value=0.0, value=0.0, format="%.2f")
    
    st.subheader("Transporte e Observações")
    transportadora = {
        'nome': st.text_input("Transportadora"), 'cnpj': st.text_input("CNPJ da Transportadora"),
        'telefone': st.text_input("Telefone da Transportadora")
    }
    observacoes = st.text_area("Observações")

# --- LÓGICA DOS ITENS (sem alteração) ---
if 'itens' not in st.session_state:
    st.session_state.itens = []

with col_itens:
    st.subheader("Itens do Orçamento")
    
    with st.form(key="add_item_form", clear_on_submit=True):
        st.write("Adicionar novo item:")
        item_cols = st.columns([3, 1, 2, 1, 2])
        
        with item_cols[0]:
            descricao = st.text_input("Descrição", "Chapa PSAI Tricamada")
        with item_cols[1]:
            filme = st.text_input("Filme", "Não")
        with item_cols[2]:
            cor_codigo = st.text_input("Cor-Código", "Branco Tricamada")
        with item_cols[3]:
            acabamento = st.text_input("Acabamento", "BM")
        with item_cols[4]:
            medida = st.text_input("Medida", "2000x1000x0,50mm")
        
        item_cols_2 = st.columns([1, 1])
        with item_cols_2[0]:
            quantidade_kg = st.number_input("Qtd (KG)", min_value=0.01, value=1.0, format="%.2f")
        with item_cols_2[1]:
            valor_kg = st.number_input("Valor (KG)", min_value=0.01, value=1.0, format="%.2f")
        
        add_item_button = st.form_submit_button("Adicionar Item")

        if add_item_button:
            if not descricao or quantidade_kg <= 0 or valor_kg <= 0:
                st.warning("Preencha a descrição, Qtd (KG) > 0 e Valor (KG) > 0.")
            else:
                st.session_state.itens.append({
                    'descricao': descricao, 'filme': filme, 'cor_codigo': cor_codigo,
                    'acabamento': acabamento, 'medida': medida, 
                    'quantidade_kg': float(quantidade_kg), 'valor_kg': float(valor_kg),
                    'ipi_item': float(impostos_ipi)
                })
                st.rerun() # Atualiza a lista de itens imediatamente

    if st.session_state.itens:
        st.write("Itens adicionados:")
        total_preview = sum(item['quantidade_kg'] * item['valor_kg'] for item in st.session_state.itens)
        for i, item in enumerate(st.session_state.itens):
            subtotal = item['quantidade_kg'] * item['valor_kg']
            st.text(f"{i+1}. {item['descricao']} ({item['medida']}) - {item['quantidade_kg']:.2f} KG x R${item['valor_kg']:.2f} = R${subtotal:,.2f}")
        
        st.markdown(f"**Total das Mercadorias: R$ {total_preview:,.2f}**")
        
        if st.button("Limpar Itens"):
            st.session_state.itens = []
            st.rerun()

st.markdown("---")

# --- GERAÇÃO DO PDF (sem alteração) ---
if st.button("Gerar PDF do Orçamento", type="primary"):
    if not cliente['razao_social'] or not st.session_state.itens:
        st.error("Preencha, no mínimo, a Razão Social do cliente e adicione pelo menos um item.")
    else:
        with st.spinner("Gerando o arquivo PDF..."):
            
            valor_mercadoria = sum(float(item['quantidade_kg']) * float(item['valor_kg']) for item in st.session_state.itens)
            ipi_percent = float(impostos_ipi)
            icms_percent = float(impostos_icms)
            qtde_parcelas_int = int(pagamento_qtde_parcelas)

            valor_ipi = valor_mercadoria * (ipi_percent / 100.0)
            total_nf = valor_mercadoria + valor_ipi
            valor_parcela = total_nf / qtde_parcelas_int if qtde_parcelas_int > 0 else 0
            
            dados_empresa = EMPRESAS[empresa_selecionada_nome].copy()

            dados = {
                'empresa': dados_empresa, 
                'orcamento_numero': orcamento_numero,
                'data_emissao': date.today().strftime('%d/%m/%Y'),
                'vendedor': vendedor,
                'cliente': cliente,
                'itens': st.session_state.itens,
                'pagamento': {
                    'condicao': pagamento_condicao,
                    'qtde_parcelas': qtde_parcelas_int,
                    'data_entrega': pagamento_data_entrega.strftime('%d/%m/%Y'),
                    'valor_parcela': valor_parcela
                },
                'totais': {
                    'base_calculo_icms': valor_mercadoria, 'icms_perc': icms_percent,
                    'valor_mercadoria': valor_mercadoria, 'ipi_perc': ipi_percent,
                    'valor_ipi': valor_ipi, 'total_nf': total_nf,
                    'total_kg': sum(float(item['quantidade_kg']) for item in st.session_state.itens)
                },
                'transportadora': transportadora,
                'observacoes': observacoes
            }
            
            nome_arquivo_pdf = f"Orcamento_{orcamento_numero}_{cliente['razao_social'].replace(' ', '_')}.pdf"
            
            pdf_bytes = criar_pdf(dados, template_path="template.html", debug_dump_html=True)

            if pdf_bytes:
                st.success(f"PDF '{nome_arquivo_pdf}' gerado com sucesso!")
                
                st.download_button(
                    label="Clique aqui para baixar o PDF",
                    data=pdf_bytes,
                    file_name=nome_arquivo_pdf,
                    mime="application/pdf"
                )
            else:
                st.error("Ocorreu um erro ao gerar o PDF. Verifique os logs.")