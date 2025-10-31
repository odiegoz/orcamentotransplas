# gerador_funcoes.py — tenta WeasyPrint; se faltar, faz fallback para xhtml2pdf
import os
import io
import re
import base64
import traceback
import streamlit as st
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

# Tenta importar WeasyPrint (recomendado)
WEASY_AVAILABLE = True
try:
    from weasyprint import HTML, CSS
except Exception:
    WEASY_AVAILABLE = False

# Fallback para xhtml2pdf se WeasyPrint não estiver disponível
if not WEASY_AVAILABLE:
    try:
        from xhtml2pdf import pisa
    except Exception:
        pisa = None

# --- Sanitizações (mantidas) ---
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

def _remove_table_styles_completely(html: str) -> str:
    if not html:
        return html
    out = _STYLE_ATTR_RE.sub(r'\1\2', html)
    out = re.sub(r"(<(?:td|th|tr|table)[^>]*?)\sstyle\s*=\s*'(?:[^']*)'([^>]*>)", r'\1\2', out, flags=re.IGNORECASE)
    return out

# --- Logo base64 (opcional) ---
def _get_logo_base64(script_dir: str):
    logo_path = os.path.join(script_dir, "logo_isoforma.jpg")
    if not os.path.exists(logo_path):
        # Sem drama: você pode injetar via dados['empresa']['logo_base64']
        return None
    try:
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        st.error(f"Erro ao carregar logo: {e}")
        return None

# --- Gerar PDF ---
def criar_pdf(dados, template_path="template.html", debug_dump_html=False):
    """
    Se WeasyPrint estiver instalado: usa WeasyPrint (suporta bem transparência e @page background).
    Caso contrário: faz fallback para xhtml2pdf/pisa (funciona, mas pode não respeitar transparência).
    """
    try:
        script_dir = os.path.dirname(os.path.realpath(__file__))

        # Injeta logo se não veio nos dados
        if 'empresa' in dados and not dados['empresa'].get('logo_base64'):
            logo_b64 = _get_logo_base64(script_dir)
            if logo_b64:
                dados['empresa']['logo_base64'] = logo_b64

        # Carrega template
        env = Environment(loader=FileSystemLoader(script_dir), autoescape=False)
        try:
            template_rel_path = os.path.basename(template_path)
            template = env.get_template(template_rel_path)
        except TemplateNotFound:
            st.error(f"Template '{template_rel_path}' não encontrado em: {script_dir}")
            return None

        html_renderizado = template.render(dados)
        if debug_dump_html:
            print("----- HTML Renderizado (início) -----")
            print(html_renderizado[:2000])
            print("----- (truncado) -----")

        html_final = _sanitize_table_dimensions(html_renderizado)

        # Caminho A: WeasyPrint disponível
        if WEASY_AVAILABLE:
            try:
                pdf_bytes = HTML(string=html_final, base_url=script_dir).write_pdf(
                    stylesheets=[CSS(string='@page { size: A4; margin: 12mm; }')]
                )
                return pdf_bytes
            except Exception as e:
                st.warning(f"WeasyPrint falhou: {e}. Tentando fallback para xhtml2pdf...")
                traceback.print_exc()

        # Caminho B: Fallback xhtml2pdf
        if pisa is None:
            st.error("xhtml2pdf não disponível e WeasyPrint ausente/falhou. Instale WeasyPrint (recomendado).")
            return None

        # Primeira tentativa com xhtml2pdf
        try:
            buf = io.BytesIO()
            pisa_status = pisa.CreatePDF(src=html_final, dest=buf)
            if pisa_status.err:
                raise Exception(f"xhtml2pdf retornou erro: {pisa_status.err}")
            return buf.getvalue()
        except Exception:
            # Fallback sem estilos bloqueadores
            html_fallback = _remove_table_styles_completely(html_renderizado)
            buf2 = io.BytesIO()
            pisa_status2 = pisa.CreatePDF(src=html_fallback, dest=buf2)
            if pisa_status2.err:
                st.error(f"Fallback xhtml2pdf também falhou: {pisa_status2.err}")
                return None
            st.info("PDF gerado com sucesso (modo fallback xhtml2pdf).")
            return buf2.getvalue()

    except Exception as e:
        st.error(f"Ocorreu um erro ao gerar o PDF: {e}")
        traceback.print_exc()
        return None