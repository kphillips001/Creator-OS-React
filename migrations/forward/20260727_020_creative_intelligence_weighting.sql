-- Rebuild aggregate category evidence using editorial decision strength.
-- The Autonomous Inspiration Engine still reads this profile only, never events.
WITH weighted_values AS (
    SELECT
        event.creator_profile_id,
        attribute.key AS dimension,
        attribute.value AS category,
        SUM(
            CASE event.event_type
                WHEN 'published' THEN 5
                WHEN 'photoshoot_added' THEN 4
                WHEN 'generation_library_retained' THEN 4
                WHEN 'edit_saved' THEN 3
                ELSE 1
            END
        )::INTEGER AS evidence_weight
    FROM public.creative_intelligence_events event
    CROSS JOIN LATERAL jsonb_each_text(event.analysis) attribute
    WHERE event.signal = 'positive'
      AND event.analysis_status = 'completed'
    GROUP BY event.creator_profile_id, attribute.key, attribute.value
),
dimension_documents AS (
    SELECT
        creator_profile_id,
        dimension,
        jsonb_object_agg(category, evidence_weight) AS categories
    FROM weighted_values
    GROUP BY creator_profile_id, dimension
),
profile_documents AS (
    SELECT
        creator_profile_id,
        jsonb_object_agg(dimension, categories) AS learned_attributes
    FROM dimension_documents
    GROUP BY creator_profile_id
)
UPDATE public.creative_intelligence_profiles profile
SET learned_attributes = document.learned_attributes,
    updated_at = NOW()
FROM profile_documents document
WHERE profile.creator_profile_id = document.creator_profile_id;
