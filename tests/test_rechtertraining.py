"""De herordenaar bijgetraind als rechter (PLAN #30.3, kandidaat D): hij leert
alleen van het lesdeel, en *zelfde* is het enige doel.
"""

from doublecheck import rechtermeting as rm
from doublecheck import rechtertraining as rt


def test_the_judge_learns_only_from_the_teaching_part():
    paren = [{"vraag": f"v{i}{rol}", "kandidaat": "k", "label": label, "rol": rol, "zaak": f"gfc-{i}"}
             for i in range(300) for rol in ("leren", "meten") for label in ("zelfde", "verwant")]
    les = rt.trainingsparen(paren)
    assert les and all(rm.deel(p["zaak"]) == "les" and p["rol"] == "leren" for p, _ in les)


def test_only_the_same_claim_is_a_positive():
    assert [rt.doel(label) for label in ("zelfde", "verwant", "anders", "tegenspraak")] == [1.0, 0.0, 0.0, 0.0]


def test_real_pairs_can_weigh_more_than_made_ones():
    paren = [{"vraag": f"v{i}", "kandidaat": "k", "label": "zelfde", "rol": "leren", "zaak": f"gfc-{i}",
              "bron": bron} for i in range(200) for bron in ("gemaakt", "haiku-echt")]
    les = rt.trainingsparen(paren, echt_gewicht=3)
    n = {b: sum(p["bron"] == b for p, _ in les) for b in ("gemaakt", "haiku-echt")}
    assert n["haiku-echt"] == 3 * n["gemaakt"]
