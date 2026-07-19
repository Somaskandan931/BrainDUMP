import { ReactNode } from "react";
import { ConnectionStatus } from "./ConnectionStatus";

export function TopBar({ children }: { children: ReactNode }) {
  return (
    <header className="flex items-center justify-between border-b border-hairline px-6 py-4 md:px-8">
      <div>{children}</div>
      <ConnectionStatus />
    </header>
  );
}
