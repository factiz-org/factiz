// De vaste teksten van het platform, uit dezelfde woordenlijsten (factiz_site/teksten/<taal>.json): de proef schrijft
// geen eigen tekst.
import en_ from '../../../factiz_site/teksten/en.json';
import nl_ from '../../../factiz_site/teksten/nl.json';
import de_ from '../../../factiz_site/teksten/de.json';
import es_ from '../../../factiz_site/teksten/es.json';
import fr_ from '../../../factiz_site/teksten/fr.json';
import pt_ from '../../../factiz_site/teksten/pt.json';
import ru_ from '../../../factiz_site/teksten/ru.json';
import uk_ from '../../../factiz_site/teksten/uk.json';
import id_ from '../../../factiz_site/teksten/id.json';
import tr_ from '../../../factiz_site/teksten/tr.json';
import zh_ from '../../../factiz_site/teksten/zh.json';
import ja_ from '../../../factiz_site/teksten/ja.json';
import hi_ from '../../../factiz_site/teksten/hi.json';
import ar_ from '../../../factiz_site/teksten/ar.json';
import fa_ from '../../../factiz_site/teksten/fa.json';

const LIJSTEN = { en: en_.teksten, nl: nl_.teksten, de: de_.teksten, es: es_.teksten, fr: fr_.teksten, pt: pt_.teksten, ru: ru_.teksten, uk: uk_.teksten, id: id_.teksten, tr: tr_.teksten, zh: zh_.teksten, ja: ja_.teksten, hi: hi_.teksten, ar: ar_.teksten, fa: fa_.teksten };

export function maakT(taal) {
  const lijst = LIJSTEN[taal];
  if (!lijst) throw new Error(`geen taal: ${taal}`);
  return (sleutel, waarden = {}) => {
    const vorm = lijst[sleutel];
    if (vorm === undefined) throw new Error(`geen tekst: ${sleutel}`);
    return vorm.replace(/\{(\w+)\}/g, (_, naam) => String(waarden[naam] ?? ''));
  };
}
