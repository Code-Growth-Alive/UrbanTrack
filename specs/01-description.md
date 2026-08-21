# Urban Track — Spécification de description produit

## 1. Nom du produit
**Urban Track** (anciennement "Urban Track AI"). Le nom est simplifié pour insister sur la fonction première : tracer, prouver et certifier les expériences réelles des experts du développement urbain en Afrique.

> **Contexte projet** : reprise à zéro. Aucun code, aucune base de données, aucun écran n'existe encore. Cette spec décrit donc un projet **greenfield** — tout est à construire, y compris le job board, le générateur de CV et le module de certification. Il n'y a pas d'ancien flux "auto-déclaré" à faire cohabiter avec le nouveau : le flux de confirmation croisée est le seul et unique flux de certification. Il n'y a pas non plus de logique de version (pas de "V1" minimale suivie d'itérations) : ce qui est décrit ici est le périmètre complet du produit.

## 2. Le problème (pourquoi)
- **CV invérifiables** : rien ne prouve qu'un expert a réellement fait ce qu'il déclare. 50–90 % des CV du secteur contiennent des informations fausses ou exagérées.
- **Vol de mérite** : les entreprises s'attribuent le crédit des projets, les experts individuels qui ont fait le travail disparaissent du narratif.
- **Silos d'information** : les grandes agences (Banque Mondiale, UE, BAD, AFD) ne partagent pas leurs données de projets entre elles ni avec le marché, ce qui empêche les petites structures et les experts de se positionner correctement.

## 3. La solution (quoi)
Urban Track est une plateforme centrale qui applique une **logique de preuve croisée, inspirée de ResearchGate**, au secteur du développement urbain :

- Sur ResearchGate, une publication n'est crédible que lorsque les co-auteurs déclarés confirment eux-mêmes y avoir contribué. Urban Track applique le même principe aux **projets urbains** : ce n'est plus l'expert qui déclare unilatéralement une expérience, c'est **l'entreprise qui a réalisé le projet qui le publie et qui déclare les contributeurs**. Chaque expert cité est ensuite invité à confirmer, ajuster ou refuser sa contribution.
- Comme sur ResearchGate, chaque **profil expert** devient une page publique consultable, listant uniquement les expériences **confirmées par les deux parties** (entreprise + expert), avec un badge de certification et un lien traçable vers la fiche projet correspondante.
- Cette double confirmation indépendante remplace la validation manuelle par un admin dans la majorité des cas — l'admin n'intervient qu'en cas de litige (contribution contestée), exactement comme un modérateur de plateforme scientifique n'intervient qu'en cas de conflit entre auteurs.
- À terme, un moteur d'intelligence artificielle exploite cette base certifiée pour recommander les meilleurs experts pour une mission (matchmaking) et estimer la probabilité de succès d'un projet selon l'équipe choisie.

## 4. Positionnement : la "Trust Layer"
Urban Track se positionne comme la **couche de confiance** du secteur — l'argument de vente principal face aux donateurs (Banque Mondiale, UE, BAD). Chaque affirmation présente sur la plateforme doit pouvoir remonter à un projet documenté et à une confirmation croisée vérifiable, exactement comme une affirmation scientifique doit remonter à une publication et à ses auteurs vérifiés.

## 5. Logique "ResearchGate" appliquée module par module
| Concept ResearchGate | Équivalent Urban Track |
|---|---|
| Profil chercheur public | Profil expert public avec ID unique et permanent |
| Publication revendiquée | Projet publié par une entreprise |
| Co-auteur invité à confirmer | Expert invité à confirmer sa contribution au projet |
| "Is this you?" / invitation par email d'un non-inscrit | `ExpertInvitation` par email + lien magique, création de compte intégrée au parcours |
| Statut de publication vérifiée | `ProjectContribution.status = confirmed`, badge "Certifié" |
| Score / métriques de profil (RG Score) | Score de confiance dynamique basé sur le nombre et le type de contributions certifiées |
| Modération en cas de litige d'auteur | Passage en statut `disputed`, arbitrage admin |
| Fil d'actualité / notifications de collaboration | Notifications internes + emails transactionnels (invitation, rappel, confirmation) |


## 6. Décisions de conception (rien à migrer, tout à construire, périmètre complet)
Comme il n'y a pas d'existant à faire évoluer, les choix issus des docs de départ deviennent directement des **décisions de scope définitives**, pas des étapes intermédiaires :
| Sujet | Décision |
|---|---|
| Job board | Fait partie intégrante du produit, au même titre que les autres modules — construit après le cœur de certification, pas "en option" |
| Certification | Uniquement le flux de confirmation croisée entreprise/expert ; pas de flux "auto-déclaré" à prévoir |
| CV | Générateur multi-templates (un moteur, plusieurs skins) dès la conception |
| Ajout de projet | Uniquement le flux "l'entreprise publie et invite, l'expert confirme" (logique ResearchGate) — pas de saisie libre par l'expert |

## 8. Identité visuelle (contrainte produit)
- **Couleur de base** : vert militaire (institutionnel, sérieux, "terrain")
- **Couleur d'accent** : rose (contraste, call-to-action, badges de confirmation/certification)
- **Neutres** : blanc et gris anthracite/noir pour le texte, les fonds et les structures de cartes
- Le détail des tokens de couleur et de la mise en œuvre Tailwind est spécifié dans `02-stack.md`.