"""
API Vercel pour recherche VIN via SerpAPI
"""

from http.server import BaseHTTPRequestHandler
import os
import re
import json
from urllib.parse import urlparse, parse_qs

# Import requests with error handling
try:
    import requests
except ImportError:
    requests = None


def search_vin_serpapi(vin: str, api_key: str) -> dict:
    """Recherche un VIN via SerpAPI"""
    result = {
        "vin": vin,
        "prix": "",
        "concessionnaire": "",
        "url": "",
        "annee": "",
        "marque": "",
        "modele": "",
        "km": "",
        "description": "",
        "statut": "Non trouvé"
    }

    if requests is None:
        result["statut"] = "Erreur: module requests non disponible"
        return result

    # Validation VIN
    vin = vin.strip().upper()
    if len(vin) != 17 or not vin.isalnum() or any(c in vin for c in 'IOQ'):
        result["statut"] = "VIN invalide"
        return result

    # Recherche SerpAPI
    try:
        params = {
            "api_key": api_key,
            "engine": "google",
            "q": f'"{vin}" voiture vente Canada',
            "num": 10,
            "gl": "ca",
            "hl": "fr",
        }

        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        search_results = data.get("organic_results", [])

        if not search_results:
            params["q"] = f'{vin} car sale Canada'
            response = requests.get("https://serpapi.com/search", params=params, timeout=30)
            data = response.json()
            search_results = data.get("organic_results", [])

        if not search_results:
            return result

        best_result = None
        best_score = 0

        auto_sites = ['autotrader', 'kijiji', 'hgregoire', 'carpages', 'cargurus', 'clutch']

        for sr in search_results[:5]:
            url = sr.get("link", "")
            title = sr.get("title", "")
            snippet = sr.get("snippet", "")
            combined = f"{title} {snippet}".upper()

            if vin not in combined:
                continue

            score = 0
            if any(site in url.lower() for site in auto_sites):
                score += 10

            prix = extract_price(f"{title} {snippet}")
            if prix:
                score += 5

            km = extract_km(f"{title} {snippet}")
            if km:
                score += 2

            if score > best_score:
                best_score = score
                best_result = {
                    "url": url,
                    "title": title,
                    "snippet": snippet,
                    "prix": prix,
                    "km": km,
                    "source": urlparse(url).netloc
                }

        if best_result:
            result["url"] = best_result["url"]
            result["prix"] = best_result.get("prix", "")
            result["km"] = best_result.get("km", "")
            result["description"] = best_result["title"][:100]
            result["concessionnaire"] = get_dealer_name(best_result["url"])

            year, make, model = extract_year_make_model(f"{best_result['title']} {best_result['snippet']}")
            result["annee"] = year
            result["marque"] = make
            result["modele"] = model
            result["statut"] = "Trouvé" if result["prix"] else "Trouvé (prix non disponible)"

        elif search_results:
            sr = search_results[0]
            result["url"] = sr.get("link", "")
            result["description"] = sr.get("title", "")[:100]
            result["concessionnaire"] = get_dealer_name(sr.get("link", ""))
            result["statut"] = "Résultat potentiel"

    except Exception as e:
        result["statut"] = f"Erreur: {str(e)[:50]}"

    return result


def extract_price(text: str) -> str:
    patterns = [
        r'\$\s*([\d,]+(?:\.\d{2})?)',
        r'([\d,]+(?:\.\d{2})?)\s*\$',
        r'([\d,]+)\s*(?:CAD|CDN)',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            price = match.replace(',', '').replace(' ', '')
            if price.replace('.', '').isdigit():
                price_int = int(float(price))
                if 1000 <= price_int <= 200000:
                    return f"{price_int:,}$".replace(',', ' ')
    return ""


def extract_km(text: str) -> str:
    patterns = [
        r'([\d,\s]+)\s*km',
        r'([\d,\s]+)\s*kilomet',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            km = match.replace(',', '').replace(' ', '')
            if km.isdigit():
                km_int = int(km)
                if 0 <= km_int <= 500000:
                    return f"{km_int:,} km".replace(',', ' ')
    return ""


def extract_year_make_model(text: str) -> tuple:
    year = ""
    make = ""
    model = ""

    year_match = re.search(r'\b(19[9][0-9]|20[0-2][0-9])\b', text)
    if year_match:
        year = year_match.group(1)

    makes = ['Honda', 'Toyota', 'Ford', 'Chevrolet', 'Nissan', 'Hyundai', 'Kia',
             'Mazda', 'Subaru', 'Volkswagen', 'BMW', 'Mercedes', 'Audi', 'Lexus',
             'Acura', 'Jeep', 'Dodge', 'Ram', 'GMC', 'Tesla', 'Porsche']

    for m in makes:
        if m.lower() in text.lower():
            make = m
            break

    models = ['Civic', 'Accord', 'CR-V', 'Camry', 'Corolla', 'RAV4', 'F-150',
              'Escape', 'Explorer', 'Silverado', 'Equinox', 'Altima', 'Rogue',
              'Elantra', 'Tucson', 'Forte', 'Sportage', 'Mazda3', 'CX-5',
              'Outback', 'Forester', 'Jetta', 'Tiguan', 'Wrangler', 'Model 3']

    for m in models:
        if m.lower() in text.lower():
            model = m
            break

    return year, make, model


def get_dealer_name(url: str) -> str:
    domain = urlparse(url).netloc.replace('www.', '')

    dealer_map = {
        'autotrader.ca': 'AutoTrader',
        'kijijiautos.ca': 'Kijiji Autos',
        'hgregoire.com': 'HGrégoire',
        'spinelli.ca': 'Spinelli',
        'carpages.ca': 'CarPages',
        'cargurus.ca': 'CarGurus',
        'clutch.ca': 'Clutch',
        'facebook.com': 'Facebook Marketplace',
    }

    for key, value in dealer_map.items():
        if key in domain:
            return value

    return domain.split('.')[0].title() if domain else ""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        vin = query.get('vin', [''])[0]

        api_key = os.environ.get('SERPAPI_KEY', '')

        if not api_key:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "SERPAPI_KEY not configured"}).encode())
            return

        if not vin:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "VIN parameter required"}).encode())
            return

        result = search_vin_serpapi(vin, api_key)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
