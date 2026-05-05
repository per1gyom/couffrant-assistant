-- ════════════════════════════════════════════════════════════════════
-- SCRIPT NETTOYAGE - Reetiquetage mails mal attribues a contact@
-- ════════════════════════════════════════════════════════════════════
-- Date  : 05/05/2026
-- Objet : Suite au diagnostic, les 111 mails enregistres sous
--         mailbox_email='contact@couffrant-solar.fr' sont en realite
--         des mails de guillaume@couffrant-solar.fr (token OAuth croisé).
-- 
-- Action : reetiqueter ces mails vers la bonne boite ET le bon graphe.
-- 
-- IMPORTANT : a executer APRES :
--   1. Confirmation diagnostic via /admin/mail/diag/all-token-identities
--   2. Validation explicite Guillaume
--   3. Backup mail_memory recommande
-- 
-- A executer EN UNE TRANSACTION (BEGIN/COMMIT) pour pouvoir rollback
-- en cas de probleme.
-- ════════════════════════════════════════════════════════════════════

BEGIN;

-- 1. Compter avant action (sanity check)
SELECT 'AVANT' AS phase,
       COUNT(*) FILTER (WHERE mailbox_email='contact@couffrant-solar.fr') AS contact,
       COUNT(*) FILTER (WHERE mailbox_email='guillaume@couffrant-solar.fr') AS guillaume
FROM mail_memory
WHERE tenant_id='couffrant_solar';

-- 2. Identifier les message_id qui existent DEJA sous guillaume@ (eviter doublons)
-- Devrait etre 0 si le diagnostic est correct (tokens differents = ids differents)
SELECT COUNT(*) AS message_id_already_in_guillaume
FROM mail_memory mm1
WHERE mm1.mailbox_email='contact@couffrant-solar.fr'
  AND mm1.tenant_id='couffrant_solar'
  AND EXISTS (
    SELECT 1 FROM mail_memory mm2
    WHERE mm2.message_id = mm1.message_id
      AND mm2.mailbox_email='guillaume@couffrant-solar.fr'
      AND mm2.tenant_id='couffrant_solar'
  );

-- 3. Reetiquetage mail_memory : contact@ -> guillaume@
-- (uniquement les mails qui n existent PAS deja sous guillaume@)
UPDATE mail_memory
SET mailbox_email = 'guillaume@couffrant-solar.fr',
    connection_id = 6,
    mailbox_source = 'outlook',
    updated_at = NOW()
WHERE mailbox_email = 'contact@couffrant-solar.fr'
  AND tenant_id = 'couffrant_solar'
  AND NOT EXISTS (
    SELECT 1 FROM mail_memory mm2
    WHERE mm2.message_id = mail_memory.message_id
      AND mm2.mailbox_email = 'guillaume@couffrant-solar.fr'
      AND mm2.tenant_id = 'couffrant_solar'
  );

-- 4. Soft-delete des mail_memory contact@ qui restent (doublons exacts avec guillaume@)
UPDATE mail_memory
SET deleted_at = NOW(), updated_at = NOW()
WHERE mailbox_email = 'contact@couffrant-solar.fr'
  AND tenant_id = 'couffrant_solar'
  AND deleted_at IS NULL;

-- 5. Compter apres
SELECT 'APRES' AS phase,
       COUNT(*) FILTER (WHERE mailbox_email='contact@couffrant-solar.fr' AND deleted_at IS NULL) AS contact_actifs,
       COUNT(*) FILTER (WHERE mailbox_email='guillaume@couffrant-solar.fr' AND deleted_at IS NULL) AS guillaume_actifs
FROM mail_memory
WHERE tenant_id='couffrant_solar';

-- 6. Si tout est coherent, valider :
-- COMMIT;
-- 
-- Sinon rollback :
-- ROLLBACK;

-- ════════════════════════════════════════════════════════════════════
-- LE COMMIT EST INTENTIONNELLEMENT EN COMMENTAIRE.
-- Verifier les resultats des SELECT avant 1er et 5eme bloc.
-- Si tout va bien, decommenter COMMIT et relancer le script.
-- ════════════════════════════════════════════════════════════════════

-- Note sur les noeuds graphe :
-- semantic_graph_nodes pointe vers mail_memory.id via source_record_id.
-- Le reetiquetage de mail_memory ne change pas l id, donc les noeuds
-- restent valides. Les soft-deletes (etape 4) declencheront les filtres
-- WHERE deleted_at IS NULL dans les recherches Raya, donc invisibles.
-- Pour cleanup propre des noeuds soft-deleted on pourra le faire plus tard.
