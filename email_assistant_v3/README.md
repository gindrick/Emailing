# Email Assistant v2

Automatizovane odesilani PDF dokumentu zakaznikum s podporou AI agenta.

## Co je noveho oproti v1

| Funkce | v1 (email_assistant) | v2 (email_assistant_v2) |
|---|---|---|
| Extrakce Bill To ID | Regex | **LLM (gpt-4.1-nano)** |
| Osloveni v emailu | Staticke "Dobry den," | **LLM - personalni dle jmena v PDF** |
| Architektura | Jednolitý Python script | **Workflow Agent + MCP Server** |
| Tools | Primo v kodu | **MCP nastroje (SharePoint, Excel, DB, SMTP, PDF)** |

## Architektura

```
main.py
  └── EmailWorkflowAgent
        ├── LLMClient (pres LiteLLM proxy → OpenAI)
        └── MCPClient → MCP Server (http://localhost:8002)
                          ├── sharepoint tools   (Graph API)
                          ├── excel tools        (pandas)
                          ├── database tools     (SQLite)
                          ├── pdf tools          (pypdf)
                          └── email sender       (SMTP)
```

### Workflow kroky

1. **Initialize** – SharePoint drive + slozky (sent, redo, skipped), SQLite DB
2. **Load Data** – Excel mapping, skip.xlsx, seznam PDF, davka k zpracovani
3. **Process Documents** – pro kazdy dokument:
   - Python: skip check, customer ID z nazvu, lookup emailu
   - MCP tool: stazeni PDF
   - **LLM: extrakce Bill To ID z textu PDF**
   - **LLM: generovani ceskeho osloveni (Vazeny pane/Vazena pani/Dobry den)**
   - Validace, odeslani emailu (MCP SMTP tool), presun (MCP SP tool)
4. **Export** – Excel reporty (log, sent, failed)

## Predpoklady

- [uv](https://docs.astral.sh/uv/) (package manager)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.12+
- OpenAI API klic
- Pristup k Microsoft SharePoint (Azure AD app registration)

## Instalace

```bash
# Klonovani / otevreni projektu
cd email_assistant_v2

# Zkopiruj a vyplne konfiguraci
cp .env.example .env
# Vyplnte vse v .env

# Vytvoreni virtualniho prostredi a instalace zavislosti
uv sync
```

## Konfigurace (.env)

Povinne:
- `OPENAI_API_KEY` – OpenAI klic
- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` – Azure AD
- `SHAREPOINT_SITE_URL` – URL SharePoint webu
- `SHAREPOINT_FOLDER_PATH` – zdrojova slozka (s podslozkama "Statements of...")
- `SHAREPOINT_SENT_FOLDER_PATH` nebo `SHAREPOINT_SENT_FOLDER_ID`
- `SHAREPOINT_DRIVE_NAME` nebo `SHAREPOINT_DRIVE_ID`
- `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` – SMTP server
- `MAPPING_EXCEL_PATH` – cesta k Excel souboru se zakaznickyma emaily

Volitelne:
- `TEST_MODE=true` – emaily jdou jen na `TEST_RECIPIENT_EMAIL`
- `BATCH_SIZE=50` – kolik dokumentu zpracovat v jednom behu
- `LITELLM_MODEL=oai-gpt-4.1-nano` – ktery model pouzit

## Spusteni

### 1. LiteLLM proxy (Docker)

```bash
docker-compose up -d
```

Proxy bezi na `http://localhost:4000`. Pouziva OPENAI_API_KEY z .env.

### 2. MCP Server

V novem terminalu:

```bash
uv run python src/mcp_server/server.py
```

Server bezi na `http://localhost:8002`. Poskytuje vsechny nastroje (SharePoint, Excel, DB, PDF, SMTP).

### 3. Spusteni agenta

```bash
uv run python main.py
```

## Struktura souboru

```
email_assistant_v2/
├── main.py                          # vstupni bod
├── pyproject.toml                   # zavislosti (uv)
├── .env.example                     # sablona konfigurace
├── docker-compose.yml               # LiteLLM proxy
├── litellm_config.yaml              # konfigurace modelu
├── data/                            # SQLite DB (auto-vytvorena)
├── inputs/
│   └── skip.xlsx                    # (volitelne) Bill-To skip list
├── output/                          # Excel reporty
└── src/
    ├── settings.py                  # konfigurace agenta
    ├── models.py                    # Pydantic modely (LLM output)
    ├── utils.py                     # pomocne funkce
    ├── agents/
    │   └── email_workflow_agent.py  # hlavni agent
    ├── clients/
    │   ├── llm_client.py            # LiteLLM klient
    │   └── mcp_client.py           # MCP klient
    └── mcp_server/
        ├── server.py                # MCP HTTP server
        └── tools/
            ├── sharepoint.py        # SharePoint Graph API
            ├── excel_tools.py       # Excel nacitani
            ├── database.py          # SQLite stav
            ├── pdf_tools.py         # PDF extrakce textu
            └── email_sender.py      # SMTP odesilani
```

## Vystupy

Po spusteni se v `output/` vytvori:
- `_log.xlsx` – kompletni log vsech zpracovanych souboru
- `_sent_report.xlsx` – uspesne odeslane dokumenty
- `_failed_report.xlsx` – dokumenty s chybou (redo)

## Reseni problemu

**MCP server nejde spustit:**
```bash
uv run python src/mcp_server/server.py
# Zkontroluj port 8002 neni obsazen
```

**LiteLLM nereaguje:**
```bash
docker-compose logs litellm
# Zkontroluj OPENAI_API_KEY v .env
```

**SharePoint chyba 401:**
- Zkontroluj AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
- Azure AD app musi mit Sites.ReadWrite.All permission
