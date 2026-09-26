"""
Validação de URL (anti-SSRF) e da imagem que vai ao embed do Discord.

Portado por DUPLICAÇÃO CONSCIENTE do gundam-news-discord (commit c8724bc,
2026-09-25) — regra-arquitetura-desacoplamento §2/§9: sem shared/ entre bots.
Contrato deste bot: validate_url devolve (ok, motivo), nunca levanta.
"""
import asyncio
import ipaddress
import logging
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

log = logging.getLogger("CyberIntel")

_REDES_BLOQUEADAS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]
_DOMINIOS_LOCAIS = {"localhost", "0.0.0.0", "::1"}  # nosec B104 - lista de BLOQUEIO, não bind
_SUFIXOS_LOCAIS = (".localhost", ".local", ".internal")
_CARACTERES_PROIBIDOS = ("\x00", "\r", "\n", "\t", " ")
_PARTE_IPV4_LEGADA = re.compile(r"^(0x[0-9a-f]+|[0-9]+)$", re.IGNORECASE)


def _ipv4_legado(host: str) -> Optional[ipaddress.IPv4Address]:
    """IPv4 nas grafias que inet_aton aceita e ipaddress não: 127.1, 2130706433, 0x7f.0.0.1, 0177.0.0.1."""
    partes = host.split(".")
    if not 1 <= len(partes) <= 4 or not all(_PARTE_IPV4_LEGADA.match(x) for x in partes):
        return None
    try:
        numeros = [
            int(x, 16) if x.lower().startswith("0x")
            else int(x, 8) if len(x) > 1 and x.startswith("0")
            else int(x)
            for x in partes
        ]
    except ValueError:
        return None
    *iniciais, ultima = numeros
    if any(n > 255 for n in iniciais) or ultima >= 256 ** (4 - len(iniciais)):
        return None
    valor = 0
    for n in iniciais:
        valor = (valor << 8) | n
    valor = (valor << (8 * (4 - len(iniciais)))) | ultima
    return ipaddress.IPv4Address(valor)


def is_private_ip(host: str) -> bool:
    """
    Diz se `host` é um endereço IP NÃO público, em qualquer grafia numérica.

    PROPÓSITO DE NEGÓCIO:
        Barreira anti-SSRF: link vindo de feed de terceiro não pode fazer o bot
        requisitar o próprio host, a rede do Docker ou o metadata de nuvem.

    INVARIANTES DO DOMÍNIO:
        - Não-global = privado: loopback, RFC1918, link-local, CGNAT, reservado.
        - IPv6 que embute IPv4 (::ffff:127.0.0.1) é julgado pelo IPv4.

    COMPORTAMENTO EM CASO DE FALHA:
        Texto que não é IP devolve False (é nome, julgado em validate_url).
        Nunca levanta.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = _ipv4_legado(host)
    if ip is None:
        return False
    mapeado = getattr(ip, "ipv4_mapped", None)
    if mapeado is not None:
        ip = mapeado
    if any(ip in rede for rede in _REDES_BLOQUEADAS if rede.version == ip.version):
        return True
    return not ip.is_global


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Valida uma URL que o bot vai BUSCAR (anti-SSRF) — parte estrutural, sem rede.

    PROPÓSITO DE NEGÓCIO:
        Impedir que um link de feed ou og:image vire pedido a endereço interno.

    INVARIANTES DO DOMÍNIO:
        - Só http/https com host presente; credenciais (user@) e colchetes de
          IPv6 são removidos antes de julgar o host real.
        - Nome local (localhost, *.local, *.internal) e IP não público, em
          qualquer grafia, são recusados.
        - Caractere de controle ou espaço na URL é recusado.

    COMPORTAMENTO EM CASO DE FALHA:
        Devolve (False, motivo). Nunca levanta.
    """
    if not url or not isinstance(url, str):
        return False, "URL vazia ou não textual"
    url = url.strip()
    if any(c in url for c in _CARACTERES_PROIBIDOS):
        return False, "URL contém caractere de controle ou espaço"
    if not url.startswith(("http://", "https://")):
        return False, "esquema diferente de http(s)"
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").rstrip(".").lower()
    except ValueError as e:
        return False, f"URL malformada: {e}"
    if parsed.scheme not in ("http", "https") or not host:
        return False, "URL sem host"
    if host in _DOMINIOS_LOCAIS or host.endswith(_SUFIXOS_LOCAIS):
        return False, f"host local '{host}'"
    if is_private_ip(host):
        return False, f"IP não público '{host}'"
    return True, None


async def resolve_para_publico(url: str) -> Tuple[bool, Optional[str]]:
    """
    Resolve o host da URL e recusa se QUALQUER endereço resolvido for não público.

    PROPÓSITO DE NEGÓCIO:
        Fechar o SSRF por nome: 'intranet.exemplo.com' passa na validação
        estrutural e pode resolver para 10.x.

    INVARIANTES DO DOMÍNIO:
        - DNS pelo loop (getaddrinfo roda no executor, não bloqueia o heartbeat).
        - Chamar DEPOIS de validate_url.

    COMPORTAMENTO EM CASO DE FALHA:
        (False, motivo) se não resolver ou se algum IP for privado. Nunca levanta.
        Risco residual declarado: o cliente HTTP resolve de novo (rebinding
        entre as duas resoluções não é coberto).
    """
    try:
        host = urlparse(url).hostname or ""
        if is_private_ip(host):
            return False, f"IP não público '{host}'"
        try:
            ipaddress.ip_address(host)
            return True, None
        except ValueError:
            pass
        loop = asyncio.get_running_loop()
        infos = await asyncio.wait_for(loop.getaddrinfo(host, None), timeout=5)
    except Exception as e:
        return False, f"host não resolvido: {type(e).__name__}"
    for info in infos:
        endereco = info[4][0]
        if is_private_ip(endereco):
            return False, f"'{host}' resolve para endereço não público {endereco}"
    return True, None


def imagem_publicavel(url) -> Optional[str]:
    """
    Decide se uma URL de imagem pode ir ao embed do Discord.

    PROPÓSITO DE NEGÓCIO:
        Impedir que uma imagem ruim APAGUE a notícia. O Discord recusa o embed
        inteiro (400, error code 50035) quando a URL de imagem é inválida: a
        notícia falha em todas as guilds, não entra no dedup e o ciclo seguinte
        tenta de novo, para sempre. Medido no gundam-news (guild
        417746665219424277) e portado para cá em 2026-09-26.

    INVARIANTES DO DOMÍNIO:
        - Só URL absoluta http(s) de host público (validate_url, sem DNS: a
          imagem é buscada pelo Discord, não pelo bot; roda no event loop).
        - SVG é recusado: o Discord não renderiza SVG em embed — o logo do NIST
          que o bot usava para toda CVE nunca aparecia.
        - Devolve None em vez de string vazia.

    COMPORTAMENTO EM CASO DE FALHA:
        Devolve None; a notícia sai SEM imagem. Nunca levanta.
    """
    if not url or not isinstance(url, str):
        return None
    limpa = url.strip()
    ok, _motivo = validate_url(limpa)
    if not ok:
        return None
    caminho = urlparse(limpa).path.lower()
    if caminho.endswith(".svg") or caminho.endswith(".svgz"):
        return None
    if len(limpa) > 2048:
        return None
    return limpa
