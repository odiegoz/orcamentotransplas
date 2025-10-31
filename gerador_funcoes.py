import os
import base64
import traceback
import streamlit as st
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from weasyprint import HTML, CSS

# (Opcional) Se não estiver usando mais, pode apagar essa função
# def _get_logo_base64(script_dir):
#     logo_path = os.path.join(script_dir, "logo_isoforma.jpg")
#     if not os.path.exists(logo_path):
#         return None
#     try:
#         with open(logo_path, "rb") as image_file:
#             return base64.b64encode(image_file.read()).decode("utf-8")
#     except Exception:
#         return None


def criar_pdf(dados, template_path="template.html", debug_dump_html=False):
    """
    Renderiza template Jinja2 e gera PDF usando 100% WeasyPrint.
    Retorna bytes do PDF ou None em caso de erro.
    """
    try:
        script_dir = os.path.dirname(os.path.realpath(__file__))

        # Jinja2: carrega template
        env = Environment(loader=FileSystemLoader(script_dir), autoescape=False)
        try:
            template = env.get_template(os.path.basename(template_path))
        except TemplateNotFound:
            st.error(f"Template '{template_path}' não encontrado em: {script_dir}")
            return None

        # Renderiza HTML
        html_renderizado = template.render(dados)

        if debug_dump_html:
            print("--- BASE URL ---")
            print(script_dir)
            print("--- HTML (primeiros 2000 chars) ---")
            print(html_renderizado[:2000], "...\n")

        # WeasyPrint: aponta base_url para resolver assets relativos corretamente
        html_obj = HTML(string=html_renderizado, base_url=script_dir)

        # CSS global mínimo: NÃO definir @page aqui para não conflitar com o template
        css_minimo = CSS(string="""
            /* Mantém cores/fundos na impressão */
            html, body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        """)

        # Gera PDF
        pdf_bytes = html_obj.write_pdf(stylesheets=[css_minimo])
        return pdf_bytes

    except Exception as e:
        st.error(f"Erro ao gerar PDF: {e}")
        print("[criar_pdf] ERRO:")
        traceback.print_exc()
        return None