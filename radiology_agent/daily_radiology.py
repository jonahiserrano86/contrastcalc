#!/usr/bin/env python3
"""Agente diario de radiología.

Busca en PubMed los artículos publicados en las últimas 24 horas en las
principales revistas de radiología, genera un mini resumen en español de
cada uno (con la API de Claude si hay clave disponible; si no, usa el
abstract original recortado) y envía el digest por Telegram.

Variables de entorno:
    TELEGRAM_BOT_TOKEN   (obligatoria) token del bot de @BotFather
    TELEGRAM_CHAT_ID     (obligatoria) chat/canal destino
    ANTHROPIC_API_KEY    (opcional)    habilita resúmenes con IA en español
    LOOKBACK_DAYS        (opcional)    días hacia atrás a buscar (default 1)
    MAX_ARTICLES         (opcional)    tope de artículos por mensaje (default 25)

Sin dependencias externas: solo librería estándar de Python 3.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Revistas principales de radiología (nombre de journal en PubMed).
JOURNALS = [
    "Radiology",
    "Radiographics",
    "AJR Am J Roentgenol",
    "Eur Radiol",
    "Invest Radiol",
    "J Am Coll Radiol",
    "AJNR Am J Neuroradiol",
    "J Vasc Interv Radiol",
    "Eur J Radiol",
    "Abdom Radiol (NY)",
    "Neuroradiology",
    "Pediatr Radiol",
    "Emerg Radiol",
    "Acad Radiol",
    "Br J Radiol",
    "Korean J Radiol",
    "Insights Imaging",
    "Cardiovasc Intervent Radiol",
    "Skeletal Radiol",
    "Clin Radiol",
]


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "radiology-digest/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_post_json(url, payload, headers=None, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    all_headers = {"Content-Type": "application/json", "User-Agent": "radiology-digest/1.0"}
    if headers:
        all_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=all_headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_pubmed(lookback_days):
    journal_clause = " OR ".join(f'"{j}"[Journal]' for j in JOURNALS)
    term = f"({journal_clause})"
    params = {
        "db": "pubmed",
        "term": term,
        "reldate": str(lookback_days),
        "datetype": "edat",
        "retmax": "200",
        "retmode": "json",
        "sort": "pub_date",
    }
    url = f"{EUTILS}/esearch.fcgi?" + urllib.parse.urlencode(params)
    data = json.loads(http_get(url).decode("utf-8"))
    return data.get("esearchresult", {}).get("idlist", [])


def fetch_articles(pmids):
    if not pmids:
        return []
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(params)
    root = ET.fromstring(http_get(url))
    articles = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//PMID", default="")
        title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else "(sin título)"
        journal = art.findtext(".//Journal/ISOAbbreviation") or art.findtext(".//Journal/Title") or ""
        abstract_parts = []
        for ab in art.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            text = "".join(ab.itertext()).strip()
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = "\n".join(abstract_parts)
        doi = ""
        for aid in art.findall(".//ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = (aid.text or "").strip()
        articles.append({
            "pmid": pmid,
            "title": title.strip(),
            "journal": journal.strip(),
            "abstract": abstract.strip(),
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })
    return articles


def summarize_with_claude(article, api_key):
    """Resumen de 2-3 frases en español usando Claude Haiku."""
    prompt = (
        "Eres un radiólogo académico. Resume el siguiente artículo en español, "
        "en 2-3 frases claras y concretas orientadas a la práctica clínica. "
        "No repitas el título ni uses viñetas; responde solo con el resumen.\n\n"
        f"Título: {article['title']}\n"
        f"Revista: {article['journal']}\n"
        f"Abstract: {article['abstract'] or '(sin abstract disponible)'}"
    )
    payload = {
        "model": "claude-haiku-4-5",
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    resp = http_post_json("https://api.anthropic.com/v1/messages", payload, headers)
    return "".join(b.get("text", "") for b in resp.get("content", [])).strip()


def fallback_summary(article, max_chars=350):
    text = article["abstract"] or "(Sin abstract disponible; consulta el enlace.)"
    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


def html_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_messages(articles, date_label):
    header = f"🩻 <b>Radiología al día — {date_label}</b>\n{len(articles)} artículo(s) nuevo(s) en las principales revistas.\n"
    if not articles:
        return [header + "\nHoy no se indexaron artículos nuevos en las revistas monitoreadas. 📭"]

    blocks = [header]
    for i, a in enumerate(articles, 1):
        block = (
            f"\n<b>{i}. {html_escape(a['title'])}</b>\n"
            f"📖 <i>{html_escape(a['journal'])}</i>\n"
            f"{html_escape(a['summary'])}\n"
            f"🔗 <a href=\"{a['url']}\">PubMed</a>"
        )
        if a["doi"]:
            block += f" · <a href=\"https://doi.org/{urllib.parse.quote(a['doi'])}\">DOI</a>"
        blocks.append(block + "\n")

    # Telegram limita cada mensaje a 4096 caracteres: agrupamos bloques.
    messages, current = [], ""
    for block in blocks:
        if len(current) + len(block) > 3900:
            messages.append(current)
            current = block
        else:
            current += block
    if current:
        messages.append(current)
    return messages


def send_telegram(token, chat_id, text):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = http_post_json(f"https://api.telegram.org/bot{token}/sendMessage", payload)
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram rechazó el mensaje: {resp}")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        sys.exit("Faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID en el entorno.")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    lookback = int(os.environ.get("LOOKBACK_DAYS", "1"))
    max_articles = int(os.environ.get("MAX_ARTICLES", "25"))

    print(f"Buscando artículos de las últimas {lookback * 24} h en {len(JOURNALS)} revistas…")
    pmids = search_pubmed(lookback)
    print(f"PubMed devolvió {len(pmids)} artículo(s).")
    articles = fetch_articles(pmids[:max_articles])

    for a in articles:
        if api_key:
            try:
                a["summary"] = summarize_with_claude(a, api_key)
                time.sleep(0.5)  # cortesía con la API
                continue
            except Exception as e:
                print(f"Resumen IA falló para PMID {a['pmid']} ({e}); uso abstract.", file=sys.stderr)
        a["summary"] = fallback_summary(a)

    date_label = time.strftime("%d/%m/%Y")
    omitted = max(0, len(pmids) - max_articles)
    messages = build_messages(articles, date_label)
    if omitted:
        messages[-1] += f"\n\n(+{omitted} artículo(s) adicionales no incluidos; ajusta MAX_ARTICLES si quieres verlos.)"

    for msg in messages:
        send_telegram(token, chat_id, msg)
        time.sleep(1)
    print(f"Enviados {len(messages)} mensaje(s) a Telegram con {len(articles)} artículo(s).")


if __name__ == "__main__":
    main()
