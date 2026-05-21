# Corretor e otimizador de Currículos

Plataforma inteligente de otimização de currículos com análise linguística utilizando LLMs, reescrita orientada por vaga e geração de versão em inglês. Com foco em aumentar a aderência a vagas específicas e maximizar a performance em sistemas de recrutamento automatizados ATS (Applicant Tracking Systems).

**Objetivo**: Resolver um problema real do mercado

> Bons currículos frequentemente não passam em ATS por falta de alinhamento com palavras-chave, estrutura e contexto da vaga.

A aplicação permite transformar um currículo comum em uma versão:
- mais estratégica
- mais alinhada à vaga
- otimizada para sistemas automatizados
- pronta para mercado internacional

> **Note on language:** The sidebar toggle changes the interface language only. All AI-generated analysis and optimization outputs are produced in Brazilian Portuguese, as this tool is designed for PT-BR resumes. The "Generate English version" feature translates the *resume content itself* — it is independent of the interface language setting.

---

## Principais funcionalidades

### 1. Análise linguística profissional
- Avaliação de:
  - Coesão e coerência
  - Gramática e ortografia
  - Formalidade profissional
- Classificação de erros por gravidade
- Feedback estruturado com justificativa técnica
- Exportação do currículo já corrigido em PDF

---

### 2. Otimização estratégica para vagas
- Extração automática de palavras-chave da vaga:
  - Hard skills, soft skills, ferramentas e tecnologias
- Análise comparativa CV vs vaga:
  - Palavras presentes vs ausentes e identificação de gaps
- Reescrita estratégica:
  - Inclusão de keywords, uso de verbos de ação, estrutura otimizada para ATS
  - Sem inventar informações
- Visualização em abas:
  - 🔑 Palavras-chave | 📊 Compatibilidade | 💡 Sugestões | 📄 Currículo otimizado | 🏆 Score ATS
- Exportação em PDF com nome dinâmico baseado no cargo da vaga

---

### 3. Geração de Versão em Inglês
- Tradução profissional (não literal)
- Adequação para mercado internacional
- Uso de padrões globais de currículo
- Linguagem natural e fluente
- Estrutura compatível com recrutadores internacionais

---

### 4. OCR para descrição de vagas
- Extração de texto a partir de imagens (PNG, JPG, JPEG, WEBP, BMP, TIFF) e PDFs escaneados
- Pré-processamento automático da imagem antes do OCR:
  - Conversão para escala de cinza
  - Upscale para resolução mínima de 2400px
  - Aumento de contraste e nitidez
- Suporte multilíngue: português + inglês (`por+eng`)
- Motor LSTM (`--oem 3`) para maior precisão
- Prévia do texto extraído antes da execução

---

### 5. Pipeline Inteligente Multietapas

Fluxo dinâmico com controle de estado via `st.session_state`. Troca de vaga reseta automaticamente resultados anteriores.

| Ponto de entrada | Fluxo | Output |
|---|---|---|
| CV em PDF | Otimização ATS | CV otimizado + análise completa + score |
| CV otimizado | → Versão em inglês | Resume em inglês baseado na versão otimizada |
| CV em PDF | Versão em inglês | Resume traduzido profissionalmente |
| Resume em inglês | → Otimização ATS | Resume otimizado diretamente em inglês |
| CV em PDF | Análise gramatical | Relatório detalhado + CV corrigido para download |

---

### 6. Exportação Profissional em PDF
- Geração em memória com `reportlab` (sem arquivos temporários)
- Layout estruturado com suporte a headings, negrito, itálico e bullet points
- Nome do arquivo dinâmico baseado no cargo extraído da vaga:
  - `Currículo para {cargo}.pdf`
  - `Resume for {cargo}.pdf`
  - `Currículo Corrigido.pdf`
- Botão de download persistente (não desaparece ao clicar)

---

### 7. Interface bilíngue (PT/EN)
- Toggle na sidebar para alternar entre 🇧🇷 Português e 🇺🇸 English
- Traduz títulos, labels, botões e mensagens da interface
- Idioma da interface é independente do idioma dos outputs gerados pelo LLM

---

### 8. Seleção de modelos por provider
- Seletor de provider na sidebar: Gemini, Groq ou ChatGPT
- Selectbox condicional de modelo exibido apenas para Gemini e ChatGPT
- Labels dos modelos Gemini traduzidos conforme o idioma da interface

---

## ⚠️ Limitações conhecidas

