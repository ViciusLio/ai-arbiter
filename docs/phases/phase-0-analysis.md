# Fase 0: Analisi dei requisiti e proposta di scope MVP

- **Stato**: chiusa il 2026-10-02. D1–D7 decise e registrate in
  [ADR-0002 … ADR-0008](../adr/README.md); lo scope v0.1 (§6) è in
  [ADR-0009](../adr/0009-v0-1-scope.md), ancora da confermare
- **Data**: 2026-10-02
- **Input**: [PROJECT_BRIEF.md](../PROJECT_BRIEF.md)
- **Output atteso**: decisioni D1–D7 (§8) e approvazione dello scope v0.1 (§6)
- **Nota**: documento storico in italiano; dalla Fase 1 la documentazione è in inglese
  (ADR-0004). L'orientamento "workspace multi-pacchetto" del §9 è stato rivisto in
  ADR-0010

> Nessun codice è stato scritto in questa fase. Le scelte tecniche di dettaglio sono
> rinviate alla Fase 1 (§9), dove verranno presentate con tabella opzioni e ADR.

---

## 1. Sintesi

Il brief è solido e coerente, ma descrive **15 moduli** su due prodotti: realizzati tutti
allo stesso livello produrrebbero un progetto largo e poco profondo. Tre osservazioni
guidano il resto dell'analisi:

1. **Il gateway da solo non è un elemento distintivo.** LiteLLM, Kong AI Gateway, Portkey
   e agentgateway coprono già routing LLM, MCP e (alcuni) A2A. Quello che nessuno di
   questi fa bene è collegare il traffico reale a un **inventario di sistemi AI
   classificati secondo l'AI Act**, con evidenze verificabili. Il valore di Arbiter è
   quel ponte.
2. **Il quadro normativo è cambiato a luglio 2026** (Digital Omnibus on AI): gli obblighi
   per l'alto rischio sono rinviati a dicembre 2027, mentre l'art. 50 è applicabile da due
   mesi. L'MVP conviene centrarlo su ciò che è già applicabile oggi.
3. **Anche i protocolli sono cambiati di recente**: A2A è alla 1.0 (Linux Foundation) e MCP
   ha pubblicato a luglio la revisione più ampia dal lancio (core stateless). Arbiter deve
   governare questi protocolli usando gli SDK ufficiali, non reimplementarli.

Proposta: **v0.1 = una fetta verticale completa** (richiesta → policy → routing → metering
→ audit → inventario → classificazione → finding → digest), dimostrabile in 5 minuti con
scenari simulati. A2A/MCP, Azure e packaging seguono come v0.2, v0.3 e v1.0.

---

## 2. Stato verificato al 2026-10-02

### 2.1 AI Act: Reg. (UE) 2024/1689 come modificato dal Digital Omnibus on AI

Il Digital Omnibus è stato adottato dal Consiglio il 29 giugno 2026, pubblicato in
Gazzetta Ufficiale a luglio ed è in vigore dal 27 luglio 2026.

| Data | Cosa si applica | Stato a oggi |
|---|---|---|
| 2 feb 2025 | Art. 5 pratiche vietate; art. 4 alfabetizzazione AI | Applicabile. L'Omnibus ha attenuato l'art. 4: da "garantire" a "sostenere lo sviluppo" dell'alfabetizzazione |
| 2 ago 2025 | Obblighi per modelli GPAI (Capo V), governance, sanzioni | Applicabile |
| 2 ago 2026 | Art. 50 obblighi di trasparenza | **Applicabile da due mesi** (non rinviato). Linee guida della Commissione adottate il 20 lug 2026 |
| 2 dic 2026 | Fine del periodo transitorio art. 50(2) (marcatura machine-readable) per sistemi generativi già sul mercato prima del 2 ago 2026; nuovi divieti art. 5 (immagini intime non consensuali, CSAM generati da AI) | Tra due mesi |
| 2 ago 2027 | Modelli GPAI immessi sul mercato prima del 2 ago 2025; termine per le sandbox nazionali | Futuro |
| 2 dic 2027 | Alto rischio: Allegato III (sistemi stand-alone) | **Rinviato** (era 2 ago 2026) |
| 2 ago 2028 | Alto rischio: Allegato I (AI integrata in prodotti regolati) | **Rinviato** (era 2 ago 2027) |

Altre modifiche rilevanti dell'Omnibus: base giuridica per trattare categorie particolari
di dati a fini di rilevazione dei bias estesa a tutti i sistemi AI e ai modelli GPAI;
competenza esclusiva dell'AI Office sui sistemi basati su GPAI dello stesso sviluppatore.

