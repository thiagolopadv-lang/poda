"""
dashboard.py â Painel de monitoramento do Poda

Acesso: GET /dashboard?token=DASHBOARD_TOKEN
API:    GET /api/metrics?token=DASHBOARD_TOKEN
"""

import logging
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from services.metrics import obter_metricas
from config import settings

logger = logging.getLogger("poda.dashboard")
router = APIRouter()


def _auth(token: str) -> bool:
    return token == settings.DASHBOARD_TOKEN


@router.get("/api/metrics")
async def api_metrics(token: str = Query("")):
    if not _auth(token):
        return JSONResponse(status_code=401, content={"erro": "Token invÃ¡lido"})
    dados = await obter_metricas()
    return dados


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(token: str = Query("")):
    if not _auth(token):
        return HTMLResponse(content=_html_login(), status_code=200)
    return HTMLResponse(content=_html_dashboard(token))


# ââ Tela de login ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _html_login() -> str:
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Poda â Acesso ao Painel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .card {
    background: #1a1f2e;
    border: 1px solid #2d3748;
    border-radius: 16px;
    padding: 40px 36px;
    width: 360px;
    text-align: center;
  }
  .logo { font-size: 3rem; margin-bottom: 12px; }
  h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 4px; }
  .sub { font-size: 0.85rem; color: #64748b; margin-bottom: 28px; }
  label { display: block; text-align: left; font-size: 0.78rem; color: #94a3b8; margin-bottom: 6px; }
  input {
    width: 100%; padding: 10px 14px;
    background: #0f1117; border: 1px solid #2d3748;
    border-radius: 8px; color: #e2e8f0; font-size: 0.9rem;
    outline: none; margin-bottom: 16px;
    transition: border-color 0.2s;
  }
  input:focus { border-color: #22c55e; }
  button {
    width: 100%; padding: 11px;
    background: #22c55e; color: #0f1117;
    border: none; border-radius: 8px;
    font-size: 0.95rem; font-weight: 700;
    cursor: pointer; transition: background 0.2s;
  }
  button:hover { background: #16a34a; }
  .erro { color: #ef4444; font-size: 0.8rem; margin-top: 10px; display: none; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">ð¿</div>
  <h1>Poda</h1>
  <p class="sub">Painel de monitoramento</p>
  <label>Token de acesso</label>
  <input type="password" id="token" placeholder="â¢â¢â¢â¢â¢â¢â¢â¢" autocomplete="off">
  <button onclick="entrar()">Entrar</button>
  <p class="erro" id="erro">Token invÃ¡lido. Tente novamente.</p>
</div>
<script>
document.getElementById('token').addEventListener('keydown', e => {
  if (e.key === 'Enter') entrar();
});
async function entrar() {
  const token = document.getElementById('token').value.trim();
  if (!token) return;
  const r = await fetch('/api/metrics?token=' + encodeURIComponent(token));
  if (r.ok) {
    window.location.href = '/dashboard?token=' + encodeURIComponent(token);
  } else {
    document.getElementById('erro').style.display = 'block';
  }
}
</script>
</body>
</html>"""


# ââ Dashboard principal âââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _html_dashboard(token: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Poda â Painel</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0f1117;
    --surface: #1a1f2e;
    --border: #2d3748;
    --text: #e2e8f0;
    --muted: #64748b;
    --subtle: #94a3b8;
    --green: #22c55e;
    --blue: #60a5fa;
    --yellow: #fbbf24;
    --red: #ef4444;
    --purple: #a78bfa;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg); color: var(--text);
    min-height: 100vh;
  }}

  /* HEADER */
  .header {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 14px 24px;
    display: flex; align-items: center; gap: 14px;
    position: sticky; top: 0; z-index: 100;
  }}
  .logo {{ font-size: 1.6rem; line-height: 1; }}
  .header-title {{ font-size: 1.05rem; font-weight: 700; color: #fff; }}
  .header-sub {{ font-size: 0.72rem; color: var(--muted); margin-top: 1px; }}
  .header-right {{ margin-left: auto; display: flex; align-items: center; gap: 12px; }}
  .status-pill {{
    display: flex; align-items: center; gap: 6px;
    background: #22c55e18; border: 1px solid #22c55e44;
    border-radius: 9999px; padding: 4px 12px;
    font-size: 0.75rem; color: var(--green); font-weight: 600;
  }}
  .status-pill.erro {{ background: #ef444418; border-color: #ef444444; color: var(--red); }}
  .status-pill .dot-pulse {{
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--green); animation: pulse 2s infinite;
  }}
  .status-pill.erro .dot-pulse {{ background: var(--red); animation: none; }}
  @keyframes pulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.5; transform: scale(0.85); }}
  }}
  .btn-atualizar {{
    background: transparent; border: 1px solid var(--border);
    color: var(--subtle); border-radius: 8px;
    padding: 5px 12px; font-size: 0.78rem; cursor: pointer;
    transition: all 0.2s;
  }}
  .btn-atualizar:hover {{ border-color: var(--blue); color: var(--blue); }}
  .hora {{ font-size: 0.78rem; color: var(--muted); font-variant-numeric: tabular-nums; }}

  /* LAYOUT */
  .container {{ max-width: 1280px; margin: 0 auto; padding: 24px 20px; }}

  /* SEÃÃES */
  .section-label {{
    font-size: 0.68rem; font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--muted); margin: 28px 0 12px;
    display: flex; align-items: center; gap: 8px;
  }}
  .section-label::after {{
    content: ''; flex: 1; height: 1px; background: var(--border);
  }}

  /* KPI CARDS */
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }}
  .kpi {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 20px 18px;
    position: relative; overflow: hidden;
    transition: border-color 0.2s;
  }}
  .kpi:hover {{ border-color: #3d4f6e; }}
  .kpi-icon {{
    font-size: 1.3rem; width: 38px; height: 38px;
    background: var(--bg); border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 14px;
  }}
  .kpi-label {{ font-size: 0.73rem; color: var(--muted); margin-bottom: 5px; }}
  .kpi-value {{
    font-size: 2.1rem; font-weight: 800; line-height: 1;
    letter-spacing: -0.03em;
  }}
  .kpi-value.blue {{ color: var(--blue); }}
  .kpi-value.green {{ color: var(--green); }}
  .kpi-value.red {{ color: var(--red); }}
  .kpi-value.yellow {{ color: var(--yellow); }}
  .kpi-value.purple {{ color: var(--purple); }}
  .kpi-sub {{ font-size: 0.71rem; color: var(--muted); margin-top: 5px; }}
  .kpi-rate {{
    position: absolute; top: 16px; right: 16px;
    font-size: 0.72rem; font-weight: 600;
    background: #22c55e18; color: var(--green);
    padding: 2px 8px; border-radius: 9999px;
  }}
  .kpi-rate.ruim {{ background: #ef444418; color: var(--red); }}

  /* GRID 2 COLUNAS */
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  .grid-3 {{ display: grid; grid-template-columns: 2fr 1fr; gap: 14px; }}

  /* PAINÃIS */
  .painel {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 20px;
  }}
  .painel-titulo {{
    font-size: 0.82rem; font-weight: 600;
    color: var(--subtle); margin-bottom: 16px;
    display: flex; align-items: center; gap: 8px;
  }}

  /* BARRAS DE TIPO */
  .tipo-item {{ margin-bottom: 14px; }}
  .tipo-item:last-child {{ margin-bottom: 0; }}
  .tipo-header {{
    display: flex; justify-content: space-between;
    font-size: 0.8rem; color: var(--subtle); margin-bottom: 5px;
  }}
  .tipo-count {{ font-weight: 600; color: var(--text); }}
  .tipo-pct {{ color: var(--muted); font-size: 0.75rem; }}
  .barra-fundo {{
    height: 6px; background: var(--bg);
    border-radius: 9999px; overflow: hidden;
  }}
  .barra-fill {{
    height: 100%; border-radius: 9999px;
    transition: width 0.8s cubic-bezier(0.4,0,0.2,1);
  }}

  /* STATUS DO SISTEMA */
  .status-item {{
    display: flex; align-items: center; gap: 10px;
    padding: 9px 0; border-bottom: 1px solid #1e2535;
  }}
  .status-item:last-child {{ border-bottom: none; }}
  .dot {{
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  }}
  .dot.verde {{ background: var(--green); }}
  .dot.vermelho {{ background: var(--red); animation: none; }}
  .dot.amarelo {{ background: var(--yellow); }}
  .status-nome {{ font-size: 0.82rem; color: var(--subtle); flex: 1; }}
  .status-valor {{ font-size: 0.82rem; color: var(--text); font-weight: 500; }}

  /* TAXA DE SUCESSO */
  .taxa-circle {{
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 28px 0;
  }}
  .taxa-num {{
    font-size: 3.2rem; font-weight: 800; line-height: 1;
    letter-spacing: -0.04em; color: var(--green);
  }}
  .taxa-label {{ font-size: 0.8rem; color: var(--muted); margin-top: 6px; }}
  .taxa-detalhe {{
    display: flex; gap: 20px; margin-top: 20px; justify-content: center;
  }}
  .taxa-item {{ text-align: center; }}
  .taxa-item .n {{ font-size: 1.1rem; font-weight: 700; color: var(--text); }}
  .taxa-item .l {{ font-size: 0.7rem; color: var(--muted); margin-top: 2px; }}

  /* LOADING */
  #loading {{
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 100px 0; gap: 16px; color: var(--muted);
  }}
  .spinner {{
    width: 36px; height: 36px;
    border: 3px solid var(--border);
    border-top-color: var(--green);
    border-radius: 50%; animation: spin 0.8s linear infinite;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

  /* FOOTER */
  .footer {{
    text-align: center; padding: 32px 20px 24px;
    font-size: 0.72rem; color: var(--muted);
  }}

  /* RESPONSIVO */
  @media (max-width: 768px) {{
    .grid-2, .grid-3 {{ grid-template-columns: 1fr; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .header-right .hora {{ display: none; }}
  }}
  @media (max-width: 480px) {{
    .kpi-grid {{ grid-template-columns: 1fr 1fr; }}
  }}
</style>
</head>
<body>

<!-- HEADER -->
<header class="header">
  <div class="logo">ð¿</div>
  <div>
    <div class="header-title">Poda</div>
    <div class="header-sub">Painel de monitoramento</div>
  </div>
  <div class="header-right">
    <span class="hora" id="hora-atual"></span>
    <div class="status-pill" id="status-pill">
      <div class="dot-pulse"></div>
      <span id="status-texto">Carregando...</span>
    </div>
    <button class="btn-atualizar" onclick="carregar()">â» Atualizar</button>
  </div>
</header>

<!-- CONTEÃDO -->
<div class="container">

  <!-- LOADING -->
  <div id="loading">
    <div class="spinner"></div>
    <span>Carregando mÃ©tricas...</span>
  </div>

  <!-- PAINEL PRINCIPAL -->
  <div id="conteudo" style="display:none">

    <!-- KPIs de hoje -->
    <div class="section-label">Uso de hoje</div>
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-icon">ð¬</div>
        <div class="kpi-label">Mensagens recebidas hoje</div>
        <div class="kpi-value blue" id="msgs-hoje">â</div>
        <div class="kpi-sub">desde meia-noite</div>
      </div>
      <div class="kpi">
        <div class="kpi-icon">ð¥</div>
        <div class="kpi-label">UsuÃ¡rios Ãºnicos hoje</div>
        <div class="kpi-value green" id="usuarios-hoje">â</div>
        <div class="kpi-sub">nÃºmeros distintos</div>
      </div>
      <div class="kpi">
        <div class="kpi-icon">ð¤</div>
        <div class="kpi-label">Respostas enviadas</div>
        <div class="kpi-value" id="msgs-enviadas">â</div>
        <div class="kpi-sub">total acumulado</div>
      </div>
      <div class="kpi">
        <div class="kpi-icon">ð¥</div>
        <div class="kpi-label">Total de mensagens</div>
        <div class="kpi-value" id="msgs-total">â</div>
        <div class="kpi-sub">total acumulado</div>
      </div>
      <div class="kpi">
        <div class="kpi-icon">â ï¸</div>
        <div class="kpi-label">Erros registrados</div>
        <div class="kpi-value red" id="erros">â</div>
        <div class="kpi-sub" id="erros-sub">total acumulado</div>
      </div>
    </div>

    <!-- Taxa de sucesso + HistÃ³rico -->
    <div class="section-label">Desempenho</div>
    <div class="grid-3">
      <!-- HistÃ³rico 7 dias -->
      <div class="painel">
        <div class="painel-titulo">ð Atividade â Ãºltimos 7 dias</div>
        <canvas id="chart-hist" height="140"></canvas>
      </div>
      <!-- Taxa de sucesso -->
      <div class="painel">
        <div class="painel-titulo">â Taxa de sucesso</div>
        <div class="taxa-circle">
          <div class="taxa-num" id="taxa-pct">â</div>
          <div class="taxa-label">das mensagens respondidas</div>
          <div class="taxa-detalhe">
            <div class="taxa-item">
              <div class="n" id="taxa-recebidas">â</div>
              <div class="l">Recebidas</div>
            </div>
            <div class="taxa-item">
              <div class="n" id="taxa-enviadas">â</div>
              <div class="l">Enviadas</div>
            </div>
            <div class="taxa-item">
              <div class="n" id="taxa-erros">â</div>
              <div class="l">Erros</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tipos de mensagem -->
    <div class="section-label">Tipos de mensagem</div>
    <div class="grid-2">
      <!-- Barras -->
      <div class="painel">
        <div class="painel-titulo">ð DistribuiÃ§Ã£o por tipo</div>
        <div id="tipos-barras"></div>
      </div>
      <!-- Donut -->
      <div class="painel">
        <div class="painel-titulo">ð¥§ ProporÃ§Ã£o</div>
        <canvas id="chart-donut" height="200"></canvas>
      </div>
    </div>

    <!-- SaÃºde do sistema -->
    <div class="section-label">SaÃºde do sistema</div>
    <div class="grid-2">
      <div class="painel">
        <div class="painel-titulo">ð§ ServiÃ§os</div>
        <div class="status-item">
          <div class="dot" id="dot-redis"></div>
          <span class="status-nome">Redis</span>
          <span class="status-valor" id="val-redis">â</span>
        </div>
        <div class="status-item">
          <div class="dot verde"></div>
          <span class="status-nome">FastAPI / Webhook</span>
          <span class="status-valor">Online â</span>
        </div>
        <div class="status-item">
          <div class="dot verde"></div>
          <span class="status-nome">WhatsApp Cloud API</span>
          <span class="status-valor">Conectado â</span>
        </div>
      </div>
      <div class="painel">
        <div class="painel-titulo">â¹ï¸ InformaÃ§Ãµes tÃ©cnicas</div>
        <div class="status-item">
          <div class="dot verde"></div>
          <span class="status-nome">Uptime do servidor</span>
          <span class="status-valor" id="val-uptime">â</span>
        </div>
        <div class="status-item">
          <div class="dot verde"></div>
          <span class="status-nome">Ãltimo evento</span>
          <span class="status-valor" id="val-ultimo">â</span>
        </div>
        <div class="status-item">
          <div class="dot verde"></div>
          <span class="status-nome">VersÃ£o do Redis</span>
          <span class="status-valor" id="val-redis-versao">â</span>
        </div>
        <div class="status-item">
          <div class="dot verde"></div>
          <span class="status-nome">Data de referÃªncia</span>
          <span class="status-valor" id="val-data">â</span>
        </div>
      </div>
    </div>

  </div><!-- /conteudo -->

</div><!-- /container -->

<footer class="footer">
  Poda Â· Painel de monitoramento Â· AtualizaÃ§Ã£o automÃ¡tica a cada 30 segundos
  <br><span id="ultima-atualizacao" style="margin-top:4px;display:inline-block"></span>
</footer>

<script>
const TOKEN = '{token}';
let chartHist = null;
let chartDonut = null;

// RelÃ³gio em tempo real
function atualizarHora() {{
  const agora = new Date();
  document.getElementById('hora-atual').textContent =
    agora.toLocaleString('pt-BR', {{ dateStyle: 'short', timeStyle: 'medium' }});
}}
atualizarHora();
setInterval(atualizarHora, 1000);

// Formata nÃºmero com separador de milhar
function fmt(n) {{
  if (n == null) return 'â';
  return Number(n).toLocaleString('pt-BR');
}}

// Anima nÃºmero de 0 atÃ© o valor
function animarNumero(el, valor, sufixo) {{
  sufixo = sufixo || '';
  const duracao = 600;
  const inicio = performance.now();
  const meta = Number(valor) || 0;
  function passo(agora) {{
    const p = Math.min((agora - inicio) / duracao, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt(Math.round(meta * eased)) + sufixo;
    if (p < 1) requestAnimationFrame(passo);
  }}
  requestAnimationFrame(passo);
}}

// Cores dos tipos
const TIPOS_CONFIG = [
  {{ chave: 'url',      nome: 'URLs processadas',   emoji: 'ð', cor: '#60a5fa' }},
  {{ chave: 'pdf',      nome: 'PDFs processados',   emoji: 'ð', cor: '#a78bfa' }},
  {{ chave: 'texto',    nome: 'Textos analisados',  emoji: 'ð', cor: '#34d399' }},
  {{ chave: 'comando',  nome: 'Comandos usados',    emoji: 'â¡', cor: '#fbbf24' }},
  {{ chave: 'saudacao', nome: 'SaudaÃ§Ãµes',          emoji: 'ð', cor: '#f472b6' }},
  {{ chave: 'invalido', nome: 'NÃ£o reconhecidos',   emoji: 'â', cor: '#94a3b8' }},
];

async function carregar() {{
  try {{
    const r = await fetch('/api/metrics?token=' + TOKEN);
    if (!r.ok) throw new Error('Erro ' + r.status);
    const d = await r.json();

    document.getElementById('loading').style.display = 'none';
    document.getElementById('conteudo').style.display = 'block';

    // KPIs
    animarNumero(document.getElementById('msgs-hoje'), d.msgs_hoje ?? 0);
    animarNumero(document.getElementById('usuarios-hoje'), d.usuarios_hoje ?? 0);
    animarNumero(document.getElementById('msgs-enviadas'), d.msgs_enviadas ?? 0);
    animarNumero(document.getElementById('msgs-total'), d.msgs_recebidas ?? 0);
    animarNumero(document.getElementById('erros'), d.erros ?? 0);

    // Taxa de sucesso
    const receb = d.msgs_recebidas ?? 0;
    const enviad = d.msgs_enviadas ?? 0;
    const erros = d.erros ?? 0;
    const taxa = receb > 0 ? Math.round((enviad / receb) * 100) : 0;
    const taxaEl = document.getElementById('taxa-pct');
    taxaEl.textContent = taxa + '%';
    taxaEl.style.color = taxa >= 90 ? 'var(--green)' : taxa >= 70 ? 'var(--yellow)' : 'var(--red)';
    document.getElementById('taxa-recebidas').textContent = fmt(receb);
    document.getElementById('taxa-enviadas').textContent = fmt(enviad);
    document.getElementById('taxa-erros').textContent = fmt(erros);

    // Erros sub-label
    if (erros > 0) {{
      document.getElementById('erros-sub').textContent = 'â ï¸ atenÃ§Ã£o necessÃ¡ria';
      document.getElementById('erros-sub').style.color = 'var(--yellow)';
    }}

    // Status pill
    const pill = document.getElementById('status-pill');
    const textoStatus = document.getElementById('status-texto');
    if (d.redis_disponivel && erros === 0) {{
      pill.className = 'status-pill';
      textoStatus.textContent = 'SaudÃ¡vel';
    }} else if (!d.redis_disponivel) {{
      pill.className = 'status-pill erro';
      textoStatus.textContent = 'Redis offline';
    }} else {{
      pill.className = 'status-pill erro';
      textoStatus.textContent = 'Erros detectados';
    }}

    // Tipos â barras de progresso
    const tipos = d.tipos || {{}};
    const totalTipos = TIPOS_CONFIG.reduce((s, tc) => s + (tipos[tc.chave] ?? 0), 0) || 1;
    const barrasEl = document.getElementById('tipos-barras');
    barrasEl.innerHTML = TIPOS_CONFIG.map(tc => {{
      const qtd = tipos[tc.chave] ?? 0;
      const pct = Math.round((qtd / totalTipos) * 100);
      return `<div class="tipo-item">
        <div class="tipo-header">
          <span>${{tc.emoji}} ${{tc.nome}}</span>
          <span><span class="tipo-count">${{fmt(qtd)}}</span> <span class="tipo-pct">(${{pct}}%)</span></span>
        </div>
        <div class="barra-fundo">
          <div class="barra-fill" style="width:0%;background:${{tc.cor}}"
               data-pct="${{pct}}"></div>
        </div>
      </div>`;
    }}).join('');
    // Anima barras
    setTimeout(() => {{
      document.querySelectorAll('.barra-fill').forEach(b => {{
        b.style.width = b.dataset.pct + '%';
      }});
    }}, 50);

    // Donut
    const donutDados = TIPOS_CONFIG.map(tc => tipos[tc.chave] ?? 0);
    const donutCores = TIPOS_CONFIG.map(tc => tc.cor);
    const donutLabels = TIPOS_CONFIG.map(tc => tc.emoji + ' ' + tc.nome);
    if (chartDonut) chartDonut.destroy();
    chartDonut = new Chart(document.getElementById('chart-donut'), {{
      type: 'doughnut',
      data: {{
        labels: donutLabels,
        datasets: [{{ data: donutDados, backgroundColor: donutCores, borderColor: '#1a1f2e', borderWidth: 3 }}]
      }},
      options: {{
        responsive: true,
        cutout: '65%',
        plugins: {{
          legend: {{
            position: 'bottom',
            labels: {{ color: '#94a3b8', font: {{ size: 11 }}, padding: 12, boxWidth: 12 }}
          }},
          tooltip: {{
            callbacks: {{
              label: ctx => ' ' + fmt(ctx.raw) + ' mensagens (' + Math.round(ctx.raw / (totalTipos || 1) * 100) + '%)'
            }}
          }}
        }}
      }}
    }});

    // HistÃ³rico 7 dias
    const hist = d.historico_7_dias ?? [];
    const labels = hist.map(h => {{
      const [, m, d2] = h.data.split('-');
      return d2 + '/' + m;
    }});
    const msgsDados = hist.map(h => h.mensagens);
    const usersDados = hist.map(h => h.usuarios);
    if (chartHist) chartHist.destroy();
    chartHist = new Chart(document.getElementById('chart-hist'), {{
      type: 'bar',
      data: {{
        labels,
        datasets: [
          {{
            label: 'Mensagens',
            data: msgsDados,
            backgroundColor: '#3b82f644',
            borderColor: '#3b82f6',
            borderWidth: 2,
            borderRadius: 5,
            yAxisID: 'y',
          }},
          {{
            label: 'UsuÃ¡rios',
            data: usersDados,
            type: 'line',
            borderColor: '#22c55e',
            backgroundColor: 'transparent',
            borderWidth: 2,
            tension: 0.4,
            pointRadius: 4,
            pointBackgroundColor: '#22c55e',
            yAxisID: 'y1',
          }},
        ]
      }},
      options: {{
        responsive: true,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
          legend: {{
            labels: {{ color: '#94a3b8', font: {{ size: 11 }}, padding: 14, boxWidth: 12 }}
          }},
          tooltip: {{
            callbacks: {{
              label: ctx => ' ' + ctx.dataset.label + ': ' + fmt(ctx.raw)
            }}
          }}
        }},
        scales: {{
          x: {{ ticks: {{ color: '#64748b', font: {{ size: 11 }} }}, grid: {{ color: '#1e2535' }} }},
          y: {{
            ticks: {{ color: '#64748b', font: {{ size: 11 }} }},
            grid: {{ color: '#1e2535' }}, beginAtZero: true,
            title: {{ display: true, text: 'Mensagens', color: '#64748b', font: {{ size: 10 }} }}
          }},
          y1: {{
            ticks: {{ color: '#22c55e', font: {{ size: 11 }} }},
            grid: {{ display: false }}, beginAtZero: true,
            position: 'right',
            title: {{ display: true, text: 'UsuÃ¡rios', color: '#22c55e', font: {{ size: 10 }} }}
          }},
        }}
      }}
    }});

    // SaÃºde do sistema
    const redisOk = d.redis_disponivel;
    document.getElementById('dot-redis').className = 'dot ' + (redisOk ? 'verde' : 'vermelho');
    document.getElementById('val-redis').textContent = redisOk ? 'Online â' : 'Offline â';
    document.getElementById('val-uptime').textContent = d.uptime ?? 'â';
    document.getElementById('val-ultimo').textContent = d.ultimo_evento
      ? d.ultimo_evento.replace('T', ' ').substring(0, 19)
      : 'â';
    document.getElementById('val-redis-versao').textContent = d.redis_versao ?? 'â';
    document.getElementById('val-data').textContent = d.data_hoje ?? 'â';

    // Footer
    document.getElementById('ultima-atualizacao').textContent =
      'Ãltima atualizaÃ§Ã£o: ' + new Date().toLocaleTimeString('pt-BR');

  }} catch (e) {{
    document.getElementById('loading').innerHTML =
      '<span style="color:var(--red)">â Erro ao carregar mÃ©tricas: ' + e.message + '</span>';
  }}
}}

carregar();
setInterval(carregar, 30000);
</script>
</body>
</html>"""
