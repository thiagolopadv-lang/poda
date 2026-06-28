# PODA — Guia de Setup do Zero

> Tempo estimado: 30–60 minutos (incluindo aprovação da Meta, que pode levar até 3 dias úteis)

---

## PRÉ-REQUISITOS

- Conta no **GitHub** (para hospedar o código)
- Conta no **Railway.app** (hosting)
- Conta no **Meta for Developers** (WhatsApp API)
- Número de telefone real para o WhatsApp Business (não pode ser usado pessoalmente)
- Python 3.11+ instalado localmente (para testes)

---

## PASSO 1 — GitHub: Criar o Repositório

1. Acesse [github.com/new](https://github.com/new)
2. Nome do repositório: `poda`
3. Visibilidade: **Privado** (o código tem suas variáveis de ambiente referenciadas)
4. Não inicializar com README (já temos os arquivos)
5. Clique em **Create repository**

No terminal, dentro da pasta `poda/`:

```bash
git init
git add .
git commit -m "feat: estrutura inicial do projeto Poda"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/poda.git
git push -u origin main
```

---

## PASSO 2 — Railway: Criar o Projeto

1. Acesse [railway.app](https://railway.app) e faça login com GitHub
2. Clique em **New Project** → **Deploy from GitHub repo**
3. Selecione o repositório `poda`
4. Railway detecta automaticamente o Python via `requirements.txt`
5. O primeiro deploy ocorre automaticamente

**Após o deploy:**
- Vá em **Settings → Networking → Generate Domain**
- Anote a URL gerada (ex: `poda-production.up.railway.app`)
- Esta é a URL do seu webhook

**Configurar variáveis de ambiente no Railway:**
- Vá em **Variables**
- Adicione as variáveis do `.env.example` (preencher os valores reais)
- O Railway reinicia automaticamente ao salvar

**Plano necessário:** Hobby ($5/mês) — ative em **Account → Billing**

---

## PASSO 3 — Meta: Criar o App e Obter Credenciais

### 3.1 Criar Conta Meta Business

1. Acesse [business.facebook.com](https://business.facebook.com)
2. Clique em **Criar conta** se ainda não tiver
3. Preencha nome da empresa: `Poda`
4. Conclua a verificação de identidade (upload de documento — pode levar 1–3 dias)

### 3.2 Criar App no Meta for Developers

1. Acesse [developers.facebook.com/apps](https://developers.facebook.com/apps)
2. Clique em **Criar app**
3. Tipo: **Business**
4. Nome: `Poda`
5. Associe à sua conta Meta Business

### 3.3 Adicionar WhatsApp ao App

1. No painel do app, clique em **Adicionar produto**
2. Encontre **WhatsApp** e clique em **Configurar**
3. Em **Configuração da API**, você verá:
   - **Token de acesso temporário** (válido por 24h — para testes)
   - **Phone number ID** (copie para o `.env`)
   - **WhatsApp Business Account ID**

> Para token permanente: vá em **Configurações do App → Avançado → Tokens de acesso → Gerar token permanente**

### 3.4 Configurar o Webhook

1. Na seção WhatsApp → Configuração, role até **Webhooks**
2. Clique em **Configurar webhooks**
3. Preencha:
   - **URL do callback:** `https://SUA-URL.up.railway.app/webhook`
   - **Token de verificação:** o mesmo valor do `WHATSAPP_VERIFY_TOKEN` no seu `.env`
4. Clique em **Verificar e salvar**
   - A Meta faz um GET na sua URL com o token — seu servidor deve responder com o `hub.challenge`
   - Se Railway já estiver rodando, a verificação ocorre instantaneamente
5. Em **Campos do webhook**, ative: `messages`

### 3.5 Testar com Número de Teste

1. Na seção **Configuração da API**, adicione seu número pessoal como destinatário do teste
2. Envie uma mensagem via interface da Meta para testar
3. Ou envie uma mensagem diretamente no WhatsApp para o número de teste fornecido pela Meta

---

## PASSO 4 — Jina AI: Obter API Key

1. Acesse [jina.ai](https://jina.ai) → **Get Started**
2. Crie uma conta gratuita
3. Vá em **Settings → API Keys → Create API Key**
4. Copie a chave para o `JINA_API_KEY` no Railway

**Plano gratuito:** 100 req/min, 1 milhão de tokens de bônus — suficiente para o MVP.

---

## PASSO 5 — Testar Localmente (Opcional)

```bash
# Instalar dependências
pip install -r requirements.txt

# Criar .env com seus valores reais
cp .env.example .env
# Edite o .env com suas chaves

# Rodar o servidor
uvicorn main:app --reload

# Em outro terminal, testar o health check
curl http://localhost:8000/
# Resposta esperada: {"status":"ok","service":"poda"}
```

Para testar o webhook localmente, use o [ngrok](https://ngrok.com):

```bash
ngrok http 8000
# Copie a URL https://... gerada pelo ngrok
# Use essa URL como callback no painel da Meta
```

---

## PASSO 6 — Verificar que Tudo Funciona

Checklist de validação:

- [ ] `GET /` retorna `{"status":"ok","service":"poda"}`
- [ ] Webhook verificado pela Meta (sem erro 403)
- [ ] Mensagem de texto recebida e processada (aparece no log do Railway)
- [ ] URL enviada → Markdown retornado no WhatsApp
- [ ] PDF enviado → Markdown retornado no WhatsApp
- [ ] Texto enviado → análise de tokens retornada

---

## VARIÁVEIS DE AMBIENTE — RESUMO

| Variável | Obrigatória | Onde obter |
|---|---|---|
| `WHATSAPP_TOKEN` | ✅ Sim | Meta for Developers → App → WhatsApp → Token |
| `WHATSAPP_PHONE_NUMBER_ID` | ✅ Sim | Meta for Developers → App → WhatsApp → Phone number ID |
| `WHATSAPP_VERIFY_TOKEN` | ✅ Sim | Você define (qualquer string) |
| `JINA_API_KEY` | ✅ Recomendado | jina.ai → Settings → API Keys |
| `FIRECRAWL_API_KEY` | ❌ Opcional | firecrawl.dev → Dashboard |
| `LLAMA_CLOUD_API_KEY` | ❌ Opcional | cloud.llamaindex.ai |
| `USD_TO_BRL` | ❌ Opcional | Default: 5.70 |

---

## ESTRUTURA DO PROJETO

```
poda/
├── main.py              # FastAPI app + verificação de webhook
├── config.py            # Variáveis de ambiente
├── routes/
│   ├── whatsapp.py      # Webhook receiver + roteamento de mensagens
│   ├── url_handler.py   # URL → Markdown
│   ├── pdf_handler.py   # PDF → Markdown
│   └── token_handler.py # Contador de tokens
├── services/
│   ├── jina.py          # Cliente Jina Reader
│   ├── firecrawl.py     # Cliente Firecrawl (fallback)
│   ├── pdf_parser.py    # Pipeline PDF: PyMuPDF4LLM → Marker → LlamaParse
│   ├── token_counter.py # tiktoken + tokencost
│   └── whatsapp_api.py  # Envio de mensagens e download de mídias
├── utils/
│   ├── detector.py      # Detecta tipo: URL / PDF / texto
│   └── formatter.py     # Formata respostas para o WhatsApp
├── requirements.txt
├── Procfile
├── railway.toml
├── .env.example
└── .gitignore
```

---

## PRÓXIMOS PASSOS (Sprint 2+)

Após o setup estar funcionando com o número de teste:

- [ ] Migrar para número real (verificar número no Meta Business)
- [ ] Implementar controle de limites diários por usuário (free tier)
- [ ] Implementar envio de arquivos .md maiores que 4.096 chars
- [ ] Configurar PIX Automático para assinaturas
- [ ] Criar landing page em poda.io
- [ ] Configurar Sentry para monitoramento de erros