**Limite di questa verifica.** Le date vengono da fonti secondarie (studi legali e
fornitori, elencati in §10), concordi tra loro. Il numero del regolamento modificativo
(riportato come Reg. (UE) 2026/1744) compare in una sola fonte. Prima di codificare le
regole in Fase 4 va fatta la verifica sul testo consolidato in EUR-Lex, articolo per
articolo.

**Conseguenze di progetto**

- Ogni rule pack dichiara `as_of`, `legal_basis` (regolamento + atti modificativi) e, per
  ogni obbligo, `applies_from`. L'output del classifier mostra sempre "applicabile dal".
- L'MVP si concentra su ciò che è applicabile ora: screening art. 5, trasparenza art. 50,
  art. 4, consapevolezza GPAI. L'alto rischio è trattato come **readiness** (cosa servirà
  entro il 2 dic 2027), non come violazione.
- Un finding non può dire "non conforme" per un obbligo non ancora applicabile: la
  severità dipende anche dalla data.

### 2.2 Protocolli

| Protocollo | Stato | Implicazione |
|---|---|---|
| **A2A** | Specifica 1.0 sotto Linux Foundation; Agent Card firmate (JWS + JCS); `a2a-sdk` Python 1.1.x con modalità di compatibilità 0.3; trasporti JSON-RPC, REST, gRPC | Usare l'SDK ufficiale. Il valore di Arbiter è registry, autorizzazione, verifica firma delle card e audit |
| **MCP** | Revisione 2026-07-28: core stateless (niente handshake `initialize` né sessione), autorizzazione più rigida (validazione `iss`, RFC 9207), framework di estensioni | Un proxy MCP è più semplice con il core stateless, ma i server esistenti parlano ancora revisioni precedenti: va fissata la matrice di versioni supportate |

### 2.3 Panorama

Gateway open source esistenti (LiteLLM, Kong, Portkey, agentgateway) offrono già proxy
OpenAI-compatibile, budget, guardrail e gateway MCP; Kong copre anche A2A. Competere sul
numero di provider o sulle prestazioni del data path non è realistico né utile al
portfolio.

---

## 3. Ambiguità e chiarimenti

| # | Requisito | Ambiguità | Proposta |
|---|---|---|---|
| A1 | "production-ready" | Significato per un progetto v0.x di una persona | Pratiche di ingegneria da produzione (test, tipi, CI, osservabilità, sicurezza di base, limiti documentati). Non: HA dimostrata, pen-test, SLA |
| A2 | `classifier` | Non è indicato **il ruolo** dell'utente (provider, deployer, importatore, distributore): gli obblighi dipendono dal ruolo, non solo dalla classe | Aggiungere `role` all'inventario; v0.1 orientata al deployer (D6) |
| A3 | `classifier` | La classe dipende dalla **finalità prevista**, che non si deduce dal traffico | Classificazione su attributi dichiarati; il traffico fornisce evidenze e incongruenze, non la classe (D2) |
| A4 | `classifier`: GPAI | Gli obblighi GPAI gravano sul **provider del modello**; chi usa il gateway quasi sempre non lo è | Registrare "usa un modello GPAI di X" come attributo; obblighi GPAI solo se role = provider di modello |
| A5 | `scanner`: "configurazioni, prompt, log, dataset" | Ambito molto ampio; l'analisi di dataset è un prodotto a sé | v0.1: configurazioni, inventario e metadati di traffico. Dataset fuori scope fino a nuova decisione |
| A6 | `findings`: "il feedback migliora le regole" | Apprendimento automatico o taratura manuale? | v0.1: soppressioni con ambito (regola/sistema/fingerprint) e precisione per regola nel digest. Nessun auto-tuning |
| A7 | `local_agent`: "flussi di dati verso servizi AI" | Implica cattura di rete: privilegi elevati, invasiva, diversa per OS | v0.1: solo scoperta statica (file di configurazione noti, in sola lettura). Nessuna cattura di rete |
| A8 | `local_agent`: utente singolo | L'uso personale non professionale è escluso dall'AI Act (art. 2(10)) | Presentare la scansione locale come **inventario AI e igiene di sicurezza** (server MCP, permessi, segreti in chiaro). La parte AI Act vale per l'uso professionale |
| A9 | `a2a`: "implementazione del protocollo" | Reimplementare o usare l'SDK? | SDK ufficiale; Arbiter aggiunge governance |
| A10 | `mcp_registry`: "logging di ogni invocazione" | Un catalogo non vede le invocazioni: serve stare nel percorso dati | In Fase 5 il modulo comprende catalogo (control plane) **e** proxy MCP (data plane) |
| A11 | `llm_router`: "classe di rischio" | Rischio di cosa? | Ogni richiesta è associata a un sistema AI dell'inventario (via API key); la classe del sistema vincola modelli e regioni ammessi |
| A12 | `policy`: post-chiamata | In streaming i token sono già stati inviati | v0.1: enforcement su risposte non-streaming; in streaming solo rilevazione e finding. Modalità buffer in seguito |
| A13 | `audit`: append-only | Conflitto con cancellazione/retention GDPR | L'audit log contiene solo metadati e identificativi pseudonimi; i payload stanno in uno store separato con retention |
| A14 | `audit`: "integrità verificabile" | Verificabile contro chi? Chi ha accesso al DB può riscrivere l'intera catena | v0.1: hash chain + comando di verifica + export. Ancoraggio esterno (checkpoint firmati) in Fase 6 |
| A15 | `finops`: costi | I prezzi cambiano e in Azure dipendono da regione e tipo di deployment | Catalogo prezzi versionato e configurabile; i costi sono sempre "stimati" |
| A16 | Postgres + CLI offline | La CLI standalone non può richiedere Postgres | Supporto doppio Postgres/SQLite: vincola lo schema a tipi portabili, CI su entrambi |
| A17 | `daily_digest`: email | Canale non specificato | Adapter SMTP (Mailpit in locale); Azure Communication Services in Fase 6 |
| A18 | `reporting`: PDF | Le librerie PDF richiedono dipendenze native, scomode su Windows | v0.1: Markdown e HTML. PDF come extra opzionale più avanti |
| A19 | Interfaccia web | Non menzionata | Nessuna SPA in v0.1 (D5) |
| A20 | Lingua degli artefatti | Brief in italiano, progetto open source | Vedi D3 |
| A21 | Nome | `arbiter` è già occupato su PyPI | Vedi D4 |

