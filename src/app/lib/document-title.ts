export const documentTitleKeys = {
  landing: null,
  login: "page_titles.login",
  signup: "page_titles.signup",
  "verify-email": "page_titles.verify_email",
  cgu: "page_titles.cgu",
  "mentions-legales": "page_titles.legal_notice",
  confidentialite: "page_titles.privacy",
  contact: "page_titles.contact",
  dashboard: "page_titles.dashboard",
  threats: "page_titles.threats",
  quarantine: "page_titles.quarantine",
  alerts: "page_titles.notifications",
  "domain-shield": "page_titles.domain_shield",
  logs: "page_titles.admin",
  "admin-operations": "admin.views.operations",
  "admin-incidents": "admin.views.incidents",
  "admin-integrations": "admin.views.integrations",
  "admin-reviews": "admin.views.reviews",
  settings: "page_titles.settings",
  support: "page_titles.support",
} as const;

export type DocumentTitleView = keyof typeof documentTitleKeys;
export type TitleTranslator = (key: string) => string;

export function buildDocumentTitle(
  view: DocumentTitleView,
  translate: TitleTranslator,
): string {
  const titleKey = documentTitleKeys[view];
  return titleKey ? `${translate(titleKey)} | Sicurre` : "Sicurre";
}