- **Qualidade do modelo**: modelos menos capazes (ex: Groq Llama 3.3 70B com contexto estourado, GPT-4.1 Nano) podem gerar currículos com menor coesão, perder seções do currículo original ou não seguir o formato de output esperado. Para melhores resultados, prefira o Gemini 2.5 Flash ou GPT-4o-mini.
- **Contexto limitado**: modelos com janela de contexto menor podem truncar currículos muito longos. O limite é ajustado automaticamente por modelo (200k tokens para Gemini, 40k para os demais), mas currículos extensos podem ser cortados nos modelos menores.
- **OCR em imagens de baixa qualidade**: o pré-processamento melhora significativamente a acurácia, mas imagens com baixo contraste, fontes decorativas, rotação ou ruído excessivo ainda podem gerar extrações imperfeitas. PDFs nativos (com texto selecionável) sempre produzem resultados mais precisos.
- **Extração de seções do output ATS**: a separação em abas (Palavras-chave, Compatibilidade, etc.) depende do modelo seguir o formato de entrega com os marcadores `1️⃣` a `5️⃣`. Modelos menores podem ocasionalmente desviar do formato, fazendo com que alguma aba apareça vazia.
- **Nome do arquivo PDF**: o cargo extraído da vaga é gerado pelo LLM — em vagas com descrição muito genérica ou mal formatada, o nome pode sair impreciso.

---

## 🏗️ Arquitetura do sistema

```
Input:
  ├── Currículo (PDF)
  └── Vaga (Texto / PDF / Imagem via OCR)

Pipeline:
  ├── Extração de texto
  │     ├── PyMuPDF (PDFs nativos)
  │     └── pytesseract + Pillow (imagens e PDFs escaneados)
  ├── Processamento com LLM (LlamaIndex)
  │     ├── Análise linguística
  │     ├── Extração de keywords
  │     ├── Reescrita otimizada (ATS)
  │     └── Tradução profissional
  └── Geração de output estruturado
        ├── Visualização em abas
        └── Exportação em PDF (reportlab)

Output:
  ├── Análise detalhada
  ├── Versão em inglês
  └── Currículo otimizado
```

---

## 🖥️ Tecnologias utilizadas

| Camada | Tecnologia |
|---|---|
| Interface | Streamlit |
| Orquestração de LLMs | LlamaIndex |
| LLMs | Google Gemini / Groq / OpenAI (seleção por provider + modelo) |
| Extração de PDF | PyMuPDF (fitz) |
| OCR | pytesseract + Pillow |
| Geração de PDF | reportlab |
| Configuração | python-dotenv |

### Modelos disponíveis por provider

| Provider | Modelos |
|---|---|
| Gemini (Google) | `gemini-2.5-flash` · `gemini-2.5-pro` · `gemini-2.0-flash` |
| Groq | `llama-3.3-70b-versatile` |
| ChatGPT (OpenAI) | `gpt-4.1` · `gpt-4.1-mini` · `gpt-4.1-nano` · `gpt-4o` · `gpt-4o-mini` |

---

## ⚙️ Como executar o projeto

### 1. Clone o repositório

```bash
git clone <repo>
cd <repo>
```

### 2. Crie e ative o ambiente virtual

```bash
python -m venv .venv
```

Windows:
```bash
.venv\Scripts\activate
```

Mac/Linux:
```bash
source .venv/bin/activate
```

### 3. Instale as dependências do sistema (Tesseract OCR)

Linux (Ubuntu/Debian):
```bash
sudo apt install tesseract-ocr tesseract-ocr-por
```

macOS:
```bash
brew install tesseract tesseract-lang
```

**Windows:**  
Baixe o instalador em: https://github.com/UB-Mannheim/tesseract/wiki  
Após instalar, adicione ao PATH: `C:\Program Files\Tesseract-OCR`  
Em "Select components to install" clique em "Additional language data (download)" e selecione "Portuguese".

### 4. Instale as dependências Python

```bash
pip install -r requirements.txt
```

### 5. Configure as variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:
```env
GOOGLE_API_KEY=your_key
GROQ_API_KEY=your_key
OPENAI_API_KEY=your_key
```

Ou use o sistema de **secrets do Streamlit Cloud** (`Settings > Secrets`).

### 6. Execute a aplicação

```bash
streamlit run Corretor_CV.py
```

---

## ☁️ Deploy no Streamlit Cloud

O Streamlit Cloud requer um arquivo `packages.txt` na raiz do repositório para instalar dependências de sistema (como o Tesseract). O arquivo já está incluído no projeto:

```
tesseract-ocr
tesseract-ocr-por
tesseract-ocr-eng
```

Configure as chaves de API em **Settings > Secrets** no painel do Streamlit Cloud.

---

## 💡 Melhorias futuras

- **Respostas para perguntas da vaga**: gerar respostas estratégicas para perguntas dissertativas comuns em formulários de candidatura (ex: "Por que você quer trabalhar conosco?"), alinhadas ao perfil do candidato e à descrição da vaga
- **Simulação de entrevista**: modo interativo onde o LLM assume o papel de recrutador e faz perguntas técnicas e comportamentais baseadas na vaga e no currículo, com feedback sobre as respostas
- **Análise de fit cultural**: cruzar o tom e os valores descritos na vaga com o perfil do candidato para sugerir como se posicionar na candidatura
- **Suporte a mais modelos**: integração com Mistral, Claude (Anthropic) e modelos locais via Ollama
- **OCR do currículo**: permitir upload de currículos em formato de imagem ou PDF escaneado, não apenas PDFs nativos
- **Histórico de otimizações**: salvar versões anteriores do currículo e comparar evoluções entre otimizações