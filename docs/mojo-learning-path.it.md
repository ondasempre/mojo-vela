# 31. Roadmap didattica Mojo

> Questo è l'unico documento del repository scritto in italiano: è materiale
> didattico personale, non documentazione per contributori. Il resto di `docs/` è in
> inglese perché il progetto nasce per essere pubblicato.

## Il metodo

Per ogni livello, sempre nello stesso ordine (§27 del brief):

1. **cosa impari** — il concetto, prima del codice;
2. **perché conta** — cosa ti permette di fare che prima non potevi;
3. **quale caratteristica Mojo** stai usando;
4. **perché quella parte è adatta a Mojo** — e quando invece non lo è;
5. **come si scriverebbe in Python** — il confronto onesto, non lo strawman;
6. **cosa succede in memoria**;
7. **cosa succede nel compilatore**;
8. **esercizio + test**;
9. **misura**, quando ha senso misurare.

La regola numero 9 ha una conseguenza scomoda e voluta: **se un livello non produce
un miglioramento misurabile, il risultato negativo si scrive lo stesso.** Imparare
*quando Mojo non serve* è metà dell'obiettivo (ADR 0001).

---

## Livello 1 — Sintassi, `fn`, tipi ✅ Milestone 1

**Cosa impari.** `fn` contro `def`, tipi espliciti, `var`, `alias`, `Bool`, `Int`,
`Float64`, il fatto che una funzione `fn` non può sollevare eccezioni se non lo
dichiara con `raises`.

**Perché conta.** È la differenza fondamentale tra i due linguaggi: in Python i tipi
esistono a runtime, in Mojo esistono a compile time. Tutto il resto discende da qui.

**Caratteristica Mojo.** Tipizzazione statica con inferenza, `alias` per le costanti a
compile time.

**Il codice** (`mojo/src/sailwise/units.mojo`):

```mojo
fn clamp01(x: Float64) -> Float64:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x
```

**Riga per riga.**

- `fn` — funzione con contratto rigido: argomenti tipizzati obbligatoriamente, niente
  eccezioni implicite. `def` in Mojo esiste ed è più permissiva; `fn` è quella che
  vuoi nel motore di calcolo.
- `x: Float64` — un float IEEE-754 a 64 bit, **non** un oggetto. In CPython un
  `float` è un `PyObject` con refcount e header: 24 byte per contenere 8 byte di dato.
  Qui sono 8 byte, spesso direttamente in un registro.
- `-> Float64` — il tipo di ritorno è parte della firma. Il compilatore lo verifica.
- I confronti e i `return` si compilano in due-tre istruzioni macchina.

**In Python:**

```python
def clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))
```

Identica come logica. Ma a runtime CPython fa: lookup di `min` e `max` nei globals,
creazione di tuple di argomenti, chiamate a funzioni C, allocazione dell'oggetto
float risultato. L'annotazione `-> float` non viene usata dall'interprete: è
documentazione.

**In memoria.** `clamp01` non alloca nulla. Nessun heap, nessun refcount, nessun GC.
Il valore vive in un registro floating-point e sparisce quando la funzione ritorna.

**Nel compilatore.** Mojo abbassa il codice a MLIR e poi a LLVM IR. Una funzione così
piccola viene quasi certamente *inlined* nel chiamante, e i tre rami diventano
istruzioni di minimo/massimo senza salti condizionali.

**Esercizio.** Esercizio 1 di [milestone-1.md](milestone-1.md): `beaufort()` con i
suoi test. Attenzione ai valori di confine — sono l'unica parte interessante.

**Misura.** Non ancora. Misurare una funzione da tre righe fuori contesto misura il
rumore, non il codice.

---

## Livello 2 — Struct e type system ✅ Milestone 1

**Cosa impari.** `struct`, `@fieldwise_init`, i trait `Copyable` e `Movable`, il
concetto di *value semantics*.

**Perché conta.** È qui che nasce il vantaggio prestazionale vero, molto più che nella
sintassi delle funzioni.

**Il codice** (`mojo/src/sailwise/weather.mojo`):

```mojo
@fieldwise_init
struct HourlyWeather(Copyable, Movable):
    var hour: Int
    var wind_kn: Float64
    var gust_kn: Float64
    # ... altri sette campi
```

**Riga per riga.**

- `@fieldwise_init` — il compilatore sintetizza `__init__` con un parametro per campo,
  nell'ordine dichiarato. Sostituisce il vecchio decoratore `@value`, ora deprecato.
- `(Copyable, Movable)` — conformità ai trait dichiarata fra parentesi. Il compilatore
  sintetizza `__copyinit__` e `__moveinit__`. Dichiararli è ciò che ti permette di
  mettere il tipo dentro una `List`.
- `var hour: Int` — campo con tipo fisso. Il layout dello struct è deciso a compile
  time: offset noti, dimensione nota.

**In Python:**

```python
@dataclass(frozen=True)
class HourlyWeather:
    hour: int
    wind_kn: float
    ...
```

**In memoria — la differenza che conta.**

```
Mojo:   List[HourlyWeather]  →  [h0][h1][h2][h3]...   un blocco contiguo
                                 ogni [hN] = 10 campi inline, ~80 byte

Python: list[HourlyWeather]  →  [ptr][ptr][ptr]...    array di puntatori
                                   ↓    ↓    ↓
                                 oggetti sparsi nell'heap, ognuno con
                                 header + __dict__ o __slots__, e ogni
                                 float è a sua volta un oggetto separato
```

Scorrere la lista Mojo significa leggere memoria consecutiva: la cache CPU fa il suo
lavoro e il prefetcher indovina. Scorrere la lista Python significa saltare a
indirizzi non correlati, e ogni `h.wind_kn` è una dereferenziazione in più.

