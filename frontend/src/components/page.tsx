import type { ReactNode } from "react";
import { AppHeader } from "@/components/app-header";
import { cn } from "@/lib/utils";

/** Standard page frame: sticky header, then a centered content column. */
export function Page({
  title,
  actions,
  children,
  className,
  storefrontPickers = true,
  countryPicker = true,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** App-independent pages (Niche research) hide the storefront and device pickers. */
  storefrontPickers?: boolean;
  /** App-wide pages (Opportunities) cover every storefront: device toggle only. */
  countryPicker?: boolean;
}) {
  return (
    <>
      <AppHeader title={title} actions={actions} storefrontPickers={storefrontPickers} countryPicker={countryPicker} />
      <main className={cn("mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 p-4 md:p-6", className)}>{children}</main>
    </>
  );
}
