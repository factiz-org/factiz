"""De proef van zoeken op een geplakt bericht (PLAN #34.2au, SPECS E9.S6 AC5).

    python -m factiz_site.berichtproef [<publicatie.db>] [--zaad N] [--toets]

P: 200 pagina's in zes talen met het Latijnse schrift, met een vast zaad. Elke vraag is de bewering met een kwart van de
woorden weg en een zin van een doorgestuurd bericht ervoor en erna, zoals iemand een bericht plakt. Goed is: de pagina
staat bij de eerste drie. S: 20 gewone berichten zonder bewering, met de hand geschreven; goed is: geen treffer.
Gemeten zoals het zoeken nu is (`bericht=False`) en zoals het wordt (`bericht=True`). De eisen staan vooraf in PLAN.
Dit meet de woorden, niet de betekenis: een bericht in andere woorden dan de bewering haalt dit niet.
"""

from __future__ import annotations

import random
import sqlite3
import statistics
import sys
from pathlib import Path

from factiz_site import db

ZAAD = 2026
AANTAL = 200
TALEN = ("en", "nl", "es", "fr", "de", "pt")
RUIS = {
    "nl": (("Doorgestuurd bericht.", "LEES DIT EN DEEL HET.", "Dit moet iedereen weten:"),
           ("Deel dit voordat het verwijderd wordt.", "Stuur door naar al je contacten.", "Ze willen niet dat je dit weet.")),
    "en": (("Forwarded as received.", "PLEASE READ AND SHARE.", "Everyone needs to know this:"),
           ("Share this before they delete it.", "Forward to all your contacts.", "They don't want you to know this.")),
    "es": (("Reenviado.", "LEAN ESTO Y COMPARTAN.", "Todos deben saber esto:"),
           ("Compártelo antes de que lo borren.", "Reenvía a todos tus contactos.", "No quieren que lo sepas.")),
    "fr": (("Transféré.", "LISEZ ET PARTAGEZ.", "Tout le monde doit savoir ceci :"),
           ("Partagez avant que ce soit supprimé.", "Transférez à tous vos contacts.", "Ils ne veulent pas que vous le sachiez.")),
    "de": (("Weitergeleitet.", "LESEN UND TEILEN.", "Das muss jeder wissen:"),
           ("Teilt das, bevor es gelöscht wird.", "Leitet es an alle Kontakte weiter.", "Sie wollen nicht, dass ihr das wisst.")),
    "pt": (("Encaminhado.", "LEIAM E COMPARTILHEM.", "Todo mundo precisa saber disso:"),
           ("Compartilhe antes que apaguem.", "Encaminhe para todos os seus contatos.", "Eles não querem que você saiba disso.")),
}
GEWOON = (
    "Hoi allemaal, morgen is de vergadering om acht uur, neem allemaal koffie mee en vergeet de stoelen niet",
    "Lieve mensen, het verjaardagsfeest van oma is verplaatst naar zondagmiddag in het buurthuis, graag een taart meenemen",
    "Wie kan zaterdag rijden naar het voetbaltoernooi? De jongens moeten om negen uur bij het veld zijn",
    "De sleutel van de schuur ligt onder de bloempot naast de achterdeur, vergeet niet af te sluiten",
    "Volgende week is de school dicht vanwege de studiedag, de opvang is wel gewoon open tot zes uur",
    "Ik heb de boodschappen gehaald maar ze hadden geen volkoren brood meer, het witte is ook prima toch",
    "Herinnering: de contributie voor het tennisseizoen moet voor het einde van de maand betaald worden",
    "Het concert van het koor begint om half acht in de kerk, kaartjes zijn nog te koop bij de ingang",
    "Kan iemand mijn planten water geven als ik op vakantie ben? Ik ben twee weken weg vanaf vrijdag",
    "De wasmachine maakt weer een raar geluid tijdens het centrifugeren, weet iemand een goede monteur in de buurt",
    "Hi everyone, dinner is at seven tonight, can someone pick up bread and a bottle of wine on the way",
    "Reminder that the book club meets on Thursday at Sarah's place, we are discussing the second half of the novel",
    "Does anyone have a ladder I can borrow this weekend? I need to clean the gutters before the rain starts",
    "The kids' swimming lesson moved to Saturday morning, please bring towels and goggles",
    "Our flight lands at half past four, could you pick us up at terminal two near the coffee shop",
    "Happy birthday to the best brother in the world, hope you have a wonderful day with the family",
    "The plumber is coming between ten and twelve tomorrow so someone needs to be home to open the door",
    "Team meeting is cancelled this week, we will catch up next Monday with the quarterly numbers",
    "I left my umbrella in your car yesterday, no rush but I would like it back before the weekend",
    "Garden party at our house on Sunday afternoon, bring a chair and something to share for the barbecue",
)

