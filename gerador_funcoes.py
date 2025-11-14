# gerador_funcoes.py
"""
Gerador de PDF usando Jinja2 + WeasyPrint.

Principais mudanças:
- NÃO usa streamlit dentro de criar_pdf (sem st.error/st.caption).
- Em vez de retornar None em erro, lança exceções claras (RuntimeError) com a causa original.
- debug_dump_html=True: grava arquivo HTML em /tmp (ou cwd) para inspeção e imprime informação útil.
- Logs mínimos via print() e traceback.print_exc() para facilitar troubleshooting em logs do Streamlit.
"""

import importlib
import os
import tempfile
import base64
import traceback
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

# WeasyPrint import (pode lançar ImportError)
try:
    from weasyprint import HTML, CSS
    _WEASYPRINT_VERSION = getattr(importlib.import_module("weasyprint"), "__version__", "unknown")
except Exception as e:
    # não suprimir aqui — propagar depois quando necessário
    HTML = None
    CSS = None
    _WEASYPRINT_VERSION = None

def _check_weasyprint():
    if HTML is None or CSS is None:
        raise RuntimeError("WeasyPrint não disponível. Instale 'weasyprint' e dependências do sistema (libpango, libcairo etc.).")

def criar_pdf(dados, template_path="template.html", debug_dump_html=False):
    """
    Renderiza template Jinja2 e gera PDF usando WeasyPrint.

    Parâmetros
    ----------
    dados : dict
        Contexto enviado para o template Jinja2.
    template_path : str
        Caminho relativo ou absoluto para o arquivo HTML/Jinja template.
    debug_dump_html : bool
        Se True, grava o HTML renderizado em arquivo temporário para depuração
        e imprime o caminho no stdout/logs.

    Retorna
    -------
    bytes
        Conteúdo do PDF gerado (bytes).

    Lança
    -----
    RuntimeError
        Em qualquer erro durante renderização/geração com mensagem descritiva.
    """
    try:
        _check_weasyprint()

        # determina diretório onde procurar o template
        script_dir = os.path.dirname(os.path.realpath(__file__))

        # se o usuário passou um caminho absoluto para template_path, usa direto
        if os.path.isabs(template_path):
            template_dir = os.path.dirname(template_path) or script_dir
            template_name = os.path.basename(template_path)
        else:
            template_dir = script_dir
            template_name = template_path

        env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False
        )

        # Carrega template
        try:
            template = env.get_template(template_name)
        except TemplateNotFound as e:
            msg = f"Template '{template_name}' não encontrado em: {template_dir}"
            print("[criar_pdf] TemplateNotFound:", msg)
            raise RuntimeError(msg) from e

        # Renderiza o HTML com os dados fornecidos
        try:
            html_renderizado = template.render(dados)
        except Exception as e:
            print("[criar_pdf] Erro durante renderização do template Jinja2.")
            traceback.print_exc()
            raise RuntimeError("Erro ao renderizar o template Jinja2.") from e

        # Opção de depuração: gravar o HTML em arquivo para inspecionar
        if debug_dump_html:
            try:
                # tenta gravar em /tmp, senão cwd
                base_tmp = tempfile.gettempdir() or os.getcwd()
                dump_name = f"orcamento_debug_{os.getpid()}_{int(os.stat(__file__).st_mtime)}.html"
                dump_path = os.path.join(base_tmp, dump_name)
                with open(dump_path, "w", encoding="utf-8") as f:
                    f.write(html_renderizado)
                print(f"[criar_pdf] HTML renderizado gravado para depuração em: {dump_path}")
            except Exception:
                print("[criar_pdf] Falha ao gravar HTML de debug.")
                traceback.print_exc()

        # cria objeto HTML com base_url apontando para script_dir (resolve caminhos relativos de assets)
        try:
            html_obj = HTML(string=html_renderizado, base_url=template_dir)
        except Exception as e:
            print("[criar_pdf] Falha ao criar objeto HTML do WeasyPrint.")
            traceback.print_exc()
            raise RuntimeError("Erro ao criar objeto HTML do WeasyPrint.") from e

        # CSS mínimo para preservar cores de fundo na impressão
        css_minimo = CSS(string="""
            html, body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        """)

        # Geração do PDF (pode lançar)
        try:
            pdf_bytes = html_obj.write_pdf(stylesheets=[css_minimo])
        except Exception as e:
            print("[criar_pdf] Falha ao gerar PDF com WeasyPrint.")
            traceback.print_exc()
            raise RuntimeError("Erro ao renderizar PDF com WeasyPrint. Verifique dependências de sistema e o HTML gerado.") from e

        # sucesso
        return pdf_bytes

    except Exception as e:
        # Normalizamos todas as exceções para RuntimeError com a causa original preservada.
        if isinstance(e, RuntimeError):
            raise
        else:
            print("[criar_pdf] Exceção não esperada:")
            traceback.print_exc()
            raise RuntimeError("Erro inesperado ao gerar PDF.") from e


# Opcional: helper para retornar versões (útil para debug externo)
def get_versions():
    """
    Retorna um dict com versões relevantes (WeasyPrint, pydyf se instalaram, etc).
    """
    versions = {}
    try:
        versions['weasyprint'] = _WEASYPRINT_VERSION or "not-installed"
    except Exception:
        versions['weasyprint'] = "unknown"
    try:
        import importlib
        pydyf = importlib.import_module("pydyf")
        versions['pydyf'] = getattr(pydyf, "__version__", "unknown")
    except Exception:
        versions['pydyf'] = "not-installed"
    return versions
