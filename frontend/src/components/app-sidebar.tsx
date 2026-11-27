import {
  ChartNoAxesColumnIncreasing,
  ChevronsUpDown,
  Gauge,
  KeyRound,
  Megaphone,
  Monitor,
  Moon,
  Plus,
  Settings,
  Sparkles,
  Sun,
  Swords,
  Telescope,
} from "lucide-react";
import { NavLink, useLocation, useSearchParams } from "react-router";
import { AppIcon } from "@/components/app-icon";
import { SyncIndicator } from "@/components/sync-indicator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { useCurrentBootstrap } from "@/lib/queries";
import { useSelection } from "@/lib/selection";
import { useTheme, type ThemePreference } from "@/lib/theme";
import { useDialogs } from "@/components/dialogs";
import { useLicence } from "@/lib/licence";

export const appViews = [
  { path: "/audit", label: "Audit", icon: Gauge },
  { path: "/keywords", label: "Keywords", icon: KeyRound },
  { path: "/optimize", label: "Optimize", icon: Sparkles },
  { path: "/competitors", label: "Competitors", icon: Swords },
  { path: "/paid", label: "Paid search", icon: Megaphone },
] as const;

const themeOptions: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function AppSidebar() {
  const { data } = useCurrentBootstrap();
  const [selection, select] = useSelection({ appId: data?.selectedAppId, country: data?.selectedCountry });
  const [params] = useSearchParams();
  const location = useLocation();
  const { theme, setTheme } = useTheme();
  const dialogs = useDialogs();
  const licence = useLicence();
  const apps = (data?.apps ?? []).filter((app) => app.active);
  const current = apps.find((app) => app.appleAppId === selection.appId) ?? apps[0];
  const search = params.toString() ? `?${params.toString()}` : "";

  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <div className="flex items-center gap-2 px-2 pt-1 pb-2 group-data-[collapsible=icon]:hidden">
              <span className="bg-primary text-primary-foreground inline-flex size-6 items-center justify-center rounded-md">
                <ChartNoAxesColumnIncreasing className="size-3.5" strokeWidth={2.5} />
              </span>
              <span className="text-sm font-semibold tracking-tight">Local ASO</span>
            </div>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent"
                  aria-label="Switch app"
                >
                  {current ? (
                    <AppIcon name={current.name} artworkUrl={current.artworkUrl} />
                  ) : (
                    <span className="bg-muted size-8 rounded-[22%]" />
                  )}
                  <span className="grid flex-1 text-left leading-tight">
                    <span className="truncate text-sm font-medium">{current?.name ?? "No app yet"}</span>
                    <span className="text-muted-foreground truncate text-xs">
                      {current ? `App Store ID ${current.appleAppId}` : "Add an app to start"}
                    </span>
                  </span>
                  <ChevronsUpDown className="text-muted-foreground ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-72" align="start" sideOffset={6}>
                <DropdownMenuLabel className="text-muted-foreground text-xs">My apps</DropdownMenuLabel>
                {apps.map((app) => (
                  <DropdownMenuItem
                    key={app.appleAppId}
                    onSelect={() => select({ appId: app.appleAppId })}
                    className="gap-2"
                  >
                    <AppIcon name={app.name} artworkUrl={app.artworkUrl} className="size-6" />
                    <span className="truncate">{app.name}</span>
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => dialogs.open("add-app")} className="gap-2">
                  <Plus className="size-4" /> Add app
                </DropdownMenuItem>
                {current ? (
                  <DropdownMenuItem
                    onSelect={() => dialogs.open("remove-app", { appleId: current.appleAppId, name: current.name })}
                    className="text-destructive focus:text-destructive gap-2"
                  >
                    Remove {current.name}…
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>App</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {appViews.map((view) => (
                <SidebarMenuItem key={view.path}>
                  <SidebarMenuButton asChild isActive={location.pathname.startsWith(view.path)} tooltip={view.label}>
                    <NavLink to={`${view.path}${search}`}>
                      <view.icon />
                      <span>{view.label}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Research</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={location.pathname.startsWith("/niche")} tooltip="Niche research">
                  <NavLink to={`/niche${search}`}>
                    <Telescope />
                    <span>Niche research</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SyncIndicator />
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton tooltip="Settings">
                  <Settings />
                  <span>Settings</span>
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" align="start" className="w-56">
                <DropdownMenuItem onSelect={() => dialogs.open("setup")}>Setup guide &amp; AI agent…</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => dialogs.open("background-sync")}>Background checks…</DropdownMenuItem>
                {licence.data?.desktop ? (
                  <DropdownMenuItem onSelect={() => dialogs.open("licence")}>
                    {licence.data.paidEdition ? "Licence & updates…" : "Updates…"}
                    {licence.data.paidEdition && !licence.data.licensed ? (
                      <span className="text-muted-foreground ml-auto text-xs">Free</span>
                    ) : null}
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-muted-foreground text-xs">Appearance</DropdownMenuLabel>
                {themeOptions.map((option) => (
                  <DropdownMenuItem key={option.value} onSelect={() => setTheme(option.value)} className="gap-2">
                    <option.icon className="size-4" />
                    {option.label}
                    {theme === option.value ? <span className="text-muted-foreground ml-auto text-xs">Active</span> : null}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
