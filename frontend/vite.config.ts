import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import type { ServerResponse } from "node:http";
import { extname, resolve } from "node:path";

import { type Connect, type Plugin } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { generationLibraryMediaUrl } from "./src/infrastructure/api/generationLibraryMedia";

type LibraryRecord = {
  image_id: string;
  output_reference: string;
  provider_id: string;
  prompt_text: string;
  creative_mode?: string | null;
  generation_date?: string;
  created_at?: string;
  status: string;
  generation_metadata?: Record<string, unknown>;
  updated_at?: string | null;
  [key: string]: unknown;
};

const libraryPath = resolve(
  import.meta.dirname,
  "../data/generation_library/generated_images.json",
);

function readLibrary(): LibraryRecord[] {
  return JSON.parse(readFileSync(libraryPath, "utf8")) as LibraryRecord[];
}

function activeRecordWithAvailableMedia(record: LibraryRecord) {
  if (record.status !== "active") return null;
  const primary = record.output_reference.trim();
  if (/^(https?:\/\/|data:)/i.test(primary) || existsSync(primary)) return record;

  const metadata = (record.generation_metadata ?? {}) as Record<string, unknown>;
  const requestMetadata = (metadata.request_metadata ?? {}) as Record<string, unknown>;
  const candidates = [
    metadata.output_reference,
    requestMetadata.output_reference,
    metadata.original_output_reference,
  ];
  const replacement = candidates
    .map((value) => String(value ?? "").trim())
    .find(
      (value) =>
        value &&
        value !== primary &&
        !/^(https?:\/\/|data:)/i.test(value) &&
        !/[\\/](posted|archive)[\\/]/i.test(value) &&
        existsSync(value),
    );
  return replacement ? { ...record, output_reference: replacement } : null;
}

function mediaType(path: string) {
  return (
    {
      ".avif": "image/avif",
      ".gif": "image/gif",
      ".jpeg": "image/jpeg",
      ".jpg": "image/jpeg",
      ".png": "image/png",
      ".webp": "image/webp",
    }[extname(path).toLowerCase()] ?? "application/octet-stream"
  );
}

function sendJson(response: ServerResponse, value: unknown, statusCode = 200) {
  response.statusCode = statusCode;
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.end(JSON.stringify(value));
}

function libraryMiddleware(): Connect.NextHandleFunction {
  return (request, response, next) => {
    if (!request.url?.startsWith("/api/generation-library")) {
      next();
      return;
    }

    try {
      const url = new URL(request.url, "http://creator-os.local");
      const records = readLibrary();
      const availableRecords = records
        .map(activeRecordWithAvailableMedia)
        .filter((record): record is LibraryRecord => record !== null);
      const mediaMatch = url.pathname.match(
        /^\/api\/generation-library\/media\/([^/]+)$/,
      );
      if (mediaMatch) {
        const record = availableRecords.find(
          ({ image_id }) => image_id === decodeURIComponent(mediaMatch[1]),
        );
        if (!record || /^https?:\/\//i.test(record.output_reference)) {
          response.statusCode = 404;
          response.end("Media not found");
          return;
        }
        const details = statSync(record.output_reference);
        response.statusCode = 200;
        response.setHeader("Content-Type", mediaType(record.output_reference));
        response.setHeader("Content-Length", details.size);
        response.setHeader("Cache-Control", "private, no-cache, must-revalidate");
        response.setHeader("ETag", `"${details.size.toString(16)}-${details.mtimeMs.toString(16)}"`);
        createReadStream(record.output_reference).pipe(response);
        return;
      }

      const actionMatch = url.pathname.match(
        /^\/api\/generation-library\/([^/]+)\/actions\/(publish|edit|photoshoot|video|register|delete)$/,
      );
      if (actionMatch) {
        if (request.method !== "POST") {
          sendJson(response, { error: "Method not allowed" }, 405);
          return;
        }
        const imageId = decodeURIComponent(actionMatch[1]);
        const action = actionMatch[2];
        const record = records.find(({ image_id }) => image_id === imageId);
        if (!record) {
          sendJson(response, { error: "Generation not found" }, 404);
          return;
        }
        // TODO(react-migration): Bridge these commands to GenerationLibraryService
        // and their existing Streamlit workflow/session orchestration. The Vite
        // adapter intentionally does not reproduce backend business logic.
        sendJson(response, {
          error: `${action} is not yet connected to the Creator OS service adapter.`,
          todo: true,
        }, 501);
        return;
      }

      if (url.pathname !== "/api/generation-library") {
        response.statusCode = 404;
        response.end("Not found");
        return;
      }

      const search = (url.searchParams.get("search") ?? "").trim().toLowerCase();
      const provider = url.searchParams.get("provider") ?? "";
      const mode = url.searchParams.get("mode") ?? "";
      const sort = url.searchParams.get("sort") ?? "newest";
      const page = Math.max(1, Number(url.searchParams.get("page")) || 1);
      const pageSize = 18;
      const activeRecords = availableRecords;
      const providers = [...new Set(activeRecords.map(({ provider_id }) => provider_id))].sort();
      const modes = [
        ...new Set(
          activeRecords
            .map(({ creative_mode }) => creative_mode)
            .filter((value): value is string => Boolean(value)),
        ),
      ].sort();
      const filtered = activeRecords.filter((record) => {
        if (provider && record.provider_id !== provider) return false;
        if (mode && record.creative_mode !== mode) return false;
        const haystack = [
          record.image_id,
          record.provider_id,
          record.prompt_text,
          record.creative_mode ?? "",
          String(record.generation_job_id ?? ""),
          String(record.prompt_plan_id ?? ""),
        ]
          .join(" ")
          .toLowerCase();
        return !search || haystack.includes(search);
      });
      filtered.sort((left, right) => {
        if (sort === "provider") {
          return left.provider_id.localeCompare(right.provider_id);
        }
        const leftDate = left.generation_date || left.created_at || "";
        const rightDate = right.generation_date || right.created_at || "";
        return sort === "oldest"
          ? leftDate.localeCompare(rightDate)
          : rightDate.localeCompare(leftDate);
      });
      const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
      const currentPage = Math.min(page, totalPages);
      const start = (currentPage - 1) * pageSize;
      const pageRecords = filtered.slice(start, start + pageSize).map((record) => ({
        ...record,
        image_url: /^https?:\/\//i.test(record.output_reference)
          ? record.output_reference
          : generationLibraryMediaUrl(record),
      }));
      sendJson(response, {
        records: pageRecords,
        total: filtered.length,
        page: currentPage,
        pageSize,
        totalPages,
        providers,
        modes,
      });
    } catch (error) {
      sendJson(response, {
        error: error instanceof Error ? error.message : "Library read failed",
      }, 500);
    }
  };
}

function generationLibraryAdapter(): Plugin {
  const install = (server: { middlewares: Connect.Server }) => {
    server.middlewares.use(libraryMiddleware());
  };
  return {
    name: "creator-os-generation-library-adapter",
    configureServer: install,
    configurePreviewServer: install,
  };
}

export default defineConfig({
  plugins: [react(), generationLibraryAdapter()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    proxy: {
      "/api/v1": "http://127.0.0.1:8001",
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    proxy: {
      "/api/v1": "http://127.0.0.1:8001",
    },
  },
});
