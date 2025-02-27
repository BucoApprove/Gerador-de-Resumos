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
    st.session_state.audio_info = {"titulo": "", "resumo": None, "transcricao": "", "data_criacao": ""}

def handle_chat_input():
    if st.session_state.processing:
        st.rerun()

def process_pending_messages():
    if st.session_state.processing:
        try:
            historico = st.session_state.chat_history
            user_message = historico[-1]["content"]
            adjusted_resumo = ajustar_resumo(historico, user_message, client)
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
    """Estima o número de tokens com base em palavras e caracteres (aproximadamente 4 caracteres por token)."""
    if not text:
        return 0
    words = len(text.split())
    chars = len(text)
    return max(words, chars // 4)  # Usa o maior valor como estimativa conservadora

def show_chat(titulo):
    st.subheader(f"Chat de ajustes - {titulo}")
    
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

def regenerate_summary(transcricao, titulo):
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text("Regenerando resumo...")
        progress_bar.progress(50)
        resumo_secoes = gerar_resumo(transcricao, client)
        
        st.session_state.chat_history = [{"role": "assistant", "content": resumo_secoes}]
        st.session_state.last_output = resumo_secoes
        st.session_state.audio_info["resumo"] = resumo_secoes
        
        progress_bar.progress(100)
        status_text.text("Resumo regenerado com sucesso!")
        time.sleep(1)
        progress_bar.empty()
        status_text.empty()
        
        st.rerun()
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"Erro ao regenerar o resumo: {str(e)}")

def process_audio_file(uploaded_file):
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
        
        progress_bar.progress(50)
        
        status_text.text("Gerando resumo...")
        resumo_secoes = gerar_resumo(transcricao, client)
        
        st.session_state.chat_history = [{"role": "assistant", "content": resumo_secoes}]
        st.session_state.last_output = resumo_secoes
        st.session_state.audio_info.update({
            "titulo": nome_sem_extensao,
            "resumo": resumo_secoes,
            "transcricao": transcricao,
            "data_criacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        progress_bar.progress(100)
        status_text.text("Resumo gerado com sucesso!")
        time.sleep(1)
        progress_bar.empty()
        status_text.empty()
        
        if os.path.exists(caminho_temp):
            os.remove(caminho_temp)
        
        st.rerun()
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"Erro ao processar o arquivo: {str(e)}")

def generate_interface():
    st.title("Gerar Resumo de Áudio")
    
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
        resumo_tokens = estimate_tokens(
            st.session_state.audio_info["resumo"]["pontos_principais"] + " " +
            st.session_state.audio_info["resumo"]["resumo_pratico"] + " " +
            st.session_state.audio_info["resumo"]["perguntas_respostas"] + " " +
            st.session_state.audio_info["resumo"]["exemplos_copy"]
        )
        st.write(f"**Estimativa de Tokens Usados:**")
        st.write(f"- Transcrição: ~{transcricao_tokens} tokens")
        st.write(f"- Resumo Gerado: ~{resumo_tokens} tokens")
        st.write(f"- Total Estimado: ~{transcricao_tokens + resumo_tokens} tokens")
        st.markdown("*(Nota: Esta é uma estimativa aproximada baseada em ~4 caracteres por token.)*")

    st.write("**Formatos suportados:** MP3, WAV, M4A")
    st.write("Carregue um arquivo de áudio por vez para gerar o resumo.")
    
    uploaded_file = st.file_uploader(
        "Carregue seu arquivo de áudio",
        type=["mp3", "wav", "m4a"],
        accept_multiple_files=False
    )
    
    if not st.session_state.audio_info["resumo"]:
        if st.button("Gerar Resumo", key="audio_button", disabled=not uploaded_file):
            process_audio_file(uploaded_file)
    
    if st.session_state.audio_info["resumo"]:
        st.success("Resumo gerado com sucesso!")
        
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
        
        if st.download_button(
            label="Baixar JSON",
            data=salvar_resumo_json(st.session_state.audio_info, st.session_state.audio_info["titulo"], return_bytes=True),
            file_name=f"{st.session_state.audio_info['titulo']}.json",
            mime="application/json"
        ):
            st.success("JSON baixado com sucesso!")
        
        if st.button("Regenerar Resumo", key="regen_audio"):
            regenerate_summary(st.session_state.audio_info["transcricao"], st.session_state.audio_info["titulo"])
        
        st.markdown(
            """
            <hr style="border: none; height: 4px; background: linear-gradient(to right, #FF6B6B, #4ECDC4); margin: 20px 0;">
            """,
            unsafe_allow_html=True
        )
        
        show_chat(st.session_state.audio_info["titulo"])
    
    if st.button("Processar Novo Arquivo", key="new_audio"):
        st.session_state.audio_info = {"titulo": "", "resumo": None, "transcricao": "", "data_criacao": ""}
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
