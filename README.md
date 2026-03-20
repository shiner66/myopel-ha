# MyOpel – Home Assistant Integration

Integrazione per Home Assistant che legge i file `.myop` esportati dall'app **MyOpel** e crea sensori + una Lovelace card per monitorare il tuo veicolo.

## Funzionalità

- 📊 **30+ sensori**: chilometraggio, carburante, consumo, velocità media, costi stimati
- 📅 Statistiche per **ultimo viaggio**, **mese corrente**, **totali** e **dall'ultimo rifornimento**
- 🔔 **Alert attivi** (binary sensor) dell'ultimo viaggio
- 📧 **Download automatico** del file `.myop` via IMAP (opzionale)
- 🗺 **Lovelace card** integrata con mappa GPS (compatibile con UnipolSai)
- 🚗 **Supporto multi-veicolo** tramite VIN

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

### 1. Carica il file .myop

Esporta il file dall'app MyOpel (**Guida → ⋮ → Esporta**) e mettilo in una cartella a tua scelta, es. `/config/myopel/`.

In alternativa configura il **download automatico via email** (vedi sotto).

### 2. Aggiungi l'integrazione

**Impostazioni → Dispositivi e servizi → Aggiungi integrazione → MyOpel**

- **Cartella**: percorso assoluto, es. `/config/myopel/` (viene creata se non esiste)
- Viene letto automaticamente il file `.myop` più recente nella cartella

### 3. Opzioni (facoltative)

Da **Configura** nell'integrazione puoi impostare:

| Opzione | Descrizione |
|---|---|
| Intervallo lettura file | Polling in secondi (default 300) |
| Ignora viaggi corti | Esclude dai calcoli i viaggi sotto la soglia |
| Distanza minima | Soglia km per ignorare un viaggio |
| Server IMAP | Per scaricare automaticamente il file da email |

### 4. Download automatico via email

Se esporti il `.myop` e te lo invii per email, l'integrazione può scaricarlo automaticamente:

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
vin: "VXKUBYHTKM4329850"   # VIN completo o ultimi 6 caratteri
car_make: opel
car_model: corsa
car_year: 2021
car_color: grey             # colore per immagine imagin.studio (opzionale)
tank_capacity: 37.7         # capacità UTILE del gauge in litri (vedi nota)
plate: "AB123CD"            # targa per integrazione UnipolSai (opzionale)
```

> **Nota `tank_capacity`**: inserire la capacità **utile** del gauge, non la capacità fisica del serbatoio.
> Il gauge dell'auto mostra 0% prima che il serbatoio sia fisicamente vuoto, e 100% prima che sia fisicamente pieno.
> Per calibrarlo: fai il pieno fino a che il gauge mostra 100%, poi guida fino a che mostra ~5-10% e controlla quanti litri hai consumato.
> In alternativa: somma litri consumati dall'ultimo pieno + litri rimanenti stimati = capacità utile.

### Integrazione con UnipolSai

Se hai anche l'integrazione [UnipolSai](https://github.com/yourusername/unipolsai-ha), aggiungi il campo `plate` con la targa del veicolo. La card mostrerà automaticamente:
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

Sovrascrivere il file `.myop` con un export più recente aggiorna automaticamente tutti i sensori al prossimo ciclo di polling (default 5 minuti). Con IMAP configurato, il download e l'aggiornamento avvengono in automatico.

