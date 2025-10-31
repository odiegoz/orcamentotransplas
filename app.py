import streamlit as st
import os
from datetime import date, datetime
from gerador_funcoes import criar_pdf
import io
import traceback
import base64
from pathlib import Path

def to_data_uri(path: str):
    p = Path(path)
    if not p.exists():
        return None
    mime = "image/png" if p.suffix.lower()==".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


# --- [MODIFICADO] --- Importações do Google Sheets
from streamlit_gsheets import GSheetsConnection
import gspread
import pandas as pd
import json # <--- [IMPORTANTE] Adicionar import json

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

# --- [MODIFICADO] --- Definição das colunas da planilha
COLUNAS_CLIENTES = [
    'id', 'razao_social', 'endereco', 'bairro', 'cidade', 'uf',
    'cep', 'cnpj', 'inscricao_estadual', 'telefone', 'contato', 'email', 'data_cadastro'
]

# --- [NOVO] --- Definição das colunas de Produtos
COLUNAS_PRODUTOS = [
    'id', 'sku', 'descricao', 'filme', 'cor_codigo', 'acabamento', 
    'medida', 'valor_kg', 'data_cadastro'
]


# --- [MODIFICADO] --- Conexão com o Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Falha ao conectar com o Google Sheets. Verifique seus 'Secrets'.")
    st.exception(e)
    st.stop()


# --- [MODIFICADO] --- FUNÇÕES DE BANCO DE DADOS (Google Sheets) ---

@st.cache_data(ttl=15)
def carregar_aba(aba_nome, colunas_esperadas): # <-- [MODIFICADO] Adicionado 'colunas_esperadas'
    """Lê todos os dados de uma aba e retorna um DataFrame."""
    try:
        creds_json_text = st.secrets["gsheets"]["service_account_info"]
        creds_json = json.loads(creds_json_text)
        sa = gspread.service_account_from_dict(creds_json)

        sh = sa.open_by_url(st.secrets["gsheets"]["spreadsheet"])
        ws = sh.worksheet(aba_nome)

        dados = ws.get_all_values()

        if len(dados) > 0:
            df = pd.DataFrame(dados[1:], columns=dados[0])
        else:
            # [MODIFICADO] Usa o argumento
            df = pd.DataFrame(columns=colunas_esperadas) 

        df.dropna(how="all", inplace=True)
        if 'id' in df.columns:
            df['id'] = df['id'].astype(str)
        
        # [NOVO] Garantir que colunas numéricas sejam tratadas
        if 'valor_kg' in df.columns:
             df['valor_kg'] = pd.to_numeric(df['valor_kg'], errors='coerce').fillna(0.0)

        return df

    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Aba '{aba_nome}' não encontrada na sua planilha! Verifique o nome.")
        return pd.DataFrame(columns=colunas_esperadas) # [MODIFICADO]
    except json.JSONDecodeError as e:
        st.error(f"Erro ao ler o JSON das credenciais nos Secrets: {e}")
        st.error("Verifique se o JSON em 'service_account_info' está formatado corretamente e sem caracteres inválidos.")
        traceback.print_exc()
        return pd.DataFrame(columns=colunas_esperadas) # [MODIFICADO]
    except Exception as e:
        st.error(f"Erro ao carregar dados da aba '{aba_nome}': {e}")
        traceback.print_exc()
        return pd.DataFrame(columns=colunas_esperadas) # [MODIFICADO]

# --- Funções de Clientes (Modificadas para usar a nova 'carregar_aba') ---

def get_all_clients():
    """Retorna lista de dicts de clientes."""
    # [MODIFICADO] Passa as colunas esperadas
    df = carregar_aba("Clientes", COLUNAS_CLIENTES) 
    if df.empty:
        return []
    return df.to_dict('records')

def get_client_by_id(client_id):
    """Retorna um dict do cliente ou None."""
    # [MODIFICADO] Passa as colunas esperadas
    df = carregar_aba("Clientes", COLUNAS_CLIENTES)
    if df.empty or 'id' not in df.columns:
        return None

    cliente_df = df[df['id'] == str(client_id)]

    if not cliente_df.empty:
        return cliente_df.to_dict('records')[0]
    return None

