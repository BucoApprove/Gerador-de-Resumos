from openai import OpenAI
from moviepy.editor import AudioFileClip
import json
import os
import math
from datetime import datetime
import io

def get_openai_client(api_key):
    return OpenAI(api_key=api_key)

def dividir_audio_em_chunks(arquivo_audio, duracao_maxima=300):
    audio = AudioFileClip(arquivo_audio)
    duracao_total = audio.duration
    
    if duracao_total <= duracao_maxima:
        audio.close()
        return [arquivo_audio]
    
    num_chunks = math.ceil(duracao_total / duracao_maxima)
    chunks_paths = []
    
    for i in range(num_chunks):
        inicio = i * duracao_maxima
        fim = min((i + 1) * duracao_maxima, duracao_total)
        temp_path = f"temp_chunk_{i}.mp3"
        chunk = audio.subclip(inicio, fim)
        chunk.write_audiofile(temp_path)
        chunks_paths.append(temp_path)
    
    audio.close()
    return chunks_paths

def transcrever_audio_whisper(arquivo_audio, client, status_callback=None):
    chunks = dividir_audio_em_chunks(arquivo_audio)
    transcricao_completa = ""
    
    for i, chunk_path in enumerate(chunks):
        if status_callback:
            status_callback(f"Transcrevendo parte {i+1} de {len(chunks)}...")
        
        with open(chunk_path, "rb") as audio_file:
            transcricao_chunk = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="pt"
            )
        
        transcricao_completa += transcricao_chunk.text + " "
        
        if chunk_path != arquivo_audio and chunk_path.startswith("temp_chunk_"):
            try:
                os.remove(chunk_path)
            except Exception:
                pass
    
    return transcricao_completa.strip()

def gerar_resumo(transcricao, client):
    prompt = f"""
    Resuma o seguinte texto em um formato estruturado como conteúdo/conhecimento técnico para alimentar um assistente de IA. Retorne cada seção com conteúdo completo e detalhado, sem omitir informações:

    ### Estrutura Obrigatória ###
    1) Pontos principais em formato de tópicos detalhados:
    2) Resumo técnico e abrangente da transcrição:
    3) Perguntas e respostas baseadas no texto:
    4) Exemplos de copy:

    ### Instruções Detalhadas ###
    1) Liste os 5-6 pontos principais em formato de tópicos detalhados, incluindo:
       - Introdução (mantendo a voz do professor/palestrante)
       - Conceito Principal
       - Técnicas Ensinadas (com exemplos)
       - Os Melhores Exemplos Dados
       - Como Aplicar na Prática
       - Frases-Chave do Apresentador

    2) Elabore um resumo técnico e abrangente da transcrição, destacando todos os pontos técnicos relevantes, conceitos importantes e metodologias apresentadas. Não limite o número de parágrafos e priorize a completude das informações técnicas.

    3) Inclua 3-5 perguntas e respostas baseadas no texto, alternando entre questões técnicas e questões mais simples. Forneça respostas completas e detalhadas.

    4) Com base no resumo acima (tópicos, resumo e perguntas/respostas), utilize o conhecimento e crie 3 copies de exemplo:
       - Uma com foco em residência bucomaxilofacial
       - Duas com tópicos variados relacionados ao conteúdo

    ### Texto para Resumir ###
    {transcricao}

    ### Formato de Resposta ###
    Responda apenas com as seções numeradas, sem texto adicional fora delas. Certifique-se de que cada seção tenha conteúdo completo e não apenas títulos.
    """
    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=5000
    )
    texto_resumo = resposta.choices[0].message.content

    secoes = {
        "pontos_principais": "",
        "resumo_tecnico": "",
        "perguntas_respostas": "",
        "exemplos_copy": ""
    }
    linhas = texto_resumo.split("\n")
    secao_atual = None
    
    for linha in linhas:
        if linha.strip().startswith("1) Pontos principais em formato de tópicos detalhados:"):
            secao_atual = "pontos_principais"
            continue
        elif linha.strip().startswith("2) Resumo técnico e abrangente da transcrição:"):
            secao_atual = "resumo_tecnico"
            continue
        elif linha.strip().startswith("3) Perguntas e respostas baseadas no texto:"):
            secao_atual = "perguntas_respostas"
            continue
        elif linha.strip().startswith("4) Exemplos de copy:"):
            secao_atual = "exemplos_copy"
            continue
        elif secao_atual and linha.strip():
            secoes[secao_atual] += linha + "\n"
    
    for chave in secoes:
        secoes[chave] = secoes[chave].strip()
        if not secoes[chave]:
            secoes[chave] = "Conteúdo não gerado para esta seção."

    return secoes

