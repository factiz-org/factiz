# Onzichtbare of regelbrekende tekens in TypeScript als escape schrijven (het schrijfgereedschap zet \u om in tekens).
import sys, unicodedata
for p in sys.argv[1:]:
    t = open(p, encoding="utf-8").read()
    uit = "".join(("\\u%04x" % ord(c) if ord(c) <= 0xffff else "\\u{%x}" % ord(c))
                  if (c not in "\n " and unicodedata.category(c) in ("Zl", "Zp", "Zs", "Cc", "Cf", "Mn", "Co", "Cs")) else c
                  for c in t)
    if uit != t:
        open(p, "w", encoding="utf-8").write(uit)
        print("escaped:", p)
