# Email Assistant (SharePoint -> Email)

Skript stahne PDF dokumenty ze SharePoint slozky (Microsoft Graph API), z nazvu souboru vycte customer ID, dohleda email v pomocnem Excelu a dokument odesle e-mailem.

Pri testovani se vsechny maily odesilaji pouze na testovaci adresu (`TEST_RECIPIENT_EMAIL`) a skutecny zakaznicky email z Excelu se vlozi do tela zpravy. Po uspesnem zpracovani se dokument presune do slozky `sent` a stav se uklada do lokalni SQLite DB, aby se soubory neposilaly opakovane.

## Soubory projektu

- `main.py` - hlavni skript pro zpracovani PDF a odeslani emailu
- `reset_processing_state.py` - utility pro vymazani SQLite stavu (retest)
- `run_email_assistant.ps1` - PowerShell launcher s automatickym logovanim
- `register_task_scheduler.ps1` - skript pro registraci Windows Task Scheduleru
- `extract_pdf_amounts.py` - utility, ktera stahne PDF ze SharePointu a vytezi Bill-To + Amount Open do Excelu
- `.env` - konfigurace (credentials, cesty, SMTP)
- `data/processing_state.db` - SQLite databaze stavu zpracovani
- `logs/run_*.log` - logy z PowerShell launcheru
- `output/` - vsechny generovane Excel reporty (`_log.xlsx`, `_sent_report.xlsx`, `_failed_report.xlsx`, `_queue.xlsx`, `_amount_open_report.xlsx`, ...)

## Reporty a vystupy

Veskere Excel vystupy se automaticky ukladaji do slozky `output/` v koreni projektu. Po kazdem behu tam najdes:

- `_log.xlsx` – kompletni tabulka `processed_files` (co je v SQLite)
- `_sent_report.xlsx`, `_failed_report.xlsx` – prehled uspesnych a chybovych souboru
- `_queue.xlsx` – davka, ktera se prave zpracovava
- `_amount_open_report.xlsx` – vystup z `extract_pdf_amounts.py` s Bill-To + Amount Open (pri rucnim spusteni utility)

Slozka se vytvari automaticky, neni nutne ji zakladat rucne.

## Spusteni

1. Vytvor `.env` soubor podle ukazky nize.
2. Priprav Excel soubor s mapou `customer_id -> email`.
3. Spust jednou z nasledujicich metod:

### Metoda 1: Pres UV (doporuceno pro vyvoj)
```bash
uv run main.py
```

### Metoda 2: Pres Python virtualenv
```bash
C:/jj/.venv/Scripts/python.exe main.py
```

Nebo z PowerShellu:
```powershell
Push-Location .\emailAssistant
C:/jj/.venv/Scripts/python.exe .\main.py
Pop-Location
```

### Metoda 3: Pres PowerShell launcher (s logovanim)
```powershell
.\run_email_assistant.ps1
```
Automaticky logy zapisuje do `logs/run_YYYYMMDD_HHMMSS.log`

### Metoda 4: Task Scheduler (automaticke/rucne spousteni)
```powershell
# Spustit existujici task
Start-ScheduledTask -TaskName "EmailAssistant_PDF_Processor"

# Zkontrolovat stav
Get-ScheduledTask -TaskName "EmailAssistant_PDF_Processor"
```

## Retest od nuly (vymazani stavu DB)

Pred opakovanym end-to-end testem vymaz stav z SQLite, aby se soubory znovu zpracovaly:

### Pres UV:
```bash
uv run reset_processing_state.py
```

### Pres Python virtualenv:
```bash
C:/jj/.venv/Scripts/python.exe reset_processing_state.py
```

Nebo z PowerShellu:
```powershell
Push-Location .\emailAssistant
C:/jj/.venv/Scripts/python.exe .\reset_processing_state.py
Pop-Location
```

Pak po manualnim presunu PDF ze `sent` zpet do zdrojove slozky (`IT TESTING`) spust znovu hlavni skript.

## Automatizace pres Windows Task Scheduler

### Registrace tasku (pouze prvni spusteni)

Task lze zaregistrovat interaktivne jako Administrator:
```powershell
# Spust jako Administrator
.\register_task_scheduler.ps1
```

