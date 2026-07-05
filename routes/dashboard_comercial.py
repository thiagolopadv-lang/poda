"""
dashboard_comercial.py — Painel de inteligência comercial da Poda
Endpoints de API e painel HTML com MRR, funil, latências e erros.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from config import settings
from services.metricas_comerciais import (
    calcular_mrr,
    obter_erros_hoje,
    obter_funil_hoje,
    obter_latencias,
)
from services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter()


def _auth(token: str) -> bool:
    return token == settings.DASHBOARD_TOKEN


# ── API: dados comerciais consolidados ───────────────────────────────────────

@router.get("/api/comercial")
async def api_comercial(token: str = Query("")):
    """Retorna MRR, funil do dia, latências e erros — para o painel comercial."""
    if not _auth(token):
        return JSONResponse(status_code=401, content={"erro": "Token inválido"})
    try:
        pro    = int(await rate_limiter.redis.scard("poda:assinantes:pro") or 0)
        equipe = int(await rate_limiter.redis.scard("poda:assinantes:equipe") or 0)
        free   = int(await rate_limiter.redis.scard("poda:assinantes:free") or 0)
    except Exception:
        pro = equipe = free = 0

    mrr      = await calcular_mrr(pro, equipe,
                                  settings.PLANO_PRO_PRECO,
                                  settings.PLANO_EQUIPE_PRECO)
    funil    = await obter_funil_hoje()
    latencia = await obter_latencias()
    erros    = await obter_erros_hoje()

    try:
        hoje = date.today().isoformat()
        novos_pro    = int(await rate_limiter.redis.get(f"poda:conv:new:pro:{hoje}") or 0)
        novos_equipe = int(await rate_limiter.redis.get(f"poda:conv:new:equipe:{hoje}") or 0)
        churn_hoje   = int(await rate_limiter.redis.get(f"poda:churn:total:{hoje}") or 0)
    except Exception:
        novos_pro = novos_equipe = churn_hoje = 0

    return {
        "planos":    {"free": free, "pro": pro, "equipe": equipe},
        "financeiro": {**mrr, "novos_pro": novos_pro,
                       "novos_equipe": novos_equipe, "churn_hoje": churn_hoje},
        "funil":    funil,
        "latencia": latencia,
        "erros":    erros,
    }


# ── Painel HTML ───────────────────────────────────────────────────────────────

def _html_comercial(token: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Poda — Painel Comercial</title>
<style>
  :root{{
    --green:#2e7d32;--green-light:#4caf50;--green-dark:#1b5e20;
    --bg:#f5f5f5;--card:#fff;--text:#212121;--sub:#757575;
    --red:#c62828;--amber:#e65100;--ok:#2e7d32;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--text);padding:20px}}
  h1{{color:var(--green-dark);font-size:1.5rem;margin-bottom:4px}}
  .sub{{color:var(--sub);font-size:.85rem;margin-bottom:24px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}}
  .card{{background:var(--card);border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.1)}}
  .card h2{{font-size:.95rem;color:var(--sub);text-transform:uppercase;letter-spacing:.06em;margin-bottom:14px}}
  .big{{font-size:2.2rem;font-weight:700;color:var(--green-dark)}}
  .row{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #f0f0f0}}
  .row:last-child{{border-bottom:none}}
  .label{{color:var(--sub);font-size:.88rem}}
  .val{{font-weight:600}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.78rem;font-weight:600}}
  .ok{{background:#e8f5e9;color:var(--ok)}}
  .warn{{background:#fff3e0;color:var(--amber)}}
  .err{{background:#ffebee;color:var(--red)}}
  .funnel{{display:flex;align-items:flex-end;gap:8px;height:80px;margin-top:8px}}
  .bar-wrap{{display:flex;flex-direction:column;align-items:center;flex:1}}
  .bar{{width:100%;background:var(--green-light);border-radius:4px 4px 0 0;transition:height .4s}}
  .bar-label{{font-size:.7rem;color:var(--sub);margin-top:4px;text-align:center}}
  .bar-val{{font-size:.8rem;font-weight:600;color:var(--text);margin-top:2px}}
  .spin{{text-align:center;padding:40px;color:var(--sub)}}
  a.back{{display:inline-block;margin-bottom:16px;color:var(--green);text-decoration:none;font-size:.9rem}}
  a.back:hover{{text-decoration:underline}}
</style>
</head>
<body>
<a class="back" href="/dashboard" onclick="history.length>1?history.back():(window.location.href='/dashboard');return false;">&#x2190; Voltar ao painel principal</a>
<h1>&#x1F33F; Poda &mdash; Intelig&ecirc;ncia Comercial</h1>
<p class="sub" id="ts">Carregando dados...</p>

<div class="grid" id="grid"><p class="spin">&#x23F3; Carregando m&eacute;tricas...</p></div>

<script>
const TOKEN = '{token}';

async function load(){{
  try{{
    const r = await fetch('/api/comercial?token=' + encodeURIComponent(TOKEN));
    if(!r.ok){{ document.getElementById('grid').innerHTML='<p class="spin">Erro ao carregar dados. Tente recarregar.</p>'; return; }}
    const d = await r.json();
    render(d);
    document.getElementById('ts').textContent = 'Atualizado em ' + new Date().toLocaleTimeString('pt-BR');
  }}catch(e){{
    document.getElementById('grid').innerHTML='<p class="spin">Sem conexão com o servidor.</p>';
  }}
}}

function fmt_brl(v){{ return 'R$ '+v.toFixed(2).replace('.',','); }}

function render(d){{
  const f = d.financeiro;
  const funil = d.funil;
  const lat = d.latencia;
  const err = d.erros;
  const pl = d.planos;

  const max_f = Math.max(funil.limite_atingido,1);
  function bar(val,label){{
    const h = Math.max(8, Math.round(val/max_f*72));
    return '<div class="bar-wrap"><div class="bar-val">'+val+'</div><div class="bar" style="height:'+h+'px"></div><div class="bar-label">'+label+'</div></div>';
  }}

  function lat_badge(ms){{
    if(ms==null) return '<span class="badge ok">—</span>';
    const cls = ms<3000?'ok':ms<8000?'warn':'err';
    return '<span class="badge '+cls+'">'+ms+'ms</span>';
  }}

  function lat_p95_badge(ms,ok_ms,warn_ms){{
    if(ms==null) return '<span class="badge ok">—</span>';
    const cls = ms<ok_ms?'ok':ms<warn_ms?'warn':'err';
    return '<span class="badge '+cls+'">'+ms+'ms</span>';
  }}

  const html =
  '<div class="card"><h2>&#x1F4B0; Receita Recorrente</h2>' +
  '<div class="big">'+fmt_brl(f.mrr)+'<span style="font-size:1rem;color:var(--sub)">/m\xeas</span></div>' +
  '<div class="row" style="margin-top:12px"><span class="label">ARR projetado</span><span class="val">'+fmt_brl(f.arr)+'</span></div>' +
  '<div class="row"><span class="label">Ticket m\xe9dio</span><span class="val">'+fmt_brl(f.ticket_medio)+'</span></div>' +
  '<div class="row"><span class="label">Total pagantes</span><span class="val">'+f.total_pagantes+'</span></div>' +
  '<div class="row"><span class="label">Novos Pro hoje</span><span class="val" style="color:var(--green)">+'+f.novos_pro+'</span></div>' +
  '<div class="row"><span class="label">Novos Equipe hoje</span><span class="val" style="color:var(--green)">+'+f.novos_equipe+'</span></div>' +
  '<div class="row"><span class="label">Churn hoje</span><span class="val" style="color:'+(f.churn_hoje>0?'var(--red)':'var(--text)')+'">-'+f.churn_hoje+'</span></div></div>' +

  '<div class="card"><h2>&#x1F4CA; Assinantes por Plano</h2>' +
  '<div class="row"><span class="label">Free</span><span class="val">'+pl.free+'</span></div>' +
  '<div class="row"><span class="label">Pro — R$19/m\xeas</span><span class="val">'+pl.pro+'</span></div>' +
  '<div class="row"><span class="label">Equipe — R$79/m\xeas</span><span class="val">'+pl.equipe+'</span></div>' +
  '<div class="row" style="margin-top:8px"><span class="label">Taxa pago/total</span>' +
  '<span class="val">'+(pl.free+pl.pro+pl.equipe>0?((pl.pro+pl.equipe)/(pl.free+pl.pro+pl.equipe)*100).toFixed(1):0)+'%</span></div></div>' +

  '<div class="card"><h2>&#x1F504; Funil de Convers\xe3o — Hoje</h2>' +
  '<div class="funnel">'+bar(funil.limite_atingido,'Atingiram<br>limite')+bar(funil.intent_upgrade,'Pediram<br>/planos')+bar(funil.cpf_informado,'CPF<br>informado')+bar(funil.pix_gerado,'PIX<br>gerado')+bar(funil.pago,'Pago ✓')+'</div>' +
  '<div class="row" style="margin-top:12px"><span class="label">Abandono de PIX</span>' +
  '<span class="val"><span class="badge '+(funil.abandono_pct>60?'err':funil.abandono_pct>30?'warn':'ok')+'">'+funil.abandono_pct+'%</span></span></div></div>' +

  '<div class="card"><h2>&#x26A1; Velocidade de Respostas</h2>' +
  '<div class="row"><span class="label">URL — P50</span><span>'+lat_badge(lat.url&&lat.url.p50)+'</span></div>' +
  '<div class="row"><span class="label">URL — P95</span><span>'+lat_p95_badge(lat.url&&lat.url.p95,5000,10000)+'</span></div>' +
  '<div class="row"><span class="label">PDF — P50</span><span>'+lat_badge(lat.pdf&&lat.pdf.p50)+'</span></div>' +
  '<div class="row"><span class="label">PDF — P95</span><span>'+lat_p95_badge(lat.pdf&&lat.pdf.p95,8000,15000)+'</span></div>' +
  '<div class="row"><span class="label">Token — P50</span><span>'+lat_badge(lat.token&&lat.token.p50)+'</span></div>' +
  '<div class="row"><span class="label">Amostras (URL/PDF/Tkn)</span><span class="val" style="font-size:.85rem">'+((lat.url&&lat.url.amostras)||0)+' / '+((lat.pdf&&lat.pdf.amostras)||0)+' / '+((lat.token&&lat.token.amostras)||0)+'</span></div></div>' +

  '<div class="card"><h2>&#x1F41B; Erros — Hoje</h2>' +
  '<div class="row"><span class="label">URL timeout</span><span class="val">'+((err.url&&err.url.timeout)||0)+'</span></div>' +
  '<div class="row"><span class="label">URL parse_fail</span><span class="val">'+((err.url&&err.url.parse_fail)||0)+'</span></div>' +
  '<div class="row"><span class="label">PDF too_large</span><span class="val">'+((err.pdf&&err.pdf.too_large)||0)+'</span></div>' +
  '<div class="row"><span class="label">PDF parse_fail</span><span class="val">'+((err.pdf&&err.pdf.parse_fail)||0)+'</span></div>' +
  '<div class="row"><span class="label">PIX fail</span><span class="val">'+((err.pix&&err.pix.fail)||0)+'</span></div>' +
  '<div class="row" style="font-weight:700"><span>Total de erros</span>' +
  '<span class="badge '+(err.total===0?'ok':err.total<10?'warn':'err')+'">'+err.total+'</span></div></div>';

  document.getElementById('grid').innerHTML = html;
}}

load();
setInterval(load, 30000);
</script>
</body>
</html>"""


@router.get("/dashboard/comercial", response_class=HTMLResponse)
async def painel_comercial(token: str = Query("")):
    """Painel HTML de inteligência comercial."""
    if not _auth(token):
        return HTMLResponse(
            content='<meta http-equiv="refresh" content="0;url=/dashboard">',
            status_code=302,
        )
    return HTMLResponse(content=_html_comercial(token))