# Nieuw voor het oordeel (2026-11-15), geschreven vóór die meting: op GEWOON en zaad 2026 is de regel bijgesteld, dus het
# oordeel valt op deze twintig en zaad 2027 (`--toets`)
GEWOON_TOETS = (
    "Goedemorgen, de bakker is vandaag gesloten dus ik haal de broodjes bij de supermarkt op de hoek",
    "Wie heeft mijn blauwe sjaal gezien? Ik denk dat ik hem gisteren bij de training heb laten liggen",
    "De buren geven zaterdag een barbecue en wij zijn ook uitgenodigd, zullen we een salade meenemen",
    "Mijn trein heeft twintig minuten vertraging, begin maar vast met eten zonder mij",
    "Vergeet niet dat de vuilniszakken dinsdagavond buiten moeten, de ophaaldienst komt woensdag vroeg",
    "Het rapport van Lisa is binnen, ze heeft een acht voor wiskunde en een negen voor tekenen",
    "Zullen we zondag gaan fietsen langs de rivier als het droog blijft? Daarna kunnen we pannenkoeken eten",
    "De kapper heeft mijn afspraak verzet naar donderdag om half vier, kun jij de kinderen ophalen",
    "Ik zoek nog iemand die een verhuisdoos of tien over heeft, we verhuizen eind volgende maand",
    "Bedankt voor de gezellige avond gisteren, de taart was heerlijk en de kinderen hebben genoten",
    "Morning all, the car is booked in for its service on Tuesday so I will need a lift to work",
    "Can someone feed the cat tonight? There is a new bag of food in the cupboard under the sink",
    "We are out of milk and eggs, I will grab some on the way home unless anyone else is passing the shop",
    "The heating engineer said the boiler is fine, it just needed the pressure topping up",
    "Congratulations on the new job, we should celebrate with a meal out when you are settled in",
    "Football practice is moved to the indoor hall this week because the pitch is flooded",
    "Please return the library books before Friday or we will have to pay another fine",
    "Grandma arrives at the station at eleven, I will meet her there and bring her straight to lunch",
    "The school photos are ready, you can order prints online until the end of next week",
    "Thanks for lending me the drill, I will drop it back round on Saturday with a few beers",
)


def bericht_uit(bewering: str, taal: str, rng: random.Random) -> str:
    """De bewering zoals iemand haar plakt: een kwart van de woorden weg, een zin ervoor en erna."""
    woorden = bewering.split()
    weg = set(rng.sample(range(len(woorden)), len(woorden) // 4))
    voor, na = RUIS[taal]
    return f"{rng.choice(voor)} {' '.join(w for i, w in enumerate(woorden) if i not in weg)} {rng.choice(na)}"


def _plek(pub: db.Publicatie, vraag: str, nummer: str | None, bericht: bool) -> tuple[int | None, int]:
    """De plek van de bedoelde factcheck bij de eerste 25, en het aantal treffers. Een geplakt bericht zonder treffer
    toont de tien met de meeste van dezelfde woorden, gemarkeerd als geen treffer: die tellen als 0 treffers, maar de plek
    erin telt wel, zoals een bezoeker haar ziet."""
    uit = pub.zoek_ruim(vraag, 1, "en", bericht=bericht)
    nummers = [r["nummer"] for r in uit["rijen"]]
    treffers = 0 if (bericht and uit.get("bericht") and uit["deels"]) else uit["totaal"]
    return (nummers.index(nummer) + 1 if nummer in nummers else None), treffers


def meet(bestand: str | Path, aantal: int = AANTAL, zaad: int = ZAAD, stil: tuple[str, ...] = GEWOON) -> dict:
    pub = db.Publicatie(bestand)
    pub.afkortingen_klaar(60)
    conn = sqlite3.connect(f"{Path(bestand).resolve().as_uri()}?mode=ro", uri=True)
    rijen = [r for r in conn.execute(
        f"SELECT nummer, bewering, taal FROM pagina WHERE taal IN ({','.join('?' * len(TALEN))}) ORDER BY nummer", TALEN)
        if 12 <= len(r[1].split()) <= 60]
    conn.close()
    rng = random.Random(zaad)
    proef = rng.sample(rijen, min(aantal, len(rijen)))
    uitslag: dict = {}
    for stand in (False, True):
        r = random.Random(zaad + 1)
        plekken, totalen = [], []
        for nummer, bewering, taal in proef:
            plek, totaal = _plek(pub, bericht_uit(bewering, taal, r), nummer, stand)
            plekken.append(plek)
            totalen.append(totaal)
        stil_ = [_plek(pub, tekst, None, stand)[1] for tekst in stil]
        uitslag["nu" if not stand else "bericht"] = {
            "eerste": sum(p == 1 for p in plekken), "eerste_drie": sum(p is not None and p <= 3 for p in plekken),
            "eerste_tien": sum(p is not None and p <= 10 for p in plekken), "vragen": len(plekken),
            "treffers_mediaan": statistics.median(totalen), "treffers_max": max(totalen),
            "stil_zonder": sum(t == 0 for t in stil_), "stil_max": max(stil_), "stil": len(stil_)}
    return uitslag


def gehaald(uitslag: dict) -> bool:
    nu, b = uitslag["nu"], uitslag["bericht"]
    return (b["eerste_drie"] >= 0.8 * b["vragen"] and b["eerste_drie"] >= nu["eerste_drie"] and b["treffers_max"] <= 100
            and b["stil_zonder"] >= 16 and b["stil_max"] <= 10)


def main() -> None:  # pragma: no cover - CLI
    from factiz_site.app import _standaard_pad

    toets = "--toets" in sys.argv
    zaad = int(sys.argv[sys.argv.index("--zaad") + 1]) if "--zaad" in sys.argv else (ZAAD + 1 if toets else ZAAD)
    argumenten = [a for a in sys.argv[1:] if not a.startswith("--") and a != str(zaad)]
    bestand = argumenten[0] if argumenten else _standaard_pad()
    uitslag = meet(bestand, zaad=zaad, stil=GEWOON_TOETS if toets else GEWOON)
    for stand, u in uitslag.items():
        print(f"{stand:8} P: eerste {u['eerste']}, eerste drie {u['eerste_drie']}, eerste tien {u['eerste_tien']} van "
              f"{u['vragen']}; treffers mediaan {u['treffers_mediaan']}, max {u['treffers_max']}. "
              f"S: {u['stil_zonder']} van {u['stil']} zonder treffer, max {u['stil_max']}")
    print(f"eis gehaald: {gehaald(uitslag)}")
    raise SystemExit(0 if gehaald(uitslag) else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
