/**
 * Tidy a stored e-mail preview before display.
 *
 * Plain-text parts arrive with Windows line endings, lines holding only spaces
 * and several blank lines between paragraphs; many are also double-spaced, every
 * wrapped line followed by a blank one. Each became an empty line in the preview,
 * so a short message needed a long scroll. The words are never changed: only
 * line endings, trailing spaces and blank lines are.
 */
export function tidyPreviewText(raw: string | null | undefined): string {
  if (!raw) return "";
  const text = raw
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.replace(/[ \t ]+$/, ""))
    .join("\n")
    .trim();

  const lines = text.split("\n");
  const contentLines = lines.filter((line) => line !== "").length;
  const adjacentContent = lines.some((line, index) => index > 0 && line !== "" && lines[index - 1] !== "");
  if (contentLines >= 4 && !adjacentContent) {
    // Double-spaced: one blank line is only a line break; a longer gap is a paragraph.
    return text.replace(/\n{2,}/g, (run) => (run.length >= 3 ? "\n\n" : "\n"));
  }
  return text.replace(/\n{3,}/g, "\n\n");
}
