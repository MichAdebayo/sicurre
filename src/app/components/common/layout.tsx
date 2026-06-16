import React from "react";
import { Navbar } from "./navbar";

interface LayoutProps {
  activeTab: "dashboard" | "threats" | "smail" | "datasets" | "settings";
  setActiveTab: (tab: "dashboard" | "threats" | "smail" | "datasets" | "settings") => void;
  onLogout: () => void;
  children: React.ReactNode;
}

export function Layout({ activeTab, setActiveTab, onLogout, children }: LayoutProps) {
  return (
    <div className="min-h-screen flex bg-slate-50 font-sans">
      {/* Sidebar Navigation */}
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} onLogout={onLogout} />

      {/* Main Viewport Content Area */}
      <main className="flex-1 overflow-y-auto p-8 lg:p-10">
        <div className="max-w-7xl mx-auto space-y-8">
          {children}
        </div>
      </main>
    </div>
  );
}
