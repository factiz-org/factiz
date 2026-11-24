"""Doublecheck — de resolver-laag voor factchecks."""

import logging

# DR3: artefactinhoud wordt nooit gelogd. De kraan gaat hier op
# bibliotheekniveau dicht in plaats van per aanroepsite.
logging.getLogger(__name__).addHandler(logging.NullHandler())
logging.getLogger(__name__).propagate = False
