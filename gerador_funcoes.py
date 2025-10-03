# gerador_funcoes.py (versão com sanitização do HTML para evitar strings em alturas/larguras)
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from xhtml2pdf import pisa
import os
import traceback
import re

# --- CONFIGURAÇÕES ---
SEU_NOME_OU_EMPRESA = "ISOFORMA PLASTICOS INDUSTRIAIS LTDA"

# regex para remover height/width attributes: height="..." width='...'
_ATTR_DIM_RE = re.compile(r'\s*(?:height|width)\s*=\s*"(?:[^"]*)"|\s*(?:height|width)\s*=\s*\'(?:[^\']*)\'', flags=re.IGNORECASE)

# regex para remover height/width declarations dentro de style="..."
_STYLE_DIM_RE = re.compile(r'(height|width)\s*:\s*[^;"]+;?', flags=re.IGNORECASE)

# regex para remover all style attributes on table-related tags (fallback)
_STYLE_ATTR_RE = re.compile(r'(<(?:td|th|tr|table)[^>]*?)\sstyle\s*=\s*"(?:[^"]*)"([^>]*>)', flags=re.IGNORECASE)

def _sanitize_table_dimensions(html: str) -> str:
    """
    Remove atributos height/width e declarações height/width dentro de style= de elementos de tabela.
    Retorna HTML sanitizado.
    """
    if not html:
        return html
    # 1) remover height="..." e width="..." (aspas duplas e simples)
    sanitized = _ATTR_DIM_RE.sub('', html)

    # 2) remover declarações de height/width dentro de style="..."
    # precisamos processar cada style="..." e remover height/width dentro dele
    def _strip_style_dims(match):
        style_content = match.group(0)
        # remove height/width declarations
        new_style = _STYLE_DIM_RE.sub('', style_content)
        return new_style

    # Para simplificar, aplicamos uma remoção global de height/width dentro de estilos:
    sanitized = _STYLE_DIM_RE.sub('', sanitized)

    # 3) limpar múltiplos espaços criados
    sanitized = re.sub(r'\s{2,}', ' ', sanitized)

    return sanitized

def _remove_table_styles_completely(html: str) -> str:
    """
    Fallback agressivo: remove o atributo style de td/th/tr/table.
    """
    if not html:
        return html
    # remove style="..." apenas de tags de tabela
    out = _STYLE_ATTR_RE.sub(r'\1\2', html)
    # também remover eventuais style='...' com aspas simples
    out = re.sub(r"(<(?:td|th|tr|table)[^>]*?)\sstyle\s*=\s*'(?:[^']*)'([^>]*>)", r'\1\2', out, flags=re.IGNORECASE)
    return out

def criar_pdf(dados, nome_arquivo="orcamento.pdf", template_path="template.html", debug_dump_html=False):
    """
    Renderiza o template Jinja2 com os dados e converte para PDF usando xhtml2pdf (pisa).
    Retorna o caminho do arquivo gerado ou None em caso de erro.
    Faz sanitização do HTML para evitar que atributos de altura/largura em string
    causem erros no ReportLab (TypeError: unsupported operand type(s) for -: 'str' and 'int').
    """
    try:
        # Verifica existência do template
        if not os.path.exists(template_path):
            print(f"[criar_pdf] ERRO: template não encontrado em: {template_path}")
            return None

        env = Environment(loader=FileSystemLoader('.'), autoescape=False)
        try:
            template = env.get_template(template_path)
        except TemplateNotFound:
            print(f"[criar_pdf] ERRO: Template '{template_path}' não encontrado no diretório atual.")
            return None

        # Renderiza o HTML (string Unicode)
        html_renderizado = template.render(dados)

        if debug_dump_html:
            # Útil para debug: salvar uma cópia do HTML gerado
            with open("debug_orcamento_render.html", "w", encoding="utf-8") as f:
                f.write(html_renderizado)

        # Sanitização inicial: remover height/width attributes e declarações dentro de style
        html_sanitizado = _sanitize_table_dimensions(html_renderizado)

        # Primeiro tentativa com HTML sanitizado
        try:
            with open(nome_arquivo, "wb") as result_file:
                pisa_status = pisa.CreatePDF(
                    src=html_sanitizado,
                    dest=result_file
                )

            if pisa_status.err:
                print(f"[criar_pdf] Primeiro intento: pisa_status.err = {pisa_status.err}")
                # mostrar parte do HTML para diagnóstico (limitado)
                snippet = html_sanitizado[:2000]
                print("[criar_pdf] Trecho do HTML sanitizado (até 2000 chars):")
                print(snippet)
                # vamos tentar fallback abaixo
                raise Exception("Erro no pisa na primeira tentativa")
        except Exception as e_first:
            print("[criar_pdf] Primeiro intento falhou: ", e_first)
            # Tentar fallback agressivo: remover completamente style de tags de tabela
            html_fallback = _remove_table_styles_completely(html_sanitizado)
            if debug_dump_html:
                with open("debug_orcamento_render_fallback.html", "w", encoding="utf-8") as f:
                    f.write(html_fallback)

            try:
                with open(nome_arquivo, "wb") as result_file:
                    pisa_status2 = pisa.CreatePDF(
                        src=html_fallback,
                        dest=result_file
                    )
                if pisa_status2.err:
                    print(f"[criar_pdf] Segundo intento (fallback) também retornou erros: {pisa_status2.err}")
                    snippet2 = html_fallback[:2000]
                    print("[criar_pdf] Trecho do HTML fallback (até 2000 chars):")
                    print(snippet2)
                    return None
            except Exception as e_second:
                print("[criar_pdf] Segundo intento (fallback) levantou exceção:")
                traceback.print_exc()
                return None

        # Se chegou aqui, teve sucesso (pisa escreveu o arquivo)
        print(f"[criar_pdf] PDF '{nome_arquivo}' criado com sucesso!")
        return nome_arquivo

    except Exception as e:
        # Impressão detalhada da stack para diagnóstico
        print("[criar_pdf] Ocorreu uma exceção inesperada em criar_pdf:")
        traceback.print_exc()
        print(f"[criar_pdf] mensagem de exceção: {e}")
        return None
