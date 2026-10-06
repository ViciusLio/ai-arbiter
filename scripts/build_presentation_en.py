"""Build the English presentation from the Italian one.

    uv run python scripts/build_presentation_en.py

`docs/presentation/arbiter.it.html` is the source: structure, style and script are
written once, there. This script replaces every Italian text with its English one and
writes `docs/presentation/arbiter.en.html`. It fails when a text of the table is not in
the source, so a change to the Italian page cannot silently leave the English one behind.
"""

import re
import sys
from pathlib import Path

DIRECTORY = Path(__file__).parents[1] / "docs" / "presentation"
SOURCE = DIRECTORY / "arbiter.it.html"
TARGET = DIRECTORY / "arbiter.en.html"

# Words that only an untranslated Italian sentence would contain.
ITALIAN = (
    r"\b(?:che|della|delle|degli|non|una|uno|per|con|sono|più|già|anche|perché|ogni|chi|"
    r"cosa|questo|quello|dove|quando|gli|nel|nella|alla|dal|dei|è|ciò)\b"
)

TEXTS: list[tuple[str, str]] = [
    ('<html lang="it">', '<html lang="en">'),
    ("<title>Arbiter in breve</title>", "<title>Arbiter in brief</title>"),
    (
        'content="Che cosa fa Arbiter, come funziona e a che punto è, spiegato a chi non è tecnico."',
        'content="What Arbiter does, how it works and where it stands, for people who are not developers."',
    ),
    ('aria-label="Comandi"', 'aria-label="Controls"'),
    (
        'aria-label="Cambia tema chiaro o scuro">Tema</button>',
        'aria-label="Switch between the light and the dark theme">Theme</button>',
    ),
    ("Arbiter · progetto open source", "Arbiter · open source project"),
    (
        "Sapere quali sistemi di IA usi.<br>E poterlo mostrare.",
        "Know which AI systems you run.<br>And be able to show it.",
    ),
    (
        "Arbiter collega due cose che di solito restano separate: ciò che un'organizzazione <strong>dichiara</strong> sui propri sistemi di intelligenza artificiale e ciò che il loro <strong>traffico reale</strong> mostra. Lo fa con l'AI Act europeo come riferimento.",
        "Arbiter links two things that usually stay apart: what an organisation <strong>declares</strong> about its artificial intelligence systems and what their <strong>real traffic</strong> shows. Its reference is the European AI Act.",
    ),
    ("Versione alpha", "Alpha version"),
    ("Prima versione di prova su PyPI</span>", "First pre-release on PyPI</span>"),
    ("Licenza Apache 2.0", "Apache 2.0 licence"),
    (
        "Vai avanti con <kbd>→</kbd>, torna indietro con <kbd>←</kbd>, oppure usa i pulsanti ai lati. Molti riquadri si possono toccare.",
        "Go forward with <kbd>→</kbd>, back with <kbd>←</kbd>, or use the buttons at the sides. Many boxes can be tapped.",
    ),
    ('aria-label="Sezione precedente"', 'aria-label="Previous section"'),
    ('aria-label="Sezione successiva"', 'aria-label="Next section"'),
    (
        "Presentazione aggiornata al 5 ottobre 2026.",
        "Presentation updated on 5 October 2026.",
    ),
    ("Il problema</div>", "The problem</div>"),
    (
        "L'IA entra in azienda più in fretta di quanto la si riesca a contare",
        "AI enters an organisation faster than anyone can count it",
    ),
    (
        "Un assistente per il servizio clienti, un modulo che ordina i curriculum, un collega che incolla dati in un chatbot. Ognuno è un sistema di IA, e la legge chiede di sapere quali sono, a cosa servono e quanto sono rischiosi.",
        "An assistant for customer service, a module that ranks job applications, a colleague who pastes data into a chatbot. Each is an AI system, and the law asks you to know which they are, what they are for and how risky they are.",
    ),
    ("L'inventario invecchia", "The inventory goes stale"),
    (
        "Un elenco scritto a mano dice ciò che qualcuno ricordava quel giorno. Non dice ciò che succede oggi.",
        "A list written by hand says what someone remembered that day. It does not say what happens today.",
    ),
    ("L'uso non dichiarato</h3>", "Undeclared use</h3>"),
    (
        "Quello che nessuno ha messo nell'elenco è proprio quello che nessuno sta controllando.",
        "What nobody put on the list is exactly what nobody is watching.",
    ),
    ("Le regole hanno date", "The rules have dates"),
    (
        "L'AI Act si applica per tappe. Sapere <em>cosa</em> vale <em>da quando</em> è metà del lavoro.",
        "The AI Act applies in stages. Knowing <em>what</em> applies <em>from when</em> is half of the work.",
    ),
    ("L'idea</div>", "The idea</div>"),
    ("Due metà che si parlano", "Two halves that talk to each other"),
    (
        "Ciascuna funziona anche da sola. Insieme fanno la cosa che conta: confrontare il dichiarato con l'osservato.",
        "Each works on its own. Together they do the thing that matters: compare what was declared with what is observed.",
    ),
    ("Il gateway: un casello", "The gateway: a toll booth"),
    (
        "Tutte le richieste ai modelli di IA passano da qui. Arbiter controlla chi chiede, applica le regole, oscura i dati personali, sceglie dove mandare la richiesta, ne stima il costo e scrive cosa è successo.",
        "Every request to an AI model goes through here. Arbiter checks who is asking, applies the rules, masks personal data, chooses where to send the request, estimates its cost and writes down what happened.",
    ),
    ("Produce le prove.", "It produces the evidence."),
    ("Il toolkit: un registro che controlla", "The toolkit: a register that checks"),
    (
        "Tiene l'inventario dei sistemi, propone per ognuno una classe di rischio secondo l'AI Act, confronta le dichiarazioni con il traffico e segnala ciò che non torna.",
        "It keeps the inventory of systems, proposes a risk class for each under the AI Act, compares the declarations with the traffic and reports what does not add up.",
    ),
    ("Usa le prove.", "It uses the evidence."),
    (
        "<strong>Il punto.</strong> I gateway per l'IA esistono già. Quello che manca è il collegamento tra il traffico e un inventario classificato secondo la legge: è lì che Arbiter lavora.",
        "<strong>The point.</strong> Gateways for AI already exist. What is missing is the link between the traffic and an inventory classified under the law: that is where Arbiter works.",
    ),
    ("Come funziona</div>", "How it works</div>"),
    ("Il viaggio di una richiesta", "The journey of a request"),
    ("Tocca i passaggi, oppure lasciali scorrere.", "Tap the steps, or let them play."),
    ("▶ Riproduci", "▶ Play"),
    ("⏸ Pausa", "⏸ Pause"),
    ("Classificazione</div>", "Classification</div>"),
    ("Una classe di rischio, sempre come proposta", "A risk class, always as a proposal"),
    (
        "Si risponde a domande prese dal testo della legge. Le stesse risposte danno sempre lo stesso risultato: nessun modello di IA decide la classe.",
        "You answer questions taken from the text of the law. The same answers always give the same result: no AI model decides the class.",
    ),
    ('Una risposta mancante non è un "no"', 'A missing answer is not a "no"'),
    (
        "Finché resta aperta una domanda che potrebbe portare a una classe più severa, il risultato è <em>indeterminato</em>.",
        "While a question is open that could lead to a more severe class, the result is <em>undetermined</em>.",
    ),
    ("Una persona conferma", "A person confirms"),
    (
        "Ogni classificazione è <em>indicativa</em> finché qualcuno, con nome e motivazione, non la conferma o la cambia.",
        "Every classification is <em>indicative</em> until someone, by name and with a reason, confirms it or changes it.",
    ),
    ("Ogni esito cita la norma", "Every outcome cites the provision"),
    (
        "Articolo e data da cui si applica. Un obbligo futuro è mostrato come preparazione, non come mancanza.",
        "The article and the date it applies from. An obligation of the future is shown as preparation, not as a failing.",
    ),
    ("Il calendario dell'AI Act", "The calendar of the AI Act"),
    ("Cosa si applica, e da quando", "What applies, and from when"),
    (
        "Le date sono quelle del Regolamento (UE) 2024/1689 come modificato nel 2026, lette sul testo della Gazzetta ufficiale.",
        "The dates are those of Regulation (EU) 2024/1689 as amended in 2026, read on the text of the Official Journal.",
    ),
    ("oggi, ottobre 2026", "today, October 2026"),
    ("<b>2 febbraio 2025</b>", "<b>2 February 2025</b>"),
    ("Pratiche vietate, alfabetizzazione sull'IA", "Prohibited practices, AI literacy"),
    ("<b>2 agosto 2026</b>", "<b>2 August 2026</b>"),
    ("Obblighi di trasparenza", "Transparency obligations"),
    ("<b>2 dicembre 2027</b>", "<b>2 December 2027</b>"),
    ("Sistemi ad alto rischio (Allegato III)", "High-risk systems (Annex III)"),
    ("<b>2 agosto 2028</b>", "<b>2 August 2028</b>"),
    ("Alto rischio in prodotti regolati (Allegato I)", "High risk in regulated products (Annex I)"),
    (
        '<strong>Limite importante.</strong> Le regole di Arbiter riassumono la legge in domande. Nessuna persona con formazione giuridica le ha ancora riviste: per questo ogni risultato dice "indicativo", e la versione 0.1.0 aspetta quella revisione.',
        '<strong>An important limit.</strong> The rules of Arbiter summarise the law as questions. No person with legal training has reviewed them yet: that is why every result says "indicative", and version 0.1.0 waits for that review.',
    ),
    ("Dichiarato contro osservato", "Declared against observed"),
    ("Quando i fatti contraddicono le carte", "When the facts contradict the paperwork"),
    (
        "Arbiter non legge il contenuto delle conversazioni: guarda solo i dati di contorno. Bastano per accorgersi di molto.",
        "Arbiter does not read the content of conversations: it looks only at the data around them. That is enough to notice a great deal.",
    ),
    (
        "<th>Cosa è stato dichiarato</th><th>Cosa mostra il traffico</th><th>Cosa segnala Arbiter</th>",
        "<th>What was declared</th><th>What the traffic shows</th><th>What Arbiter reports</th>",
    ),
    ('"Usiamo solo il modello A"', '"We only use model A"'),
    ("Richieste anche al modello B", "Requests to model B as well"),
    ("Modello non dichiarato", "Undeclared model"),
    ('"Non trattiamo dati personali"', '"We process no personal data"'),
    ("Indirizzi email nei messaggi", "E-mail addresses in the messages"),
    ("Dati personali non dichiarati", "Undeclared personal data"),
    ('"Quel sistema è dismesso"', '"That system is retired"'),
    ("<td>Risponde ancora</td>", "<td>It still answers</td>"),
    ("Sistema dismesso in uso", "Retired system in use"),
    ("<td>Nulla</td>", "<td>Nothing</td>"),
    ("Un gruppo di lavoro fa centinaia di richieste", "A team makes hundreds of requests"),
    ("Sistema candidato, mai dichiarato", "Candidate system, never declared"),
    ("Rilievi, non sentenze", "Findings, not verdicts"),
    (
        "Ogni rilievo si conferma, si respinge o si accetta come rischio con una scadenza. Sempre con una persona.",
        "Every finding is confirmed, rejected, or accepted as a risk with an expiry date. Always by a person.",
    ),
    ("Un riepilogo quotidiano", "A daily digest"),
    (
        "In italiano e in inglese, anche via email. Più i report da consegnare a chi non usa "
        "lo strumento, anche in PDF.",
        "In English and in Italian, by e-mail too. Plus reports to hand to people who do not "
        "use the tool, as PDF too.",
    ),
    ("Anche da altri gateway", "From other gateways too"),
    (
        "I registri di un altro sistema si importano senza il loro contenuto.",
        "The records of another system are imported without their content.",
    ),
    ("Strumenti e agenti</div>", "Tools and agents</div>"),
    ("L'IA che usa strumenti e parla con altre IA", "AI that uses tools and talks to other AI"),
    (
        "I sistemi di oggi non si limitano a rispondere: leggono file, interrogano archivi, chiedono aiuto ad altri agenti. Arbiter si mette in mezzo anche lì.",
        "Today's systems do more than answer: they read files, query archives, ask other agents for help. Arbiter stands in between there too.",
    ),
    ("Strumenti (protocollo MCP)", "Tools (the MCP protocol)"),
    (
        "Un catalogo dei server di strumenti conosciuti. Nessuno può usarne uno finché un permesso non lo dice, anche strumento per strumento. Ogni chiamata è registrata: chi, quale strumento, come è finita. Mai cosa è stato chiesto o risposto.",
        "A catalogue of the tool servers that are known. Nobody may use one until a grant says so, tool by tool if needed. Every call is recorded: who, which tool, how it ended. Never what was asked or answered.",
    ),
    ("Agenti (protocollo A2A)", "Agents (the A2A protocol)"),
    (
        'Un registro degli agenti esterni e del loro "biglietto da visita". La firma del biglietto vale solo se fatta con una chiave di cui l\'organizzazione si fida già: un biglietto che porta con sé la propria chiave garantisce solo per se stesso.',
        'A registry of external agents and of their "business card". The signature on the card counts only if made with a key the organisation already trusts: a card that brings its own key vouches only for itself.',
    ),
    (
        "<strong>Stessa regola per tutto:</strong> prima si decide, poi si scrive la decisione nel registro, e solo dopo la richiesta parte. Se il registro non si può scrivere, la richiesta non parte.",
        "<strong>One rule for everything:</strong> first decide, then write the decision in the log, and only then let the request go. If the log cannot be written, the request does not go.",
    ),
    ("Di cosa ci si può fidare", "What you can rely on"),
    ("Come è costruito", "How it is built"),
    ("Un registro a catena", "A chained log"),
    (
        "Ogni voce contiene l'impronta della precedente. Cambiarne una rompe la catena, e si vede.",
        "Each entry holds the fingerprint of the one before. Changing one breaks the chain, and it shows.",
    ),
    ("Niente contenuti salvati", "No content is kept"),
    (
        "Domande e risposte non vengono conservate. Un test cerca in tutto il database per dimostrarlo.",
        "Questions and answers are not stored. A test searches the whole database to prove it.",
    ),
    ("Regole come dati", "Rules as data"),
    (
        "Le regole sono file leggibili, con versione. Si possono leggere, confrontare e sostituire senza toccare il programma.",
        "The rules are readable files, with a version. They can be read, compared and replaced without touching the program.",
    ),
    ("Decide una persona", "A person decides"),
    (
        "Classificazioni e rilievi sono proposte. La macchina non chiude mai una questione da sola.",
        "Classifications and findings are proposals. The machine never settles a matter on its own.",
    ),
    ("Decisioni scritte", "Decisions on record"),
    (
        "Ogni scelta di progetto è registrata con le alternative scartate e il perché.",
        "Every design choice is recorded with the alternatives set aside and the reason.",
    ),
    ("Funziona anche offline", "It works offline too"),
    (
        "Si prova su un portatile, senza cloud e senza un modello vero. Una dimostrazione guidata segue una società di consulenza inventata, con il suo regolamento interno.",
        "You can try it on a laptop, with no cloud and no real model. A guided "
        "demonstration follows an invented consulting firm, with its internal regulation.",
    ),
    ('data-prefix="oltre ">oltre 1.100</div>', 'data-prefix="over ">over 1,100</div>'),
    ("test automatici", "automated tests"),
    ("del codice coperto dai test", "of the code covered by tests"),
    ("decisioni di progetto registrate", "design decisions on record"),
    ("controlli sul traffico", "checks on the traffic"),
    ("Con onestà</div>", "In all honesty</div>"),
    ("Cosa Arbiter non fa", "What Arbiter does not do"),
    ("Non è consulenza legale", "It is not legal advice"),
    (
        'È uno strumento di supporto. Non dice mai che un sistema "è conforme": dice "indicativo" e "nessun rilievo".',
        'It is a support tool. It never says a system "is compliant": it says "indicative" and "no findings".',
    ),
    (
        "Non verifica che le dichiarazioni siano vere",
        "It does not check that declarations are true",
    ),
    (
        "Una classificazione vale quanto le risposte date. Il traffico ne smentisce alcune, non tutte.",
        "A classification is as good as the answers given. The traffic contradicts some of them, not all.",
    ),
    ('<span class="pill warn">Limite</span>', '<span class="pill warn">Limit</span>'),
    ('<span class="pill info">Stato</span>', '<span class="pill info">Status</span>'),
    ("Dati personali: formati, nomi e luoghi", "Personal data: formats, names and places"),
    (
        "Di base trova email, telefoni, IBAN, codici fiscali. Un componente opzionale, che lavora in locale, aggiunge nomi e luoghi scritti a parole: su un centinaio di frasi inventate ne ha trovati tra l'81 e il 93 per cento. I dati sanitari non li riconosce nessuno dei due.",
        "By default it finds e-mail addresses, phone numbers, IBANs, tax codes. An optional component, which works locally, adds names and places written in words: on about a hundred invented sentences it found between 81% and 93% of them. Neither recognises health data.",
    ),
    ("Solo chi usa l'IA, non chi la produce", "Only those who use AI, not those who make it"),
    (
        "Oggi valuta gli obblighi di chi impiega un sistema. Quelli di chi lo sviluppa arriveranno dopo.",
        "Today it evaluates the obligations of those who deploy a system. Those of whoever develops it will come later.",
    ),
    ("Registro che rivela, non che impedisce", "A log that reveals, not one that prevents"),
    (
        "Una manomissione parziale si vede. Chi può riscrivere tutto il database può riscrivere tutta la catena: serve una copia esterna dell'ultima impronta.",
        "A partial tampering shows. Whoever can rewrite the whole database can rewrite the whole chain: a copy of the last fingerprint has to be kept elsewhere.",
    ),
    ("Versione di prova</h3>", "A pre-release</h3>"),
    (
        "Su PyPI c'è una prima versione alpha. Nessuno la usa in produzione, e diverse parti "
        "sono state provate solo con controparti simulate.",
        "A first alpha is on PyPI. Nobody runs it in production, and several parts were "
        "tested only against simulated counterparts.",
    ),
    ("A che punto siamo</div>", "Where we are</div>"),
    ("Il percorso, fase per fase", "The road, phase by phase"),
    (
        "Stima al 5 ottobre 2026. Le percentuali misurano il lavoro di costruzione, non il valore legale delle regole.",
        "An estimate on 5 October 2026. The percentages measure the work of building, not the legal value of the rules.",
    ),
    ("del percorso complessivo", "of the whole road"),
    ("Prima della versione 0.1.0", "Before version 0.1.0"),
    (
        "Una revisione delle regole da parte di una persona con formazione giuridica, e un confronto degli articoli citati con la fonte ufficiale.",
        "A review of the rules by a person with legal training, and a comparison of the quoted articles with the official source.",
    ),
    ("<h3>Dopo</h3>", "<h3>After that</h3>"),
    (
        "L'installazione su cloud (Azure) e la documentazione per chi lo adotta. Tra i desiderata: leggere anche i log della rete aziendale, per vedere l'IA usata fuori da Arbiter.",
        "The installation on a cloud (Azure) and the documentation for those who adopt "
        "it. On the wish list: reading the logs of the company network too, to see the AI "
        "used outside Arbiter.",
    ),
    ("In sintesi</div>", "In short</div>"),
    ("Cosa ottieni", "What you get"),
    ("Un inventario che resta vero", "An inventory that stays true"),
    (
        "Perché viene confrontato ogni giorno con ciò che accade, e non solo con ciò che si ricorda.",
        "Because it is compared every day with what happens, and not only with what is remembered.",
    ),
    (
        'Una risposta a "da dove viene questo risultato?"',
        'An answer to "where does this result come from?"',
    ),
    (
        "Ogni esito porta con sé la regola, l'articolo, la data e chi lo ha confermato.",
        "Every outcome carries the rule, the article, the date and who confirmed it.",
    ),
    ("Meno sorprese", "Fewer surprises"),
    (
        "L'uso non dichiarato emerge da solo, come proposta da valutare, prima che lo trovi qualcun altro.",
        "Undeclared use surfaces by itself, as a proposal to assess, before someone else finds it.",
    ),
    ("Prove che reggono", "Evidence that holds"),
    (
        "Un registro verificabile di cosa è stato deciso e quando, senza conservare il contenuto delle conversazioni.",
        "A verifiable log of what was decided and when, without keeping the content of conversations.",
    ),
    (
        "Arbiter è uno strumento di supporto. Non fornisce consulenza legale.",
        "Arbiter is a support tool. It does not provide legal advice.",
    ),
    # The journey of a request.
    ('t: "Chi chiede"', 't: "Who is asking"'),
    (
        "Ogni applicazione ha una chiave. Arbiter la riconosce e sa a quale gruppo, progetto e sistema di IA appartiene. Una chiave revocata smette di funzionare alla richiesta successiva.",
        "Every application has a key. Arbiter recognises it and knows which team, project and AI system it belongs to. A revoked key stops working at the next request.",
    ),
    (
        "chiave  →  progetto “Risorse umane”, sistema “Selezione CV”",
        "key  →  project “Human resources”, system “CV screening”",
    ),
    ('t: "Le regole"', 't: "The rules"'),
    (
        "Regole scritte come dati decidono se la richiesta può proseguire: modello ammesso, limiti di spesa, sistema non classificato come pratica vietata. Un rifiuto spiega sempre quale regola l'ha causato.",
        "Rules written as data decide whether the request may go on: an allowed model, spending limits, a system not classified as a prohibited practice. A refusal always says which rule caused it.",
    ),
    (
        "sistema classificato “pratica vietata”  →  richiesta negata, art. 5",
        "system classified “prohibited practice”  →  request denied, Art. 5",
    ),
    ('t: "Dati personali"', 't: "Personal data"'),
    (
        "Prima che il messaggio lasci l'organizzazione, email, telefoni, IBAN e codici fiscali vengono sostituiti da segnaposto.",
        "Before the message leaves the organisation, e-mail addresses, phone numbers, IBANs and tax codes are replaced by placeholders.",
    ),
    (
        "“Scrivi a mario.rossi@example.com”  →  “Scrivi a [EMAIL]”",
        "“Write to mario.rossi@example.com”  →  “Write to [EMAIL]”",
    ),
    ('t: "Dove va"', 't: "Where it goes"'),
    (
        "La richiesta è inviata al fornitore giusto, per priorità o per costo, e solo dove la classe di rischio del sistema lo consente. Se un fornitore non risponde, si prova il successivo.",
        "The request is sent to the right provider, by priority or by cost, and only where the risk class of the system allows. If a provider does not answer, the next one is tried.",
    ),
    ("alto rischio  →  solo regioni europee", "high risk  →  European regions only"),
    ('t: "Quanto costa"', 't: "What it costs"'),
    (
        "Si contano le unità consumate e si stima il costo, attribuito a gruppo, progetto e sistema. Un limite di spesa può avvisare oppure bloccare.",
        "The units consumed are counted and the cost is estimated, attributed to team, project and system. A spending limit can warn or block.",
    ),
    (
        "progetto “Risorse umane”: 12,40 su 50,00 questo mese",
        "project “Human resources”: 12.40 of 50.00 this month",
    ),
    ('t: "Cosa resta scritto"', 't: "What stays on record"'),
    (
        "La decisione entra in un registro a catena. Resta chi ha chiesto, cosa è stato deciso e perché. Non resta il testo della conversazione.",
        "The decision goes into a chained log. What stays is who asked, what was decided and why. The text of the conversation does not.",
    ),
    (
        "voce 1.284  →  impronta legata alla voce 1.283",
        "entry 1,284  →  fingerprint tied to entry 1,283",
    ),
    ('n.textContent = "PASSO " + (i + 1);', 'n.textContent = "STEP " + (i + 1);'),
    # Risk tiers.
    ('n: "Fuori ambito"', 'n: "Out of scope"'),
    (
        "La legge non si applica: per esempio un sistema ancora in sviluppo e mai messo in servizio, o usato solo per ricerca scientifica.",
        "The law does not apply: for example a system still in development and never put into service, or used only for scientific research.",
    ),
    (
        "Un prototipo del gruppo dati, mai usato in produzione.",
        "A prototype of the data team, never used in production.",
    ),
    ('n: "Pratica vietata"', 'n: "Prohibited practice"'),
    (
        "Usi che la legge proibisce. Arbiter li segnala con la massima gravità e il gateway non concede loro alcun modello.",
        "Uses the law forbids. Arbiter reports them with the highest severity and the gateway gives them no model.",
    ),
    (
        "Dedurre le emozioni dei dipendenti dalla voce durante le chiamate.",
        "Inferring the emotions of employees from their voice during calls.",
    ),
    ('n: "Alto rischio"', 'n: "High risk"'),
    (
        "Sistemi che incidono su persone in ambiti delicati: lavoro, credito, istruzione, servizi essenziali. Comportano obblighi precisi per chi li usa.",
        "Systems that affect people in sensitive areas: work, credit, education, essential services. They bring precise obligations for those who use them.",
    ),
    (
        "Un modulo che ordina le candidature per i selezionatori.",
        "A module that ranks job applications for recruiters.",
    ),
    ('n: "Trasparenza"', 'n: "Transparency"'),
    (
        "Sistemi che parlano con le persone o producono contenuti: chi li incontra deve sapere che ha a che fare con un'IA.",
        "Systems that talk to people or produce content: whoever meets them must know they are dealing with an AI.",
    ),
    (
        "L'assistente che risponde ai clienti sul sito.",
        "The assistant that answers customers on the website.",
    ),
    ('n: "Rischio minimo"', 'n: "Minimal risk"'),
    (
        "Tutto il resto. Nessun obbligo specifico oltre a quelli generali.",
        "Everything else. No specific obligation beyond the general ones.",
    ),
    (
        "Un sistema che legge fatture e precompila la contabilità.",
        "A system that reads invoices and pre-fills the accounts.",
    ),
    ('n: "Indeterminato"', 'n: "Undetermined"'),
    (
        "Mancano risposte che potrebbero portare a una classe più severa. Arbiter elenca le domande ancora aperte invece di tirare a indovinare.",
        "Answers are missing that could lead to a more severe class. Arbiter lists the questions still open instead of guessing.",
    ),
    (
        "Un generatore di testi di cui si conosce solo l'ambito d'uso.",
        "A text generator of which only the scope is known.",
    ),
    (
        'e.textContent = "Esempio inventato: " + t.e;',
        'e.textContent = "An invented example: " + t.e;',
    ),
    # Phases.
    ('["Analisi e architettura", 100]', '["Analysis and architecture", 100]'),
    ('["Fondamenta del progetto", 100]', '["Foundations of the project", 100]'),
    ('["Toolkit di conformità", 100]', '["Compliance toolkit", 100]'),
    ('["Importazione, report, scoperta", 100]', '["Import, reports, discovery", 100]'),
    ('["Strumenti e agenti (MCP, A2A)", 100]', '["Tools and agents (MCP, A2A)", 100]'),
    ('["Installazione su cloud", 0]', '["Installation on a cloud", 0]'),
    ('["Documentazione e rilascio", 0]', '["Documentation and release", 0]'),
    ('toLocaleString("it-IT")', 'toLocaleString("en-GB")'),
]


def say(line: str) -> None:
    sys.stdout.write(line + "\n")


def main() -> int:
    page = SOURCE.read_text(encoding="utf-8")
    missing = [italian for italian, _ in TEXTS if italian not in page]
    if missing:
        for italian in missing:
            say(f"not in the Italian page: {italian[:70]}")
        return 1
    for italian, english in TEXTS:
        page = page.replace(italian, english)
    visible = re.sub(r"<style>.*?</style>", "", page, flags=re.DOTALL)
    left = sorted(set(re.findall(ITALIAN, visible)))
    if left:
        say(f"Italian words left in the English page: {', '.join(left)}")
        return 1
    TARGET.write_text(page, encoding="utf-8", newline="\n")
    say(f"Wrote {TARGET.relative_to(DIRECTORY.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
