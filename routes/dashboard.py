"""
dashboard.py — Painel de monitoramento do Poda

Autenticação via cookie HttpOnly (sem token na URL ou no HTML).
Login: POST /dashboard/login  →  seta cookie de sessão seguro
Painel: GET /dashboard        →  exige cookie válido
API:    GET /api/metrics      →  exige cookie válido
"""

import logging
import secrets
import json as json_mod
from fastapi import APIRouter, Request, Form, HTTPException, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from services.metrics import obter_metricas
from config import settings

logger = logging.getLogger("poda.dashboard")
router = APIRouter()

# TTL da sessão em segundos (8 horas)
SESSION_TTL = 60 * 60 * 8
COOKIE_NAME = "poda_session"

# Proteção contra força bruta
MAX_TENTATIVAS_LOGIN = 5       # tentativas antes do bloqueio
LOCKOUT_TTL = 15 * 60         # bloqueio de 15 minutos


# ── helpers de sessão (Redis) ────────────────────────────────────────────────

SESSIONS_SET = "poda:sessions:active"  # R4: índice de sessões ativas


async def _criar_sessao() -> str:
    """Gera um session_id aleatório e armazena no Redis com TTL.
    R4: também adiciona ao SET de sessões ativas para revogação em massa.
    """
    from services.rate_limiter import rate_limiter
    session_id = secrets.token_urlsafe(32)
    if rate_limiter.redis:
        pipe = rate_limiter.redis.pipeline()
        pipe.setex(f"poda:session:{session_id}", SESSION_TTL, "1")
        pipe.sadd(SESSIONS_SET, session_id)
        await pipe.execute()
    return session_id


async def _destruir_sessao(session_id: str) -> None:
    """R4: Remove sessão do Redis e do índice de sessões ativas."""
    from services.rate_limiter import rate_limiter
    if rate_limiter.redis and session_id:
        try:
            pipe = rate_limiter.redis.pipeline()
            pipe.delete(f"poda:session:{session_id}")
            pipe.srem(SESSIONS_SET, session_id)
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Erro ao destruir sessão {session_id[:8]}…: {e}")


async def _sessao_valida(session_id: str) -> bool:
    """Verifica se o session_id existe no Redis."""
    if not session_id:
        return False
    from services.rate_limiter import rate_limiter
    if rate_limiter.redis:
        val = await rate_limiter.redis.get(f"poda:session:{session_id}")
        return val is not None
    # Fallback sem Redis: nega sempre (seguro por padrão)
    return False


# ── helpers de força bruta ───────────────────────────────────────────────────

async def _checar_bloqueio(ip: str) -> bool:
    """Retorna True se o IP está temporariamente bloqueado por excesso de tentativas."""
    from services.rate_limiter import rate_limiter
    if not rate_limiter.redis:
        return False
    val = await rate_limiter.redis.get(f"poda:login:fails:{ip}")
    return val is not None and int(val) >= MAX_TENTATIVAS_LOGIN


async def _registrar_falha(ip: str) -> int:
    """Incrementa contador de falhas do IP. Retorna tentativas restantes antes do bloqueio."""
    from services.rate_limiter import rate_limiter
    if not rate_limiter.redis:
        return MAX_TENTATIVAS_LOGIN
    key = f"poda:login:fails:{ip}"
    pipe = rate_limiter.redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, LOCKOUT_TTL)
    results = await pipe.execute()
    tentativas_feitas = int(results[0])
    return max(0, MAX_TENTATIVAS_LOGIN - tentativas_feitas)


async def _limpar_falhas(ip: str) -> None:
    """Remove o contador de falhas após login bem-sucedido."""
    from services.rate_limiter import rate_limiter
    if rate_limiter.redis:
        await rate_limiter.redis.delete(f"poda:login:fails:{ip}")


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    session_id = request.cookies.get(COOKIE_NAME, "")
    if not await _sessao_valida(session_id):
        return HTMLResponse(content=_html_login(erro=False), status_code=200)
    return HTMLResponse(content=_html_dashboard(), media_type="text/html; charset=utf-8")


