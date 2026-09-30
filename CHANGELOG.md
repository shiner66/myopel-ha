# Changelog

Tutte le modifiche rilevanti a questa integrazione sono documentate qui.

---

## [1.4.5] – 2026-09-30

### Correzioni
- Sostituito il server pubblico `tile.openstreetmap.org`, che può rifiutare le
  richieste del frontend Home Assistant con `403` per la propria tile usage
  policy, con la mappa vettoriale OpenFreeMap in stile Liberty: nessuna API key,
  nomi delle strade visibili e attribuzione corretta. MapLibre GL JS `5.24.0`
  e il relativo adapter Leaflet sono inclusi nell'integrazione; se WebGL o
  OpenFreeMap non sono disponibili, la card usa OpenTopoMap come servizio di
  riserva e mostra un errore leggibile se anche questo non risponde.
- Ripubblicata la correzione della mappa con una nuova versione per risolvere
  la collisione della `1.4.4`: alcuni pacchetti o installazioni da `main`
  esponevano già lo stesso numero di versione pur contenendo ancora le tile
  CARTO, impedendo a HACS e al browser di rilevare l'aggiornamento.
- La card ricava ora la propria versione dall'URL statico versionato e la mostra
  nella console del browser. Se trova già registrata una card legacy o di una
  versione diversa, avvisa che occorre un hard refresh o l'arresto forzato
  della Companion App e segnala di controllare eventuali risorse duplicate.

---

## [1.4.4] – 2026-09-30

### Correzioni
- Sostituito l'endpoint CARTO che mostrava `API KEY REQUIRED` con le tile
  standard OpenStreetMap: nessuna chiave richiesta, nomi di strade e località
  visibili e attribuzione corretta.
- La mini mappa valida anche coordinate pari a zero, isola Leaflet in un iframe
  sandboxed, convalida i messaggi di aggiornamento e recupera gli update GPS
  arrivati durante il caricamento; corretti inoltre timestamp non validi e
  fuso orario del frontend.
- Il binary sensor *"Ultimo viaggio – Alert presenti"* viene ora pubblicato
  correttamente come `binary_sensor` e l'eventuale entità legacy nel dominio
  `sensor` viene rimossa durante la migrazione.
  Le automazioni che usavano il precedente entity ID `sensor.*` devono essere
  aggiornate al nuovo entity ID nel dominio `binary_sensor`.
- Il download IMAP non marca più come lette le email estranee: unisce le
  ricerche recenti/non lette, usa `BODY.PEEK`, valida dimensione, JSON e VIN e
  sostituisce lo snapshot in modo atomico prima di eliminare i file obsoleti.
- Serializzati i fetch IMAP concorrenti; IDLE reagisce subito alle nuove email
  e si arresta senza bloccare il loop di Home Assistant o lasciare thread attivi.
- Gli snapshot malformati o appartenenti a un altro VIN non contaminano più le
  statistiche; aggiunto il supporto effettivo al file `trips` senza estensione
  e ai suffissi `.MYOP` maiuscoli.
- Normalizzati percorso e campi IMAP salvati dalle Opzioni; gli aggregati Oggi
  e Mese rispettano l'offset orario configurato.
- Pulizia completa di watchdog, IMAP e listener se setup/unload falliscono;
  quando una cartella inizialmente vuota rivela il VIN, l'entry viene ricaricata
  per ricreare entità e device con gli identificativi corretti.
- Registrazione della card compatibile con la vecchia API static path di Home
  Assistant e con `StaticPathConfig` nelle versioni recenti; la registrazione
  frontend viene rinviata finché il frontend è disponibile, preservando le
  installazioni headless.

### Modifiche
- Fissata la dipendenza frontend Lit alla versione `3.2.1`; protetta la
  registrazione della custom card da caricamenti duplicati.

---

## [1.4.1] – 2026-04-17

