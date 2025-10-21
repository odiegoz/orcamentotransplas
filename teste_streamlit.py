import streamlit as st
from gerador_funcoes import criar_pdf

# --- Título ---
st.title("Gerador de Orçamento PDF - ISOFORMA")

# --- Dados do teste ---
st.header("Dados da Empresa / Cliente")
empresa = st.text_input("Empresa:", "ISOFORMA PLASTICOS INDUSTRIAIS LTDA")
orcamento_numero = st.text_input("Número do Orçamento:", "12345")
data_emissao = st.date_input("Data de Emissão")
vendedor = st.text_input("Vendedor:", "João Silva")

cliente = {
    "razao_social": st.text_input("Razão Social:", "Cliente XYZ Ltda"),
    "cnpj": st.text_input("CNPJ:", "12.345.678/0001-90"),
    "endereco": st.text_input("Endereço:", "Rua A, 123"),
    "bairro": st.text_input("Bairro:", "Centro"),
    "cidade": st.text_input("Cidade:", "São Paulo"),
    "uf": st.text_input("UF:", "SP"),
    "contato": st.text_input("Contato:", "Maria"),
    "telefone": st.text_input("Telefone:", "(11) 99999-9999"),
    "cep": st.text_input("CEP:", "01000-000"),
    "email": st.text_input("E-mail:", "cliente@xyz.com")
}

itens = [
    {
        "descricao": "Chapa de PS Cristal",
        "medida": "2x1",
        "cor_codigo": "Transparente",
        "acabamento": "Brilho",
        "filme": "Proteção",
        "quantidade_kg": 50.0,
        "valor_kg": 20.0,
        "ipi_item": 5.0
    }
]

totais = {
    "valor_mercadoria": 1000.0,
    "base_calculo_icms": 1000.0,
    "icms_perc": 18.0,
    "ipi_perc": 5.0,
    "valor_ipi": 50.0,
    "total_nf": 1050.0
}

# --- Botão para gerar PDF ---
if st.button("Gerar PDF"):
    dados = {
        "empresa": empresa,
        "orcamento_numero": orcamento_numero,
        "data_emissao": data_emissao.strftime("%d/%m/%Y"),
        "vendedor": vendedor,
        "cliente": cliente,
        "itens": itens,
        "totais": totais
    }

    pdf_file = criar_pdf(dados, nome_arquivo="orcamento.pdf", template_path="template.html")

    if pdf_file:
        st.success(f"PDF gerado: {pdf_file}")
        with open(pdf_file, "rb") as f:
            st.download_button("Download PDF", f, file_name=pdf_file, mime="application/pdf")
    else:
        st.error("Falha ao gerar PDF.")
