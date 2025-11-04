# pages/2_Enviar_XML_UP.py
import requests
import streamlit as st
from xml.etree import ElementTree as ET

st.set_page_config(page_title="Enviar XML (SIEG UP)", layout="wide")
st.title("Enviar XML para SIEG (UP – EnviarXml)")

BASE_URL = st.secrets.get("sieg_up", {}).get("base_url", "").rstrip("/")
API_KEY  = st.secrets.get("sieg_up", {}).get("api_key", "")

def parse_nfe_xml(xml_bytes: bytes) -> dict:
    """Extrai dados básicos (opcional) só para pré-visualização."""
    try:
        root = ET.fromstring(xml_bytes)
        ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
        ide = root.find(".//nfe:ide", ns)
        emit = root.find(".//nfe:emit", ns)
        dest = root.find(".//nfe:dest", ns)
        chave = root.attrib.get("Id", "").replace("NFe", "")
        return {
            "chave": chave or "",
            "emissao": (ide.findtext("nfe:dhEmi", default="", namespaces=ns) or ide.findtext("nfe:dEmi", default="", namespaces=ns)),
            "emitente": emit.findtext("nfe:xNome", default="", namespaces=ns) if emit is not None else "",
            "destinatario": dest.findtext("nfe:xNome", default="", namespaces=ns) if dest is not None else "",
        }
    except Exception:
        return {}

st.info("Este modo usa o endpoint **EnviarXml** (upload-only). Para listar/manifestar, use a página 'Consultar_DFe_API'.")

xml_file = st.file_uploader("Selecione um arquivo XML (NFe/CTe/MDFe)", type=["xml"])
if xml_file:
    xml_bytes = xml_file.read()

    with st.expander("Pré-visualização do XML (opcional)"):
        st.json(parse_nfe_xml(xml_bytes) or {"info": "Não consegui extrair dados (ok continuar)."})

    if st.button("Enviar XML agora", type="primary"):
        if not (BASE_URL and API_KEY):
            st.error("Configure base_url e api_key em [sieg_up] no secrets.toml.")
        else:
            with st.spinner("Enviando para SIEG..."):
                try:
                    files = {"file": ("documento.xml", xml_bytes, "application/xml")}
                    r = requests.post(BASE_URL, params={"api_key": API_KEY}, files=files, timeout=120)
                    r.raise_for_status()
                    try:
                        st.success("XML enviado com sucesso ✅")
                        st.json(r.json())
                    except ValueError:
                        st.success("XML enviado com sucesso ✅")
                        st.code(r.text)
                except requests.HTTPError as e:
                    st.error(f"HTTP {e.response.status_code}")
                    st.code((e.response.text or "")[:1000])
                except Exception as e:
                    st.exception(e)