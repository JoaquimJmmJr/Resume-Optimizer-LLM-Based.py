# Corretor e otimizador de Currículos

Plataforma inteligente de otimização de currículos com análise linguística utilizando LLMs, reescrita orientada por vaga e geração de versão em inglês. Com foco em aumentar a aderência a vagas específicas e maximizar a performance em sistemas de recrutamento automatizados ATS (Applicant Tracking Systems).

**Objetivo**: Resolver um problema real do mercado

> Bons currículos frequentemente não passam em ATS por falta de alinhamento com palavras-chave, estrutura e contexto da vaga.

A aplicação permite transformar um currículo comum em uma versão:
- mais estratégica
- mais alinhada à vaga
- otimizada para sistemas automatizados
- pronta para mercado internacional

---

## Principais funcionalidades

### 1. Análise linguística do currículo:

- Coesão e coerência textual 
- Gramática normativa (pontuação, concordância, regência, crase) 
- Ortografia
- Formalidade profissional
- Feedback estruturado com correções

### 2. Otimização estratégica para vaga (ATS):
 #### Extração de palavras-chave da vaga
- Hard skills
- Soft skills
- Tecnologias
- Ferramentas
- Termos relevantes
#### Análise de compatibilidade (CV × vaga)
- Keywords presentes
- Keywords ausentes
- Lacunas estratégicas
- Score estimado de compatibilidade
#### Reescrita otimizada do currículo
- Sem inventar informações
- Uso de palavras-chave relevantes
- Melhor estrutura e clareza
- Verbos de ação
- Foco em ATS
#### Ajuste ao perfil da empresa
- Linguagem adequada ao contexto
- Destaque de experiências relevantes
- Resumo profissional otimizado

### 3. Geração de Versão em Inglês
- Tradução profissional (não literal)
- Adequação para mercado internacional
- Uso de padrões globais de currículo
- Linguagem natural e fluente
- Estrutura compatível com recrutadores internacionais

### 4. OCR para descrição de vagas
- Extração de texto a partir de imagens (PNG, JPG, JPEG, WEBP, BMP, TIFF) e PDFs escaneados
- Pré-processamento automático da imagem antes do OCR:
  - Conversão para escala de cinza
  - Upscale para resolução mínima de 2400px
  - Aumento de contraste e nitidez
- Suporte multilíngue: português + inglês (por+eng)
- Motor LSTM (--oem 3) para maior precisão
- Prévia do texto extraído antes da execução

### 5. Pipeline Inteligente Multietapas
Fluxo dinâmico com controle de estado:

- CV original → otimização → versão em inglês  
- CV original → versão em inglês → otimização  
- CV otimizado → tradução → reotimização  

Gerenciado via `st.session_state` para evitar redundâncias e inconsistências.

### 6. Exportação Profissional em PDF
- Geração automática do currículo otimizado em memória com reportlab (sem arquivos temporários)
- Layout estruturado com suporte a headings, negrito, itálico e bullet points
- Nome do arquivo dinâmico baseado no cargo extraído da vaga:
```
    Currículo para {cargo}.pdf
    Resume for {cargo}.pdf
    Currículo Corrigido.pdf
```
- Botão de download persistente (não desaparece ao clicar)
- Pronto para envio

### 7. Interface Inteligente (Streamlit)
- UI adaptativa por contexto
- Abas (tabs) para navegação das etapas:
    - 🔑 Palavras-chave | 📊 Compatibilidade | 💡 Sugestões | 📄 Currículo otimizado | 🏆 Score ATS
- Controle dinâmico de fluxo
- Feedback visual (score, progresso)

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
| LLMs | Google Gemini 2.5 flash / Groq Llama Llama 4 Maverick / OpenAI GPT-4o Mini|
| Extração de PDF | PyMuPDF (fitz) |
|OCR |	pytesseract + Pillow |
|Geração de PDF |	reportlab |
|Configuração |	python-dotenv |

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

