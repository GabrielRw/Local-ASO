import { useMutation } from "@tanstack/react-query";
import { FolderDown } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { apiPost } from "@/lib/api";

interface ExportResult {
  path: string;
  locales: string[];
  skipped: { locale: string; reason: string }[];
}

/** Writes the main listing and approved drafts as a fastlane `deliver` metadata folder. */
export function FastlaneExportButton({ appId }: { appId: number }) {
  const reveal = useMutation({
    mutationFn: (path: string) => apiPost("/api/reveal", { path }),
    onError: (error) => toast.error(error.message),
  });
  const exportMetadata = useMutation({
    mutationFn: () => apiPost<ExportResult>("/api/exports/fastlane", { appId }),
    onSuccess: (result) => {
      const skipped = result.skipped.length
        ? ` ${result.skipped.length} unapproved draft${result.skipped.length === 1 ? "" : "s"} left out.`
        : "";
      toast.success(`fastlane metadata for ${result.locales.join(", ")}`, {
        description: `${result.path}.${skipped}`,
        action: { label: "Show in Finder", onClick: () => reveal.mutate(result.path) },
        duration: 10_000,
      });
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <Button
      size="sm"
      variant="outline"
      onClick={() => exportMetadata.mutate()}
      disabled={exportMetadata.isPending}
      title="Write the main listing and approved drafts as fastlane metadata/<locale>/*.txt"
    >
      <FolderDown /> {exportMetadata.isPending ? "Exporting…" : "Export to fastlane"}
    </Button>
  );
}
