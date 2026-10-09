# OverLoad — atelier média local

OverLoad prépare les médias téléchargés avant le montage : organisation par projet, détection des conteneurs et codecs, contrôle de lisibilité, diagnostic de compatibilité prudent et conversion facultative vers MP4 H.264/AAC.

> **État de cette base :** le dépôt ne contenait que son README initial — aucun téléchargeur ni intégration existante. Le bouton **Télécharger et importer** ouvre donc le sélecteur de fichiers et importe une copie locale déjà téléchargée. Il ne récupère pas encore de média depuis une URL ou un service. Le raccordement au moteur de téléchargement devra se faire lorsque son code et ses sources seront disponibles.

## Démarrage

Prérequis : Python 3.10 ou supérieur. L'interface et l'API n'utilisent que la bibliothèque standard Python.

```bash
python -m overload
```

OverLoad ouvre son interface dans le navigateur, sur `http://127.0.0.1:8765`. Pour choisir un port ou un dossier de données :

```bash
python -m overload serve --port 9000 --data-dir ~/Videos/OverLoad
```

Pour un lancement sans navigateur :

```bash
python -m overload serve --no-browser
```

Les projets sont enregistrés dans `~/.overload/projects` par défaut. `OVERLOAD_HOME` permet de remplacer cet emplacement. Les fichiers choisis dans le navigateur sont **copiés** dans le projet OverLoad ; le fichier source de l'utilisateur n'est ni déplacé ni supprimé.

## FFmpeg et FFprobe

Installe une distribution FFmpeg contenant **ffmpeg** et **ffprobe** et rends les deux exécutables accessibles dans le `PATH`. Sans FFprobe, OverLoad conserve les fichiers mais les marque **non vérifiés** ; il ne prétend pas connaître leurs codecs. Sans FFmpeg, l'analyse des métadonnées peut fonctionner avec FFprobe, mais le décodage intégral et la conversion ne sont pas disponibles.

Les chemins peuvent être définis explicitement avec `OVERLOAD_FFMPEG` et `OVERLOAD_FFPROBE`. La page d'accueil affiche l'état de ces outils.

Un import vérifie d'abord la taille reçue lorsque celle du fichier source est connue et lit les métadonnées avec FFprobe. Si FFmpeg est disponible, OverLoad tente aussi de décoder les flux audio et vidéo jusqu'au bout. Une vérification complète peut donc prendre du temps ; l'interface n'affiche pas le média comme intégralement vérifié avant sa fin. Les avertissements de compatibilité codec ne sont pas confondus avec les erreurs d'intégrité.

## Fonctions incluses

- Conteneurs et flux vidéo/audio : MP4, WebM, MKV, MOV et autres formats reconnus par FFprobe ; codec, durée, dimensions, cadence, nombre de pistes audio.
- Diagnostic séparé pour média lisible, codec à risque, taille incomplète, flux indécodables et absence d'outils.
- Classement automatique dans `Media/Video`, `Media/Audio`, `Media/Images` ou `Needs review`.
- Profil facultatif **MP4 H.264/AAC** dans `Converted`. Les médias déjà compatibles peuvent être remultiplexés/copier les flux ; sinon FFmpeg réencode. L'original reste intact, la résolution n'est pas réduite et la cadence n'est pas forcée par une option de sortie.
- Progression, estimation du temps restant lorsque FFmpeg la fournit et annulation des tâches de conversion.
- Ouverture du fichier par l'application système, ouverture du dossier de projet et lancement best-effort dans Premiere Pro, DaVinci Resolve ou CapCut lorsque l'application est détectée.
- Une structure de projet commune, indépendante du logiciel de montage, et un manifeste JSON local.

## Limites importantes

