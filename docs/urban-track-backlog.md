# Backlog — Corrections plateforme Urban Track

Source : audit du 17/09/2026 (Jérôme Chenal, africancitiesexperts.org).
Ce document reformule les constats de l'audit en tickets exploitables par un agent de développement. Chaque ticket peut être copié tel quel dans l'outil de suivi (Jira, Linear, GitHub Issues...).

Convention de priorité : P0 = bloquant confiance/sécurité, P1 = fonctionnel majeur, P2 = complétude, P3 = qualité/finition.

---

## P0 — Confiance et intégrité des données

### T1. Corriger la règle de déclaration des contributeurs
**Problème** : le message `"The publishing company cannot declare itself as contributor"` bloque le cas normal du consultant individuel et du petit bureau d'études (dirigeant = expert), sans bloquer réellement la fraude (la contribution passe quand même en "certifiée" malgré le message d'erreur).
**Action attendue** :
- Remplacer la règle "société ≠ déclarant de ses propres experts" par une règle "une même personne physique ne peut pas être à la fois déclarant et confirmateur".
- Implémenter 3 parcours de confirmation distincts :
  1. Consultant individuel (société = personne) → confirmation demandée au client / maître d'ouvrage.
  2. Expert salarié/associé d'une société tierce qui publie → déclaration par la société, confirmation par l'expert (cas aujourd'hui bloqué à tort).
  3. Sous-traitant / membre de groupement → déclaration par le chef de file du groupement.
- Corriger l'incohérence : si la règle refuse la déclaration, la contribution ne doit **jamais** apparaître comme "certifiée" sur le profil public.
**Critères d'acceptation** :
- Un consultant individuel peut déclarer un projet et faire confirmer par son client.
- Un expert salarié peut être déclaré par sa société et confirmer lui-même, sans erreur.
- Une déclaration refusée par la règle ne peut en aucun cas produire un badge "certifié".
- Tests unitaires couvrant les 3 cas + le cas de contournement observé.

### T2. Sécuriser le rattachement à une société existante
**Problème** : n'importe qui peut se déclarer membre d'une société existante en tapant simplement son nom lors de l'inscription. Aucune validation.
**Action attendue** :
- Ajouter un workflow de validation à l'adhésion : invitation par un administrateur de la société, OU vérification de domaine de messagerie professionnel, OU demande d'adhésion soumise à approbation d'un admin existant.
- Tant que la demande n'est pas validée, l'utilisateur n'apparaît pas comme membre de la société (ni dans l'équipe, ni dans les déclarations de contribution possibles).
**Critères d'acceptation** :
- Impossible de rejoindre une société sans action d'un administrateur de cette société.
- Historique/log des validations d'adhésion.

### T3. Corriger la traçabilité des contributions certifiées
**Problème** : le profil public affiche "traçable jusqu'à la page du projet" alors que le projet est privé et que la page projet publique n'existe pas → lien de preuve mort pour un tiers.
**Action attendue** (au choix, à trancher en priorité produit) :
- Option A : générer automatiquement une page projet minimale publique (nom, client, dates, contributeurs) même quand le projet reste en mode privé sur le reste de son contenu.
- Option B : retirer la mention "traçable" tant que la page cible n'est pas publiquement accessible.
**Critères d'acceptation** :
- Aucune mention de traçabilité affichée sans qu'un lien public fonctionnel existe réellement derrière.

---

## P1 — Complétude du CV généré

