import streamlit as st
from functions import (
    baixar_audio_youtube, get_video_title, extrair_intervalo_audio,
    transcrever_audio_whisper, gerar_resumo, get_openai_client, salvar_resumo_json, ajustar_resumo
)
import os
import zipfile
from datetime import datetime
import time
import streamlit.components.v1 as components

st.set_page_config(page_title="Gerador de Resumos", layout="wide")

api_key = st.secrets["openai"]["api_key"]
client = get_openai_client(api_key)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "chat_histories" not in st.session_state:
    st.session_state.chat_histories = {}
if "last_outputs" not in st.session_state:
    st.session_state.last_outputs = {}
if "processing" not in st.session_state:
    st.session_state.processing = {}
if "youtube_info" not in st.session_state:
    st.session_state.youtube_info = {"url": "", "inicio": 0, "fim": 1, "resumo_gerado": False}
if "uploaded_files_info" not in st.session_state:
    st.session_state.uploaded_files_info = []
if "current_view" not in st.session_state:
    st.session_state.current_view = "generate"

def handle_chat_input(file_key):
    if file_key in st.session_state.chat_histories:
        st.session_state.processing[file_key] = True
        st.rerun()

def process_pending_messages():
    for file_key, is_processing in list(st.session_state.processing.items()):
        if is_processing:
            try:
                historico = st.session_state.chat_histories[file_key]
                for i in range(len(historico) - 1, -1, -1):
                    if historico[i]["role"] == "user":
                        user_message = historico[i]["content"]
                        break
                adjusted_resumo = ajustar_resumo(historico, user_message, client)
                st.session_state.chat_histories[file_key].append({"role": "assistant", "content": adjusted_resumo})
                st.session_state.last_outputs[file_key] = adjusted_resumo
                if st.session_state.youtube_info.get("titulo") == file_key:
                    st.session_state.youtube_info["resumo"] = adjusted_resumo
                for arquivo in st.session_state.uploaded_files_info:
                    if arquivo.get("titulo") == file_key:
                        arquivo["resumo"] = adjusted_resumo
            except Exception as e:
                st.session_state.chat_histories[file_key].append(
                    {"role": "assistant", "content": f"Erro ao ajustar o resumo: {str(e)}"}
                )
            st.session_state.processing[file_key] = False

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
    """Remove ou substitui caracteres inválidos em nomes de arquivos."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename

def show_chat(file_key, titulo):
    st.subheader(f"Chat de ajustes - {titulo}")
    
    chat_container = st.container()
    with chat_container:
        if file_key in st.session_state.chat_histories:
            for msg in st.session_state.chat_histories[file_key]:
                if msg["role"] == "user":
                    st.chat_message("user").write(msg["content"])
                else:
                    if isinstance(msg["content"], dict):
                        texto_completo = (
                            "1) Pontos principais em formato de tópicos detalhados:\n" + msg["content"]["pontos_principais"] + "\n\n" +
                            "2) Resumo técnico e abrangente da transcrição:\n" + msg["content"]["resumo_tecnico"] + "\n\n" +
                            "3) Perguntas e respostas baseadas no texto:\n" + msg["content"]["perguntas_respostas"] + "\n\n" +
                            "4) Exemplos de copy:\n" + msg["content"]["exemplos_copy"]
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
            if f"input_value_{file_key}" not in st.session_state:
                st.session_state[f"input_value_{file_key}"] = ""
            user_input = st.text_input(
                "Digite ou fale sua solicitação de ajuste",
                key=f"user_message_{file_key}",
                placeholder="Digite aqui ou use o microfone ao lado...",
                value=st.session_state[f"input_value_{file_key}"],
                on_change=lambda: st.session_state.update({f"input_value_{file_key}": st.session_state[f"user_message_{file_key}"]})
            )
        with col_mic:
            audio_value = st.audio_input(
                "",
                key=f"audio_input_{file_key}",
                label_visibility="collapsed"
            )
        
        col_submit = st.columns([5, 1])[1]
        with col_submit:
            if st.button("Enviar", key=f"send_button_{file_key}"):
                if user_input and user_input.strip():
                    if file_key not in st.session_state.chat_histories:
                        st.session_state.chat_histories[file_key] = []
                    st.session_state.chat_histories[file_key].append({"role": "user", "content": user_input})
                    st.session_state.processing[file_key] = True
                    st.session_state[f"input_value_{file_key}"] = ""
                    if f"audio_processed_{file_key}" in st.session_state:
                        del st.session_state[f"audio_processed_{file_key}"]
                    st.rerun()
        
        if audio_value is not None and f"audio_processed_{file_key}" not in st.session_state:
            with st.spinner("Transcrevendo áudio..."):
                safe_file_key = sanitize_filename(file_key)
                temp_audio_path = f"temp_chat_audio_{safe_file_key}.mp3"
                with open(temp_audio_path, "wb") as f:
                    f.write(audio_value.read())
                transcricao = transcrever_audio_whisper(temp_audio_path, client)
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)
                if transcricao and transcricao.strip():
                    st.session_state[f"input_value_{file_key}"] = transcricao
                    st.session_state[f"audio_processed_{file_key}"] = True
                    st.rerun()

def regenerate_summary(transcricao, file_key=None):
    """Regenera o resumo a partir de uma transcrição existente."""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text("Regenerando resumo...")
        progress_bar.progress(50)
        resumo_secoes = gerar_resumo(transcricao, client)
        
        if file_key:  # Atualiza o resumo existente
            if file_key in st.session_state.chat_histories:
                st.session_state.chat_histories[file_key] = [{"role": "assistant", "content": resumo_secoes}]
            else:
                st.session_state.chat_histories[file_key] = [{"role": "assistant", "content": resumo_secoes}]
            st.session_state.last_outputs[file_key] = resumo_secoes
            
            if st.session_state.youtube_info.get("titulo") == file_key:
                st.session_state.youtube_info["resumo"] = resumo_secoes
                caminho_json = salvar_resumo_json(st.session_state.youtube_info, file_key)
                st.session_state.youtube_info["caminho_json"] = caminho_json
            for arquivo in st.session_state.uploaded_files_info:
                if arquivo.get("titulo") == file_key:
                    arquivo["resumo"] = resumo_secoes
                    caminho_json = salvar_resumo_json(arquivo, file_key)
                    arquivo["caminho_json"] = caminho_json
        
        progress_bar.progress(100)
        status_text.text("Resumo regenerado com sucesso!")
        time.sleep(1)
        progress_bar.empty()
        status_text.empty()
        
        return resumo_secoes
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"Erro ao regenerar o resumo: {str(e)}")
        return None

def process_youtube():
    url = st.session_state.youtube_info["url"]
    inicio = st.session_state.youtube_info["inicio"]
    fim = st.session_state.youtube_info["fim"]
    
    if not st.session_state.youtube_info.get("resumo_gerado", False):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            status_text.text("Baixando áudio do YouTube...")
            progress_bar.progress(20)
            arquivo_audio = baixar_audio_youtube(url)
            
            status_text.text("Obtendo informações do vídeo...")
            progress_bar.progress(30)
            video_title = get_video_title(url)
            
            status_text.text("Extraindo trecho de áudio...")
            progress_bar.progress(40)
            audio_cortado = extrair_intervalo_audio(arquivo_audio, inicio, fim)
            
            def update_status(message):
                status_text.text(message)
            
            status_text.text("Iniciando transcrição...")
            transcricao = transcrever_audio_whisper(audio_cortado, client, status_callback=update_status)
            progress_bar.progress(80)
            
            status_text.text("Gerando resumo...")
            resumo_secoes = gerar_resumo(transcricao, client)
            
            dados_json = {
                "titulo": video_title,
                "url": url,
                "transcricao": transcricao,
                "resumo": resumo_secoes,
                "data_criacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            caminho_json = salvar_resumo_json(dados_json, video_title)
            st.session_state.chat_histories[video_title] = [{"role": "assistant", "content": resumo_secoes}]
            st.session_state.last_outputs[video_title] = resumo_secoes
            st.session_state.youtube_info.update({
                "titulo": video_title,
                "resumo": resumo_secoes,
                "transcricao": transcricao,  # Salva a transcrição
                "caminho_json": caminho_json,
                "data_criacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "resumo_gerado": True
            })
            
            progress_bar.progress(100)
            status_text.text("Resumo gerado com sucesso!")
            time.sleep(1)
            progress_bar.empty()
            status_text.empty()
            
            for temp_file in ["audio_temp.mp3", "audio_cortado.mp3"]:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except PermissionError:
                        pass
                        
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"Erro ao processar o áudio: {str(e)}")
            return False
    
    return True

def process_audio_files(uploaded_files):
    if not uploaded_files:
        st.error("Por favor, carregue pelo menos um arquivo de áudio.")
        return False
        
    progress_bar = st.progress(0)
    status_text = st.empty()
    caminhos_json = []
    
    st.session_state.uploaded_files_info = []
    
    try:
        total_files = len(uploaded_files)
        for i, uploaded_file in enumerate(uploaded_files):
            file_progress_base = int((i / total_files) * 100)
            progress_bar.progress(file_progress_base)
            status_text.text(f"Processando arquivo {i+1} de {total_files}: {uploaded_file.name}")
            
            nome_sem_extensao = os.path.splitext(uploaded_file.name)[0]
            caminho_temp = f"temp_{nome_sem_extensao}.mp3"
            with open(caminho_temp, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            def update_status(message):
                status_text.text(f"Arquivo {i+1}/{total_files}: {message}")
            
            status_text.text(f"Arquivo {i+1}/{total_files}: Iniciando transcrição...")
            transcricao = transcrever_audio_whisper(caminho_temp, client, status_callback=update_status)
            file_progress = int(((i + 0.8) / total_files) * 100)
            progress_bar.progress(file_progress)
            
            status_text.text(f"Arquivo {i+1}/{total_files}: Gerando resumo...")
            resumo_secoes = gerar_resumo(transcricao, client)
            
            dados_json = {
                "titulo": nome_sem_extensao,
                "url": None,
                "transcricao": transcricao,
                "resumo": resumo_secoes,
                "data_criacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            caminho_json = salvar_resumo_json(dados_json, nome_sem_extensao)
            caminhos_json.append(caminho_json)
            
            st.session_state.uploaded_files_info.append({
                "titulo": nome_sem_extensao,
                "resumo": resumo_secoes,
                "transcricao": transcricao,  # Salva a transcrição
                "caminho_json": caminho_json,
                "data_criacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            st.session_state.chat_histories[nome_sem_extensao] = [{"role": "assistant", "content": resumo_secoes}]
            st.session_state.last_outputs[nome_sem_extensao] = resumo_secoes
            
            if os.path.exists(caminho_temp):
                try:
                    os.remove(caminho_temp)
                except PermissionError:
                    pass
        
        if len(caminhos_json) > 1:
            zip_path = "resumos_audio.zip"
            with zipfile.ZipFile(zip_path, "w") as zipf:
                for caminho_json in caminhos_json:
                    zipf.write(caminho_json)
            st.session_state.zip_path = zip_path
        
        progress_bar.progress(100)
        status_text.text(f"Processamento concluído: {len(uploaded_files)} arquivos processados com sucesso!")
        time.sleep(1)
        progress_bar.empty()
        status_text.empty()
        
        return True
        
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"Erro ao processar arquivos: {str(e)}")
        return False

def generate_interface():
    st.title("Gerar Resumos de Vídeos ou Áudios")
    
    fonte = st.radio("Escolha a fonte do conteúdo:", ("URL do YouTube", "Arquivos de áudio"))
    
    if fonte == "URL do YouTube":
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            url = st.text_input("URL do YouTube:", value=st.session_state.youtube_info["url"])
        with col2:
            inicio = st.number_input("Início (segundos):", min_value=0, step=1, value=st.session_state.youtube_info["inicio"])
        with col3:
            fim = st.number_input("Fim (segundos):", min_value=inicio + 1, step=1, value=max(inicio + 1, st.session_state.youtube_info["fim"]))
        
        st.session_state.youtube_info["url"] = url
        st.session_state.youtube_info["inicio"] = inicio
        st.session_state.youtube_info["fim"] = fim
        
        if not st.session_state.youtube_info.get("resumo_gerado", False):
            if st.button("Gerar Resumo", key="youtube_button", disabled=not url):
                if process_youtube():
                    st.rerun()
        
        if st.session_state.youtube_info.get("resumo_gerado", False):
            st.success("Resumo gerado com sucesso!")
            st.write(f"**Título:** {st.session_state.youtube_info['titulo']}")
            st.write("**Resumo:**")
            st.write("1) Pontos principais em formato de tópicos detalhados:")
            st.write(st.session_state.youtube_info["resumo"]["pontos_principais"])
            st.write("2) Resumo técnico e abrangente da transcrição:")
            st.write(st.session_state.youtube_info["resumo"]["resumo_tecnico"])
            st.write("3) Perguntas e respostas baseadas no texto:")
            st.write(st.session_state.youtube_info["resumo"]["perguntas_respostas"])
            st.write("4) Exemplos de copy:")
            st.write(st.session_state.youtube_info["resumo"]["exemplos_copy"])
            
            with open(st.session_state.youtube_info["caminho_json"], "rb") as f:
                st.download_button(
                    label="Baixar JSON",
                    data=f,
                    file_name=f"{st.session_state.youtube_info['titulo']}.json",
                    mime="application/json"
                )
            
            # Botão para regenerar resumo
            if st.button("Regenerar Resumo", key="regen_youtube"):
                if "transcricao" in st.session_state.youtube_info:
                    regenerate_summary(st.session_state.youtube_info["transcricao"], st.session_state.youtube_info["titulo"])
                    st.rerun()
                else:
                    st.error("Transcrição não disponível para regenerar o resumo.")
            
            st.markdown(
                """
                <hr style="border: none; height: 4px; background: linear-gradient(to right, #FF6B6B, #4ECDC4); margin: 20px 0;">
                """,
                unsafe_allow_html=True
            )
            
            show_chat(st.session_state.youtube_info["titulo"], st.session_state.youtube_info["titulo"])
        
        if st.button("Criar Novo Resumo", key="new_youtube"):
            st.session_state.youtube_info = {"url": "", "inicio": 0, "fim": 1, "resumo_gerado": False}
            if "titulo" in st.session_state.youtube_info:
                del st.session_state.chat_histories[st.session_state.youtube_info["titulo"]]
            st.rerun()
    
    else:
        st.write("**Formatos suportados:** MP3, WAV, M4A")
        st.write("Os áudios carregados serão processados integralmente, sem necessidade de recorte.")
        
        uploaded_files = st.file_uploader(
            "Carregue seus arquivos de áudio",
            type=["mp3", "wav", "m4a"],
            accept_multiple_files=True
        )
        
        if not st.session_state.uploaded_files_info:
            if st.button("Gerar Resumos", key="audio_button", disabled=not uploaded_files):
                if process_audio_files(uploaded_files):
                    st.rerun()
        
        if st.session_state.uploaded_files_info:
            st.success(f"{len(st.session_state.uploaded_files_info)} arquivo(s) processado(s) com sucesso!")
            
            if len(st.session_state.uploaded_files_info) > 1:
                arquivo_tabs = st.tabs([arquivo["titulo"] for arquivo in st.session_state.uploaded_files_info])
                for i, tab in enumerate(arquivo_tabs):
                    with tab:
                        arquivo = st.session_state.uploaded_files_info[i]
                        st.write(f"**Arquivo:** {arquivo['titulo']}")
                        st.write("**Resumo:**")
                        st.write("1) Pontos principais em formato de tópicos detalhados:")
                        st.write(arquivo["resumo"]["pontos_principais"])
                        st.write("2) Resumo técnico e abrangente da transcrição:")
                        st.write(arquivo["resumo"]["resumo_tecnico"])
                        st.write("3) Perguntas e respostas baseadas no texto:")
                        st.write(arquivo["resumo"]["perguntas_respostas"])
                        st.write("4) Exemplos de copy:")
                        st.write(arquivo["resumo"]["exemplos_copy"])
                        
                        with open(arquivo["caminho_json"], "rb") as f:
                            st.download_button(
                                label=f"Baixar JSON",
                                data=f,
                                file_name=f"{arquivo['titulo']}.json",
                                mime="application/json",
                                key=f"download_{i}"
                            )
                        
                        # Botão para regenerar resumo
                        if st.button("Regenerar Resumo", key=f"regen_audio_{i}"):
                            if "transcricao" in arquivo:
                                regenerate_summary(arquivo["transcricao"], arquivo["titulo"])
                                st.rerun()
                            else:
                                st.error("Transcrição não disponível para regenerar o resumo.")
                        
                        st.markdown(
                            """
                            <hr style="border: none; height: 4px; background: linear-gradient(to right, #FF6B6B, #4ECDC4); margin: 20px 0;">
                            """,
                            unsafe_allow_html=True
                        )
                        
                        show_chat(arquivo["titulo"], arquivo["titulo"])
                
                if hasattr(st.session_state, "zip_path") and os.path.exists(st.session_state.zip_path):
                    with open(st.session_state.zip_path, "rb") as f:
                        st.download_button(
                            label=f"Baixar todos os JSONs (ZIP - {len(st.session_state.uploaded_files_info)} arquivos)",
                            data=f,
                            file_name="resumos_audio.zip",
                            mime="application/zip"
                        )
            else:
                arquivo = st.session_state.uploaded_files_info[0]
                st.write(f"**Arquivo:** {arquivo['titulo']}")
                st.write("**Resumo:**")
                st.write("1) Pontos principais em formato de tópicos detalhados:")
                st.write(arquivo["resumo"]["pontos_principais"])
                st.write("2) Resumo técnico e abrangente da transcrição:")
                st.write(arquivo["resumo"]["resumo_tecnico"])
                st.write("3) Perguntas e respostas baseadas no texto:")
                st.write(arquivo["resumo"]["perguntas_respostas"])
                st.write("4) Exemplos de copy:")
                st.write(arquivo["resumo"]["exemplos_copy"])
                
                with open(arquivo["caminho_json"], "rb") as f:
                    st.download_button(
                        label="Baixar JSON",
                        data=f,
                        file_name=f"{arquivo['titulo']}.json",
                        mime="application/json"
                    )
                
                # Botão para regenerar resumo
                if st.button("Regenerar Resumo", key="regen_audio_single"):
                    if "transcricao" in arquivo:
                        regenerate_summary(arquivo["transcricao"], arquivo["titulo"])
                        st.rerun()
                    else:
                        st.error("Transcrição não disponível para regenerar o resumo.")
                
                st.markdown(
                    """
                    <hr style="border: none; height: 4px; background: linear-gradient(to right, #FF6B6B, #4ECDC4); margin: 20px 0;">
                    """,
                    unsafe_allow_html=True
                )
                
                show_chat(arquivo["titulo"], arquivo["titulo"])
        
        if st.button("Processar Novos Arquivos", key="new_audio"):
            st.session_state.uploaded_files_info = []
            if hasattr(st.session_state, "zip_path"):
                delattr(st.session_state, "zip_path")
            for arquivo in st.session_state.uploaded_files_info:
                if arquivo["titulo"] in st.session_state.chat_histories:
                    del st.session_state.chat_histories[arquivo["titulo"]]
            st.rerun()

def main_screen():
    process_pending_messages()
    generate_interface()

if not st.session_state.logged_in:
    login_screen()
else:
    main_screen()