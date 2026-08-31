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
  children,
}: {
  workspaceId: string;
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
    return (
      domains.find((item) => item.status === "active")?.zone_name
      ?? domains[0]?.zone_name
      ?? ""
    ).toLowerCase();
  }, [domains, selected]);

  useEffect(() => {
    if (!activeDomain) return;
    localStorage.setItem(storageKey, activeDomain);
  }, [activeDomain, storageKey]);

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
