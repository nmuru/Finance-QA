import type { Metadata } from "next";
import "./globals.css";
import WorkspaceCloseControl from "./workspace-close-control";
import CancelledReturnControl from "./cancelled-return-control";
import V1WorkspaceDisplayControl from "./v1-workspace-display-control";
import BackendCapacityControl from "./backend-capacity-control";
import SessionExpiryControl from "./session-expiry-control";

export const metadata: Metadata = {
  title: "Financial Analysis",
  description: "Reverse engineer GitHub repositories into financial analysis documentation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><WorkspaceCloseControl /><CancelledReturnControl /><V1WorkspaceDisplayControl /><BackendCapacityControl /><SessionExpiryControl />{children}</body></html>;
}