@router.post("/dashboard/login")
async def dashboard_login(
    request: Request,
    usuario: str = Form(""),
    senha: str = Form(""),
):
    """Autentica com usuário+senha e seta cookie de sessão HttpOnly.
    Protegido contra força bruta: bloqueia IP após 5 tentativas falhas por 15 min.
    """
    ip = request.client.host if request.client else "?"

    # Checar bloqueio por força bruta antes de qualquer validação
    if await _checar_bloqueio(ip):
        logger.warning("IP bloqueado tentou login: %s", ip)
        return HTMLResponse(content=_html_login(bloqueado=True), status_code=429)

    dashboard_user = settings.DASHBOARD_USER
    dashboard_password = settings.DASHBOARD_PASSWORD

    # Fail-secure: se credenciais não configuradas no Railway, nega acesso
    if not dashboard_user or not dashboard_password:
        logger.error("DASHBOARD_USER ou DASHBOARD_PASSWORD não configurados no Railway.")
        return HTMLResponse(content=_html_login(erro=True), status_code=200)

    # Comparação em tempo constante (previne timing attacks)
    try:
        user_ok = secrets.compare_digest(usuario.encode("utf-8"), dashboard_user.encode("utf-8"))
        pass_ok = secrets.compare_digest(senha.encode("utf-8"), dashboard_password.encode("utf-8"))
    except Exception:
        user_ok = False
        pass_ok = False

    if not (user_ok and pass_ok):
        restantes = await _registrar_falha(ip)
        logger.warning("Login inválido. IP: %s. Tentativas restantes: %d", ip, restantes)
        bloqueado = restantes == 0
        return HTMLResponse(
            content=_html_login(erro=True, tentativas_restantes=restantes, bloqueado=bloqueado),
            status_code=200,
        )

    # Login bem-sucedido: limpa contagem de falhas e cria sessão
    await _limpar_falhas(ip)
    session_id = await _criar_sessao()
    logger.info("Login bem-sucedido. IP: %s", ip)
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=SESSION_TTL,
        path="/",
    )
    return response


@router.post("/dashboard/logout")
async def dashboard_logout(request: Request):
    """R4: Remove sessão do Redis e do índice de sessões ativas."""
    session_id = request.cookies.get(COOKIE_NAME, "")
    await _destruir_sessao(session_id)
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/api/metrics")
async def api_metrics(request: Request):
    session_id = request.cookies.get(COOKIE_NAME, "")
    if not await _sessao_valida(session_id):
        return JSONResponse(status_code=401, content={"erro": "Não autenticado"})
    dados = await obter_metricas()
    return dados


@router.post("/dashboard/logout-all")
async def dashboard_logout_all(request: Request):
    """R4: Invalida TODAS as sessões ativas — útil em caso de comprometimento de credenciais.
    Requer autenticação (cookie válido) para evitar logout DoS não autenticado.
    """
    session_id = request.cookies.get(COOKIE_NAME, "")
    if not await _sessao_valida(session_id):
        return JSONResponse(status_code=401, content={"erro": "Não autenticado"})

    from services.rate_limiter import rate_limiter
    invalidadas = 0
    if rate_limiter.redis:
        try:
            membros = await rate_limiter.redis.smembers(SESSIONS_SET)
            if membros:
                pipe = rate_limiter.redis.pipeline()
                for sid in membros:
                    pipe.delete(f"poda:session:{sid}")
                pipe.delete(SESSIONS_SET)
                await pipe.execute()
                invalidadas = len(membros)
                logger.warning(f"logout-all executado: {invalidadas} sessões invalidadas.")
        except Exception as e:
            logger.error(f"Erro em logout-all: {e}")
            return JSONResponse(status_code=500, content={"erro": "Falha ao invalidar sessões."})

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.post("/api/metrics/reset")
async def api_metrics_reset(request: Request):
    """R1: Zera contadores globais de métricas. Requer autenticação de dashboard.
    Útil para limpar dados de staging/teste sem precisar de KEYS bloqueante.
    """
    session_id = request.cookies.get(COOKIE_NAME, "")
    if not await _sessao_valida(session_id):
        return JSONResponse(status_code=401, content={"erro": "Não autenticado"})

    from services.rate_limiter import rate_limiter
    if not rate_limiter.redis:
        return JSONResponse(status_code=503, content={"erro": "Redis indisponível."})

    CHAVES_GLOBAIS = [
        "poda:metrics:msgs_recebidas",
        "poda:metrics:msgs_enviadas",
        "poda:metrics:erros",
        "poda:metrics:ultimo_evento",
        "poda:metrics:inicio",
        "poda:metrics:tipos:url",
        "poda:metrics:tipos:pdf",
        "poda:metrics:tipos:texto",
        "poda:metrics:tipos:comando",
        "poda:metrics:tipos:saudacao",
        "poda:metrics:tipos:invalido",
    ]
    try:
        await rate_limiter.redis.delete(*CHAVES_GLOBAIS)
        logger.warning("Métricas globais resetadas via /api/metrics/reset.")
        return JSONResponse(content={"ok": True, "chaves_removidas": len(CHAVES_GLOBAIS)})
    except Exception as e:
        logger.error(f"Erro ao resetar métricas: {e}")
        return JSONResponse(status_code=500, content={"erro": str(e)})


