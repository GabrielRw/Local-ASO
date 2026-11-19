import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { parseAppleId } from "@/lib/apple-id";
import { useInvalidate } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { BackgroundSyncDialog } from "@/components/background-sync-dialog";
import { OnboardingDialog } from "@/features/onboarding/onboarding-dialog";

// App-wide dialogs that can be opened from the sidebar and from any view.

type DialogName = "add-app" | "remove-app" | "setup" | "background-sync";
interface DialogState {
  name: DialogName | null;
  props: Record<string, unknown>;
}

interface DialogsApi {
  open: (name: DialogName, props?: Record<string, unknown>) => void;
  close: () => void;
}

const DialogsContext = createContext<DialogsApi | null>(null);

export function useDialogs(): DialogsApi {
  const value = useContext(DialogsContext);
  if (!value) throw new Error("useDialogs must be used inside DialogsProvider");
  return value;
}

export function DialogsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DialogState>({ name: null, props: {} });
  const open = useCallback((name: DialogName, props: Record<string, unknown> = {}) => setState({ name, props }), []);
  const close = useCallback(() => setState({ name: null, props: {} }), []);
  const api = useMemo(() => ({ open, close }), [open, close]);

  return (
    <DialogsContext.Provider value={api}>
      {children}
      <AddAppDialog open={state.name === "add-app"} onClose={close} />
      <RemoveAppDialog
        open={state.name === "remove-app"}
        onClose={close}
        appleId={Number(state.props.appleId ?? 0)}
        name={String(state.props.name ?? "")}
      />
      <OnboardingDialog open={state.name === "setup"} onClose={close} />
      <BackgroundSyncDialog open={state.name === "background-sync"} onClose={close} />
    </DialogsContext.Provider>
  );
}

function AddAppDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [value, setValue] = useState("");
  const [selection, select] = useSelection();
  const invalidate = useInvalidate();
  const appleId = parseAppleId(value);
  const add = useMutation({
    mutationFn: () =>
      apiPost<{ created: boolean; app: { name: string; appleAppId: number } }>("/api/apps", {
        appleId,
        country: selection.country,
      }),
    onSuccess: async (result) => {
      toast.success(result.created ? `${result.app.name} added` : `${result.app.name} is already tracked`);
      await invalidate.bootstrap();
      select({ appId: result.app.appleAppId });
      setValue("");
      onClose();
    },
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (appleId) add.mutate();
          }}
          className="grid gap-4"
        >
          <DialogHeader>
            <DialogTitle>Add an app</DialogTitle>
            <DialogDescription>
              The name and artwork are retrieved from Apple&rsquo;s public App Store data. No Apple login is needed.
            </DialogDescription>
          </DialogHeader>
          <Field data-invalid={value !== "" && !appleId}>
            <FieldLabel htmlFor="add-app-id">App Store link or ID</FieldLabel>
            <Input
              id="add-app-id"
              autoFocus
              placeholder="https://apps.apple.com/us/app/example/id123456789"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              aria-invalid={value !== "" && !appleId}
            />
            <FieldDescription>Use the App Store ID, not the bundle ID or an Apple Ads account ID.</FieldDescription>
            {add.error ? <FieldError>{add.error.message}</FieldError> : null}
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!appleId || add.isPending}>
              {add.isPending ? "Adding…" : "Add app"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RemoveAppDialog({
  open,
  onClose,
  appleId,
  name,
}: {
  open: boolean;
  onClose: () => void;
  appleId: number;
  name: string;
}) {
  const [, select] = useSelection();
  const invalidate = useInvalidate();
  const remove = useMutation({
    mutationFn: () => apiPost<{ removed: boolean; name: string }>("/api/apps/deactivate", { appleId }),
    onSuccess: async () => {
      toast.success(`${name} removed from the sidebar`);
      select({ appId: null });
      await invalidate.bootstrap();
      onClose();
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <AlertDialog open={open} onOpenChange={(next) => !next && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {name}?</AlertDialogTitle>
          <AlertDialogDescription>
            The app stops being tracked and leaves the sidebar. Its rank history stays in the local database, and
            adding it again restores it.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(event) => {
              event.preventDefault();
              remove.mutate();
            }}
            disabled={remove.isPending}
          >
            {remove.isPending ? "Removing…" : "Remove app"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
