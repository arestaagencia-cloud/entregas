"""Confere se o NOTION_TOKEN enxerga as databases necessárias (só leitura)."""
import json, os, urllib.request

TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("NOTION_TOKEN não está cadastrado nos segredos do repositório.")


def api(metodo, caminho, corpo=None):
    req = urllib.request.Request(f"https://api.notion.com/v1/{caminho}", method=metodo,
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


eu = api("GET", "users/me")
print("Integração:", eu.get("name"), "| workspace:", eu.get("bot", {}).get("workspace_name"))
achadas = api("POST", "search", {"filter": {"property": "object", "value": "database"}, "page_size": 100})["results"]
for d in achadas:
    titulo = "".join(t["plain_text"] for t in d.get("title", []))
    n, cursor = 0, None
    while True:
        corpo = {"page_size": 100} | ({"start_cursor": cursor} if cursor else {})
        r = api("POST", f"databases/{d['id']}/query", corpo)
        n += len(r["results"])
        if not r.get("has_more"):
            break
        cursor = r["next_cursor"]
    print(f"DB: {titulo!r:40} id={d['id']} páginas={n}")
faltam = {"Conteúdos", "Serviços", "Clientes"} - {"".join(t["plain_text"] for t in d.get("title", [])).strip() for d in achadas}
print("FALTAM:", ", ".join(sorted(faltam)) if faltam else "nenhuma (acesso ok)")