def add_client(data_dict):
    """Adiciona cliente no Google Sheets."""
    try:
        creds_json_text = st.secrets["gsheets"]["service_account_info"]
        creds_json = json.loads(creds_json_text)
        sa = gspread.service_account_from_dict(creds_json)

        sh = sa.open_by_url(st.secrets["gsheets"]["spreadsheet"])
        ws = sh.worksheet("Clientes")

        # Checar duplicidade de CNPJ
        try:
            cnpj_col_index = COLUNAS_CLIENTES.index('cnpj') + 1
        except ValueError:
            st.error("Erro crítico: Coluna 'cnpj' não encontrada. Verifique 'COLUNAS_CLIENTES'.")
            return False

        cnpjs_existentes = ws.col_values(cnpj_col_index)
        if data_dict['cnpj'] and data_dict['cnpj'] in cnpjs_existentes: # [MODIFICADO] Checa se cnpj não é vazio
            st.sidebar.error("Cliente com este CNPJ já existe.")
            return False

        # Pegar próximo ID
        try:
            id_col_index = COLUNAS_CLIENTES.index('id') + 1
        except ValueError:
            st.error("Erro crítico: Coluna 'id' não encontrada. Verifique 'COLUNAS_CLIENTES'.")
            return False

        ids = ws.col_values(id_col_index)[1:]
        ids_num = [int(i) for i in ids if i and i.isdigit()]
        next_id = max(ids_num) + 1 if ids_num else 1

        # Montar a linha na ordem correta
        nova_linha = []
        data_dict['id'] = next_id
        data_dict['data_cadastro'] = datetime.now().strftime("%Y-%m-%d")

        for coluna in COLUNAS_CLIENTES:
            nova_linha.append(data_dict.get(coluna, ""))

        # Adicionar a linha e limpar o cache
        ws.append_row(nova_linha)
        st.cache_data.clear()
        return True

    except gspread.exceptions.WorksheetNotFound:
        st.error("Aba 'Clientes' não foi encontrada na planilha. Não foi possível salvar.")
        return False
    except json.JSONDecodeError as e:
        st.error(f"Erro ao ler o JSON das credenciais nos Secrets: {e}")
        st.error("Verifique se o JSON em 'service_account_info' está formatado corretamente.")
        traceback.print_exc()
        return False
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets:")
        st.exception(e)
        return False

# --- [NOVO] --- FUNÇÕES DE PRODUTOS ---

def get_all_products():
    """Carrega todos os produtos da aba 'Produtos'."""
    df = carregar_aba("Produtos", COLUNAS_PRODUTOS)
    if df.empty:
        return []
    return df.to_dict('records')

def get_product_by_id(product_id):
    """Busca um produto pelo ID."""
    df = carregar_aba("Produtos", COLUNAS_PRODUTOS)
    if df.empty or 'id' not in df.columns:
        return None
    
    produto_df = df[df['id'] == str(product_id)]
    
    if not produto_df.empty:
        return produto_df.to_dict('records')[0]
    return None

def add_product(data_dict):
    """Adiciona um novo produto na aba 'Produtos'."""
    try:
        creds_json_text = st.secrets["gsheets"]["service_account_info"]
        creds_json = json.loads(creds_json_text)
        sa = gspread.service_account_from_dict(creds_json)

        sh = sa.open_by_url(st.secrets["gsheets"]["spreadsheet"])
        ws = sh.worksheet("Produtos") # <-- Aponta para a aba "Produtos"

        # 2. Checar duplicidade de SKU
        try:
            sku_col_index = COLUNAS_PRODUTOS.index('sku') + 1
        except ValueError:
            st.error("Erro crítico: Coluna 'sku' não encontrada. Verifique 'COLUNAS_PRODUTOS'.")
            return False

        skus_existentes = ws.col_values(sku_col_index)
        if data_dict['sku'] and data_dict['sku'] in skus_existentes: # <-- Checa SKU
            st.sidebar.error("Produto com este SKU já existe.")
            return False

        # 3. Pegar próximo ID
        try:
            id_col_index = COLUNAS_PRODUTOS.index('id') + 1
        except ValueError:
            st.error("Erro crítico: Coluna 'id' não encontrada. Verifique 'COLUNAS_PRODUTOS'.")
            return False

        ids = ws.col_values(id_col_index)[1:]
        ids_num = [int(i) for i in ids if i and i.isdigit()]
        next_id = max(ids_num) + 1 if ids_num else 1

        # 4. Montar a linha na ordem correta
        nova_linha = []
        data_dict['id'] = next_id
        data_dict['data_cadastro'] = datetime.now().strftime("%Y-%m-%d")

        for coluna in COLUNAS_PRODUTOS: # <-- Usa COLUNAS_PRODUTOS
            nova_linha.append(data_dict.get(coluna, ""))

        # 5. Adicionar a linha e limpar o cache
        ws.append_row(nova_linha)
        st.cache_data.clear()
        return True

    except gspread.exceptions.WorksheetNotFound:
        st.error("Aba 'Produtos' não foi encontrada na planilha. Não foi possível salvar.")
        return False
    except Exception as e:
        st.error(f"Erro ao salvar Produto no Google Sheets:")
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
st.sidebar.title("Gerenciamento")
st.sidebar.header("Clientes")

try:
    clientes = get_all_clients() 

    cliente_map = {}
    if clientes:
        clientes_validos = [c for c in clientes if c.get('razao_social') and c.get('id')]
        cliente_map = {f"{c['razao_social']} (ID: {c['id']})": c['id'] for c in clientes_validos}

    opcoes_cliente = ["- Selecione um Cliente -"] + list(cliente_map.keys())

    cliente_selecionado_str = st.sidebar.selectbox("Carregar Cliente Existente", options=opcoes_cliente)

    if cliente_selecionado_str != "- Selecione um Cliente -":
        cliente_id = cliente_map[cliente_selecionado_str]
        if 'cliente_id' not in st.session_state or st.session_state.cliente_id != cliente_id:
            st.session_state.cliente_id = cliente_id
            st.session_state.dados_cliente = get_client_by_id(cliente_id) 
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
                    if add_client(new_cliente_data): 
                        st.sidebar.success("Cliente salvo!")
                        st.rerun()
