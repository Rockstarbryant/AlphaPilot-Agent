import { SideNav, MobileNav } from "@/components/nav";
import { TopBar } from "@/components/topbar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 min-h-screen">
      <SideNav />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 p-4 md:p-6 pb-20 md:pb-6 max-w-6xl w-full mx-auto">{children}</main>
      </div>
      <MobileNav />
    </div>
  );
}