Nebo bez admin prav (pouze pro aktualniho uzivatele):
```powershell
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"C:\jj\emailAssistant\run_email_assistant.ps1`"" -WorkingDirectory "C:\jj\emailAssistant"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddYears(10)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName "EmailAssistant_PDF_Processor" -Description "Processes PDFs from SharePoint" -Action $action -Trigger $trigger -Settings $settings -User $env:USERNAME
```

### Ovladani zaregistrovaneho tasku

```powershell
# Spustit task rucne
Start-ScheduledTask -TaskName "EmailAssistant_PDF_Processor"

# Zkontrolovat stav a posledni beh
Get-ScheduledTask -TaskName "EmailAssistant_PDF_Processor" | Select-Object TaskName, State, LastRunTime, LastTaskResult

# Vypnout task
Disable-ScheduledTask -TaskName "EmailAssistant_PDF_Processor"

# Zapnout task
Enable-ScheduledTask -TaskName "EmailAssistant_PDF_Processor"

# Smazat task
Unregister-ScheduledTask -TaskName "EmailAssistant_PDF_Processor" -Confirm:$false
```

### Nastaveni pravidelneho spousteni

Pro automaticke spousteni (napr. kazde 4 hodiny) uprav trigger:
```powershell
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 4) -RepetitionDuration ([TimeSpan]::MaxValue)
Set-ScheduledTask -TaskName "EmailAssistant_PDF_Processor" -Trigger $trigger
```

Nebo denni v 8:00:
```powershell
$trigger = New-ScheduledTaskTrigger -Daily -At "08:00"
Set-ScheduledTask -TaskName "EmailAssistant_PDF_Processor" -Trigger $trigger
```

### Kontrola logu z Task Scheduleru

```powershell
Get-ChildItem "C:\jj\emailAssistant\logs\" -Filter "run_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content
```

## Povinne `.env` promenne

```env
# Microsoft Graph (app registration / client credentials)
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=your-secret

# SharePoint site (preferovano)
SHAREPOINT_SITE_URL=https://contoso.sharepoint.com/sites/MySite

# Alternativa k SHAREPOINT_SITE_URL (legacy)
SHAREPOINT_SITE_HOSTNAME=contoso.sharepoint.com
SHAREPOINT_SITE_PATH=/sites/MySite

# Vyber jedno: SHAREPOINT_DRIVE_ID nebo SHAREPOINT_DRIVE_NAME
SHAREPOINT_DRIVE_ID=
SHAREPOINT_DRIVE_NAME=Documents

# Slozka v danem drive (muze byt i cely SharePoint URL, skript si to normalizuje)
SHAREPOINT_FOLDER_PATH=Shared Documents/Faktury

# Cilova slozka pro zpracovane soubory (sent) - nastav SHAREPOINT_SENT_FOLDER_ID nebo SHAREPOINT_SENT_FOLDER_PATH
SHAREPOINT_SENT_FOLDER_ID=
SHAREPOINT_SENT_FOLDER_PATH=Shared Documents/Faktury/sent

# Excel mapa
MAPPING_EXCEL_PATH=data/customer_emails.xlsx
MAPPING_ID_COLUMN=customer_id
MAPPING_EMAIL_COLUMN=email

# Lokalni DB stav zpracovani (ochrana proti duplicitnimu odeslani)
STATE_DB_PATH=data/processing_state.db

# Test mode: vsechny maily jdou pouze sem
TEST_MODE=true
TEST_RECIPIENT_EMAIL=jindrich.jansa@hranipex.com

# Volitelne: regex pro extrakci customer ID z nazvu souboru bez pripony
# Pokud ma regex skupinu, pouzije se group(1), jinak cely match
CUSTOMER_ID_REGEX=(\d+)

# SMTP
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=sender@contoso.com
SMTP_PASSWORD=your-password
SMTP_USE_TLS=true
EMAIL_FROM=sender@contoso.com

