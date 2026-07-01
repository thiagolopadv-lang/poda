"""
dashboard.py â Painel de monitoramento + uso do Poda

Acesso: GET /dashboard?token=DASHBOARD_TOKEN
API:    GET /api/metrics?token=DASHBOARD_TOKEN
"""

import logging
from fastapi import APIRouter, Request, Query
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
        return HTMLResponse(
            content="<h2 style='font-family:sans-serif;margin:40px'>ð Acesso negado. ForneÃ§a ?token=SEU_TOKEN</h2>",
            status_code=401,
        )
    return HTMLResponse(content=_html(token))


def _html(token: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Poda â Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }}
  .header {{ background: #1a1f2e; border-bottom: 1px solid #2d3748; padding: 16px 24px; display: flex; align-items: center; gap: 12px; }}
  .header h1 {{ font-size: 1.25rem; font-weight: 600; color: #fff; }}
  .header .badge {{ background: #22c55e22; color: #22c55e; font-size: 0.75rem; padding: 2px 8px; border-radius: 9999px; border: 1px solid #22c55e44; }}
  .badge.erro {{ background: #ef444422; color: #ef4444; border-color: #ef444444; }}
  .last-update {{ margin-left: auto; font-size: 0.75rem; color: #64748b; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
  .section-title {{ font-size: 0.7rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: #64748b; margin-bottom: 12px; margin-top: 28px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
  .card {{ background: #1a1f2e; border: 1px solid #2d3748; border-radius: 12px; padding: 18px; }}
  .card .label {{ font-size: 0.72rem; color: #64748b; margin-bottom: 6px; }}
  .card .value {{ font-size: 1.8rem; font-weight: 700; color: #fff; line-height: 1; }}
  .card .sub {{ font-size: 0.72rem; color: #64748b; margin-top: 4px; }}
  .card.green .value {{ color: #22c55e; }}
  .card.red .value {{ color: #ef4444; }}
  .card.blue .value {{ color: #60a5fa; }}
  .card.yellow .value {{ color: #fbbf24; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 0; }}
  .chart-box {{ background: #1a1f2e; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; }}
  .chart-box h3 {{ font-size: 0.85rem; font-weight: 600; color: #94a3b8; margin-bottom: 16px; }}
  .status-row {{ display: flex; align-items: center; gap: 8px; padding: 10px 0; border-bottom: 1px solid #1e2535; }}
  .status-row:last-child {{ border-bottom: none; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .dot.green {{ background: #22c55e; }}
  .dot.red {{ background: #ef4444; }}
  .dot.yellow {{ background: #fbbf24; }}
  .status-label {{ font-size: 0.82rem; color: #94a3b8; flex: 1; }}
  .status-value {{ font-size: 0.82rem; color: #e2e8f0; font-weight: 500; }}
  .status-box {{ background: #1a1f2e; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; }}
  .status-box h3 {{ font-size: 0.85rem; font-weight: 600; color: #94a3b8; margin-bottom: 12px; }}
  #loading {{ text-align: center; color: #64748b; padding: 60px; font-size: 0.9rem; }}
  @media (max-width: 768px) {{ .charts {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="header">
  <span style="font-size:1.4rem">ð±</span>
  <h1>Poda Dashboard</h1>
  <span class="badge" id="status-badge">Carregando...</span>
  <span class="last-update" id="last-update"></span>
</div>

<div class="container">
  <div id="loading">â³ Carregando mÃ©tricas...</div>
  <div id="content" style="display:none">

    <p class="section-title">ð Uso de hoje</p>
    <div class="cards">
      <div class="card blue"><div class="label">Mensagens hoje</div><div class="value" id="msgs-hoje">-</div><div class="sub">desde meia-noite</div></div>
      <div class="card green"><div class="label">UsuÃ¡rios Ãºnicos hoje</div><div class="value" id="usuarios-hoje">-</div><div class="sub">nÃºmeros distintos</div></div>
      <div class="card"><div class="label">Total de mensagens</div><div class="value" id="msgs-total">-</div><div class="sub">desde o inÃ­cio</div></div>
      <div class="card"><div class="label">Respostas enviadas</div><div class="value" id="msgs-enviadas">-</div><div class="sub">total enviado</div></div>
      <div class="card red"><div class="label">Erros registrados</div><div class="value" id="erros">-</div><div class="sub">total acumulado</div></div>
    </div>

    <p class="section-title">ð¡ Tipos de mensagem</p>
    <div class="cards">
      <div class="card"><div class="label">ð URLs processadas</div><div class="value" id="tipo-url">-</div></div>
      <div class="card"><div class="label">ð PDFs processados</div><div class="value" id="tipo-pdf">-</div></div>
      <div class="card"><div class="label">ð Textos analisados</div><div class="value" id="tipo-texto">-</div></div>
      <div class="card"><div class="label">â¡ Comandos usados</div><div class="value" id="tipo-comando">-</div></div>
      <div class="card"><div class="label">ð SaudaÃ§Ãµes</div><div class="value" id="tipo-saudacao">-</div></div>
      <div class="card yellow"><div class="label">â NÃ£o reconhecidos</div><div class="value" id="tipo-invalido">-</div></div>
    </div>

    <p class="section-title">ð Ãltimos 7 dias + SaÃºde tÃ©cnica</p>
    <div class="charts">
      <div class="chart-box">
        <h3>Mensagens por dia</h3>
        <canvas id="chart-msgs" height="160"></canvas>
      </div>
      <div class="chart-box">
        <h3>UsuÃ¡rios Ãºnicos por dia</h3>
        <canvas id="chart-usuarios" height="160"></canvas>
      </div>
    </div>

    <p class="section-title">ð§ SaÃºde do sistema</p>
    <div class="charts">
      <div class="status-box">
        <h3>ServiÃ§os</h3>
        <div class="status-row">
          <div class="dot" id="dot-redis"></div>
          <span class="status-label">Redis</span>
          <span class="status-value" id="info-redis">-</span>
        </div>
        <div class="status-row">
          <div class="dot green"></div>
          <span class="status-label">FastAPI / Webhook</span>
          <span class="status-value">Online</span>
        </div>
        <div class="status-row">
          <div class="dot green"></div>
          <span class="status-label">WhatsApp Cloud API</span>
          <span class="status-value">Conectado</span>
        </div>
      </div>
      <div class="status-box">
        <h3>InformaÃ§Ãµes</h3>
        <div class="status-row">
          <div class="dot green"></div>
          <span class="status-label">Uptime (desde inÃ­cio)</span>
          <span class="status-value" id="info-uptime">-</span>
        </div>
        <div class="status-row">
          <div class="dot green"></div>
          <span class="status-label">Ãltimo evento</span>
          <span class="status-value" id="info-ultimo">-</span>
        </div>
        <div class="status-row">
          <div class="dot green"></div>
          <span class="status-label">MemÃ³ria Redis</span>
          <span class="status-value" id="info-memoria">-</span>
        </div>
        <div class="status-row">
          <div class="dot green"></div>
          <span class="status-label">VersÃ£o Redis</span>
          <span class="status-value" id="info-redis-versao">-</span>
        </div>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /container -->

<script>
const TOKEN = '{token}';
let chartMsgs = null, chartUsuarios = null;

async function carregar() {{
  try {{
    const r = await fetch(`/api/metrics?token=${{TOKEN}}`);
    const d = await r.json();

    document.getElementById('loading').style.display = 'none';
    document.getElementById('content').style.display = 'block';

    // Cards de hoje
    document.getElementById('msgs-hoje').textContent = d.msgs_hoje ?? 0;
    document.getElementById('usuarios-hoje').textContent = d.usuarios_hoje ?? 0;
    document.getElementById('msgs-total').textContent = d.msgs_recebidas ?? 0;
    document.getElementById('msgs-enviadas').textContent = d.msgs_enviadas ?? 0;
    document.getElementById('erros').textContent = d.erros ?? 0;

    // Tipos
    const t = d.tipos || {{}};
    document.getElementById('tipo-url').textContent = t.url ?? 0;
    document.getElementById('tipo-pdf').textContent = t.pdf ?? 0;
    document.getElementById('tipo-texto').textContent = t.texto ?? 0;
    document.getElementById('tipo-comando').textContent = t.comando ?? 0;
    document.getElementById('tipo-saudacao').textContent = t.saudacao ?? 0;
    document.getElementById('tipo-invalido').textContent = t.invalido ?? 0;

    // SaÃºde
    const redisOk = d.redis_disponivel;
    document.getElementById('dot-redis').className = 'dot ' + (redisOk ? 'green' : 'red');
    document.getElementById('info-redis').textContent = redisOk ? 'Online' : 'Offline';
    document.getElementById('info-uptime').textContent = d.uptime ?? 'â';
    document.getElementById('info-ultimo').textContent = d.ultimo_evento ? d.ultimo_evento.replace('T', ' ') : 'â';
    document.getElementById('info-memoria').textContent = d.redis_memoria ?? 'â';
    document.getElementById('info-redis-versao').textContent = d.redis_versao ?? 'â';

    // Badge de status
    const badge = document.getElementById('status-badge');
    if (redisOk && (d.erros ?? 0) === 0) {{
      badge.textContent = 'â SaudÃ¡vel';
      badge.className = 'badge';
    }} else if (!redisOk) {{
      badge.textContent = 'ð´ Redis offline';
      badge.className = 'badge erro';
    }} else {{
      badge.textContent = 'â ï¸ Erros detectados';
      badge.className = 'badge erro';
    }}

    document.getElementById('last-update').textContent = 'Atualizado: ' + new Date().toLocaleTimeString('pt-BR');

    // GrÃ¡ficos
    const hist = d.historico_7_dias ?? [];
    const labels = hist.map(h => h.data.slice(5));
    const msgsDados = hist.map(h => h.mensagens);
    const usersDados = hist.map(h => h.usuarios);

    const chartOpts = {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: '#64748b', font: {{ size: 11 }} }}, grid: {{ color: '#1e2535' }} }},
        y: {{ ticks: {{ color: '#64748b', font: {{ size: 11 }} }}, grid: {{ color: '#1e2535' }}, beginAtZero: true }},
      }},
    }};

    if (chartMsgs) chartMsgs.destroy();
    chartMsgs = new Chart(document.getElementById('chart-msgs'), {{
      type: 'bar',
      data: {{ labels, datasets: [{{ data: msgsDados, backgroundColor: '#3b82f644', borderColor: '#3b82f6', borderWidth: 2, borderRadius: 4 }}] }},
      options: chartOpts,
    }});

    if (chartUsuarios) chartUsuarios.destroy();
    chartUsuarios = new Chart(document.getElementById('chart-usuarios'), {{
      type: 'line',
      data: {{ labels, datasets: [{{ data: usersDados, borderColor: '#22c55e', backgroundColor: '#22c55e11', borderWidth: 2, tension: 0.4, fill: true, pointRadius: 4, pointBackgroundColor: '#22c55e' }}] }},
      options: chartOpts,
    }});

  }} catch(e) {{
    document.getElementById('loading').textContent = 'â Erro ao carregar: ' + e.message;
  }}
}}

carregar();
setInterval(carregar, 30000); // Atualiza a cada 30s
</script>
</body>
</html>"""
