import io
import json
import os
import queue
import random
import threading
import time
import urllib.request
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import urlencode, urlparse

# Pillow sert a afficher les images des mods. Sans lui, l'appli marche
# quand meme (des vignettes de couleur remplacent les images).
try:
    from PIL import Image, ImageOps, ImageTk
    PILLOW = True
except ImportError:
    PILLOW = False

# ============================================================
# REGLAGES : remplace les valeurs "TON_..." par les tiennes
# ============================================================
NOM_APPLI = "minecraft mods"

URL_GITHUB = "https://github.com/NOVA-SCR1PT"          # ta page GitHub
URL_DISCORD = "https://discord.gg/TON_INVITATION"     # invitation de ton serveur

GITHUB_DEPOT = "NOVA-SCR1PT/MonLauncher"                 # pour l'onglet Releases
URL_LISTE_MODS = "https://raw.githubusercontent.com/NOVA-SCR1PT/MonLauncher/main/mods.json"

# Onglet Idees : lien "formResponse" de ton Google Form + numero du champ
FORM_URL = "https://docs.google.com/forms/d/e/TON_ID_FORM/formResponse"
FORM_CHAMP = "entry.0000000000"

# Dossier de base : celui de Minecraft. Chaque fichier va dans un sous-dossier
# selon son "type" dans mods.json (mod, texture, shader). Le bouton
# "Changer le dossier" permet de viser une autre installation.
DOSSIER_PAR_DEFAUT = Path(os.environ.get("APPDATA", str(Path.home()))) / ".minecraft"
SOUS_DOSSIERS = {"mod": "mods", "texture": "resourcepacks", "shader": "shaderpacks"}
TAILLE_IMAGE = 110      # taille des images des mods (pixels)
COLONNES = 3            # nombre de cartes par ligne
TELECHARGEMENTS_EN_MEME_TEMPS = 3

# ============================================================
# COULEURS : theme galactique sombre et clair
# ============================================================
THEMES = {
    "sombre": {
        "fond": "#0a0820", "panneau": "#15123a", "carte": "#1d1a4d",
        "survol": "#2b2670", "texte": "#ece9ff", "discret": "#9a95d0",
        "accent": "#8a63ff", "accent2": "#3fe0ff", "etoile": "#ffffff",
        "barre_fond": "#2a2660", "blanc": "#ffffff",
    },
    "clair": {
        "fond": "#f3f0ff", "panneau": "#e4deff", "carte": "#ffffff",
        "survol": "#d5ccff", "texte": "#1d1a45", "discret": "#6a65a0",
        "accent": "#6a3df0", "accent2": "#0a8fbd", "etoile": "#b9aaf5",
        "barre_fond": "#d9d3f5", "blanc": "#ffffff",
    },
}
theme_actuel = "sombre"


def coul(cle):
    return THEMES[theme_actuel][cle]


ENTETES = {"User-Agent": "MonLauncher/1.0"}
file_attente = queue.Queue()    # messages des threads vers la fenetre
limite_dl = threading.Semaphore(TELECHARGEMENTS_EN_MEME_TEMPS)
generation = 0                  # evite de melanger deux chargements de la liste

registre = []       # (widget, {option: cle de couleur}) recolores au changement de theme
redessins = []      # fonctions a rappeler au changement de theme
cartes = []         # les cartes de mods affichees


# ============================================================
# OUTILS
# ============================================================
def ouvrir_url(url):
    requete = urllib.request.Request(url, headers=ENTETES)
    return urllib.request.urlopen(requete, timeout=15)


def formater_temps(secondes):
    secondes = int(secondes)
    if secondes >= 60:
        return f"{secondes // 60} min {secondes % 60:02d} s"
    return f"{secondes} s"


def formater_taille(octets):
    return f"{octets / 1e6:.1f} Mo" if octets else "taille inconnue"


