# Changelog

Tutte le modifiche rilevanti a questa integrazione sono documentate qui.

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
