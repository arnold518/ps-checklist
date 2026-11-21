-- Public archive objects are visible only while a current published material
-- references them. Old object rows stay available for retention and review.
BEGIN;

CREATE INDEX catalog_materials_archive_id_idx ON catalog.materials ((payload->>'archiveId'))
    WHERE is_public AND payload ? 'archiveId';

DROP POLICY public_objects ON archive.objects;
CREATE POLICY public_objects ON archive.objects FOR SELECT TO anon USING (
    is_public AND EXISTS (
        SELECT 1 FROM catalog.materials m
        WHERE m.is_public AND m.payload->>'archiveId' = archive.objects.id::text
    )
);

DROP POLICY accessible_objects ON archive.objects;
CREATE POLICY accessible_objects ON archive.objects FOR SELECT TO authenticated USING (
    (is_public AND EXISTS (
        SELECT 1 FROM catalog.materials m
        WHERE m.is_public AND m.payload->>'archiveId' = archive.objects.id::text
    )) OR owner_id = (SELECT auth.uid())
);

COMMIT;