def taille_distante(url):
    """Taille d'un fichier avant de le telecharger (0 si inconnue)."""
    try:
        requete = urllib.request.Request(url, method="HEAD", headers=ENTETES)
        with urllib.request.urlopen(requete, timeout=15) as reponse:
            return int(reponse.headers.get("Content-Length", 0))
    except Exception:
        return 0


def charger_image(url):
    """Telecharge une image et la met au carre. None si impossible."""
    if not PILLOW or not url or urlparse(url).scheme != "https":
        return None
    try:
        with ouvrir_url(url) as reponse:
            donnees = reponse.read(3_000_000)
        image = Image.open(io.BytesIO(donnees)).convert("RGBA")
        return ImageOps.fit(image, (TAILLE_IMAGE, TAILLE_IMAGE))
    except Exception:
        return None


def reg(widget, **options):
    """Enregistre un widget : ses couleurs suivront le theme."""
    registre.append((widget, options))
    widget.config(**{opt: coul(cle) for opt, cle in options.items()})
    return widget


def appliquer_theme():
    registre[:] = [(w, o) for w, o in registre if w.winfo_exists()]
    for widget, options in registre:
        widget.config(**{opt: coul(cle) for opt, cle in options.items()})
    fenetre.config(bg=coul("fond"))
    bouton_theme.config(bg=coul("accent"), activebackground=coul("accent2"))
    for redessiner in redessins:
        redessiner()
    for carte in cartes:
        dessiner_vignette(carte)
        dessiner_barre(carte)


# ============================================================
# ICONES (dessinees avec des formes, aucune image a installer)
# ============================================================
def icone_releases(cv, col, fond):
    cv.create_polygon(6, 6, 17, 6, 27, 16, 17, 26, 6, 15, outline=col, fill="", width=2)
    cv.create_oval(9, 9, 13, 13, outline=col, width=2)


def icone_download(cv, col, fond):
    cv.create_line(16, 5, 16, 19, fill=col, width=3)
    cv.create_polygon(8, 15, 24, 15, 16, 24, fill=col, outline=col)
    cv.create_line(7, 28, 25, 28, fill=col, width=3)


def icone_idee(cv, col, fond):
    cv.create_oval(8, 4, 24, 20, outline=col, width=2)
    cv.create_rectangle(12, 21, 20, 25, outline=col, width=2)
    cv.create_line(13, 28, 19, 28, fill=col, width=2)


def icone_github(cv, col, fond):
    cv.create_line(9, 11, 9, 22, fill=col, width=2)
    cv.create_line(23, 13, 23, 16, 9, 21, fill=col, width=2)
    for x0, y0, x1, y1 in ((6, 5, 12, 11), (6, 22, 12, 28), (20, 7, 26, 13)):
        cv.create_oval(x0, y0, x1, y1, outline=col, fill=fond, width=2)


def icone_discord(cv, col, fond):
    cv.create_polygon(5, 9, 10, 6, 20, 6, 25, 9, 27, 20, 22, 24, 19, 21, 11, 21, 8, 24, 3, 20,
                      smooth=True, outline=col, fill="", width=2)
    cv.create_oval(10, 12, 14, 17, fill=col, outline=col)
    cv.create_oval(18, 12, 22, 17, fill=col, outline=col)


def bouton_nav(parent, texte, dessin, commande):
    """Bouton du menu lateral : icone + petit texte. Renvoie (cadre, definir_actif)."""
    cadre = tk.Frame(parent, cursor="hand2")
    cv = tk.Canvas(cadre, width=32, height=32, highlightthickness=0, cursor="hand2")
    lbl = tk.Label(cadre, text=texte, font=("Segoe UI", 8), cursor="hand2")
    cv.pack(pady=(8, 0))
    lbl.pack(pady=(0, 8))
    etat = {"actif": False, "survol": False}

    def redessiner():
        allume = etat["actif"] or etat["survol"]
        fond = coul("survol") if allume else coul("panneau")
        trait = coul("accent2") if etat["actif"] else coul("texte")
        cadre.config(bg=fond)
        cv.config(bg=fond)
        lbl.config(bg=fond, fg=coul("accent2") if etat["actif"] else coul("discret"))
        cv.delete("all")
        dessin(cv, trait, fond)

    def entrer(_):
        etat["survol"] = True
        redessiner()

    def sortir(_):
        etat["survol"] = False
        redessiner()

    for w in (cadre, cv, lbl):
        w.bind("<Button-1>", lambda e: commande())
        w.bind("<Enter>", entrer)
        w.bind("<Leave>", sortir)

    def definir_actif(valeur):
        etat["actif"] = valeur
        redessiner()

    redessins.append(redessiner)
    redessiner()
    return cadre, definir_actif