- Le diagnostic de compatibilité est volontairement conservateur : la prise en charge exacte dépend de la version, du système d'exploitation et des extensions installées. OverLoad n'interroge pas encore la version précise de Premiere Pro/Resolve/CapCut.
- « Ouvrir dans un logiciel » lance l'application avec le fichier en argument lorsque possible. L'import dans un projet ou une timeline n'est pas garanti par une interface de ligne de commande commune ; l'utilisateur peut devoir confirmer l'import dans l'application.
- Cette version importe des fichiers locaux déjà téléchargés ; elle ne surveille pas un dossier de téléchargement et ne contient pas de fournisseur/téléchargeur média.
- Les médias sont copiés dans le dossier de données OverLoad ; prévois l'espace disque nécessaire aux originaux et aux versions converties.
- Le serveur écoute sur `127.0.0.1` par défaut et vérifie l'en-tête `Host` pour limiter les requêtes par rebinding DNS. Les hôtes locaux et le domaine de prévisualisation Arena (`*.e2b.app`) sont autorisés ; pour un proxy inverse de confiance, configure `OVERLOAD_ALLOWED_HOSTS`. Ne l'expose pas sur un réseau public sans ajouter une authentification et une politique d'accès adaptées.

## CLI

Inspecter un média et imprimer le rapport JSON :

```bash
python -m overload inspect "clip.mp4" --editor premiere
python -m overload inspect "clip.webm" --editor resolve --expected-size 28400123
python -m overload inspect "clip.mov" --metadata-only
```

Les codes de sortie de `inspect` sont `0` pour un fichier vérifié/lisible et `1` lorsqu'il est incomplet, corrompu ou non vérifié. `--metadata-only` évite le décodage intégral.

## Développement et tests

```bash
python -m unittest discover -s tests -v
```

Les tests unitaires simulent FFprobe/FFmpeg et n'exigent pas leur installation. Un test d'intégration réel (dimensions, cadence, taille et SSIM) s'exécute si FFmpeg dispose de `libx264` et du filtre `ssim`, sinon il est ignoré. Les essais avec plusieurs versions de logiciels de montage restent à effectuer sur les systèmes cibles.

Voir [`docs/ROADMAP.md`](docs/ROADMAP.md) pour le découpage d'implémentation et les validations prévues.
<p align="center">
  <img src="assets/logo/logo-256.png" width="120" alt="Logo OverLoad">
</p>

<h1 align="center">OverLoad</h1>
<p align="center"><b>Fast downloads. Smooth workflow. Built for editors.</b></p>

<p align="center">
  <a href="https://github.com/TOFazer/OverLoad/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/TOFazer/OverLoad?color=8b5cf6"></a>
  <a href="https://github.com/TOFazer/OverLoad/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/TOFazer/OverLoad/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%7C%2011-3b82f6">
  <img alt="Licence" src="https://img.shields.io/badge/licence-MIT-22c55e">
</p>

OverLoad est une application Windows qui sert à préparer, lancer et organiser les téléchargements de vidéos
(YouTube, Vimeo et [plus de 1 000 sources](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md))
pour le montage, sans garder dix onglets ouverts dans le navigateur.

![Accueil](docs/screenshots/home.png)

## ✨ Fonctionnalités

