import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { AlertTriangle, Home, Hospital, MessageCircle, Phone, Shield, Truck, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePushNotifications } from "@/hooks/usePushNotifications";

const nav = [
  { to: "/", label: "Dashboard", icon: Home },
  { to: "/alerts", label: "Alerts", icon: AlertTriangle },
  { to: "/hospitals", label: "Hospitals", icon: Hospital },
  { to: "/police", label: "Police", icon: Shield },
  { to: "/towing", label: "Towing", icon: Truck },
  { to: "/chat", label: "AI Assist", icon: MessageCircle },
  { to: "/contacts", label: "Contacts", icon: Users },
];

export function AppLayout() {
  const { location } = useRouterState();
  usePushNotifications();

  return (
    <div className="h-screen overflow-hidden bg-background text-foreground flex">
      <aside className="hidden md:flex w-64 shrink-0 flex-col border-r border-border bg-sidebar">
        <div className="px-6 py-5 border-b border-sidebar-border flex items-center gap-2">
          <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center font-bold text-primary-foreground">
            R
          </div>
          <div>
            <div className="font-bold tracking-tight">RoadSoS</div>
            <div className="text-[11px] text-muted-foreground">AI Road Safety</div>
          </div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {nav.map((n) => {
            const active = location.pathname === n.to;
            const Icon = n.icon;
            return (
              <Link
                key={n.to}
                to={n.to}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent"
                )}
              >
                <Icon className="h-4 w-4" />
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-sidebar-border text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Phone className="h-3.5 w-3.5" />
            Emergency: 112
          </div>
        </div>
      </aside>

      <main className="flex-1 min-w-0 min-h-0 flex flex-col">
        <header className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border bg-sidebar">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-md bg-primary flex items-center justify-center font-bold text-primary-foreground text-sm">R</div>
            <span className="font-bold">RoadSoS</span>
          </div>
        </header>
        <div className="flex-1 min-h-0 overflow-auto">
          <Outlet />
        </div>
        <nav className="md:hidden grid grid-cols-7 border-t border-border bg-sidebar">
          {nav.map((n) => {
            const active = location.pathname === n.to;
            const Icon = n.icon;
            return (
              <Link
                key={n.to}
                to={n.to}
                className={cn(
                  "flex flex-col items-center gap-0.5 py-2 text-[10px]",
                  active ? "text-primary" : "text-muted-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {n.label}
              </Link>
            );
          })}
        </nav>
      </main>
    </div>
  );
}