except Exception as e:
    st.sidebar.error(f"Erro ao carregar clientes: {e}")
    traceback.print_exc() 

# --- [NOVO] --- BARRA LATERAL PARA GERENCIAR PRODUTOS ---
st.sidebar.header("📦 Produtos")

try:
    with st.sidebar.expander("➕ Adicionar Novo Produto", expanded=False):
        with st.form("new_product_form", clear_on_submit=True):
            new_product_data = {
                'sku': st.text_input("SKU (Código)*"),
                'descricao': st.text_input("Descrição*"),
                'filme': st.text_input("Filme", "Não"),
                'cor_codigo': st.text_input("Cor-Código", "Branco Tricamada"),
                'acabamento': st.text_input("Acabamento", "BM"),
                'medida': st.text_input("Medida", "2000x1000x0,50mm"),
                'valor_kg': st.number_input("Valor Padrão (KG)", min_value=0.0, value=1.0, format="%.2f")
            }
            submitted_prod = st.form_submit_button("Salvar Novo Produto")
            if submitted_prod:
                if not new_product_data['sku'] or not new_product_data['descricao']:
                    st.sidebar.error("SKU e Descrição são obrigatórios.")
                else:
                    if add_product(new_product_data):
                        st.sidebar.success("Produto salvo!")
                        st.rerun() # Força recarregar o selectbox de produtos
                    # Msg de erro (SKU duplicado) já aparece na função
except Exception as e:
    st.sidebar.error(f"Erro nas operações de produto: {e}")
    traceback.print_exc()


# --- FORMULÁRIO PRINCIPAL DO ORÇAMENTO (sem alteração) ---
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

# --- [MODIFICADO] --- COLUNA DE ITENS ---
with col_itens:
    st.subheader("Itens do Orçamento")

    # --- [NOVO] Carregador de Produtos ---
    try:
        produtos_db = get_all_products()
        produto_map = {}
        if produtos_db:
            produtos_validos = [p for p in produtos_db if p.get('descricao') and p.get('id')]
            # Mapeia a string de exibição para o dicionário completo do produto
            produto_map = {f"{p['descricao']} (SKU: {p.get('sku', 'N/A')})": p for p in produtos_validos}
        
        opcoes_produto = ["- Digitar Manualmente -"] + list(produto_map.keys())
        
        # Este selectbox fica FORA do form. Ao mudar, ele recarrega o app
        # e os valores padrão do form abaixo são atualizados.
        produto_selecionado_str = st.selectbox(
            "Carregar Produto do Banco de Dados", 
            options=opcoes_produto, 
            key="produto_select" # Uma chave para o widget
        )
        
        # Pega os dados do produto selecionado ou um dict vazio se for manual
        produto_default = {}
        if produto_selecionado_str != "- Digitar Manualmente -":
            produto_default = produto_map[produto_selecionado_str]
    
    except Exception as e:
        st.error(f"Erro ao carregar produtos do BD: {e}")
        produto_default = {} # Garante que 'produto_default' exista
    # --- Fim do Carregador de Produtos ---


    with st.form(key="add_item_form", clear_on_submit=True):
        st.write("Adicionar novo item:")
        item_cols = st.columns([3, 1, 2, 1, 2])

        # [MODIFICADO] Os campos agora usam 'value' para preencher 
        # com os dados do 'produto_default' carregado acima.
        
        with item_cols[0]:
            descricao = st.text_input("Descrição", value=produto_default.get('descricao', 'Chapa PSAI Tricamada'))
        with item_cols[1]:
            filme = st.text_input("Filme", value=produto_default.get('filme', 'Não'))
        with item_cols[2]:
            cor_codigo = st.text_input("Cor-Código", value=produto_default.get('cor_codigo', 'Branco Tricamada'))
        with item_cols[3]:
            acabamento = st.text_input("Acabamento", value=produto_default.get('acabamento', 'BM'))
        with item_cols[4]:
            medida = st.text_input("Medida", value=produto_default.get('medida', '2000x1000x0,50mm'))

        item_cols_2 = st.columns([1, 1])
        with item_cols_2[0]:
            quantidade_kg = st.number_input("Qtd (KG)", min_value=0.01, value=1.0, format="%.2f")
        with item_cols_2[1]:
            # [MODIFICADO] Converte o 'valor_kg' para float, com fallback
            valor_kg_default = float(produto_default.get('valor_kg', 1.0) or 1.0)
            valor_kg = st.number_input("Valor (KG)", min_value=0.01, value=valor_kg_default, format="%.2f")

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

            # >>> NOVO: gera a data URI da marca d'água (usa seu arquivo PNG)
            watermark_datauri = to_data_uri("/workspaces/orcamentotransplas/watermark.png")

            # >>> IMPORTANTE: coloque watermark_datauri DENTRO do dict 'dados'
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
                'observacoes': observacoes,

                # >>> ESTA LINHA É A NOVIDADE <<<
                'watermark_datauri': watermark_datauri
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