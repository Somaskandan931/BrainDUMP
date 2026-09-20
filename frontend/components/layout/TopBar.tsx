import { ReactNode } from "react";
import { ConnectionStatus } from "./ConnectionStatus";
import { NotificationBell } from "./NotificationBell";

export function TopBar({ children }: { children: ReactNode }) {
  return (
    <header className="flex items-center justify-between border-b border-hairline px-6 py-4 md:px-8">
      <div>{children}</div>
      <div className="flex items-center gap-3">
        <NotificationBell />
        <ConnectionStatus />
      </div>
    </header>
  );
}