| | |
|---|---|
| ⚡ **Rapidité** | Fragments parallèles (connexions **adaptées à la taille du fichier**), plusieurs téléchargements en même temps, vitesse réelle en Mo/s et graphique en direct |
| 🎬 **Pour les monteurs** | Un **dossier par projet**, classement par projet ou par source, MP4 H.264 compatible avec Premiere Pro, DaVinci Resolve et Final Cut, WAV sans perte |
| 📚 **En lot** | Colle plusieurs liens d'un coup (un par ligne) : ils partent tous dans la file |
| 📂 **Prêt pour le montage** | Bibliothèque consultable par recherche : résolution, images/s, codecs, taille ; ouvrir le fichier ou son dossier |
| 🔁 **Fiable** | Reprise des téléchargements interrompus (même après une fermeture de l'app), nouvelles tentatives automatiques, vérification d'intégrité et empreinte SHA-256 |
| 🛡️ **Sûr** | Liens filtrés (http/https publics uniquement), noms de fichiers assainis, mises à jour vérifiées via les Releases GitHub officielles |
| 🎨 **Agréable** | Thème sombre ou clair, français ou anglais, notifications, aucune publicité |

<p>
  <img src="docs/screenshots/downloads.png" width="49%" alt="Téléchargements">
  <img src="docs/screenshots/library.png" width="49%" alt="Bibliothèque">
</p>

## 📥 Installation

1. Ouvre la [dernière release](https://github.com/TOFazer/OverLoad/releases/latest).
2. Télécharge **`OverLoad-Setup-x.y.z.exe`**. Une version portable `.zip` est aussi disponible.
3. *(Recommandé)* Vérifie l'empreinte du fichier avec `SHA256SUMS.txt` :
   ```powershell
   Get-FileHash .\OverLoad-Setup-1.0.0.exe -Algorithm SHA256
   ```
4. Lance l'installateur ; tu peux choisir de créer un raccourci sur le bureau.

> Tant que l'exe n'est pas signé numériquement, Windows SmartScreen peut afficher un avertissement :
> clique sur **Informations complémentaires**, puis sur **Exécuter quand même**.

Tes paramètres, ton historique et ta file d'attente sont enregistrés dans `%APPDATA%\OverLoad`. Ils sont **conservés lors des mises à jour**.

## ⚡ À propos de la vitesse

OverLoad utilise le moteur [yt-dlp](https://github.com/yt-dlp/yt-dlp) et cherche à **tirer le meilleur parti de ta connexion**
(connexions parallèles quand la source les autorise, file intelligente, reprise). En revanche, **aucune application ne
peut garantir une vitesse supérieure sur toutes les plateformes** : le serveur, ta connexion et les limites imposées par la source
comptent autant que le logiciel.

Pour mesurer toi-même la vitesse obtenue (médiane sur plusieurs essais, par nombre de connexions) :

```bash
python scripts/benchmark.py "https://lien-de-test" --connections 1 4 8 --runs 3
```

Le script produit un rapport Markdown et un fichier CSV : **seules des mesures réelles sont publiées**.

## 🛠️ Développement

```bash
git clone https://github.com/TOFazer/OverLoad && cd OverLoad
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py          # lancer l'app
python -m pytest        # 34 tests (dont de vrais téléchargements en local)
build.bat               # exe + installateur (Inno Setup requis pour l'installateur)
```

```
OverLoad/
├── main.py                  # point d'entrée
├── version.py
├── ui/                      # interface PySide6
│   ├── main_window.py       # barre latérale + navigation
│   ├── home_page.py         # coller / analyser / télécharger
│   ├── downloads_page.py    # file, progression, graphique de vitesse
│   ├── projects_page.py     # Mode Monteur
│   ├── history_page.py      # bibliothèque
│   ├── settings_page.py
│   ├── speed_graph.py, theme.py, common.py
├── core/
│   ├── url_analyzer.py      # validation, qualités, tailles, infos techniques
│   ├── download_manager.py  # moteur yt-dlp, connexions adaptatives, intégrité
│   └── queue_manager.py     # simultanés, doublons, reprise
├── services/                # paramètres, historique, i18n, mises à jour
├── assets/                  # logo et icônes
├── installer/               # Inno Setup
├── scripts/benchmark.py
└── tests/
```

**Publier une version :** modifie `version.py` et `CHANGELOG.md`, puis
`git tag v1.0.0 && git push --tags`. GitHub Actions teste, construit l'installateur et la version portable,
calcule les empreintes SHA-256 et publie la release.

## ⚖️ Usage responsable

Télécharge uniquement des contenus dont tu détiens les droits, qui sont sous licence libre, ou pour lesquels tu as
l'autorisation de l'auteur. Respecte les conditions d'utilisation de chaque plateforme.

## 🤝 Contribuer

Les retours et contributions sont les bienvenus : voir [CONTRIBUTING.md](CONTRIBUTING.md) et la [roadmap](ROADMAP.md).
Tu as trouvé un bug ? Ouvre une [issue](https://github.com/TOFazer/OverLoad/issues).

## Licence

[MIT](LICENSE). OverLoad s'appuie sur [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), [PySide6](https://doc.qt.io/qtforpython/) (LGPL) et [FFmpeg](https://ffmpeg.org) (LGPL/GPL, via imageio-ffmpeg).
