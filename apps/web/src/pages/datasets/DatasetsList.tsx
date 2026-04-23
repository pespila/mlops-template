import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/atoms/Button";
import { FileDropzone } from "@/components/molecules/FileDropzone";
import { GlassCard } from "@/components/molecules/GlassCard";
import { Modal } from "@/components/molecules/Modal";
import { useT } from "@/i18n";
import { api, errorMessage, type DatasetRead } from "@/lib/api/client";
import { formatBytes, formatRelative } from "@/lib/format";

function StatusPill({ status }: { status: DatasetRead["status"] }) {
  const classes =
    status === "ready"
      ? "bg-teal-50 text-teal-900"
      : status === "failed"
        ? "bg-bg-muted text-danger"
        : "bg-bg-muted text-fg2";
  return (
    <span
      className={`inline-flex items-center rounded-pill px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] ${classes}`}
    >
      {status}
    </span>
  );
}

export function DatasetsList() {
  const t = useT();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);

  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.datasets.list(),
  });

  const upload = useMutation({
    mutationFn: (file: File) => api.datasets.upload(file, setUploadPct),
    onSuccess: (dataset) => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setUploadOpen(false);
      setUploadPct(0);
      navigate(`/datasets/${dataset.id}`);
    },
  });

  const [toDelete, setToDelete] = useState<DatasetRead | null>(null);
  const deleteMut = useMutation({
    mutationFn: (ds: DatasetRead) => api.datasets.remove(ds.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setToDelete(null);
    },
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
            {t("datasets.title")}
          </h1>
          <p className="mt-2 max-w-xl text-fg2">{t("datasets.subtitle")}</p>
        </div>
        <Button leftIcon={<Upload size={16} strokeWidth={2} />} onClick={() => setUploadOpen(true)}>
          {t("datasets.uploadCta")}
        </Button>
      </header>

      <GlassCard className="!p-0 overflow-hidden">
        {datasetsQuery.isPending ? (
          <div className="p-6 text-sm text-fg3">{t("common.loading")}…</div>
        ) : datasetsQuery.isError ? (
          <div className="p-6 text-sm text-danger">{t("common.error")}</div>
        ) : datasetsQuery.data.length === 0 ? (
          <div className="p-8 text-center text-sm text-fg3">{t("datasets.empty")}</div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="bg-bg-muted text-left">
              <tr>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("datasets.columns.name")}
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("datasets.columns.rows")}
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("datasets.columns.cols")}
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("datasets.columns.status")}
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  Size
                </th>
                <th className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("datasets.columns.created")}
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
                  {t("common.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--border)]">
              {datasetsQuery.data.map((ds) => (
                <tr
                  key={ds.id}
                  className="cursor-pointer hover:bg-bg-muted/60"
                  onClick={() => navigate(`/datasets/${ds.id}`)}
                >
                  <td className="px-6 py-3 font-medium text-fg1">{ds.name}</td>
                  <td className="px-6 py-3 text-right font-mono text-xs text-fg2">
                    {ds.row_count ?? "—"}
                  </td>
                  <td className="px-6 py-3 text-right font-mono text-xs text-fg2">
                    {ds.column_count ?? "—"}
                  </td>
                  <td className="px-6 py-3">
                    <StatusPill status={ds.status} />
                  </td>
                  <td className="px-6 py-3 text-xs text-fg2">{formatBytes(ds.size_bytes)}</td>
                  <td className="px-6 py-3 text-xs text-fg2">{formatRelative(ds.created_at)}</td>
                  <td className="px-6 py-3 text-right">
                    <button
                      type="button"
                      aria-label={t("datasets.delete")}
                      title={t("datasets.delete")}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        setToDelete(ds);
                      }}
                      className="inline-flex h-7 w-7 items-center justify-center rounded-md text-fg2 hover:bg-bg-muted hover:text-danger"
                    >
                      <Trash2 size={14} strokeWidth={2} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>

      <Modal
        open={uploadOpen}
        onClose={() => (upload.isPending ? undefined : setUploadOpen(false))}
        title={t("datasets.uploadCta")}
      >
        <FileDropzone
          accept={{
            "text/csv": [".csv"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
            "application/octet-stream": [".parquet"],
          }}
          maxSize={512 * 1024 * 1024}
          onFile={(file) => upload.mutate(file)}
          disabled={upload.isPending}
        />
        {upload.isPending ? (
          <div className="mt-4">
            <div className="h-1.5 w-full overflow-hidden rounded-pill bg-bg-muted">
              <div
                className="h-full bg-primary transition-[width] duration-200"
                style={{ width: `${Math.round(uploadPct * 100)}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-fg3">Uploading… {Math.round(uploadPct * 100)}%</p>
          </div>
        ) : null}
        {upload.isError ? (
          <p className="mt-3 text-xs font-semibold text-danger">{t("common.error")}</p>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(toDelete)}
        onClose={() => (deleteMut.isPending ? undefined : setToDelete(null))}
        title={t("datasets.delete")}
      >
        <p className="text-sm text-fg1">
          {t("datasets.deleteConfirm")}{" "}
          <span className="font-semibold">{toDelete?.name ?? ""}</span>
        </p>
        {deleteMut.isError ? (
          <p className="mt-3 text-xs font-semibold text-danger">
            {errorMessage(deleteMut.error, t("common.error"))}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <Button
            variant="ghost"
            onClick={() => setToDelete(null)}
            disabled={deleteMut.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            variant="danger"
            onClick={() => (toDelete ? deleteMut.mutate(toDelete) : undefined)}
            disabled={deleteMut.isPending}
          >
            {t("datasets.delete")}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
