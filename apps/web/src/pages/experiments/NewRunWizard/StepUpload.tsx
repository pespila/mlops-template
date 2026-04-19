import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Button } from "@/components/atoms/Button";
import { FileDropzone } from "@/components/molecules/FileDropzone";
import { api, type DatasetRead } from "@/lib/api/client";
import { formatBytes, formatRelative } from "@/lib/format";
import { useWizardStore } from "@/state/wizardStore";

export function StepUpload() {
  const datasetId = useWizardStore((s) => s.datasetId);
  const setDatasetId = useWizardStore((s) => s.setDatasetId);
  const next = useWizardStore((s) => s.next);
  const qc = useQueryClient();
  const [uploadPct, setUploadPct] = useState(0);

  const datasets = useQuery({ queryKey: ["datasets"], queryFn: () => api.datasets.list() });
  const upload = useMutation({
    mutationFn: (file: File) => api.datasets.upload(file, setUploadPct),
    onSuccess: (dataset) => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setDatasetId(dataset.id);
      setUploadPct(0);
    },
  });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queryDataset = params.get("dataset");
    if (queryDataset && !datasetId) setDatasetId(queryDataset);
  }, [datasetId, setDatasetId]);

  const ready: DatasetRead[] = (datasets.data ?? []).filter((d) => d.status === "ready");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-fg1">Pick or upload a dataset</h2>
        <p className="mt-1 text-sm text-fg2">
          Existing datasets appear below. Or upload a new file - CSV, Parquet, or Excel.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_1px_1fr]">
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
            Existing datasets
          </h3>
          {datasets.isPending ? (
            <p className="text-sm text-fg3">Loading…</p>
          ) : ready.length === 0 ? (
            <p className="text-sm text-fg3">No ready datasets yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {ready.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => setDatasetId(d.id)}
                    className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                      datasetId === d.id
                        ? "border-primary bg-teal-50"
                        : "border-[color:var(--border)] bg-bg hover:bg-bg-muted"
                    }`}
                  >
                    <div className="font-medium text-fg1">{d.name}</div>
                    <div className="text-xs text-fg3">
                      {d.row_count ?? 0} rows · {formatBytes(d.size_bytes)} ·{" "}
                      {formatRelative(d.created_at)}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="hidden w-px bg-[color:var(--border)] md:block" />
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
            Upload a file
          </h3>
          <FileDropzone
            className="mt-2"
            accept={{
              "text/csv": [".csv"],
              "application/octet-stream": [".parquet"],
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
            }}
            maxSize={512 * 1024 * 1024}
            onFile={(file) => upload.mutate(file)}
            disabled={upload.isPending}
          />
          {upload.isPending ? (
            <div className="mt-3">
              <div className="h-1.5 w-full overflow-hidden rounded-pill bg-bg-muted">
                <div
                  className="h-full bg-primary transition-[width] duration-200"
                  style={{ width: `${Math.round(uploadPct * 100)}%` }}
                />
              </div>
              <p className="mt-1.5 text-xs text-fg3">Uploading… {Math.round(uploadPct * 100)}%</p>
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex justify-end">
        <Button disabled={!datasetId} onClick={next}>
          Continue →
        </Button>
      </div>
    </div>
  );
}
