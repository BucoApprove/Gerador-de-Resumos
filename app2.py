import streamlit as st
from functions import (
    transcrever_audio_whisper, gerar_resumo, get_openai_client, salvar_resumo_json, ajustar_resumo
)
import os
from datetime import datetime
import streamlit.components.v1 as components
import time

st.set_page_config(page_title="Gerador de Resumos", layout="wide")

api_key = st.secrets["openai"]["api_key"]
client = get_openai_client(api_key)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "last_output" not in st.session_state:
    st.session_state.last_output = None
if "processing" not in st.session_state:
    st.session_state.processing = False
if "audio_info" not in st.session_state:
    st.session_state.audio_info = {"titulo": "", "resumo": None, "transcricao": "", "data_criacao": "", "modelo_escolhido": None}

def handle_chat_input():
    if st.session_state.processing:
        st.rerun()

def process_pending_messages():
    if st.session_state.processing:
        try:
            historico = st.session_state.chat_history
            user_message = historico[-1]["content"]
            modelo = st.session_state.audio_info["modelo_escolhido"]
            adjusted_resumo = ajustar_resumo(historico, user_message, client, modelo)
            st.session_state.chat_history.append({"role": "assistant", "content": adjusted_resumo})
            st.session_state.last_output = adjusted_resumo
            st.session_state.audio_info["resumo"] = adjusted_resumo
        except Exception as e:
            st.session_state.chat_history.append(
                {"role": "assistant", "content": f"Erro ao ajustar o resumo: {str(e)}"}
            )
        st.session_state.processing = False
        st.rerun()