def ajustar_resumo(historico, instrucao_usuario, client):
    historico_texto = "\n\n".join([f"{msg['role'].upper()}: {msg['content'] if isinstance(msg['content'], str) else json.dumps(msg['content'])}" for msg in historico])

    resumo_anterior = None
    for mensagem in reversed(historico):
        if mensagem["role"] == "assistant" and isinstance(mensagem["content"], dict):
            resumo_anterior = mensagem["content"]
            break
    
    if not resumo_anterior:
        resumo_anterior = {
            "pontos_principais": "Resumo original não encontrado.",
            "resumo_tecnico": "Resumo original não encontrado.",
            "perguntas_respostas": "Resumo original não encontrado.",
            "exemplos_copy": "Resumo original não encontrado."
        }

    prompt = f"""
    Aqui está o histórico completo de interações:

    {historico_texto}

    Aqui está o resumo mais recente a ser ajustado:
    1) Pontos principais em formato de tópicos detalhados:
    {resumo_anterior['pontos_principais']}

    2) Resumo técnico e abrangente da transcrição:
    {resumo_anterior['resumo_tecnico']}

    3) Perguntas e respostas baseadas no texto:
    {resumo_anterior['perguntas_respostas']}

    4) Exemplos de copy:
    {resumo_anterior['exemplos_copy']}

    ### Instrução do Usuário ###
    '{instrucao_usuario}'

    ### Objetivo ###
    Ajuste o resumo acima APENAS conforme a instrução do usuário. Não gere um novo resumo do zero nem modifique partes que não foram explicitamente solicitadas na instrução. Preserve o formato estruturado com as quatro seções numeradas (1, 2, 3, 4) e mantenha o conteúdo original das seções não afetadas pela instrução. Forneça apenas o resumo ajustado nas seções numeradas, sem comentários adicionais fora delas.
    """
    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=5000
    )
    texto_resumo = resposta.choices[0].message.content

    secoes = {
        "pontos_principais": "",
        "resumo_tecnico": "",
        "perguntas_respostas": "",
        "exemplos_copy": ""
    }
    linhas = texto_resumo.split("\n")
    secao_atual = None
    
    for linha in linhas:
        if linha.strip().startswith("1) Pontos principais em formato de tópicos detalhados:"):
            secao_atual = "pontos_principais"
            continue
        elif linha.strip().startswith("2) Resumo técnico e abrangente da transcrição:"):
            secao_atual = "resumo_tecnico"
            continue
        elif linha.strip().startswith("3) Perguntas e respostas baseadas no texto:"):
            secao_atual = "perguntas_respostas"
            continue
        elif linha.strip().startswith("4) Exemplos de copy:"):
            secao_atual = "exemplos_copy"
            continue
        elif secao_atual and linha.strip():
            secoes[secao_atual] += linha + "\n"
    
    for chave in secoes:
        secoes[chave] = secoes[chave].strip()
        if not secoes[chave]:
            secoes[chave] = resumo_anterior[chave]  # Preserva o conteúdo original se não ajustado

    return secoes

def salvar_resumo_json(dados, nome_arquivo, return_bytes=False):
    nome_arquivo = "".join(c if c.isalnum() or c in " _-" else "_" for c in nome_arquivo)
    
    dados_json = {
        "titulo": dados["titulo"],
        "data_criacao": dados["data_criacao"],
        "resumo": {
            "pontos_principais": dados["resumo"]["pontos_principais"],
            "resumo_tecnico": dados["resumo"]["resumo_tecnico"],
            "perguntas_respostas": dados["resumo"]["perguntas_respostas"],
            "exemplos_copy": dados["resumo"]["exemplos_copy"]
        }
    }
    
    if return_bytes:
        json_str = json.dumps(dados_json, ensure_ascii=False, indent=4)
        return io.BytesIO(json_str.encode('utf-8'))
    else:
        caminho = f"{nome_arquivo}.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados_json, f, ensure_ascii=False, indent=4)
        return caminho
