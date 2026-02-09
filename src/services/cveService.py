import aiohttp
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

log = logging.getLogger("CyberIntel")

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

from settings import NVD_API_KEY

async def fetch_nvd_cves(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Busca as últimas CVEs críticas/altas na API do NIST.
    
    Args:
        limit (int): Número máximo de CVEs para retornar.
        
    Returns:
        List[Dict]: Lista de CVEs formatadas como 'news entries'.
    """
    
    # Filtra por data de publicação (últimos 7 dias) para reduzir load e focar em novidades
    now = datetime.utcnow()
    pub_start_date = (now - timedelta(days=7)).isoformat(timespec='milliseconds') + "Z"
    pub_end_date = now.isoformat(timespec='milliseconds') + "Z"

    params = {
        "pubStartDate": pub_start_date,
        "pubEndDate": pub_end_date,
        "resultsPerPage": 20, # Pega um pouco mais para filtrar por CVSS depois
        "noRejected": "" # Ignora CVEs rejeitadas
    }

    headers = {
        "User-Agent": "CyberIntelBot/1.0 (students_project)"
    }
    
    # Adiciona API Key se configurada (aumenta rate limit)
    if NVD_API_KEY:
        headers["apiKey"] = NVD_API_KEY

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(NVD_API_URL, params=params, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    log.warning(f"⚠️ NVD API retornou status {resp.status}")
                    return []
                
                data = await resp.json()
                
        cve_items = data.get("vulnerabilities", [])
        results = []
        
        for item in cve_items:
            cve = item.get("cve", {})
            cve_id = cve.get("id")
            
            # 1. Checagem de Severidade (CVSS v3.1)
            metrics = cve.get("metrics", {})
            cvss_data = None
            
            # Tenta pegar V31, depois V30, depois V2
            if "cvssMetricV31" in metrics:
                cvss_data = metrics["cvssMetricV31"][0]["cvssData"]
            elif "cvssMetricV30" in metrics:
                cvss_data = metrics["cvssMetricV30"][0]["cvssData"]
                
            if not cvss_data:
                continue # Pula se não tiver score CVSS moderno
                
            score = cvss_data.get("baseScore", 0)
            
            # Filtro: Apenas ALTA ou CRÍTICA (> 7.0)
            if score < 7.0:
                continue

            # 2. Descrição
            descriptions = cve.get("descriptions", [])
            summary = "Sem descrição disponível."
            for d in descriptions:
                if d.get("lang") == "en":
                    summary = d.get("value")
                    break
            
            # 3. Formatação
            entry = {
                "title": f"🚨 {cve_id} (CVSS {score}): {summary[:50]}...",
                "link": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                "summary": f"**Severity:** {cvss_data.get('baseSeverity', 'UNKNOWN')} ({score})\n**Vector:** {cvss_data.get('vectorString')}\n\n{summary}",
                "published": cve.get("published"), # ISO String
                "source": "NIST NVD"
            }
            results.append(entry)
            
            if len(results) >= limit:
                break
                
        return results



    except Exception as e:
        log.error(f"❌ Erro ao consultar NVD API: {e}")
        return []

async def get_cve_details(cve_id: str) -> Optional[Dict[str, Any]]:
    """
    Busca detalhes de uma CVE específica.
    """
    params = {"cveId": cve_id}
    headers = {"User-Agent": "CyberIntelBot/1.0", "apiKey": NVD_API_KEY} if NVD_API_KEY else {"User-Agent": "CyberIntelBot/1.0"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(NVD_API_URL, params=params, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        
        vulns = data.get("vulnerabilities", [])
        if not vulns:
            return None
            
        cve_item = vulns[0].get("cve", {})
        
        # Extrai metrics (CVSS)
        metrics = cve_item.get("metrics", {})
        cvss = "UNKNOWN"
        if "cvssMetricV31" in metrics:
            cvss = metrics["cvssMetricV31"][0]["cvssData"]["baseScore"]
        elif "cvssMetricV30" in metrics:
            cvss = metrics["cvssMetricV30"][0]["cvssData"]["baseScore"]
        elif "cvssMetricV2" in metrics:
            cvss = metrics["cvssMetricV2"][0]["cvssData"]["baseScore"]
            
        # Extrai descrição
        summary = "Sem descrição."
        for d in cve_item.get("descriptions", []):
            if d.get("lang") == "en":
                summary = d.get("value")
                break
                
        # Extrai referências
        refs = [r.get("url") for r in cve_item.get("references", [])]
        
        # Extrai configs (produtos vulneráveis - simplificado)
        products = []
        # Nota: Parsing de CPE é complexo, aqui pegamos apenas se disponível de forma fácil
        # Para simplificar, deixamos vazio por enquanto ou pegamos do configurations se sesejado.
        
        return {
            "id": cve_item.get("id"),
            "cvss": cvss,
            "summary": summary,
            "published": cve_item.get("published"),
            "vulnerable_product": products,
            "references": refs
        }
        
    except Exception as e:
        log.error(f"Erro ao buscar CVE details: {e}")
        return None
