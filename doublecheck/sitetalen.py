"""De talen van de site (B74, B79, PLAN #34.2be), uit de ene lijst die het platform en de site ook lezen
(`factiz_site/teksten/sitetalen.json`). `BASIS` zijn de vijf van B74: hun teksten heeft een mens gezien, en een naam moet in
elk van hen een label hebben; in een nieuwe taal valt een naam zonder label terug op het Engels."""

import json
from pathlib import Path

_LIJST = json.loads((Path(__file__).resolve().parent.parent / "factiz_site" / "teksten" / "sitetalen.json")
                   .read_text(encoding="utf-8"))
SITETALEN: tuple[str, ...] = tuple(t["code"] for t in _LIJST["talen"])
BASIS: tuple[str, ...] = tuple(_LIJST["_meta"]["basis"])
