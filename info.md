## MyOpel – Home Assistant Integration

Integrazione per monitorare il tuo veicolo **Opel / Vauxhall** tramite i dati esportati dall'app MyOpel.

### Funzionalità principali

- **30+ sensori**: chilometraggio, carburante, consumo, velocità media, costi
- Statistiche per **ultimo viaggio**, **mese corrente**, **totali** e **dall'ultimo rifornimento**
- **Lovelace card** con immagine 3D interattiva, rotazione 360° con inerzia e mappa GPS
- **Aggiornamento in tempo reale** via watchdog — nessun polling necessario
- **Download automatico** tramite IMAP (opzionale)
- Formati accettati: `trips.json`, `trips` (senza estensione — iOS Shortcuts), `.myop` (legacy)

### Installazione

1. **HACS** → Integrazioni → ⋮ → Repository personalizzati → aggiungi questo URL
2. Cerca **MyOpel** e installa
3. Riavvia Home Assistant
4. **Impostazioni → Dispositivi → Aggiungi integrazione → MyOpel**

### Lovelace Card

```yaml
type: custom:myopel-card
name: Opel Corsa
vin: "VXKUBYHTKM4329850"
tank_capacity: 37.7
plate: "AB123CD"   # opzionale — integrazione UnipolSai
```

Clicca il badge **360°** nella card per attivare la vista 3D interattiva.
