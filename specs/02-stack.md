# Urban Track: Spécification technique (stack)

## 1. Vue d'ensemble
- **Backend** : Python / Django (monolithe modulaire, ORM natif adapté au modèle de données relationnel du projet)
- **Frontend** : Django Templates + **Tailwind CSS** (server-rendered, progressive enhancement via Alpine.js ou HTMX pour l'interactivité légère: formulaire de contributeurs dynamique, confirmation en un clic)
- **Base de données** : SQLite (données utilisateurs, projets, contributions: relationnel, intégrité forte requise pour la certification)
- **Génération de documents** : WeasyPrint (à intégrer dès le départ, rien n'est en place) pour les CV PDF multi-templates
- **Tâches asynchrones / planifiées** : Celery + Celery Beat (ou cron) + Redis comme broker, pour les relances automatiques et l'expiration des invitations
- **Email transactionnel** : SendGrid, Mailgun ou Amazon SES (à trancher), avec suivi ouverture/clic
- **Authentification** : Django auth étendu, + flux "lien magique" (token UUID4, ou `itsdangerous`) pour l'inscription contextualisée sans mot de passe au premier clic
- **API** : Django REST Framework, architecture API-first pour permettre les connecteurs externes (Banque Mondiale, AFD et autres partenaires stratégiques)
- **OXID / ID unique** : chaque expert a un identifiant unique et permanent, utilisé pour le dédoublonnage et la traçabilité des contributions certifiées (OX-XXXXXX)

## 2. Identité visuelle: Design system Tailwind

### 2.1 Palette de couleurs
| Rôle | Nom du token | Usage |
|---|---|---|
| Primaire / base | `military` (vert militaire, ex. `#4B5320` à `#5C6B2F` selon nuance retenue) | Headers, navigation, boutons primaires, badges "Certifié" |
| Accent | `pink` (ex. `#EC4899` / à ajuster) | Call-to-action, liens de confirmation, notifications, éléments interactifs |
| Neutre clair | `white` (`#FFFFFF`) | Fonds, cartes, espaces négatifs |
| Neutre foncé | `charcoal` / `black-gray` (ex. `#1F2320` à `#2B2E2C`) | Texte principal, footer, contrastes forts |

Configuration `tailwind.config.js` (extrait) :
```js
theme: {
  extend: {
    colors: {
      military: {
        50: '#f2f4ec', 100: '#e1e6cf', 300: '#a9b57a',
        500: '#5c6b2f', 700: '#3f4a20', 900: '#2a3116',
      },
      accent: {
        50: '#fdf2f8', 300: '#f9a8d4', 500: '#ec4899',
        700: '#be185d',
      },
      charcoal: {
        50: '#f5f5f4', 300: '#a8a8a6', 700: '#3f3f3e', 900: '#1c1c1b',
      },
    },
  },
},
```

### 2.2 Principes d'usage
- Vert militaire = confiance institutionnelle (dominante, 60–70 % des surfaces)
- Rose = actions et statuts vivants (boutons "Confirmer", badges "En attente", notifications): utilisé avec parcimonie pour ne pas diluer son effet d'attention
- Blanc / gris anthracite = lisibilité, structure, hiérarchie typographique
- Deux badges (pas de flux historique à distinguer, projet greenfield) : "Certifié via confirmation croisée" (vert + icône check) et "En attente de confirmation" (rose/orange neutre)

## 3. Modèle de données (Django): composants clés
- `Project` (nouveau, à créer) : `official_name`, `description`, `deliverables`, `duration_start/end`, `budget`, `client_name`, `status` (Draft/Published/Archived), `visibility` (Public/Privé)
- `ProjectContribution` (nouveau: cœur du système) : `project` (FK), `expert` (FK nullable), `invited_email`, `role_type` (Directeur/Manager/Assistant/Spécialiste), `contribution_bullets`, `status` (invited → pending_confirmation → confirmed/rejected/disputed), `added_by` (FK User entreprise), `confirmed_at`
- `ExpertInvitation` (nouveau) : `contribution` (FK), `email`, `token` (UUID unique), `sent_at`, `expires_at` (~14 jours), `status` (sent/opened/converted/expired), `reminder_count`
- `CVTemplate` (config) : templates pluggables `templates/cv/world_bank.html`, `templates/cv/afd.html`, `templates/cv/academic_harvard_mit.html`, alimentés par la même source de données (profil + contributions certifiées), champ `cv_template` sur le générateur, rendu bilingue FR/EN dupliqué par template

## 4. Composants techniques à développer
1. Service d'email transactionnel fiable avec suivi d'ouverture/clic
2. Système de lien magique / token sécurisé (uuid4 + expiration)
3. Formulaire "Publier un projet" côté entreprise, avec ajout dynamique de contributeurs (recherche autocomplete d'experts existants + ajout par email)
4. Page de confirmation côté expert (3 actions : confirmer / ajuster / refuser), avec inscription intégrée si non-inscrit
5. Dédoublonnage automatique par email lors de la liaison à un compte existant
6. Tâches planifiées Celery pour relances (max 2) et expiration des invitations
7. Système de templates CV pluggables (un moteur, plusieurs skins)
8. API-first (DRF) pour connecteurs externes (Banque Mondiale, AFD et autres partenaires stratégiques)

## 5. Non-fonctionnel (hérité de la doc d'origine, à respecter)
- **Intégrité des données** : une fois certifiée, une contribution ne peut être modifiée sans nouveau cycle de validation
- **Protection des données personnelles** : conformité type RGPD ou équivalent local
- **Scalabilité géographique** : architecture pensée pour passer d'un déploiement local à panafricain puis international sans réécriture
- **Automatisation** : privilégier les parcours self-service pour limiter l'intervention humaine (l'admin n'intervient que sur les litiges)
- **Accessibilité web** : application 100 % cloud, sans installation locale