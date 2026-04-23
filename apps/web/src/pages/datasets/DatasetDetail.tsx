import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/atoms/Button";
import { GlassCard } from "@/components/molecules/GlassCard";
import { Modal } from "@/components/molecules/Modal";
import { FeatureProfilePanel } from "@/components/organisms/FeatureProfilePanel";
import { useT } from "@/i18n";
import { api, errorMessage, type FeatureType } from "@/lib/api/client";
import { formatBytes, formatRelative } from "@/lib/format";

export function DatasetDetail() {
  const t = useT();
  const { id = "" } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const dataset = useQuery({
    queryKey: ["datasets", id],
    queryFn: () => api.datasets.get(id),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data?.status === "ready" ? false : 1500),
  });

  const schema = useQuery({
    queryKey: ["datasets", id, "schema"],
    queryFn: () => api.datasets.schema(id),
    enabled: Boolean(id) && dataset.data?.status === "ready",
  });

  const renameMut = useMutation({
    mutationFn: (name: string) => api.datasets.rename(id, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets", id] });
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setRenameOpen(false);
    },
  });
  const deleteMut = useMutation({
    mutationFn: () => api.datasets.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      navigate("/datasets");
    },
  });
  const patchTypeMut = useMutation({
    mutationFn: (v: { name: string; type: FeatureType }) =>
      api.datasets.patchColumnType(id, v.name, v.type),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets", id, "schema"] });
      qc.invalidateQueries({ queryKey: ["datasets", id] });
    },
  });

  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-display-lg font-extrabold tracking-tight text-fg1">
            {dataset.data?.name ?? "Dataset"}
          </h1>
          <p className="mt-2 text-sm text-fg2">
            {dataset.data
              ? `${dataset.data.row_count ?? 0} rows · ${dataset.data.column_count ?? 0} columns · ${formatBytes(dataset.data.size_bytes)} · created ${formatRelative(dataset.data.created_at)}`
              : "Loading…"}
          </p>
          {patchTypeMut.isError ? (
            <p className="mt-2 text-xs font-semibold text-danger">
              {errorMessage(patchTypeMut.error, t("common.error"))}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            leftIcon={<Pencil size={14} strokeWidth={2} />}
            onClick={() => {
              setRenameValue(dataset.data?.name ?? "");
              setRenameOpen(true);
            }}
          >
            {t("datasets.rename")}
          </Button>
          <Button
            variant="ghost"
            leftIcon={<Trash2 size={14} strokeWidth={2} />}
            onClick={() => setDeleteOpen(true)}
          >
            {t("datasets.delete")}
          </Button>
          <Button
            asChild
            as="link"
            to={`/experiments/new?dataset=${id}`}
            rightIcon={<ArrowRight size={14} strokeWidth={2} />}
          >
            Use in new run
          </Button>
        </div>
      </header>

      <GlassCard>
        <h2 className="font-display text-xl font-bold text-fg1">Columns</h2>
        <p className="mt-1 text-sm text-fg2">
          Inferred feature types, missing-value summary, and unique cardinality.
          Changing a column's type re-profiles the dataset under the new
          interpretation.
        </p>
        <div className="mt-5">
          {schema.isPending ? (
            <div className="text-sm text-fg3">Loading…</div>
          ) : schema.isError ? (
            <div className="text-sm text-danger">Could not load schema.</div>
          ) : (
            <FeatureProfilePanel
              schema={schema.data}
              onChange={(name, type) => patchTypeMut.mutate({ name, type })}
            />
          )}
        </div>
      </GlassCard>

      <Modal
        open={renameOpen}
        onClose={() => (renameMut.isPending ? undefined : setRenameOpen(false))}
        title={t("datasets.rename")}
      >
        <label className="block text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
          {t("datasets.columns.name")}
        </label>
        <input
          type="text"
          value={renameValue}
          onChange={(ev) => setRenameValue(ev.target.value)}
          className="mt-2 w-full rounded-md border border-[color:var(--border)] bg-bg px-3 py-2 text-sm"
          autoFocus
        />
        {renameMut.isError ? (
          <p className="mt-3 text-xs font-semibold text-danger">
            {errorMessage(renameMut.error, t("common.error"))}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <Button
            variant="ghost"
            onClick={() => setRenameOpen(false)}
            disabled={renameMut.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => renameMut.mutate(renameValue.trim())}
            disabled={renameMut.isPending || !renameValue.trim()}
          >
            {t("datasets.rename")}
          </Button>
        </div>
      </Modal>

      <Modal
        open={deleteOpen}
        onClose={() => (deleteMut.isPending ? undefined : setDeleteOpen(false))}
        title={t("datasets.delete")}
      >
        <p className="text-sm text-fg1">
          {t("datasets.deleteConfirm")}{" "}
          <span className="font-semibold">{dataset.data?.name ?? ""}</span>
        </p>
        {deleteMut.isError ? (
          <p className="mt-3 text-xs font-semibold text-danger">
            {errorMessage(deleteMut.error, t("common.error"))}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <Button
            variant="ghost"
            onClick={() => setDeleteOpen(false)}
            disabled={deleteMut.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            variant="danger"
            onClick={() => deleteMut.mutate()}
            disabled={deleteMut.isPending}
          >
            {t("datasets.delete")}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
