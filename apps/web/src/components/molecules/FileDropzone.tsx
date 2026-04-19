import { UploadCloud } from "lucide-react";
import { useCallback } from "react";
import { useDropzone, type Accept } from "react-dropzone";

import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";

interface FileDropzoneProps {
  accept?: Accept;
  maxSize?: number;
  onFile: (file: File) => void;
  className?: string;
  disabled?: boolean;
  hint?: string;
}

export function FileDropzone({
  accept,
  maxSize,
  onFile,
  className,
  disabled,
  hint,
}: FileDropzoneProps) {
  const onDrop = useCallback(
    (files: File[]) => {
      if (files.length === 0) return;
      onFile(files[0]);
    },
    [onFile],
  );

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept,
    maxSize,
    multiple: false,
    disabled,
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "relative flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed",
        "border-[color:var(--border-primary)] bg-bg-muted px-6 py-10 text-center",
        "cursor-pointer transition-colors duration-[var(--dur)] ease-[var(--ease-out)]",
        isDragActive && "border-primary bg-teal-50",
        isDragReject && "border-danger",
        disabled && "opacity-50 cursor-not-allowed",
        className,
      )}
    >
      <input {...getInputProps()} />
      <div className="inline-flex h-12 w-12 items-center justify-center rounded-md bg-gradient-primary text-white shadow-glow">
        <UploadCloud size={24} strokeWidth={2} aria-hidden="true" />
      </div>
      <div>
        <p className="font-display text-base font-semibold text-fg1">
          {isDragActive ? "Drop the file to upload" : "Drop a file, or click to browse"}
        </p>
        <p className="mt-1 text-sm text-fg2">
          {hint ?? "CSV, Parquet, or Excel"}
          {maxSize ? ` · up to ${formatBytes(maxSize)}` : ""}
        </p>
      </div>
    </div>
  );
}
