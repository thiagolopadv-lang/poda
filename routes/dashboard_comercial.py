"""
dashboard_comercial.py — Painel de inteligência comercial da Poda
Auth: cookie de sessão HttpOnly (mesmo sistema do dashboard.py)
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from config import settings
from services.metricas_comerciais import (
    calcular_mrr,
    obter_erros_hoje,
    obter_funil_hoje,
    obter_latencias,
    reconciliar_assinantes,
)
from services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter()

COOKIE_NAME = "poda_session"


async def _sessao_valida(session_id: str) -> bool:
    """Verifica se o session_id existe no Redis (mesmo padrão do dashboard.py)."""
    if not session_id:
        return False
    if rate_limiter.redis:
        try:
            val = await rate_limiter.redis.get(f"poda:session:{session_id}")
            return val is not None
        except Exception:
            pass
    return False


# ── Analytics do site (sem cookies, sem dados pessoais — LGPD-friendly) ─────

EVENTOS_SITE_VALIDOS = {
    "pageview", "cta_hero", "cta_nav", "cta_final",
    "cta_planos_free", "cta_planos_starter", "cta_planos_pro", "cta_planos_equipe",
}


@router.post("/api/site/hit")
async def site_hit(request: Request):
    """
    Beacon de analytics da landing page. Recebe {"evento": "..."} e incrementa
    contadores diários no Redis. Não coleta IP, cookie nem dado pessoal.
    """
    try:
        body = await request.json()
        evento = str(body.get("evento", ""))[:40]
    except Exception:
        evento = ""
    if evento not in EVENTOS_SITE_VALIDOS:
        return JSONResponse(status_code=204, content=None)
    try:
        hoje = date.today().isoformat()
        chave = f"poda:site:{evento}:{hoje}"
        await rate_limiter.redis.incr(chave)
        await rate_limiter.redis.expire(chave, 86400 * 60)
    except Exception:
        pass
    return JSONResponse(status_code=204, content=None)


async def _stats_site() -> dict:
    """Visitas e cliques de CTA do site — hoje."""
    hoje = date.today().isoformat()
    stats = {}
    try:
        for ev in EVENTOS_SITE_VALIDOS:
            val = await rate_limiter.redis.get(f"poda:site:{ev}:{hoje}")
            stats[ev] = int(val or 0)
        # Quantos abriram conversa vindos do site (saudação "Oi! Vim pelo site")
        val = await rate_limiter.redis.get(f"poda:site:wa_in:{hoje}")
        stats["chegou_whatsapp"] = int(val or 0)
    except Exception:
        stats = {ev: 0 for ev in EVENTOS_SITE_VALIDOS}
        stats["chegou_whatsapp"] = 0
    stats["cliques_total"] = sum(v for k, v in stats.items()
                                 if k.startswith("cta_"))
    return stats


# ── API: dados comerciais consolidados ───────────────────────────────────────

@router.get("/api/comercial")
async def api_comercial(request: Request):
    """Retorna MRR, funil do dia, latências e erros — exige sessão válida."""
    session_id = request.cookies.get(COOKIE_NAME, "")
    if not await _sessao_valida(session_id):
        return JSONResponse(status_code=401, content={"erro": "Não autenticado"})

    # Reconciliação: conta assinantes válidos e remove expirados dos sets
    contagem = await reconciliar_assinantes()
    starter = contagem.get("starter", 0)
    pro     = contagem.get("pro", 0)
    equipe  = contagem.get("equipe", 0)

    try:
        free = int(await rate_limiter.redis.scard("poda:assinantes:free") or 0)
    except Exception:
        free = 0

    mrr      = await calcular_mrr(starter, pro, equipe,
                                  settings.PLANO_STARTER_PRECO,
                                  settings.PLANO_PRO_PRECO,
                                  settings.PLANO_EQUIPE_PRECO)
    funil    = await obter_funil_hoje()
    latencia = await obter_latencias()
    erros    = await obter_erros_hoje()

    try:
        hoje = date.today().isoformat()
        novos_starter = int(await rate_limiter.redis.get(f"poda:conv:new:starter:{hoje}") or 0)
        novos_pro     = int(await rate_limiter.redis.get(f"poda:conv:new:pro:{hoje}") or 0)
        novos_equipe  = int(await rate_limiter.redis.get(f"poda:conv:new:equipe:{hoje}") or 0)
        churn_hoje    = int(await rate_limiter.redis.get(f"poda:churn:total:{hoje}") or 0)
    except Exception:
        novos_starter = novos_pro = novos_equipe = churn_hoje = 0

    site = await _stats_site()

    return {
        "planos":    {"free": free, "starter": starter, "pro": pro, "equipe": equipe},
        "financeiro": {**mrr, "novos_starter": novos_starter, "novos_pro": novos_pro,
                       "novos_equipe": novos_equipe, "churn_hoje": churn_hoje},
        "funil":    funil,
        "latencia": latencia,
        "erros":    erros,
        "site":     site,
    }


# ── Painel HTML ───────────────────────────────────────────────────────────────

def _html_comercial() -> str:
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Poda — Painel Comercial</title>
<style>
  :root{
    --green:#2e7d32;--green-light:#4caf50;--green-dark:#1b5e20;
    --bg:#f5f5f5;--card:#fff;--text:#212121;--sub:#757575;
    --red:#c62828;--amber:#e65100;--ok:#2e7d32;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--text);padding:20px}
  h1{color:var(--green-dark);font-size:1.5rem;margin-bottom:4px}
  .sub{color:var(--sub);font-size:.85rem;margin-bottom:24px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
  .card{background:var(--card);border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.1)}
  .card h2{font-size:.95rem;color:var(--sub);text-transform:uppercase;letter-spacing:.06em;margin-bottom:14px}
  .big{font-size:2.2rem;font-weight:700;color:var(--green-dark)}
  .row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #f0f0f0}
  .row:last-child{border-bottom:none}
  .label{color:var(--sub);font-size:.88rem}
  .val{font-weight:600}
  .badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.78rem;font-weight:600}
  .ok{background:#e8f5e9;color:var(--ok)}
  .warn{background:#fff3e0;color:var(--amber)}
  .err{background:#ffebee;color:var(--red)}
  .funnel{display:flex;align-items:flex-end;gap:8px;height:80px;margin-top:8px}
  .bar-wrap{display:flex;flex-direction:column;align-items:center;flex:1}
  .bar{width:100%;background:var(--green-light);border-radius:4px 4px 0 0;transition:height .4s}
  .bar-label{font-size:.7rem;color:var(--sub);margin-top:4px;text-align:center}
  .bar-val{font-size:.8rem;font-weight:600;color:var(--text);margin-top:2px}
  .spin{text-align:center;padding:40px;color:var(--sub)}
  a.back{display:inline-block;margin-bottom:16px;color:var(--green);text-decoration:none;font-size:.9rem}
  a.back:hover{text-decoration:underline}
</style>
</head>
<body>
<a class="back" href="/dashboard">&larr; Voltar ao painel principal</a>
<h1>&#x1F33F; Poda &mdash; Intelig&ecirc;ncia Comercial</h1>
<p class="sub" id="ts">Carregando dados...</p>

<div class="grid" id="grid"><p class="spin">&#x23F3; Carregando m&eacute;tricas...</p></div>

<script>
async function load(){
  try{
    const r = await fetch('/api/comercial', {credentials:'include'});
    if(r.status===401){ window.location.href='/dashboard'; return; }
    if(!r.ok){ document.getElementById('grid').innerHTML='<p class="spin">Erro ao carregar dados. Tente recarregar.</p>'; return; }
    const d = await r.json();
    render(d);
    document.getElementById('ts').textContent = 'Atualizado em ' + new Date().toLocaleTimeString('pt-BR');
  }catch(e){
    document.getElementById('grid').innerHTML='<p class="spin">Sem conex\xe3o com o servidor.</p>';
  }
}

function fmt_brl(v){ return 'R$ '+v.toFixed(2).replace('.',','); }

function render(d){
  const f = d.financeiro;
  const funil = d.funil;
  const lat = d.latencia;
  const err = d.erros;
  const pl = d.planos;

  const max_f = Math.max(funil.limite_atingido,1);
  function bar(val,label){
    const h = Math.max(8, Math.round(val/max_f*72));
    return '<div class="bar-wrap"><div class="bar-val">'+val+'</div><div class="bar" style="height:'+h+'px"></div><div class="bar-label">'+label+'</div></div>';
  }

  function lat_badge(ms){
    if(ms==null) return '<span class="badge ok">&mdash;</span>';
    const cls = ms<3000?'ok':ms<8000?'warn':'err';
    return '<span class="badge '+cls+'">'+ms+'ms</span>';
  }

  function lat_p95_badge(ms,ok_ms,warn_ms){
    if(ms==null) return '<span class="badge ok">&mdash;</span>';
    const cls = ms<ok_ms?'ok':ms<warn_ms?'warn':'err';
    return '<span class="badge '+cls+'">'+ms+'ms</span>';
  }

  const html =
  '<div class="card"><h2>&#x1F4B0; Receita Recorrente</h2>' +
  '<div class="big">'+fmt_brl(f.mrr)+'<span style="font-size:1rem;color:var(--sub)">/m\xeas</span></div>' +
  '<div class="row" style="margin-top:12px"><span class="label">ARR projetado</span><span class="val">'+fmt_brl(f.arr)+'</span></div>' +
  '<div class="row"><span class="label">Ticket m\xe9dio</span><span class="val">'+fmt_brl(f.ticket_medio)+'</span></div>' +
  '<div class="row"><span class="label">Total pagantes</span><span class="val">'+f.total_pagantes+'</span></div>' +
  '<div class="row"><span class="label">Novos Starter hoje</span><span class="val" style="color:var(--green)">+'+(f.novos_starter||0)+'</span></div>' +
  '<div class="row"><span class="label">Novos Pro hoje</span><span class="val" style="color:var(--green)">+'+f.novos_pro+'</span></div>' +
  '<div class="row"><span class="label">Novos Equipe hoje</span><span class="val" style="color:var(--green)">+'+f.novos_equipe+'</span></div>' +
  '<div class="row"><span class="label">Churn hoje</span><span class="val" style="color:'+(f.churn_hoje>0?'var(--red)':'var(--text)')+'">-'+f.churn_hoje+'</span></div></div>' +

  '<div class="card"><h2>&#x1F4CA; Assinantes por Plano</h2>' +
  '<div class="row"><span class="label">Free</span><span class="val">'+pl.free+'</span></div>' +
  '<div class="row"><span class="label">Starter &mdash; R$9/m\xeas</span><span class="val">'+(pl.starter||0)+'</span></div>' +
  '<div class="row"><span class="label">Pro &mdash; R$19/m\xeas</span><span class="val">'+pl.pro+'</span></div>' +
  '<div class="row"><span class="label">Equipe &mdash; R$79/m\xeas</span><span class="val">'+pl.equipe+'</span></div>' +
  '<div class="row" style="margin-top:8px"><span class="label">Taxa pago/total</span>' +
  '<span class="val">'+(pl.free+(pl.starter||0)+pl.pro+pl.equipe>0?(((pl.starter||0)+pl.pro+pl.equipe)/(pl.free+(pl.starter||0)+pl.pro+pl.equipe)*100).toFixed(1):0)+'%</span></div></div>' +

  '<div class="card"><h2>&#x1F504; Funil de Convers\xe3o &mdash; Hoje</h2>' +
  '<div class="funnel">'+bar(funil.limite_atingido,'Atingiram<br>limite')+bar(funil.intent_upgrade,'Pediram<br>/planos')+bar(funil.cpf_informado,'CPF<br>informado')+bar(funil.pix_gerado,'PIX<br>gerado')+bar(funil.pago,'Pago ✓')+'</div>' +
  '<div class="row" style="margin-top:12px"><span class="label">Abandono de PIX</span>' +
  '<span class="val"><span class="badge '+(funil.abandono_pct>60?'err':funil.abandono_pct>30?'warn':'ok')+'">'+funil.abandono_pct+'%</span></span></div></div>' +

  '<div class="card"><h2>&#x26A1; Velocidade de Respostas</h2>' +
  '<div class="row"><span class="label">URL &mdash; P50</span><span>'+lat_badge(lat.url&&lat.url.p50)+'</span></div>' +
  '<div class="row"><span class="label">URL &mdash; P95</span><span>'+lat_p95_badge(lat.url&&lat.url.p95,5000,10000)+'</span></div>' +
  '<div class="row"><span class="label">PDF &mdash; P50</span><span>'+lat_badge(lat.pdf&&lat.pdf.p50)+'</span></div>' +
  '<div class="row"><span class="label">PDF &mdash; P95</span><span>'+lat_p95_badge(lat.pdf&&lat.pdf.p95,8000,15000)+'</span></div>' +
  '<div class="row"><span class="label">Token &mdash; P50</span><span>'+lat_badge(lat.token&&lat.token.p50)+'</span></div>' +
  '<div class="row"><span class="label">Amostras (URL/PDF/Tkn)</span><span class="val" style="font-size:.85rem">'+((lat.url&&lat.url.amostras)||0)+' / '+((lat.pdf&&lat.pdf.amostras)||0)+' / '+((lat.token&&lat.token.amostras)||0)+'</span></div></div>' +

  '<div class="card"><h2>&#x1F41B; Erros &mdash; Hoje</h2>' +
  '<div class="row"><span class="label">URL timeout</span><span class="val">'+((err.url&&err.url.timeout)||0)+'</span></div>' +
  '<div class="row"><span class="label">URL parse_fail</span><span class="val">'+((err.url&&err.url.parse_fail)||0)+'</span></div>' +
  '<div class="row"><span class="label">PDF too_large</span><span class="val">'+((err.pdf&&err.pdf.too_large)||0)+'</span></div>' +
  '<div class="row"><span class="label">PDF parse_fail</span><span class="val">'+((err.pdf&&err.pdf.parse_fail)||0)+'</span></div>' +
  '<div class="row"><span class="label">PIX fail</span><span class="val">'+((err.pix&&err.pix.fail)||0)+'</span></div>' +
  '<div class="row" style="font-weight:700"><span>Total de erros</span>' +
  '<span class="badge '+(err.total===0?'ok':err.total<10?'warn':'err')+'">'+err.total+'</span></div></div>' +

  (d.site ? (
  '<div class="card"><h2>&#x1F310; Site poda.digital &mdash; Hoje</h2>' +
  '<div class="row"><span class="label">Visitas (pageviews)</span><span class="val">'+(d.site.pageview||0)+'</span></div>' +
  '<div class="row"><span class="label">Cliques em CTA (total)</span><span class="val">'+(d.site.cliques_total||0)+'</span></div>' +
  '<div class="row"><span class="label">&nbsp;&nbsp;Hero</span><span class="val">'+(d.site.cta_hero||0)+'</span></div>' +
  '<div class="row"><span class="label">&nbsp;&nbsp;Planos (S/P/E)</span><span class="val">'+(d.site.cta_planos_starter||0)+' / '+(d.site.cta_planos_pro||0)+' / '+(d.site.cta_planos_equipe||0)+'</span></div>' +
  '<div class="row"><span class="label">Chegaram no WhatsApp</span><span class="val" style="color:var(--green)">'+(d.site.chegou_whatsapp||0)+'</span></div>' +
  '<div class="row"><span class="label">Convers\xe3o visita&rarr;clique</span><span class="val">'+((d.site.pageview||0)>0?((d.site.cliques_total||0)/(d.site.pageview)*100).toFixed(1):0)+'%</span></div></div>'
  ) : '');

  document.getElementById('grid').innerHTML = html;
}

load();
setInterval(load, 30000);
</script>
</body>
</html>"""


@router.get("/dashboard/comercial", response_class=HTMLResponse)
async def painel_comercial(request: Request):
    """Painel HTML de inteligência comercial — exige cookie de sessão válido."""
    session_id = request.cookies.get(COOKIE_NAME, "")
    if not await _sessao_valida(session_id):
        return RedirectResponse(url="/dashboard", status_code=302)
    return HTMLResponse(content=_html_comercial())
