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

    style_title  = ParagraphStyle("CVTitle",  parent=styles["Title"],   fontSize=16, spaceAfter=14, textColor=colors.HexColor("#1a1a2e"))
    style_h1     = ParagraphStyle("CVH1",     parent=styles["Heading1"], fontSize=13, spaceBefore=10, spaceAfter=4,  textColor=colors.HexColor("#16213e"))
    style_h2     = ParagraphStyle("CVH2",     parent=styles["Heading2"], fontSize=11, spaceBefore=8,  spaceAfter=3,  textColor=colors.HexColor("#0f3460"))
    style_h3     = ParagraphStyle("CVH3",     parent=styles["Heading3"], fontSize=10, spaceBefore=6,  spaceAfter=2,  textColor=colors.HexColor("#0f3460"))
    style_body   = ParagraphStyle("CVBody",   parent=styles["Normal"],   fontSize=10, leading=14, spaceAfter=4,  alignment=TA_LEFT)
    style_bullet = ParagraphStyle("CVBullet", parent=styles["Normal"],   fontSize=10, leading=14, leftIndent=16, spaceAfter=2, bulletIndent=6)

    def escape_xml(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def apply_inline(s: str) -> str:
        s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
        s = re.sub(r'\*(.+?)\*',     r'<i>\1</i>', s)
        s = re.sub(r'`(.+?)`',       r'<font name="Courier">\1</font>', s)
        return s

    story = []
    story.append(Paragraph(_strip_emojis(titulo), style_title))
    story.append(Spacer(1, 0.3 * cm))

    for raw_line in texto.splitlines():
        line = _strip_emojis(raw_line)

        if line.startswith("### "):
            story.append(Paragraph(escape_xml(line[4:].strip()), style_h3))
        elif line.startswith("## "):
            story.append(Paragraph(escape_xml(line[3:].strip()), style_h2))
        elif line.startswith("# "):
            story.append(Paragraph(escape_xml(line[2:].strip()), style_h1))
        elif re.match(r'^[-*_]{3,}$', line.strip()):
            story.append(Spacer(1, 0.2 * cm))
        elif re.match(r'^[\-\*\•]\s+', line):
            content = re.sub(r'^[\-\*\•]\s+', '', line)
            story.append(Paragraph(apply_inline(escape_xml(content)), style_bullet, bulletText="•"))
        elif re.match(r'^\d+[\.\)]\s+', line):
            content = re.sub(r'^\d+[\.\)]\s+', '', line)
            story.append(Paragraph(apply_inline(escape_xml(content)), style_bullet))
        elif line.strip() == "":
            story.append(Spacer(1, 0.15 * cm))
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
        # Substitui ligaduras Unicode comuns que confundem o LLM
        text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
        # Remove caracteres de controle que poluem o texto
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        parts.append(text)
    full_text = "\n".join(parts).strip()
    return full_text[:max_chars] if full_text else ""

def _preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """Pré-processa imagem para maximizar acurácia do OCR:
    1. Converte para escala de cinza
    2. Escala para pelo menos 2400px de largura (~300 DPI efetivo)
    3. Aumenta contraste e nitidez
    """
    # 1. Escala de cinza
    img = img.convert("L")

    # 2. Upscale: garante largura mínima de 2400px
    min_width = 2400
    if img.width < min_width:
        scale = min_width / img.width
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    # 3. Contraste
    img = ImageEnhance.Contrast(img).enhance(2.0)

    # 4. Nitidez
    img = ImageEnhance.Sharpness(img).enhance(2.0)

    # 5. Realce de bordas (melhora letras finas)
    img = img.filter(ImageFilter.SHARPEN)

    return img

def extract_text_from_image_ocr(file_bytes: bytes, filename: str, max_chars: int = 120_000) -> str:
    """Extrai texto de imagem ou PDF escaneado via OCR (pytesseract).

    - Imagens (PNG, JPG, WEBP, BMP, TIFF): pré-processa e aplica OCR.
    - PDF: renderiza cada página em alta resolução via PyMuPDF, pré-processa e aplica OCR.
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    tess_config = "--oem 3 --psm 6"  # oem 3 = LSTM; psm 6 = bloco de texto uniforme
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
        return Groq(model="llama-3.3-70b-versatile", temperature=0.1)

    if model_choice == "ChatGPT (gpt-4o-mini)":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error("OPENAI_API_KEY não encontrado no .env")
            st.stop()
        return OpenAI(model="gpt-4o-mini", temperature=0.1)

    st.error("Modelo inválido.")
    st.stop()

def llm_complete(llm, prompt: str) -> str:
    """Wrapper robusto para pegar o texto retornado pelo LlamaIndex."""
    resp = llm.complete(prompt)
    text = getattr(resp, "text", None)
    if text:
        return text.strip()
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
    return output

def extrair_cargo_da_vaga(llm, job_text: str) -> str:
    """Extrai o cargo/título da vaga a partir da descrição."""
    prompt = (
        "Extraia apenas o título/cargo da vaga do texto abaixo. "
        "Responda SOMENTE com o título, sem explicações, pontuação extra ou aspas.\n\n"
        f"Descrição da vaga:\n{job_text[:3000]}"
    )
    cargo = llm_complete(llm, prompt).strip().strip('"').strip("'")
    cargo = re.sub(r'[\\/*?:"<>|]', '', cargo)
    return cargo or "Vaga"

def CVCorrigido(llm, cv_content: str, analise: str) -> str:
    """Gera o currículo com todas as correções gramaticais já aplicadas."""
    template = """
Você é uma revisora especialista em língua portuguesa.
Abaixo estão o currículo original e a análise gramatical com as correções sugeridas.

Sua tarefa: reescreva o currículo aplicando TODAS as correções indicadas na análise.
- Corrija ortografia, gramática, concordância, regência e pontuação conforme sugerido.
- Mantenha 100% das informações originais — não acrescente nem remova conteúdo.
- Preserve a estrutura e formatação original (seções, ordem, etc.).
- Incorpore as melhorias de clareza e formalidade sugeridas.

Entregue APENAS o currículo corrigido, sem explicações, comentários ou marcações.

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

def exibir_output_ats_em_abas(output: str, pdf_bytes: bytes = None, pdf_name: str = None) -> None:
    """Divide o output do CVStrategicOptimizer em abas por etapa."""
    marcadores = {
        "1️⃣": "🔑 Palavras-chave",
        "2️⃣": "📊 Compatibilidade",
        "3️⃣": "💡 Sugestões",
        "4️⃣": "📄 CV Otimizado",
        "5️⃣": "🏆 Score ATS",
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
                st.info("Conteúdo não encontrado para esta etapa.")
            if emoji == "4️⃣" and pdf_bytes and pdf_name:
                st.divider()
                st.download_button(
                    label="📥 Baixar currículo otimizado em PDF",
                    data=pdf_bytes,
                    file_name=pdf_name,
                    mime="application/pdf",
                    key="dl_ats_main",
                )


# ============================ UI Streamlit ============================ #

st.set_page_config(page_title="Análise de Currículos", page_icon="📄", layout="wide")
st.title("Análise e adequação de Currículos 📄")

with st.sidebar:
    st.subheader("Modelo (LlamaIndex)")
    model_choice = st.selectbox("Escolha o modelo:", [
        "Gemini (gemini-2.5-flash)",
        "Groq (Llama 3.3 70B)",
        "ChatGPT (gpt-4o-mini)"
    ])
    llm = get_llm(model_choice)
    limit = 200_000 if "Gemini" in model_choice else 40_000

    st.subheader("Currículo (PDF)")
    cv_file = st.file_uploader("Envie o currículo (PDF):", type=["pdf"])

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("1) O que você quer fazer?")
    mode = st.selectbox(
        "Selecione:",
        ["Otimização estratégica para vaga específica",
         "Gerar versão do currículo em inglês",
         "Análise gramatical e de clareza"]
    )

# Controla se o usuário quer otimizar após gerar a versão em inglês
if "optimize_after_english" not in st.session_state:
    st.session_state["optimize_after_english"] = False

# Campos de vaga ficam desabilitados quando:
# - modo é "Análise gramatical" OU
# - modo é "Gerar versão em inglês" E o usuário ainda NÃO pediu otimização posterior
is_grammar      = mode == "Análise gramatical e de clareza"
is_english_mode = mode == "Gerar versão do currículo em inglês"
job_fields_disabled = is_grammar or (is_english_mode and not st.session_state["optimize_after_english"])

with col2:
    st.subheader("2) Descrição da vaga")
    job_input_type = st.selectbox(
        "Formato da vaga:", ["Texto", "PDF", "Imagem (OCR)"],
        disabled=job_fields_disabled,
        key="job_input_type",
    )

# inicializando a variável que vai armazenar o texto da vaga
job_text = ""

if job_input_type == "Texto":
    job_text = st.text_area(
        "Cole aqui a descrição da vaga:",
        height=220,
        key="job_text",
        disabled=job_fields_disabled,
    )
elif job_input_type == "PDF":
    job_pdf = st.file_uploader(
        "Envie a vaga (PDF):",
        type=["pdf"],
        key="jobpdf",
        disabled=job_fields_disabled,
    )
    if job_pdf:
        job_text = extract_text_from_pdf_bytes(job_pdf.read(), max_chars=120_000)
else:
    if not job_fields_disabled:
        job_ocr_file = st.file_uploader(
            "Envie a imagem ou PDF escaneado da vaga:",
            type=["png", "jpg", "jpeg", "webp", "bmp", "tiff", "pdf"],
            key="job_ocr",
            disabled=job_fields_disabled,
        )
        if job_ocr_file:
            with st.spinner("Extraindo texto via OCR..."):
                job_text = extract_text_from_image_ocr(
                    job_ocr_file.read(),
                    job_ocr_file.name,
                    max_chars=120_000,
                )
            if job_text:
                with st.expander("Texto extraído por OCR (prévia)"):
                    st.write(job_text[:2000] + ("..." if len(job_text) > 2000 else ""))
            else:
                st.warning("Não foi possível extrair texto. Verifique se a imagem está legível.")

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
        st.error("Não consegui extrair texto do currículo. Se for PDF escaneado, precisará de OCR.")
        st.stop()

    with st.expander("Texto extraído do currículo (prévia)"):
        st.write(cv_content[:4000] + ("..." if len(cv_content) > 4000 else ""))

    if mode == "Otimização estratégica para vaga específica":
        if not job_text.strip():
            st.warning("Para otimização ATS, você precisa fornecer a descrição da vaga (texto ou PDF).")
            st.stop()
        with st.expander("Texto extraído da vaga (prévia)"):
            st.write(job_text[:4000] + ("..." if len(job_text) > 4000 else ""))

    btn_labels = {
        "Otimização estratégica para vaga específica": "Otimizar currículo",
        "Gerar versão do currículo em inglês":         "Gerar versão em inglês",
        "Análise gramatical e de clareza":             "Executar análise",
    }

    if st.button(btn_labels[mode], type="primary"):
        with st.spinner("Gerando resposta..."):
            if mode == "Otimização estratégica para vaga específica":
                output = CVStrategicOptimizer(llm, cv_content, job_text)
                cargo  = extrair_cargo_da_vaga(llm, job_text)
                cv_para_pdf = extrair_cv_otimizado(output)
                pdf_bytes   = markdown_to_pdf_bytes(cv_para_pdf, f"Currículo para {cargo}")
                st.session_state["ats_output"]    = output
                st.session_state["cargo_da_vaga"] = cargo
                st.session_state["ats_pdf_bytes"] = pdf_bytes
                st.session_state["ats_pdf_name"]  = f"Currículo para {cargo}.pdf"

            elif mode == "Gerar versão do currículo em inglês":
                output    = CVEnglishVersionGenerator(llm, cv_content)
                pdf_bytes = markdown_to_pdf_bytes(output, "Resume")
                st.session_state["english_output"]    = output
                st.session_state["english_pdf_bytes"] = pdf_bytes
                st.session_state["optimize_after_english"] = False

            else:
                output       = curriculum_analyser(llm, cv_content)
                cv_corrigido = CVCorrigido(llm, cv_content, output)
                pdf_bytes    = markdown_to_pdf_bytes(cv_corrigido, "Currículo Corrigido")
                st.session_state["grammar_output"]    = output
                st.session_state["grammar_pdf_bytes"] = pdf_bytes

    # ─────────────────────  Renderização fora do botão (persiste após download) ───────────────────── #
    if mode == "Otimização estratégica para vaga específica" and "ats_output" in st.session_state:
        st.success("Concluído ✅")
        exibir_output_ats_em_abas(
            st.session_state["ats_output"],
            pdf_bytes=st.session_state.get("ats_pdf_bytes"),
            pdf_name=st.session_state.get("ats_pdf_name"),
        )

    elif mode == "Gerar versão do currículo em inglês" and "english_output" in st.session_state:
        st.success("Concluído ✅")
        st.markdown(st.session_state["english_output"])
        if "english_pdf_bytes" in st.session_state:
            st.download_button(
                label="📥 Baixar currículo em inglês em PDF",
                data=st.session_state["english_pdf_bytes"],
                file_name="Resume.pdf",
                mime="application/pdf",
                key="dl_english_main",
            )

    elif mode == "Análise gramatical e de clareza" and "grammar_output" in st.session_state:
        st.success("Concluído ✅")
        st.markdown(st.session_state["grammar_output"])
        if "grammar_pdf_bytes" in st.session_state:
            st.download_button(
                label="📥 Baixar currículo corrigido em PDF",
                data=st.session_state["grammar_pdf_bytes"],
                file_name="Currículo Corrigido.pdf",
                mime="application/pdf",
                key="dl_grammar_main",
            )

    # ─────────────────────  Pós ATS: oferecer versão em inglês ───────────────────── #
    if mode == "Otimização estratégica para vaga específica" and "ats_output" in st.session_state:
        st.divider()
        st.subheader("🌐 Próximo passo")
        st.info("Deseja gerar a versão em inglês com base no currículo **otimizado** acima?")

        if st.button("Gerar versão em inglês do currículo otimizado", type="secondary"):
            with st.spinner("Traduzindo e adaptando para o inglês..."):
                eng_opt = CVEnglishVersionGenerator(llm, st.session_state["ats_output"])
            cargo     = st.session_state.get("cargo_da_vaga", "Vaga")
            pdf_bytes = markdown_to_pdf_bytes(eng_opt, f"Resume for {cargo}")
            st.session_state["english_output_optimized"]          = eng_opt
            st.session_state["english_output_optimized_pdf"]      = pdf_bytes
            st.session_state["english_output_optimized_pdf_name"] = f"Resume for {cargo}.pdf"

        if "english_output_optimized" in st.session_state:
            st.success("Versão em inglês gerada ✅")
            st.markdown(st.session_state["english_output_optimized"])
            st.download_button(
                label="📥 Baixar versão em inglês em PDF",
                data=st.session_state["english_output_optimized_pdf"],
                file_name=st.session_state["english_output_optimized_pdf_name"],
                mime="application/pdf",
                key="dl_english_from_ats",
            )

    # ───────────────────── Pós Inglês: oferecer otimização ATS ───────────────────── #
    if mode == "Gerar versão do currículo em inglês" and "english_output" in st.session_state:
        st.divider()
        st.subheader("🎯 Próximo passo")

        if not st.session_state["optimize_after_english"]:
            st.info("Deseja otimizar o currículo em inglês para uma vaga específica?")
            if st.button("Otimizar para uma vaga (ATS)", type="secondary"):
                st.session_state["optimize_after_english"] = True
                st.rerun()
        else:
            st.info("Preencha a descrição da vaga acima e clique em **Otimizar currículo em inglês para a vaga**.")

            if job_text.strip():
                if st.button("Otimizar currículo em inglês para a vaga", type="primary"):
                    with st.spinner("Otimizando para ATS..."):
                        ats_english_output = CVStrategicOptimizerEnglish(
                            llm, st.session_state["english_output"], job_text
                        )
                    cargo     = extrair_cargo_da_vaga(llm, job_text)
                    pdf_bytes = markdown_to_pdf_bytes(ats_english_output, f"Resume for {cargo}")
                    st.session_state["ats_english_output"]   = ats_english_output
                    st.session_state["ats_english_pdf"]      = pdf_bytes
                    st.session_state["ats_english_pdf_name"] = f"Resume for {cargo}.pdf"

                if "ats_english_output" in st.session_state:
                    st.success("Currículo em inglês otimizado ✅")
                    st.markdown(st.session_state["ats_english_output"])
                    st.download_button(
                        label="📥 Baixar currículo otimizado em PDF",
                        data=st.session_state["ats_english_pdf"],
                        file_name=st.session_state["ats_english_pdf_name"],
                        mime="application/pdf",
                        key="dl_ats_english",
                    )
            else:
                st.warning("Preencha a descrição da vaga acima para continuar.")

else:
    st.info("Envie o currículo em PDF na barra lateral para começar.")