# ── HTML: tela de login ──────────────────────────────────────────────────────

def _html_login(
    erro: bool = False,
    tentativas_restantes: int = MAX_TENTATIVAS_LOGIN,
    bloqueado: bool = False,
) -> str:
    if bloqueado:
        aviso_html = (
            '<div class="aviso bloqueado">'
            '🔒 Muitas tentativas. Aguarde 15 minutos e tente novamente.'
            '</div>'
        )
    elif erro and tentativas_restantes <= 0:
        aviso_html = (
            '<div class="aviso bloqueado">'
            '🔒 Acesso bloqueado por 15 minutos.'
            '</div>'
        )
    elif erro and tentativas_restantes <= 2:
        aviso_html = (
            f'<div class="aviso erro">'
            f'Usuário ou senha inválidos. '
            f'Restam {tentativas_restantes} tentativa(s).'
            f'</div>'
        )
    elif erro:
        aviso_html = '<div class="aviso erro">Usuário ou senha inválidos.</div>'
    else:
        aviso_html = ''

    btn_disabled = 'disabled' if bloqueado else ''

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Poda — Acesso ao Painel</title>
<!-- PWA / iPhone Home Screen -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Poda Admin">
<meta name="theme-color" content="#0f1117">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f1117; color: #e2e8f0;
    min-height: 100vh; display: flex;
    align-items: center; justify-content: center;
    padding: 20px;
  }}
  .card {{
    background: #1a1f2e; border: 1px solid #2d3748;
    border-radius: 16px; padding: 40px 36px;
    width: 100%; max-width: 360px; text-align: center;
  }}
  .logo {{ font-size: 3rem; margin-bottom: 12px; }}
  h1 {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 4px; }}
  .sub {{ font-size: 0.85rem; color: #8b95a7; margin-bottom: 28px; }}
  .campo {{ margin-bottom: 14px; text-align: left; }}
  label {{ display: block; font-size: 0.78rem; color: #8b95a7; margin-bottom: 5px; }}
  input {{
    width: 100%; padding: 11px 14px;
    background: #0f1117; border: 1px solid #2d3748;
    border-radius: 8px; color: #e2e8f0; font-size: 0.95rem;
    outline: none; transition: border-color 0.2s;
  }}
  input:focus {{ border-color: #22c55e; }}
  input:focus-visible {{ border-color: #22c55e; outline: none; }}
  button[type=submit] {{
    width: 100%; padding: 12px; margin-top: 6px;
    background: #22c55e; color: #0f1117;
    border: none; border-radius: 8px;
    font-size: 0.95rem; font-weight: 700;
    cursor: pointer; transition: background 0.2s;
  }}
  button[type=submit]:hover:not(:disabled) {{ background: #16a34a; }}
  button[type=submit]:disabled {{ background: #2d3748; color: #6b7280; cursor: not-allowed; }}
  :focus-visible {{ outline: 2px solid #4ade80; outline-offset: 3px; border-radius: 4px; }}
  .aviso {{
    margin-top: 14px; padding: 9px 12px;
    border-radius: 8px; font-size: 0.82rem; text-align: left;
  }}
  .aviso.erro {{ background: #450a0a; border: 1px solid #991b1b; color: #fca5a5; }}
  .aviso.bloqueado {{ background: #1c1410; border: 1px solid #92400e; color: #fbbf24; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">🌿</div>
  <h1>Poda</h1>
  <p class="sub">Painel de monitoramento</p>
  <form method="POST" action="/dashboard/login" autocomplete="on">
    <div class="campo">
      <label for="usuario-input">Usuário</label>
      <input type="text" id="usuario-input" name="usuario"
             placeholder="seu_usuario" autocomplete="username"
             {'disabled' if bloqueado else ''} required>
    </div>
    <div class="campo">
      <label for="senha-input">Senha</label>
      <input type="password" id="senha-input" name="senha"
             placeholder="••••••••" autocomplete="current-password"
             {'disabled' if bloqueado else ''} required>
    </div>
    <button type="submit" {btn_disabled}>
      {'🔒 Bloqueado' if bloqueado else 'Entrar'}
    </button>
  </form>
  {aviso_html}
</div>
<script>
  // Auto-foco no campo usuário ao carregar
  document.getElementById('usuario-input') &&
    document.getElementById('usuario-input').focus();
</script>
</body>
</html>"""


# ── HTML: dashboard principal ────────────────────────────────────────────────

def _html_dashboard() -> str:
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Poda — Painel</title>
<!-- PWA / iPhone Home Screen -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Poda Admin">
<meta name="theme-color" content="#0f1117">
<link rel="stylesheet" href="/static/design-tokens.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
  integrity="sha512-ZwR1/gSZM3ai6vCdI+LVF1zSq/5HznD3oD+sCoJrzXJ+yKoAClMLqJ47L0O0zKkaE8TMR78kOzFW9kUnNB2A=="
  crossorigin="anonymous" referrerpolicy="no-referrer"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    /* W1: tokens herdados de design-tokens.css — apenas override genuíno do dashboard */
    --border: var(--border-solid); /* dashboard usa borda sólida; landing usa rgba translúcida */
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg); color: var(--text); min-height: 100vh; }
  .header {
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 14px 24px; display: flex; align-items: center;
    justify-content: space-between;
  }
  .header-left { display: flex; align-items: center; gap: 10px; }
  .logo-text { font-size: 1.3rem; font-weight: 800; }
  .badge { background: var(--accent-muted); color: var(--green);
    font-size: 0.7rem; padding: 3px 8px; border-radius: var(--radius-pill); font-weight: 600; }
  .header-right { display: flex; align-items: center; gap: 16px; }
  .hora { font-size: 0.8rem; color: var(--muted); }
  .btn-logout {
    font-size: 0.75rem; color: var(--muted); background: none;
    border: 1px solid var(--border); border-radius: var(--radius-sm);
    padding: 4px 10px; cursor: pointer; text-decoration: none;
  }
  .btn-logout:hover { color: var(--red); border-color: var(--red); }
  .btn-logout:active { opacity: 0.8; }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 4px; }
  .periodo-btn:focus-visible { outline: 2px solid var(--green); outline-offset: 2px; }
  .container { max-width: 1100px; margin: 0 auto; padding: 28px 20px; }
  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 28px; }
  .kpi { background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 20px 18px; }
  .kpi-label { font-size: var(--text-xs); color: var(--muted); margin-bottom: 8px; }
  .kpi-val { font-size: 1.9rem; font-weight: 800; }
  .kpi-trend { font-size: var(--text-xs); margin-top: 6px; height: 16px; }
  .kpi-trend.up { color: var(--green); }
  .kpi-trend.down { color: var(--red); }
  .kpi-trend.flat { color: var(--muted); }
  .periodo-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 20px; }
  .periodo-label { font-size: var(--text-xs); color: var(--muted); }
  .periodo-btn {
    font-size: var(--text-xs); padding: 5px 14px; border-radius: var(--radius-pill);
    border: 1px solid var(--border); background: none; color: var(--muted);
    cursor: pointer; transition: all 0.15s;
  }
  .periodo-btn:hover { border-color: var(--green); color: var(--text); }
  .periodo-btn.active { background: var(--green); color: #000; border-color: var(--green); font-weight: 700; }
  #empty-state { text-align: center; padding: 60px 20px; }
  .empty-icon { font-size: 2.5rem; margin-bottom: 12px; }
  #empty-state p { font-size: 1rem; font-weight: 600; margin-bottom: 6px; }
  #empty-state span { font-size: 0.85rem; color: var(--muted); }
  .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 28px; }
  @media (max-width: 700px) { .charts { grid-template-columns: 1fr; } }
  .card { background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 20px; }
  .card h3 { font-size: var(--text-sm); color: var(--muted); margin-bottom: 16px; text-transform: uppercase; letter-spacing: .05em; }
  .tipos-list { display: grid; gap: 10px; }
  .tipo-row { display: flex; align-items: center; gap: 10px; }
  .tipo-emoji { font-size: 1.1rem; width: 28px; text-align: center; }
  .tipo-nome { font-size: 0.85rem; flex: 1; }
  .tipo-bar-wrap { flex: 2; background: #ffffff10; border-radius: 4px; height: 6px; overflow: hidden; }
  .tipo-bar { height: 100%; border-radius: 4px; transition: width .6s; }
  .tipo-val { font-size: 0.85rem; font-weight: 700; min-width: 36px; text-align: right; }
  .hist-wrap { position: relative; height: 200px; }
  .footer { text-align: center; color: var(--muted); font-size: 0.75rem; padding: 24px; }
  /* Skeleton loader */
  .skel { border-radius: 4px; background: #ffffff0a; animation: shimmer 1.4s ease-in-out infinite; }
  @keyframes shimmer { 0%,100%{opacity:.4} 50%{opacity:.9} }

  /* Toast */
  #toast-container { position: fixed; bottom: 24px; right: 24px; display: flex; flex-direction: column; gap: 8px; z-index: 9999; pointer-events: none; }
  .toast-item { padding: 10px 16px; border-radius: 8px; font-size: 13px; display: flex; gap: 8px; align-items: center; pointer-events: all; animation: slideUp .25s ease; max-width: 320px; }
  .toast-success { background: #052e16; border: 1px solid #166534; color: #86efac; }
  .toast-error   { background: #450a0a; border: 1px solid #991b1b; color: #fca5a5; }
  .toast-info    { background: #0c1a2e; border: 1px solid #1e3a8a; color: #93c5fd; }
  @keyframes slideUp { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }

  /* Modal de confirmação */
  #confirm-modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1000; align-items: center; justify-content: center; }
  .modal-inner { background: #1a1f2e; border: 1px solid #2d3748; border-radius: 12px; padding: 24px; max-width: 360px; width: 90%; }
  .modal-title { font-size: 15px; font-weight: 700; margin-bottom: 8px; color: var(--text); }
  .modal-body-text { font-size: 13px; color: var(--muted); margin-bottom: 20px; line-height: 1.5; }
  .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
  .btn-mc { padding: 7px 14px; font-size: 13px; border-radius: 8px; cursor: pointer; font-family: inherit; }
  .btn-mc-cancel { background: none; border: 1px solid #2d3748; color: var(--muted); }
  .btn-mc-cancel:hover { color: var(--text); border-color: #4a5568; }
  .btn-mc-confirm { background: #ef4444; border: none; color: #fff; font-weight: 700; }
  .btn-mc-confirm:hover { background: #dc2626; }

  /* Barra de saúde */
  #health-bar { display: flex; align-items: center; gap: 14px; padding: 6px 24px; border-bottom: 1px solid var(--border); font-size: 11px; color: var(--muted); }
  .h-svc { display: flex; align-items: center; gap: 5px; }
  .h-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: #4b5563; }

  /* Botões de ação no header */
  .btn-action { font-size: 0.72rem; color: var(--muted); background: none; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 4px 10px; cursor: pointer; font-family: inherit; transition: color .15s, border-color .15s; }
  .btn-action:hover { color: #eab308; border-color: #eab308; }
  .btn-action.danger:hover { color: var(--red, #ef4444); border-color: var(--red, #ef4444); }

  #loading { padding: 20px 0; }
  #conteudo { display: none; }
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <span class="logo-text">🌿 Poda</span>
    <span class="badge">LIVE</span>
  </div>
  <div class="header-right">
    <span class="hora" id="hora-atual"></span>
    <button class="btn-action" onclick="confirmarAcao('Redefinir métricas?','Os contadores globais serão zerados. Esta ação não pode ser desfeita.',resetarMetricas)">Redefinir métricas</button>
    <button class="btn-action danger" onclick="confirmarAcao('Encerrar todas as sessões?','Todos os administradores serão desconectados imediatamente.',encerrarTodasSessoes)">Encerrar sessões</button>
    <form method="POST" action="/dashboard/logout" style="margin:0">
      <button type="submit" class="btn-logout">Sair</button>
    </form>
  </div>
</div>

<div id="health-bar" role="status" aria-live="polite">
  <span class="h-svc"><span class="h-dot" id="dot-redis"></span><span id="lbl-redis">Redis…</span></span>
  <span style="color:#2d3748">|</span>
  <span class="h-svc"><span class="h-dot" id="dot-asaas"></span><span id="lbl-asaas">Asaas…</span></span>
</div>

<div class="container">
  <!-- Seletor de período (item 4.2) -->
  <div class="periodo-bar">
    <span class="periodo-label">Período:</span>
    <button class="periodo-btn active" data-dias="0" onclick="selecionarPeriodo(0)">Hoje</button>
    <button class="periodo-btn" data-dias="7" onclick="selecionarPeriodo(7)">7 dias</button>
    <button class="periodo-btn" data-dias="30" onclick="selecionarPeriodo(30)">30 dias</button>
  </div>

  <div id="loading">
    <div class="kpi-grid">
      <div class="kpi"><div class="skel" style="height:11px;width:65%;margin-bottom:10px"></div><div class="skel" style="height:30px;width:40%"></div></div>
      <div class="kpi"><div class="skel" style="height:11px;width:55%;margin-bottom:10px"></div><div class="skel" style="height:30px;width:50%"></div></div>
      <div class="kpi"><div class="skel" style="height:11px;width:70%;margin-bottom:10px"></div><div class="skel" style="height:30px;width:35%"></div></div>
      <div class="kpi"><div class="skel" style="height:11px;width:60%;margin-bottom:10px"></div><div class="skel" style="height:30px;width:45%"></div></div>
      <div class="kpi"><div class="skel" style="height:11px;width:50%;margin-bottom:10px"></div><div class="skel" style="height:30px;width:38%"></div></div>
    </div>
  </div>

  <!-- Estado vazio (item 4.5) -->
  <div id="empty-state" style="display:none">
    <div class="empty-icon">📭</div>
    <p>Nenhum dado ainda hoje.</p>
    <span>As métricas aparecem assim que o primeiro usuário interagir.</span>
  </div>

  <div id="conteudo">
    <!-- KPIs com tendência (item 4.1) -->
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-label">Msgs hoje</div>
        <div class="kpi-val" id="msgs-hoje">—</div>
        <div class="kpi-trend" id="trend-msgs-hoje"></div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Usuários hoje</div>
        <div class="kpi-val" id="usuarios-hoje">—</div>
        <div class="kpi-trend" id="trend-usuarios-hoje"></div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Enviadas</div>
        <div class="kpi-val" id="msgs-enviadas">—</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Total recebidas</div>
        <div class="kpi-val" id="msgs-total">—</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Erros</div>
        <div class="kpi-val" id="erros" style="color:var(--red)">—</div>
      </div>
    </div>
    <div class="charts">
      <div class="card">
        <h3>Tipos de conteúdo</h3>
        <div class="tipos-list" id="tipos-list"></div>
      </div>
      <div class="card">
        <h3 id="hist-titulo">Histórico 7 dias</h3>
        <div class="hist-wrap"><canvas id="chart-hist"></canvas></div>
      </div>
    </div>
  </div>
</div>

<footer class="footer">
  Poda · Painel de monitoramento · Atualização a cada 30 segundos
</footer>

<script>
let chartHist = null;
let periodoAtual = 0; // 0 = hoje, 7 = 7 dias, 30 = 30 dias

function atualizarHora() {
  document.getElementById('hora-atual').textContent =
    new Date().toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
}
atualizarHora();
setInterval(atualizarHora, 1000);

function fmt(n) { return n == null ? '—' : Number(n).toLocaleString('pt-BR'); }
function cssVar(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

function animarNumero(el, valor, sufixo) {
  sufixo = sufixo || '';
  const duracao = 600, inicio = performance.now(), meta = Number(valor) || 0;
  function passo(agora) {
    const p = Math.min((agora - inicio) / duracao, 1);
    el.textContent = fmt(Math.round(meta * (1 - Math.pow(1 - p, 3)))) + sufixo;
    if (p < 1) requestAnimationFrame(passo);
  }
  requestAnimationFrame(passo);
}

// item 4.1 — tendência vs dia anterior
function renderTrend(elId, hoje, ontem) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (ontem === 0) { el.className = 'kpi-trend flat'; el.textContent = ''; return; }
  const diff = hoje - ontem;
  const pct = Math.round(Math.abs(diff) / ontem * 100);
  if (diff > 0)      { el.className = 'kpi-trend up';   el.textContent = `↑ ${pct}% vs ontem`; }
  else if (diff < 0) { el.className = 'kpi-trend down'; el.textContent = `↓ ${pct}% vs ontem`; }
  else               { el.className = 'kpi-trend flat'; el.textContent = '= igual a ontem'; }
}

// item 4.2 — seleção de período
function selecionarPeriodo(dias) {
  periodoAtual = dias;
  document.querySelectorAll('.periodo-btn').forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.dias) === dias);
  });
  carregar();
}

const TIPOS_CONFIG = [
  { chave: 'url',      nome: 'URLs processadas',  emoji: '🔗', cor: cssVar('--blue') },
  { chave: 'pdf',      nome: 'PDFs processados',  emoji: '📄', cor: cssVar('--purple') },
  { chave: 'texto',    nome: 'Textos analisados', emoji: '📝', cor: cssVar('--teal') },
  { chave: 'comando',  nome: 'Comandos usados',   emoji: '⚡', cor: cssVar('--yellow') },
  { chave: 'saudacao', nome: 'Saudações',         emoji: '👋', cor: cssVar('--pink') },
  { chave: 'invalido', nome: 'Não reconhecidos',  emoji: '❓', cor: cssVar('--slate') },
];

async function carregar() {
  try {
    const r = await fetch('/api/metrics', { credentials: 'same-origin' });
    if (r.status === 401) { window.location.href = '/dashboard'; return; }
    if (!r.ok) throw new Error('Erro ' + r.status);
    const d = await r.json();

    document.getElementById('loading').style.display = 'none';

    const hist = d.historico_7_dias || [];

    const vazio = (d.msgs_hoje ?? 0) === 0 && (d.usuarios_hoje ?? 0) === 0 &&
                  (d.msgs_recebidas ?? 0) === 0;
    document.getElementById('empty-state').style.display = vazio ? 'block' : 'none';
    document.getElementById('conteudo').style.display = vazio ? 'none' : 'block';

    if (vazio) return;

    let msgsKpi, usuariosKpi;
    if (periodoAtual === 0) {
      msgsKpi = d.msgs_hoje ?? 0;
      usuariosKpi = d.usuarios_hoje ?? 0;
    } else {
      const fatia = hist.slice(-periodoAtual);
      msgsKpi = fatia.reduce((s, h) => s + h.mensagens, 0);
      usuariosKpi = fatia.reduce((s, h) => s + h.usuarios, 0);
    }

    animarNumero(document.getElementById('msgs-hoje'), msgsKpi);
    animarNumero(document.getElementById('usuarios-hoje'), usuariosKpi);
    animarNumero(document.getElementById('msgs-enviadas'), d.msgs_enviadas ?? 0);
    animarNumero(document.getElementById('msgs-total'), d.msgs_recebidas ?? 0);
    animarNumero(document.getElementById('erros'), d.erros ?? 0);

    if (hist.length >= 2) {
      const ontem = hist[hist.length - 2];
      const anteontem = hist.length >= 3 ? hist[hist.length - 3] : { mensagens: 0, usuarios: 0 };
      renderTrend('trend-msgs-hoje', ontem.mensagens, anteontem.mensagens);
      renderTrend('trend-usuarios-hoje', ontem.usuarios, anteontem.usuarios);
    }

    const tipos = d.tipos || {};
    const totalTipos = TIPOS_CONFIG.reduce((s, tc) => s + (tipos[tc.chave] ?? 0), 0) || 1;
    document.getElementById('tipos-list').innerHTML = TIPOS_CONFIG.map(tc => {
      const qtd = tipos[tc.chave] ?? 0;
      const pct = Math.round(qtd / totalTipos * 100);
      return `<div class="tipo-row">
        <span class="tipo-emoji">${tc.emoji}</span>
        <span class="tipo-nome">${tc.nome}</span>
        <div class="tipo-bar-wrap">
          <div class="tipo-bar" style="width:${pct}%;background:${tc.cor}"></div>
        </div>
        <span class="tipo-val">${fmt(qtd)}</span>
      </div>`;
    }).join('');

    const fatiaHist = periodoAtual === 0 ? hist.slice(-1) : hist.slice(-Math.min(periodoAtual, hist.length));
    const labels = fatiaHist.map(h => { const [,m,d2] = h.data.split('-'); return d2+'/'+m; });
    document.getElementById('hist-titulo').textContent =
      periodoAtual === 0 ? 'Hoje (histórico)' : `Últimos ${periodoAtual} dias`;

    if (chartHist) chartHist.destroy();
    chartHist = new Chart(document.getElementById('chart-hist'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Mensagens', data: fatiaHist.map(h => h.mensagens),
            backgroundColor: '#3b82f644', borderColor: '#3b82f6',
            borderWidth: 2, borderRadius: 4,
          },
          {
            label: 'Usuários', data: fatiaHist.map(h => h.usuarios),
            type: 'line', borderColor: cssVar('--green'), backgroundColor: 'transparent',
            borderWidth: 2, tension: 0.4, pointRadius: 3, pointBackgroundColor: cssVar('--green'),
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: cssVar('--muted'), font: { size: 11 }, padding: 12, boxWidth: 12 } },
        },
        scales: {
          x: { ticks: { color: cssVar('--muted'), font: { size: 10 } }, grid: { color: '#ffffff08' } },
          y: { ticks: { color: cssVar('--muted'), font: { size: 10 } }, grid: { color: '#ffffff08' }, beginAtZero: true },
        },
      },
    });

  } catch (e) {
    document.getElementById('loading').textContent = '❌ Erro ao carregar: ' + e.message;
  }
}

// ── Toast
function showToast(msg, tipo) {
  tipo = tipo || 'success';
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  const item = document.createElement('div');
  item.className = 'toast-item toast-' + tipo;
  item.textContent = (icons[tipo] || '') + ' ' + msg;
  document.getElementById('toast-container').appendChild(item);
  setTimeout(() => item.remove(), 3800);
}

// ── Modal de confirmação
function confirmarAcao(titulo, corpo, fn) {
  document.getElementById('modal-title').textContent = titulo;
  document.getElementById('modal-body').textContent = corpo;
  document.getElementById('modal-confirm-btn').onclick = () => { closeModal(); fn(); };
  document.getElementById('confirm-modal').style.display = 'flex';
}
function closeModal() {
  document.getElementById('confirm-modal').style.display = 'none';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── Ações protegidas
async function encerrarTodasSessoes() {
  try {
    const r = await fetch('/dashboard/logout-all', { method: 'POST', credentials: 'same-origin' });
    if (r.ok || r.redirected) {
      showToast('Todas as sessões encerradas.', 'info');
      setTimeout(() => { window.location.href = '/dashboard'; }, 1600);
    } else {
      showToast('Erro ao encerrar sessões (status ' + r.status + ').', 'error');
    }
  } catch (e) { showToast('Falha na requisição.', 'error'); }
}
async function resetarMetricas() {
  try {
    const r = await fetch('/api/metrics/reset', { method: 'POST', credentials: 'same-origin' });
    const d = await r.json();
    if (d.ok) { showToast('Métricas zeradas com sucesso.', 'success'); setTimeout(carregar, 800); }
    else { showToast(d.erro || 'Erro ao redefinir.', 'error'); }
  } catch (e) { showToast('Falha na requisição.', 'error'); }
}

// ── Verificação de saúde
function setDot(dotId, lblId, label, ok) {
  document.getElementById(dotId).style.background = ok ? '#22c55e' : '#ef4444';
  document.getElementById(lblId).textContent = label + ': ' + (ok ? 'online' : 'offline');
}
async function checkHealth() {
  try {
    const r = await fetch('/api/metrics', { credentials: 'same-origin' });
    setDot('dot-redis', 'lbl-redis', 'Redis', r.ok);
    setDot('dot-asaas', 'lbl-asaas', 'Asaas', r.ok);
  } catch (e) {
    setDot('dot-redis', 'lbl-redis', 'Redis', false);
    setDot('dot-asaas', 'lbl-asaas', 'Asaas', false);
  }
}

checkHealth();
setInterval(checkHealth, 60000);
carregar();
setInterval(carregar, 30000);
</script>

<div id="toast-container" aria-live="polite" aria-atomic="true"></div>

<div id="confirm-modal" role="dialog" aria-modal="true" onclick="if(event.target===this)closeModal()">
  <div class="modal-inner">
    <div class="modal-title" id="modal-title"></div>
    <div class="modal-body-text" id="modal-body"></div>
    <div class="modal-actions">
      <button class="btn-mc btn-mc-cancel" onclick="closeModal()">Cancelar</button>
      <button class="btn-mc btn-mc-confirm" id="modal-confirm-btn">Confirmar</button>
    </div>
  </div>
</div>
</body>
</html>"""