# Sablony
EMAIL_SUBJECT_TEMPLATE=Dokument pro zakaznika {customer_id}
EMAIL_BODY_TEMPLATE=Dobry den,\n\nv priloze posilame PDF dokument.\n\nS pozdravem
```

## Poznamka k opravneneim

Azure AD aplikace musi mit Graph aplikačni prava alespon:

- `Sites.Read.All` (cteni dokumentu)

A tato prava musi byt schvalena (admin consent).

### Kompatibilita nazvu

Skript podporuje i puvodni nazvy promennych (`MS_*`, `SP_*`) kvuli zpetne kompatibilite,
ale doporuceny sjednoceny format je `AZURE_*` a `SHAREPOINT_*`.

### Ochrana proti duplicite

Stav kazdeho souboru je v SQLite tabulce `processed_files`:

- `email_sent=1` znamena, ze mail uz byl odeslan.
- `moved_to_sent=1` znamena, ze soubor uz byl uspesne presunut.

Pri dalsim behu skript soubor s `moved_to_sent=1` preskoci. Pokud je `email_sent=1` ale presun selhal, pokusi se jen o presun bez znovuodeslani mailu.

## Prechod z Excel na SQL

Logika dohledani emailu je oddelena ve funkci `load_customer_email_map(...)`.
Pozdeji se muze nahradit SQL dotazem bez zmeny zbytku toku.

## Prechod z testovaci do produkce

Pro produkci (skutecne odeslani emailu zakaznikum namisto testovaci adresy):

1. V `.env` zmen:
```env
TEST_MODE=false
# Nebo smazat/zakomentovat radek TEST_MODE

# Smazat/zakomentovat testovaci email:
# TEST_RECIPIENT_EMAIL=test@example.com
```

2. Vymaz DB stav pro ciste spusteni:
```bash
C:/jj/.venv/Scripts/python.exe reset_processing_state.py
```

3. Zkontroluj SMTP nastaveni - musi odpovidat produkci

4. Spust prvni produkci run:
```bash
C:/jj/.venv/Scripts/python.exe main.py
```

**VAROVANÍ:** Bez TEST_MODE se emaily posilaji skutecnym zakaznikum podle Excelu!

## Rychly pruvodce - nejcastejsi prikazy

### Testovaci beh (rucne, s logem)
```powershell
cd C:\jj\emailAssistant
.\run_email_assistant.ps1
```

### Vymaz DB a spust znovu
```powershell
cd C:\jj\emailAssistant
C:/jj/.venv/Scripts/python.exe .\reset_processing_state.py
C:/jj/.venv/Scripts/python.exe .\main.py
```

### Spust pres Task Scheduler
```powershell
Start-ScheduledTask -TaskName "EmailAssistant_PDF_Processor"
```

### Zkontroluj posledni log
```powershell
Get-ChildItem C:\jj\emailAssistant\logs\ -Filter "run_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 20
```

### Zkontroluj stav DB
```powershell
cd C:\jj\emailAssistant
C:/jj/.venv/Scripts/python.exe -c "import sqlite3; conn = sqlite3.connect('data/processing_state.db'); print(f'Celkem zpracovano: {conn.execute(\"SELECT COUNT(*) FROM processed_files\").fetchone()[0]}'); conn.close()"
```

## Extrakce Amount Open z PDF

Pro hromadnou kontrolu castky `Amount Open` je k dispozici skript `extract_pdf_amounts.py`. Pouziva stejne SharePoint credentials jako hlavni aplikace, PDF stahuje pres Graph API a hodnoty vytezi pomoci `pdfplumber`. Vysledkem je Excel v `output/_amount_open_report.xlsx`.

### Spusteni cele sady

```powershell
cd C:\jj\emailAssistant
C:/jj/emailAssistant/.venv/Scripts/python.exe extract_pdf_amounts.py
```

- Skript projde vsechny PDF ve zdrojove slozce, ke kazdemu ulozi Bill-To (z nazvu i z tela PDF), sumu `Amount Open`, menu a pripadne chyby extrakce.
- Excel se vzdy prepise (muzes ho premenovat, pokud chces archivovat). Cesta lze zmenit parametrem `--output`.

### Rychly test na vzorku

```powershell
C:/jj/emailAssistant/.venv/Scripts/python.exe extract_pdf_amounts.py --limit 50
```

Parametr `--limit` omezi pocet souboru pro rychle overeni logiky. Vystup se ulozi do stejne slozky `output/`.