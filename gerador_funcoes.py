import os
import base64
import traceback
import streamlit as st
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

def _get_logo_base64(script_dir):
    logo_path = os.path.join(script_dir, "logo_isoforma.jpg")
    if not os.path.exists(logo_path):
        return None
    try:
        with open(logo_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except:
        return None


def criar_pdf(dados, template_path="template.html", debug_dump_html=False):
    """
    Renderiza template Jinja2 e gera PDF usando 100% WeasyPrint.
    Retorna bytes do PDF.
    """
    try:
        script_dir = os.path.dirname(os.path.realpath(__file__))

        # Carrega logo para marca d´água e/ou cabeçalho
        logo_b64 = _get_logo_base64(script_dir)
        if logo_b64 and "empresa" in dados:
            dados["empresa"]["logo_base64"] = logo_b64

        env = Environment(loader=FileSystemLoader(script_dir), autoescape=False)
        template = env.get_template(os.path.basename(template_path))

        html_renderizado = template.render(dados)

        if debug_dump_html:
            print("--- HTML ---")
            print(html_renderizado[:2000], "...\n")

        html_obj = HTML(string=html_renderizado, base_url=script_dir)

        # CSS global obrigatório para tamanho correto do A4
        css_default = CSS(string="""
            @page { size: A4; margin: 12mm; }
            body { -webkit-print-color-adjust: exact; }
        """)

        pdf_bytes = html_obj.write_pdf(stylesheets=[css_default])

        return pdf_bytes

    except Exception as e:
        st.error(f"Erro ao gerar PDF: {e}")
        print("[criar_pdf] ERRO:")
        traceback.print_exc()
        return None