### T4. Ajouter les rubriques manquantes au modèle de CV
**Problème** : sur les 18 rubriques attendues d'un CV de consultant international (référence GIZ/Banque mondiale), la plateforme n'en couvre que 3 partiellement (~15 % du contenu). Rubriques totalement absentes : profil civil (naissance, nationalité, contact), points forts, indicateurs de synthèse, autres formations/séminaires, associations et mandats, pays d'intervention, langues, expériences professionnelles (postes/employeurs), publications, enseignement, médias, divers, mention de conformité/pagination.
**Action attendue** : ouvrir dans le portfolio les champs/structures de données suivants :
- État civil sommaire (nationalité, ville, contact — champs optionnels, RGPD-friendly)
- Points forts du CV (liste courte, 3-5 items)
- Indicateurs de synthèse (voir T7, calculés automatiquement)
- Autres formations / séminaires (liste datée)
- Associations et mandats professionnels (liste)
- Pays d'intervention (liste, idéalement dérivée automatiquement des projets)
- Langues avec 3 niveaux distincts : lu / parlé / écrit (voir aussi T4a)
- Publications (titre, année, support)
- Enseignement (cours, niveau, institution, années)
- Médias (titre, support, date, lien)
- Divers (champ libre court)
- Pied de page : mention de conformité, lieu, date, pagination automatique
**Critères d'acceptation** : chaque rubrique est éditable dans le portfolio, optionnelle, et s'affiche dans l'export CV quand elle est renseignée.

