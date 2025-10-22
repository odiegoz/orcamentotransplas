import streamlit as st
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from xhtml2pdf import pisa
import os
import traceback
import re
import io  # Importado para lidar com bytes em memória

# --- CONFIGURAÇÕES ---
SEU_NOME_OU_EMPRESA = "ISOFORMA PLASTICOS INDUSTRIAIS LTDA"

# --- Funções de Sanitização (Idênticas às suas) ---

# regex para remover height/width attributes: height="..." width='...'
_ATTR_DIM_RE = re.compile(r'\s*(?:height|width)\s*=\s*"(?:[^"]*)"|\s*(?:height|width)\s*=\s*\'(?:[^\']*)\'', flags=re.IGNORECASE)
_STYLE_DIM_RE_INTERNAL = re.compile(r'\b(height|width)\s*:\s*[^;"]+;?', flags=re.IGNORECASE)
_STYLE_ATTR_RE_GENERIC = re.compile(r'(<[^>]*?)\sstyle\s*=\s*(")([^"]*)(")', flags=re.IGNORECASE)
_STYLE_ATTR_RE_GENERIC_SINGLE = re.compile(r"(<[^>]*?)\sstyle\s*=\s*(')([^']*)(')", flags=re.IGNORECASE)
_STYLE_ATTR_RE = re.compile(r'(<(?:td|th|tr|table)[^>]*?)\sstyle\s*=\s*"(?:[^"]*)"([^>]*>)', flags=re.IGNORECASE)

def _sanitize_table_dimensions(html: str) -> str:
    """
    Remove atributos height/width e declarações height/width dentro de style=
    de elementos de tabela (e outros elementos, por segurança).
    Retorna HTML sanitizado.
    """
    if not html:
        return html
    
    sanitized = _ATTR_DIM_RE.sub('', html)

    def _strip_style_dims(match):
        pre_tag = match.group(1)
        quote = match.group(2)
        style_content = match.group(3)
        new_style_content = _STYLE_DIM_RE_INTERNAL.sub('', style_content)
        new_style_content = re.sub(r';\s*;', ';', new_style_content)
        new_style_content = re.sub(r'\s{2,}', ' ', new_style_content).strip()
        return f'{pre_tag} style={quote}{new_style_content}{quote}'

    sanitized = _STYLE_ATTR_RE_GENERIC.sub(_strip_style_dims, sanitized)
    sanitized = _STYLE_ATTR_RE_GENERIC_SINGLE.sub(_strip_style_dims, sanitized)
    sanitized = re.sub(r'\s{2,}', ' ', sanitized)
    return sanitized

def _remove_table_styles_completely(html: str) -> str:
    """
    Fallback agressivo: remove o atributo style de td/th/tr/table.
    """
    if not html:
        return html
    out = _STYLE_ATTR_RE.sub(r'\1\2', html)
    out = re.sub(r"(<(?:td|th|tr|table)[^>]*?)\sstyle\s*=\s*'(?:[^']*)'([^>]*>)", r'\1\2', out, flags=re.IGNORECASE)
    return out

# --- FUNÇÃO DE GERAR PDF (MODIFICADA PARA STREAMLIT) ---