---

## 4. Rischi

| # | Rischio | Prob. | Impatto | Mitigazione |
|---|---|---|---|---|
| R1 | Scope troppo ampio: molti moduli a metà, nessuna demo completa | Alta | Alto | Fetta verticale in v0.1; ogni fase si chiude con qualcosa di eseguibile |
| R2 | Regole AI Act superate da nuovi atti (linee guida, atti delegati, standard armonizzati) | Alta | Alto | Rule pack versionati con `as_of`; verifica su fonte primaria a ogni rilascio; data di verifica visibile in ogni output |
| R3 | Falsa sensazione di conformità per l'utente | Media | Alto | Disclaimer in ogni output; lessico "indicativo" e "nessun rilievo", mai "conforme"; revisione umana nel workflow |
| R4 | Il gateway custodisce chiavi dei provider e vede i prompt: bersaglio ad alto valore | Media | Alto | Segreti solo via adapter (Key Vault / env); API key salvate come hash; nessun corpo dei prompt persistito di default; threat model in Fase 1 |
| R5 | Qualità della rilevazione PII, in particolare in italiano | Alta | Medio | Detector pluggable; metriche di precisione sugli scenari simulati; limiti dichiarati |
| R6 | Evoluzione rapida di A2A e MCP | Media | Medio | Versioni di specifica fissate e dichiarate; SDK ufficiali dietro adapter; test di contratto |
| R7 | Latenza aggiunta dal proxy | Media | Medio | Data path async; policy con budget di tempo; overhead misurato in CI |
| R8 | Doppio database (Postgres + SQLite) | Media | Medio | Solo tipi portabili; migrazioni testate su entrambi |
| R9 | Sviluppo su Windows, produzione su Linux | Media | Basso | Docker Compose via WSL2; matrice CI con `windows-latest` per la CLI |
| R10 | Costi Azure fuori controllo per un progetto dimostrativo | Bassa | Medio | Scale-to-zero, SKU minimi, budget alert nell'IaC, comando di teardown |
| R11 | La scansione locale legge file sensibili | Media | Alto | Sola lettura, elenco esplicito dei percorsi prima dell'esecuzione, consenso per categoria, nessun valore di segreti nei risultati, nessuna rete |
| R12 | Catena di hash sotto scritture concorrenti | Media | Medio | Una catena per tenant con scrittura serializzata; progettazione in Fase 1 |

