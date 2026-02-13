import aiohttp
import logging
from typing import Dict, Any, Optional, List
from settings import URLSCAN_API_KEY, OTX_API_KEY, VT_API_KEY, GREYNOISE_API_KEY, SHODAN_API_KEY

log = logging.getLogger("CyberIntel_ThreatService")


class ThreatService:
    """
    Serviço centralizado para consultas de Threat Intelligence
    (URLScan, AlienVault OTX, VirusTotal, Ransomware.live, GreyNoise, Shodan).
    """

    @staticmethod
    async def scan_url_urlscan(url_to_scan: str) -> Optional[Dict[str, Any]]:
        """
        Submete uma URL para análise no URLScan.io
        """
        if not URLSCAN_API_KEY:
            log.warning("URLScan API Key não configurada.")
            return None
        
        endpoint = "https://urlscan.io/api/v1/scan/"
        headers = {
            "API-Key": URLSCAN_API_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "url": url_to_scan,
            "visibility": "public"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, headers=headers, json=data, timeout=30) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        log.warning("URLScan Rate Limit atingido.")
                    else:
                        log.error(f"URLScan erro: {resp.status}")
        except Exception as e:
            log.error(f"Erro ao conectar URLScan: {e}")
        return None

    @staticmethod
    async def get_urlscan_result(uuid: str) -> Optional[Dict[str, Any]]:
        """Busca o resultado de um scan UUID."""
        if not uuid: return None
        endpoint = f"https://urlscan.io/api/v1/result/{uuid}/"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, timeout=30) as resp:
                     if resp.status == 200:
                         return await resp.json()
        except Exception as e:
            log.error(f"Erro ao buscar resultado URLScan: {e}")
        return None

    @staticmethod
    async def get_otx_pulses(limit: int = 5) -> list:
        """
        Busca pulses recentes do AlienVault OTX
        """
        if not OTX_API_KEY:
            return []
        
        endpoint = "https://otx.alienvault.com/api/v1/pulses/subscribed"
        headers = {"X-OTX-API-KEY": OTX_API_KEY}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, headers=headers, params={"limit": limit}, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("results", [])
                    else:
                        log.warning(f"OTX retornou status {resp.status}")
        except Exception as e:
            log.error(f"Erro ao consultar OTX: {e}")
        return []

    @staticmethod
    async def check_vt_reputation(url: str) -> Dict[str, Any]:
        """
        Checa reputação no VirusTotal (Scan URL)
        """
        if not VT_API_KEY:
            return {}
            
        endpoint = "https://www.virustotal.com/api/v3/urls"
        headers = {"x-apikey": VT_API_KEY}
        data = {"url": url}

        try:
            async with aiohttp.ClientSession() as session:
                # 1. Submeter
                async with session.post(endpoint, headers=headers, data=data, timeout=30) as resp:
                    if resp.status != 200:
                        return {"error": f"VT submit error {resp.status}"}
                    submit_data = await resp.json()
                # Resultado é um ID de análise que pode ser consultado posteriormente
                return submit_data
        except Exception as e:
            log.error(f"Erro ao consultar VT: {e}")
            return {"error": str(e)}

    @staticmethod
    async def get_ransomware_live_recent(limit: int = 20) -> List[Dict[str, Any]]:
        """
        Busca vítimas recentes de ransomware na API pública do Ransomware.live.
        Não requer API key.
        """
        endpoint = "https://api.ransomware.live/v2/recentvictims"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, timeout=30) as resp:
                    if resp.status != 200:
                        log.warning(f"Ransomware.live retornou status {resp.status}")
                        return []
                    data = await resp.json()
        except Exception as e:
            log.error(f"Erro ao consultar Ransomware.live: {e}")
            return []

        if isinstance(data, list):
            return data[:limit] if limit and limit > 0 else data
        if isinstance(data, dict):
            items = data.get("data") or data.get("results") or []
            if isinstance(items, list):
                return items[:limit] if limit and limit > 0 else items
        return []

    @staticmethod
    async def lookup_greynoise_ip(ip: str) -> Optional[Dict[str, Any]]:
        """
        Consulta reputação de IP na GreyNoise Community API.
        Requer GREYNOISE_API_KEY configurada no .env.
        """
        if not GREYNOISE_API_KEY:
            log.warning("GREYNOISE_API_KEY não configurada. Pulando consulta ao GreyNoise.")
            return None

        endpoint = f"https://api.greynoise.io/v3/community/{ip}"
        headers = {"key": GREYNOISE_API_KEY}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    if resp.status == 404:
                        return {"noise": False, "message": "IP não observado na GreyNoise."}
                    log.warning(f"GreyNoise retornou status {resp.status} para IP {ip}")
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            log.error(f"Erro ao consultar GreyNoise para IP {ip}: {e}")
            return None

    @staticmethod
    async def lookup_shodan_ip(ip: str) -> Optional[Dict[str, Any]]:
        """
        Consulta exposição de um IP na API pública do Shodan.
        Requer SHODAN_API_KEY configurada no .env.
        """
        if not SHODAN_API_KEY:
            log.warning("SHODAN_API_KEY não configurada. Pulando consulta ao Shodan.")
            return None

        endpoint = f"https://api.shodan.io/shodan/host/{ip}?key={SHODAN_API_KEY}&minify=true"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, timeout=20) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    if resp.status == 404:
                        return {"error": "IP não encontrado no Shodan."}
                    log.warning(f"Shodan retornou status {resp.status} para IP {ip}")
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            log.error(f"Erro ao consultar Shodan para IP {ip}: {e}")
            return None