def login_screen():
    st.title("Login - Gerador de Resumos")
    with st.form(key="login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submit_button = st.form_submit_button(label="Entrar")
    if submit_button:
        stored_username = st.secrets["credentials"]["user"]
        stored_password = st.secrets["credentials"]["password"]
        if username == stored_username and password == stored_password:
            st.session_state.logged_in = True
            st.success("Login bem-sucedido!")
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos!")

def sanitize_filename(filename):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename

def estimate_tokens(text):
    if not text:
        return 0
    words = len(text.split())
    chars = len(text)
    return max(words, chars // 4)

def show_chat(titulo):
    st.subheader(f"Chat de ajustes - {titulo} (Modelo: {st.session_state.audio_info['modelo_escolhido']})")
    
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.chat_message("user").write(msg["content"])
            else:
                if isinstance(msg["content"], dict):
                    texto_completo = (
                        "1) Pontos principais em formato de tópicos detalhados:\n" + msg["content"].get("pontos_principais", "Não disponível") + "\n\n" +
                        "2) Resumo prático e completo da transcrição:\n" + msg["content"].get("resumo_pratico", "Não disponível") + "\n\n" +
                        "3) Perguntas e respostas baseadas no texto:\n" + msg["content"].get("perguntas_respostas", "Não disponível") + "\n\n" +
                        "4) Exemplos de copy:\n" + msg["content"].get("exemplos_copy", "Não disponível")
                    )
                    st.chat_message("assistant").write(texto_completo)
                else:
                    st.chat_message("assistant").write(msg["content"])
    
    st.markdown(
        """
        <hr style="border: none; height: 4px; background: linear-gradient(to right, #FF6B6B, #4ECDC4); margin: 20px 0;">
        """,
        unsafe_allow_html=True
    )
    
    with st.container():
        col_input, col_mic = st.columns([5, 1])
        with col_input:
            if "input_value" not in st.session_state:
                st.session_state.input_value = ""
            user_input = st.text_input(
                "Digite ou fale sua solicitação de ajuste",
                key="user_message",
                placeholder="Digite aqui ou use o microfone ao lado...",
                value=st.session_state.input_value,
                on_change=lambda: st.session_state.update({"input_value": st.session_state["user_message"]})
            )
        with col_mic:
            audio_value = st.audio_input(
                "",
                key="audio_input",
                label_visibility="collapsed"
            )
        
        col_submit = st.columns([5, 1])[1]
        with col_submit:
            if st.button("Enviar", key="send_button"):
                if user_input and user_input.strip():
                    st.session_state.chat_history.append({"role": "user", "content": user_input})
                    st.session_state.processing = True
                    st.session_state.input_value = ""
                    if "audio_processed" in st.session_state:
                        del st.session_state.audio_processed
                    st.rerun()
        
        if audio_value is not None and "audio_processed" not in st.session_state:
            with st.spinner("Transcrevendo áudio..."):
                safe_file_key = sanitize_filename(titulo)
                temp_audio_path = f"temp_chat_audio_{safe_file_key}.mp3"
                with open(temp_audio_path, "wb") as f:
                    f.write(audio_value.read())
                transcricao = transcrever_audio_whisper(temp_audio_path, client)
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)
                if transcricao and transcricao.strip():
                    st.session_state.input_value = transcricao
                    st.session_state.audio_processed = True
                    st.rerun()

def transcrever_audio(uploaded_file):
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        nome_sem_extensao = os.path.splitext(uploaded_file.name)[0]
        caminho_temp = f"temp_{nome_sem_extensao}.mp3"
        with open(caminho_temp, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        def update_status(message):
            status_text.text(message)
        
        status_text.text("Iniciando transcrição...")
        transcricao = transcrever_audio_whisper(caminho_temp, client, status_callback=update_status)
        
        progress_bar.progress(100)
        status_text.text("Transcrição concluída com sucesso!")
        time.sleep(1)
        progress_bar.empty()
        status_text.empty()
        
        st.session_state.audio_info.update({
            "titulo": nome_sem_extensao,
            "transcricao": transcricao,
            "data_criacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        if os.path.exists(caminho_temp):
            os.remove(caminho_temp)
        
        st.rerun()
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"Erro ao transcrever o arquivo: {str(e)}")

def gerar_resumo_com_modelo(modelo):
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text(f"Gerando resumo com {modelo}...")
        progress_bar.progress(50)
        resumo_secoes = gerar_resumo(st.session_state.audio_info["transcricao"], client, modelo)
        
        st.session_state.chat_history = [{"role": "assistant", "content": resumo_secoes}]
        st.session_state.last_output = resumo_secoes
        st.session_state.audio_info["resumo"] = resumo_secoes
        st.session_state.audio_info["modelo_escolhido"] = modelo
        
        progress_bar.progress(100)
        status_text.text("Resumo gerado com sucesso!")
        time.sleep(1)
        progress_bar.empty()
        status_text.empty()
        
        st.rerun()
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"Erro ao gerar o resumo: {str(e)}")

def generate_interface():
    st.title("Gerar Resumo de Áudio")
    
    st.write("**Formatos suportados:** MP3, WAV, M4A")
    st.write("Carregue um arquivo de áudio para transcrever e depois escolha um modelo para gerar o resumo.")
    
    uploaded_file = st.file_uploader(
        "Carregue seu arquivo de áudio",
        type=["mp3", "wav", "m4a"],
        accept_multiple_files=False
    )
    
    if uploaded_file and not st.session_state.audio_info["transcricao"]:
        if st.button("Transcrever Áudio", key="transcribe_button"):
            transcrever_audio(uploaded_file)
    
    if st.session_state.audio_info["transcricao"]:
        st.subheader("Transcrição do Áudio")
        st.markdown(
            f"""
            <div style="max-height: 150px; overflow-y: auto; border: 1px solid #ccc; padding: 10px; background-color: #f9f9f9;">
                {st.session_state.audio_info["transcricao"]}
            </div>
            """,
            unsafe_allow_html=True
        )
        transcricao_tokens = estimate_tokens(st.session_state.audio_info["transcricao"])
        st.write(f"**Estimativa de Tokens da Transcrição:** ~{transcricao_tokens} tokens")
        
        st.subheader("Escolha um Modelo para Gerar o Resumo")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Gerar com GPT-4o Mini", key="gpt4o_mini"):
                gerar_resumo_com_modelo("gpt-4o-mini")
        with col2:
            if st.button("Gerar com o1-mini", key="o1-mini"):
                gerar_resumo_com_modelo("o1-mini")
        with col3:
            if st.button("Gerar com o3-mini", key="o3-mini"):
                gerar_resumo_com_modelo("o3-mini")
    
    if st.session_state.audio_info["resumo"]:
        st.success(f"Resumo gerado com {st.session_state.audio_info['modelo_escolhido']}!")
        
        st.write(f"**Arquivo:** {st.session_state.audio_info['titulo']}")
        st.write("**Último Resumo Atualizado:**")
        ultimo_resumo = st.session_state.last_output if st.session_state.last_output else st.session_state.audio_info["resumo"]
        st.write("1) Pontos principais em formato de tópicos detalhados:")
        st.write(ultimo_resumo.get("pontos_principais", "Não disponível"))
        st.write("2) Resumo prático e completo da transcrição:")
        st.write(ultimo_resumo.get("resumo_pratico", "Não disponível"))
        st.write("3) Perguntas e respostas baseadas no texto:")
        st.write(ultimo_resumo.get("perguntas_respostas", "Não disponível"))
        st.write("4) Exemplos de copy:")
        st.write(ultimo_resumo.get("exemplos_copy", "Não disponível"))
        
        resumo_tokens = estimate_tokens(
            ultimo_resumo["pontos_principais"] + " " +
            ultimo_resumo["resumo_pratico"] + " " +
            ultimo_resumo["perguntas_respostas"] + " " +
            ultimo_resumo["exemplos_copy"]
        )
        st.write(f"**Estimativa de Tokens do Resumo:** ~{resumo_tokens} tokens")
        
        if st.download_button(
            label="Baixar JSON",
            data=salvar_resumo_json(st.session_state.audio_info, st.session_state.audio_info["titulo"], return_bytes=True),
            file_name=f"{st.session_state.audio_info['titulo']}.json",
            mime="application/json"
        ):
            st.success("JSON baixado com sucesso!")
        
        st.subheader("Tente Outro Modelo")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Regenerar com GPT-4o Mini", key="regen_gpt4o_mini"):
                gerar_resumo_com_modelo("gpt-4o-mini")
        with col2:
            if st.button("Regenerar com o1-mini", key="regen_o1-mini"):
                gerar_resumo_com_modelo("o1-mini")
        with col3:
            if st.button("Regenerar com o3-mini", key="regen_o3-mini"):
                gerar_resumo_com_modelo("o3-mini")
        
        st.markdown(
            """
            <hr style="border: none; height: 4px; background: linear-gradient(to right, #FF6B6B, #4ECDC4); margin: 20px 0;">
            """,
            unsafe_allow_html=True
        )
        
        show_chat(st.session_state.audio_info["titulo"])
    
    if st.button("Processar Novo Arquivo", key="new_audio"):
        st.session_state.audio_info = {"titulo": "", "resumo": None, "transcricao": "", "data_criacao": "", "modelo_escolhido": None}
        st.session_state.chat_history = []
        st.session_state.last_output = None
        st.rerun()

def main_screen():
    process_pending_messages()
    generate_interface()

if not st.session_state.logged_in:
    login_screen()
else:
    main_screen()
