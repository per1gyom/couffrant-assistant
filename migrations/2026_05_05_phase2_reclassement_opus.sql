-- Migration: Phase 2 mini-Graphiti — Reclassement Opus des 168 règles actives
-- Date: 05/05/2026 soir
-- Branche: feat/learning-hierarchy
-- Validé par Guillaume :
--   - Archivage de 4 règles obsolètes (85, 135, 6, 275)
--   - Conservation des 3 valeurs Atemporal/Static/Dynamic
--   - Static = "vrai aujourd'hui, peut périmer mais pas forcément"
--     (parts sociales, équipe, clients, outils connectés, etc.)

BEGIN;

-- =====================================================================
-- BLOC 0 : ARCHIVAGE de règles obsolètes (active=false)
-- =====================================================================

UPDATE aria_rules SET active = false WHERE id = 85;
UPDATE aria_rules SET active = false WHERE id = 135;
UPDATE aria_rules SET active = false WHERE id = 6;
UPDATE aria_rules SET active = false WHERE id = 275;


-- =====================================================================
-- BLOC 1 : valid_at = created_at pour toutes les règles actives
-- =====================================================================

UPDATE aria_rules
SET valid_at = created_at
WHERE active = true AND valid_at IS NULL;


-- =====================================================================
-- BLOC 2 : BEHAVIOR + Atemporal (règles de comportement Raya)
-- =====================================================================
-- Toutes durables par essence (pas de date d'expiration intrinsèque).

UPDATE aria_rules
SET type = 'Behavior', temporal_class = 'Atemporal'
WHERE active = true
  AND (
       category IN ('Comportement', 'Limites', 'Mémoire', 'Tri mails',
                    'Regroupement', 'Surveillance', 'Météo', 'Priorités',
                    'Affichage')
       OR id IN (15, 16, 66, 88, 91, 107, 113, 116, 137, 150,
                 215, 216, 217, 218, 230)
  );


-- =====================================================================
-- BLOC 3 : PREFERENCE + Atemporal (préférences user)
-- =====================================================================
-- Durables jusqu'à contradiction explicite par l'utilisateur.

UPDATE aria_rules
SET type = 'Preference', temporal_class = 'Atemporal'
WHERE active = true
  AND (
       category IN ('Style', 'UX')
       OR id IN (11, 57, 63, 65, 68, 78, 79, 80, 92, 93,
                 100, 101, 139, 163, 178, 181)
  );


-- =====================================================================
-- BLOC 4 : KNOWLEDGE + Atemporal (vocabulaire conceptuel durable)
-- =====================================================================
-- Définitions métier et catégories qui ne dépendent pas du temps.
-- Note : 147, 157, 159 (limitations API Odoo) seront passées en Static
-- au bloc 7 car elles peuvent évoluer.

UPDATE aria_rules
SET type = 'Knowledge', temporal_class = 'Atemporal'
WHERE active = true
  AND (
       category IN ('Métier', 'categories_mail', 'Données')
       OR id IN (23, 25, 26, 148, 164, 177, 184)
  );


-- =====================================================================
-- BLOC 5 : KNOWLEDGE + Static (concepts qui peuvent évoluer)
-- =====================================================================
-- Les limitations API Odoo et l'inventaire des modules installés
-- peuvent changer si on installe de nouveaux modules ou si l'API
-- expose plus de champs un jour.

UPDATE aria_rules
SET type = 'Knowledge', temporal_class = 'Static'
WHERE active = true
  AND id IN (
       147,    -- "project.project pas accessible via API"
       157,    -- "Odoo : seuls base_automation et mail_bot installés"
       159     -- "API Odoo n'expose que métadonnées des devis"
  );


-- =====================================================================
-- BLOC 6 : FACT + Dynamic (états temporels actifs)
-- =====================================================================

UPDATE aria_rules
SET type = 'Fact', temporal_class = 'Dynamic'
WHERE active = true
  AND id IN (109, 110, 120, 123, 138, 140, 141, 142, 152, 155, 215);


-- =====================================================================
-- BLOC 7 : FACT + Static (faits qui peuvent un jour changer)
-- =====================================================================
-- Tout le reste des Fact qui n'est pas Dynamic ni explicitement
-- Atemporal au BLOC 8. C'est la majorité : équipe, clients, outils
-- connectés, parts sociales, descriptions structurelles.

UPDATE aria_rules
SET type = 'Fact', temporal_class = 'Static'
WHERE active = true
  AND type = 'Fact'  -- Filtre : ce qui n'a pas été reclassé en Behavior/Preference/Knowledge/Dynamic
  AND temporal_class = 'Atemporal'  -- Encore au défaut, donc à muscler en Static
  AND id NOT IN (62);  -- Exception Atemporal au BLOC 8


-- =====================================================================
-- BLOC 8 : FACT + Atemporal (descriptions identitaires intemporelles)
-- =====================================================================
-- Très peu de cas. Description du métier PV qui est une caractéristique
-- intrinsèque au métier, pas un état du monde.

UPDATE aria_rules
SET type = 'Fact', temporal_class = 'Atemporal'
WHERE active = true AND id = 62;


COMMIT;

-- =====================================================================
-- ROLLBACK :
-- BEGIN;
-- UPDATE aria_rules SET active = true WHERE id IN (6, 85, 135, 275);
-- UPDATE aria_rules SET type='Fact', temporal_class='Atemporal',
--                       valid_at=NULL, invalid_at=NULL
-- WHERE active=true;
-- COMMIT;
-- =====================================================================
