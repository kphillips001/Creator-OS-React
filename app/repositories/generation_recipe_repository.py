"""Append-only PostgreSQL persistence for generation recipes."""
from __future__ import annotations

import json
from typing import Any, Mapping
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.generation_recipe import (
    GenerationRecipe, GenerationRecipeExecution, GenerationRecipeOutput,
    GenerationRecipeReference,
)


class GenerationRecipeRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def create(self, recipe: GenerationRecipe) -> GenerationRecipe:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.generation_recipes(
                   recipe_id,schema_version,generation_job_id,generation_request_id,prompt_plan_id,
                   submission_index,source_workflow,workflow_origin,provider_id,provider_family,
                   provider_adapter,provider_adapter_version,provider_endpoint,provider_model,
                   provider_model_revision,generation_type,media_type,planned_prompt,final_prompt,
                   final_prompt_sha256,creative_mode,render_policy,render_policy_version,
                   normalized_settings,output_format,width,height,aspect_ratio,resolution,seed,
                   seed_policy,sanitized_provider_payload,sanitized_payload_sha256,
                   source_generated_image_id,source_recipe_id,regeneration_operation_id)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                          %s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)""",
                (recipe.recipe_id,recipe.schema_version,recipe.generation_job_id,
                 recipe.generation_request_id,recipe.prompt_plan_id,recipe.submission_index,
                 recipe.source_workflow,recipe.workflow_origin,recipe.provider_id,
                 recipe.provider_family,recipe.provider_adapter,recipe.provider_adapter_version,
                 recipe.provider_endpoint,recipe.provider_model,recipe.provider_model_revision,
                 recipe.generation_type,recipe.media_type,recipe.planned_prompt,recipe.final_prompt,
                 recipe.final_prompt_sha256,recipe.creative_mode,recipe.render_policy,
                 recipe.render_policy_version,json.dumps(dict(recipe.normalized_settings)),
                 recipe.output_format,recipe.width,recipe.height,recipe.aspect_ratio,
                 recipe.resolution,recipe.seed,recipe.seed_policy,
                 json.dumps(dict(recipe.sanitized_provider_payload)),recipe.sanitized_payload_sha256,
                 recipe.source_generated_image_id,recipe.source_recipe_id,
                 recipe.regeneration_operation_id),
            )
            for reference in recipe.references:
                cursor.execute(
                    """INSERT INTO public.generation_recipe_references(
                       recipe_reference_id,recipe_id,position,role,source_type,source_id,asset_id,
                       generated_image_id,media_type,content_sha256,provider_reference_kind,
                       diagnostic_metadata)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    (reference.recipe_reference_id,recipe.recipe_id,reference.position,reference.role,
                     reference.source_type,reference.source_id,reference.asset_id,
                     reference.generated_image_id,reference.media_type,reference.content_sha256,
                     reference.provider_reference_kind,json.dumps(dict(reference.diagnostic_metadata))),
                )
            cursor.execute(
                "INSERT INTO public.generation_recipe_executions(recipe_id,status) VALUES(%s,'PREPARED')",
                (recipe.recipe_id,),
            )
        return recipe

    def get(self, recipe_id: UUID | str) -> GenerationRecipe | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.generation_recipes WHERE recipe_id=%s", (recipe_id,))
            row = cursor.fetchone()
            if not row:
                return None
            cursor.execute(
                "SELECT * FROM public.generation_recipe_references WHERE recipe_id=%s ORDER BY position",
                (recipe_id,),
            )
            references = tuple(GenerationRecipeReference(**dict(item)) for item in cursor.fetchall())
        values = dict(row)
        values["references"] = references
        return GenerationRecipe(**values)

    def prefetch(self, recipe_ids) -> "PrefetchedGenerationRecipeRepository":
        ids = tuple(dict.fromkeys(str(value) for value in recipe_ids if value))
        if not ids:
            return PrefetchedGenerationRecipeRepository({}, {}, {})
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.generation_recipes WHERE recipe_id=ANY(%s::uuid[])", (list(ids),))
            recipe_rows = {str(row["recipe_id"]): dict(row) for row in cursor.fetchall()}
            cursor.execute("SELECT * FROM public.generation_recipe_references WHERE recipe_id=ANY(%s::uuid[]) ORDER BY recipe_id,position", (list(ids),))
            references = {}
            for row in cursor.fetchall():
                references.setdefault(str(row["recipe_id"]), []).append(GenerationRecipeReference(**dict(row)))
            cursor.execute("SELECT * FROM public.generation_recipe_executions WHERE recipe_id=ANY(%s::uuid[])", (list(ids),))
            executions = {}
            allowed = GenerationRecipeExecution.__dataclass_fields__
            for row in cursor.fetchall():
                executions[str(row["recipe_id"])] = GenerationRecipeExecution(**{key: row.get(key) for key in allowed})
            cursor.execute("SELECT * FROM public.generation_recipe_outputs WHERE recipe_id=ANY(%s::uuid[]) ORDER BY recipe_id,output_index", (list(ids),))
            outputs = {}
            for row in cursor.fetchall():
                outputs.setdefault(str(row["recipe_id"]), []).append(GenerationRecipeOutput(**dict(row)))
        recipes = {}
        for recipe_id, values in recipe_rows.items():
            values["references"] = tuple(references.get(recipe_id, ()))
            recipes[recipe_id] = GenerationRecipe(**values)
        return PrefetchedGenerationRecipeRepository(recipes, executions, outputs)

    def get_by_request(self, generation_request_id: str, submission_index: int = 0) -> GenerationRecipe | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT recipe_id FROM public.generation_recipes WHERE generation_request_id=%s AND submission_index=%s",
                (generation_request_id, int(submission_index)),
            )
            row = cursor.fetchone()
        return self.get(row["recipe_id"]) if row else None

    def get_execution(self, recipe_id: UUID | str) -> GenerationRecipeExecution | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.generation_recipe_executions WHERE recipe_id=%s", (recipe_id,))
            row = cursor.fetchone()
        if not row:
            return None
        allowed = GenerationRecipeExecution.__dataclass_fields__
        return GenerationRecipeExecution(**{key: row.get(key) for key in allowed})

    def outputs(self, recipe_id: UUID | str) -> tuple[GenerationRecipeOutput, ...]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM public.generation_recipe_outputs WHERE recipe_id=%s ORDER BY output_index",
                (recipe_id,),
            )
            rows = cursor.fetchall()
        return tuple(GenerationRecipeOutput(**dict(row)) for row in rows)

    def transition_execution(self, recipe_id: UUID | str, status: str, *,
                             provider_request_id: str | None = None,
                             provider_terminal_status: str | None = None,
                             error_code: str | None = None,
                             error_message: str | None = None) -> None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.generation_recipe_executions SET status=%s,
                   provider_request_id=COALESCE(%s,provider_request_id),
                   submission_started_at=CASE WHEN %s='SUBMISSION_STARTED' THEN COALESCE(submission_started_at,NOW()) ELSE submission_started_at END,
                   submitted_at=CASE WHEN %s='SUBMITTED' THEN COALESCE(submitted_at,NOW()) ELSE submitted_at END,
                   completed_at=CASE WHEN %s IN ('SUBMISSION_REJECTED','SUBMISSION_AMBIGUOUS','SUCCEEDED','FAILED','RESULT_UNKNOWN','CANCELLED') THEN NOW() ELSE completed_at END,
                   provider_terminal_status=COALESCE(%s,provider_terminal_status),error_code=%s,
                   error_message=%s,updated_at=NOW() WHERE recipe_id=%s""",
                (status,provider_request_id,status,status,status,provider_terminal_status,
                 error_code,error_message,recipe_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("Generation Recipe execution not found.")

    def associate_output(self, recipe_id: UUID | str, *, generation_result_id: str | None,
                         generated_image_id: str | None, output_index: int,
                         output_reference_hash: str | None) -> None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.generation_recipe_outputs(
                   recipe_output_id,recipe_id,generation_result_id,generated_image_id,output_index,
                   output_reference_hash) VALUES(%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(recipe_id,output_index) DO UPDATE SET
                   generation_result_id=COALESCE(generation_recipe_outputs.generation_result_id,EXCLUDED.generation_result_id),
                   generated_image_id=COALESCE(generation_recipe_outputs.generated_image_id,EXCLUDED.generated_image_id),
                   output_reference_hash=COALESCE(generation_recipe_outputs.output_reference_hash,EXCLUDED.output_reference_hash)""",
                (uuid4(),recipe_id,generation_result_id,generated_image_id,int(output_index),
                 output_reference_hash),
            )


class PrefetchedGenerationRecipeRepository:
    def __init__(self, recipes, executions, outputs):
        self.recipes = recipes
        self.executions = executions
        self.output_rows = outputs

    def get(self, recipe_id):
        return self.recipes.get(str(recipe_id))

    def get_execution(self, recipe_id):
        return self.executions.get(str(recipe_id))

    def outputs(self, recipe_id):
        return tuple(self.output_rows.get(str(recipe_id), ()))
