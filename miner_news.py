#!/usr/bin/env python3
import os, sys, time, json, textwrap
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
import feedparser

TZ = ZoneInfo("America/Bahia")  # seu fuso
UA = {"User-Agent": "Mozilla/5.0 (+news-bot)"}

# Feeds Google News (PT-BR/BR) p/ mineração "setor mineral" e "cripto"
FEEDS = [
    "https://news.google.com/rss/search?q=minera%C3%A7%C3%A3o+setor+mineral&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://news.google.com/rss/search?q=minera%C3%A7%C3%A3o+bitcoin+OU+criptomoedas&hl=pt-BR&gl=BR&ceid=BR:pt-419",
]

def is_yesterday(dt_utc, tz=TZ):
    yday = (datetime.now(tz).date() - timedelta(days=1))
    return dt_utc.astimezone(tz).date() == yday

def load_items():
    items = []
    seen = set()
    for url in FEEDS:
        fp = feedparser.parse(url)
        print(f"Feed {url} retornou {len(fp.entries)} entradas")
        for e in fp.entries:
            link = getattr(e, "link", "")
            if not link or link in seen:
                continue
            # published -> datetime
            dt = None
            for attr in ("published_parsed", "updated_parsed"):
                t = getattr(e, attr, None)
                if t:
                    dt = datetime(*t[:6], tzinfo=timezone.utc)
                    break
            if not dt:
                continue
            if is_yesterday(dt):
                title = getattr(e, "title", "").strip()
                source = getattr(getattr(e, "source", {}), "title", "") or getattr(e, "source", "")
                items.append({"title": title, "link": link, "source": source, "dt": dt})
                seen.add(link)
    print(f"Manchetes encontradas: {len(items)}")
    items.sort(key=lambda x: x["dt"])
    return items

def call_openai(headlines_text, openai_api_key):
    prompt = f"""
Você é um analista que escreve para executivos. A seguir há manchetes de ontem no mundo sobre mineração (setor mineral). 
1) Produza um resumo em PT-BR, direto ao ponto, com 5–10 tópicos do que IMPORTA (sem floreio).
2) Separe seção 'Principais manchetes' listando 8–15 títulos curtos com fonte.
3) Termine com 'Links-chave' e inclua 3–5 URLs mais relevantes.
Use a data de ontem e evite duplicatas. Manchetes:
---
{headlines_text}
---
"""
    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Você resume notícias de forma clara e objetiva."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def main():
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Faltou OPENAI_API_KEY no ambiente.", file=sys.stderr)
        sys.exit(1)

    items = load_items()
    yday = (datetime.now(TZ).date() - timedelta(days=1)).strftime("%d/%m/%Y")
    print(f"Procurando manchetes de {yday}, total de items: {len(items)}")

    if not items:
        # fallback: se nada de ontem, pega os 10 mais recentes do 1º feed
        fp = feedparser.parse(FEEDS[0])
        alt = []
        for e in fp.entries[:10]:
            title = getattr(e, "title", "").strip()
            link = getattr(e, "link", "")
            source = getattr(getattr(e, "source", {}), "title", "") or getattr(e, "source", "")
            alt.append({"title": title, "link": link, "source": source, "dt": datetime.now(timezone.utc)})
        items = alt
        print("Usando fallback: 10 itens mais recentes")

    # monta texto de manchetes para o prompt
    lines = []
    for it in items:
        src = f" — {it['source']}" if it.get("source") else ""
        lines.append(f"• {it['title']}{src} — {it['link']}")
    headlines_text = "\n".join(lines)
    print(f"Texto enviado à API: {headlines_text[:200]}...")  # Mostra os primeiros 200 caracteres

    try:
        summary = call_openai(headlines_text, openai_api_key)
        print(f"Resumo gerado: {summary[:200]}...")
    except Exception as e:
        summary = "Não foi possível gerar o resumo hoje. Erro: " + str(e)
        print(f"Erro na API: {str(e)}")

    now_ba = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
    out = []
    out.append(f"Resumo diário de mineração — {yday}")
    out.append(f"(Gerado em {now_ba} BRT)\n")
    out.append(summary)
    out.append("\n— Fonte automatizada via Google News (PT-BR/BR).")
    text = "\n".join(out).strip() + "\n"
    print(f"Texto final a ser salvo: {text[:200]}...")

    with open("resumo-mineracao.txt", "w", encoding="utf-8") as f:
        f.write(text)
        print("Arquivo salvo com sucesso!")

if __name__ == "__main__":
    main()
