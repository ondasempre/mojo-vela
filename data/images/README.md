# Photographs

Barche in navigazione: la banda in cima alla pagina e la galleria dello spot.

## Aggiungere le tue foto — due passi

**1. Copia i file** in `data/images/photos/` (crea la cartella se non c'è):

```
data/images/photos/dervio-breva.jpg
data/images/photos/colico-regata.jpg
```

**2. Elencali** in `images.json`:

```json
{
  "photos": [
    {
      "id": "dervio-breva",
      "file": "dervio-breva.jpg",
      "caption": "Breva al pomeriggio, vista da Dervio",
      "credit": "Flavio Macciocchi",
      "licence": "© tutti i diritti riservati",
      "water_body": "lago_di_como",
      "spot_id": "dervio"
    }
  ]
}
```

Ricarica la pagina: la foto compare nella banda in cima e nella galleria dello spot.

| Campo | Obbligatorio | Note |
|---|---|---|
| `file` **oppure** `url` | sì | `file` è relativo a `photos/`; `url` per un'immagine ospitata altrove |
| `credit` | **sì** | Senza credito la voce viene ignorata. Non è burocrazia: è la riga che permette di pubblicare la foto |
| `licence` | consigliato | Mostrato accanto al credito |
| `water_body` | consigliato | La foto compare quando è selezionato quel lago |
| `spot_id` | opzionale | Priorità massima su quello spot |
| `caption` | opzionale | Testo alternativo e didascalia |

Formati accettati: `.jpg`, `.jpeg`, `.png`, `.webp`, `.avif`, `.svg`.

## Perché il file parte vuoto

Le fotografie hanno un autore. SailWise non distribuisce immagini su cui non ha
diritti, e una foto trovata su un sito non diventa utilizzabile perché sta bene nella
homepage. Le tue foto invece sono tue: mettile e l'app diventa la tua.

Se usi una foto di qualcun altro, servono il permesso o una licenza compatibile
(Creative Commons, Wikimedia Commons, Unsplash…). In quel caso `credit` e `licence`
sono ciò che rende la cosa in regola, ed è per questo che senza `credit` la voce viene
scartata invece che mostrata.

## Cosa c'è già

Due illustrazioni vettoriali disegnate per questo progetto:

- `backend/static/img/hero-light.svg` — barca a vela su un lago alpino
- `backend/static/img/hero-dark.svg` — la stessa scena al tramonto, per il tema scuro

Sono parte del repository sotto licenza MIT, si adattano al tema e pesano pochi KB.
Restano come sfondo quando non hai ancora aggiunto foto, quindi l'app non è mai spoglia
e non ha mai bisogno di un segnaposto preso in prestito.

## Consigli pratici

- **Formato orizzontale**, almeno 1600 px di larghezza: la banda è larga e bassa.
- Il **soggetto leggermente decentrato**: al centro passa il titolo.
- Comprimi prima di committare — `.webp` a qualità 80 pesa un quarto di un JPEG.
- Le foto in `data/images/photos/` sono **git-ignored** per default: sono tue, non
  finiscono nel repository per sbaglio. Se vuoi pubblicarle, togli l'esclusione da
  `.gitignore` consapevolmente.
