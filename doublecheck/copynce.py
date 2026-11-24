"""De matcher van CopyNCE, nagebouwd in eigen code (PLAN #32.20 V3).

CopyNCE (Lu e.a., ICCV 2025, Apache-2.0) is gemaakt om kopieën van een beeld te herkennen, ook bewerkt: uitgesneden,
met tekst of een stempel erover, in een collage. De matcher kijkt naar twee beelden tegelijk en geeft een score van 0
tot 1. Vrijgegeven is alleen de ViT-S van 224 pixels zonder fijnafstemming.

Hun code draait hier nooit. Het model is nagebouwd uit hun beschrijving (`core/models` en
`matching_default_config.yaml` in github.com/eddielyc/CopyNCE):
- per beeld 8 lagen van een ViT-S (patches van 16 pixels, 384 breed, 6 koppen), zonder laatste normalisatie;
- de tokens van de twee beelden achter elkaar, met een eigen CLS-token ervoor, door 4 lagen en een normalisatie;
- de kop: nog een normalisatie, de CLS-token, een lineaire laag en een sigmoid.

De volgorde van de twee beelden doet er niet toe: de lagen samen weten niet welk token van welk beeld komt. De gewichten
worden alleen als getallen geladen (`weights_only`) en moeten precies passen. Een meting, geen kern: alleen als V3 de
beslisregel haalt, komt hij in de kern.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from doublecheck.image_fingerprint import as_image

VERSIE = "copynce-matcher-vits224-v1"
GEWICHTEN = Path(__file__).resolve().parent.parent / "data" / "extern" / "copynce" / "matcher_vits_224.pth.tar"
# sha256 van matcher_vits_224.pth.tar zoals gedownload op 2026-11-01 van de link in de README van de makers
VINGERAFDRUK = "dd8dea1c345039bbda303c42457aa3a0389d46fb37ea39506bfb1faddedda1df"
MAAT, PATCH, BREED, KOPPEN = 224, 16, 384, 6
LAGEN_BEELD, LAGEN_SAMEN = 8, 4
GEMIDDELDE, SPREIDING = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
_EPS = 1e-4


class Weigering(Exception):
    """De gewichten zijn niet de vrijgegeven gewichten, of bevatten meer dan getallen."""


class _Aandacht(nn.Module):
    def __init__(self):
        super().__init__()
        self.qkv = nn.Linear(BREED, 3 * BREED)
        self.proj = nn.Linear(BREED, BREED)

    def forward(self, x):
        b, n, c = x.shape
        q, k, v = self.qkv(x).reshape(b, n, 3, KOPPEN, c // KOPPEN).permute(2, 0, 3, 1, 4)
        return self.proj(F.scaled_dot_product_attention(q, k, v).transpose(1, 2).reshape(b, n, c))


class _Mlp(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(BREED, 4 * BREED)
        self.fc2 = nn.Linear(4 * BREED, BREED)

    def forward(self, x):
        return self.fc2(F.gelu(self.fc1(x)))


class _Laag(nn.Module):
    def __init__(self):
        super().__init__()
        self.norm1 = nn.LayerNorm(BREED, eps=_EPS)
        self.attn = _Aandacht()
        self.norm2 = nn.LayerNorm(BREED, eps=_EPS)
        self.mlp = _Mlp()

    def forward(self, x):
        x = x + self.attn(self.norm1(x))
        return x + self.mlp(self.norm2(x))


class _Patches(nn.Module):
    def __init__(self):
        super().__init__()
        self.proj = nn.Conv2d(3, BREED, PATCH, PATCH)

    def forward(self, x):
        return self.proj(x).flatten(2).transpose(1, 2)


class _Beeld(nn.Module):
    def __init__(self):
        super().__init__()
        self.patch_embed = _Patches()
        self.cls_token = nn.Parameter(torch.zeros(1, 1, BREED))
        self.pos_embed = nn.Parameter(torch.zeros(1, (MAAT // PATCH) ** 2 + 1, BREED))
        self.blocks = nn.ModuleList(_Laag() for _ in range(LAGEN_BEELD))

    def forward(self, x):
        x = self.patch_embed(x)
        x = torch.cat([self.cls_token.expand(x.shape[0], -1, -1), x], dim=1) + self.pos_embed
        for laag in self.blocks:
            x = laag(x)
        return x


class _Samen(nn.Module):
    def __init__(self):
        super().__init__()
        self.cls_token = nn.Parameter(torch.zeros(1, 1, BREED))
        self.blocks = nn.ModuleList(_Laag() for _ in range(LAGEN_SAMEN))
        self.norm = nn.LayerNorm(BREED, eps=_EPS)

    def forward(self, x):
        x = torch.cat([self.cls_token.expand(x.shape[0], -1, -1), x], dim=1)
        for laag in self.blocks:
            x = laag(x)
        return self.norm(x)


class _Kop(nn.Module):
    def __init__(self, met_classifier: bool):
        super().__init__()
        self.norm = nn.LayerNorm(BREED, eps=_EPS)
        if met_classifier:
            self.classifier = nn.Linear(BREED, 1)


class Matcher(nn.Module):
    """De namen van de onderdelen volgen de vrijgegeven gewichten, zodat die precies passen. De kop `fusion_head` hoort
    bij hun leerdoel en doet bij een score niets."""

    def __init__(self):
        super().__init__()
        self.encoder = _Beeld()
        self.fusion = _Samen()
        self.heads = nn.ModuleDict({"cls_head": _Kop(True), "fusion_head": _Kop(False)})

    @torch.no_grad()
    def tokens(self, beelden: torch.Tensor) -> torch.Tensor:
        """[B, 3, 224, 224] -> [B, 197, 384]: per beeld één keer, daarna te combineren met elk ander beeld."""
        return self.encoder(beelden)

    @torch.no_grad()
    def score(self, a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        """Tokens van twee rijtjes beelden [B, 197, 384] -> [B] scores van 0 tot 1."""
        kop = self.heads["cls_head"]
        x = kop.norm(self.fusion(torch.cat([a, b], dim=1)))
        return torch.sigmoid(kop.classifier(x[:, 0])).squeeze(-1)


def laad(pad: Path = GEWICHTEN, vingerafdruk: str = VINGERAFDRUK, apparaat: str = "cpu") -> Matcher:
    """De vrijgegeven gewichten, alleen als getallen, en alleen als het bestand het verwachte is en precies past."""
    inhoud = Path(pad).read_bytes()
    if hashlib.sha256(inhoud).hexdigest() != vingerafdruk:
        raise Weigering(f"{Path(pad).name} is niet het bestand met vingerafdruk {vingerafdruk[:12]}")
    del inhoud
    try:
        pakket = torch.load(pad, map_location="cpu", weights_only=True)
    except Exception as e:   # meer dan getallen: nooit laden
        raise Weigering(f"{Path(pad).name} bevat meer dan gewichten") from e
    staat = pakket.get("model", pakket) if isinstance(pakket, dict) else pakket
    model = Matcher()
    model.load_state_dict({k.removeprefix("module."): v for k, v in staat.items()}, strict=True)
    return model.to(apparaat).train(False)


def invoer(beeld) -> torch.Tensor:
    """Een beeld (bytes of PIL) als [3, 224, 224]: kleur, bicubisch naar 224 bij 224 zonder bijsnijden, en genormaliseerd
    zoals bij hun toets."""
    b = as_image(beeld).convert("RGB").resize((MAAT, MAAT), resample=3)   # 3 = bicubisch
    x = (np.asarray(b, dtype=np.float32) / 255.0 - np.array(GEMIDDELDE, np.float32)) / np.array(SPREIDING, np.float32)
    return torch.from_numpy(x.transpose(2, 0, 1).copy())


def scores(model: Matcher, vraag: torch.Tensor, index: torch.Tensor, batch: int = 64) -> np.ndarray:
    """De score van één beeld (tokens [197, 384]) tegen elk beeld van een index (tokens [N, 197, 384])."""
    uit = []
    for i in range(0, index.shape[0], batch):
        deel = index[i:i + batch]
        uit.append(model.score(vraag[None].expand(deel.shape[0], -1, -1), deel).float().cpu().numpy())
    return np.concatenate(uit) if uit else np.zeros(0, dtype=np.float32)
