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

---

## 🏗️ Arquitetura do sistema

```
Input:
  ├── Currículo (PDF)
  └── Vaga (Texto / PDF)

Pipeline:
  ├── Extração de texto (PyMuPDF)
  ├── Processamento com LLM (LlamaIndex)
  │     ├── Análise linguística
  │     ├── Extração de keywords
  │     ├── Reescrita otimizada (ATS)
  │     └── Tradução profissional
  └── Geração de output estruturado

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

---

## ⚙️ Como executar o projeto

### 1. Clone o repositório

```
git clone <repo> 
cd <repo>
```

### 2. Crie o ambiente virtual

```
python -m venv .venv
```

### 3. Ative o ambiente

  Windows:

  ```
  .venv\Scripts\activate
  ```

  Mac/Linux:

  ```
  source .venv/bin/activate
  ```

### 4. Instale as dependências

  ```
  pip install -r requirements.txt
  ```

### 5. Configure as variáveis de ambiente

  Crie um `.env`:
  ```
  GOOGLE_API_KEY=your_key
  GROQ_API_KEY=your_key
  OPENAI_API_KEY=your_key
  ```
ou use o sistema de **secrets do Streamlit Cloud**

### 6. Execute a aplicação
  ```
  streamlit run Corretor_CV.py
  ```
---

## 💡 Melhorias futuras:
* Currículo otimizado em inglês
* Implementar OCR para analise de imagem
* Exportar no formato PDF
* Separar a resposta da otimização em abas para melhorar a visualização
* Perguntas da vaga e respostas para aumentar a aderência do candidato
* Simulação de entrevista para a vaga
* Inserir mais modelos de LLM