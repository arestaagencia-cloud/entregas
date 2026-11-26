# Gera os LUTs iniciais (.cube, 33 pontos, Rec709 -> Rec709) que vêm com o Editor de Bailes.
# Pensados para vídeo de baile gravado em Rec709 na A7IV: luz de salão quente, pouca luz, pele.
import numpy as np
from pathlib import Path

N = 33
OUT = Path(__file__).resolve().parent / "Editor de Bailes.app/Contents/Resources/luts"
g = np.linspace(0, 1, N)
B, G, R = np.meshgrid(g, g, g, indexing="ij")   # .cube: o vermelho varia mais rápido
rgb = np.stack([R, G, B], -1).reshape(-1, 3)

luma = lambda c: c @ np.array([0.2126, 0.7152, 0.0722])
def sat(c, k):
    y = luma(c)[:, None]; return y + (c - y) * k
def curva(c, k):  # S suave em torno de 0.5 (k>0 = mais contraste)
    return c + k * np.sin((c - 0.5) * np.pi) * 0.5 * (1 - np.abs(2 * c - 1)) * 2
def lift(c, preto=0.0, branco=1.0):
    return preto + c * (branco - preto)
def tons(c, sombra, luz):  # cor nas sombras / altas luzes (vetores RGB pequenos)
    y = luma(c)[:, None]
    return c + np.array(sombra) * (1 - y) ** 2 + np.array(luz) * y ** 2
def meios(c, v):
    y = luma(c)[:, None]; return c + np.array(v) * 4 * y * (1 - y)

LOOKS = {
    "01 Natural+":            lambda c: sat(curva(c, 0.10), 1.08),
    "02 Quente dourado":      lambda c: sat(curva(meios(c, [0.035, 0.012, -0.04]), 0.10), 1.06),
    "03 Corrige luz amarela": lambda c: sat(curva(meios(c, [-0.035, -0.01, 0.05]), 0.06), 0.96),
    "04 Cinema suave":        lambda c: sat(curva(tons(lift(c, 0.025, 0.985), [-0.02, 0.01, 0.035], [0.03, 0.012, -0.03]), 0.14), 0.95),
    "05 Noite elegante":      lambda c: sat(curva(tons(c, [-0.015, 0.0, 0.03], [0.02, 0.01, -0.01]), 0.20), 0.90),
    "06 Vintage":             lambda c: sat(tons(lift(curva(c, -0.04), 0.06, 0.95), [0.01, 0.02, 0.0], [0.04, 0.02, -0.03]), 0.78),
    "07 Vibrante":            lambda c: sat(curva(c, 0.16), 1.25),
    "08 Preto e branco":      lambda c: np.repeat(curva(luma(c)[:, None], 0.18), 3, 1),
}

for nome, f in LOOKS.items():
    out = np.clip(f(rgb.copy()), 0, 1)
    linhas = [f'TITLE "{nome[3:]}"', f"LUT_3D_SIZE {N}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    linhas += ["%.6f %.6f %.6f" % tuple(v) for v in out]
    (OUT / f"{nome}.cube").write_text("\n".join(linhas) + "\n")
    print(nome)
