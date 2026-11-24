"""Een paneel van schriften, om code te toetsen die stilzwijgend Latijn aanneemt.

Vijf keer in dit project ging hetzelfde mis, en elke keer zag het er goed uit:

- **§17a** — `.upper()` is een no-op in het Arabisch, Han en Devanagari, dus het
  "artefact" wás de claim. Gelijkenis 1,000, een schitterend cijfer, nul bewijs.
- **§39** — het onderscheid gemeten op twaalf handgekozen talen in plaats van
  alle 44; zes ineengeklapte talen bleven onopgemerkt tot een cluster van 89
  leden opdook.
- **§45** — de oordeeltabel kende Nederlands en Engels terwijl de index zestien
  talen droeg: 53% van het corpus kwam terug als `onbekend`.
- **§46** — de entiteitsmaat leunde op hoofdletters, en vuurde daardoor nul keer
  op 61% van de vetoblokkades.
- **§48c en §50c** — de uitgeverssleutel sneed twee keer te diep: `[a-z0-9]`
  smolt 107 Cyrillische namen tot één, en `\\w` verminkte `क्विंट हिंदी` tot
  `कवटहद` omdat het combinerende tekens laat vallen.

Het patroon is niet "iemand vergat het". Het is dat **niets het merkte**: de
tests draaiden op Latijnse invoer, de cijfers werden beter, en de fout viel per
constructie buiten elke meting.

Dit paneel is de tegenmaatregel. Alle teksten zijn écht corpusmateriaal — geen
verzonnen strings in schriften die de opsteller niet leest.
"""

from __future__ import annotations

# Uit `claim.canonical_text` van het CC BY-corpus (2026-08-31).
UIT_HET_CORPUS = {
    "arabisch": 'استبعاد الطالبة السورية "رؤى محمود شيخ" من قائمة أوائل الجمهورية',
    "bengaals": "ভাৰতত শ্বেখ হাছিনাই হিন্দু ধৰ্ম গ্ৰহণ কৰিছে ।",
    "han": "衆院選・佐賀1区で無効5000票、不正選挙の疑惑?",
    "cyrillisch": "В Беларуси роды бесплатные, а в европейских страна стоят €10-12 тыс.",
    "devanagari": "इज़राइल अब ईरान को दूसरा गांजापट्टी बनाकर ही दम लेगा..!!",
    "ethiopisch": "ኢትዮጵያ የነዳጅ ምርቷን ለገበያ ማቅረቧን ያሳያል በሚል ፌስቡክ ላይ የተጋራው ይህ ልጥፍ",
    "georgisch": "ქრისტეს ხატი ჭიანჭველებმა დაწვას გადაარჩინეს",
    "grieks": "Ρομπότ του διαδικτύου τσακώνονται στη Wikipedia για τον Μέγα Αλέξανδρο",
    "gujarati": "અડવાણીએ RSS વિરુદ્ધ ટ્વિટ કર્યું હતું.",
    "hangul": "하루 42만원 꼴 '의원 세비'…반납 가능할까",
    "hebreeuws": "משרד הבריאות בשווייץ ממליץ לא לעשות ממוגרפיה",
    "hiragana": "ほんこん氏「トランプ大統領になってからガザで人は亡くなっていない」?",
    "katakana": "イスラエルの原子力発電所をイランのミサイルが破壊?",
    "latijn": "Buddha Statue “Surviving” Nepal’s Recent Floods?",
    "birmaans": "ဂမ်ဘီယာနိုင်ငံ NLD ကိုထောက်ခံနေကြတဲ့ ဓာတ်ပုံတွေ",
    "oriya": "ସୀତା-ଅବତାରରେ ସୀତାଙ୍କ ଭୂମିକା ପାଇଁ କରୀନା କପୁରଙ୍କ ନିକଟକୁ ଯାଇଥିଲେ",
    "thai": "สิงคโปร์ไล่กัมพูชาออกจากอาเซียน พร้อมแบ่งดินแดนให้ไทย ลาว และเวียดนาม",
}

# Uit de Data Commons-feed. Deze negen talen zijn geweerd omdat het model ze
# niet uit elkaar houdt (§39) — maar de code moet ze wél heel laten, want een
# ander model kan ze morgen wél aan. Khmer, Singalees en Telugu dragen
# zero-width tekens: precies het soort teken dat een sleutel stil weggooit.
UIT_DE_FEED = {
    "gurmukhi": "ਕਰਤਾਰਪੁਰ ਸਾਹਿਬ ਦੇ ਦਰਸ਼ਨਾਂ ਲਈ ਰਜਿਸਟ੍ਰੇਸ਼ਨ ਫਾਰਮ ਜਾਰੀ",
    "kannada": "ಈ ಚಿತ್ರದಲ್ಲಿ ಪ್ರಧಾನಿ ಮೋದಿಯವರೊಂದಿಗೆ ಕಾಣುವ ವ್ಯಕ್ತಿ ಜಾರ್ಜ್ ಸೊರೊಸ್",
    "khmer": "នៅ​ថៃ​រញ្ជួយ​ដី​សារថ្មី​កម្រិត ៣.៥",
    "malayalam": "റഷ്യൻ എണ്ണക്കപ്പൽ അമേരിക്ക പിടിച്ചെടുക്കുന്ന ദൃശ്യങ്ങൾ",
    "singalees": "කොටුවේ පොඩි හාමුදුරුවන් අපවත් ‌වී ඇත",
    "tamil": "மெரினாவில் வைக்கவிருந்த பேனா சிலை அகற்றப்படும் காட்சி",
    "telugu": "బీజేపీ ఎంపీ కంగనా రనౌత్‌పై దాడి వీడియో",
}

# Uitgeversnamen uit het corpus. Korter dan claims, en juist dáár ging de
# sleutel twee keer stuk.
NAMEN = {
    "naam-devanagari": "क्विंट हिंदी",
    "naam-devanagari-variant": "क्विंट हिन्दी",
    "naam-tamil": "ஃபேக்ட் கிரஸண்டோ",
    "naam-arabisch": "المرصد الفلسطيني “تحقق”",
    "naam-cyrillisch": "Вокс Чек",
    "naam-latijn-diakriet": "Di Động Việt",
    "naam-latijn": "El Detector / Univision Noticias",
}

PANEEL = {**UIT_HET_CORPUS, **UIT_DE_FEED, **NAMEN}
