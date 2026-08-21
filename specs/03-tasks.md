# Urban Track — Découpage des tâches (tasks)

> **Projet greenfield** : reprise à zéro, rien n'existe (pas de repo, pas de modèles, pas d'auth, pas de job board livré). Ce document part donc de zéro, y compris pour les fondations techniques (Épique -1) avant d'attaquer le design system et le cœur métier. **Il n'y a pas de notion de version** : ce qui est listé ici constitue le périmètre complet du produit, pas une V1 suivie d'itérations futures — seul l'ordre de construction est séquencé.

Priorité absolue dès que les fondations sont posées : **Module de certification croisée** (logique ResearchGate). Le job board fait pleinement partie du produit et est construit une fois le cœur de certification en place, mais avec le même niveau d'exigence que les autres modules.

## Épique -1 — Bootstrap technique
- [ ] Initialiser le repo Django (structure d'apps : `accounts`, `projects`, `certification`, `cv_generator`, `jobs`)
- [ ] Configurer PostgreSQL (local + environnement de déploiement)
- [ ] Installer et configurer Tailwind CSS dans le projet Django (django-tailwind ou pipeline npm + `{% tailwind_css %}`)
- [ ] Mettre en place Celery + Redis (worker + beat) pour les tâches planifiées
- [ ] Mettre en place l'environnement de settings (dev/staging/prod), variables d'environnement, `.env`
- [ ] Créer le modèle `User` custom Django avec les 3 rôles (Expert individuel / Entreprise / Agence donateur) — OF-01
- [ ] Génération de l'identifiant professionnel unique, permanent et gratuit à l'inscription (OF-02)
- [ ] CI minimale (lint + tests) et déploiement initial (staging)

## Épique 0 — Design system & fondations UI
- [ ] Configurer `tailwind.config.js` avec les tokens `military`, `accent` (rose), `charcoal`, `white`
- [ ] Créer les composants Tailwind réutilisables : bouton primaire (vert militaire), bouton d'action (rose), carte projet, carte profil expert
- [ ] Créer les 2 variantes de badge nécessaires : "Certifié via confirmation croisée" et "En attente de confirmation" (pas de flux historique à distinguer)
- [ ] Définir la typographie et la hiérarchie visuelle (page profil public type ResearchGate : bandeau, stats, liste de contributions certifiées)

## Épique 1 — Modèle de données métier (Django)
- [ ] Créer le modèle `Project` (nouveau) : `official_name`, `description`, `deliverables`, `duration_start/end`, `budget`, `client_name`, `status`, `visibility`
- [ ] Créer le modèle `ProjectContribution` (project, expert nullable, invited_email, role_type, contribution_bullets, status, added_by, confirmed_at)
- [ ] Créer le modèle `ExpertInvitation` (contribution, email, token UUID, sent_at, expires_at, status, reminder_count)
- [ ] Migrations + contrainte d'intégrité : une contribution `confirmed` ne peut plus être modifiée sans nouveau cycle de validation (ONF-03)
- [ ] Créer le modèle `ExpertProfile` (portfolio dynamique : compétences, formations, expériences liées — OF-03) lié au `User` expert
- [ ] Champ `cv_template` prévu dès la conception du futur générateur de CV (épique 7)

## Épique 2 — Publication de projet côté entreprise
- [ ] Écran "Publier un projet" : formulaire des champs `Project`
- [ ] Section "Contributeurs" avec recherche autocomplete d'un expert existant (par nom ou OXID/ID unique)
- [ ] Ajout d'un contributeur par email si non-inscrit
- [ ] Sélection du rôle (Directeur / Manager / Assistant / Spécialiste) et saisie des bullets de contribution par contributeur
- [ ] Gestion du statut Draft / Published / Archived et de la visibilité Public / Privé pendant rédaction

## Épique 3 — Invitation & atterrissage expert (logique ResearchGate)
- [ ] Déclenchement automatique : si l'expert a déjà un compte → notification interne + email de confirmation
- [ ] Déclenchement automatique : si l'email ne correspond à aucun compte → création `ExpertInvitation` (token unique) + email "Vous avez été identifié comme contributeur au projet [X] par [Entreprise]"
- [ ] Page d'atterrissage pré-remplie (projet, rôle, bullets proposés) accessible via lien magique
- [ ] 3 actions expert : Confirmer tel quel / Confirmer avec ajustement (déclenche re-validation) / Refuser
- [ ] Parcours de création de compte intégré à la page d'atterrissage (sans friction supplémentaire) si l'expert n'a pas de compte
- [ ] Dédoublonnage automatique par email : liaison à un compte existant plutôt que création d'un doublon

## Épique 4 — Certification & profil public (page type ResearchGate)
- [ ] Passage automatique en `confirmed` dès confirmation expert
- [ ] Apparition automatique de l'expérience dans le CV généré, avec badge "Certifié"
- [ ] Lien traçable et cliquable entre profil expert ↔ fiche projet publique
- [ ] Mise à jour temps réel du profil (accréditation dynamique, OF-08)
- [ ] Page profil expert publique : liste des contributions certifiées, badges, lien vers projets (inspirée d'une page profil ResearchGate)
- [ ] Score de confiance / indicateur de crédibilité du profil basé sur les contributions certifiées (équivalent RG Score : nombre de contributions certifiées par rôle)

## Épique 5 — Gestion des cas limites
- [ ] Tâche planifiée (Celery) : relance automatique si pas de réponse (jusqu'à 2 relances), puis passage en `expired`
- [ ] Gestion du litige : passage en `disputed` si l'expert conteste, remontée dans une file d'arbitrage admin (seul cas d'intervention humaine)
- [ ] Interface admin d'arbitrage des litiges

## Épique 6 — Infrastructure email & sécurité
- [ ] Intégration backend transactionnel (SendGrid / Mailgun / SES) — décision à trancher
- [ ] Suivi ouverture/clic sur les invitations, mise à jour du statut `ExpertInvitation` (sent/opened/converted/expired)
- [ ] Génération de lien magique sécurisé (uuid4 + expiration ou `itsdangerous`)
- [ ] Revue sécurité : protection des données personnelles (RGPD ou équivalent local), gestion de l'expiration des tokens (~14 jours)

## Épique 7 — Générateur de CV multi-templates
- [ ] Intégrer WeasyPrint au projet (rien n'est en place)
- [ ] Construire le moteur de génération générique ("un moteur, plusieurs skins") consommant uniquement les données de profil + `ProjectContribution.status = confirmed`
- [ ] Créer les 3 templates prévus au périmètre : académique (MIT/Harvard), AFD, Banque Mondiale
- [ ] Écran `/cv-generator/` avec sélecteur `cv_template`
- [ ] Rendu bilingue FR/EN pour chaque template
- [ ] **Bloquant** : obtenir de Jerome les exemples de CV + le template Banque Mondiale (action déjà actée en réunion) avant de démarrer précisément ce template

## Épique 8 — Job board
- [ ] Construit après livraison des épiques 1 à 4 (certification) et 7 (CV), mais fait pleinement partie du périmètre du produit
- [ ] Publication d'une offre par une entreprise, consultation par les experts, candidature
- [ ] Fonctionnalités associées prévues au périmètre : mise en avant des offres, filtrage/recherche pour les experts, gestion des candidatures côté entreprise

## Épique 9 — Connecteurs de données externes (après le cœur de certification)
- [ ] Connecteur API Banque Mondiale (ingestion de projets)
- [ ] Connecteur API AFD (ingestion de projets)
- [ ] Standardisation des données hétérogènes (formats de dates, conventions de nommage de projets) — ONF-02

## Épique 10 — IA & Matchmaking
- [ ] Algorithme de recommandation d'experts (matchmaking) basé sur les contributions certifiées
- [ ] Score de prédiction de succès de projet selon la composition de l'équipe

## Ordre de construction recommandé
Toutes les épiques ci-dessus font partie du périmètre complet du produit — l'ordre ci-dessous est un ordre de construction (dépendances techniques), pas un découpage en versions :
1. **Épique -1 (bootstrap technique)** — préalable incontournable, rien ne peut démarrer sans ça
2. Épique 0 (design system) + Épique 1 (modèle de données métier) — en parallèle, dès que le bootstrap est prêt
3. Épique 2 (publication projet) → Épique 3 (invitation expert) → Épique 4 (certification/profil public)
4. Épique 5 (cas limites) + Épique 6 (infra email/sécurité) — en parallèle de l'épique 3-4
5. Épique 7 (CV multi-templates) — dès que l'épique 4 fournit des contributions `confirmed` exploitables ; template Banque Mondiale bloqué tant que Jerome n'a pas fourni ses exemples
6. Épique 9 (connecteurs externes)
7. Épique 10 (IA/matchmaking)
8. Épique 8 (job board)