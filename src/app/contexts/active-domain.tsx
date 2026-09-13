import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useCloudflareList, type CloudflareStatus } from "../lib/api";

interface ActiveDomainContextValue {
  domains: CloudflareStatus[];
  activeDomain: string;
  activeIntegration?: CloudflareStatus;
  setActiveDomain: (domain: string) => void;
  isLoading: boolean;
  isError: boolean;
  retry: () => void;
}

const ActiveDomainContext = createContext<ActiveDomainContextValue | null>(null);

export function ActiveDomainProvider({
  workspaceId,
  initialDomain = "",
  children,
}: {
  workspaceId: string;
  /** The session's default domain, used only until the domain list arrives. */
  initialDomain?: string | null;
  children: React.ReactNode;
}) {
  const query = useCloudflareList();
  const domains = query.data ?? [];
  const storageKey = `sicurre:active-domain:${workspaceId}`;
  const [selected, setSelected] = useState(() => localStorage.getItem(storageKey) ?? "");

  const activeDomain = useMemo(() => {
    if (domains.some((item) => item.zone_name?.toLowerCase() === selected.toLowerCase())) {
      return selected.toLowerCase();
    }
    const listed = (
      domains.find((item) => item.status === "active")?.zone_name
      ?? domains[0]?.zone_name
      ?? ""
    ).toLowerCase();
    if (listed || !query.isLoading || selected) return listed;
    // While the list loads, and with no stored choice to honour, open on the
    // domain the session named. The API checks ownership on every request, so
    // this only saves waiting for the list.
    return (initialDomain ?? "").trim().toLowerCase();
  }, [domains, selected, query.isLoading, initialDomain]);

  useEffect(() => {
    // Only a domain confirmed by the list is remembered.
    if (!activeDomain || query.isLoading) return;
    localStorage.setItem(storageKey, activeDomain);
  }, [activeDomain, query.isLoading, storageKey]);

  const setActiveDomain = (domain: string) => {
    const normalized = domain.trim().toLowerCase();
    if (domains.some((item) => item.zone_name?.toLowerCase() === normalized)) {
      setSelected(normalized);
    }
  };

  return (
    <ActiveDomainContext.Provider
      value={{
        domains,
        activeDomain,
        activeIntegration: domains.find(
          (item) => item.zone_name?.toLowerCase() === activeDomain,
        ),
        setActiveDomain,
        isLoading: query.isLoading,
        isError: query.isError && query.data === undefined,
        retry: () => { void query.refetch(); },
      }}
    >
      {children}
    </ActiveDomainContext.Provider>
  );
}

export function useActiveDomain(): ActiveDomainContextValue {
  const context = useContext(ActiveDomainContext);
  if (!context) throw new Error("useActiveDomain must be used inside ActiveDomainProvider");
  return context;
}
