# NXT — Onboarding Bootcamp

Application d’onboarding en français, réalisée en HTML, CSS, JavaScript, JSON et Python, sans dépendance externe.

Un participant saisit son code d’invitation, complète un questionnaire à réponses libres, puis découvre la présentation du bootcamp. Ses réponses peuvent être sauvegardées et reprises plus tard. Un espace administrateur permet de consulter les candidatures reçues.

## Fonctionnalités

- Page d’accès séparée avec validation d’un code d’invitation.
- Questionnaire vertical et scrollable, généré depuis un fichier JSON.
- Questions, explications et contraintes modifiables sans toucher au HTML.
- Sauvegarde d’un brouillon associé au code du participant.
- Restauration automatique du brouillon lors de la prochaine connexion.
- Enregistrement définitif des réponses avant la redirection vers la présentation du bootcamp.
- Espace administrateur protégé par mot de passe.
- Recherche et consultation des réponses par identifiant ou code d’invitation.
- Couleurs centralisées sous forme de tokens CSS.

## Prérequis

- Python 3.10 ou une version plus récente.
- Un navigateur web récent.

Aucune installation de paquet n’est nécessaire.

## Démarrage

Lors de la première installation, crée ton fichier local de codes d’accès à partir de l’exemple :

```bash
cp access_codes.example.json access_codes.json
```

Modifie ensuite les codes dans `access_codes.json`, puis démarre le serveur depuis le dossier du projet :

```bash
python3 server.py
```

Ouvre ensuite :

