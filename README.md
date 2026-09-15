# NXT — Onboarding Bootcamp

Application d’onboarding en français déployable sur Vercel. Le frontend est en HTML, CSS et JavaScript, les questions restent dans un fichier JSON, l’API est écrite en Python et les données persistantes sont stockées dans PostgreSQL avec Neon.

## Fonctionnalités

- Accès participant avec un code d’invitation.
- Collecte du nom, du prénom, du téléphone et de l’email avant le questionnaire.
- Questionnaire vertical à réponses libres, généré depuis `questions.json`.
- Sauvegarde et restauration des brouillons par code.
- Enregistrement définitif des réponses dans PostgreSQL.
- Espace administrateur protégé par un mot de passe fort.
- Consultation et recherche des soumissions par identifiant ou code.
- Déploiements automatiques Vercel depuis la branche `main`.

## Architecture

| Élément | Technologie |
| --- | --- |
| Pages | HTML |
| Styles | CSS avec tokens `--color-*` |
| Interactions | JavaScript natif |
| Questions | `questions.json` |
| API | Fonction Python Vercel |
| Données | PostgreSQL avec Neon |
| Hébergement | Vercel |

## Prérequis

- Python 3.12.
- Vercel CLI.
- Un projet Vercel lié à une base Neon.

## Installation locale

Le projet est déjà lié à Vercel. Pour une nouvelle installation :

```bash
vercel link
vercel env pull .env.local --yes
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Le fichier `.env.local` doit contenir ces trois variables :

```text
DATABASE_URL
NXT_ADMIN_PASSWORD
NXT_SERVER_SECRET
```

Leurs valeurs ne doivent jamais être ajoutées à Git.

## Démarrage local

```bash
vercel dev
```

Le CLI indique l’adresse locale à ouvrir. L’accueil et l’administration sont ensuite disponibles aux adresses suivantes :

- `/`
- `/admin.html`

## Modifier les questions

Les questions sont définies dans `questions.json`. Elles peuvent être ajoutées, supprimées, réordonnées ou modifiées directement.

```json
{
  "id": "presentation",
  "title": "Présente-toi",
  "helper": "Parle-nous brièvement de ton parcours.",
  "placeholder": "Je suis…",
  "required": true
}
```

Le champ `id` doit être unique et stable. Les réponses ne possèdent aucune limite minimale ou maximale ; une question obligatoire doit simplement contenir un texte non vide.

## Créer un code d’accès

Le moyen le plus simple est d’ouvrir `/admin.html`, puis d’utiliser la section **Codes d’accès**. Elle permet de créer un code personnalisé de 1 à 6 lettres, d’en générer un aléatoirement et d’activer ou désactiver les codes existants. Les changements sont immédiats et ne demandent aucun redéploiement.

Depuis le terminal, il reste également possible d’ajouter un code directement dans Neon :

Depuis le dossier du projet :

```bash
.venv/bin/python db/add_code.py "NOUVEAU-CODE"
```

Le code est normalisé en majuscules, enregistré dans Neon et utilisable immédiatement, sans redéploiement.

Il est également possible d’exécuter cette requête dans l’éditeur SQL de Neon :

```sql
INSERT INTO access_codes (code, active)
VALUES (UPPER('NOUVEAU-CODE'), TRUE)
ON CONFLICT (code) DO UPDATE SET active = TRUE;
```

Chaque participant devrait recevoir son propre code, car les brouillons et les soumissions y sont associés.

## Base de données

Le schéma se trouve dans `db/schema.sql`. Il contient :

- `access_codes` pour les invitations ;
- `participants` pour les coordonnées associées à chaque code ;
- `drafts` pour les sauvegardes temporaires ;
- `submissions` pour les réponses définitives.

Pour créer ou mettre à jour les tables et importer les anciens fichiers JSON locaux :

```bash
.venv/bin/python db/migrate.py
```

La migration est réexécutable : les codes sont mis à jour et les soumissions déjà présentes ne sont pas dupliquées.

## Administration

L’administration est disponible sur `/admin.html`. Elle regroupe la gestion des codes d’accès et la consultation des réponses. Le mot de passe est la valeur de `NXT_ADMIN_PASSWORD`.

Sur la machine ayant servi à configurer le projet, cette valeur se trouve uniquement dans `.env.local`, qui est ignoré par Git. Pour la modifier :

```bash
vercel env update NXT_ADMIN_PASSWORD production
vercel env update NXT_ADMIN_PASSWORD preview
vercel env update NXT_ADMIN_PASSWORD development
vercel env pull .env.local --yes
```

La session administrateur expire après deux heures. Les sessions participant expirent après quatre heures.

## Déploiement Vercel

### Déploiement automatique

Une fois le dépôt GitHub connecté au projet Vercel, chaque push sur `main` crée un déploiement de production.

### Déploiement manuel

```bash
vercel --prod
```

Les variables `DATABASE_URL`, `NXT_ADMIN_PASSWORD` et `NXT_SERVER_SECRET` doivent être configurées pour Production, Preview et Development avant le déploiement.

## Fichiers principaux

| Fichier | Description |
| --- | --- |
| `index.html` | Accès participant. |
| `profile.html` | Coordonnées du participant. |
| `questionnaire.html` | Questionnaire scrollable. |
| `experience.html` | Présentation après l’envoi. |
| `admin.html` | Administration. |
| `styles.css` | Styles et tokens de couleur. |
| `app.js` | Parcours participant. |
| `admin.js` | Consultation administrateur. |
| `questions.json` | Questions et explications. |
| `api/index.py` | API Python serverless. |
| `db/schema.sql` | Schéma PostgreSQL. |
| `db/migrate.py` | Migration des données locales. |
| `db/add_code.py` | Ajout d’un code d’accès. |
| `vercel.json` | Routes, fonction et en-têtes Vercel. |
| `requirements.txt` | Dépendances Python. |
| `pyproject.toml` | Configuration Python utilisée par Vercel. |
| `uv.lock` | Versions reproductibles des dépendances. |

## Données privées

Les fichiers et dossiers suivants sont exclus de Git et/ou du déploiement :

- `.env.local` ;
- `.vercel/` ;
- `access_codes.json` ;
- `drafts.json` ;
- `responses.json`.

Les codes et réponses de production résident exclusivement dans Neon.