**Nel compilatore.** `HourlyWeather` non ha vtable, non ha refcount, non ha
indirezioni. `hours[i].wind_kn` diventa `base + i*sizeof(HourlyWeather) + offset`:
un'unica operazione di indirizzamento.

**La cosa importante da capire adesso**, perché condiziona il livello 6: questo layout
è *array of structs* (AoS). Va benissimo per il codice scalare. Quando arriverai a
SIMD ti servirà il layout opposto, *struct of arrays* (SoA): tutti i `wind_kn` in un
array contiguo, tutti i `gust_kn` in un altro. È il motivo per cui
[03-system-architecture.md](03-system-architecture.md) impone la conversione a array
piatti **al confine**, una volta sola.

**Esercizio.** Aggiungi `fn is_gusty(self) -> Bool` a `HourlyWeather` (rapporto raffica
/ vento sopra 1.4). Nota che `self` è in sola lettura di default: per mutare servirebbe
`mut self`.

---

## Livello 3 — Collections e data processing → Milestone 2

**Cosa impari.** `List[T]`, iterazione, la ricerca della finestra migliore come primo
algoritmo vero.

**Perché è adatto a Mojo.** La ricerca della finestra è una riduzione scorrevole su un
array contiguo di float: nessun ramo imprevedibile, nessuna allocazione nel ciclo
interno. È il caso ideale.

**In Python** si scriverebbe con `itertools` e una comprehension, ed è perfettamente
leggibile. Su 24 ore la differenza è invisibile. Diventa visibile su 5.000 spot × 24
ore, che è lo scenario nazionale del roadmap.

**Da misurare.** Prima misura reale del progetto: finestra migliore su N giorni
sintetici, Python puro contro NumPy contro Mojo scalare. Aspettati che NumPy vinca
contro Mojo scalare su array grandi — è vettorizzato in C. Se succede, scrivilo.

---

## Livello 4 — Memory management → Milestone 3

`owned`, `mut`, `read`, ownership transfer, `^` (transfer sigil), perché
`List[HourlyWeather]` passata come argomento non viene copiata.

**Il punto didattico:** Python risolve la gestione della memoria con il refcount e il
GC, e ti fa pagare quel servizio su ogni oggetto. Mojo la risolve a compile time con
l'ownership, e non ti fa pagare nulla a runtime — in cambio devi dire chi possiede
cosa. Il livello 4 è il momento in cui questo passa da fastidio a strumento.

**Esercizio.** Riscrivi `compute_wind_stats` in modo che non costruisca le due `List`
temporanee `speeds` e `gusts`. Misura prima e dopo. È la prima ottimizzazione onesta
del progetto.

---

## Livello 5 — Algoritmi → Milestone 3 / 7

Ranking, top-k con selezione parziale invece di ordinamento completo, filtri
geospaziali. Complessità: `O(n log n)` contro `O(n log k)`, e quando la differenza
smette di essere teorica.

---

## Livello 6 — SIMD → Milestone 8

**Cosa impari.** `SIMD[DType.float64, width]`, `simd_width_of`, vettorizzazione
esplicita, il residuo finale quando `n` non è multiplo della larghezza.

**Perché è adatto a Mojo.** Mojo espone SIMD come tipo di prima classe, non come
libreria. È probabilmente la ragione più forte per usarlo su questo progetto.

**Il prerequisito che ti sarai già costruito:** i dati in SoA (livello 2). Senza
quello, SIMD richiede una *gather* e il vantaggio evapora.

**Onestà obbligatoria.** Il confronto non è contro il ciclo Python: è contro NumPy,
che è già vettorizzato. Se Mojo SIMD non batte NumPy, il numero si pubblica lo stesso.

---

## Livello 7 — Parallelismo → Milestone 9

`parallelize[func](n_workers)`, partizionamento sugli spot, misura dello *speed-up*
reale contro il numero di core. Attenzione: lo scoring di 50 spot è troppo piccolo per
il parallelismo — l'overhead dei thread supera il lavoro. Serve N grande, ed è il
motivo per cui il benchmark è una *curva* e non un numero.

---

## Livello 8 — Interoperabilità Python ↔ Mojo → Milestone 10

Moduli di estensione Python scritti in Mojo, `PythonObject`, la conversione ai
confini. Vedi [adr/0003](adr/0003-mojo-python-boundary.md) per il motivo per cui
questo livello arriva **tardi** e non subito: l'interoperabilità in-process è ancora
in evoluzione, mentre il confine via CLI funziona oggi e ti isola dai cambiamenti del
linguaggio.

---

## Livello 9 — Benchmarking → trasversale

Il modulo `benchmark` della stdlib, warm-up, varianza, misurare il calcolo e non
l'I/O, non pubblicare mai un numero senza la macchina su cui è stato prodotto. La
strategia completa è in [09-testing-benchmarks.md](09-testing-benchmarks.md).

---

## Livello 10 — Architettura di produzione → Milestone 10

Impacchettare, versionare e distribuire il core Mojo; il fallback Python; cosa fare
quando un aggiornamento del linguaggio rompe la build il giorno del deploy. Questo
livello riguarda meno il linguaggio e più il fatto di dipendere da un linguaggio
giovane in produzione.

---

## Il dubbio da tenere vivo per tutto il percorso

Dopo ogni livello, rispondi per iscritto a due domande:

1. **Questo pezzo è più veloce in Mojo?** Con un numero, su una macchina nominata.
2. **Quel guadagno serve a un velista?** Se il ranking passa da 40 ms a 8 ms dentro
   una richiesta che ne impiega 280 di rete, la risposta onesta è no — e va scritta.

Un progetto che risponde "no" cinque volte su dieci e lo documenta ti ha insegnato
molto più di uno che riscrive tutto in Mojo e non misura niente.
