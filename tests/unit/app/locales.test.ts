import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

type LocaleTree = Record<string, string | LocaleTree>;

function flattenLocale(tree: LocaleTree, prefix = ""): Record<string, string> {
  return Object.entries(tree).reduce<Record<string, string>>((result, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") {
      result[path] = value;
    } else {
      Object.assign(result, flattenLocale(value, path));
    }
    return result;
  }, {});
}

function readLocale(language: "fr" | "en"): Record<string, string> {
  const path = resolve(`src/app/locales/${language}.json`);
  return flattenLocale(JSON.parse(readFileSync(path, "utf8")) as LocaleTree);
}

function readApplicationSources(directory = resolve("src/app")): string {
  return readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory()) return [readApplicationSources(path)];
      return /\.(?:ts|tsx)$/.test(entry.name) ? [readFileSync(path, "utf8")] : [];
    })
    .join("\n");
}

describe("application locale dictionaries", () => {
  it("keeps French and English keys in exact parity", () => {
    expect(Object.keys(readLocale("fr")).sort()).toEqual(
      Object.keys(readLocale("en")).sort(),
    );
  });

  it("defines every literal translation key referenced by the application", () => {
    const translations = readLocale("fr");
    const sourceFiles = readApplicationSources();
    const keys = [...sourceFiles.matchAll(/\bt\("([^"]+)"/g)].map((match) => match[1]);

    // i18next v4 resolves a counted key through its _one / _other forms, so the
    // bare key legitimately has no entry of its own.
    const isDefined = (key: string) =>
      key in translations ||
      (`${key}_one` in translations && `${key}_other` in translations);

    expect(keys.filter((key) => !isDefined(key))).toEqual([]);
  });

  it("does not keep translated copy in inline locale ternaries", () => {
    const sourceFiles = readApplicationSources();
    const localeBranches = [
      ...sourceFiles.matchAll(
        /(?:isFR|lang\s*===\s*"fr"|i18n\.language\s*===\s*"fr")\s*\?\s*"([^"]+)"/g,
      ),
    ].map((match) => match[1]);

    expect(
      localeBranches.filter((value) => value !== "fr-FR"),
    ).toEqual([]);
  });

  it("uses Spam consistently for the French classification", () => {
    const frenchCopy = [
      ...Object.values(readLocale("fr")),
      readApplicationSources(),
    ].join("\n");

    expect(frenchCopy.toLocaleLowerCase("fr")).not.toMatch(/ind[ée]sirable/);
  });
});
