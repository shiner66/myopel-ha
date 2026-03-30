# MyOpel – Home Assistant Integration

Integrazione per Home Assistant che legge i file esportati dall'app **MyOpel** e crea sensori + una Lovelace card per monitorare il tuo veicolo Opel/Vauxhall.

## Funzionalità

- **30+ sensori**: chilometraggio, carburante, consumo, velocità media, costi stimati
- Statistiche per **ultimo viaggio**, **mese corrente**, **totali** e **dall'ultimo rifornimento**
- **Alert attivi** (binary sensor) dell'ultimo viaggio
- **Download automatico** del file di dati via IMAP (opzionale)
- **Lovelace card** con mappa GPS, immagine 3D interattiva e rotazione 360° con inerzia
- **Supporto multi-veicolo** tramite VIN
- **Aggiornamento in tempo reale** via watchdog (inotify) non appena il file viene scritto
- **Compatibile con iOS Shortcuts**: accetta file `trips`, `trips.json` e `.myop`

---

## Installazione via HACS

1. In HACS → Integrazioni → ⋮ → **Repository personalizzati**
2. Aggiungi l'URL del repository con categoria **Integration**
3. Cerca **MyOpel** e installa
4. Riavvia Home Assistant

### Installazione manuale

Copia la cartella `custom_components/myopel/` in `/config/custom_components/myopel/` e riavvia.

---

## Configurazione

### 1. Carica il file dei dati

Esporta il file dall'app MyOpel (**Guida → ⋮ → Esporta**) e mettilo in una cartella, es. `/config/myopel/`.

Formati accettati (viene sempre letto il più recente per data di modifica):

| File | Descrizione |
|---|---|
| `trips.json` | Formato nativo app MyOpel |
| `trips` | Senza estensione — per iOS Shortcuts |
| `*.myop` | Formato legacy |

In alternativa configura il **download automatico via email** (vedi sotto).

### 2. Aggiungi l'integrazione

**Impostazioni → Dispositivi e servizi → Aggiungi integrazione → MyOpel**

- **Cartella**: percorso assoluto, es. `/config/myopel/` (default, viene creata se non esiste)
- Viene letto automaticamente il file più recente nella cartella

### 3. Opzioni (facoltative)

Da **Configura** nell'integrazione puoi modificare:

| Opzione | Descrizione |
|---|---|
| Cartella file | Percorso della cartella dati (modificabile a caldo) |
| Intervallo lettura file | Polling di backup in secondi (default 300) |
| Ignora viaggi corti | Esclude dai calcoli i viaggi sotto la soglia |
| Distanza minima | Soglia km per ignorare un viaggio |
| Server IMAP | Per scaricare automaticamente il file da email |
| Disabilita IMAP | Disattiva il download via email senza rimuovere le credenziali |

### 4. Download automatico via email

Se esporti il file e te lo invii per email, l'integrazione può scaricarlo automaticamente:

- **Server IMAP**: es. `imap.gmail.com`
- **Porta**: 993
- **Email + Password** (per Gmail usa una *App Password*)
- **Filtro mittente**: opzionale, filtra da quale indirizzo accettare il file
- **Intervallo**: ogni quanti secondi controllare la casella

---

## Lovelace Card

La card si registra automaticamente all'avvio. Aggiungila alla dashboard:

```yaml
type: custom:myopel-card
name: Opel Corsa
vin: "VXKUBYHTKM4329850"   # VIN completo (17 caratteri)
car_make: opel
car_model: corsa
car_year: 2021
car_color: grey             # colore per immagine imagin.studio (opzionale)
tank_capacity: 37.7         # capacità UTILE del gauge in litri
plate: "AB123CD"            # targa per integrazione UnipolSai (opzionale)
```

### Immagine 3D

La card mostra automaticamente l'immagine del tuo veicolo dal CDN Opel Visual3D usando il VIN completo.

Per la **vista 360° interattiva**, clicca il badge `360°` in alto a destra nella card. Trascina l'immagine per ruotare il veicolo con inerzia fluida.

> **Nota `tank_capacity`**: inserire la capacità **utile** del gauge, non la capacità fisica del serbatoio.

### Integrazione con UnipolSai

Se hai anche l'integrazione UnipolSai, aggiungi il campo `plate` con la targa del veicolo. La card mostrerà automaticamente:
- Mini mappa GPS con posizione attuale
- Indirizzo geocodificato
- Data/ora ultimo aggiornamento GPS

---

## Sensori creati

| Gruppo | Sensori |
|---|---|
| Veicolo | Chilometraggio, Livello carburante, Autonomia |
| Ultimo viaggio | Distanza, Durata, Velocità media, Consumo, Carburante, Costo, Alert |
| Mese corrente | Viaggi, Distanza, Carburante, Consumo, Costo, Alert |
| Totali | Viaggi, Distanza, Ore, Velocità media, Carburante, Costo, Alert |
| Dall'ultimo rifornimento | Viaggi, Distanza, Ore, Carburante, Consumo, Costo |
| Manutenzione | Giorni al tagliando, Km al tagliando |
| Binary sensor | Alert attivi nell'ultimo viaggio |

---

## Aggiornamento dati

Il file viene monitorato via **watchdog (inotify)**: non appena viene scritto/sostituito, i sensori si aggiornano istantaneamente senza attendere il polling. Il polling rimane attivo come fallback.
