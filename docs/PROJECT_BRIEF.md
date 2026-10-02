# Arbiter: AI Governance Gateway & AI Act Compliance Toolkit

> **Documento di avvio progetto**: versione originale del 2026-10-02.
> È la fonte di verità dei requisiti iniziali. Non si modifica a posteriori: ogni
> cambiamento di scope o di scelta tecnica passa da un ADR in `docs/adr/`.

## Ruolo e obiettivo

Agisci come senior software architect e Python engineer. Costruiamo insieme un progetto
open source (Apache 2.0), modulare e production-ready, che serva anche come portfolio
delle mie competenze in: A2A (Agent2Agent protocol), MCP (Model Context Protocol),
FinOps per AI, Compliance & Governance (EU AI Act, GDPR), automazione e scalabilità.

Il progetto ha due componenti che condividono un core comune:

1. **Gateway / Control Plane**: layer tra applicazioni e modelli/agenti che gestisce
   routing, comunicazione A2A, registry di server MCP, metering dei costi, policy e audit.
2. **Compliance Toolkit**: analisi e monitoraggio della conformità all'AI Act, utilizzabile
   sia integrato nel gateway (sui dati di traffico reali) sia standalone da singoli utenti
   tramite CLI/agente locale per analizzare i propri sistemi o il proprio PC.

## Stack vincolante

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, uv per la gestione pacchetti
- Azure come cloud target: Azure OpenAI / AI Foundry, Azure Container Apps (default) con
  opzione AKS, Azure Database for PostgreSQL, Azure Key Vault, Azure Monitor/App Insights,
  Entra ID per autenticazione, Azure Service Bus o Event Grid per eventi asincroni
- Infrastructure as Code: Bicep (preferito) o Terraform
- OpenTelemetry per tracing/metriche/log
- Policy engine: valuta OPA (Rego) vs motore di regole Python; proponi e motiva
- Docker Compose per sviluppo locale con emulatori/mock al posto dei servizi Azure
- Test: pytest, coverage > 80% sul core; lint e type-check con ruff e mypy (strict)
- CI/CD: GitHub Actions (lint, test, security scan, build immagini, deploy su Azure)

## Principi architetturali

- Architettura modulare a plugin: ogni capacità è un modulo con interfaccia esplicita
  (Protocol/ABC), sostituibile e disattivabile da configurazione
- Provider astratti: Azure è l'implementazione di riferimento, ma nessun modulo del core
  deve dipendere direttamente da SDK Azure (adapter pattern)
- 12-factor app, configurazione via env + file, nessun segreto nel codice
- Privacy by design: minimizzazione dati, redazione PII prima della persistenza,
  retention configurabile, data residency UE
- Ogni decisione automatizzata è spiegabile e tracciata nell'audit log

## Moduli del Gateway

1. **llm_router**: proxy compatibile OpenAI API, routing tra modelli in base a costo,
   latenza, policy e classe di rischio; fallback e retry
2. **a2a**: implementazione del protocollo A2A (Agent Card, task lifecycle, streaming);
   registry degli agenti con capabilities e autorizzazioni
3. **mcp_registry**: catalogo governato di server MCP, approvazione dei tool,
   scoping dei permessi per agente/team, logging di ogni invocazione
4. **finops**: metering di token e costi per tenant/team/progetto/utente, budget e
   alert, report, raccomandazioni di ottimizzazione (modelli più economici, caching)
5. **policy**: valutazione pre e post chiamata (PII, contenuti vietati, uso non consentito,
   limiti per classe di rischio)
6. **audit**: log append-only con hash chain per integrità verificabile, esportabile
7. **identity**: multi-tenancy, RBAC, integrazione Entra ID

## Moduli del Compliance Toolkit

1. **inventory**: registro dei sistemi AI (scoperti dal gateway o dichiarati manualmente)
2. **classifier**: classificazione secondo l'AI Act: fuori ambito, pratiche vietate
   (art. 5), alto rischio (art. 6 e Allegato III), obblighi di trasparenza (art. 50),
   GPAI; ogni classificazione con motivazione e articoli di riferimento
3. **scanner**: analisi di configurazioni, prompt, log, dataset e uso dei modelli per
   rilevare rischi e potenziali violazioni