---

## 5. Semplificazioni proposte

1. **Provider LLM**: tre adapter (Azure OpenAI, generico OpenAI-compatibile, mock). Il
   generico copre già Ollama, vLLM e la maggior parte dei servizi.
2. **Eventi asincroni**: bus in-process dietro un `Protocol` più tabella outbox in v0.1;
   Service Bus arriva come adapter in Fase 6. Nessun broker da avviare in locale.
3. **Identity**: tenant/team/progetto/API key e tre ruoli (admin, auditor, developer) in
   v0.1; validazione OIDC generica ed Entra ID in Fase 6. `tenant_id` è presente in ogni
   tabella dal primo giorno.
4. **Scheduler**: il digest è un comando (`arbiter digest run`); la schedulazione è
   esterna (cron in locale, Container Apps Job in Azure).
5. **Simulation** anticipata in v0.1: gli scenari fittizi sono insieme dati demo, fixture
   di test e benchmark delle regole. Costano poco e rendono il progetto dimostrabile.
6. **AKS e Terraform**: documentati come opzione, non implementati.
7. **Scanner** in v0.1 ridotto a un set di 10–15 regole ad alta precisione.

---

## 6. Scope proposto per la v0.1

| Modulo | Dentro la v0.1 | Fuori (e quando) |
|---|---|---|
| **core** | Config (env + file), registry dei plugin, modelli di dominio, contesto tenant, persistenza Postgres/SQLite, bus eventi in-process, bootstrap OpenTelemetry, primitive di redazione | - |
| **llm_router** | `/v1/chat/completions` con streaming SSE, `/v1/models`; adapter Azure OpenAI, OpenAI-compatibile, mock; routing per priorità, costo e vincoli di policy/classe di rischio; fallback e retry | Routing per latenza, embeddings, Responses API, cache semantica (v0.2+) |
| **finops** | Metering per tenant/team/progetto/utente/sistema AI; catalogo prezzi versionato; budget con soglia soft e hard; API di consumo e report Markdown | Alert via email/webhook, raccomandazioni di ottimizzazione (v0.2) |
| **policy** | Motore pre/post chiamata; rilevazione e redazione PII; allowlist di modelli e regioni per classe di rischio; enforcement dei budget | Moderazione dei contenuti con classificatori esterni, adapter OPA (dopo decisione in Fase 1) |
| **audit** | Log append-only con hash chain per tenant; `arbiter audit verify`; export JSONL | Ancoraggio esterno e firma dei checkpoint (v0.3) |
| **identity** | Tenant, team, progetti, API key (hash), RBAC a tre ruoli | Entra ID / OIDC (v0.3) |
| **inventory** | Sistemi dichiarati via YAML/API/CLI con ruolo AI Act; scoperta dal traffico del gateway; segnalazione di uso non dichiarato | - |
| **classifier** | Rule pack versionato; esiti: fuori ambito, pratica vietata, alto rischio (art. 6, Allegato III, deroga 6(3)), trasparenza (art. 50), rischio minimo; motivazione, articoli e date di applicazione | Obblighi lato provider di modelli GPAI; assistenza LLM (v0.2+) |
| **scanner** | 10–15 regole su configurazioni, inventario e metadati di traffico | Analisi di prompt/log estesa, dataset |
| **findings** | Modello completo (severità, confidenza, evidenze, articolo, stato); macchina a stati con revisione umana via CLI/API; soppressioni | Auto-tuning delle regole |
| **daily_digest** | Markdown e HTML; comando CLI; invio SMTP opzionale | Canali aggiuntivi (Teams, ACS) |
| **local_agent** | Scoperta statica con consenso: configurazioni MCP e strumenti AI noti, in sola lettura e offline | Estensioni di IDE/browser, flussi di rete (v0.2+) |
| **simulation** | 4 scenari: chatbot con disclosure corretta; screening CV (alto rischio, Allegato III); riconoscimento emozioni sul lavoro (vietato, art. 5); assistente di codice interno (minimo) | Altri scenari |
| **reporting** | Report di sistema e di audit in Markdown | PDF |
| **a2a** | - | Fase 5 (v0.2) |
| **mcp_registry** | - | Fase 5 (v0.2) |
| **Azure / IaC** | Solo l'adapter Azure OpenAI | Fase 6 (v0.3) |
| **Interfaccia web** | - | Da decidere dopo la v0.1 |

