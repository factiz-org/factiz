"""Zichtbare bron in een artefact vastleggen als *waargenomen* (E1.S3-AC3).

Een logo of URL in een screenshot zegt dat er iets op het beeld stáát — niet
dat de bron het ook gepubliceerd heeft. Screenshots worden nagemaakt; dat is
juist een klassiek desinformatiepatroon. Daarom is het onderscheid hier
structureel en geen afspraak: `ObservedSource` heeft geen veld dat een
geverifieerde status kan uitdrukken, en `status` is een property die altijd
"waargenomen" teruggeeft en niet overschreven kan worden.

Verifiëren zou betekenen: bij de uitgever navragen of dit echt van hen is.
Dat doet Doublecheck niet — de aanwijsbare bron komt uitsluitend uit de
factcheck in de index (DR1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Expliciete TLD-lijst in plaats van "alles met een punt": OCR laat regelmatig
# een spatie weg na een punt, en "niet.Volgens" is geen bron. De lijst dekt de
# TLD's die in het corpus voorkomen (com, be, nl, vlaanderen, org) plus de
# gangbare Europese en nieuws-TLD's; uitbreiden is een kwestie van toevoegen.
_TLDS = (
    "nl", "be", "eu", "de", "fr", "com", "org", "net", "info", "news", "media",
    "vlaanderen", "amsterdam", "brussels", "co.uk", "tv", "press",
)
# Twee vormen: mét expliciet http(s):// of www. (ondubbelzinnig), of een kaal
# domein waarvan de TLD in de lijst staat.
_MET_PREFIX = re.compile(
    r"(?:https?://|www\.)((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.[a-z]{2,24})",
    re.IGNORECASE,
)
_KAAL_DOMEIN = re.compile(
    r"\b((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:"
    + "|".join(tld.replace(".", r"\.") for tld in _TLDS)
    + r"))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ObservedSource:
    kind: str
    value: str

    @property
    def status(self) -> str:
        """Altijd 'waargenomen'; er bestaat geen andere status (E1.S3-AC3)."""
        return "waargenomen"


def observe_sources(text: str) -> tuple[ObservedSource, ...]:
    if not text:
        return ()
    gezien: list[ObservedSource] = []
    for patroon in (_MET_PREFIX, _KAAL_DOMEIN):
        for treffer in patroon.finditer(text):
            waarde = treffer.group(1).casefold().removeprefix("www.")
            if waarde not in {bron.value for bron in gezien}:
                gezien.append(ObservedSource(kind="domein", value=waarde))
    return tuple(gezien)
