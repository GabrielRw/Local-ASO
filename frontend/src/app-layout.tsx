import { useEffect, useRef } from "react";
import { Outlet } from "react-router";
import { AppSidebar } from "@/components/app-sidebar";
import { DialogsProvider, useDialogs } from "@/components/dialogs";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useCurrentBootstrap } from "@/lib/queries";

/** Opens the setup guide once per launch while the server says setup is unfinished. */
function FirstRunGuide() {
  const { data } = useCurrentBootstrap();
  const dialogs = useDialogs();
  const shown = useRef(false);
  useEffect(() => {
    if (!shown.current && data?.onboarding.shouldOpen) {
      shown.current = true;
      dialogs.open("setup");
    }
  }, [data?.onboarding.shouldOpen, dialogs]);
  return null;
}

export function AppLayout() {
  return (
    <DialogsProvider>
      <FirstRunGuide />
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="min-w-0">
          <Outlet />
        </SidebarInset>
      </SidebarProvider>
    </DialogsProvider>
  );
}
