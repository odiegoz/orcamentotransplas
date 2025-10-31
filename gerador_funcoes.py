# gerador_funcoes.py — versão WeasyPrint
import os
import io
import re
import base64
import traceback
import streamlit as st
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

# WeasyPrint
from weasyprint import HTML, CSS

# --- Sanitizações (mantidas; não são obrigatórias no WeasyPrint, mas ajudam a limpar) ---
_ATTR_DIM_RE = re.compile(
    r'\s*(?:height|width)\s*=\s*"(?:[^"]*)"|\s*(?:height|width)\s*=\s*\'(?:[^\']*)\'',
    flags=re.IGNORECASE
)
_STYLE_DIM_RE_INTERNAL = re.compile(r'\b(height|width)\s*:\s*[^;"]+;?', flags=re.IGNORECASE)
_STYLE_ATTR_RE_GENERIC = re.compile(r'(<[^>]*?)\sstyle\s*=\s*(")([^"]*)(")', flags=re.IGNORECASE)
_STYLE_ATTR_RE_GENERIC_SINGLE = re.compile(r"(<[^>]*?)\sstyle\s*=\s*(')([^']*)(')", flags=re.IGNORECASE)
_STYLE_ATTR_RE = re.compile(r'(<(?:td|th|tr|table)[^>]*?)\sstyle\s*=\s*"(?:[^"]*)"([^>]*>)', flags=re.IGNORECASE)

def _sanitize_table_dimensions(html: str) -> str:
    if not html:
        return html
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

# --- Logo em Base64 (opcional) ---
def _get_logo_base64(script_dir: str):
    """
    Tenta carregar 'logo_isoforma.jpg' no mesmo diretório do script.
    Se não existir, não é erro (a logo pode vir via dados['empresa']['logo_base64']).
    """
    logo_path = os.path.join(script_dir, "logo_isoforma.jpg")
    if not os.path.exists(logo_path):
        # Avisa, mas não trava
        st.warning("logo_isoforma.jpg não encontrada (ok se você já injeta a logo via dados['empresa']['logo_base64']).")
        return None
    try:
        with open(logo_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        st.error(f"Erro ao carregar logo: {e}")
        return None

# --- Principal: gerar PDF com WeasyPrint ---
def criar_pdf(dados, template_path="template.html", debug_dump_html=False):
    """
    Renderiza o template Jinja2 e converte para PDF com WeasyPrint.
    Retorna bytes do PDF ou None em caso de erro.

    Observações:
    - WeasyPrint respeita transparência no PNG e `@page { background-image }`.
    - Suporta `background-size`, caso queira ajustar a marca d'água no template.
    """
    try:
        script_dir = os.path.dirname(os.path.realpath(__file__))

        # Injeta logo base64 se não veio nos dados
        try:
            if 'empresa' in dados and not dados['empresa'].get('logo_base64'):
                logo_b64 = _get_logo_base64(script_dir)
                if logo_b64:
                    dados['empresa']['logo_base64'] = logo_b64
        except Exception:
            # Não trava o fluxo se algo der errado aqui
            traceback.print_exc()

        # Carrega template
        env = Environment(loader=FileSystemLoader(script_dir), autoescape=False)
        try:
            template_rel_path = os.path.basename(template_path)
            template = env.get_template(template_rel_path)
        except TemplateNotFound:
            st.error(f"Template '{template_rel_path}' não encontrado em: {script_dir}")
            return None

        # Renderiza
        html_renderizado = template.render(dados)
        if debug_dump_html:
            print("----- HTML Renderizado (início) -----")
            print(html_renderizado[:2000])
            print("----- (truncado) -----")

        # Sanitização leve (opcional)
        html_final = _sanitize_table_dimensions(html_renderizado)

        # Geração do PDF
        # base_url permite resolver caminhos relativos de imgs/css se existirem
        pdf_bytes = HTML(string=html_final, base_url=script_dir).write_pdf(
            stylesheets=[
                CSS(string='@page { size: A4; margin: 12mm; }')  # redundante com seu CSS, mas seguro
            ]
        )

        return pdf_bytes

    except Exception as e:
        st.error(f"Erro ao gerar PDF com WeasyPrint: {e}")
        traceback.print_exc()
        return None
# --- Fim do gerador_funcoes.py ---