**Criterio di accettazione della v0.1**: da repository pulito, `docker compose up` e un
comando di demo mostrano in meno di 5 minuti una richiesta bloccata per policy, una
instradata per costo, il costo attribuito a un progetto, la catena di audit verificata,
i quattro sistemi classificati con articoli e date, e un digest con i finding.

---

## 7. Fasi e versioni

| Fase | Contenuto | Rilascio |
|---|---|---|
| 1 | Architettura, modello dati, interfacce, ADR | - |
| 2 | Scaffolding, CI, Compose, core | - |
| 3 | Gateway MVP | `0.1.0-alpha` |
| 4 | Compliance MVP + simulation + CLI | **`0.1.0`** |
| 5 | A2A + MCP + demo multi-agente | `0.2.0` |
| 6 | Azure, Entra ID, osservabilità, hardening | `0.3.0` |
| 7 | Documentazione e packaging | `1.0.0` |

Due variazioni rispetto al brief: **simulation** entra in Fase 4 (§5.5) e README/quickstart
crescono a ogni fase invece di nascere tutti in Fase 7.

---

## 8. Decisioni richieste ora

### D1: Posizionamento

| Criterio | A. Compliance-first, gateway snello proprio | B. Gateway-first, compliance come estensione | C. Solo toolkit, come plugin di un gateway esistente |
|---|---|---|---|
| Complessità | Media | Alta | Bassa |
| Costo su Azure | Basso (un'app + Postgres) | Medio | Minimo |
| Scalabilità | Adeguata (proxy async stateless) | Richiede ottimizzazione seria del data path | Delegata al gateway ospite |
| Sicurezza | Superficie contenuta, sotto controllo diretto | Superficie ampia | Ereditata dall'ospite |
| Compliance / privacy | Evidenze di prima mano; controllo pieno su redazione e audit | Come A, ma con meno tempo dedicato | Limitata a ciò che l'ospite espone |
| Manutenibilità | Sostenibile per una persona | Non sostenibile | Dipende dalle API di terzi |
| Lock-in | Nessuno | Nessuno | Sul gateway ospite |
| Valore per il portfolio | Alto: mostra tutte le competenze in una nicchia libera | Basso: clone di prodotti maturi | Medio: non mostra A2A/MCP/routing |

**Raccomandazione: A.** È l'unica opzione che dimostra tutte le competenze elencate nel
brief senza entrare in una gara di funzionalità con prodotti maturi.

### D2: Approccio del classifier

| Criterio | A. Deterministico (albero decisionale su attributi dichiarati) | B. LLM-first (classifica da descrizione libera) | C. Ibrido (decide il deterministico; l'LLM, opt-in, suggerisce solo gli attributi) |
|---|---|---|---|
| Complessità | Media | Bassa all'inizio, alta per renderlo affidabile | Alta |
| Costo su Azure | Nullo | Token a ogni classificazione | Token solo se attivato |
| Scalabilità | Ottima | Limitata da quote e latenza | Ottima |
| Sicurezza | Nessun dato esce | Le descrizioni dei sistemi vanno a un modello | Opt-in esplicito |
| Compliance / privacy | Spiegabile e riproducibile; funziona offline | Non riproducibile, difficile da difendere in audit | Spiegabile; suggerimenti marcati come tali |
| Manutenibilità | Regole da aggiornare a mano con la norma | Prompt fragili | Entrambe |
| Lock-in | Nessuno | Sul modello | Nessuno |

**Raccomandazione: A in v0.1**, con interfacce che permettano C in seguito. Il brief
richiede decisioni spiegabili e una CLI offline-first: B non soddisfa nessuno dei due.

### D3: Lingua degli artefatti

| Opzione | Pro | Contro |
|---|---|---|
| **A. Inglese** per codice, README, documentazione e ADR; conversazione in italiano | Pubblico open source e recruiter internazionali; coerenza con l'ecosistema | Il brief resta in italiano come documento storico |
| B. Italiano | Coerenza con il brief | Riduce molto la platea |
| C. Bilingue | Massima copertura | Doppia manutenzione di ogni documento |

**Raccomandazione: A**, con digest e report localizzabili (en/it) perché sono rivolti a
utenti finali. I criteri tecnici del brief qui non sono discriminanti.

### D4: Nome e pacchetto

`arbiter` su PyPI è occupato (libreria di gestione dati, ultimo rilascio 2021). Su GitHub
esistono inoltre più progetti "Arbiter" in ambito LLM, tra cui un router LLM e un
framework di valutazione.

| Opzione | Pro | Contro |
|---|---|---|
| **A. Marchio "Arbiter", distribuzione con altro nome** (es. `arbiter-gov`), comando `arbiter` | Mantiene il nome scelto | `uvx arbiter` non funziona (serve `uvx arbiter-gov`); omonimie su GitHub |
| B. Nuovo nome univoco | Ricercabilità, `pip install <nome>` uguale al comando | Va scelto e verificato |

**Raccomandazione: A** se il nome ti sta a cuore, verificando la disponibilità del nome di
distribuzione prima della Fase 2. Se la ricercabilità conta di più, B.

### D5: Interfaccia web

**Raccomandazione: nessuna SPA in v0.1.** API, CLI e report/digest HTML statici bastano per
la demo. Una dashboard in sola lettura si può valutare dopo la v0.1 con un ADR dedicato.

### D6: Ruolo AI Act primario

**Raccomandazione: deployer.** Chi mette un gateway davanti a modelli di terzi è quasi
sempre un deployer. Gli obblighi del provider (di sistema o di modello GPAI) restano nel
modello dati ma vengono coperti dalle regole più avanti.

### D7: Azure (non bloccante)

Hai già una sottoscrizione e un budget mensile indicativo? Serve per dimensionare la
Fase 6. Stima di massima per l'ambiente demo: poche decine di euro al mese con
scale-to-zero, più i token consumati.

---

## 9. Decisioni rinviate alla Fase 1

Ognuna verrà presentata con tabella completa e ADR. L'orientamento indicato è preliminare.

| Tema | Opzioni | Orientamento |
|---|---|---|
| Policy engine | OPA (Rego) / motore Python con regole dichiarative | Python dietro `Protocol`, adapter OPA opzionale: niente sidecar, funziona nella CLI offline |
| Livello provider LLM | Adapter propri / libreria LiteLLM | Adapter propri: poche dipendenze nel data path |
| Rilevazione PII | Regex / Presidio / Azure AI Language | Regex di base più detector pluggable |
| Struttura del monorepo | Pacchetto unico con extras / workspace uv multi-pacchetto | Workspace: la CLI non deve tirarsi dietro FastAPI |
| Persistenza | Solo Postgres / Postgres + SQLite | Entrambi (A16) |
| Eventi | In-process + outbox / Service Bus / Event Grid | In-process + outbox, poi Service Bus |
| IaC | Bicep / Terraform | Bicep, come da preferenza del brief |
| Integrità dell'audit | Solo hash chain / checkpoint firmati / storage immutabile | Hash chain ora, checkpoint firmati in Fase 6 |
| Store dei payload | Nessun corpo / corpo redatto con retention | Nessun corpo di default |

---

## 10. Fonti

AI Act e Digital Omnibus:

- [Gibson Dunn: EU AI Act Omnibus Agreement](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/)
- [Morgan Lewis: What went into effect on 2 August](https://www.morganlewis.com/blogs/sourcingatmorganlewis/2026/08/eu-ai-acts-transparency-rules-what-went-into-effect-on-2-august)
- [Commissione europea: FAQ sugli obblighi di trasparenza dell'art. 50](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act)
- [Cloud Security Alliance: Article 50 transparency obligations take effect](https://labs.cloudsecurityalliance.org/research/csa-research-note-eu-ai-act-article-50-transparency-20260729/)
- [Fontvera: AI Act Digital Omnibus is law](https://fontvera.eu/intelligence/ai-act-omnibus-delay-failed)
- [Usercentrics: Digital Omnibus now in force](https://usercentrics.com/knowledge-hub/eu-ai-act-high-risk-delay-article-50-transparency-consent/)

Protocolli:

- [a2a-sdk su PyPI](https://pypi.org/project/a2a-sdk/)
- [MCP: The 2026-07-28 Specification](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [MCP: Key Changes 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/changelog)

Panorama e nome:

- [Braintrust: AI gateway comparison 2026](https://www.braintrust.dev/articles/ai-gateway-comparison-2026)
- [Maxim: LLM gateways for AI agents 2026](https://www.getmaxim.ai/articles/5-best-llm-gateways-for-ai-agents-in-2026-mcp-support-tool-governance-and-cost-tracking/)
- [PyPI: arbiter](https://pypi.org/project/arbiter/)
- [cnf/arbiter](https://github.com/cnf/arbiter), [ashita-ai/arbiter](https://github.com/ashita-ai/arbiter)

---

*Questo documento è un supporto alla progettazione e non costituisce consulenza legale.*
