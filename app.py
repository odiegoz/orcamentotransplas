# app.py
import os
import io
import json
import base64
import traceback
from pathlib import Path
from datetime import date, datetime

import streamlit as st
from streamlit_gsheets import GSheetsConnection
import gspread
import pandas as pd

from gerador_funcoes import criar_pdf

# ---- Safe rerun helper (keep for safety but avoid forcing reruns) ----
def safe_rerun():
    try:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
        else:
            st.session_state['_needs_rerun'] = True
            st.stop()
    except Exception:
        st.session_state['_needs_rerun'] = True
        st.stop()

# If a previous fallback requested a rerun, attempt once now.
if st.session_state.get("_needs_rerun"):
    st.session_state.pop("_needs_rerun", None)
    try:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
        else:
            st.stop()
    except Exception:
        st.stop()
# ---------------------------------------------------------------------------

# ---------------------- HELPERS: logo & watermark ----------------------------
def encode_image_b64(path: str | Path) -> str | None:
    p = Path(path) if path else None
    if not p or not p.exists():
        return None
    try:
        return base64.b64encode(p.read_bytes()).decode("utf-8")
    except Exception:
        return None

def to_data_uri(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    try:
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    except Exception:
        return None

def find_watermark_path() -> Path | None:
    candidates = [
        Path(__file__).parent / "watermark.png",
        Path(__file__).parent / "assets" / "watermark.png",
        Path.cwd() / "watermark.png",
        Path.cwd() / "assets" / "watermark.png",
        Path("/mount/src/orcamentotransplas/watermark.png"),
        Path("/workspaces/orcamentotransplas/watermark.png"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

def find_logo_path_from_hint(empresa_key: str, hint: str | Path | None) -> Path | None:
    """
    Procura um arquivo de logo a partir de um hint (nome ou caminho) e por nomes
    padrão como logo_<empresa>.png / .jpg em diretórios comuns.
    Retorna Path ou None.
    """
    empresa_key = (empresa_key or "").upper()
    base_names = []

    if hint:
        try:
            hint_path = Path(str(hint))
            if hint_path.name:
                base_names.append(hint_path.name)
        except Exception:
            pass

    nome_base = f"logo_{empresa_key.lower()}"
    base_names += [f"{nome_base}.png", f"{nome_base}.jpg"]

    # remover duplicados mantendo ordem
    seen = set()
    base_names = [x for x in base_names if not (x in seen or seen.add(x))]

    search_dirs = [
        Path(__file__).parent,
        Path(__file__).parent / "assets",
        Path.cwd(),
        Path.cwd() / "assets",
        Path("/workspaces/orcamentotransplas"),
        Path("/mount/src/orcamentotransplas"),
    ]

    # Se o hint era um path absoluto, tenta primeiro
    if hint:
        try:
            hint_path = Path(str(hint))
            if hint_path.is_absolute() and hint_path.exists():
                return hint_path
        except Exception:
            pass

    for d in search_dirs:
        for name in base_names:
            p = d / name
            if p.exists():
                return p
    return None
# ---------------------------------------------------------------------------

# ------------------------------------------------------------
# CONFIG & TÍTULO
# ------------------------------------------------------------
st.set_page_config(layout="wide", page_title="Gerador de Propostas e Orçamentos")
st.title("📄 Gerador de Propostas e Orçamentos")

# ------------------------------------------------------------
# DADOS DAS EMPRESAS
# ------------------------------------------------------------
EMPRESAS = {
    "ISOFORMA": {
        'nome': "ISOFORMA PLÁSTICOS INDÚSTRIAIS LTDA",
        'endereco': "RODOVIA DOM GABRIEL PAULINO BUENO COUTO, SN",
        'bairro_cidade_uf': "Bairro Pinhal - Cabreúva - SP",
        'cep': "13317-204",
        'contato': "(11) 4409-0919",
        'logo_path': "/workspaces/orcamentotransplas/logo_isoforma.png",
    },
    "PLASTY": {
        'nome': "PLASTY COMERCIAL DE PLÁSTICOS LTDA",
        'endereco': "RUA CARLOS SILVEIRA FRANCO NETO, 77",
        'bairro_cidade_uf': "Bairro do Jacaré - Cabreúva - SP",
        'cep': "13318-000",
        'contato': "(11) 4409-0919",
        'logo_path': "/workspaces/orcamentotransplas/logo_plasty.png",
    }
}

# ------------------------------------------------------------
# COLUNAS
# ------------------------------------------------------------
COLUNAS_CLIENTES = [
    'id', 'razao_social', 'endereco', 'bairro', 'cidade', 'uf',
    'cep', 'cnpj', 'inscricao_estadual', 'telefone', 'contato', 'email', 'condicao_pagamento', 'data_cadastro'
]
COLUNAS_PRODUTOS = [
    'id', 'sku', 'descricao', 'filme', 'cor_codigo', 'acabamento',
    'medida', 'valor_kg', 'data_cadastro'
]

# ------------------------------------------------------------
# CONEXÃO GOOGLE SHEETS (cache resource + cached reads)
# ------------------------------------------------------------
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Falha ao conectar com o Google Sheets. Verifique seus 'Secrets'.")
    st.exception(e)
    st.stop()

@st.cache_resource
def get_gspread_client():
    """
    Cria e retorna o cliente do gspread a partir dos secrets.
    Cacheado via st.cache_resource para ser reutilizado durante a vida do processo.
    """
    creds_json_text = st.secrets["gsheets"]["service_account_info"]
    creds_json = json.loads(creds_json_text)
    sa = gspread.service_account_from_dict(creds_json)
    return sa

@st.cache_data(ttl=300)  # cache por 5 minutos
def carregar_aba(aba_nome, colunas_esperadas):
    """
    Lê a aba do Google Sheets usando client cacheado. Retorna DataFrame.
    """
    try:
        sa = get_gspread_client()
        sh = sa.open_by_url(st.secrets["gsheets"]["spreadsheet"])
        ws = sh.worksheet(aba_nome)

        dados = ws.get_all_values()
        if len(dados) > 0:
            df = pd.DataFrame(dados[1:], columns=dados[0])
        else:
            df = pd.DataFrame(columns=colunas_esperadas)

        df.dropna(how="all", inplace=True)
        if 'id' in df.columns:
            df['id'] = df['id'].astype(str)

        if 'valor_kg' in df.columns:
            df['valor_kg'] = pd.to_numeric(df['valor_kg'], errors='coerce').fillna(0.0)

        return df

    except gspread.exceptions.WorksheetNotFound:
        print(f"[carregar_aba] Aba '{aba_nome}' não encontrada.")
        return pd.DataFrame(columns=colunas_esperadas)
    except Exception as e:
        # Log no servidor (menos poluição na UI)
        print(f"[carregar_aba] Erro ao carregar '{aba_nome}': {e}")
        traceback.print_exc()
        return pd.DataFrame(columns=colunas_esperadas)

def get_all_clients():
    # usa cache em session_state se disponível para evitar chamada desnecessária
    if 'clientes_cache' in st.session_state and st.session_state['clientes_cache'] is not None:
        return st.session_state['clientes_cache']
    df = carregar_aba("Clientes", COLUNAS_CLIENTES)
    if df.empty:
        clientes = []
    else:
        clientes = df.to_dict('records')
    st.session_state['clientes_cache'] = clientes
    return clientes

def get_client_by_id(client_id):
    # reutiliza cache local para não re-chamar a planilha
    clients = get_all_clients()
    for c in clients:
        if str(c.get('id')) == str(client_id):
            return c
    return None

def add_client(data_dict):
    try:
        sa = get_gspread_client()
        sh = sa.open_by_url(st.secrets["gsheets"]["spreadsheet"])
        ws = sh.worksheet("Clientes")

        try:
            cnpj_col_index = COLUNAS_CLIENTES.index('cnpj') + 1
        except ValueError:
            print("Erro crítico: Coluna 'cnpj' não encontrada.")
            return False
        cnpjs_existentes = ws.col_values(cnpj_col_index)
        if data_dict['cnpj'] and data_dict['cnpj'] in cnpjs_existentes:
            # Mensagem na UI será tratada pelo chamador
            return False

        try:
            id_col_index = COLUNAS_CLIENTES.index('id') + 1
        except ValueError:
            print("Erro crítico: Coluna 'id' não encontrada.")
            return False
        ids = ws.col_values(id_col_index)[1:]
        ids_num = [int(i) for i in ids if i and i.isdigit()]
        next_id = max(ids_num) + 1 if ids_num else 1

        data_dict['id'] = next_id
        data_dict['data_cadastro'] = datetime.now().strftime("%Y-%m-%d")
        nova_linha = [data_dict.get(col, "") for col in COLUNAS_CLIENTES]

        ws.append_row(nova_linha)

        # Atualiza cache local (session_state) para evitar re-leitura
        novo = {col: data_dict.get(col, "") for col in COLUNAS_CLIENTES}
        if 'clientes_cache' not in st.session_state or st.session_state['clientes_cache'] is None:
            st.session_state['clientes_cache'] = []
        st.session_state['clientes_cache'].append(novo)

        return True

    except gspread.exceptions.WorksheetNotFound:
        print("Aba 'Clientes' não foi encontrada na planilha.")
        return False
    except json.JSONDecodeError as e:
        print(f"Erro ao ler o JSON das credenciais: {e}")
        traceback.print_exc()
        return False
    except Exception as e:
        print("Erro ao salvar no Google Sheets (Clientes):")
        traceback.print_exc()
        return False

def get_all_products():
    if 'produtos_cache' in st.session_state and st.session_state['produtos_cache'] is not None:
        return st.session_state['produtos_cache']
    df = carregar_aba("Produtos", COLUNAS_PRODUTOS)
    if df.empty:
        produtos = []
    else:
        produtos = df.to_dict('records')
    st.session_state['produtos_cache'] = produtos
    return produtos

def get_product_by_id(product_id):
    products = get_all_products()
    for p in products:
        if str(p.get('id')) == str(product_id):
            return p
    return None

def add_product(data_dict):
    try:
        sa = get_gspread_client()
        sh = sa.open_by_url(st.secrets["gsheets"]["spreadsheet"])
        ws = sh.worksheet("Produtos")

        try:
            sku_col_index = COLUNAS_PRODUTOS.index('sku') + 1
        except ValueError:
            print("Erro crítico: Coluna 'sku' não encontrada.")
            return False
        skus_existentes = ws.col_values(sku_col_index)
        if data_dict['sku'] and data_dict['sku'] in skus_existentes:
            return False

        try:
            id_col_index = COLUNAS_PRODUTOS.index('id') + 1
        except ValueError:
            print("Erro crítico: Coluna 'id' não encontrada.")
            return False
        ids = ws.col_values(id_col_index)[1:]
        ids_num = [int(i) for i in ids if i and i.isdigit()]
        next_id = max(ids_num) + 1 if ids_num else 1

        data_dict['id'] = next_id
        data_dict['data_cadastro'] = datetime.now().strftime("%Y-%m-%d")
        nova_linha = [data_dict.get(col, "") for col in COLUNAS_PRODUTOS]

        ws.append_row(nova_linha)

        # Atualiza cache local
        novo = {col: data_dict.get(col, "") for col in COLUNAS_PRODUTOS}
        if 'produtos_cache' not in st.session_state or st.session_state['produtos_cache'] is None:
            st.session_state['produtos_cache'] = []
        st.session_state['produtos_cache'].append(novo)

        return True

    except gspread.exceptions.WorksheetNotFound:
        print("Aba 'Produtos' não foi encontrada na planilha.")
        return False
    except Exception as e:
        print("Erro ao salvar Produto no Google Sheets:")
        traceback.print_exc()
        return False

# ------------------------------------------------------------
# UI: SELEÇÃO DE EMPRESA
# ------------------------------------------------------------
empresa_selecionada_nome = st.selectbox(
    "**Selecione a Empresa para o Orçamento**",
    options=list(EMPRESAS.keys())
)
st.markdown("---")

# ------------------------------------------------------------
# SIDEBAR: CLIENTES
# ------------------------------------------------------------
st.sidebar.title("Gerenciamento")
st.sidebar.header("Clientes")
try:
    # Carregamento com spinner e usando cache em session_state/get_all_clients que já é otimizado
    with st.spinner("Carregando clientes..."):
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
            # Não forçamos rerun; o formulário/navegador já provoca reexecução natural.

    with st.sidebar.expander("➕ Adicionar Novo Cliente", expanded=False):
        with st.form("new_client_form", clear_on_submit=True):
            new_cliente_data = {
                'razao_social': st.text_input("Razão Social*"),
                'cnpj': st.text_input("CNPJ*"),
                'endereco': st.text_input("Endereço"), 'bairro': st.text_input("Bairro"),
                'cidade': st.text_input("Cidade"), 'uf': st.text_input("UF"), 'cep': st.text_input("CEP"),
                'inscricao_estadual': st.text_input("Inscrição Estadual"),
                'telefone': st.text_input("Telefone"), 'contato': st.text_input("Contato"),
                'email': st.text_input("E-mail"), 'condicao_pagamento': st.text_input("Condição de Pagamento (padrão)", value="")
            }
            submitted = st.form_submit_button("Salvar Novo Cliente")
            if submitted:
                if not new_cliente_data['razao_social'] or not new_cliente_data['cnpj']:
                    st.sidebar.error("Razão Social e CNPJ são obrigatórios.")
                else:
                    ok = add_client(new_cliente_data)
                    if ok:
                        st.sidebar.success("Cliente salvo!")
                    else:
                        st.sidebar.error("Falha ao salvar cliente (ver logs).")
except Exception as e:
    st.sidebar.error(f"Erro ao carregar clientes: {e}")
    traceback.print_exc()

def update_client_condicao(client_id, nova_condicao):
    try:
        sa = get_gspread_client()
        sh = sa.open_by_url(st.secrets["gsheets"]["spreadsheet"])
        ws = sh.worksheet("Clientes")

        dados = ws.get_all_values()
        if not dados:
            return False

        header = dados[0]
        linhas = dados[1:]

        try:
            id_index = header.index("id")
            cond_index = header.index("condicao_pagamento")
        except ValueError:
            print("Colunas necessárias não encontradas (id / condicao_pagamento).")
            return False

        for i, linha in enumerate(linhas):
            if str(linha[id_index]) == str(client_id):
                ws.update_cell(i + 2, cond_index + 1, nova_condicao)
                return True

        return False

    except Exception:
        print("Erro ao atualizar condição de pagamento:")
        traceback.print_exc()
        return False

# ------------------------------------------------------------
# SIDEBAR: PRODUTOS
# ------------------------------------------------------------
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
                    ok = add_product(new_product_data)
                    if ok:
                        st.sidebar.success("Produto salvo!")
                    else:
                        st.sidebar.error("Falha ao salvar produto (ver logs).")
except Exception as e:
    st.sidebar.error(f"Erro nas operações de produto: {e}")
    traceback.print_exc()

# ------------------------------------------------------------
# FORMULÁRIO PRINCIPAL
# ------------------------------------------------------------
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
default_cond = (dados_cliente_atual.get('condicao_pagamento') if dados_cliente_atual else "") or "28/35/42 ddl"
pagamento_condicao = st.text_input("Cond. Pagamento", value=default_cond)
pagamento_qtde_parcelas = st.number_input("Quantidade de Parcelas", min_value=1, value=3, step=1)

if dados_cliente_atual:
    if st.button("💾 Salvar condição no cadastro do cliente"):
        ok = update_client_condicao(
            st.session_state.get("cliente_id"),
            pagamento_condicao
        )
        if ok:
            st.success("Condição de pagamento atualizada no cadastro.")
            st.session_state['clientes_cache'] = None
            st.cache_data.clear()
            st.session_state['dados_cliente'] = get_client_by_id(st.session_state.get("cliente_id"))
        else:
            st.error("Não foi possível atualizar o cliente.")

    # Data de entrega opcional
    sem_data_entrega = st.checkbox("Sem data de entrega definida", value=False)
    if sem_data_entrega:
        pagamento_data_entrega = None
    else:
        pagamento_data_entrega = st.date_input("Data de Entrega", value=date.today())

    st.subheader("Impostos")
    impostos_icms = st.number_input("ICMS (%)", min_value=0.0, value=18.0, format="%.2f")
    impostos_ipi = st.number_input("IPI (%)", min_value=0.0, value=0.0, format="%.2f")

    st.subheader("Transporte e Observações")
    transportadora = {
        'nome': st.text_input("Transportadora"),
        'cnpj': st.text_input("CNPJ da Transportadora"),
        'telefone': st.text_input("Telefone da Transportadora")
    }
    observacoes = st.text_area("Observações")

# --- ITENS ---
if 'itens' not in st.session_state:
    st.session_state.itens = []

if 'editing_item' not in st.session_state:
    st.session_state.editing_item = None

with col_itens:
    st.subheader("Itens do Orçamento")

    try:
        produtos_db = get_all_products()
        produto_map = {}
        if produtos_db:
            produtos_validos = [p for p in produtos_db if p.get('descricao') and p.get('id')]
            produto_map = {f"{p['descricao']} (SKU: {p.get('sku', 'N/A')})": p for p in produtos_validos}
        opcoes_produto = ["- Digitar Manualmente -"] + list(produto_map.keys())
        produto_selecionado_str = st.selectbox(
            "Carregar Produto do Banco de Dados",
            options=opcoes_produto,
            key="produto_select"
        )
        produto_default = {}
        if produto_selecionado_str != "- Digitar Manualmente -":
            produto_default = produto_map[produto_selecionado_str]
    except Exception as e:
        st.error(f"Erro ao carregar produtos do BD: {e}")
        produto_default = {}

    # Formulário de edição (se estiver editando um item)
    editing_idx = st.session_state.get('editing_item')
    if editing_idx is not None:
        try:
            item = st.session_state.itens[editing_idx]
        except Exception:
            st.session_state.editing_item = None
            item = None

        if item:
            with st.form(key=f"edit_item_form_{editing_idx}"):
                st.write(f"Editando item {editing_idx+1}")
                descricao_e = st.text_input("Descrição", value=item['descricao'])
                filme_e = st.text_input("Filme", value=item.get('filme', 'Não'))
                cor_codigo_e = st.text_input("Cor-Código", value=item.get('cor_codigo', 'Branco Tricamada'))
                acabamento_e = st.text_input("Acabamento", value=item.get('acabamento', 'BM'))
                medida_e = st.text_input("Medida", value=item.get('medida', '2000x1000x0,50mm'))
                quantidade_e = st.number_input("Qtd (KG)", value=item['quantidade_kg'], min_value=0.01, format="%.2f")
                valor_kg_e = st.number_input("Valor (KG)", value=item['valor_kg'], min_value=0.01, format="%.2f")
                save = st.form_submit_button("Salvar Alterações")
                cancelar = st.form_submit_button("Cancelar Edição")
                if save:
                    st.session_state.itens[editing_idx].update({
                        'descricao': descricao_e,
                        'filme': filme_e,
                        'cor_codigo': cor_codigo_e,
                        'acabamento': acabamento_e,
                        'medida': medida_e,
                        'quantidade_kg': float(quantidade_e),
                        'valor_kg': float(valor_kg_e)
                    })
                    st.session_state.editing_item = None
                if cancelar:
                    st.session_state.editing_item = None

    # Formulário para adicionar novo item
    with st.form(key="add_item_form", clear_on_submit=True):
        st.write("Adicionar novo item:")
        item_cols = st.columns([3, 1, 2, 1, 2])

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
                # sem rerun forçado (form já provoca reexecução)

    # Exibição dos itens com ações individuais
    if st.session_state.itens:
        st.write("Itens adicionados:")
        total_preview = sum(item['quantidade_kg'] * item['valor_kg'] for item in st.session_state.itens)
        for i, item in enumerate(st.session_state.itens):
            subtotal = item['quantidade_kg'] * item['valor_kg']
            with st.expander(f"{i+1}. {item['descricao']} ({item['medida']}) - {item['quantidade_kg']:.2f} KG x R${item['valor_kg']:.2f} = R${subtotal:,.2f}"):
                st.write(f"Medida: {item['medida']}")
                st.write(f"Valor KG: R$ {item['valor_kg']:.2f}")
                st.write(f"IPI item: {item.get('ipi_item', 0)}%")

                col_a, col_b = st.columns([1, 1])
                if col_a.button("Remover", key=f"remover_{i}"):
                    st.session_state.itens.pop(i)
                if col_b.button("Editar", key=f"editar_{i}"):
                    st.session_state.editing_item = i

        st.markdown(f"**Total das Mercadorias: R$ {total_preview:,.2f}**")

        if st.button("Limpar Itens"):
            st.session_state.itens = []

st.markdown("---")

# ------------------------------------------------------------
# VALIDAÇÃO PRÉ-GERAÇÃO
# ------------------------------------------------------------
def validar_dados_para_pdf(dados):
    erros = []
    if not dados['cliente'].get('razao_social'):
        erros.append("Razão social do cliente vazia.")
    if not dados['itens']:
        erros.append("Nenhum item adicionado.")
    for idx, it in enumerate(dados['itens']):
        if it.get('quantidade_kg', 0) <= 0:
            erros.append(f"Item {idx+1}: quantidade inválida.")
        if it.get('valor_kg', 0) <= 0:
            erros.append(f"Item {idx+1}: valor inválido.")
    return erros

# ------------------------------------------------------------
# GERAÇÃO DO PDF (tratamento de erro sem apagar estado)
# ------------------------------------------------------------
if st.button("Gerar PDF do Orçamento", type="primary"):
    if not cliente['razao_social'] or not st.session_state.itens:
        st.error("Preencha, no mínimo, a Razão Social do cliente e adicione pelo menos um item.")
    else:
        with st.spinner("Gerando o arquivo PDF..."):
            try:
                # cálculos
                valor_mercadoria = sum(float(item['quantidade_kg']) * float(item['valor_kg']) for item in st.session_state.itens)
                ipi_percent = float(impostos_ipi)
                icms_percent = float(impostos_icms)
                qtde_parcelas_int = int(pagamento_qtde_parcelas)

                valor_ipi = valor_mercadoria * (ipi_percent / 100.0)
                total_nf = valor_mercadoria + valor_ipi
                valor_parcela = total_nf / qtde_parcelas_int if qtde_parcelas_int > 0 else 0

                dados_empresa = EMPRESAS[empresa_selecionada_nome].copy()
                hint = dados_empresa.get('logo_path', '')
                logo_path_obj = find_logo_path_from_hint(empresa_selecionada_nome, hint)
                if logo_path_obj:
                    mime = "image/png" if logo_path_obj.suffix.lower() == ".png" else "image/jpeg"
                    dados_empresa['logo_base64'] = f"data:{mime};base64," + encode_image_b64(logo_path_obj)
                else:
                    dados_empresa['logo_base64'] = None

                wm_path = find_watermark_path()
                watermark_datauri = to_data_uri(wm_path) if wm_path else ''

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
                        'data_entrega': pagamento_data_entrega.strftime('%d/%m/%Y') if pagamento_data_entrega else "",
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
                    'watermark_datauri': watermark_datauri,
                }

                # validação antes de gerar
                erros = validar_dados_para_pdf(dados)
                if erros:
                    for e in erros:
                        st.error(e)
                    st.warning("Corrija os erros acima antes de gerar o PDF.")
                else:
                    nome_arquivo_pdf = f"Orcamento_{orcamento_numero}_{cliente['razao_social'].replace(' ', '_')}.pdf"
                    try:
                        # debug_dump_html desligado para evitar lentidão em uso normal
                        pdf_bytes = criar_pdf(dados, template_path="template.html", debug_dump_html=False)
                    except Exception as e:
                        st.error("Erro ao gerar o PDF (na função criar_pdf). Veja detalhes abaixo.")
                        st.exception(e)
                        pdf_bytes = None

                    if pdf_bytes:
                        st.success(f"PDF '{nome_arquivo_pdf}' gerado com sucesso!")
                        st.download_button(
                            label="Clique aqui para baixar o PDF",
                            data=pdf_bytes,
                            file_name=nome_arquivo_pdf,
                            mime="application/pdf"
                        )

            except Exception as e:
                # Qualquer erro de preparo aqui NÃO deve apagar st.session_state.itens
                st.error("Ocorreu um erro ao preparar o PDF. Os dados não foram apagados — corrija e tente novamente.")
                st.exception(e)
