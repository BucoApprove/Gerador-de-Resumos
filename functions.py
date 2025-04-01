from openai import OpenAI
from moviepy.editor import AudioFileClip
import json
import os
import math
from datetime import datetime
import io

def get_openai_client(api_key):
    return OpenAI(api_key=api_key)

def dividir_audio_em_chunks(arquivo_audio, duracao_maxima=180):
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

def gerar_resumo(transcricao, client, model):
    prompt = f"""
    Resuma o seguinte texto em um formato estruturado, transformando-o em algo prático e descontraído para um assistente de IA que fala a língua do dia a dia. Foque nos exemplos práticos da transcrição, trazendo tudo de forma completa e detalhada, sem deixar nada de fora:

    ### Estrutura Obrigatória ###
    1) Pontos principais em formato de tópicos detalhados:
    2) Resumo prático e completo da transcrição:
    3) Perguntas e respostas baseadas no texto:
    4) Exemplos de copy:

    ### Instruções Detalhadas ###
    1) Liste os 12 pontos principais em tópicos detalhados, com um tom informal e foco nos exemplos práticos, incluindo:
        - Introdução (na voz do professor, como se fosse um papo solto) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Conceito Principal (explicado de forma simples e direta) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Técnicas Ensinadas (dando destaque pros exemplos da aula) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - O Melhor Exemplo Dado na Aula (escreva o exemplo todinho, com detalhes) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Como Aplicar Isso em Copywriting (um guia prático, tipo receita de bolo) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Frases-Chave do Professor (as pérolas que ele soltou, com contexto) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Gatilhos Mentais Usados na Aula (explicados de um jeito fácil, com exemplos) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Padrões e Estruturas de Copy que Rolam (mostre como funcionam na prática) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Conceitos-Chave pra Convencer (foco em como usar, não só teoria) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Frases de Impacto Criadas na Aula (traga todas, com explicação) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Dúvidas e Objeções que o Professor Resolveu (com as respostas na lata) (OBRIGATÓRIAMENTE Mínimo 300 palavras)
        - Desafios e Exercícios da Aula (descreva como fazer, passo a passo) (OBRIGATÓRIAMENTE Mínimo 300 palavras)

    2) Faça um resumo prático e completo da transcrição, contando a história da aula de um jeito solto, com foco nos exemplos práticos e nas sacadas que rolaram. Nada de linguagem técnica complicada, só o que dá pra usar no dia a dia. (Tem que ter OBRIGATÓRIAMENTE NO MÍNIMO 3000 palavras e cobrir pelo menos 80% do que foi dito na transcrição.)

    3) Crie 3-5 perguntas e respostas baseadas no texto, misturando perguntas práticas e curiosidades simples. Responda de forma descontraída e completa, como se fosse uma conversa. (Cada resposta com no mínimo 250 palavras.)

    4) Com base em tudo isso (tópicos, resumo e perguntas/respostas), crie 3 copies de exemplo, com tom informal e prático:
       - Um focado em residência bucomaxilofacial (pra vender a ideia de um jeito leve)
       - Dois com temas variados ligados ao conteúdo (bem criativos e úteis)

    ### Instruções Adicionais sobre Extensão ###
    - Esse é um resumo EXTENSO e descontraído. Use pelo menos 70% do limite de tokens disponível.
    - Cada tópico principal tem que ter no mínimo 300 palavras, com foco nos exemplos práticos.
    - O resumo prático precisa ter OBRIGATÓRIAMENTE NO MÍNIMO 3000 palavras e pegar pelo menos 80% do conteúdo da transcrição.
    - Cada resposta das perguntas tem que ter no mínimo 250 palavras, num papo leve e direto.

    ### Texto para Resumir ###
    {transcricao}

    ### Formato de Resposta ###
    Responda só com as seções numeradas, sem enrolação fora delas. Cada seção tem que vir recheada de conteúdo, nada de títulos pelados. NÃO inclua nenhuma seção chamada 'Resumo técnico', apenas 'Resumo prático e completo da transcrição'.
    """
    resposta = client.chat.completions.create(
        model=model,  # Usa o modelo escolhido pelo usuário
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16000,
        temperature=0.9,
        top_p=0.9
    )
    texto_resumo = resposta.choices[0].message.content

    secoes = {
        "pontos_principais": "",
        "resumo_pratico": "",
        "perguntas_respostas": "",
        "exemplos_copy": ""
    }
    
    linhas = texto_resumo.split("\n")
    secao_atual = None
    
    for i, linha in enumerate(linhas):
        linha_strip = linha.strip()
        
        if "1) Pontos principais em formato de tópicos detalhados" in linha_strip:
            secao_atual = "pontos_principais"
            continue
        elif "2) Resumo prático e completo da transcrição" in linha_strip:
            secao_atual = "resumo_pratico"
            continue
        elif "3) Perguntas e respostas baseadas no texto" in linha_strip:
            secao_atual = "perguntas_respostas"
            continue
        elif "4) Exemplos de copy" in linha_strip:
            secao_atual = "exemplos_copy"
            continue
        
        if secao_atual and linha_strip:
            secoes[secao_atual] += linha + "\n"
    
    for chave in secoes:
        secoes[chave] = secoes[chave].strip()
        if not secoes[chave]:
            secoes[chave] = f"Conteúdo não gerado para a seção '{chave}'."

    return secoes

def ajustar_resumo(historico, instrucao_usuario, client, model):
    historico_texto = "\n\n".join([f"{msg['role'].upper()}: {msg['content'] if isinstance(msg['content'], str) else json.dumps(msg['content'])}" for msg in historico])

    resumo_anterior = None
    for mensagem in reversed(historico):
        if mensagem["role"] == "assistant" and isinstance(mensagem["content"], dict):
            resumo_anterior = mensagem["content"]
            break
    
    if not resumo_anterior:
        resumo_anterior = {
            "pontos_principais": "Resumo original não encontrado.",
            "resumo_pratico": "Resumo original não encontrado.",
            "perguntas_respostas": "Resumo original não encontrado.",
            "exemplos_copy": "Resumo original não encontrado."
        }

    prompt = f"""
    Aqui está o histórico completo de interações:

    {historico_texto}

    Aqui está o resumo mais recente a ser ajustado:
    1) Pontos principais em formato de tópicos detalhados:
    {resumo_anterior['pontos_principais']}

    2) Resumo prático e completo da transcrição:
    {resumo_anterior['resumo_pratico']}

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
        model=model,  # Usa o modelo escolhido pelo usuário
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16000,
        temperature=0.9,
        top_p=0.9
    )
    texto_resumo = resposta.choices[0].message.content

    secoes = {
        "pontos_principais": "",
        "resumo_pratico": "",
        "perguntas_respostas": "",
        "exemplos_copy": ""
    }
    linhas = texto_resumo.split("\n")
    secao_atual = None
    
    for linha in linhas:
        linha_strip = linha.strip()
        if linha_strip.startswith("1) Pontos principais em formato de tópicos detalhados:"):
            secao_atual = "pontos_principais"
            continue
        elif linha_strip.startswith("2) Resumo prático e completo da transcrição:"):
            secao_atual = "resumo_pratico"
            continue
        elif linha_strip.startswith("3) Perguntas e respostas baseadas no texto:"):
            secao_atual = "perguntas_respostas"
            continue
        elif linha_strip.startswith("4) Exemplos de copy:"):
            secao_atual = "exemplos_copy"
            continue
        elif secao_atual and linha_strip:
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
            "resumo_pratico": dados["resumo"]["resumo_pratico"],
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