4. **findings**: ogni rilevazione ha severità, confidenza, evidenze, articolo AI Act/GDPR
   collegato e stato (aperto, confermato, falso positivo, mitigato, accettato) con
   workflow di revisione umana; il feedback sui falsi positivi migliora le regole
5. **daily_digest**: sintesi giornaliera automatica (job schedulato) con nuovi findings,
   trend, rischi emergenti, falsi positivi chiusi, azioni consigliate; output Markdown,
   HTML ed email
6. **local_agent**: CLI `arbiter` installabile (`pip install` / `uvx`) per singoli utenti
   che analizza il proprio PC o sistema in modalità locale e offline-first: tool AI
   installati, configurazioni di agenti e server MCP locali, estensioni, flussi di dati
   verso servizi AI; solo con consenso esplicito, nessun invio di dati senza opt-in
7. **simulation**: modalità sandbox con scenari di esempio (sistemi fittizi conformi e
   non) per dimostrazioni e formazione
8. **reporting**: documentazione tecnica e report di audit esportabili (PDF/Markdown)

Tutti gli output devono riportare chiaramente che si tratta di uno strumento di supporto
e non di consulenza legale. Le regole devono essere versionate e indicare a quale
versione/stato dell'AI Act si riferiscono (le scadenze applicative cambiano nel tempo):
prima di codificarle, verifica lo stato normativo aggiornato.

## Modalità di lavoro

NON scrivere codice subito. Procedi per fasi e fermati alla fine di ognuna per la mia
approvazione:

- **Fase 0 – Analisi**: rivedi i requisiti, segnala ambiguità, rischi e semplificazioni
  possibili. Proponi lo scope dell'MVP (cosa entra nella v0.1 e cosa no).
- **Fase 1 – Architettura**: struttura del monorepo, diagrammi (Mermaid) di componenti e
  flussi, modello dati, interfacce dei moduli, ADR per le scelte principali.
- **Fase 2 – Scaffolding**: repo, tooling, CI, Docker Compose, core condiviso, config.
- **Fase 3 – MVP Gateway**: llm_router + finops + audit + policy di base.
- **Fase 4 – MVP Compliance**: inventory + classifier + findings + daily_digest + CLI.
- **Fase 5 – A2A e MCP**: registry e comunicazione tra agenti con una demo multi-agente.
- **Fase 6 – Azure**: IaC Bicep, deploy su Container Apps, osservabilità, hardening.
- **Fase 7 – Packaging**: README da portfolio, quickstart in 5 minuti, demo scenario,
  documentazione (MkDocs), esempi, CONTRIBUTING, SECURITY.md.

Per ogni fase: elenca i task, implementa con test, aggiorna la documentazione, e chiudi con
un riepilogo di cosa è stato fatto, cosa resta e le decisioni prese. Crea e mantieni un file
CLAUDE.md con convenzioni, comandi e decisioni del progetto.

## Decisioni e tracciabilità

Ogni scelta non banale (tecnologia, architettura, scope, trade-off) va valutata insieme
prima di essere implementata:

1. Presentami le opzioni (almeno 2) con una tabella pro/contro che consideri: complessità,
   costo su Azure, scalabilità, sicurezza, impatto su compliance/privacy, manutenibilità,
   lock-in. Indica la tua raccomandazione motivata e attendi la mia decisione.
2. Dopo la decisione, crea un ADR in `docs/adr/NNNN-titolo.md` (formato MADR) con:
   contesto, opzioni considerate, pro/contro, decisione, conseguenze, stato
   (proposto / accettato / sostituito da ADR-XXXX). Le decisioni non si cancellano:
   se cambiano, si crea un nuovo ADR che sostituisce il precedente.
3. Aggiorna `CHANGELOG.md` seguendo Keep a Changelog e Semantic Versioning, con le
   sezioni Added / Changed / Deprecated / Removed / Fixed / Security, collegando
   ogni voce rilevante all'ADR corrispondente.
4. Usa Conventional Commits (feat, fix, docs, refactor, chore...) in modo che il
   changelog sia coerente con la history git e generabile anche automaticamente.
5. A fine di ogni fase, riepiloga le decisioni prese e le eventuali questioni aperte
   in `docs/adr/README.md` (indice delle decisioni).
