import streamlit as st
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from xhtml2pdf import pisa
import os
import traceback
import re
import io
import base64 # Importado para corrigir a imagem

# --- Funções de Sanitização (Mantidas como estavam) ---
_ATTR_DIM_RE = re.compile(r'\s*(?:height|width)\s*=\s*"(?:[^"]*)"|\s*(?:height|width)\s*=\s*\'(?:[^\']*)\'', flags=re.IGNORECASE)
_STYLE_DIM_RE_INTERNAL = re.compile(r'\b(height|width)\s*:\s*[^;"]+;?', flags=re.IGNORECASE)
_STYLE_ATTR_RE_GENERIC = re.compile(r'(<[^>]*?)\sstyle\s*=\s*(")([^"]*)(")', flags=re.IGNORECASE)
_STYLE_ATTR_RE_GENERIC_SINGLE = re.compile(r"(<[^>]*?)\sstyle\s*=\s*(')([^']*)(')", flags=re.IGNORECASE)
_STYLE_ATTR_RE = re.compile(r'(<(?:td|th|tr|table)[^>]*?)\sstyle\s*=\s*"(?:[^"]*)"([^>]*>)', flags=re.IGNORECASE)

def _sanitize_table_dimensions(html: str) -> str:
    if not html: return html
    sanitized = _ATTR_DIM_RE.sub('', html)
    
    def _strip_style_dims(match):
        pre_tag, quote, style_content = match.group(1), match.group(2), match.group(3)
        new_style_content = _STYLE_DIM_RE_INTERNAL.sub('', style_content)
        new_style_content = re.sub(r';\s*;', ';', new_style_content).strip()
        new_style_content = re.sub(r'\s{2,}', ' ', new_style_content)
        return f'{pre_tag} style={quote}{new_style_content}{quote}'

    sanitized = _STYLE_ATTR_RE_GENERIC.sub(_strip_style_dims, sanitized)
    sanitized = _STYLE_ATTR_RE_GENERIC_SINGLE.sub(_strip_style_dims, sanitized)
    sanitized = re.sub(r'\s{2,}', ' ', sanitized)
    return sanitized

def _remove_table_styles_completely(html: str) -> str:
    if not html: return html
    out = _STYLE_ATTR_RE.sub(r'\1\2', html)
    out = re.sub(r"(<(?:td|th|tr|table)[^>]*?)\sstyle\s*=\s*'(?:[^']*)'([^>]*>)", r'\1\2', out, flags=re.IGNORECASE)
    return out

# --- CORREÇÃO: Função para carregar e encodar a logo ---
def _get_logo_base64(script_dir):
    logo_path = os.path.join(script_dir, "logo_isoforma.jpg")
    if not os.path.exists(logo_path):
        st.warning("logo_isoforma.jpg não encontrada.")
        return None
    try:
        with open(logo_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return encoded_string
    except Exception as e:
        st.error(f"Erro ao carregar logo: {e}")
        return None

# --- FUNÇÃO DE GERAR PDF (Corrigida para Streamlit) ---

def criar_pdf(dados, template_path="template.html", debug_dump_html=False):
    """
    Renderiza o template Jinja2 e converte para PDF em memória (io.BytesIO).
    Retorna os bytes do PDF ou None em caso de erro.
    """
    try:
        # Pega o diretório onde este script (gerador_funcoes.py) está
        script_dir = os.path.dirname(os.path.realpath(__file__))
        
        # --- CORREÇÃO: Carrega a logo e injeta nos dados ---
        logo_b64 = _get_logo_base64(script_dir)
        if logo_b64:
            # Adiciona a logo dentro do dicionário da empresa
            if 'empresa' in dados:
                dados['empresa']['logo_base64'] = logo_b64
        # --- Fim da correção da logo ---

        env = Environment(loader=FileSystemLoader(script_dir), autoescape=False)
        
        try:
            template_rel_path = os.path.basename(template_path)
            template = env.get_template(template_rel_path)
        except TemplateNotFound:
            st.error(f"Template '{template_rel_path}' não encontrado em: {script_dir}")
            print(f"[criar_pdf] ERRO: Template '{template_rel_path}' não encontrado em: {script_dir}")
            return None

        html_renderizado = template.render(dados)
        
        if debug_dump_html:
            print(f"--- HTML Renderizado (Debug) --- \n{html_renderizado[:1500]}...")

        html_sanitizado = _sanitize_table_dimensions(html_renderizado)
        result_buffer = io.BytesIO()
        
        # Tentativa 1
        try:
            pisa_status = pisa.CreatePDF(src=html_sanitizado, dest=result_buffer)
            if pisa_status.err:
                st.warning(f"Erro na primeira tentativa do PDF (pisa_status.err): {pisa_status.err}")
                print(f"[criar_pdf] Primeiro intento: pisa_status.err = {pisa_status.err}")
                raise Exception("Erro no pisa na primeira tentativa")
            
            print("[criar_pdf] PDF gerado na primeira tentativa!")
            return result_buffer.getvalue()

        # Fallback
        except Exception as e_first:
            st.warning(f"Primeira tentativa falhou: {e_first}. Tentando fallback...")
            print(f"[criar_pdf] Primeiro intento falhou: {e_first}")
            
            html_fallback = _remove_table_styles_completely(html_renderizado)
            fallback_buffer = io.BytesIO()
            
            try:
                pisa_status2 = pisa.CreatePDF(src=html_fallback, dest=fallback_buffer)
                if pisa_status2.err:
                    st.error(f"Tentativa de fallback também falhou: {pisa_status2.err}")
                    print(f"[criar_pdf] Segundo intento (fallback) também retornou erros: {pisa_status2.err}")
                    return None
                
                st.info("PDF gerado com sucesso (modo fallback).")
                print("[criar_pdf] PDF gerado com sucesso (modo fallback).")
                return fallback_buffer.getvalue()
                
            except Exception as e_second:
                st.error(f"Exceção catastrófica no fallback: {e_second}")
                print("[criar_pdf] Segundo intento (fallback) levantou exceção:")
                traceback.print_exc()
                return None

    except Exception as e:
        st.error(f"Ocorreu uma exceção inesperada em criar_pdf: {e}")
        print("[criar_pdf] Ocorreu uma exceção inesperada em criar_pdf:")
        traceback.print_exc()
        return None