### T4a. Ajouter la rubrique "postes / employeurs"
**Problème** : la plateforme ne modélise que des "projets". Un poste (ex. direction d'un centre de recherche depuis 2014) n'est pas un projet et n'a pas de mécanisme de confirmation adapté. Sans cette rubrique, le CV généré n'a pas de colonne vertébrale de parcours professionnel.
**Action attendue** :
- Créer une entité "Poste" distincte de "Projet" : employeur, fonction, période (début/fin ou "en cours"), description courte.
- Ne pas soumettre les postes au mécanisme de double confirmation projet-par-projet (pas pertinent) — cf. T5 pour leur statut de fiabilité.
- Afficher les postes en ordre chronologique inversé dans le CV, comme rubrique séparée des projets.
**Critères d'acceptation** : un utilisateur peut saisir une liste de postes successifs et les voir apparaître dans le CV indépendamment des projets.

### T5. Créer un statut "déclaré (non confirmé)"
**Problème** : exiger une confirmation tierce pour chaque élément (ex. 114 projets, dont certains datent de 1996) rend la certification hors d'atteinte pour un consultant expérimenté. Le CV certifié restera toujours très inférieur à un CV classique.
**Action attendue** :
- Ajouter un statut "déclaré / non confirmé" pour tout élément (poste, projet, formation...) saisi par l'utilisateur mais non encore confirmé par un tiers.
- Marque visuelle distincte et explicite dans l'UI et dans l'export CV (ex. pictogramme + légende "non confirmé par un tiers").
- Décision produit à documenter : le CV généré doit-il mélanger éléments certifiés et déclarés (avec distinction visuelle), ou rester un document de preuve court séparé du CV classique ? Trancher avant implémentation.
**Critères d'acceptation** : un élément non confirmé peut apparaître dans le CV avec un marqueur visuel clair, distinct des éléments certifiés.

### T6. Enrichir la fiche projet (formulaire de publication)
**Problème** : champs manquants par rapport aux attentes des formats bailleurs.
**Action attendue** — ajouter au formulaire de publication de projet :
- Pays (champ structuré, pas texte libre)
- Bailleur, distinct du maître d'ouvrage (champ structuré)
- Volume d'intervention (homme-jours ou mois-personnes)
- Durée de la participation personnelle (distincte de la durée totale du projet)
- Rôle réel : remplacer la liste fermée à 4 valeurs par une liste plus large et extensible (ex. promoteur, directeur d'étude, assistant technique, keynote speaker, chef de file, membre de groupement, sous-traitant...)
- Statut (en cours / achevé)
- Mots-clés thématiques (tags, idéalement issus d'un référentiel contrôlé, cf. T9)
**Critères d'acceptation** : tous les champs listés sont saisissables, stockés de façon structurée (pas en texte libre pour pays/bailleur), et exploitables en filtre/recherche.

### T7. Calculer et certifier automatiquement les indicateurs de synthèse
**Problème** : le tableau d'indicateurs (années d'expérience, nombre de missions, de pays, de programmes financés par des bailleurs) est aujourd'hui saisi à la main dans les CV classiques et se périme vite.
**Action attendue** : calculer ces indicateurs automatiquement à partir des projets/postes certifiés de l'utilisateur, et les afficher/exporter comme bloc "indicateurs certifiés" en tête de CV.
**Critères d'acceptation** : les indicateurs se recalculent automatiquement à chaque nouvelle certification, sans saisie manuelle.

---

## P1 — Onglet "bureau d'études" (entité société)

### T8. Créer l'entité société avec fiche et vitrine
**Problème** : une société n'existe aujourd'hui que comme champ texte libre à l'inscription ; aucune page, profil, ni répertoire des sociétés.
**Action attendue** — créer une page/entité "société" comprenant :
- Fiche société : pays, année de création, effectifs, domaines, agréments
- Références projets certifiées au niveau de la société (parcours de la structure, pas seulement des individus)
- Équipe rattachée, avec les scores individuels
- Rôle de la société sur chaque projet (chef de file, membre de groupement, sous-traitant)
- Recherche de sociétés par pays, bailleur et domaine (pour montage d'équipe / groupement)
- Génération automatique d'une fiche de référence projet au format bailleur pour la société (équivalent du CV, pour la structure)
**Critères d'acceptation** : chaque société inscrite dispose d'une page publique consultable listant ses informations et son équipe validée (cf. T2).

---

## P2 — Export et localisation

### T9. Créer un référentiel contrôlé pour client/bailleur
**Problème** : le nom du client est saisi en texte libre, avec des fautes de frappe sur les noms de bailleurs ; les données ne sont donc pas exploitables pour la recherche, les filtres et les statistiques.
**Action attendue** : remplacer le champ texte libre par une liste à sélection/autocomplétion adossée à un référentiel (base de bailleurs et clients institutionnels connus), avec possibilité d'ajouter une nouvelle entrée soumise à normalisation (ex. dédoublonnage manuel côté admin).
**Critères d'acceptation** : recherche et filtres par client/bailleur retournent des résultats cohérents sans doublons dus à des variantes orthographiques.

### T10. Export Word éditable
**Problème** : les bailleurs demandent souvent un format modifiable pour insérer le CV dans leur propre trame.
**Action attendue** : ajouter un export `.docx` du CV généré, en plus du HTML/PDF existant, avec la même structure de rubriques.
**Critères d'acceptation** : le fichier `.docx` généré s'ouvre et se modifie normalement dans Word/LibreOffice, sans perte de mise en forme majeure.

### T11. Version française de l'interface et des CV
**Problème** : le public cible est principalement francophone ; l'interface et les CV générés doivent être disponibles en français.
**Action attendue** : ajouter une localisation FR complète (interface + labels d'export CV), avec sélection de langue par utilisateur/CV.
**Critères d'acceptation** : un utilisateur peut basculer l'interface et générer un CV entièrement en français.

### T12. CV ciblé (sélection de projets par avis)
**Problème** : aucun mécanisme pour sélectionner un sous-ensemble pertinent de projets pour répondre à un avis à manifestation d'intérêt (AMI) donné.
**Action attendue** : permettre à l'utilisateur de créer un "CV ciblé" en cochant un sous-ensemble de projets/postes/publications à inclure dans un export donné, sans dupliquer les données sources.
**Critères d'acceptation** : un même profil peut générer plusieurs CV ciblés différents, chacun avec une sélection propre de projets.

---

## P3 — Corrections mineures / qualité

### T13. Corriger le rendu du nom et des accents dans l'export CV
**Problème** : le CV généré coupe le nom en haut de page et perd les accents (encodage).
**Action attendue** : corriger l'encodage (UTF-8 de bout en bout) et le layout de l'en-tête pour éviter la troncature du nom.

### T14. Formulaire portfolio — ajout de lignes dynamique
**Problème** : le formulaire fonctionne avec deux lignes vides toujours disponibles ; un bouton "Ajouter une ligne" serait plus clair.
**Action attendue** : remplacer les lignes vides statiques par un bouton d'ajout dynamique, sur toutes les listes du portfolio (formations, langues, publications, etc.).

### T15. Documenter publiquement le score de confiance
**Problème** : le score de confiance n'est expliqué nulle part ; sans formule publique, aucun bailleur ne s'y fiera.
**Action attendue** : publier une page expliquant la méthodologie de calcul du score de confiance (facteurs pris en compte, pondération), accessible depuis chaque affichage du score.

### T16. Masquer les compteurs à zéro en phase de lancement
**Problème** : afficher des compteurs à zéro (nombre de projets, de sociétés, etc.) donne une impression de site vide.
**Action attendue** : masquer ou remplacer par un message d'accueil les compteurs/statistiques tant qu'ils sont à zéro ou proches de zéro, avec un seuil configurable.

---

## Nouveau chantier — Modèle de CV "Banque mondiale" (hors audit initial)

### T17. Nouveau template d'export CV au format Banque mondiale
**Objectif** : créer un nouveau template d'export de CV suivant le format standard Banque mondiale (les 18 rubriques identifiées dans l'audit, cf. T4/T4a), et le proposer par défaut au moment de la génération de CV (à la place ou en complément du format actuel réduit à deux lignes de formation).
**Action attendue** :
- Implémenter un template dédié au format Banque mondiale, structuré selon les 18 rubriques (voir maquette jointe `cv-world-bank-template.html`).
- En faire le choix par défaut proposé à l'utilisateur dans le sélecteur de format d'export (l'utilisateur peut toujours choisir un autre format).
- Le rendu doit être conçu comme un document de type "dossier papier" (mise en page façon document imprimé : marges, typographie sobre, pagination, en-tête/pied de page répétés à l'impression) et non comme une page web classique (pas de barre de navigation, pas de cartes, pas d'éléments d'interface dans l'export).
- Gérer l'affichage différencié "certifié" / "déclaré non confirmé" (cf. T5) directement dans ce template.
- Prévoir l'impression / export PDF fidèle (CSS `@media print`, sauts de page propres entre rubriques).
**Livrable joint** : `cv-world-bank-template.html` — maquette HTML statique du template, avec données d'exemple, à intégrer côté moteur de génération (remplacement des données d'exemple par les données réelles du profil).
**Critères d'acceptation** :
- Le format Banque mondiale est proposé par défaut à la génération de CV.
- Le rendu imprimé/PDF ne comporte aucun élément d'interface web (nav, boutons, cartes) — uniquement un document texte structuré.
- Les rubriques vides ne s'affichent pas (pas de titre de section sans contenu).
- Les éléments "déclarés non confirmés" sont visuellement distincts des éléments certifiés.

### T18. Généraliser et centraliser le dictionnaire de labels (i18n)
**Problème** : le template Banque mondiale (T17) introduit à lui seul une trentaine de nouvelles clés de label (`strengths`, `indicators`, `positions`, `teaching_masters`, `status_confirmed`...). Si chaque template gère ses propres libellés en dur ou dans des fichiers séparés non coordonnés, chaque nouveau template (ou chaque nouvelle rubrique) recrée le même risque d'oubli de traduction déjà constaté sur l'absence de version française (T11).
**Action attendue** :
- Créer un dictionnaire i18n **unique et partagé** par tous les templates de CV (actuel + Banque mondiale + futurs formats), organisé par langue puis par clé plate (voir livrable `cv-labels.i18n.json` joint, qui liste l'ensemble des clés utilisées à ce jour, FR et EN).
- Mettre en place un **repli automatique** côté backend : si une clé demandée par un template est absente dans la langue cible, utiliser la valeur anglaise (langue de repli), et logguer un avertissement (pas d'échec silencieux, pas de clé brute affichée dans le CV).
- Ajouter une commande ou un test CI qui compare, pour chaque template, les clés `labels.xxx` réellement utilisées dans le fichier `.html` à celles présentes dans le dictionnaire i18n, et fait échouer le build si une clé est utilisée sans traduction déclarée dans au moins la langue de repli.
**Critères d'acceptation** :
- Ajouter un nouveau template ou une nouvelle rubrique ne peut plus produire de clé de label manquante en silence : soit elle est traduite, soit elle tombe sur l'anglais avec un log, jamais sur du texte cassé.
- Le dictionnaire FR est complet à 100 % pour les clés listées dans `cv-labels.i18n.json`.
**Livrable joint** : `cv-labels.i18n.json` — dictionnaire FR/EN généralisé, structuré pour être consommé par n'importe quel template de CV (pas seulement celui de la Banque mondiale).

### T19. Contrôle de complétude du profil avant génération de CV
**Problème** : rien n'avertit aujourd'hui l'utilisateur, avant export, que des rubriques attendues par un format donné sont vides (le CV se génère simplement en sautant les sections manquantes, cf. les `{% if %}` du template). Un consultant peut envoyer un CV Banque mondiale à un bailleur sans réaliser qu'il lui manque, par exemple, la rubrique langues ou pays d'intervention.
**Action attendue** :
- Définir, par format de CV (Banque mondiale, format court, futur format), une liste de rubriques "recommandées" et de rubriques "obligatoires" (ex. langues et formation obligatoires pour le format Banque mondiale ; publications recommandées mais non bloquantes).
- Avant génération, afficher à l'utilisateur un indicateur de complétude du profil pour le format choisi (ex. "82 % — il vous manque : Langues, Pays d'intervention") avec lien direct vers les champs à compléter dans le portfolio.
- Ne jamais bloquer la génération (un CV incomplet reste un CV valide), mais rendre l'incomplétude visible avant l'export plutôt que de la découvrir dans le document final.
**Critères d'acceptation** :
- Chaque format de CV déclare sa propre liste de rubriques obligatoires/recommandées.
- L'utilisateur voit, avant de télécharger, un résumé clair des rubriques manquantes pour le format sélectionné.

### T20. Documenter et faire respecter le contrat de données de chaque template
**Problème** : les variables de contexte attendues par un template (ex. `cv.positions`, `cv.indicators`, `cv.languages`...) ne vivent aujourd'hui que dans les commentaires du fichier `.html` du template (voir l'en-tête ajouté dans `world_bank.html`). Rien ne garantit que le code qui prépare les données pour le moteur de rendu (Jinja) reste synchronisé si le template évolue.
**Action attendue** :
- Extraire un schéma de données (JSON Schema ou équivalent) par template, listant les champs attendus, leur type, et s'ils sont optionnels ou obligatoires.
- Valider automatiquement (test ou vérification au moment de la génération) que l'objet `cv` transmis au moteur de rendu respecte ce schéma, avec message d'erreur explicite en cas de champ du mauvais type (plutôt qu'un rendu silencieusement incomplet ou une exception Jinja peu lisible).
- Garder le schéma comme source de vérité pour T19 (quelles rubriques sont "obligatoires"/"recommandées" par format).
**Critères d'acceptation** : ajouter un champ mal typé ou un format de date incohérent dans les données d'un CV déclenche une erreur explicite en environnement de test, avant la mise en production.

---

## Ordre de traitement suggéré
1. T1, T2, T3 (confiance — sans cela, rien d'autre n'a de valeur)
2. T4, T4a, T5, T6, T7 (le CV redevient utilisable)
3. T18, T20 (fondations : dictionnaire i18n partagé + contrat de données), puis T17 (nouveau template Banque mondiale, s'appuie sur T4/T4a/T5/T18/T20)
4. T19 (complétude, s'appuie sur le schéma défini en T20)
5. T8 (bureau d'études)
6. T9, T10, T11, T12 (export/localisation — T11 réutilise le dictionnaire i18n de T18)
7. T13 à T16 (finitions)