### Aggiunte
- **Acknowledgment degli alert**: ora è possibile "confermare" gli alert
  segnalati. Un alert confermato non fa più scattare il binary sensor
  *"Alert presenti"* ma resta visibile nella card (sezione comprimibile
  *"Mostra N alert confermati"*).
  - Nuovi servizi: `myopel.acknowledge_alert`, `myopel.acknowledge_all_alerts`,
    `myopel.unacknowledge_alert`, `myopel.reset_alert_acknowledgments`.
  - I servizi accettano il parametro `scope` (`last_trip`, `today`, `month`,
    `total`) per applicare l'ack a tutti i viaggi di quell'ambito in un colpo
    solo; default `last_trip` per retro-compatibilità.
  - Ack disponibile su **tutte le tab** della card (Viaggio, Mese/Oggi,
    Totali), non solo sull'ultimo viaggio.
  - Nuovi sensori: *"Ultimo viaggio – Alert non letti"* (numero) ed etichette,
    più versioni equivalenti per mese/oggi
    (`mese_corrente_alert_non_letti`, `oggi_alert_non_letti`).
  - Nuovi attributi sugli entity relativi agli alert: `all_codes`,
    `acknowledged_codes`, `unacknowledged_codes`, `code_labels`, `trip_id`,
    `entry_id`, `scope`, `code_to_trips`.
  - Persistenza tramite `homeassistant.helpers.storage.Store` (sopravvive ai
    riavvii). L'acknowledgment è legato alla coppia `(trip_id, code)`:
    se lo stesso codice ricompare in un nuovo viaggio torna a essere segnalato.
- **Card Lovelace**: ogni alert attivo ha ora un pulsante "✓ Conferma";
  se più alert sono attivi compare "✓✓ Conferma tutti". Gli alert confermati
  si possono ri-espandere e ripristinare con "↺ Ripristina".
- **Sezione "Oggi"**: aggregazione dei viaggi della giornata corrente
  (distanza, durata, consumo, costo, alert). Accessibile tramite uno switch
  nella tab *Mese* che permette di passare tra vista *Oggi* e *Mese corrente*
  senza aggiungere una nuova tab. Nuovi sensori `oggi_*` analoghi a quelli
  del mese.

### Modifiche
- Il binary sensor *"Ultimo viaggio – Alert presenti"* ora riflette gli alert
  **non confermati** (prima rifletteva tutti). L'attributo `has_any_alerts`
  resta `True` finché esistono alert (anche confermati) così da poter
  ricostruire il comportamento precedente nelle automazioni.
- `INTEGRATION_VERSION` ora viene letto da `manifest.json` invece di essere
  hard-coded: l'URL della card Lovelace resta sempre allineato alla versione
  effettiva dell'integrazione.

---

## [1.3.0] – 2026-03-25

### Aggiunte
- **Supporto `trips.json`**: accettato come sorgente dati accanto ai file `.myop` legacy.
  Stesso parser JSON — viene usato il file più recente tra quelli presenti nella cartella.
  `trips.json` è il formato nativo dell'app e contiene dati più aggiornati e numeri più precisi.
- **File watching con watchdog (inotify)**: i dati vengono aggiornati istantaneamente quando
  il file viene sovrascritto, senza attendere il ciclo di polling.
  Gestisce sia `on_modified` (sovrascrittura) che `on_created` (ricreazione del file).
  Il polling rimane attivo come rete di sicurezza. `iot_class` aggiornata a `local_push`.
- **Percorso cartella modificabile dalle opzioni**: il percorso della cartella monitorata
  può ora essere cambiato da "Configura" senza reinstallare — il vecchio observer viene
  fermato e uno nuovo avviato sul nuovo percorso senza riavvio di HA.
- **Disabilitazione IMAP dalle opzioni**: nuovo toggle "Disabilita download automatico via email"
  per disattivare IMAP senza perdere le credenziali configurate.
- **Immagine auto 3D dal VIN** (card Lovelace): la card usa ora il CDN Opel visual3D
  (`visual3d-secure.opel-vauxhall.com`) con il VIN per ottenere un'immagine 3D reale del veicolo.
  Supporta il parametro `car_view` (default `001`; valori validi: `001`–`004`, `010`–`012`,
  `020`–`025`, `030`–`053`). Fallback a imagin.studio se il VIN non è configurato.

### Modifiche
- **Config flow**: percorso cartella pre-compilato con `/config/myopel/` come default.
- **Opzioni IMAP prendono precedenza sui dati originali**: le credenziali IMAP aggiornate
  nelle opzioni sono ora applicate al riavvio senza dover reinstallare l'integrazione.

---

## [1.2.0] – 2026-03-25

