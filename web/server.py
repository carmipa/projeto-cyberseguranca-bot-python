"""
Web Server module using aiohttp.
Integrates directly with the bot loop.
"""
import logging
from aiohttp import web
import aiohttp_jinja2
import jinja2

from core.stats import stats
from utils.storage import p

log = logging.getLogger("MaftyWeb")

routes = web.RouteTableDef()

@routes.get('/')
async def index(request):
    """Renderiza a página inicial."""
    return aiohttp_jinja2.render_template('index.html', request, {})

@routes.get('/api/stats')
async def api_stats(request):
    """API JSON para atualizar status via AJAX."""
    return web.json_response({
        "uptime": stats.format_uptime(),
        "scans": stats.scans_completed,
        "news_posted": stats.news_posted,
        "cache_hits": stats.cache_hits_total,
        "last_scan": stats.last_scan_time.isoformat() if stats.last_scan_time else "Never"
    })


@routes.post('/api/sync_from_discord')
async def api_sync_from_discord(request):
    """
    Sincroniza notícias já publicadas no Discord para database.json.
    Chamado para popular o painel Windows com o histórico do canal.
    """
    bot = getattr(api_sync_from_discord, "_bot", None)
    if not bot:
        return web.json_response({"status": "error", "detail": "Bot não disponível"}, status=503)
    try:
        from utils.discord_sync import sync_from_discord
        added = await sync_from_discord(bot)
        return web.json_response({"status": "ok", "added": added})
    except Exception as e:
        log.exception(f"❌ Erro ao sincronizar do Discord: {e}")
        return web.json_response({"status": "error", "detail": "falha no sync; ver log"}, status=500)


@routes.post('/api/trigger_scan')
async def api_trigger_scan(request):
    """
    Dispara varredura manual. Chamado pela vps_api quando o painel Windows
    clica em 'Executar NOW (Scanner)'.
    """
    bot = getattr(api_trigger_scan, "_bot", None)
    if not bot:
        log.warning("⚠️ Bot não disponível para trigger_scan")
        return web.json_response({"status": "error", "detail": "Bot não inicializado"}, status=503)
    # Porta única, SEM bypass: antes cada clique em "Executar NOW" no painel
    # repostava tudo dos últimos 7 dias em todas as guilds.
    from bot.permissoes import solicitar_varredura_manual
    ok, texto = await solicitar_varredura_manual(bot, "api_now")
    return web.json_response({"status": "ok" if ok else "recusado", "detail": texto}, status=200 if ok else 429)

# =========================================================
# ACTIVE DEFENSE (HONEYPOT)
# =========================================================

async def intruder_response(request, attempt_type="Unknown"):
    """
    Resposta padrão para tentativas de intrusão.
    Loga o IP e retorna 403.
    """
    peername = request.transport.get_extra_info('peername')
    ip = peername[0] if peername else "Unknown"
    
    log.warning("⚠️ TENTATIVA DE INTRUSÃO DETECTADA!")
    log.warning(f"Origem: {ip} | Alvo: {request.path} | Tipo: {attempt_type}")
    log.warning("MENSAGEM: 'O malandro se acha malandro até achar um malandro melhor.'")
    
    # Aqui poderíamos adicionar lógica de ban automático no firewall
    
    return web.Response(text="⛔ ACESSO NEGADO: Sistema de Defesa Ativa acionado. Seu IP foi registrado.", status=403)

@routes.get('/admin')
@routes.get('/admin/')
@routes.get('/wp-login.php')
@routes.get('/.env')
@routes.get('/config.json')
async def honeypot_routes(request):
    """Rotas armadilha para pegar scanners e curiosos."""
    return await intruder_response(request, attempt_type="Honeypot Trap")


async def start_web_server(bot=None, host='0.0.0.0', port=8080):  # nosec B104 - dentro do contêiner; o compose publica só em 127.0.0.1
    """Inicia o servidor web aiohttp. Recebe bot para endpoints /api/trigger_scan e /api/sync_from_discord."""
    if bot:
        api_trigger_scan._bot = bot
        api_sync_from_discord._bot = bot
    app = web.Application()
    
    # Configura templates
    template_dir = p("web/templates")
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(template_dir))
    
    app.add_routes(routes)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    
    log.info(f"🌍 Web Dashboard iniciado em http://{host}:{port}")
    await site.start()