- Site participant : [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Administration : [http://127.0.0.1:8000/admin.html](http://127.0.0.1:8000/admin.html)

Pour utiliser un autre port :

```bash
NXT_PORT=8765 python3 server.py
```

Il faut passer par le serveur Python. Ouvrir directement les fichiers HTML empêche le chargement des questions, la validation des codes et la sauvegarde des réponses.

## Parcours participant

1. Le participant saisit un code valide sur la page d’accueil.
2. Il est redirigé vers `questionnaire.html`.
3. Les questions sont affichées les unes à la suite des autres sur une seule page scrollable.
4. Il peut sauvegarder ses réponses et revenir plus tard avec le même code.
5. Lors de l’envoi définitif, les réponses sont enregistrées et le brouillon est supprimé.
6. Le participant est redirigé vers `experience.html`.

## Créer des codes d’accès

Les codes autorisés se trouvent dans le fichier local `access_codes.json`. Ajoute simplement une valeur au tableau `codes` :

```json
{
  "codes": [
    "NXT-2026",
    "BOOTCAMP-VIP",
    "NOUVEL-INVITE"
  ]
}
```

Le serveur relit ce fichier à chaque tentative. Il n’est donc pas nécessaire de le redémarrer après l’ajout d’un code.

Le fichier contenant les vrais codes est exclu de Git afin de ne pas publier les accès des participants. Le dépôt contient uniquement `access_codes.example.json`, que tu peux copier lors d’une nouvelle installation.

Chaque participant devrait recevoir un code unique : les brouillons et les réponses sont associés au code utilisé. La saisie n’est pas sensible aux majuscules et les espaces placés avant ou après le code sont ignorés.

### Attention à la syntaxe JSON

Chaque code doit être suivi d’une virgule, sauf le dernier. Les commentaires et les virgules après la dernière valeur ne sont pas autorisés.

Pour vérifier le fichier avant de tester un nouveau code :

```bash
python3 -m json.tool access_codes.json
```

Si cette commande affiche une erreur, le site refusera les codes jusqu’à la correction du fichier.

## Modifier les questions

Toutes les questions sont définies dans `questions.json`. Il est possible de les ajouter, supprimer, réordonner ou modifier directement dans ce fichier.

Exemple :

```json
{
  "id": "presentation",
  "title": "Présente-toi",
  "helper": "Parle-nous brièvement de ton parcours et de ce qui t’anime aujourd’hui.",
  "placeholder": "Ton parcours, tes expériences, tes motivations…",
  "required": true,
  "minLength": 10,
  "maxLength": 1200
}
```

Propriétés disponibles :

| Propriété | Rôle |
| --- | --- |
| `id` | Identifiant unique et stable de la question. |
| `title` | Question affichée au participant. |
| `helper` | Courte explication affichée sous la question. |
| `placeholder` | Exemple discret affiché dans la zone de réponse. |
| `required` | Indique si la réponse est obligatoire. |
| `minLength` | Nombre minimal de caractères attendu. |
| `maxLength` | Nombre maximal de caractères autorisé. |

Le champ `id` doit rester unique. Évite de le modifier après avoir reçu des réponses, car il sert à relier les réponses enregistrées à leur question.

## Sauvegarde des données

Les données sont conservées localement dans deux fichiers, créés automatiquement si nécessaire :

- `drafts.json` contient les brouillons, associés au code d’invitation.
- `responses.json` contient les réponses envoyées définitivement, avec leur identifiant, leur code et leur date.

La sauvegarde d’un nouveau brouillon avec le même code met à jour le brouillon existant. L’envoi définitif crée une soumission, puis supprime ce brouillon.

Pour conserver les données, sauvegarde régulièrement ces deux fichiers. Évite de les modifier manuellement pendant que le serveur est en train d’enregistrer une réponse.

Ces fichiers sont exclus de Git pour empêcher la publication des réponses des participants.

## Administration

L’espace administrateur est accessible à l’adresse :

[http://127.0.0.1:8000/admin.html](http://127.0.0.1:8000/admin.html)

Le mot de passe initial est :

```text
NXT-ADMIN-2026
```

Pour définir ton propre mot de passe au démarrage :

```bash
NXT_ADMIN_PASSWORD="un-mot-de-passe-long-et-unique" python3 server.py
```

Ce réglage remplace le mot de passe par défaut sans modifier les fichiers du projet. La session administrateur expire automatiquement après deux heures.

Change impérativement le mot de passe initial avant toute utilisation avec de vraies données. L’interface d’administration est prévue pour la consultation : elle ne modifie pas les réponses.

## Personnaliser les couleurs

Toutes les couleurs principales sont regroupées en haut de `styles.css` sous forme de variables `--color-*` :

```css
:root {
  --color-background: #08090c;
  --color-text: #f5f3ee;
  --color-accent: #e50914;
}
```

Modifier ces tokens permet de faire évoluer rapidement l’identité visuelle sans rechercher chaque couleur dans la feuille de styles.

## Configuration du serveur

Les variables d’environnement disponibles sont :

| Variable | Valeur par défaut | Usage |
| --- | --- | --- |
| `NXT_HOST` | `127.0.0.1` | Adresse d’écoute du serveur. |
| `NXT_PORT` | `8000` | Port HTTP utilisé. |
| `NXT_ADMIN_PASSWORD` | Mot de passe configuré localement | Remplace le mot de passe administrateur. |
| `NXT_SERVER_SECRET` | Secret généré au démarrage | Signe les sessions administrateur. |

Pour conserver les sessions administrateur après un redémarrage, définis un secret long et aléatoire :

```bash
NXT_SERVER_SECRET="un-secret-long-et-aleatoire" python3 server.py
```

## Structure du projet

| Fichier | Description |
| --- | --- |
| `index.html` | Page d’accès participant. |
| `questionnaire.html` | Questionnaire scrollable. |
| `experience.html` | Présentation du bootcamp après l’envoi. |
| `admin.html` | Connexion et consultation administrateur. |
| `styles.css` | Styles du site et tokens de couleur. |
| `app.js` | Accès participant, questionnaire et sauvegarde. |
| `admin.js` | Connexion et affichage des réponses côté administrateur. |
| `questions.json` | Questions et explications du questionnaire. |
| `access_codes.example.json` | Modèle public de configuration des codes. |
| `access_codes.json` | Codes d’invitation locaux, non publiés dans Git. |
| `drafts.json` | Brouillons locaux des participants, non publiés dans Git. |
| `responses.json` | Soumissions définitives locales, non publiées dans Git. |
| `admin_config.json` | Configuration sécurisée du mot de passe administrateur. |
| `server.py` | Serveur web, validation et persistance des données. |

## Dépannage

### Un code valide est refusé

Vérifie d’abord la syntaxe de `access_codes.json` :

```bash
python3 -m json.tool access_codes.json
```

Vérifie ensuite que le code se trouve bien entre guillemets et que les valeurs sont séparées par des virgules.

### Le site ne charge pas les questions

Assure-toi que `server.py` est en cours d’exécution et que le site est ouvert avec une adresse commençant par `http://127.0.0.1:`.

### Le port est déjà utilisé

Démarre le serveur sur un autre port :

```bash
NXT_PORT=8765 python3 server.py
```

## Mise en production

Le serveur Python intégré convient à une utilisation locale, une démonstration ou un prototype interne. Pour exposer le site publiquement, prévois au minimum HTTPS, un hébergement persistant, des sauvegardes, un mot de passe administrateur fort et une solution de stockage adaptée à plusieurs utilisateurs simultanés.
