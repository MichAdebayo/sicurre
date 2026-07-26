import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import App from "./App.tsx";
import "./index.css";

import frTranslation from "./locales/fr.json";
import enTranslation from "./locales/en.json";

// Initialize translations
i18n.use(initReactI18next).init({
  resources: {
    fr: { translation: frTranslation },
    en: { translation: enTranslation },
  },
  lng: localStorage.getItem("sicurre_lang") || "fr",
  fallbackLng: "fr",
  interpolation: {
    escapeValue: false,
  },
});
document.documentElement.lang = i18n.language;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
