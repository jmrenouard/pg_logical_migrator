![pg_logical_migrator](../pg_logical_migrator.jpg)

# Utiliser Docker avec pg_logical_migrator

L'utilisation de Docker est le moyen le plus simple et le plus sûr d'exécuter `pg_logical_migrator` sans avoir à installer Python, Git, PostgreSQL client ou d'autres dépendances directement sur votre machine hôte.

Ce document décrit comment construire l'image Docker de l'outil puis comment s'en servir pour exécuter des migrations interactives ou automatisées.

---

## 1. Pourquoi utiliser Docker ?

- **Portabilité complète** : Le conteneur inclut toutes les bibliothèques Python nécessaires (`psycopg`, `textual`, `rich`, etc.) ainsi que les binaires clients de PostgreSQL (`pg_dump`, `psql`).
- **Isolation** : L'exécution n'affecte pas environnement Python de l'hôte.
- **Déploiement simple** : Dans un cadre CI/CD, l'image Docker peut être utilisée comme étape automatisée du pipeline de migration.

---

## 2. Construction de l'image (Build)

Pour compiler l'image Docker, exécutez la commande suivante à la racine du dépôt (où se trouve le fichier `Dockerfile`) :

```bash
docker build -t pg_logical_migrator .
```

Cela créera une image Docker nommée `pg_logical_migrator` prête à l'emploi.

---

## 3. Configuration

L'image est construite avec le fichier d'exemple `config_migrator.sample.ini` renommé en `config_migrator.ini` dans le répertoire de travail (`/app`).

Pour que vos propres identifiants soient pris en compte à l'exécution, vous devez monter votre propre fichier `config_migrator.ini` en tant que volume à l'intérieur du conteneur.

Assurez-vous d'avoir créé au préalable un fichier de configuration valide :

```bash
cp config_migrator.sample.ini config_migrator.ini
# Éditez ensuite le fichier pour indiquer vos accès source et destination
```

Il est aussi recommandé de monter le répertoire `RESULTS` de l'hôte afin de pouvoir facilement récupérer les rapports HTML et logs générés par l'outil.

---

## 4. Exécuter le conteneur

L'image exécute par défaut le script CLI complet (`pg_migrator.py`). Il faut donc passer le nom de la commande (comme `check`, `tui` ou `auto`) à la fin du `docker run`.

Voici un bloc d'exécution type pour une exécution **interactive (TUI)** :

```bash
docker run -it --rm \
  -v $(pwd)/config_migrator.ini:/app/config_migrator.ini \
  -v $(pwd)/RESULTS:/app/RESULTS \
  pg_logical_migrator tui
```

### Options expliquées

- `-it` : Permet l'interactivité. Indispensable pour la TUI (Terminal UI) ou pour voir les résultats de ligne de commande proprement formatés.
- `--rm` : Supprime le conteneur dès qu'il s'arrête.
- `-v $(pwd)/config_migrator.ini:/app/config_migrator.ini` : Monte votre fichier de configuration local à la configuration attendue par le programme.
- `-v $(pwd)/RESULTS:/app/RESULTS` : Synchronise les journaux et les rapports HTML générés pendant la migration vers votre machine.

---

## 5. Exemples de commandes

Toutes les commandes documentées dans [TOOLS.md](TOOLS.md) peuvent être appelées après le nom de l'image.

**Tester la connexion (Step 1)** :

```bash
docker run -it --rm \
  -v $(pwd)/config_migrator.ini:/app/config_migrator.ini \
  pg_logical_migrator check
```

**Lancer le diagnostic pré-migration (Step 2)** :

```bash
docker run -it --rm \
  -v $(pwd)/config_migrator.ini:/app/config_migrator.ini \
  pg_logical_migrator diagnose
```

**Lancer la migration automatisée** :

```bash
docker run -it --rm \
  -v $(pwd)/config_migrator.ini:/app/config_migrator.ini \
  -v $(pwd)/RESULTS:/app/RESULTS \
  pg_logical_migrator auto
```

*(Dans le cadre d'un système CI/CD automatisé, l'option `-it` n'est pas nécessaire).*