def creer_ciel(parent, fond_cle, nombre):
    """Zone remplie d'etoiles (decor de la barre laterale)."""
    cv = tk.Canvas(parent, highlightthickness=0, width=10, height=10)
    graines = [(random.random(), random.random(), random.choice([1, 1, 2])) for _ in range(nombre)]

    def redessiner(_=None):
        cv.config(bg=coul(fond_cle))
        cv.delete("etoiles")
        largeur, hauteur = cv.winfo_width(), cv.winfo_height()
        for x, y, r in graines:
            cv.create_oval(x * largeur, y * hauteur, x * largeur + r, y * hauteur + r,
                           fill=coul("etoile"), outline="", tags="etoiles")

    cv.bind("<Configure>", redessiner)
    redessins.append(redessiner)
    return cv


# ============================================================
# RELEASES
# ============================================================
def charger_releases():
    def tache():
        try:
            url = f"https://api.github.com/repos/{GITHUB_DEPOT}/releases?per_page=5"
            with ouvrir_url(url) as reponse:
                releases = json.loads(reponse.read().decode("utf-8"))
            texte = ""
            for rel in releases:
                titre = rel.get("name") or rel.get("tag_name")
                date = (rel.get("published_at") or "")[:10]
                notes = rel.get("body") or "Pas de description."
                texte += f"{titre}  ({date})\n{notes}\n\n{'-' * 40}\n\n"
            if not texte:
                texte = "Aucune mise a jour pour le moment."
        except Exception as erreur:
            texte = f"Impossible de charger les mises a jour : {erreur}"
        file_attente.put(("releases", texte))

    threading.Thread(target=tache, daemon=True).start()


# ============================================================
# DOWNLOAD : cartes de mods
# ============================================================
def charger_mods():
    global generation
    generation += 1
    gen = generation
    etat_mods.set("Chargement de la liste...")

    def tache():
        try:
            with ouvrir_url(URL_LISTE_MODS) as reponse:
                liste = json.loads(reponse.read().decode("utf-8"))
            mods = []
            for element in liste:
                url = element["url"]
                nom = Path(element["nom"]).name        # securite : juste un nom de fichier
                if urlparse(url).scheme != "https" or not nom:
                    continue
                genre = str(element.get("type", "mod")).lower()
                mods.append({"nom": nom, "url": url, "titre": element.get("titre") or nom,
                             "image": element.get("image"), "taille": 0,
                             "sous_dossier": SOUS_DOSSIERS.get(genre, "autres")})
            file_attente.put(("mods", gen, mods))
            for i, mod in enumerate(mods):
                file_attente.put(("taille", gen, i, taille_distante(mod["url"])))
                image = charger_image(mod["image"])
                if image is not None:
                    file_attente.put(("image", gen, i, image))
        except Exception as erreur:
            file_attente.put(("mods_erreur", gen, f"Impossible de charger la liste : {erreur}"))

    threading.Thread(target=tache, daemon=True).start()