def criar_pdf_em_memoria(dados, template_path="template.html", debug_dump_html=False):
    """
    Renderiza o template Jinja2 e converte para PDF em memória (io.BytesIO).
    Retorna os bytes do PDF ou None em caso de erro.
    """
    try:
        # --- Carregamento robusto do template ---
        # __file__ se refere a este script (gerador_para_streamlit.py)
        # os.path.dirname(__file__) é o diretório onde o script está
        script_dir = os.path.dirname(__file__)
        
        # Procura templates no diretório do script
        env = Environment(loader=FileSystemLoader(script_dir), autoescape=False)
        
        try:
            # Garante que estamos pegando o template_path relativo ao script_dir
            # (embora o FileSystemLoader(script_dir) já deva fazer isso)
            template_rel_path = os.path.basename(template_path)
            template = env.get_template(template_rel_path)
        except TemplateNotFound:
            st.error(f"Template '{template_rel_path}' não encontrado em: {script_dir}")
            return None

        # Renderiza o HTML
        html_renderizado = template.render(dados)
        
        if debug_dump_html:
            print("--- HTML Renderizado (Debug) ---")
            print(html_renderizado)
            print("---------------------------------")

        # Sanitização inicial
        html_sanitizado = _sanitize_table_dimensions(html_renderizado)

        # --- MODIFICAÇÃO PRINCIPAL: Usar io.BytesIO ---
        result_buffer = io.BytesIO()
        
        # Primeiro tentativa com HTML sanitizado
        try:
            pisa_status = pisa.CreatePDF(
                src=html_sanitizado,
                dest=result_buffer
            )

            if pisa_status.err:
                st.warning(f"Erro na primeira tentativa do PDF: {pisa_status.err}")
                raise Exception("Erro no pisa na primeira tentativa")
            
            # Sucesso
            return result_buffer.getvalue()

        except Exception as e_first:
            st.warning(f"Primeira tentativa falhou: {e_first}. Tentando fallback...")
            
            # Tentar fallback agressivo (removendo todos os estilos de tabelas)
            html_fallback = _remove_table_styles_completely(html_renderizado)
            
            # Precisamos de um novo buffer para a segunda tentativa
            fallback_buffer = io.BytesIO()
            
            try:
                pisa_status2 = pisa.CreatePDF(
                    src=html_fallback,
                    dest=fallback_buffer
                )
                if pisa_status2.err:
                    st.error(f"Tentativa de fallback também falhou: {pisa_status2.err}")
                    return None
                
                # Sucesso no fallback
                st.info("PDF gerado com sucesso (modo fallback).")
                return fallback_buffer.getvalue()
                
            except Exception as e_second:
                st.error(f"Exceção catastrófica no fallback: {e_second}")
                traceback.print_exc()
                return None

    except Exception as e:
        st.error(f"Ocorreu uma exceção inesperada em criar_pdf: {e}")
        traceback.print_exc()
        return None

# --- Exemplo de App Streamlit ---

st.title("Gerador de Orçamentos em PDF")

# Dados de exemplo para o template
dados_exemplo = {
    "empresa": SEU_NOME_OU_EMPRESA,
    "cliente_nome": "Cliente de Teste Ltda.",
    "cliente_cnpj": "12.345.678/0001-99",
    "numero_orcamento": "2025-001",
    "itens": [
        {"desc": "Produto A", "qtd": 2, "preco_unit": 50.00, "total": 100.00},
        {"desc": "Produto B", "qtd": 1, "preco_unit": 150.00, "total": 150.00},
        {"desc": "Serviço de Instalação", "qtd": 10, "preco_unit": 20.00, "total": 200.00}
    ],
    "total_geral": 450.00
}

st.subheader("Dados do Orçamento")
st.json(dados_exemplo)

# Caminho para o template (deve estar no mesmo diretório do script)
TEMPLATE_FILE = "template.html" 

if st.button("Gerar Orçamento PDF"):
    with st.spinner("Gerando PDF... Isso pode levar alguns segundos."):
        
        # Verifica se o template existe ANTES de tentar gerar
        template_full_path = os.path.join(os.path.dirname(__file__), TEMPLATE_FILE)
        if not os.path.exists(template_full_path):
            st.error(f"Erro Crítico: Arquivo 'template.html' não encontrado em {template_full_path}")
            st.stop()
            
        # Chama a função modificada
        pdf_bytes = criar_pdf_em_memoria(dados_exemplo, template_path=TEMPLATE_FILE, debug_dump_html=True)
        
        if pdf_bytes:
            st.success("PDF Gerado com Sucesso!")
            
            # --- O modo Streamlit de fazer download ---
            st.download_button(
                label="Baixar PDF",
                data=pdf_bytes,
                file_name=f"orcamento_{dados_exemplo['numero_orcamento']}.pdf",
                mime="application/pdf"
            )
        else:
            st.error("Falha ao gerar o PDF. Verifique os logs.")