### Aggiunte
- **Traduzione codici alert**: i sensori "Alert attivi", "Riepilogo codici alert" (totale e mensile)
  mostrano ora il nome leggibile dell'anomalia (es. `Anomalia impianto frenante×2`) invece del
  codice numerico grezzo. Mappatura completa di 124 codici alert estratti dall'app MyOpel.
- **GitHub Actions – Pre-release automatica**: ad ogni push su branch non-main viene creata
  automaticamente una pre-release GitHub con il file `myopel-ha.zip` pronto all'installazione.
- **GitHub Actions – Release automatica**: ad ogni merge su `main` viene creata una release
  GitHub con tag versionato e note di rilascio estratte dal CHANGELOG.

---

## [1.1.0] – 2026-03-21

### Aggiunte
- **IMAP IDLE (RFC 2177)**: il download del file `.myop` avviene ora in tempo reale non appena la mail arriva in casella, senza attendere il ciclo di polling. Il polling rimane attivo come rete di sicurezza.
- **Notifica IDLE non supportato**: se il server IMAP non supporta IDLE, viene mostrata una notifica persistente in Home Assistant con suggerimenti su come risolvere.
- **Sensori "Dall'ultimo rifornimento"**: 8 nuovi sensori (distanza, ore, carburante, consumo, costo, velocità media, data rifornimento) calcolati automaticamente a partire dall'ultimo aumento del livello carburante ≥5%.
- **Mappa Leaflet via iframe**: la mini mappa GPS (con integrazione UnipolSai) usa ora Leaflet.js con tile CartoDB Dark Matter in un `<iframe srcdoc>` autocontenuto, evitando i problemi di rendering nel shadow DOM.
- **Stima litri rimanenti**: configurando `tank_capacity` nella card, il footer della barra carburante mostra i litri stimati rimanenti.
- **Supporto colore auto**: parametro `car_color` per la card (es. `grey`) passa il paintId a imagin.studio CDN.
- **Integrazione multi-veicolo**: gli entity ID includono ora gli ultimi 6 caratteri del VIN; la card accetta il parametro `vin` per collegarsi ai sensori corretti.
- **Collegamento UnipolSai**: parametro `plate` nella card per collegare la mappa GPS dell'integrazione UnipolSai.

### Modifiche
- **Timestamp corretti**: i timestamp del file `.myop` erano marcati come UTC ma contengono ora locale italiana. Ora vengono interpretati correttamente, eliminando lo sfasamento di +1 ora.
- **Filtro distanza minima applicato globalmente**: i viaggi sotto soglia vengono esclusi da tutti i calcoli (totali, mensili, alert, costi) e non solo dalla selezione dell'ultimo viaggio.
- **File IMAP sempre sovrascritto**: il file `.myop` viene ora sovrascritto anche se ha lo stesso nome del precedente, permettendo aggiornamenti con file dallo stesso nome.
- **Cartella IMAP creata automaticamente**: la cartella di destinazione viene creata se non esiste.

### Correzioni
- Fix **500 Internal Server Error** nel flusso opzioni: rimosso `__init__` ridondante da `OptionsFlow`.
- Fix **entry "unknown"**: l'entry di configurazione aggiorna automaticamente title e unique_id non appena il primo file `.myop` viene letto e il VIN è disponibile.
- Fix **`DEFAULT_TIME_ZONE` deprecata**: sostituita con `dt_util.get_default_time_zone()`.

---

## [1.0.0] – 2026-03-20

### Prima release

- Lettura file `.myop` da cartella locale con rilevamento automatico del file più recente.
- 42 sensori: chilometraggio, carburante, autonomia, ultimo viaggio, statistiche mensili, totali, manutenzione (tagliando).
- Binary sensor alert attivi nell'ultimo viaggio.
- Download automatico via IMAP con supporto filtro mittente.
- Config flow a due step (cartella + IMAP opzionale) con validazione credenziali in tempo reale.
- Filtro distanza minima per escludere i viaggi corti.
- Lovelace card `custom:myopel-card` registrata automaticamente — nessuna configurazione manuale richiesta.
- Card con 4 tab: Viaggio, Mese, Totali, Manutenzione.
- Immagine auto da imagin.studio CDN.
- Barra carburante a segmenti con glow colorato.
- Compatibile con HACS (repository personalizzato).