def dessiner_vignette(carte):
    cv = carte["vignette"]
    cv.delete("all")
    t = TAILLE_IMAGE
    if carte.get("photo") is not None:
        cv.create_image(t / 2, t / 2, image=carte["photo"])
    else:
        cv.create_rectangle(0, 0, t, t, fill=coul("survol"), outline="")
        cv.create_text(t / 2, t / 2, text=carte["mod"]["titre"][:1].upper(),
                       fill=coul("accent2"), font=("Segoe UI", 32, "bold"))


def dessiner_barre(carte):
    cv = carte["barre"]
    cv.delete("all")
    largeur = TAILLE_IMAGE
    cv.create_rectangle(0, 0, largeur, 6, fill=coul("barre_fond"), outline="")
    cv.create_rectangle(0, 0, largeur * carte["pct"] / 100, 6, fill=coul("accent2"), outline="")


def texte_carte_pret(carte):
    taille = carte["mod"]["taille"]
    return f"{carte['mod']['sous_dossier']} - {formater_taille(taille)}"


def construire_cartes(mods):
    for enfant in grille.winfo_children():
        enfant.destroy()
    cartes.clear()
    if not mods:
        etat_mods.set("Aucun mod dans la liste.")
        return
    etat_mods.set(f"{len(mods)} fichier(s). Clique sur une image pour telecharger.")

    for i, mod in enumerate(mods):
        cadre = reg(tk.Frame(grille, cursor="hand2", padx=10, pady=10), bg="carte")
        cadre.grid(row=i // COLONNES, column=i % COLONNES, padx=8, pady=8, sticky="nsew")
        vignette = reg(tk.Canvas(cadre, width=TAILLE_IMAGE, height=TAILLE_IMAGE,
                                 highlightthickness=0, cursor="hand2"), bg="carte")
        vignette.pack()
        titre = reg(tk.Label(cadre, text=mod["titre"], font=("Segoe UI", 10, "bold"),
                             wraplength=TAILLE_IMAGE + 20, cursor="hand2"), bg="carte", fg="texte")
        titre.pack(pady=(6, 0))
        info = reg(tk.Label(cadre, text="", font=("Segoe UI", 8), wraplength=TAILLE_IMAGE + 20,
                            cursor="hand2"), bg="carte", fg="discret")
        info.pack()
        barre = reg(tk.Canvas(cadre, width=TAILLE_IMAGE, height=6, highlightthickness=0), bg="carte")
        barre.pack(pady=(6, 0))

        carte = {"mod": mod, "vignette": vignette, "info": info, "barre": barre,
                 "pct": 0, "occupe": False, "photo": None}
        cartes.append(carte)
        info.config(text=texte_carte_pret(carte))
        for w in (cadre, vignette, titre, info):
            w.bind("<Button-1>", lambda e, n=i: telecharger_mod(n))
        dessiner_vignette(carte)
        dessiner_barre(carte)

    for col in range(COLONNES):
        grille.columnconfigure(col, weight=1, uniform="col")


def telecharger_mod(i):
    if i >= len(cartes) or cartes[i]["occupe"]:
        return
    carte = cartes[i]
    carte["occupe"] = True
    carte["pct"] = 0
    dessiner_barre(carte)
    carte["info"].config(text="En attente...")
    mod = carte["mod"]
    dossier = Path(dossier_mods.get()) / mod["sous_dossier"]

    def tache():
        with limite_dl:
            try:
                dossier.mkdir(parents=True, exist_ok=True)
                temporaire = dossier / (mod["nom"] + ".part")
                debut = time.time()
                fait = 0
                with ouvrir_url(mod["url"]) as reponse, open(temporaire, "wb") as sortie:
                    total = int(reponse.headers.get("Content-Length", 0)) or mod["taille"]
                    while True:
                        bloc = reponse.read(64 * 1024)
                        if not bloc:
                            break
                        sortie.write(bloc)
                        fait += len(bloc)
                        vitesse = fait / max(time.time() - debut, 0.1)
                        if total:
                            reste = max(total - fait, 0) / vitesse
                            texte = f"{vitesse / 1e6:.1f} Mo/s - reste ~{formater_temps(reste)}"
                            file_attente.put(("mod_progres", carte, fait / total * 100, texte))
                        else:
                            file_attente.put(("mod_progres", carte, 0, f"{fait / 1e6:.1f} Mo telecharges"))
                temporaire.replace(dossier / mod["nom"])
                file_attente.put(("mod_fini", carte, True, "Telecharge !"))
            except Exception as erreur:
                file_attente.put(("mod_fini", carte, False, f"Erreur : {erreur}"))

    threading.Thread(target=tache, daemon=True).start()


def tout_telecharger():
    for i in range(len(cartes)):
        telecharger_mod(i)


def changer_dossier():
    choix = filedialog.askdirectory(title="Ou installer les fichiers ?")
    if choix:
        dossier_mods.set(choix)


# ============================================================
# IDEES
# ============================================================
derniere_idee = 0


def envoyer_idee():
    global derniere_idee
    texte = champ_idee.get("1.0", tk.END).strip()
    if len(texte) < 5:
        messagebox.showwarning("Idee", "Ecris une idee un peu plus longue.")
        return
    if time.time() - derniere_idee < 30:
        messagebox.showinfo("Idee", "Attends 30 secondes entre deux idees.")
        return
    texte = texte[:1000]
    derniere_idee = time.time()
    bouton_idee.config(state="disabled")
    etat_idee.set("Envoi...")

    def tache():
        try:
            donnees = urlencode({FORM_CHAMP: texte}).encode("utf-8")
            requete = urllib.request.Request(FORM_URL, data=donnees, headers=ENTETES)
            urllib.request.urlopen(requete, timeout=15).close()
            file_attente.put(("idee", True, "Merci, ton idee est envoyee !"))
        except Exception as erreur:
            file_attente.put(("idee", False, f"Echec de l'envoi : {erreur}"))

    threading.Thread(target=tache, daemon=True).start()


# ============================================================
# MESSAGES DES THREADS (verifies toutes les 100 ms)
# ============================================================
def traiter_file():
    try:
        while True:
            m = file_attente.get_nowait()
            try:
                traiter_message(m)
            except tk.TclError:
                pass    # le widget n'existe plus : on ignore
    except queue.Empty:
        pass
    fenetre.after(100, traiter_file)


def traiter_message(m):
    genre = m[0]
    if genre == "releases":
        zone_releases.config(state="normal")
        zone_releases.delete("1.0", tk.END)
        zone_releases.insert(tk.END, m[1])
        zone_releases.config(state="disabled")
    elif genre == "mods" and m[1] == generation:
        construire_cartes(m[2])
    elif genre == "mods_erreur" and m[1] == generation:
        etat_mods.set(m[2])
    elif genre == "taille" and m[1] == generation and m[2] < len(cartes):
        carte = cartes[m[2]]
        carte["mod"]["taille"] = m[3]
        if not carte["occupe"]:
            carte["info"].config(text=texte_carte_pret(carte))
    elif genre == "image" and m[1] == generation and m[2] < len(cartes):
        carte = cartes[m[2]]
        carte["photo"] = ImageTk.PhotoImage(m[3])
        dessiner_vignette(carte)
    elif genre == "mod_progres":
        carte = m[1]
        carte["pct"] = m[2]
        carte["info"].config(text=m[3])
        dessiner_barre(carte)
    elif genre == "mod_fini":
        carte = m[1]
        carte["occupe"] = False
        carte["pct"] = 100 if m[2] else 0
        carte["info"].config(text=m[3])
        dessiner_barre(carte)
    elif genre == "idee":
        etat_idee.set(m[2])
        if m[1]:
            champ_idee.delete("1.0", tk.END)
        bouton_idee.config(state="normal")


# ============================================================
# LA FENETRE
# ============================================================
fenetre = tk.Tk()
fenetre.title(NOM_APPLI)
fenetre.geometry("880x580")
fenetre.minsize(780, 500)

# --- Bandeau du haut (etoiles + titre + bouton de theme) ---
bandeau = tk.Canvas(fenetre, height=54, highlightthickness=0)
bandeau.pack(side="top", fill="x")
etoiles_bandeau = [(random.random(), random.random(), random.choice([1, 1, 2])) for _ in range(70)]


def basculer_theme():
    global theme_actuel
    theme_actuel = "clair" if theme_actuel == "sombre" else "sombre"
    bouton_theme.config(text="Mode sombre" if theme_actuel == "clair" else "Mode clair")
    appliquer_theme()


bouton_theme = tk.Button(bandeau, text="Mode clair", command=basculer_theme, relief="flat",
                         fg="white", activeforeground="white", padx=12, pady=4,
                         cursor="hand2", font=("Segoe UI", 9, "bold"))
item_theme = bandeau.create_window(0, 27, window=bouton_theme, anchor="e")


def redessiner_bandeau(_=None):
    bandeau.config(bg=coul("panneau"))
    bandeau.delete("deco")
    largeur = bandeau.winfo_width()
    for x, y, r in etoiles_bandeau:
        bandeau.create_oval(x * largeur, y * 54, x * largeur + r, y * 54 + r,
                            fill=coul("etoile"), outline="", tags="deco")
    bandeau.create_text(20, 27, text="\u2726 " + NOM_APPLI, anchor="w", fill=coul("texte"),
                        font=("Segoe UI", 16, "bold"), tags="deco")
    bandeau.coords(item_theme, largeur - 16, 27)


bandeau.bind("<Configure>", redessiner_bandeau)
redessins.append(redessiner_bandeau)

corps = reg(tk.Frame(fenetre), bg="fond")
corps.pack(fill="both", expand=True)

# --- Menu lateral ---
lateral = reg(tk.Frame(corps, width=92), bg="panneau")
lateral.pack(side="left", fill="y")
lateral.pack_propagate(False)

bas = reg(tk.Frame(lateral), bg="panneau")
bas.pack(side="bottom", fill="x")
haut = reg(tk.Frame(lateral), bg="panneau")
haut.pack(side="top", fill="x")

pages = {}
nav_actifs = {}


def afficher(nom):
    for page in pages.values():
        page.pack_forget()
    pages[nom].pack(fill="both", expand=True)
    for n, definir_actif in nav_actifs.items():
        definir_actif(n == nom)


for nom, texte, dessin in (("releases", "Releases", icone_releases),
                           ("download", "Download", icone_download),
                           ("idees", "Idees", icone_idee)):
    cadre_nav, definir = bouton_nav(haut, texte, dessin, lambda n=nom: afficher(n))
    cadre_nav.pack(fill="x")
    nav_actifs[nom] = definir

# GitHub et Discord : tout en bas a gauche, ils ouvrent le navigateur
cadre_dc, _ = bouton_nav(bas, "Discord", icone_discord, lambda: webbrowser.open(URL_DISCORD))
cadre_dc.pack(fill="x", side="bottom")
cadre_gh, _ = bouton_nav(bas, "GitHub", icone_github, lambda: webbrowser.open(URL_GITHUB))
cadre_gh.pack(fill="x", side="bottom")

ciel = creer_ciel(lateral, "panneau", 40)
ciel.pack(fill="both", expand=True)

contenu = reg(tk.Frame(corps), bg="fond")
contenu.pack(side="left", fill="both", expand=True)


def titre_page(parent, texte):
    return reg(tk.Label(parent, text=texte, font=("Segoe UI", 16, "bold"), anchor="w"),
               bg="fond", fg="texte")


def bouton(parent, texte, commande):
    return reg(tk.Button(parent, text=texte, command=commande, relief="flat", padx=12, pady=5,
                         cursor="hand2", font=("Segoe UI", 9, "bold"), borderwidth=0),
               bg="accent", fg="blanc", activebackground="accent2", activeforeground="blanc")


# --- Page Releases ---
page_releases = reg(tk.Frame(contenu), bg="fond")
pages["releases"] = page_releases
titre_page(page_releases, "Dernieres mises a jour").pack(fill="x", padx=20, pady=(16, 6))
bouton(page_releases, "Actualiser", charger_releases).pack(anchor="w", padx=20)
zone_releases = reg(tk.Text(page_releases, wrap="word", relief="flat", padx=12, pady=10,
                            state="disabled", font=("Segoe UI", 10)),
                    bg="carte", fg="texte", insertbackground="texte")
zone_releases.pack(fill="both", expand=True, padx=20, pady=12)

# --- Page Download ---
page_download = reg(tk.Frame(contenu), bg="fond")
pages["download"] = page_download
titre_page(page_download, "Telechargements").pack(fill="x", padx=20, pady=(16, 4))

dossier_mods = tk.StringVar(value=str(DOSSIER_PAR_DEFAUT))
ligne = reg(tk.Frame(page_download), bg="fond")
ligne.pack(fill="x", padx=20)
reg(tk.Label(ligne, textvariable=dossier_mods, anchor="w", font=("Segoe UI", 9)),
    bg="fond", fg="discret").pack(side="left")

actions = reg(tk.Frame(page_download), bg="fond")
actions.pack(fill="x", padx=20, pady=8)
bouton(actions, "Changer le dossier", changer_dossier).pack(side="left", padx=(0, 8))
bouton(actions, "Tout telecharger", tout_telecharger).pack(side="left", padx=(0, 8))
bouton(actions, "Actualiser la liste", charger_mods).pack(side="left")

etat_mods = tk.StringVar(value="")
reg(tk.Label(page_download, textvariable=etat_mods, anchor="w", font=("Segoe UI", 9)),
    bg="fond", fg="discret").pack(fill="x", padx=20)

zone_defilante = reg(tk.Canvas(page_download, highlightthickness=0), bg="fond")
defilement = tk.Scrollbar(page_download, orient="vertical", command=zone_defilante.yview)
zone_defilante.configure(yscrollcommand=defilement.set)
defilement.pack(side="right", fill="y")
zone_defilante.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=8)
grille = reg(tk.Frame(zone_defilante), bg="fond")
fenetre_grille = zone_defilante.create_window((0, 0), window=grille, anchor="nw")
grille.bind("<Configure>", lambda e: zone_defilante.configure(scrollregion=zone_defilante.bbox("all")))
zone_defilante.bind("<Configure>", lambda e: zone_defilante.itemconfig(fenetre_grille, width=e.width))
zone_defilante.bind_all("<MouseWheel>", lambda e: zone_defilante.yview_scroll(int(-e.delta / 120), "units"))

# --- Page Idees ---
page_idees = reg(tk.Frame(contenu), bg="fond")
pages["idees"] = page_idees
titre_page(page_idees, "Une idee ?").pack(fill="x", padx=20, pady=(16, 4))
reg(tk.Label(page_idees, text="Dis-moi ce que je pourrais ameliorer :", anchor="w",
             font=("Segoe UI", 10)), bg="fond", fg="discret").pack(fill="x", padx=20)
champ_idee = reg(tk.Text(page_idees, height=9, wrap="word", relief="flat", padx=12, pady=10,
                         font=("Segoe UI", 10)), bg="carte", fg="texte", insertbackground="texte")
champ_idee.pack(fill="x", padx=20, pady=12)
bouton_idee = bouton(page_idees, "Envoyer mon idee", envoyer_idee)
bouton_idee.pack(anchor="w", padx=20)
etat_idee = tk.StringVar()
reg(tk.Label(page_idees, textvariable=etat_idee, anchor="w", font=("Segoe UI", 9)),
    bg="fond", fg="discret").pack(fill="x", padx=20, pady=8)

# --- Demarrage ---
appliquer_theme()
afficher("download")
charger_releases()
charger_mods()
traiter_file()
fenetre.mainloop()
