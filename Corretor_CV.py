import os
import re
import io
import streamlit as st
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
from dotenv import load_dotenv

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT

from llama_index.llms.groq import Groq
from llama_index.llms.gemini import Gemini
from llama_index.llms.openai import OpenAI
load_dotenv()


# ============================ PDF Export ============================= #

def _strip_emojis(text: str) -> str:
    """Remove emojis e símbolos fora do range Latin/BMP que reportlab não suporta."""
    return re.sub(r'[^\x00-\x7F\u00C0-\u024F\u2000-\u206F\u2100-\u214F]', '', text)

def markdown_to_pdf_bytes(texto: str, titulo: str = "Currículo") -> bytes:
    """Converte texto markdown em PDF formatado usando reportlab."""
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()

    style_title   = ParagraphStyle("CVTitle",   parent=styles["Title"],   fontSize=16, spaceAfter=14, textColor=colors.HexColor("#1a1a2e"))
    style_h1      = ParagraphStyle("CVH1",      parent=styles["Heading1"], fontSize=13, spaceBefore=10, spaceAfter=4,  textColor=colors.HexColor("#16213e"))
    style_h2      = ParagraphStyle("CVH2",      parent=styles["Heading2"], fontSize=11, spaceBefore=8,  spaceAfter=3,  textColor=colors.HexColor("#0f3460"))
    style_h3      = ParagraphStyle("CVH3",      parent=styles["Heading3"], fontSize=10, spaceBefore=6,  spaceAfter=2,  textColor=colors.HexColor("#0f3460"))
    style_body    = ParagraphStyle("CVBody",    parent=styles["Normal"],   fontSize=10, leading=14, spaceAfter=4,  alignment=TA_LEFT)
    style_bullet  = ParagraphStyle("CVBullet",  parent=styles["Normal"],   fontSize=10, leading=14, leftIndent=16, spaceAfter=2, bulletIndent=6)

    def escape_xml(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def apply_inline(s: str) -> str:
        """Converte **negrito** e *itálico* para tags reportlab."""
        s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
        s = re.sub(r'\*(.+?)\*',     r'<i>\1</i>', s)
        s = re.sub(r'`(.+?)`',       r'<font name="Courier">\1</font>', s)
        return s

    story = []
    story.append(Paragraph(_strip_emojis(titulo), style_title))
    story.append(Spacer(1, 0.3 * cm))

    for raw_line in texto.splitlines():
        line = _strip_emojis(raw_line)

        # Headings
        if line.startswith("### "):
            story.append(Paragraph(escape_xml(line[4:].strip()), style_h3))
        elif line.startswith("## "):
            story.append(Paragraph(escape_xml(line[3:].strip()), style_h2))
        elif line.startswith("# "):
            story.append(Paragraph(escape_xml(line[2:].strip()), style_h1))

        # Separador horizontal
        elif re.match(r'^[-*_]{3,}$', line.strip()):
            story.append(Spacer(1, 0.2 * cm))

        # Bullet points (-, *, •)
        elif re.match(r'^[\-\*\•]\s+', line):
            content = re.sub(r'^[\-\*\•]\s+', '', line)
            story.append(Paragraph(apply_inline(escape_xml(content)), style_bullet, bulletText="•"))

        # Listas numeradas
        elif re.match(r'^\d+[\.\)]\s+', line):
            content = re.sub(r'^\d+[\.\)]\s+', '', line)
            story.append(Paragraph(apply_inline(escape_xml(content)), style_bullet))

        # Linha vazia
        elif line.strip() == "":
            story.append(Spacer(1, 0.15 * cm))

        # Texto normal
        else:
            story.append(Paragraph(apply_inline(escape_xml(line)), style_body))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ============================ Helpers ================================ #

def extract_text_from_pdf_bytes(pdf_bytes: bytes, max_chars: int = 200_000) -> str:
    """Extrai texto de PDF com PyMuPDF (PDFs com texto selecionável).
    sort=True garante ordem de leitura correta; limpeza remove artefatos de encoding.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts = []
    for page in doc:
        text = page.get_text("text", sort=True)
        # Remove caracteres de controle e substitui ligaduras comuns
        text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        parts.append(text)
    full_text = "\n".join(parts).strip()
    return full_text[:max_chars] if full_text else ""

def _preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """Pré-processa imagem para maximizar acurácia do OCR:
    1. Converte para escala de cinza
    2. Escala para pelo menos 2400px de largura (simula ~300 DPI)
    3. Aumenta contraste e nitidez
    """
    # 1. Escala de cinza
    img = img.convert("L")

    # 2. Upscale: garante largura mínima de 2400px para boa resolução no OCR
    min_width = 2400
    if img.width < min_width:
        scale = min_width / img.width
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    # 3. Contraste
    img = ImageEnhance.Contrast(img).enhance(2.0)

    # 4. Nitidez
    img = ImageEnhance.Sharpness(img).enhance(2.0)

    # 5. Filtro de realce de bordas (melhora letras finas)
    img = img.filter(ImageFilter.SHARPEN)

    return img

def extract_text_from_image_ocr(file_bytes: bytes, filename: str, max_chars: int = 120_000) -> str:
    """Extrai texto de imagem ou PDF escaneado via OCR (pytesseract).

    - Imagens (PNG, JPG, WEBP, BMP, TIFF): pré-processa e aplica OCR.
    - PDF: renderiza cada página em alta resolução via PyMuPDF, pré-processa e aplica OCR.
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    # oem 3 = LSTM engine (mais preciso); psm 6 = bloco de texto uniforme
    tess_config = "--oem 3 --psm 6"
    lang = "por+eng"
    parts = []

    if ext == "pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            mat = fitz.Matrix(2.5, 2.5)  # ~200 DPI base → 500 DPI efetivo
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img = _preprocess_image_for_ocr(img)
            text = pytesseract.image_to_string(img, lang=lang, config=tess_config)
            parts.append(text)
    else:
        img = Image.open(io.BytesIO(file_bytes))
        img = _preprocess_image_for_ocr(img)
        text = pytesseract.image_to_string(img, lang=lang, config=tess_config)
        parts.append(text)

    full_text = "\n".join(parts).strip()
    return full_text[:max_chars] if full_text else ""

def get_llm(model_choice: str):
    """Cria o LLM (LlamaIndex puro)."""
    if model_choice == "Gemini (gemini-2.5-flash)":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            st.error("GOOGLE_API_KEY não encontrado no .env")
            st.stop()
        return Gemini(model="models/gemini-2.5-flash")

    if model_choice == "Groq (Llama 3.3 70B)":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            st.error("GROQ_API_KEY não encontrado no .env")
            st.stop()
        return Groq(
            model="llama-3.3-70b-versatile",
            temperature=0.1,
        )

    if model_choice == "ChatGPT (gpt-4o-mini)":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error("OPENAI_API_KEY não encontrado no .env")
            st.stop()
        return OpenAI(
            model="gpt-4o-mini",
            temperature=0.1
        )

    st.error("Modelo inválido.")
    st.stop()

def llm_complete(llm, prompt: str) -> str:
    """Wrapper robusto para pegar o texto retornado pelo LlamaIndex."""
    resp = llm.complete(prompt)
    # Normalmente é resp.text
    text = getattr(resp, "text", None)
    if text:
        return text.strip()
    # fallback
    return str(resp).strip()

# ============================ Prompts ================================ #

def curriculum_analyser(llm, cv_content: str) -> str:
    template = """
Atue como professora especialista em gramática normativa da língua portuguesa, com experiência na revisão de currículos profissionais.

Analise cuidadosamente o texto do meu currículo com base nos seguintes critérios:
- Coesão: conexão adequada entre frases, orações e parágrafos, fluidez textual, conectivos.
- Coerência: ideias organizadas de forma lógica, sem contradições ou ambiguidades.
- Formalidade: linguagem adequada ao contexto profissional, norma culta, sem gírias/coloquialismos.
- Ortografia: erros de grafia.
- Gramática: concordância verbal/nominal, regência, pontuação, crase etc.

Para cada erro encontrado:
- Classifique a gravidade (leve, moderado ou grave).
- Apresente no formato:
  🔎 Trecho original
  ✅ Correção sugerida
  📘 Justificativa técnica

Caso o trecho esteja correto, confirme explicitamente que está adequado.

Ao final:
- Faça um resumo geral da qualidade textual do currículo.
- Dê uma nota de 0 a 10 (considerando apenas critérios linguísticos).
- Aponte sugestões estratégicas para tornar o texto mais claro, direto e profissional.

Seja técnica, objetiva e assertiva.

Currículo:
{cv}
"""
    prompt = template.format(cv=cv_content)
    return llm_complete(llm, prompt)

def CVStrategicOptimizer(llm, cv_content: str, job_description: str) -> str:
    template = """
Atue como especialista em recrutamento, sistemas ATS (Applicant Tracking Systems) e redação estratégica de currículos.
Você receberá:
1) O currículo do candidato
2) A descrição de uma vaga específica

Sua tarefa é realizar uma análise técnica e estratégica seguindo as etapas abaixo:

ETAPA 1 — Extração de Palavras-Chave (da VAGA)
Identifique palavras-chave técnicas, comportamentais e específicas do setor presentes na descrição da vaga.
Liste:
- Hard skills
- Soft skills
- Ferramentas
- Tecnologias
- Certificações
- Termos estratégicos repetidos

ETAPA 2 — Análise de Compatibilidade (CV x VAGA)
Compare o currículo com a vaga e informe:
- Palavras-chave já presentes no currículo
- Palavras-chave ausentes
- Experiências que podem ser melhor descritas para alinhar com a vaga
- Nível estimado de compatibilidade (0% a 100%) com justificativa curta

ETAPA 3 — Otimização Estratégica para ATS (SEM INVENTAR)
Gere uma versão adaptada do currículo:
- Mantendo 100% da veracidade das informações (não inventar experiências/habilidades)
- Reorganizando e reescrevendo para incluir palavras-chave relevantes
- Melhorando clareza e objetividade
- Usando verbos de ação
- Priorizando termos compatíveis com ATS
- Adequando o resumo profissional para a empresa e vaga

ETAPA 4 — Ajuste Estratégico para a Empresa
Analise o tom da vaga e adapte o currículo para:
- Cultura mais técnica, corporativa ou inovadora
- Linguagem alinhada ao perfil da empresa
- Destaque de experiências e habilidades mais relevantes para o setor e tipo de empresa
- Condense as o objetivo/resumo do candidato em uma frase estratégica, forte e profissional, mantendo suas principais qualidades que podem contribuir para a vaga e a empresa
- Seja o mais conciso possível, sem perder impacto.  

ETAPA 5 — Entrega Estruturada
Responda exatamente neste formato:
1️⃣ Palavras-chave identificadas
2️⃣ Análise de compatibilidade
3️⃣ Sugestões estratégicas de melhoria
4️⃣ Versão otimizada completa do currículo
5️⃣ Score estimado de otimização ATS (0–100) com justificativa curta

Seja técnico, estratégico e objetivo.
Não inclua elogios genéricos.
Não invente informações que não estejam no currículo.

Currículo:
{cv}

Descrição da vaga:
{job}
"""
    prompt = template.format(cv=cv_content, job=job_description)
    return llm_complete(llm, prompt)

def CVEnglishVersionGenerator(llm, cv_content: str) -> str:
    template = """
    You are a professional resume editor and English language specialist with experience in international recruiting and ATS systems.
    Your task is to convert the following resume into a **fully professional English version** suitable for international companies.
    Follow these rules carefully:

    1. Translate the entire resume into **natural, fluent, and professional English**.
    2. Preserve all factual information. **Do not invent or remove experiences.**
    3. Improve clarity, coherence, and conciseness where necessary.
    4. Use vocabulary commonly found in **international technical resumes**.
    5. Ensure the text is grammatically correct and stylistically professional.
    6. Adapt section titles to standard English resume sections, such as:
    - Professional Summary
    - Education
    - Technical Skills
    - Projects
    - Certifications
    - Languages
    7. Rewrite sentences when needed to sound **natural in English**, not like a literal translation.
    8. Use action verbs commonly used in professional resumes.
    9. Maintain a clean and structured resume format.
    10. Use concise bullet points and strong action verbs commonly used in professional resumes such as: Developed, Implemented, Designed, Built, Led, Integrated, Optimized, Automated, Analyzed.

    Important constraints:
    - Do not include explanations.
    - Do not include translation notes.
    - Output **only the final English resume**.
    - The resume must read as if it were originally written in English.

    Resume:
    {cv}
    """
    prompt = template.format(cv=cv_content)
    return llm_complete(llm, prompt)

def extrair_cv_otimizado(output: str) -> str:
    """Extrai apenas a seção 4️⃣ (versão otimizada) do output do CVStrategicOptimizer."""
    match = re.search(r'4️⃣[^\n]*\n(.*?)(?=5️⃣|\Z)', output, re.DOTALL)
    if match:
        return match.group(1).strip()
    return output  # fallback: retorna tudo se não encontrar o padrão

def extrair_cargo_da_vaga(llm, job_text: str) -> str:
    """Extrai o cargo/título da vaga a partir da descrição."""
    prompt = (
        "Extraia apenas o título/cargo da vaga do texto abaixo. "
        "Responda SOMENTE com o título, sem explicações, pontuação extra ou aspas.\n\n"
        f"Descrição da vaga:\n{job_text[:3000]}"
    )
    cargo = llm_complete(llm, prompt).strip().strip('"').strip("'")
    # Sanitiza para uso em file_name: remove caracteres inválidos
    cargo = re.sub(r'[\\/*?:"<>|]', '', cargo)
    return cargo or "Vaga"

def CVCorrigido(llm, cv_content: str, analise: str) -> str:
    """Gera o currículo com todas as correções gramaticais já aplicadas, formatado em markdown."""
    template = """
Você é uma revisora especialista em língua portuguesa.
Abaixo estão o currículo original e a análise gramatical com as correções sugeridas.

Sua tarefa: reescreva o currículo aplicando TODAS as correções indicadas na análise.
- Corrija ortografia, gramática, concordância, regência e pontuação conforme sugerido.
- Mantenha 100% das informações originais — não acrescente nem remova conteúdo.
- Preserve a estrutura e a ordem das seções do original.
- Incorpore as melhorias de clareza e formalidade sugeridas.

Formatação obrigatória (markdown):
- Use ## para o nome do candidato e ### para os títulos de cada seção (ex: ### Experiência Profissional)
- Use **negrito** para os títulos de cada seção (ex: **Contatos**,**Formação Acadêmica**, **Principais competências**) e informações de destaque como projetos
- Use bullet points (- ) para listar responsabilidades, conquistas, habilidades e atividades
- Use texto corrido apenas para resumo/objetivo profissional

Entregue APENAS o currículo corrigido e formatado, sem explicações, comentários ou marcações extras.

Currículo original:
{cv}

Análise gramatical:
{analise}
"""
    prompt = template.format(cv=cv_content, analise=analise)
    return llm_complete(llm, prompt)

def CVStrategicOptimizerEnglish(llm, cv_content: str, job_description: str) -> str:
    template = """
You are an expert in recruitment, ATS (Applicant Tracking Systems), and strategic resume writing.
You will receive:
1) The candidate's resume (already in English)
2) A job description

Your task is to produce an ATS-optimized version of the resume tailored to the job.

Rules:
- Write entirely in English.
- Keep 100% of the factual information — do not invent or remove experiences.
- Incorporate relevant keywords from the job description naturally.
- Use strong action verbs (Developed, Implemented, Led, Designed, Built, Optimized, etc.).
- Rewrite bullet points to highlight impact and alignment with the role.
- Condense the professional summary into one strong, targeted sentence.
- Use standard English resume section titles (Professional Summary, Experience, Education, Skills, etc.).
- Be concise, clear, and ATS-friendly.

Output ONLY the final optimized resume in English. Do not include analysis, scores, explanations, or any other text.

Resume:
{cv}

Job Description:
{job}
"""
    prompt = template.format(cv=cv_content, job=job_description)
    return llm_complete(llm, prompt)

def exibir_output_ats_em_abas(output: str, T: dict, pdf_bytes: bytes = None, pdf_name: str = None) -> None:
    """Divide o output do CVStrategicOptimizer em abas por etapa."""
    marcadores = {
        "1️⃣": T["tab_keywords"],
        "2️⃣": T["tab_compat"],
        "3️⃣": T["tab_suggest"],
        "4️⃣": T["tab_cv"],
        "5️⃣": T["tab_score"],
    }

    secoes = {}
    chaves = list(marcadores.keys())
    for i, emoji in enumerate(chaves):
        proximo = chaves[i + 1] if i + 1 < len(chaves) else None
        padrao = (
            rf'{re.escape(emoji)}[^\n]*\n(.*?)(?={re.escape(proximo)}|\Z)'
            if proximo
            else rf'{re.escape(emoji)}[^\n]*\n(.*)'
        )
        match = re.search(padrao, output, re.DOTALL)
        secoes[emoji] = match.group(1).strip() if match else ""

    abas = st.tabs(list(marcadores.values()))
    for aba, emoji in zip(abas, chaves):
        with aba:
            conteudo = secoes.get(emoji, "")
            if conteudo:
                st.markdown(conteudo)
            else:
                st.info(T["tab_empty"])
            if emoji == "4️⃣" and pdf_bytes and pdf_name:
                # st.divider()
                st.download_button(
                    label=T["dl_ats"],
                    data=pdf_bytes,
                    file_name=pdf_name,
                    mime="application/pdf",
                    key="dl_ats_main",
                )


# ============================ Traduções ============================ #

TEXTS = {
    "pt": {
        "page_title":           "Análise de Currículos",
        "app_title":            "Análise e adequação de Currículos 📄",
        "lang_toggle":          "🌐 Idioma / Language",
        "sidebar_model":        "Modelo (LlamaIndex)",
        "sidebar_model_label":  "Escolha o modelo:",
        "sidebar_cv":           "Currículo (PDF)",
        "sidebar_cv_upload":    "Envie o currículo (PDF):",
        "col1_title":           "1) O que você quer fazer?",
        "col2_title":           "2) Descrição da vaga",
        "select_mode":          "Selecione:",
        "mode_ats":             "Otimização estratégica para vaga específica",
        "mode_english":         "Gerar versão do currículo em inglês",
        "mode_grammar":         "Análise gramatical e de clareza",
        "job_format_label":     "Formato da vaga:",
        "job_format_text":      "Texto",
        "job_format_pdf":       "PDF",
        "job_format_ocr":       "Imagem (OCR)",
        "job_text_area":        "Cole aqui a descrição da vaga:",
        "job_pdf_upload":       "Envie a vaga (PDF):",
        "job_ocr_upload":       "Envie a imagem ou PDF escaneado da vaga:",
        "ocr_spinner":          "Extraindo texto via OCR...",
        "ocr_preview":          "Texto extraído por OCR (prévia)",
        "ocr_warning":          "Não foi possível extrair texto. Verifique se a imagem está legível.",
        "cv_preview":           "Texto extraído do currículo (prévia)",
        "job_preview":          "Texto extraído da vaga (prévia)",
        "warn_no_job":          "Para otimização ATS, você precisa fornecer a descrição da vaga (texto, PDF ou imagem).",
        "err_no_cv_text":       "Não consegui extrair texto do currículo. Se for PDF escaneado, precisará de OCR.",
        "info_upload_cv":       "Envie o currículo em PDF na barra lateral para começar.",
        "btn_ats":              "Otimizar currículo",
        "btn_english":          "Gerar versão em inglês",
        "btn_grammar":          "Executar análise",
        "spinner_main":         "Gerando resposta...",
        "spinner_corrected":    "Gerando currículo corrigido para exportação...",
        "success_done":         "Concluído ✅",
        "dl_ats":               "📥 Baixar currículo otimizado em PDF",
        "dl_english":           "📥 Baixar currículo em inglês em PDF",
        "dl_grammar":           "📥 Baixar currículo corrigido em PDF",
        "dl_english_from_ats":  "📥 Baixar versão em inglês em PDF",
        "dl_ats_english":       "📥 Baixar currículo otimizado em PDF",
        "next_english_title":   "🌐 Próximo passo",
        "next_english_info":    "Deseja gerar a versão em inglês com base no currículo **otimizado** acima?",
        "btn_gen_english_opt":  "Gerar versão em inglês do currículo otimizado",
        "success_english":      "Versão em inglês gerada ✅",
        "next_ats_title":       "🎯 Próximo passo",
        "next_ats_info":        "Deseja otimizar o currículo em inglês para uma vaga específica?",
        "btn_opt_ats":          "Otimizar para uma vaga (ATS)",
        "next_ats_fill":        "Preencha a descrição da vaga acima e clique em **Otimizar currículo em inglês para a vaga**.",
        "btn_opt_ats_en":       "Otimizar currículo em inglês para a vaga",
        "spinner_ats":          "Otimizando para ATS...",
        "success_ats_en":       "Currículo em inglês otimizado ✅",
        "warn_fill_job":        "Preencha a descrição da vaga acima para continuar.",
        "spinner_en_opt":       "Traduzindo e adaptando para o inglês...",
        "tab_keywords":         "🔑 Palavras-chave",
        "tab_compat":           "📊 Compatibilidade",
        "tab_suggest":          "💡 Sugestões",
        "tab_cv":               "📄 CV Otimizado",
        "tab_score":            "🏆 Score ATS",
        "tab_empty":            "Conteúdo não encontrado para esta etapa.",
        "pdf_title_ats":        "Currículo para",
        "pdf_title_english":    "Resume",
        "pdf_title_grammar":    "Currículo Corrigido",
        "pdf_name_grammar":     "Currículo Corrigido.pdf",
        "pdf_resume_for":       "Resume for",
    },
    "en": {
        "page_title":           "Resume Analysis",
        "app_title":            "Resume Analysis & Optimization 📄",
        "lang_toggle":          "🌐 Idioma / Language",
        "sidebar_model":        "Model (LlamaIndex)",
        "sidebar_model_label":  "Choose model:",
        "sidebar_cv":           "Resume (PDF)",
        "sidebar_cv_upload":    "Upload your resume (PDF):",
        "col1_title":           "1) What do you want to do?",
        "col2_title":           "2) Job description",
        "select_mode":          "Select:",
        "mode_ats":             "Otimização estratégica para vaga específica",
        "mode_english":         "Gerar versão do currículo em inglês",
        "mode_grammar":         "Análise gramatical e de clareza",
        "job_format_label":     "Job format:",
        "job_format_text":      "Text",
        "job_format_pdf":       "PDF",
        "job_format_ocr":       "Image (OCR)",
        "job_text_area":        "Paste the job description here:",
        "job_pdf_upload":       "Upload the job description (PDF):",
        "job_ocr_upload":       "Upload the job image or scanned PDF:",
        "ocr_spinner":          "Extracting text via OCR...",
        "ocr_preview":          "OCR extracted text (preview)",
        "ocr_warning":          "Could not extract text. Please check if the image is readable.",
        "cv_preview":           "Extracted resume text (preview)",
        "job_preview":          "Extracted job text (preview)",
        "warn_no_job":          "For ATS optimization, please provide the job description (text, PDF or image).",
        "err_no_cv_text":       "Could not extract text from the resume. If it's a scanned PDF, OCR is required.",
        "info_upload_cv":       "Upload your resume PDF in the sidebar to get started.",
        "btn_ats":              "Optimize resume",
        "btn_english":          "Generate English version",
        "btn_grammar":          "Run analysis",
        "spinner_main":         "Generating response...",
        "spinner_corrected":    "Generating corrected resume for export...",
        "success_done":         "Done ✅",
        "dl_ats":               "📥 Download optimized resume as PDF",
        "dl_english":           "📥 Download English resume as PDF",
        "dl_grammar":           "📥 Download corrected resume as PDF",
        "dl_english_from_ats":  "📥 Download English version as PDF",
        "dl_ats_english":       "📥 Download optimized resume as PDF",
        "next_english_title":   "🌐 Next step",
        "next_english_info":    "Would you like to generate the English version based on the **optimized** resume above?",
        "btn_gen_english_opt":  "Generate English version of optimized resume",
        "success_english":      "English version generated ✅",
        "next_ats_title":       "🎯 Next step",
        "next_ats_info":        "Would you like to optimize the English resume for a specific job?",
        "btn_opt_ats":          "Optimize for a job (ATS)",
        "next_ats_fill":        "Fill in the job description above and click **Optimize English resume for the job**.",
        "btn_opt_ats_en":       "Optimize English resume for the job",
        "spinner_ats":          "Optimizing for ATS...",
        "success_ats_en":       "English resume optimized ✅",
        "warn_fill_job":        "Please fill in the job description above to continue.",
        "spinner_en_opt":       "Translating and adapting to English...",
        "tab_keywords":         "🔑 Keywords",
        "tab_compat":           "📊 Compatibility",
        "tab_suggest":          "💡 Suggestions",
        "tab_cv":               "📄 Optimized Resume",
        "tab_score":            "🏆 ATS Score",
        "tab_empty":            "Content not found for this step.",
        "pdf_title_ats":        "Resume for",
        "pdf_title_english":    "Resume",
        "pdf_title_grammar":    "Corrected Resume",
        "pdf_name_grammar":     "Corrected Resume.pdf",
        "pdf_resume_for":       "Resume for",
    }
}

# ============================ UI Streamlit ============================ #

st.set_page_config(page_title="Resume Analysis / Análise de Currículos", page_icon="📄", layout="wide")

# ──────────────── Toggle de idioma (sidebar, antes de tudo) ──────────────── #
if "lang" not in st.session_state:
    st.session_state["lang"] = "pt"

with st.sidebar:
    selected_lang = st.radio(
        "🌐 Idioma / Language",
        options=["pt", "en"],
        format_func=lambda x: "🇧🇷 Português" if x == "pt" else "🇺🇸 English",
        index=0 if st.session_state["lang"] == "pt" else 1,
        horizontal=True,
        key="lang_radio",
    )
    if selected_lang != st.session_state["lang"]:
        st.session_state["lang"] = selected_lang
        st.rerun()

T = TEXTS[st.session_state["lang"]]

# Modos internos (sempre em PT, usados como chaves de comparação)
MODE_ATS     = "Otimização estratégica para vaga específica"
MODE_ENGLISH = "Gerar versão do currículo em inglês"
MODE_GRAMMAR = "Análise gramatical e de clareza"

MODE_LABELS = {
    MODE_ATS:     T["mode_ats"]     if st.session_state["lang"] == "pt" else "Strategic optimization for a specific job",
    MODE_ENGLISH: T["mode_english"] if st.session_state["lang"] == "pt" else "Generate English version of resume",
    MODE_GRAMMAR: T["mode_grammar"] if st.session_state["lang"] == "pt" else "Grammar and clarity analysis",
}

st.title(T["app_title"])

with st.sidebar:
    st.subheader(T["sidebar_model"])
    model_choice = st.selectbox(T["sidebar_model_label"], [
        "Gemini (gemini-2.5-flash)",
        "Groq (Llama 3.3 70B)",
        "ChatGPT (gpt-4o-mini)"
    ])
    llm = get_llm(model_choice)
    limit = 200_000 if "Gemini" in model_choice else 40_000

    st.subheader(T["sidebar_cv"])
    cv_file = st.file_uploader(T["sidebar_cv_upload"], type=["pdf"])

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader(T["col1_title"])
    mode = st.selectbox(
        T["select_mode"],
        options=[MODE_ATS, MODE_ENGLISH, MODE_GRAMMAR],
        format_func=lambda x: MODE_LABELS[x],
    )

# Controla se o usuário quer otimizar após gerar a versão em inglês
if "optimize_after_english" not in st.session_state:
    st.session_state["optimize_after_english"] = False

is_grammar      = mode == MODE_GRAMMAR
is_english_mode = mode == MODE_ENGLISH
job_fields_disabled = is_grammar or (is_english_mode and not st.session_state["optimize_after_english"])

JOB_FORMAT_OPTIONS = [T["job_format_text"], T["job_format_pdf"], T["job_format_ocr"]]

with col2:
    st.subheader(T["col2_title"])
    job_input_type = st.selectbox(
        T["job_format_label"],
        JOB_FORMAT_OPTIONS,
        disabled=job_fields_disabled,
        key="job_input_type",
    )

# inicializando a variável que vai armazenar o texto da vaga
job_text = ""

if job_input_type == T["job_format_text"]:
    job_text = st.text_area(
        T["job_text_area"],
        height=220,
        key="job_text",
        disabled=job_fields_disabled,
    )
elif job_input_type == T["job_format_pdf"]:
    job_pdf = st.file_uploader(
        T["job_pdf_upload"],
        type=["pdf"],
        key="jobpdf",
        disabled=job_fields_disabled,
    )
    if job_pdf:
        job_text = extract_text_from_pdf_bytes(job_pdf.read(), max_chars=120_000)
else:
    if not job_fields_disabled:
        job_ocr_file = st.file_uploader(
            T["job_ocr_upload"],
            type=["png", "jpg", "jpeg", "webp", "bmp", "tiff", "pdf"],
            key="job_ocr",
            disabled=job_fields_disabled,
        )
        if job_ocr_file:
            with st.spinner(T["ocr_spinner"]):
                job_text = extract_text_from_image_ocr(
                    job_ocr_file.read(),
                    job_ocr_file.name,
                    max_chars=120_000,
                )
            if job_text:
                with st.expander(T["ocr_preview"]):
                    st.write(job_text[:2000] + ("..." if len(job_text) > 2000 else ""))
            else:
                st.warning(T["ocr_warning"])

# Reseta ats_output e derivados sempre que uma nova descrição de vaga for detectada
if job_text.strip():
    last_job = st.session_state.get("last_job_text", "")
    if job_text.strip() != last_job:
        st.session_state["last_job_text"] = job_text.strip()
        for key in ["ats_output", "ats_pdf_bytes", "ats_pdf_name",
                    "cargo_da_vaga", "english_output_optimized",
                    "english_output_optimized_pdf", "english_output_optimized_pdf_name"]:
            st.session_state.pop(key, None)

st.divider()

# ============================ Execução ============================ #

if cv_file:
    cv_content = extract_text_from_pdf_bytes(cv_file.read(), max_chars=limit)

    if not cv_content:
        st.error(T["err_no_cv_text"])
        st.stop()

    with st.expander(T["cv_preview"]):
        st.write(cv_content[:4000] + ("..." if len(cv_content) > 4000 else ""))

    if mode == MODE_ATS:
        if not job_text.strip():
            st.warning(T["warn_no_job"])
            st.stop()
        with st.expander(T["job_preview"]):
            st.write(job_text[:4000] + ("..." if len(job_text) > 4000 else ""))

    btn_labels = {
        MODE_ATS:     T["btn_ats"],
        MODE_ENGLISH: T["btn_english"],
        MODE_GRAMMAR: T["btn_grammar"],
    }

    if st.button(btn_labels[mode], type="primary"):
        with st.spinner(T["spinner_main"]):
            if mode == MODE_ATS:
                output = CVStrategicOptimizer(llm, cv_content, job_text)
                cargo  = extrair_cargo_da_vaga(llm, job_text)
                cv_para_pdf = extrair_cv_otimizado(output)
                pdf_bytes   = markdown_to_pdf_bytes(cv_para_pdf, f"{T['pdf_title_ats']} {cargo}")
                st.session_state["ats_output"]    = output
                st.session_state["cargo_da_vaga"] = cargo
                st.session_state["ats_pdf_bytes"] = pdf_bytes
                st.session_state["ats_pdf_name"]  = f"{T['pdf_title_ats']} {cargo}.pdf"

            elif mode == MODE_ENGLISH:
                output    = CVEnglishVersionGenerator(llm, cv_content)
                pdf_bytes = markdown_to_pdf_bytes(output, T["pdf_title_english"])
                st.session_state["english_output"]     = output
                st.session_state["english_pdf_bytes"]  = pdf_bytes
                st.session_state["optimize_after_english"] = False

            else:
                output       = curriculum_analyser(llm, cv_content)
                cv_corrigido = CVCorrigido(llm, cv_content, output)
                pdf_bytes    = markdown_to_pdf_bytes(cv_corrigido, T["pdf_title_grammar"])
                st.session_state["grammar_output"]    = output
                st.session_state["grammar_pdf_bytes"] = pdf_bytes

    # ──────────────── Renderização fora do botão (persiste após download) ──────────────── #
    if mode == MODE_ATS and "ats_output" in st.session_state:
        st.success(T["success_done"])
        exibir_output_ats_em_abas(
            st.session_state["ats_output"],
            T,
            pdf_bytes=st.session_state.get("ats_pdf_bytes"),
            pdf_name=st.session_state.get("ats_pdf_name"),
        )

    elif mode == MODE_ENGLISH and "english_output" in st.session_state:
        st.success(T["success_done"])
        st.markdown(st.session_state["english_output"])
        if "english_pdf_bytes" in st.session_state:
            st.download_button(
                label=T["dl_english"],
                data=st.session_state["english_pdf_bytes"],
                file_name="Resume.pdf",
                mime="application/pdf",
                key="dl_english_main",
            )

    elif mode == MODE_GRAMMAR and "grammar_output" in st.session_state:
        st.success(T["success_done"])
        st.markdown(st.session_state["grammar_output"])
        if "grammar_pdf_bytes" in st.session_state:
            st.download_button(
                label=T["dl_grammar"],
                data=st.session_state["grammar_pdf_bytes"],
                file_name=T["pdf_name_grammar"],
                mime="application/pdf",
                key="dl_grammar_main",
            )

    # ──────────────── Pós ATS: oferecer versão em inglês ──────────────── #
    if mode == MODE_ATS and "ats_output" in st.session_state:
        st.divider()
        st.subheader(T["next_english_title"])
        st.info(T["next_english_info"])

        if st.button(T["btn_gen_english_opt"], type="secondary"):
            with st.spinner(T["spinner_en_opt"]):
                eng_opt = CVEnglishVersionGenerator(llm, st.session_state["ats_output"])
            cargo     = st.session_state.get("cargo_da_vaga", "Vaga")
            pdf_bytes = markdown_to_pdf_bytes(eng_opt, f"{T['pdf_resume_for']} {cargo}")
            st.session_state["english_output_optimized"]          = eng_opt
            st.session_state["english_output_optimized_pdf"]      = pdf_bytes
            st.session_state["english_output_optimized_pdf_name"] = f"{T['pdf_resume_for']} {cargo}.pdf"

        if "english_output_optimized" in st.session_state:
            st.success(T["success_english"])
            st.markdown(st.session_state["english_output_optimized"])
            st.download_button(
                label=T["dl_english_from_ats"],
                data=st.session_state["english_output_optimized_pdf"],
                file_name=st.session_state["english_output_optimized_pdf_name"],
                mime="application/pdf",
                key="dl_english_from_ats",
            )

    # ──────────────── Pós Inglês: oferecer otimização ATS ──────────────── #
    if mode == MODE_ENGLISH and "english_output" in st.session_state:
        st.divider()
        st.subheader(T["next_ats_title"])

        if not st.session_state["optimize_after_english"]:
            st.info(T["next_ats_info"])
            if st.button(T["btn_opt_ats"], type="secondary"):
                st.session_state["optimize_after_english"] = True
                st.rerun()
        else:
            st.info(T["next_ats_fill"])
            if job_text.strip():
                if st.button(T["btn_opt_ats_en"], type="primary"):
                    with st.spinner(T["spinner_ats"]):
                        ats_english_output = CVStrategicOptimizerEnglish(
                            llm, st.session_state["english_output"], job_text
                        )
                    cargo     = extrair_cargo_da_vaga(llm, job_text)
                    pdf_bytes = markdown_to_pdf_bytes(ats_english_output, f"{T['pdf_resume_for']} {cargo}")
                    st.session_state["ats_english_output"]    = ats_english_output
                    st.session_state["ats_english_pdf"]       = pdf_bytes
                    st.session_state["ats_english_pdf_name"]  = f"{T['pdf_resume_for']} {cargo}.pdf"

                if "ats_english_output" in st.session_state:
                    st.success(T["success_ats_en"])
                    st.markdown(st.session_state["ats_english_output"])
                    st.download_button(
                        label=T["dl_ats_english"],
                        data=st.session_state["ats_english_pdf"],
                        file_name=st.session_state["ats_english_pdf_name"],
                        mime="application/pdf",
                        key="dl_ats_english",
                    )
            else:
                st.warning(T["warn_fill_job"])

else:
    st.info(T["info_upload_cv"])