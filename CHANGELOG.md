# Changelog

Tutte le modifiche rilevanti a questa integrazione sono documentate qui.

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
